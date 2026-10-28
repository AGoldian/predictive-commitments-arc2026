# SPDX-License-Identifier: MIT-0
"""Host-only admission of complete requests followed by settled tool/history work.

This component neither executes requests nor observes a game. The host must make
truthful boundary assertions, bind opaque identities, and stop physical workers
on GateBroken. No prompt, payload, response, or model-facing priority is handled.
"""
from __future__ import annotations

import math
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable


class GateBroken(RuntimeError):
    """Persistent failure: no subsequent dispatch is permitted."""


class AdmissionCancelled(RuntimeError):
    """The session was cancelled, expired, or explicitly terminated."""


@dataclass(frozen=True)
class SettledBoundary:
    session_id: str
    episode_id: str
    binding_sha256: str
    action_watermark: int
    usage_watermark: int
    features_sha256: str
    model_sha256: str
    http_inflight: bool
    tool_inflight: bool
    pending_commit: bool
    history_settled: bool
    usage_available: bool


@dataclass(frozen=True)
class Lease:
    session_id: str
    lease_id: int
    owner_thread: int


@dataclass
class _Ticket:
    boundary: SettledBoundary
    snapshot: bytes
    multiplier: float
    owner_thread: int
    cancel_event: threading.Event | None
    deadline: float | None
    arrival: int
    enqueue_base: float
    admission_base: float
    enqueued_at: float


@dataclass
class _Active:
    lease: Lease
    ticket: _Ticket
    begun: bool = False


_HASH = re.compile(r"[0-9a-f]{64}\Z")
_TERMINAL = {"terminal", "failed", "cancelled"}
_REASONS = {"finished", "startup_failed", "request_failed", "tool_failed",
            "cancelled", "deadline", "host_stop", "unknown_usage"}


class FleetGate:
    """Readiness-aware bootstrap, then descending ``baseline(now) * multiplier``.

    All planned sessions are registered at construction. Calling acquire makes a
    session ready atomically with enqueue; an unavailable worker is never a
    barrier. A first service is recorded only by settle/handover after begin.
    Bootstrap uses frozen fleet order among ready unserved sessions. Served
    sessions may continue at baseline priority while another planned session is
    unready/active; those admissions are explicitly logged. Exact priority ties
    use enqueue order. Snapshot refresh retains the frozen multiplier.

    baseline_priority(bytes_snapshot, common_monotonic_now) must be pure, quick,
    and return a finite nonnegative plain scalar, without encoded tiers. It is
    evaluated outside the lock and committed only if the waiting generation is
    unchanged. No feature/model callback runs under this gate's lock.

    event_sink receives only whitelisted metadata, synchronously under the lock
    before a transition can dispatch. It must durably persist as required by the
    host, finish promptly, and never call mutating gate methods. Any sink failure
    permanently poisons the gate, invalidates logical leases, wakes waiters, and
    prevents new admissions. The host must still drain/stop physical work.
    """

    def __init__(self, planned_session_ids: tuple[str, ...], capacity: int,
                 baseline_priority: Callable[[bytes, float], float],
                 event_sink: Callable[[dict], None], *, model_sha256: str,
                 priority_semantics: str, clock: Callable[[], float] = time.monotonic,
                 poll_interval: float = 0.02, allow_uncontended_control: bool = False):
        if not isinstance(planned_session_ids, tuple) or not planned_session_ids:
            raise ValueError("freeze a nonempty tuple of opaque planned session IDs")
        if any(not isinstance(s, str) or not s or len(s) > 128 for s in planned_session_ids):
            raise ValueError("invalid opaque session ID")
        if len(set(planned_session_ids)) != len(planned_session_ids):
            raise ValueError("duplicate planned session")
        if type(capacity) is not int or not 0 < capacity <= len(planned_session_ids):
            raise ValueError("capacity must be in 1..fleet size")
        if capacity == len(planned_session_ids) and not allow_uncontended_control:
            raise ValueError("capacity must be smaller than fleet; explicit control only")
        if priority_semantics != "plain_nonnegative_scalar":
            raise ValueError("explicit plain scalar priority semantics required")
        if not isinstance(model_sha256, str) or not _HASH.fullmatch(model_sha256):
            raise ValueError("invalid frozen model hash")
        if not callable(baseline_priority) or not callable(event_sink):
            raise ValueError("priority callback and event sink required")
        if not math.isfinite(poll_interval) or not 0 < poll_interval <= 0.5:
            raise ValueError("invalid bounded poll interval")
        self.fleet = planned_session_ids
        self.capacity = capacity
        self.model_sha256 = model_sha256
        self._index = {sid: i for i, sid in enumerate(self.fleet)}
        self._priority = baseline_priority
        self._sink = event_sink
        self._clock = clock
        self._poll = poll_interval
        self._cv = threading.Condition(threading.RLock())
        self._waiting: dict[str, _Ticket] = {}
        self._active: dict[str, _Active] = {}
        self._states = {sid: "registered" for sid in self.fleet}
        self._served = {sid: False for sid in self.fleet}
        self._bindings: dict[str, tuple[str, str]] = {}
        self._watermarks: dict[str, tuple[int, int]] = {}
        self._cancelled: set[str] = set()
        self._version = self._arrival = self._lease_seq = self._event_seq = 0
        self._broken: str | None = None
        self._emitting = False
        with self._cv:
            self._emit("fleet_registered", planned_sessions=list(self.fleet),
                       uncontended_control=capacity == len(self.fleet))

    @staticmethod
    def _number(value: float, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError(f"{name} must be a finite scalar")
        try:
            result = float(value)
        except OverflowError:
            raise ValueError(f"{name} must be finite") from None
        if not math.isfinite(result) or result < 0:
            raise ValueError(f"{name} must be finite and nonnegative")
        return result

    def _guard(self):
        if self._broken:
            raise GateBroken(self._broken)
        if self._emitting:
            raise RuntimeError("event sink must not mutate the gate")

    def _sid(self, sid: str):
        if sid not in self._states:
            raise ValueError("session is not in frozen planned fleet")

    def _boundary(self, boundary: SettledBoundary, sid: str, *, allow_unknown=False):
        if not isinstance(boundary, SettledBoundary) or boundary.session_id != sid:
            raise ValueError("boundary session mismatch")
        if not isinstance(boundary.episode_id, str) or not boundary.episode_id or len(boundary.episode_id) > 128:
            raise ValueError("invalid opaque episode")
        for name in ("binding_sha256", "features_sha256", "model_sha256"):
            value = getattr(boundary, name)
            if not isinstance(value, str) or not _HASH.fullmatch(value):
                raise ValueError(f"invalid {name}")
        if boundary.model_sha256 != self.model_sha256:
            raise ValueError("frozen model mismatch")
        for name in ("action_watermark", "usage_watermark"):
            value = getattr(boundary, name)
            if type(value) is not int or value < 0:
                raise ValueError("watermarks must be nonnegative integers")
        for name in ("http_inflight", "tool_inflight", "pending_commit", "history_settled", "usage_available"):
            if type(getattr(boundary, name)) is not bool:
                raise ValueError("boundary assertions must be explicit booleans")
        if boundary.http_inflight or boundary.tool_inflight or boundary.pending_commit or not boundary.history_settled:
            raise ValueError("exchange is not settled")
        if not boundary.usage_available and not allow_unknown:
            raise ValueError("accepted usage unavailable")
        binding = (boundary.episode_id, boundary.binding_sha256)
        if sid in self._bindings and self._bindings[sid] != binding:
            raise ValueError("host ownership binding changed")
        old = self._watermarks.get(sid, (0, 0))
        if boundary.action_watermark < old[0] or boundary.usage_watermark < old[1]:
            raise ValueError("watermark regression")

    def _commit_boundary(self, boundary: SettledBoundary):
        sid = boundary.session_id
        self._bindings[sid] = (boundary.episode_id, boundary.binding_sha256)
        self._watermarks[sid] = (boundary.action_watermark, boundary.usage_watermark)

    def _poison(self, code: str):
        self._broken = code
        self._waiting.clear()
        self._active.clear()
        for sid, state in self._states.items():
            if state not in _TERMINAL:
                self._states[sid] = "failed"
        self._version += 1
        self._cv.notify_all()

    def _emit(self, event: str, sid: str | None = None, ticket: _Ticket | None = None, **fields):
        self._event_seq += 1
        record = {"schema_version": 1, "sequence": self._event_seq,
                  "event": event, "monotonic": self._clock(),
                  "capacity": self.capacity, "queue_count": len(self._waiting),
                  "queue_sessions": sorted(self._waiting, key=lambda s: self._waiting[s].arrival),
                  "active_count": len(self._active),
                  "active_sessions": sorted(self._active, key=self._index.__getitem__),
                  "bootstrap_complete": self._bootstrap_done()}
        if sid is not None:
            record.update(session_id=sid, fleet_index=self._index[sid], first_service=self._served[sid])
        if ticket:
            b = ticket.boundary
            record.update(arrival=ticket.arrival, baseline_at_enqueue=ticket.enqueue_base,
                          baseline_at_admission=None if event == "enqueue" else ticket.admission_base,
                          frozen_multiplier=ticket.multiplier,
                          action_watermark=b.action_watermark, usage_watermark=b.usage_watermark,
                          features_sha256=b.features_sha256, model_sha256=b.model_sha256,
                          binding_sha256=b.binding_sha256, episode_id=b.episode_id)
        record.update(fields)  # Only internal, fixed-key calls reach this private method.
        self._emitting = True
        try:
            self._sink(record)
        except BaseException as exc:
            self._poison("event_sink_failed:" + type(exc).__name__)
            raise GateBroken(self._broken) from None
        finally:
            self._emitting = False

    def _bootstrap_done(self):
        return all(self._served[sid] or self._states[sid] in _TERMINAL for sid in self.fleet)

    def _stop_reason(self, sid: str, ticket: _Ticket) -> str | None:
        if sid in self._cancelled or (ticket.cancel_event is not None and ticket.cancel_event.is_set()):
            return "cancelled"
        if ticket.deadline is not None and self._clock() >= ticket.deadline:
            return "deadline"
        return None

    def _prune(self):
        # Begun work keeps its physical slot until a settled endpoint or abort.
        for sid, ticket in list(self._waiting.items()):
            reason = self._stop_reason(sid, ticket)
            if reason:
                del self._waiting[sid]
                self._states[sid] = "cancelled"
                self._cancelled.add(sid)
                self._version += 1
                self._emit("cancel", sid, ticket, reason=reason, dispatch_started=False)
        for sid, active in list(self._active.items()):
            reason = self._stop_reason(sid, active.ticket)
            if reason and not active.begun:
                del self._active[sid]
                self._states[sid] = "cancelled"
                self._cancelled.add(sid)
                self._version += 1
                self._emit("cancel", sid, active.ticket, reason=reason, dispatch_started=False,
                           lease_id=active.lease.lease_id)
        self._cv.notify_all()

    def _new_ticket(self, sid, boundary, snapshot, multiplier, cancel_event, deadline, base):
        self._boundary(boundary, sid)
        if self._states[sid] in _TERMINAL or sid in self._cancelled:
            raise AdmissionCancelled("session is terminal")
        if sid in self._waiting or sid in self._active:
            raise ValueError("session already queued or leased")
        if type(snapshot) is not bytes or len(snapshot) > 65536:
            raise ValueError("immutable bounded baseline snapshot bytes required")
        multiplier = self._number(multiplier, "multiplier")
        if not 0.5 <= multiplier <= 1.5:
            raise ValueError("frozen multiplier must be in [0.5, 1.5]")
        if cancel_event is not None and not isinstance(cancel_event, threading.Event):
            raise ValueError("cancel_event must be a threading.Event")
        if deadline is not None:
            deadline = self._number(deadline, "deadline")
        self._arrival += 1
        ticket = _Ticket(boundary, snapshot, multiplier, threading.get_ident(), cancel_event,
                         deadline, self._arrival, base, base, self._clock())
        self._commit_boundary(boundary)
        self._waiting[sid] = ticket
        self._states[sid] = "ready"
        self._version += 1
        self._emit("enqueue", sid, ticket)
        return ticket

    def acquire(self, sid: str, boundary: SettledBoundary, baseline_snapshot: bytes, multiplier: float,
                *, cancel_event: threading.Event | None = None, deadline: float | None = None) -> Lease:
        with self._cv:
            self._guard()
            self._sid(sid)
        # The callback never runs under the condition lock, including enqueue.
        base = self._evaluate(baseline_snapshot, self._clock())
        with self._cv:
            self._guard()
            self._new_ticket(sid, boundary, baseline_snapshot, multiplier, cancel_event, deadline, base)
        return self._await(sid)

    def _evaluate(self, snapshot, now):
        try:
            if type(snapshot) is not bytes or len(snapshot) > 65536:
                raise ValueError("immutable bounded baseline snapshot bytes required")
            return self._number(self._priority(snapshot, now), "baseline priority")
        except BaseException as exc:
            with self._cv:
                self._poison("priority_callback_failed:" + type(exc).__name__)
            raise GateBroken(self._broken) from None

    def refresh(self):
        """Refresh all waiting scores at one time; discard stale generations."""
        while True:
            with self._cv:
                self._guard()
                self._prune()
                if not self._waiting or len(self._active) >= self.capacity:
                    return
                version = self._version
                candidates = tuple(self._waiting.items())
                now = self._clock()
            refreshed = [(sid, ticket, self._evaluate(ticket.snapshot, now)) for sid, ticket in candidates]
            with self._cv:
                self._guard()
                self._prune()
                if self._version != version:
                    continue
                for sid, ticket, base in refreshed:
                    ticket.admission_base = base
                self._emit("refresh", refreshed_sessions=[sid for sid, _, _ in refreshed], refresh_now=now,
                           refreshed_scores=[{"session_id": sid, "arrival": ticket.arrival,
                                              "baseline": base, "frozen_multiplier": ticket.multiplier}
                                             for sid, ticket, base in refreshed])
                while self._waiting and len(self._active) < self.capacity:
                    self._prune()
                    if not self._waiting:
                        break
                    done = self._bootstrap_done()
                    unserved = [sid for sid in self._waiting if not self._served[sid]]
                    if not done and unserved:
                        sid = min(unserved, key=lambda s: self._index[s])
                        mode = "bootstrap_first_service"
                    else:
                        mode = "adaptive" if done else "bootstrap_baseline_fallback"
                        sid = min(self._waiting, key=lambda s: (
                            -(self._waiting[s].admission_base * (self._waiting[s].multiplier if done else 1.0)),
                            self._waiting[s].arrival))
                    ticket = self._waiting[sid]
                    # Recheck stop/deadline directly at the admission transition.
                    if self._stop_reason(sid, ticket):
                        self._prune()
                        continue
                    effective = ticket.multiplier if done else 1.0
                    adjusted = ticket.admission_base * effective
                    if not math.isfinite(adjusted):
                        self._poison("adjusted_priority_overflow")
                        raise GateBroken(self._broken)
                    del self._waiting[sid]
                    self._lease_seq += 1
                    lease = Lease(sid, self._lease_seq, ticket.owner_thread)
                    self._active[sid] = _Active(lease, ticket)
                    self._states[sid] = "active"
                    self._version += 1
                    self._emit("admit", sid, ticket, lease_id=lease.lease_id, mode=mode,
                               effective_multiplier=effective, adjusted_priority=adjusted,
                               wait_seconds=max(0.0, self._clock() - ticket.enqueued_at),
                               no_unserved_ready=not unserved)
                    self._cv.notify_all()
                return

    def _await(self, sid: str) -> Lease:
        while True:
            self.refresh()
            with self._cv:
                self._guard()
                self._prune()
                if sid in self._active:
                    return self._active[sid].lease
                if self._states[sid] in _TERMINAL:
                    raise AdmissionCancelled("session cancelled, expired, or terminated")
                ticket = self._waiting[sid]
                timeout = self._poll
                if ticket.deadline is not None:
                    timeout = min(timeout, max(0, ticket.deadline - self._clock()))
                self._cv.wait(timeout)

    def _owned(self, lease: Lease) -> _Active:
        if not isinstance(lease, Lease) or lease.owner_thread != threading.get_ident():
            raise ValueError("lease belongs to another thread")
        active = self._active.get(lease.session_id)
        if active is None or active.lease is not lease:
            raise ValueError("lease is stale, foreign, or forged")
        return active

    def begin(self, lease: Lease):
        """Host must call directly before dispatch, then keep slot through settlement."""
        with self._cv:
            self._guard()
            active = self._owned(lease)
            if active.begun:
                raise ValueError("lease already began its one exchange")
            reason = self._stop_reason(lease.session_id, active.ticket)
            if reason:
                self._prune()
                raise AdmissionCancelled(reason)
            self._emit("begin", lease.session_id, active.ticket, lease_id=lease.lease_id)
            # A sink can take time: stop may change while the intent is persisted.
            reason = self._stop_reason(lease.session_id, active.ticket)
            if reason:
                self._prune()
                raise AdmissionCancelled(reason)
            active.begun = True

    def _settle(self, lease, boundary, completed_successfully=True):
        active = self._owned(lease)
        if type(completed_successfully) is not bool:
            self._poison("invalid_logical_outcome")
            raise GateBroken(self._broken)
        if not active.begun:
            raise ValueError("no complete request can settle before begin")
        try:
            self._boundary(boundary, lease.session_id)
        except ValueError:
            self._poison("invalid_settlement_boundary")
            raise GateBroken(self._broken) from None
        self._commit_boundary(boundary)
        sid = lease.session_id
        del self._active[sid]
        reason = self._stop_reason(sid, active.ticket)
        self._states[sid] = "cancelled" if reason else "idle"
        self._version += 1
        if completed_successfully and not self._served[sid]:
            self._served[sid] = True
            try:
                self._emit("first_service", sid, active.ticket, lease_id=lease.lease_id,
                           completed_action_watermark=boundary.action_watermark,
                           completed_usage_watermark=boundary.usage_watermark)
            except GateBroken:
                self._served[sid] = False  # A failed durable append is no bootstrap receipt.
                raise
        if not completed_successfully:
            self._emit("failed_exchange_settled", sid, active.ticket, lease_id=lease.lease_id,
                       accepted_usage_available=True,
                       completed_action_watermark=boundary.action_watermark,
                       completed_usage_watermark=boundary.usage_watermark)
        self._emit("settle", sid, active.ticket, lease_id=lease.lease_id,
                   completed_successfully=completed_successfully,
                   completed_action_watermark=boundary.action_watermark,
                   completed_usage_watermark=boundary.usage_watermark)
        if reason:
            self._cancelled.add(sid)
            self._emit("cancel", sid, active.ticket, reason=reason, dispatch_started=True)
        self._cv.notify_all()
        return active, reason

    def settle(self, lease: Lease, boundary: SettledBoundary, *, completed_successfully: bool = True):
        """Release a settled logical exchange; known failures earn no first service."""
        with self._cv:
            self._guard()
            self._settle(lease, boundary, completed_successfully)
        self.refresh()

    def handover(self, lease: Lease, boundary: SettledBoundary, baseline_snapshot: bytes,
                 multiplier: float, *, cancel_event: threading.Event | None = None,
                 deadline: float | None = None, completed_successfully: bool = True) -> Lease:
        """Atomic settled release + reenqueue, preserving known-cost failure retries."""
        with self._cv:
            self._guard()
            active = self._owned(lease)
            if not active.begun:
                raise ValueError("no complete request can hand over before begin")
        base = self._evaluate(baseline_snapshot, self._clock())
        with self._cv:
            self._guard()
            active = self._owned(lease)
            # Validate all enqueue arguments before releasing the owned slot.
            try:
                self._boundary(boundary, lease.session_id)
                value = self._number(multiplier, "multiplier")
                if not 0.5 <= value <= 1.5:
                    raise ValueError("invalid multiplier")
                if cancel_event is not None and not isinstance(cancel_event, threading.Event):
                    raise ValueError("invalid cancellation event")
                if deadline is not None:
                    self._number(deadline, "deadline")
            except ValueError:
                self._poison("invalid_handover_boundary_or_controls")
                raise GateBroken(self._broken) from None
            _, reason = self._settle(lease, boundary, completed_successfully)
            if reason:
                raise AdmissionCancelled(reason)
            self._new_ticket(lease.session_id, boundary, baseline_snapshot, value,
                             active.ticket.cancel_event if cancel_event is None else cancel_event,
                             active.ticket.deadline if deadline is None else deadline, base)
        return self._await(lease.session_id)

    def abort(self, lease: Lease, boundary: SettledBoundary, *, reason: str = "request_failed"):
        """Release a physically stopped exchange; never count failure as first service."""
        with self._cv:
            self._guard()
            active = self._owned(lease)
            if reason not in _REASONS:
                raise ValueError("unrecognized whitelisted failure reason")
            try:
                self._boundary(boundary, lease.session_id, allow_unknown=True)
            except ValueError:
                self._poison("unsafe_abort_boundary")
                raise GateBroken(self._broken) from None
            self._commit_boundary(boundary)
            del self._active[lease.session_id]
            self._states[lease.session_id] = "failed"
            self._version += 1
            self._emit("abort", lease.session_id, active.ticket, lease_id=lease.lease_id,
                       reason=reason, dispatch_started=active.begun,
                       accepted_usage_available=boundary.usage_available,
                       completed_action_watermark=boundary.action_watermark,
                       completed_usage_watermark=boundary.usage_watermark)
            if not boundary.usage_available or reason == "unknown_usage":
                self._poison("accepted_usage_unavailable")
                raise GateBroken(self._broken)
            self._cv.notify_all()
        self.refresh()

    def terminate(self, sid: str, *, reason: str = "finished"):
        """Explicitly close unready/idle/queued sessions, including startup failures."""
        with self._cv:
            self._guard()
            self._sid(sid)
            if reason not in _REASONS:
                raise ValueError("unrecognized whitelisted terminal reason")
            if sid in self._active:
                raise ValueError("active owner must settle or abort before termination")
            ticket = self._waiting.pop(sid, None)
            self._states[sid] = "failed" if reason.endswith("failed") else "terminal"
            self._version += 1
            self._emit("terminal", sid, ticket, reason=reason)
            if reason == "unknown_usage":
                self._poison("accepted_usage_unavailable")
                raise GateBroken(self._broken)
            self._cv.notify_all()
        self.refresh()

    def cancel(self, sid: str):
        """Cancel a wait immediately; begun physical work retains its slot."""
        with self._cv:
            self._guard()
            self._sid(sid)
            self._cancelled.add(sid)
            self._version += 1
            if sid in self._active and self._active[sid].begun:
                self._emit("cancel_requested", sid, self._active[sid].ticket,
                           lease_id=self._active[sid].lease.lease_id, dispatch_started=True)
            elif sid not in self._waiting and sid not in self._active:
                self._states[sid] = "cancelled"
                self._emit("cancel", sid, reason="cancelled", dispatch_started=False)
            self._prune()
        self.refresh()

    def snapshot(self) -> dict:
        """Nonsecret diagnostics remain available after a persistent failure."""
        with self._cv:
            return {"fleet": list(self.fleet), "states": dict(self._states),
                    "first_service": dict(self._served), "capacity": self.capacity,
                    "waiting": sorted(self._waiting, key=lambda s: self._waiting[s].arrival),
                    "active": list(self._active), "bootstrap_complete": self._bootstrap_done(),
                    "broken": self._broken, "generation": self._version}
