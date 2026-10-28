# SPDX-License-Identifier: MIT-0
"""Common complete-exchange admission for the pinned host-accounting harness.

Installed by the exclusive source builder, never on import. The joined accounting
bridge supplies physical boundary proofs; no solver/child assertions are used.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from functools import wraps
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
from types import MappingProxyType

from .allocation import COMMON_FEATURES, RESIDUAL_FEATURES, ProgressModel, adjusted_priority
from .fleet_gate import AdmissionCancelled, FleetGate, GateBroken, SettledBoundary
from .franzen_host_accounting_v2 import HostStopped


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _positive(value, label):
    if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
        raise ValueError('invalid ' + label)
    return float(value)


@dataclass(frozen=True)
class CommonFleetConfig:
    planned_session_ids: tuple[str, ...]
    capacity: int
    arm: str
    worker_ready_timeout_s: float
    admission_deadline_monotonic: float
    drain_timeout_s: float
    teardown_reserve_s: float
    whole_deadline_monotonic: float

    def validate(self):
        if (type(self.planned_session_ids) is not tuple or len(self.planned_session_ids) < 1
                or any(type(s) is not str or not s or len(s) > 128 for s in self.planned_session_ids)
                or len(set(self.planned_session_ids)) != len(self.planned_session_ids)):
            raise ValueError('explicit frozen opaque planned fleet required')
        if type(self.capacity) is not int or self.capacity != min(2, len(self.planned_session_ids)):
            raise ValueError('official deployment capacity min(2,N) required')
        if self.arm not in ('B1', 'A1', 'P'):
            raise ValueError('B0 requires a separate original-prompt/batch accounting build')
        for name in ('worker_ready_timeout_s', 'admission_deadline_monotonic', 'drain_timeout_s',
                     'teardown_reserve_s', 'whole_deadline_monotonic'):
            _positive(getattr(self, name), name)
        if (self.admission_deadline_monotonic + self.drain_timeout_s + self.teardown_reserve_s
                > self.whole_deadline_monotonic):
            raise ValueError('common whole-session deadline must reserve drain and teardown')
        return self


@dataclass(frozen=True)
class PurePriorityPolicy:
    """Pinned priority_value arithmetic, frozen options, common clock; no tiers."""
    started_at: float
    deadline: float
    endgame_after_s: float
    tail_fade: bool
    tail_window_s: float
    pace_enabled: bool
    options: dict = field(repr=False)
    snapshot_type: object = field(repr=False, compare=False)
    priority_value: object = field(repr=False, compare=False)
    action_count: object = field(repr=False, compare=False)

    @classmethod
    def capture(cls, tool_module, *, started_at, deadline):
        options = dict(tool_module._priority_level_options())
        options.update(human_actions=tool_module._priority_human_actions(),
                       action_scale=tool_module._priority_action_scale(),
                       token_scale=tool_module._priority_token_scale(),
                       action_weight=tool_module._priority_action_weight(),
                       tail_base=tool_module._priority_tail_base(), tail_cap=tool_module._priority_tail_cap())
        # Read only these public scheduling settings; never enumerate environment.
        fade = tool_module._get_env_bool('ARC3_PRIORITY_TAIL_FADE', False)
        fraction = os.environ.get('ARC3_PRIORITY_TAIL_FADE_FRACTION', '').strip()
        if fraction:
            value = float(fraction)
            if not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError('invalid frozen tail-fade fraction')
            window = value * (deadline - started_at)
        else:
            window = max(1., 60 * tool_module._get_env_float('ARC3_PRIORITY_TAIL_FADE_MINUTES', 90.))
        _encoded(options)
        return cls(started_at, deadline, 60 * tool_module._endgame_start_minutes(), fade, window,
                   tool_module._get_env_bool('ARC3_PRIORITY_PACE', False), MappingProxyType(options),
                   tool_module.PrioritySnapshot, tool_module.priority_value, tool_module._priority_action_count)

    def manifest(self):
        return {'started_at': self.started_at, 'deadline': self.deadline,
                'endgame_after_s': self.endgame_after_s, 'tail_fade': self.tail_fade,
                'tail_window_s': self.tail_window_s, 'pace_enabled': self.pace_enabled,
                'options': dict(self.options), 'warmth_or_phase_offsets': False,
                'adjusted_priority_rounding': False}

    def snapshot(self, binding):
        agent = binding.agent
        summary = agent._last_step_summary or {}
        level = int(summary.get('level') or 1)
        actions = max(0, self.action_count(summary) - agent._actions_at_level_start)
        tokens = max(0, agent._session_generated_tokens - getattr(agent, '_tokens_at_level_start', 0))
        pace = agent._progress_pace.cost_multiplier() if self.pace_enabled else 1.
        total = agent._priority_total_levels() if self.options['normalize_score'] or self.options['tail_lookup'] else None
        return _encoded({'level': level, 'actions': actions, 'tokens': tokens,
                         'cost_multiplier': pace, 'total_levels': total})

    def baseline(self, snapshot, now):
        data = json.loads(snapshot)
        if set(data) != {'level', 'actions', 'tokens', 'cost_multiplier', 'total_levels'}:
            raise ValueError('numeric priority snapshot schema mismatch')
        if (type(data['level']) is not int or data['level'] < 1 or type(data['actions']) is not int
                or data['actions'] < 0 or type(data['tokens']) not in (int, float)
                or not math.isfinite(data['tokens']) or data['tokens'] < 0
                or type(data['cost_multiplier']) not in (int, float)
                or not math.isfinite(data['cost_multiplier']) or not .5 <= data['cost_multiplier'] <= 2
                or data['total_levels'] is not None and (type(data['total_levels']) is not int or data['total_levels'] < 1)):
            raise ValueError('invalid numeric priority snapshot')
        state = self.snapshot_type(**data)
        fraction = max(0., self.deadline - now) / self.tail_window_s if self.tail_fade else None
        endgame = self.endgame_after_s > 0 and now - self.started_at >= self.endgame_after_s
        return self.priority_value(state, endgame=endgame, tail_fraction=fraction, **self.options)


class _Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('x', encoding='utf-8'):
            pass
        self._lock = threading.Lock()

    def __call__(self, record):
        data = _encoded(record) + b'\n'
        with self._lock, self.path.open('ab') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())


@dataclass
class _Owner:
    binding: object
    lease: object = None
    logical_sequence: int | None = None
    ready: bool = False
    closed: bool = False
    feature_sha256: str | None = None


def _models(models, arm):
    if arm == 'B1':
        if models:
            raise ValueError('B1 has no learned allocation model')
        return {}, {'constant_multiplier': 1.}
    if type(models) is not dict or set(models) != {'A1', 'P'}:
        raise ValueError('both frozen matched allocation models required')
    result = {}
    for key, names in (('A1', COMMON_FEATURES), ('P', COMMON_FEATURES + RESIDUAL_FEATURES)):
        model = models[key]
        if (type(model) is not ProgressModel or model.names != names
                or any(type(getattr(model, name)) is not tuple
                       for name in ('names', 'means', 'scales', 'coefficients'))
                or len(model.means) != len(names) or len(model.scales) != len(names)
                or len(model.coefficients) != len(names) + len(COMMON_FEATURES)
                or not all(type(v) in (float, int) and math.isfinite(v)
                           for v in (*model.means, *model.scales, *model.coefficients, model.intercept))
                or any(v <= 0 for v in model.scales) or type(model.training_rows) is not int or model.training_rows < 2
                or type(model.training_sha256) is not str or len(model.training_sha256) != 64
                or any(c not in '0123456789abcdef' for c in model.training_sha256)
                or any(type(v) not in (float, int) for v in (model.l2, model.learning_rate))
                or (model.l2, model.iterations, model.learning_rate) != (1., 2000, .05)
                or type(model.iterations) is not int):
            raise ValueError('invalid frozen allocation model')
        result[key] = model
    if result['A1'].training_sha256 != result['P'].training_sha256 or result['A1'].training_rows != result['P'].training_rows:
        raise ValueError('allocation models must use identical frozen training rows')
    return MappingProxyType(result), {key: value.to_dict() for key, value in result.items()}


class FleetAdmission:
    """Actual accounting-bridge callbacks; holds leases until the next real boundary."""
    def __init__(self, solver, games, config, accounting_fleet, *, log_root, hard_stop, models=None,
                 clock=time.monotonic, priority_module=None):
        self.config = config.validate()
        if len(games) != len(config.planned_session_ids) or len({id(g) for g in games}) != len(games):
            raise ValueError('actual whole fleet differs from frozen planned sessions')
        if int(solver.concurrency) < len(games):
            raise ValueError('all fleet workers must be exposed before admission')
        pool = getattr(solver, '_worker_pool', None)
        if pool is not None and pool._max_workers < len(games):
            raise ValueError('existing worker pool hides planned sessions')
        if accounting_fleet.stop_event is not solver._stop_event or not callable(hard_stop):
            raise ValueError('joined common stop and actual hard-stop governor required')
        if any(callback is not None for callback in (accounting_fleet.before_exchange,
                accounting_fleet.on_bind, accounting_fleet.on_session_close)) or accounting_fleet._agents:
            raise ValueError('accounting callbacks already in use or workers already started')
        self.solver, self.accounting = solver, accounting_fleet
        self.clock, self.hard_stop = clock, hard_stop
        self.games = tuple(games)
        self._plans = {id(game): sid for game, sid in zip(games, config.planned_session_ids)}
        self._owners, self._bindings = {}, {}
        self._workers_started, self._workers_finished = set(), set()
        self._threads, self._worker_threads = {}, {}
        self._physical_sessions_closed = set()
        self._hard_stopped = False
        self._lock = threading.RLock()
        self._closed = threading.Event()
        self.invalid_reason = None
        self.started_at = clock()
        if self.started_at >= config.admission_deadline_monotonic:
            raise ValueError('admission deadline already expired')
        if priority_module is None:
            from inference.agent import tool_agent as priority_module
        self.priority = PurePriorityPolicy.capture(priority_module, started_at=self.started_at,
                                                  deadline=config.admission_deadline_monotonic)
        self.models, model_payload = _models(models, config.arm)
        allocation_bytes = _encoded({'config': asdict(config), 'models': model_payload,
                                     'priority': self.priority.manifest()})
        self.allocation_sha256 = _sha(allocation_bytes)
        manifest_path = Path(log_root) / 'fleet-allocation-manifest.json'
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open('xb') as stream:
            stream.write(allocation_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        self._journal = _Journal(Path(log_root) / 'fleet-admission.jsonl')
        self.gate = FleetGate(config.planned_session_ids, config.capacity, self.priority.baseline,
                              self._journal, model_sha256=self.allocation_sha256,
                              priority_semantics='plain_nonnegative_scalar', clock=clock,
                              allow_uncontended_control=config.capacity == len(config.planned_session_ids))
        self._record('common_fleet_started', config_sha256=_sha(_encoded(asdict(config))),
                     allocation_sha256=self.allocation_sha256, workers=int(solver.concurrency))
        accounting_fleet.before_exchange = self.before_exchange
        accounting_fleet.on_bind = self.on_bind
        accounting_fleet.on_session_close = self.on_session_close
        self._watchdog = threading.Thread(target=self._watch, name='fleet-startup-watchdog', daemon=True)
        self._watchdog.start()

    def _record(self, event, **fields):
        try:
            self._journal({'schema_version': 1, 'event': event, 'monotonic': self.clock(), **fields})
        except BaseException:
            self.invalid_reason = self.invalid_reason or 'admission_journal_failed'
            self.solver._stop_event.set()
            raise GateBroken(self.invalid_reason) from None

    def _fail(self, reason):
        with self._lock:
            self.invalid_reason = self.invalid_reason or reason
            self.solver._stop_event.set()
        raise GateBroken(self.invalid_reason)

    def on_bind(self, binding):
        try:
            sid = self._plans.get(id(binding.game))
            if sid is None or binding.game is not self.games[self.config.planned_session_ids.index(sid)]:
                raise ValueError('binding is outside the frozen full fleet')
            with self._lock:
                if (sid in self._owners or binding.fleet is not self.accounting
                        or self._worker_threads.get(sid) is not threading.current_thread()):
                    raise ValueError('duplicate or foreign actual host binding')
                self._owners[sid] = _Owner(binding)
                self._bindings[id(binding)] = sid
                self._threads[sid] = threading.current_thread()
            self._record('planned_session_bound', planned_session_id=sid,
                         accounting_session_id=binding.session_id, run_id=binding.anchor.run_id)
        except BaseException:
            self._fail('invalid_admission_binding')

    def _snapshot(self, binding, *, terminal=False):
        # This method must read the joined bridge's real frozen proof, never booleans
        # supplied by the caller, a child, raw HTTP logger, or a response payload.
        snapshot = binding.boundary_snapshot(terminal=terminal)
        if snapshot is None:
            raise ValueError('no validated physical/history boundary snapshot')
        return snapshot

    def _boundary(self, sid, snapshot, feature_sha):
        return SettledBoundary(sid, snapshot.action_episode, snapshot.binding_sha256,
                               snapshot.action_sequence, snapshot.accepted_target_tokens,
                               feature_sha, self.allocation_sha256,
                               False, False, False, True, True)

    def before_exchange(self, binding):
        try:
            with self._lock:
                if self.invalid_reason:
                    raise GateBroken(self.invalid_reason)
                sid = self._bindings.get(id(binding))
                owner = self._owners.get(sid)
                if owner is None or owner.binding is not binding or owner.closed:
                    raise ValueError('stale admission owner')
            snapshot = self._snapshot(binding)
            raw_priority = self.priority.snapshot(binding)
            base = self.priority.baseline(raw_priority, self.clock())
            features = binding.session._arc_paper_evidence_history.features(
                baseline_priority=base, generated_target_tokens=snapshot.accepted_target_tokens)
            feature_bytes = _encoded(features)
            feature_sha = _sha(feature_bytes)
            multiplier = adjusted_priority(1., features, self.models, self.config.arm)
            boundary = self._boundary(sid, snapshot, feature_sha)
            with self._lock:
                owner.ready = True
            self._record('boundary_frozen', planned_session_id=sid, features_sha256=feature_sha,
                         allocation_sha256=self.allocation_sha256, baseline_snapshot_sha256=_sha(raw_priority),
                         features=json.loads(feature_bytes), priority_snapshot=json.loads(raw_priority),
                         logical_sequence=snapshot.logical_sequence, action_watermark=snapshot.action_sequence,
                         accepted_target_tokens=snapshot.accepted_target_tokens, frozen_multiplier=multiplier)
            if owner.lease is None:
                owner.lease = self.gate.acquire(sid, boundary, raw_priority, multiplier,
                    cancel_event=self.solver._stop_event, deadline=self.config.admission_deadline_monotonic)
            else:
                if snapshot.logical_sequence != owner.logical_sequence + 1 or type(snapshot.last_logical_succeeded) is not bool:
                    raise ValueError('logical exchange completion association mismatch')
                owner.lease = self.gate.handover(owner.lease, boundary, raw_priority, multiplier,
                    cancel_event=self.solver._stop_event, deadline=self.config.admission_deadline_monotonic,
                    completed_successfully=snapshot.last_logical_succeeded)
            owner.logical_sequence = snapshot.logical_sequence
            owner.feature_sha256 = feature_sha
            self.gate.begin(owner.lease)
            # Bridge reasserts its current ownership/stop proof after this wait,
            # and again at every physical send. Feature/model snapshot stays frozen.
        except AdmissionCancelled:
            if owner is not None and sid not in self.gate.snapshot()['active']:
                owner.lease = None  # A cancelled handover may already have settled.
            raise HostStopped('admission_cancelled') from None
        except HostStopped:
            raise
        except (ValueError, GateBroken):
            self._fail('admission_boundary_or_gate_failed')

    def _joined_owner(self, binding):
        """Terminal joining never obtains a new generation permit."""
        sid = self._bindings.get(id(binding))
        with self._lock:
            owner = self._owners.get(sid)
            if (owner is None or owner.binding is not binding or owner.closed
                    or binding.fleet is not self.accounting
                    or self._threads.get(sid) is not threading.current_thread()
                    or self._worker_threads.get(sid) is not threading.current_thread()):
                raise ValueError('foreign_common_terminal_owner')
        return sid, owner


    def on_session_close(self, binding, failed):
        sid = self._bindings.get(id(binding))
        with self._lock:
            owner = self._owners.get(sid)
            if (type(failed) is not bool or owner is None or owner.binding is not binding
                    or self._plans.get(id(binding.game)) != sid or sid not in self._workers_started
                    or self._threads.get(sid) is not threading.current_thread()
                    or self._worker_threads.get(sid) is not threading.current_thread()
                    or binding.fleet is not self.accounting
                    or self.accounting._sessions.get(id(binding.session)) is not binding
                    or id(binding.session) not in self.accounting._closed
                    or sid in self._physical_sessions_closed):
                self._fail('common_physical_host_close_identity_failed')
            # Actual host finally has revoked the session. This is deliberately
            # independent of a valid terminal snapshot, lease release or refund.
            self._physical_sessions_closed.add(sid)
        self._record('physical_session_close_observed', planned_session_id=sid,
            accounting_session_id=binding.session_id, run_id=binding.anchor.run_id,
            failed=failed, semantic_settlement_not_implied=True)
        return self._semantic_session_close(binding, failed)


    def _semantic_session_close(self, binding, failed):
        try:
            sid = self._bindings.get(id(binding))
            owner = self._owners.get(sid)
            if owner is None or owner.binding is not binding or owner.closed:
                raise ValueError('session close admission association mismatch')
            snapshot = self._snapshot(binding, terminal=True)
            if owner.lease is not None:
                if snapshot.logical_sequence not in (owner.logical_sequence, owner.logical_sequence + 1):
                    raise ValueError('terminal logical exchange association mismatch')
                # Terminal snapshot is validated/frozen by bridge before closure.
                feature_sha = owner.feature_sha256
                if feature_sha is None:
                    raise ValueError('missing frozen allocation feature hash')
                if snapshot.logical_sequence == owner.logical_sequence:
                    # Admission succeeded but the bridge's post-wait stop check
                    # prevented the logical request from starting. No service.
                    self.gate.abort(owner.lease, self._boundary(sid, snapshot, feature_sha), reason='host_stop')
                else:
                    if type(snapshot.last_logical_succeeded) is not bool:
                        raise ValueError('missing terminal logical outcome')
                    self.gate.settle(owner.lease, self._boundary(sid, snapshot, feature_sha),
                                     completed_successfully=snapshot.last_logical_succeeded)
                owner.lease = None
            self.gate.terminate(sid, reason='request_failed' if failed else 'finished')
            owner.closed = True
            self._record('planned_session_closed', planned_session_id=sid, censored=bool(failed),
                         action_watermark=snapshot.action_sequence,
                         accepted_target_tokens=snapshot.accepted_target_tokens)
        except BaseException:
            self._fail('unsettled_or_invalid_session_close')

    def _watch(self):
        try:
            startup_deadline = self.started_at + self.config.worker_ready_timeout_s
            while not self._closed.wait(.02):
                now = self.clock()
                if now >= self.config.admission_deadline_monotonic:
                    self._record('admission_deadline_reached')
                    self.solver._stop_event.set()
                    return
                if now >= startup_deadline:
                    with self._lock:
                        missing = [sid for sid in self.config.planned_session_ids
                                   if sid not in self._owners or not self._owners[sid].ready and not self._owners[sid].closed]
                    if missing:
                        for sid in missing:
                            self.gate.terminate(sid, reason='startup_failed')
                            self._record('planned_session_censored', planned_session_id=sid,
                                         reason='worker_ready_timeout', censored=True)
                        # Actual pinned sessions share one stop event: conservatively
                        # stop/drain the whole fleet; do not invent per-worker stop.
                        self.invalid_reason = 'planned_worker_startup_timeout'
                        self.solver._stop_event.set()
                        return
        except BaseException:
            self.invalid_reason = self.invalid_reason or 'startup_watchdog_failed'
            self.solver._stop_event.set()

    def finish_governor(self):
        self._closed.set()
        if self._watchdog is not threading.current_thread():
            self._watchdog.join(.5)

    def worker_started(self, game, index):
        with self._lock:
            sid = self._plans.get(id(game))
            if sid is None or self.config.planned_session_ids[index] != sid or sid in self._workers_started:
                self._fail('worker_registration_mismatch')
            if sid in self._worker_threads or game is not self.games[index]:
                self._fail('common_physical_worker_identity_failed')
            self._worker_threads[sid] = threading.current_thread()
            self._workers_started.add(sid)
        self._record('physical_worker_started', planned_session_id=sid)

    def worker_finished(self, game):
        with self._lock:
            sid = self._plans.get(id(game))
            if sid is None or sid not in self._workers_started or sid in self._workers_finished:
                self._fail('worker_finish_mismatch')
            if (self._worker_threads.get(sid) is not threading.current_thread()
                    or game is not self.games[self.config.planned_session_ids.index(sid)]):
                self._fail('common_physical_return_identity_failed')
            self._workers_finished.add(sid)
            if sid not in self._owners:
                # The real worker returned before binding (e.g. analyzer or
                # session construction failed). It cannot silently disappear
                # from bootstrap. A started physical request requires a joined
                # binding, so there is no lease to certify/release here.
                self.gate.terminate(sid, reason='startup_failed')
                self._record('planned_session_censored', planned_session_id=sid,
                             reason='worker_returned_before_bind', censored=True)
        self._record('physical_worker_finished', planned_session_id=sid)

    def physically_closed(self):
        # Delegate finally + host close is not OS Thread/process/child exit.
        # Invalid owner/held lease facts remain intact for semantic rejection.
        with self._lock:
            return (self._workers_finished == set(self.config.planned_session_ids)
                    and all(sid in self._physical_sessions_closed for sid in self._owners)
                    and all(binding.fleet is self.accounting
                        and (owner := self._owners.get(self._plans.get(id(binding.game)))) is not None
                        and owner.binding is binding
                        and self._plans[id(binding.game)] in self._physical_sessions_closed
                        for binding in self.accounting._sessions.values()))

    def _hard_stop(self, reason):
        if not self._hard_stopped:
            self._hard_stopped = True
            self.hard_stop(reason)

    async def govern(self, coroutine):
        """Drive the original solver cancellation/drain path under shared deadlines."""
        task = asyncio.create_task(coroutine)
        try:
            while not task.done() and not self.solver._stop_event.is_set():
                if self.clock() >= self.config.admission_deadline_monotonic:
                    self.solver._stop_event.set()
                    break
                await asyncio.wait({task}, timeout=.02)
            if not task.done():
                task.cancel()  # Original _run_games executes _drain_game_tasks.
                done, _ = await asyncio.wait({task}, timeout=self.config.drain_timeout_s)
                if not done or not self.physically_closed():
                    self._record('physical_drain_failed', invalid_reason=self.invalid_reason,
                                 logical_active_count=len(self.gate.snapshot()['active']))
                    self._hard_stop('physical_drain_failed')
                    self._fail('physical_drain_failed')
            try:
                result = task.result()
            except asyncio.CancelledError:
                result = None
            if not self.physically_closed():
                self._hard_stop('physical_work_unsettled_after_solver')
                self._fail('physical_work_unsettled_after_solver')
            if self.invalid_reason:
                raise GateBroken(self.invalid_reason)
            return result
        except asyncio.CancelledError:
            self.solver._stop_event.set()
            task.cancel()
            done, _ = await asyncio.wait({task}, timeout=self.config.drain_timeout_s)
            if not done or not self.physically_closed():
                self._hard_stop('cancelled_fleet_drain_failed')
            raise
        except BaseException:
            self.solver._stop_event.set()
            if not task.done():
                task.cancel()
                await asyncio.wait({task}, timeout=self.config.drain_timeout_s)
            if not self.physically_closed():
                self._hard_stop('failed_fleet_drain_unsettled')
            raise
        finally:
            self.finish_governor()


def configure_common_fleet(solver, *, config, log_root, hard_stop, models=None, sdk_verifier=None):
    """Trusted notebook setup before any SDK factory; no permissive default mode."""
    from . import franzen_host_accounting_v2 as accounting
    config.validate()
    if not callable(hard_stop) or hasattr(solver, '_arc_paper_common_configuration'):
        raise ValueError('fresh solver and explicit real hard-stop callback required')
    kwargs = {'log_root': Path(log_root) / 'accounting', 'stop_event': solver._stop_event}
    if sdk_verifier is not None:
        kwargs['sdk_verifier'] = sdk_verifier  # Host-only benign fixtures; real default pins SDK bytes.
    fleet = accounting.configure_fleet(**kwargs)
    solver._arc_paper_common_configuration = (config, Path(log_root), hard_stop, models, fleet)
    return fleet


def common_mode(solver):
    return hasattr(solver, '_arc_paper_common_configuration')


def common_agent_mode(agent):
    from . import franzen_host_accounting_v2 as accounting
    owner = accounting._FLEET._agents.get(id(agent))
    return owner is not None and owner[0] is agent and common_mode(owner[1].solver)


def host_admitted_run_games(original):
    """Wrap actual _run_games; original owns its task list and drain implementation."""
    @wraps(original)
    async def wrapped(solver, games):
        if not common_mode(solver):
            return await original(solver, games)
        config, root, hard_stop, models, fleet = solver._arc_paper_common_configuration
        try:
            if fleet.stop_event.is_set():
                raise GateBroken('fleet_stopped_before_worker_registration')
            admission = FleetAdmission(solver, games, config, fleet, log_root=root,
                                       hard_stop=hard_stop, models=models)
            solver._arc_paper_fleet_admission = admission
            return await admission.govern(original(solver, games))
        except BaseException:
            solver._stop_event.set()
            raise
    return wrapped


def host_admitted_play_one(original):
    """Track actual worker return, not only completed asyncio Future wrappers."""
    @wraps(original)
    def wrapped(solver, game, index, *args, **kwargs):
        admission = getattr(solver, '_arc_paper_fleet_admission', None)
        if admission is None:
            return original(solver, game, index, *args, **kwargs)
        admission.worker_started(game, index)
        try:
            return original(solver, game, index, *args, **kwargs)
        finally:
            admission.worker_finished(game)
    return wrapped
