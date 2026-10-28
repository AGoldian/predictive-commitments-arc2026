"""Host-only bridge for exact pinned Franzen/TAAF/SDK infrastructure (MIT-0).

This module installs no hooks on import and starts no game/model/network call.
The source builder supplies the only runtime call sites. Queue callbacks are
optional host interfaces; no allocation policy or window collector is installed.
"""
from __future__ import annotations

from .automatic_reset_prefix_v1 import assert_sdk_dispatch, host_prefix_logical_preflight

from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
import hashlib
import importlib
import importlib.metadata
import json
import math
from pathlib import Path
import threading
import uuid

from .host_accounting import AccountingError, HostAccountingRegistry, HostEpisodeAnchor, HostIdentity, InitialResetCapture
from .prediction_adapter import PublicObservation, action_from_sdk, canonical_action, observation_from_sdk
from .franzen_host_accounting_v2 import HostStopped

BRIDGE_VERSION = 3


SDK_VERSION = "0.9.8"
SDK_SHA256 = {
    "base": "42973618f223096d6269422352980e85bdf6b2b51dcb42e7390f96164b0f994f",
    "local_wrapper": "77e0a39f583e148bfc785f933d111ed4d8653d134def55b204dda3064e93bbd2",
    "remote_wrapper": "ebe8fd0a5ab2d5f65600f072fb22cf1de21c347a55b8c5ef569d6d7305c520e5",
    "wrapper": "deaf07a628fb2e0f743366de4967110d4c06bafa21c5b61561d9ca02f31055ee",
    "scorecard": "1cc830e48008bec60b8a98ae14d3e9312e8408f102a9878bad42744aa9e489b7",
}
_FACTORY = ContextVar("arc_paper_factory", default=None)
_ACTION = ContextVar("arc_paper_action", default=None)
_WRAPPER_LOCK = threading.RLock()
_WRAPPER_HOOKS = {}
_BOUND_ENVIRONMENTS = {}


@dataclass(frozen=True)
class HostBoundarySnapshot:
    binding_sha256: str
    session_id: str
    action_episode: str
    accounting_sequence: int
    accepted_target_tokens: int
    sdk_calls_executed: int
    taaf_history_commits: int
    action_sequence: int
    public_observation_sha256: str
    logical_sequence: int
    last_logical_succeeded: bool | None
    successful_logical_requests: int


def verify_sdk_infrastructure():
    """Verify only SDK infrastructure bytes/version, never environment files."""
    distribution = importlib.metadata.distribution('arc-agi')
    if distribution.version != SDK_VERSION:
        raise AccountingError("sdk_version_mismatch")
    paths = {name: Path(distribution.locate_file('arc_agi/' + name + '.py')).resolve() for name in SDK_SHA256}
    for name, path in paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != SDK_SHA256[name]:
            raise AccountingError('sdk_source_mismatch')
    modules = {name: importlib.import_module("arc_agi." + name) for name in SDK_SHA256}
    for name, module in modules.items():
        if (Path(module.__file__).resolve() != paths[name]
                or hashlib.sha256(paths[name].read_bytes()).hexdigest() != SDK_SHA256[name]):
            raise AccountingError("sdk_source_mismatch")
    return (modules["local_wrapper"].LocalEnvironmentWrapper, modules["remote_wrapper"].RemoteEnvironmentWrapper)


@dataclass
class _GameStart:
    fleet: object
    game: object
    anchor: HostEpisodeAnchor
    capture: InitialResetCapture
    wrapper: object = None
    resets: int = 0
    environment: object = None
    game_run: object = None
    initial_observation: object = None
    complete: bool = False


@dataclass(frozen=True)
class SessionBinding:
    anchor: HostEpisodeAnchor
    session_id: str
    game: object = field(repr=False)
    game_run: object = field(repr=False)
    environment: object = field(repr=False)
    session: object = field(repr=False)
    agent: object = field(repr=False)
    ledger: object = field(repr=False)
    fleet: object = field(repr=False)

    def boundary_snapshot(self, *, terminal=False):
        return self.fleet.boundary_snapshot(self, terminal=terminal)


@dataclass
class _ActionCall:
    binding: SessionBinding
    history_before: int
    dispatched: bool = False
    sdk_returned: bool = False
    sdk_entered: bool = False
    known_refused: bool = False
    public_observation: object = None
    commitment: object = None
    depth: int = 0


def _ledger_invalid(ledger, reason):
    with ledger._lock:
        try:
            ledger._fail(reason)
        except AccountingError:
            pass


class FleetAccounting:
    """One host registry for one fleet, including pre-factory reservations.

    Callbacks run only on the host. before_exchange is at a logical request
    preflight, on_bind before session.play, on_session_close after settlement.
    A callback may block for admission, but any BaseException latches failure.
    No callback is invoked by raw HTTP return/usage to release a queue lease.
    """
    def __init__(self, log_root=None, *, stop_event=None, observers=(), sdk_verifier=verify_sdk_infrastructure,
                 before_exchange=None, on_bind=None, on_session_close=None):
        self.log_root = Path(log_root) if log_root is not None else Path.cwd() / "arc_paper_host_accounting"
        self.stop_event = stop_event if stop_event is not None else threading.Event()
        self.observers = tuple(observers)
        self.sdk_verifier = sdk_verifier
        self.before_exchange, self.on_bind, self.on_session_close = before_exchange, on_bind, on_session_close
        self.registry = HostAccountingRegistry()
        self._lock = threading.RLock()
        self._games, self._agents, self._sessions = {}, {}, {}
        self._closed, self._tool_depth = set(), {}
        self._logical, self._final_snapshots = {}, {}
        self.invalid_reason = None
        self._common_clock = None
        self._common_admission = None

    def prepare_common_clock(self, solver, config, clock):
        """Join the actual post-copy solver before factories, without a future queue."""
        with self._lock:
            configuration = getattr(solver, '_arc_paper_common_configuration', None)
            if (self._common_clock is not None or self._games or not callable(clock)
                    or type(configuration) is not tuple or len(configuration) != 5
                    or configuration[0] is not config or configuration[4] is not self
                    or getattr(solver, '_stop_event', None) is not self.stop_event):
                self.fail('invalid_common_clock_setup')
            config.validate()
            deadline = config.admission_deadline_monotonic
            self._common_clock = (solver, configuration, config, clock, deadline)
        self._assert_common_clock()

    def common_clock(self, solver, config):
        self._assert_common_clock()
        record = self._common_clock
        if record is None or record[0] is not solver or record[2] is not config:
            self.fail('missing_joined_common_clock')
        return record[3]

    def join_common_admission(self, admission, solver, config, clock):
        self.common_clock(solver, config)
        with self._lock:
            if (self._common_admission is not None or self._common_clock[3] is not clock
                    or admission.solver is not solver or admission.accounting is not self
                    or admission.config is not config or admission.clock is not clock):
                self.fail('invalid_common_admission_clock_join')
            self._common_admission = admission

    def _assert_common_clock(self, binding=None):
        """Current host object identities are proof; no caller supplied stopped flag."""
        record = self._common_clock
        solver = getattr(binding.session, 'solver', None) if binding is not None else None
        configured = getattr(solver, '_arc_paper_common_configuration', None) if solver is not None else None
        if record is None:
            if configured is not None:
                self.fail('common_configuration_without_joined_clock')
            return  # Explicit noncommon path retains v2 session/stop semantics.
        owner, configuration, config, clock, deadline = record
        if (getattr(owner, '_arc_paper_common_configuration', None) is not configuration
                or configuration[0] is not config or configuration[4] is not self
                or getattr(owner, '_stop_event', None) is not self.stop_event
                or config.admission_deadline_monotonic != deadline):
            self.fail('common_clock_owner_changed')
        if binding is not None:
            admission = self._common_admission
            if (binding.fleet is not self or solver is not owner
                    or admission is None or getattr(owner, '_arc_paper_fleet_admission', None) is not admission
                    or admission.solver is not owner or admission.accounting is not self
                    or admission.config is not config or admission.clock is not clock):
                self.fail('bound_common_admission_owner_changed')
        try:
            now = clock()
        except BaseException:
            self.fail('common_clock_read_failed')
        if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
            self.fail('invalid_common_clock_read')
        if now >= deadline:
            self.stop_event.set()
            if binding is not None:
                binding.session.stop_event.set()
            raise HostStopped('common_admission_deadline')

    def _factory_preflight(self):
        # Before a session exists the configured played solver owns this clock.
        # An initial RESET already entered may still finish and receive its real receipt.
        self._assert_common_clock()
        if self._common_clock is not None and self.stop_event.is_set():
            raise HostStopped('common_factory_stopped')

    def fail(self, reason):
        with self._lock:
            self.invalid_reason = self.invalid_reason or reason
            self.stop_event.set()
            bindings = tuple(self._sessions.values())
        for binding in bindings:
            binding.session.stop_event.set()
            _ledger_invalid(binding.ledger, self.invalid_reason)
        raise AccountingError(self.invalid_reason)

    def _callback(self, callback, *args):
        if callback is not None:
            try:
                return callback(*args)
            except HostStopped:
                self.stop_event.set()
                raise
            except BaseException:
                self.fail("host_boundary_callback_failed")

    def begin_game(self, game):
        self._factory_preflight()
        with self._lock:
            invalid = self.invalid_reason or self.stop_event.is_set() or id(game) in self._games or game.game_run is not None
            if not invalid:
                anchor = HostEpisodeAnchor("run-" + uuid.uuid4().hex)
                capture = InitialResetCapture(run_id=anchor.run_id, run=anchor, capture_id="init-" + uuid.uuid4().hex,
                    log_path=self.log_root / (anchor.run_id + "-initial.jsonl"), stop_event=self.stop_event)
                start = _GameStart(self, game, anchor, capture)
                self._games[id(game)] = start
                return start
        self.fail("invalid_game_factory_start")

    def make(self, game, factory, *args, **kwargs):
        start = self._games.get(id(game))
        if start is None or start.game is not game or start.environment is not None or _FACTORY.get() is not None:
            self.fail("missing_or_nested_factory_anchor")
        try:
            self._factory_preflight()
            classes = self.sdk_verifier()
            _install_sdk_observers(classes)
            token = _FACTORY.set(start)
            try:
                env = factory(*args, **kwargs)
            finally:
                _FACTORY.reset(token)
            if env is None or start.resets != 1 or env is not start.wrapper or not start.capture.valid:
                self.fail("factory_reset_environment_mismatch")
            start.environment = env
            return env
        except HostStopped:
            raise
        except BaseException:
            self.fail("factory_reset_capture_failed")

    def finish_game(self, game):
        start = self._games.get(id(game))
        if (start is None or start.game is not game or start.complete or game.game_run is None
                or getattr(game, "env", None) is not start.environment or start.environment is None
                or len(game.game_run.history) != 0 or not start.capture.valid or start.initial_observation is None):
            self.fail("game_run_factory_join_failed")
        actual = observation_from_sdk(game.current_state.raw, episode=start.anchor.run_id, sequence=0)
        if actual.sha256 != start.initial_observation.sha256:
            self.fail('factory_reset_initial_observation_mismatch')
        start.game_run, start.complete = game.game_run, True

    def bind_session(self, session):
        game, agent = session.game, session.analyzer
        start = self._games.get(id(game))
        error = None
        with self._lock:
            if (start is None or not start.complete or start.game is not game or game.game_run is not start.game_run
                    or getattr(game, "env", None) is not start.environment or self.invalid_reason
                    or self.stop_event.is_set() or session.stop_event.is_set()):
                error = "session_factory_join_failed"
            elif id(agent) in self._agents or id(session) in self._sessions:
                error = "analyzer_or_session_already_reserved"
            # Reserve BEFORE _ensure_session can clear shared history or IDs.
            else:
                self._agents[id(agent)] = (agent, session)
        if error:
            self.fail(error)
        binding = None
        try:
            from .franzen_prediction_runtime import _adapter
            adapter = _adapter(session)
            agent._ensure_session(session.state_path)
            identity = HostIdentity(start.anchor.run_id, "session-" + uuid.uuid4().hex,
                start.anchor, session, agent, session.state_path, adapter.current.episode,
                session._arc_paper_evidence_history.episode, agent._arc_paper_agent_id, agent._arc_paper_episode_id)
            ledger = self.registry.bind(identity, log_path=self.log_root / (start.anchor.run_id + "-events.jsonl"),
                stop_event=session.stop_event, initialization=start.capture, observers=self.observers)
            binding = SessionBinding(start.anchor, identity.session_id, game, start.game_run,
                start.environment, session, agent, ledger, self)
            with self._lock:
                self._sessions[id(session)] = binding
                self._tool_depth[id(agent)] = 0
                self._logical[id(agent)] = dict(pending=False, sequence=0, last_success=None, successes=0)
            with _WRAPPER_LOCK:
                prior = _BOUND_ENVIRONMENTS.get(id(start.environment))
                if prior is None:
                    _BOUND_ENVIRONMENTS[id(start.environment)] = binding
            if prior is not None:
                self.fail("sdk_environment_already_bound")
            self._callback(self.on_bind, binding)
            return binding
        except BaseException as primary:
            # bind_session runs before session.play's terminal finally. Only a
            # binding actually published by THIS invocation is offered to close.
            # This attempt cannot grant semantic settlement or certify custody.
            try:
                session.stop_event.set()
            except BaseException:
                pass
            try:
                self.fail("session_binding_failed")
            except BaseException:
                pass
            if (binding is not None and self._sessions.get(id(session)) is binding
                    and binding.session is session and binding.fleet is self):
                try:
                    self.session_close(session, failed=True)
                except BaseException as secondary:
                    raise primary from secondary
            raise

    def binding_for_agent(self, agent):
        owner = self._agents.get(id(agent))
        binding = self._sessions.get(id(owner[1])) if owner is not None and owner[0] is agent else None
        if binding is None or binding.agent is not agent:
            self.fail("missing_joined_host_agent")
        return binding

    def identity(self, binding, *, terminal=False):
        session, agent = binding.session, binding.agent
        if (self._sessions.get(id(session)) is not binding or session.analyzer is not agent
                or session.game is not binding.game or binding.game.game_run is not binding.game_run
                or getattr(binding.game, "env", None) is not binding.environment
                or getattr(agent, "_arc_paper_state_path", None) != session.state_path
                or id(session) in self._closed):
            self.fail("current_host_join_changed")
        callback = getattr(agent, "_step_env_callback", None)
        if callback is not None and getattr(callback, "__self__", None) is not session:
            self.fail("foreign_step_callback")
        if not terminal and self.invalid_reason:
            raise AccountingError(self.invalid_reason)
        if not terminal and (self.stop_event.is_set() or session.stop_event.is_set()):
            raise HostStopped("host_stop_requested")
        if not terminal:
            self._assert_common_clock(binding)
        adapter = session._arc_paper_prediction_adapter
        if adapter.current is None and not terminal:
            self.fail('missing_current_public_observation')
        episode = adapter.current.episode if adapter.current is not None else binding.ledger.binding.action_episode
        return HostIdentity(binding.anchor.run_id, binding.session_id, binding.anchor, session, agent,
            session.state_path, episode, session._arc_paper_evidence_history.episode,
            agent._arc_paper_agent_id, agent._arc_paper_episode_id)

    def boundary_snapshot(self, binding, *, terminal=False):
        if terminal and id(binding.session) in self._closed:
            snapshot = self._final_snapshots.get(id(binding.session))
            if snapshot is None or not binding.ledger.valid or self.invalid_reason:
                raise AccountingError("no_valid_terminal_boundary")
            return snapshot
        proof = self.identity(binding, terminal=terminal)
        ledger, session, agent = binding.ledger, binding.session, binding.agent
        ledger.check_request_allowed(proof)
        adapter, history = session._arc_paper_prediction_adapter, session._arc_paper_evidence_history
        logical = self._logical[id(agent)]
        if (adapter.pending is not None or adapter.current is None or ledger._action is not None
                or self._tool_depth.get(id(agent), 0) != 0 or _ACTION.get() is not None or logical['pending']):
            self.fail("unsettled_tool_or_prediction_boundary")
        totals, current = ledger.totals, adapter.current
        actual = observation_from_sdk(binding.game.current_state.raw, episode=current.episode, sequence=current.sequence)
        executed = {row['transition_id'] for row in ledger.events
                    if row['event'] == 'action_receipt' and row['execution'] == 'executed'}
        if (session._arc_paper_evidence_history_stopped or history.episode != current.episode
                or current.episode != ledger.binding.action_episode or history.level != current.levels_completed
                or history.actions != totals.post_start_sdk_calls_executed or current.sequence != history.actions
                or len(binding.game_run.history) != totals.taaf_history_commits
                or not executed.issubset(history.seen)
                or actual.frames[-1:] != current.frames[-1:]
                or (current.state is not None and current.state != actual.state)
                or (current.levels_completed is not None and current.levels_completed != actual.levels_completed)):
            self.fail("host_history_observation_reconciliation_failed")
        stable = dict(run_id=binding.anchor.run_id, session_id=binding.session_id,
                      action_episode=current.episode, http_agent_id=ledger.binding.http_agent_id,
                      http_episode_id=ledger.binding.http_episode_id, state_path=str(ledger.binding.canonical_state_path))
        digest = hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return HostBoundarySnapshot(digest, binding.session_id, current.episode, len(ledger.events),
            totals.accepted_target_tokens, totals.post_start_sdk_calls_executed, totals.taaf_history_commits,
            current.sequence, current.sha256, logical['sequence'], logical['last_success'], logical['successes'])

    def assert_boundary(self, agent):
        binding = self.binding_for_agent(agent)
        self.boundary_snapshot(binding)
        return binding

    @host_prefix_logical_preflight
    def logical_preflight(self, agent, purpose="main"):
        binding = self.assert_boundary(agent)
        if purpose not in ("main", "summary", "tail"):
            self.fail("invalid_logical_request_purpose")
        self._callback(self.before_exchange, binding)
        # A blocking future gate/deadline callback can make the first check stale.
        self.assert_boundary(agent)
        logical = self._logical[id(agent)]
        logical['pending'], logical['sequence'] = True, logical['sequence'] + 1
        with binding.ledger._lock:
            binding.ledger._emit('logical_request_started', dict(logical_sequence=logical['sequence'], purpose=purpose))
        return binding

    def logical_finished(self, agent, *, succeeded):
        binding = self.binding_for_agent(agent)
        logical = self._logical[id(agent)]
        if not logical['pending']:
            self.fail('logical_request_finish_without_start')
        logical['pending'], logical['last_success'] = False, bool(succeeded)
        logical['successes'] += int(bool(succeeded))
        with binding.ledger._lock:
            binding.ledger._emit('logical_request_finished', dict(logical_sequence=logical['sequence'],
                succeeded=bool(succeeded), successful_logical_requests=logical['successes']))

    def before_physical_send(self, agent, context, purpose="main"):
        binding = self.binding_for_agent(agent)
        proof = self.identity(binding)
        binding.ledger.check_request_allowed(proof)
        try:
            should_stop = binding.session.should_stop()
        except BaseException:
            self.fail('session_guard_failed')
        if should_stop:
            raise HostStopped("session_guard_stop")
        if not self._logical[id(agent)]['pending']:
            self.fail('physical_send_outside_logical_request')
        self._assert_common_clock(binding)
        # The actual joined begun lease owns this physical read budget.
        # Do not reuse a timeout computed before admission/queue waiting.
        admission = getattr(binding.session.solver, '_arc_paper_fleet_admission', None)
        if admission is None or admission.accounting is not self:
            self.fail('physical_timeout_missing_actual_admission')
        with admission._lock, admission.gate._cv:
            sid = admission._bindings.get(id(binding))
            owner = admission._owners.get(sid)
            if owner is None or owner.binding is not binding or owner.closed or owner.lease is None:
                self.fail('physical_timeout_missing_owned_lease')
            active = admission.gate._owned(owner.lease)
            if not active.begun:
                self.fail('physical_timeout_before_lease_begin')
            now = admission.clock()
            config = admission.config
            if now >= config.admission_deadline_monotonic:
                raise HostStopped('physical_send_after_admission_cutoff')
            configured = getattr(agent, '_timeout', None)
            if type(configured) not in (int, float) or not math.isfinite(configured) or configured <= 0:
                self.fail('physical_timeout_missing_configured_bound')
            physical_end = min(config.admission_deadline_monotonic + config.drain_timeout_s,
                               config.whole_deadline_monotonic - config.teardown_reserve_s)
            read_seconds = min(120., float(configured), physical_end - now)
            if read_seconds <= 0:
                raise HostStopped('physical_response_envelope_expired')
            context['host_transport_read_timeout_seconds'] = read_seconds
        context["host_terminal_accounted"] = False
        binding.ledger.request_started(proof, call_id=context["call_id"], attempt_id=context["attempt_id"], purpose=purpose)

    def account_response(self, agent, context, usage, *, error_type=None):
        binding = self.binding_for_agent(agent)
        if context.get("host_terminal_accounted"):
            return  # Same physical response, outer parser error: never charge twice.
        # Set before fsync/callback; an exception after physical state advances
        # cannot lead the outer error handler to charge the same attempt again.
        context["host_terminal_accounted"] = True
        proof = self.identity(binding, terminal=True)
        try:
            if error_type is None:
                return binding.ledger.request_completed(proof, call_id=context["call_id"], attempt_id=context["attempt_id"], usage=usage)
            return binding.ledger.request_failed(proof, call_id=context["call_id"], attempt_id=context["attempt_id"],
                error_type=error_type, usage=usage)
        except BaseException:
            self.fail("physical_request_accounting_failed")

    def session_close(self, session, *, failed=False):
        binding = self._sessions.get(id(session))
        if binding is None or binding.session is not session:
            self.fail("missing_session_close_binding")
        with self._lock:
            if id(session) in self._closed:
                return
        try:
            proof = self.identity(binding, terminal=True)
            if binding.ledger.totals.pending_request:
                # In synchronous pinned code this is an invariant violation;
                # there is no trustworthy response body/ID to invent here.
                _ledger_invalid(binding.ledger, "unsettled_request_at_session_close")
                failed = True
            if binding.ledger._action is not None or session._arc_paper_prediction_adapter.pending is not None:
                _ledger_invalid(binding.ledger, "unsettled_action_at_session_close")
                failed = True
            if failed:
                _ledger_invalid(binding.ledger, "host_session_failed")
            elif binding.ledger.valid:
                self._final_snapshots[id(session)] = self.boundary_snapshot(binding, terminal=True)
                binding.ledger.close(proof)
        except BaseException:
            session.stop_event.set()
            _ledger_invalid(binding.ledger, "host_session_close_failed")
            failed = True
        finally:
            with self._lock:
                self._closed.add(id(session))
            self._callback(self.on_session_close, binding, bool(failed or not binding.ledger.valid))


def _install_sdk_observers(classes):
    # Caller verifies real SDK bytes BEFORE this function mutates class methods.
    with _WRAPPER_LOCK:
        for cls in classes:
            for name in ("reset", "step"):
                key = (cls, name)
                previous = _WRAPPER_HOOKS.get(key)
                if previous is not None:
                    if getattr(cls, name) is not previous[1]:
                        raise AccountingError("sdk_public_observer_replaced")
                    continue
                original = getattr(cls, name)
                def delegate(wrapper, *args, __original=original, __name=name, **kwargs):
                    factory, action = _FACTORY.get(), _ACTION.get()
                    if __name == "reset" and factory is not None:
                        factory.fleet._factory_preflight()
                        if factory.resets != 0 or (factory.wrapper is not None and factory.wrapper is not wrapper):
                            factory.fleet.fail("multiple_factory_reset_calls")
                        factory.wrapper, factory.resets = wrapper, factory.resets + 1
                        factory.capture.dispatch(run=factory.anchor)
                        try:
                            raw = __original(wrapper, *args, **kwargs)
                            echo = action_from_sdk(raw.action_input)["name"] if raw is not None else None
                            observation = observation_from_sdk(raw, episode=factory.anchor.run_id, sequence=0)
                            factory.initial_observation = observation
                            with factory.capture._lock:
                                factory.capture._emit('initial_reset_public_return',
                                    dict(public_observation=observation.to_dict()))
                            factory.capture.receipt(run=factory.anchor, execution="executed" if raw is not None else "unknown",
                                returned_action=echo, full_reset=getattr(raw, "full_reset", None),
                                levels_completed=observation.levels_completed)
                            return raw
                        except BaseException:
                            if not factory.capture._finished:
                                factory.capture.receipt(run=factory.anchor, execution="unknown")
                            raise
                    if action is not None:
                        if wrapper is not action.binding.environment:
                            action.binding.fleet.fail("foreign_sdk_action_environment")
                        if __name == "reset" and action.depth:
                            return __original(wrapper, *args, **kwargs)  # step(RESET)'s same command
                        if __name != "step" or action.dispatched:
                            action.binding.fleet.fail("unexpected_or_duplicate_sdk_action")
                        binding = action.binding
                        commitment = binding.session._arc_paper_prediction_adapter.pending
                        if commitment is None:
                            binding.fleet.fail("sdk_dispatch_without_host_commitment")
                        sdk_action = args[0] if args else kwargs.get("action")
                        sdk_data = args[1] if len(args) > 1 else kwargs.get('data')
                        canonical = canonical_action({'name': getattr(sdk_action, 'name', None), 'data': sdk_data or {}})
                        # SDK step receives GameAction enum, not ActionInput.
                        if canonical != commitment.action:
                            binding.fleet.fail("sdk_action_commitment_mismatch")
                        action.commitment = commitment
                        proof = binding.fleet.identity(binding)  # expected stop may still refuse here
                        assert_sdk_dispatch(binding, commitment)
                        try:
                            binding.ledger.action_dispatched(proof, transition_id=commitment.transition_id,
                                commitment_id=commitment.id, action=canonical["name"], automatic=commitment.automatic)
                        finally:
                            # The primitive advances physical intent before
                            # fsync/observers. Preserve its terminal drain even
                            # when that emission raises before SDK entry.
                            pending = binding.ledger._action
                            action.dispatched = pending is not None and pending[:2] == (commitment.transition_id, commitment.id)
                        binding.session._arc_paper_prediction_adapter.mark_dispatched(
                            commitment.id, commitment.transition_id, canonical)
                        action.depth, action.sdk_entered = 1, True
                        try:
                            raw = __original(wrapper, *args, **kwargs)
                            if raw is not None:
                                if action_from_sdk(raw.action_input) != commitment.action:
                                    binding.fleet.fail("sdk_action_echo_mismatch")
                                # Freeze permitted return before TAAF can modify
                                # it or raise during its bookkeeping.
                                action.public_observation = observation_from_sdk(raw, episode=commitment.before.episode,
                                    sequence=commitment.before.sequence + 1)
                                action.sdk_returned = True
                                with binding.ledger._lock:
                                    binding.ledger._emit('sdk_public_return', dict(transition_id=commitment.transition_id,
                                        commitment_id=commitment.id, public_observation=action.public_observation.to_dict()))
                            return raw
                        finally:
                            action.depth = 0
                    bound = _BOUND_ENVIRONMENTS.get(id(wrapper))
                    if bound is not None and bound.environment is wrapper:
                        bound.fleet.fail("bound_sdk_call_outside_host_context")
                    return __original(wrapper, *args, **kwargs)
                delegate = wraps(original)(delegate)
                _WRAPPER_HOOKS[key] = (original, delegate)
                setattr(cls, name, delegate)


_FLEET = FleetAccounting()


def configure_fleet(**kwargs):
    """Explicit host setup before any factory; no untrusted/runtime toggles."""
    global _FLEET
    if _FLEET._games:
        raise AccountingError("fleet_already_started")
    _FLEET = FleetAccounting(**kwargs)
    return _FLEET


def host_accounted_game_start(original):
    @wraps(original)
    def wrapped(game, *args, **kwargs):
        _FLEET.begin_game(game)
        try:
            result = original(game, *args, **kwargs)
            _FLEET.finish_game(game)
            return result
        except HostStopped:
            raise
        except BaseException:
            _FLEET.fail("game_start_failed")
    return wrapped


def host_make(game, factory, *args, **kwargs):
    return _FLEET.make(game, factory, *args, **kwargs)


def bind_session(session):
    return _FLEET.bind_session(session)


def assert_exchange_boundary(agent):
    return _FLEET.assert_boundary(agent)


def logical_preflight(agent, purpose="main"):
    return _FLEET.logical_preflight(agent, purpose)


def before_physical_send(agent, context, purpose="main"):
    return _FLEET.before_physical_send(agent, context, purpose)


def account_response(agent, context, usage, *, error_type=None):
    return _FLEET.account_response(agent, context, usage, error_type=error_type)


def host_accounted_tool(original):
    @wraps(original)
    def wrapped(agent, *args, **kwargs):
        binding = _FLEET.binding_for_agent(agent)
        _FLEET.identity(binding)
        _FLEET._tool_depth[id(agent)] += 1
        try:
            return original(agent, *args, **kwargs)
        finally:
            _FLEET._tool_depth[id(agent)] -= 1
    return wrapped


def host_accounted_chat(original):
    @wraps(original)
    def wrapped(agent, *args, **kwargs):
        _FLEET.logical_preflight(agent, kwargs.get('_arc_paper_purpose', 'main'))
        succeeded = False
        try:
            result = original(agent, *args, **kwargs)
            succeeded = True
            return result
        finally:
            _FLEET.logical_finished(agent, succeeded=succeeded)
    return wrapped


def _prediction_game_action_v3(session, action, *, generated_tokens, automatic, call):
    """Resolve a proven pre-SDK stop as refusal; never erase a real dispatch.

    The frozen original runtime unconditionally marks prediction dispatch before
    TAAF reaches the SDK and treats every exception as unknown. This dedicated
    host helper leaves those bytes intact and moves the mark into the verified
    SDK delegate. Its ordinary successful/unknown projection is unchanged.
    """
    adapter = session._arc_paper_prediction_adapter
    canonical = action_from_sdk(action)
    if adapter.pending is None:
        if not automatic or canonical['name'] != 'RESET':
            session.stop_event.set()
            raise AccountingError('real_action_without_tool_commitment')
        commitment = adapter.commit(canonical, None, automatic=True)
    else:
        commitment = adapter.pending
        if automatic or commitment.action != canonical:
            session.stop_event.set()
            raise AccountingError('action_commitment_changed_before_dispatch')
    try:
        _FLEET.identity(call.binding)
        new_state = session.game.execute_action(action, generated_tokens=generated_tokens, uncached_input_tokens=0)
        if not call.dispatched or not call.sdk_entered or not call.sdk_returned:
            raise AccountingError('framework_return_without_verified_sdk_return')
        raw = new_state.raw
        after = observation_from_sdk(raw, episode=commitment.before.episode, sequence=commitment.before.sequence + 1)
        if canonical['name'] != 'RESET' and getattr(raw, 'full_reset', False):
            after = PublicObservation(after.episode, after.sequence, after.frames, None, None, after.available_actions, False)
        adapter.resolve(commitment.id, commitment.transition_id, canonical, after, execution='executed',
                        echoed_action=action_from_sdk(raw.action_input))
        return new_state
    except BaseException as error:
        session.stop_event.set()
        known_refused = (isinstance(error, HostStopped) and not call.dispatched and not call.sdk_entered
                         and len(call.binding.game_run.history) == call.history_before)
        call.known_refused = known_refused
        if adapter.pending is not None:
            adapter.resolve(commitment.id, commitment.transition_id, canonical, None,
                execution='refused' if known_refused else 'unknown',
                reason='host_stop_before_sdk_entry' if known_refused else 'host_action_exception:' + type(error).__name__)
        if known_refused:
            with call.binding.ledger._lock:
                call.binding.ledger._emit('sdk_action_refused', dict(transition_id=commitment.transition_id,
                    commitment_id=commitment.id, action=canonical['name'], reason='host_stop_before_sdk_entry',
                    sdk_dispatches=0, sdk_calls_executed=0, history_committed=False))
        raise


def accounted_prediction_game_action(session, action, *, generated_tokens, automatic):
    binding = _FLEET.binding_for_agent(session.analyzer)
    # Prove ownership before context creation. Expected pre-SDK stop belongs
    # inside the protected action helper so a pending commitment is refused.
    _FLEET.identity(binding, terminal=True)
    if _ACTION.get() is not None:
        _FLEET.fail("nested_framework_action")
    call = _ActionCall(binding, len(binding.game_run.history))
    token = _ACTION.set(call)
    failed = False
    try:
        return _prediction_game_action_v3(session, action, generated_tokens=generated_tokens, automatic=automatic, call=call)
    except BaseException:
        failed = True
        raise
    finally:
        _ACTION.reset(token)
        if call.dispatched:
            delta = len(binding.game_run.history) - call.history_before
            if delta not in (0, 1):
                _FLEET.fail("framework_history_delta_invalid")
            commitment = call.commitment
            binding.ledger.action_receipt(_FLEET.identity(binding, terminal=True),
                transition_id=commitment.transition_id, commitment_id=commitment.id, action=commitment.action["name"],
                execution="executed" if call.sdk_returned else "unknown", history_committed=delta == 1,
                levels_completed=call.public_observation.levels_completed if call.sdk_returned else None)
        elif failed and not call.known_refused:
            _ledger_invalid(binding.ledger, "framework_action_before_sdk_failed")
        if failed and not call.known_refused:
            session.stop_event.set()
            _ledger_invalid(binding.ledger, "framework_action_processing_failed")


def host_accounted_session_play(original):
    @wraps(original)
    def wrapped(session, *args, **kwargs):
        failed = False
        try:
            return original(session, *args, **kwargs)
        except HostStopped:
            raise
        except BaseException:
            failed = True
            raise
        finally:
            _FLEET.session_close(session, failed=failed)
    return wrapped


def session_close(session, *, failed=False):
    return _FLEET.session_close(session, failed=failed)
