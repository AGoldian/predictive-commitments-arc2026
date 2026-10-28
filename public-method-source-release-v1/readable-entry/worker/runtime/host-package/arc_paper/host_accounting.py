"""Host ownership and durable physical-cost primitives (MIT-0).

No upstream imports, solver hooks, model/network calls or window collector.
Only trusted host call sites may supply identity proofs and public receipt
fields. This is association/accounting plumbing, not OS authentication. Never
pass these objects or their owner references into a solver subprocess.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from types import MappingProxyType


class AccountingError(ValueError):
    """Sticky accounting failure: stop the bound episode; do not guess costs."""


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_:-]{1,128}", value):
        raise AccountingError("invalid_identifier")
    return value


def _count(value):
    if type(value) is not int or value < 0:
        raise AccountingError("invalid_nonnegative_integer")
    return value


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _observer_key(observer):
    owner = getattr(observer, "__self__", None)
    if owner is not None:
        function = getattr(observer, "__func__", None)
        return (id(owner), id(function) if function is not None else getattr(observer, "__name__", None))
    return (id(observer),)


def _path(value):
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise AccountingError("missing_state_path")
    path = Path(value).expanduser().resolve()
    if path.is_dir():
        raise AccountingError("state_path_is_directory")
    return path


@dataclass(frozen=True, eq=False)
class HostEpisodeAnchor:
    """Fresh per-play host identity created before SDK factory/reset.

    This object is not the future GameRun. The integration must assert the
    actual GameRun/Session/SDK ownership join before binding it to this anchor.
    Keep the same private anchor for the full play; never expose it to children.
    """
    run_id: str

    def __post_init__(self):
        _identifier(self.run_id)


@dataclass(frozen=True)
class HostIdentity:
    """Fresh host-supplied ownership proof; owner objects are compared by `is`.

    The integration must read current path/IDs/references at each boundary.
    Replaying an old proof cannot establish that an external object is current.
    `run` is the pre-factory HostEpisodeAnchor, not the future GameRun.
    Private object references and the exact path are never serialized to logs.
    """
    run_id: str
    session_id: str
    run: object = field(repr=False, compare=False)
    session: object = field(repr=False, compare=False)
    analyzer: object = field(repr=False, compare=False)
    state_path: Path = field(repr=False)
    action_episode: str
    history_episode: str
    http_agent_id: str
    http_episode_id: str


@dataclass(frozen=True)
class HostBinding:
    run_id: str
    session_id: str
    run: object = field(repr=False, compare=False)
    session: object = field(repr=False, compare=False)
    analyzer: object = field(repr=False, compare=False)
    canonical_state_path: Path = field(repr=False)
    original_state_path: Path = field(repr=False)
    action_episode: str
    history_episode: str
    http_agent_id: str
    http_episode_id: str


def _binding(identity):
    if not isinstance(identity, HostIdentity):
        raise AccountingError("missing_host_identity")
    for name in ("run_id", "session_id", "action_episode", "history_episode", "http_agent_id", "http_episode_id"):
        _identifier(getattr(identity, name))
    if any(getattr(identity, name) is None for name in ("run", "session", "analyzer")):
        raise AccountingError("missing_owner_reference")
    if not isinstance(identity.run, HostEpisodeAnchor) or identity.run.run_id != identity.run_id:
        raise AccountingError("invalid_episode_anchor")
    if identity.action_episode != identity.history_episode:
        raise AccountingError("action_history_episode_mismatch")
    path = _path(identity.state_path)
    return HostBinding(identity.run_id, identity.session_id, identity.run, identity.session,
                       identity.analyzer, path, Path(identity.state_path).expanduser().absolute(),
                       identity.action_episode, identity.history_episode, identity.http_agent_id,
                       identity.http_episode_id)


def accepted_usage(usage):
    """Validate an already extracted usage object; never accept response bodies.

    Unknown fields are dropped. Output aliases are alternatives, never sums.
    Missing or conflicting accepted generation is a failure, not zero.
    This does not establish the backend's field semantics or draft-model cost.
    """
    if not isinstance(usage, dict):
        raise AccountingError("accepted_usage_missing")
    result = {}
    for name in ("completion_tokens", "output_tokens", "generated_tokens", "prompt_tokens",
                 "input_tokens", "total_tokens", "reasoning_tokens"):
        if name in usage:
            result[name] = _count(usage[name])
    outputs = [result[name] for name in ("completion_tokens", "output_tokens", "generated_tokens") if name in result]
    if not outputs:
        raise AccountingError("accepted_usage_missing")
    if len(set(outputs)) != 1:
        raise AccountingError("accepted_usage_alias_conflict")
    inputs = [result[name] for name in ("prompt_tokens", "input_tokens") if name in result]
    if len(set(inputs)) > 1:
        raise AccountingError("input_usage_alias_conflict")
    for group, names in (
        ("prompt_tokens_details", ("cached_tokens", "image_tokens")),
        ("completion_tokens_details", ("reasoning_tokens", "accepted_prediction_tokens", "rejected_prediction_tokens")),
    ):
        if group in usage:
            if not isinstance(usage[group], dict):
                raise AccountingError("invalid_usage_details")
            kept = {name: _count(usage[group][name]) for name in names if name in usage[group]}
            if kept:
                result[group] = kept
    return outputs[0], inputs[0] if inputs else None, result


class _DurableLog:
    def __init__(self, path, common, clock):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # A new episode may never append to an old run or truncate it.
        with self.path.open("x", encoding="utf-8") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        # Persist the new directory entry as well as subsequent file contents.
        directory = os.open(self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        self.common, self.clock = dict(common), clock
        self.sequence = self.last_ns = 0
        self.events = []
        self.failed = False

    def append(self, event, fields):
        if self.failed:
            raise AccountingError("durable_host_log_failed")
        try:
            at = self.clock()
            if type(at) is not int or at < self.last_ns:
                raise AccountingError("host_clock_regressed")
            row = {"schema_version": 1, **self.common, "sequence": self.sequence + 1,
                   "monotonic_ns": at, "event": event, **fields}
            encoded = json.dumps(row, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException as exc:
            self.failed = True
            raise AccountingError("durable_host_log_failed") from exc
        self.sequence, self.last_ns = row["sequence"], at
        frozen = _freeze(row)
        self.events.append(frozen)
        return frozen


class _Ledger:
    def __init__(self, path, common, stop_event, observers, clock):
        self._lock = threading.RLock()
        self._stop_event = stop_event
        self._invalid_reason = None
        self._notifying = False
        self._observers = tuple(observers)
        if (any(not callable(observer) for observer in self._observers)
                or len({_observer_key(observer) for observer in self._observers}) != len(self._observers)):
            stop_event.set()
            raise AccountingError("invalid_observer")
        try:
            self._log = _DurableLog(path, common, clock)
        except BaseException:
            stop_event.set()
            raise

    @property
    def valid(self):
        return self._invalid_reason is None

    @property
    def invalid_reason(self):
        return self._invalid_reason

    @property
    def events(self):
        with self._lock:
            return tuple(self._log.events)

    def _fail(self, reason):
        if self._invalid_reason is None:
            self._invalid_reason = reason
            self._stop_event.set()
            try:
                self._log.append("accounting_invalid", {"reason": reason})
            except AccountingError:
                pass
        raise AccountingError(self._invalid_reason)

    def _ready(self):
        if not self.valid:
            raise AccountingError(self._invalid_reason)
        if self._notifying:
            self._fail("reentrant_observer_mutation")

    def _emit(self, event, fields):
        try:
            row = self._log.append(event, {**fields, "after_stop": not self.valid})
        except AccountingError:
            self._fail("durable_host_log_failed")
        # State is updated before emit. Callbacks see only an immutable durable
        # packet and its current totals. An observer is never retried/redelivered.
        self._notifying = True
        failed = False
        try:
            for observer in self._observers:
                try:
                    observer(row)
                except BaseException:
                    failed = True
        finally:
            self._notifying = False
        if failed:
            self._fail("host_observer_failed")
        return row


class InitialResetCapture(_Ledger):
    """Separate factory-time public RESET capture, before a harness session exists.

    Caller brackets the actual public wrapper.reset, not a configured expectation.
    This has no before-frame or prediction target. It never increments an
    official scorecard count or fabricates a framework history record.
    """
    def __init__(self, *, run_id, run, capture_id, log_path, stop_event,
                 observers=(), clock=time.monotonic_ns):
        _identifier(run_id)
        _identifier(capture_id)
        if not isinstance(run, HostEpisodeAnchor) or run.run_id != run_id:
            raise AccountingError("invalid_episode_anchor")
        self._run_id, self._run, self._capture_id = run_id, run, capture_id
        self._started = self._finished = False
        self._execution = None
        self._claimed_by = None
        super().__init__(log_path, {"run_id": run_id, "capture_id": capture_id,
                                   "scope": "sdk_initialization"}, stop_event, observers, clock)

    @property
    def run_id(self):
        return self._run_id

    @property
    def run(self):
        return self._run

    @property
    def capture_id(self):
        return self._capture_id

    def dispatch(self, *, run):
        with self._lock:
            self._ready()
            if run is not self.run or self._started:
                self._fail("initial_reset_owner_or_duplicate")
            self._started = True
            return self._emit("initial_reset_dispatch", {"action": "RESET", "before_available": False,
                                                         "prediction_target_excluded": True})

    def receipt(self, *, run, execution, returned_action=None, full_reset=None, levels_completed=None):
        with self._lock:
            # A dispatch already made may finish after a stop/observer failure.
            # Preserve that physical fact; this never permits another dispatch.
            if self._notifying:
                self._fail("reentrant_observer_mutation")
            if run is not self.run or not self._started or self._finished:
                self._fail("initial_reset_receipt_association")
            if not isinstance(execution, str) or execution not in {"executed", "unknown"}:
                self._fail("invalid_initial_reset_execution")
            if execution == "executed" and returned_action != "RESET":
                self._fail("initial_reset_action_echo_mismatch")
            if full_reset is not None and type(full_reset) is not bool:
                self._fail("invalid_full_reset_field")
            if levels_completed is not None:
                try:
                    _count(levels_completed)
                except AccountingError:
                    self._fail("invalid_public_level_count")
            self._finished, self._execution = True, execution
            result = self._emit("initial_reset_receipt", {
                "action": "RESET", "execution": execution, "full_reset": full_reset,
                "levels_completed": levels_completed, "sdk_calls_executed": 1 if execution == "executed" else None,
                "taaf_history_commits": 0, "official_actions": None,
                "prediction_target_excluded": True, "before_available": False,
            })
            if execution == "unknown":
                self._fail("initial_reset_execution_unknown")
            return result


@dataclass(frozen=True)
class PhysicalTotals:
    known_accepted_target_tokens: int
    accepted_target_tokens: int | None
    unknown_usage_attempts: int
    pending_request: bool
    post_start_sdk_dispatches: int
    post_start_sdk_calls_executed: int
    sdk_calls_unknown: int
    initialization_sdk_calls_executed: int | None
    captured_sdk_calls_executed: int
    taaf_history_commits: int
    official_actions: int | None
    official_actions_sequence: int | None


class HostAccounting(_Ledger):
    """Registry-created single-owner ledger; all mutations require host proof."""
    def __init__(self, binding, *, log_path, stop_event, observers, clock, initialization):
        self._binding_record = binding
        self._closed = False
        self._requests = {}
        self._request = self._action = None
        self._transitions = set()
        self._commitments = set()
        self._known_tokens = self._unknown_usage = 0
        self._dispatches = self._sdk_executed = self._sdk_unknown = self._history_commits = 0
        self._last_usage_sequence = None
        self._official_actions = self._official_sequence = None
        self._initial_calls = 1 if initialization is not None else None
        common = {name: getattr(binding, name) for name in (
            "run_id", "session_id", "action_episode", "history_episode", "http_agent_id", "http_episode_id")}
        super().__init__(log_path, common, stop_event, observers, clock)
        self._emit("ownership_bound", {
            "canonical_state_path_sha256": hashlib.sha256(str(binding.canonical_state_path).encode()).hexdigest(),
            "initialization_capture_id": initialization.capture_id if initialization else None,
            "initialization_sdk_calls_executed": self._initial_calls,
            "initialization_receipt_sequence": initialization.events[-1]["sequence"] if initialization else None,
            "official_actions": None,
        })

    @property
    def binding(self):
        return self._binding_record

    @property
    def totals(self):
        with self._lock:
            return PhysicalTotals(self._known_tokens,
                None if self._unknown_usage or self._request is not None else self._known_tokens,
                self._unknown_usage, self._request is not None, self._dispatches, self._sdk_executed,
                self._sdk_unknown, self._initial_calls, (self._initial_calls or 0) + self._sdk_executed,
                self._history_commits, self._official_actions, self._official_sequence)

    def _owner(self, identity, *, terminal=False):
        if not terminal:
            self._ready()
        elif self._notifying:
            self._fail("reentrant_observer_mutation")
        if self._closed:
            self._fail("closed_host_session")
        try:
            current = _binding(identity)
        except (AccountingError, OSError, RuntimeError):
            self._fail("missing_or_invalid_host_identity")
        expected = self.binding
        names = ("run_id", "session_id", "canonical_state_path", "action_episode", "history_episode",
                 "http_agent_id", "http_episode_id")
        if any(getattr(current, name) != getattr(expected, name) for name in names):
            self._fail("stale_or_foreign_host_identity")
        if any(getattr(current, name) is not getattr(expected, name) for name in ("run", "session", "analyzer")):
            self._fail("cross_owner_host_identity")
        try:
            if expected.original_state_path.resolve() != expected.canonical_state_path:
                self._fail("state_path_symlink_changed")
        except (OSError, RuntimeError):
            self._fail("state_path_resolution_failed")

    def check_request_allowed(self, identity):
        with self._lock:
            self._owner(identity)
            if self._request is not None or self._action is not None:
                self._fail("request_with_unsettled_exchange")

    def check_action_allowed(self, identity):
        with self._lock:
            self._owner(identity)
            if self._request is not None or self._action is not None:
                self._fail("action_before_usage_or_prior_receipt")

    def request_started(self, identity, *, call_id, attempt_id, purpose):
        with self._lock:
            self.check_request_allowed(identity)
            try:
                key = (_identifier(call_id), _identifier(attempt_id))
            except AccountingError:
                self._fail("invalid_request_identifier")
            if not isinstance(purpose, str) or purpose not in {"main", "summary", "tail"}:
                self._fail("invalid_request_purpose")
            if key in self._requests or any(attempt_id == old[1] for old in self._requests):
                self._fail("duplicate_request_attempt")
            self._requests[key] = "pending"
            self._request = (key, purpose)
            return self._emit("request_started", {"call_id": call_id, "attempt_id": attempt_id, "purpose": purpose})

    def _terminal_request(self, identity, call_id, attempt_id, usage, error_type):
        self._owner(identity, terminal=True)
        try:
            _identifier(call_id)
            _identifier(attempt_id)
        except AccountingError:
            self._fail("invalid_request_identifier")
        key = (call_id, attempt_id)
        if self._request is None or self._request[0] != key or self._requests.get(key) != "pending":
            self._fail("stale_missing_or_duplicate_request_terminal")
        purpose = self._request[1]
        try:
            output, input_count, clean = accepted_usage(usage)
        except AccountingError as exc:
            self._request = None
            self._requests[key] = "unavailable"
            self._unknown_usage += 1
            self._emit("usage_unavailable", {"call_id": call_id, "attempt_id": attempt_id, "purpose": purpose,
                "accepted_target_tokens": None, "usage": None, "reason": str(exc), "error_type": error_type})
            self._fail(str(exc))
        # Physical cost is retained even if fsync/observer fails after this point.
        # Neither context rollback nor retry can subtract it.
        self._request = None
        self._requests[key] = "accounted"
        self._known_tokens += output
        self._last_usage_sequence = self._log.sequence + 1
        return self._emit("accepted_usage", {"call_id": call_id, "attempt_id": attempt_id, "purpose": purpose,
            "accepted_target_tokens": output, "reported_input_tokens": input_count, "usage": clean,
            "known_accepted_target_tokens_total": self._known_tokens, "error_type": error_type})

    def request_completed(self, identity, *, call_id, attempt_id, usage):
        with self._lock:
            return self._terminal_request(identity, call_id, attempt_id, usage, None)

    def request_failed(self, identity, *, call_id, attempt_id, error_type, usage=None):
        with self._lock:
            allowed = {"TimeoutError", "HTTPError", "ParseError", "TransportError", "OtherError"}
            safe_error = error_type if isinstance(error_type, str) and error_type in allowed else "OtherError"
            return self._terminal_request(identity, call_id, attempt_id, usage, safe_error)

    def action_dispatched(self, identity, *, transition_id, commitment_id, action, automatic=False):
        with self._lock:
            self.check_action_allowed(identity)
            try:
                _identifier(transition_id)
                _identifier(commitment_id)
            except AccountingError:
                self._fail("invalid_action_identifier")
            if (not isinstance(action, str) or action not in {"RESET", *[f"ACTION{i}" for i in range(1, 8)]}
                    or type(automatic) is not bool):
                self._fail("invalid_action_fields")
            if transition_id in self._transitions:
                self._fail("duplicate_action_transition")
            if commitment_id in self._commitments:
                self._fail("duplicate_action_commitment")
            if automatic and action != "RESET":
                self._fail("automatic_action_must_be_reset")
            if self._last_usage_sequence is None and not automatic:
                self._fail("action_without_accepted_usage")
            self._transitions.add(transition_id)
            self._commitments.add(commitment_id)
            self._action = (transition_id, commitment_id, action, automatic)
            self._dispatches += 1
            return self._emit("action_dispatch", {"transition_id": transition_id, "commitment_id": commitment_id,
                "action": action, "automatic": automatic, "last_accepted_usage_sequence": self._last_usage_sequence})

    def action_receipt(self, identity, *, transition_id, commitment_id, action, execution,
                       history_committed, levels_completed=None):
        with self._lock:
            self._owner(identity, terminal=True)
            try:
                _identifier(transition_id)
                _identifier(commitment_id)
            except AccountingError:
                self._fail("invalid_action_identifier")
            if self._action is None or (transition_id, commitment_id, action) != self._action[:3]:
                self._fail("stale_missing_or_duplicate_action_receipt")
            if (not isinstance(execution, str) or execution not in {"executed", "unknown"}
                    or type(history_committed) is not bool):
                self._fail("invalid_action_receipt_fields")
            if history_committed and execution != "executed":
                self._fail("unknown_execution_cannot_commit_history")
            if levels_completed is not None:
                try:
                    _count(levels_completed)
                except AccountingError:
                    self._fail("invalid_public_level_count")
            automatic = self._action[3]
            self._action = None
            self._sdk_executed += int(execution == "executed")
            self._sdk_unknown += int(execution == "unknown")
            self._history_commits += int(history_committed)
            result = self._emit("action_receipt", {"transition_id": transition_id, "commitment_id": commitment_id,
                "action": action, "execution": execution, "automatic": automatic,
                "history_committed": history_committed, "levels_completed": levels_completed})
            if execution == "unknown":
                self._fail("sdk_action_execution_unknown")
            return result

    def official_actions_observed(self, identity, *, total, source):
        """Explicit public count reconciliation; never inferred from SDK calls."""
        with self._lock:
            self._owner(identity)
            if self._request is not None or self._action is not None:
                self._fail("official_count_with_unsettled_exchange")
            try:
                _count(total)
            except AccountingError:
                self._fail("invalid_official_action_count")
            if (not isinstance(source, str)
                    or source not in {"public_sdk_scorecard", "official_scorecard", "synthetic_public_fixture"}):
                self._fail("invalid_official_count_source")
            if self._official_actions is not None and total < self._official_actions:
                self._fail("official_action_total_regressed")
            self._official_actions = total
            self._official_sequence = self._log.sequence + 1
            return self._emit("official_actions_observed", {"official_actions": total, "source": source})

    def close(self, identity):
        with self._lock:
            self.check_request_allowed(identity)
            result = self._emit("session_closed", {"known_accepted_target_tokens_total": self._known_tokens})
            self._closed = True
            return result


class HostAccountingRegistry:
    """Strong references prevent object-ID reuse and cross-owner analyzer reuse."""
    def __init__(self):
        self._lock = threading.RLock()
        self._owners = []

    def bind(self, identity, *, log_path, stop_event, initialization=None, observers=(), clock=time.monotonic_ns):
        with self._lock:
            try:
                binding = _binding(identity)
            except (AccountingError, OSError, RuntimeError):
                stop_event.set()
                raise AccountingError("missing_or_invalid_host_identity") from None
            collision_owner = None
            for owner in self._owners:
                prior = owner["binding"]
                collision = (prior.analyzer is binding.analyzer or prior.session is binding.session
                    or prior.run_id == binding.run_id or prior.session_id == binding.session_id
                    or prior.canonical_state_path == binding.canonical_state_path
                    or prior.http_agent_id == binding.http_agent_id or prior.http_episode_id == binding.http_episode_id
                    or prior.action_episode == binding.action_episode)
                if collision:
                    stop_event.set()
                    owner["stop_event"].set()
                    collision_owner = owner
                    break
            if collision_owner is None:
                # Reserve before constructing the ledger: constructor observers
                # cannot reenter bind and attach a second owner. Failed bindings
                # remain reserved and cannot be silently retried with fresh IDs.
                owner = {"binding": binding, "stop_event": stop_event, "ledger": None}
                self._owners.append(owner)
        if collision_owner is not None:
            # Never take a ledger/capture lock under the registry lock. A host
            # observer may inspect/register another episode without deadlock.
            old = collision_owner["ledger"]
            if old is not None:
                with old._lock:
                    old._fail("ownership_registry_collision")
            raise AccountingError("ownership_registry_collision")
        if initialization is not None:
            if not isinstance(initialization, InitialResetCapture):
                stop_event.set()
                raise AccountingError("invalid_or_reused_initial_reset_capture")
            with initialization._lock:
                if (not initialization.valid or not initialization._finished
                    or initialization._execution != "executed" or initialization.run is not binding.run
                    or initialization.run_id != binding.run_id or initialization._claimed_by is not None):
                    stop_event.set()
                    raise AccountingError("invalid_or_reused_initial_reset_capture")
                # Claim before creating a new ledger, even across registries.
                initialization._claimed_by = owner
        try:
            ledger = HostAccounting(binding, log_path=log_path, stop_event=stop_event,
                observers=observers, clock=clock, initialization=initialization)
        except Exception:
            stop_event.set()
            raise
        with self._lock:
            owner["ledger"] = ledger
        if stop_event.is_set():
            with ledger._lock:
                ledger._fail("host_binding_stopped")
        return ledger
