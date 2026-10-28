# SPDX-License-Identifier: MIT-0
"""Prepared common cancellation owner; deliberately not wired into a runtime.

The real coordinator supplies the joined clock, stop Event, physical ownership
predicate, journal, hard-stop bridge and finalization. This helper owns no HTTP,
SDK or cost ledger. A successful hard-stop callback requests external custody;
it is not proof that processes were reaped. Synchronous callbacks/OS stalls
still require the separately bounded external supervisor.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import math
import sys


class GovernorError(RuntimeError):
    pass


def _number(value, name, *, positive=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or (value <= 0 if positive else value < 0)):
        raise GovernorError('invalid_'+name)
    return float(value)


@dataclass(frozen=True)
class _Bounds:
    admission: float
    drain: float
    whole: float
    teardown: float

    @classmethod
    def capture(cls, config):
        b = cls(_number(config.admission_deadline_monotonic, 'admission', positive=True),
                _number(config.drain_timeout_s, 'drain', positive=True),
                _number(config.whole_deadline_monotonic, 'whole', positive=True),
                _number(config.teardown_reserve_s, 'teardown', positive=True))
        if b.admission+b.drain+b.teardown > b.whole:
            raise GovernorError('common_deadline_reserves_missing')
        return b


@dataclass
class _InnerOutcome:
    value: object = None
    error: BaseException | None = None


@dataclass
class GovernorState:
    """Retained custody and failure evidence, including pending work on failure."""
    owner: object
    bounds: _Bounds
    inner_task: asyncio.Task | None = None
    join_task: asyncio.Task | None = None
    first_stop_monotonic: float | None = None
    drain_end_monotonic: float | None = None
    first_stop_origin: str | None = None
    last_clock: float | None = None
    outer_cancellations: int = 0
    inner_cancel_count: int = 0
    hard_stop_attempted: bool = False
    hard_stop_returned: bool = False
    physically_closed_observed: bool = False
    disposition: str | None = None
    failures: list[tuple[str, BaseException]] = field(default_factory=list)
    inner_outcome: _InnerOutcome | None = None
    original_coroutine: object = None
    inner_entered: bool = False
    start_gate: asyncio.Event = field(default_factory=asyncio.Event)
    _inner_done_logged: bool = False

    def clock(self):
        now = _number(self.owner.clock(), 'common_clock')
        if self.last_clock is not None and now < self.last_clock:
            raise GovernorError('common_clock_decreased')
        self.last_clock = now
        return now

    def failure(self, stage, exc):
        self.failures.append((stage, exc))
        try:
            self.owner.solver._stop_event.set()
        except BaseException as stop_error:
            self.failures.append(('stop_event', stop_error))

    def record(self, event, **fields):
        try:
            self.owner._record(event, **fields)
        except BaseException as exc:
            self.failure('journal', exc)
            self.request_stop('journal_failure', record=False)

    def request_stop(self, origin, *, record=True):
        try:
            self.owner.solver._stop_event.set()
        except BaseException as exc:
            self.failure('stop_event', exc)
        if self.first_stop_origin is not None:
            return
        self.first_stop_origin = origin
        try:
            now = self.clock()
            self.first_stop_monotonic = now
            self.drain_end_monotonic = min(now+self.bounds.drain,
                self.bounds.admission+self.bounds.drain,
                self.bounds.whole-self.bounds.teardown)
        except BaseException as exc:
            self.failure('clock', exc)
            # No invented clock or deadline. The drive loop must fail closed.
        if record:
            self.record('governor_v2_stop_requested', origin=origin,
                first_stop_monotonic=self.first_stop_monotonic,
                drain_end_monotonic=self.drain_end_monotonic)

    def outer_cancel(self):
        self.outer_cancellations += 1
        self.request_stop('outer_cancel')
        self.record('governor_v2_outer_cancel_observed', count=self.outer_cancellations)

    def cancel_inner_once(self):
        if self.inner_task is None or self.inner_task.done() or self.inner_cancel_count:
            return
        self.inner_cancel_count = 1
        self.inner_task.cancel()
        self.close_unentered_original()
        self.record('governor_v2_inner_cancel_requested', count=1)

    def close_unentered_original(self):
        if not self.inner_entered and self.original_coroutine is not None:
            try:
                self.original_coroutine.close()
            except BaseException as exc:
                self.failure('coroutine_close', exc)

    def closure(self):
        try:
            closed = self.owner.physically_closed()
            if type(closed) is not bool:
                raise GovernorError('physical_closure_not_boolean')
        except BaseException as exc:
            self.failure('physical_closure', exc)
            self.request_stop('physical_closure_failure')
            return None
        if closed and not self.physically_closed_observed:
            self.physically_closed_observed = True
            self.record('governor_v2_physical_closure_observed')
        return closed

    def hard_stop(self):
        if self.hard_stop_attempted:
            return
        self.hard_stop_attempted = True
        reason = ('cancelled_fleet_drain_failed' if self.outer_cancellations
                  else 'physical_drain_failed')
        self.record('governor_v2_hard_stop_attempted', reason=reason)
        try:
            self.owner._hard_stop(reason)
            self.hard_stop_returned = True
        except BaseException as exc:
            self.failure('hard_stop_callback', exc)

    def normal_cutoff_drain(self):
        # Normal cutoff closes new work while an admitted exchange settles
        # inside the ORIGINAL drain. Early stops and genuine invalidity retain
        # the destructive failure path and never erase unknown accounting.
        return (self.first_stop_origin in {'admission_deadline', 'outer_cancel', 'shared_stop'}
                and self.first_stop_monotonic is not None
                and self.first_stop_monotonic >= self.bounds.admission
                and not self.failures
                and not getattr(self.owner, 'invalid_reason', None)
                and not getattr(getattr(self.owner, 'accounting', None), 'invalid_reason', None))

    async def run_inner(self, coroutine):
        # Capture even BaseException as data; it must not bypass custody by
        # escaping a detached task. The caller receives it after disposition.
        try:
            # No original work may enter until both custody tasks exist.
            await self.start_gate.wait()
            self.inner_entered = True
            outcome = _InnerOutcome(value=await coroutine)
        except BaseException as exc:
            outcome = _InnerOutcome(error=exc)
        self.inner_outcome = outcome
        return outcome

    async def drive(self):
        """Separate retained supervision task; outer callers only shield it."""
        try:
            self.record('governor_v2_started')
            while True:
                now = self.clock()
                if self.first_stop_origin is None:
                    if self.owner.solver._stop_event.is_set():
                        self.request_stop('shared_stop')
                    elif now >= self.bounds.admission:
                        self.request_stop('admission_deadline')
                done = self.inner_task.done()
                if done and not self._inner_done_logged:
                    self._inner_done_logged = True
                    if self.inner_outcome is None:
                        self.failure('inner_task', GovernorError('inner_outcome_missing'))
                    elif self.inner_outcome.error is not None:
                        exc = self.inner_outcome.error
                        if not isinstance(exc, asyncio.CancelledError) or self.first_stop_origin is None:
                            self.failure('inner_task', exc)
                    self.record('governor_v2_inner_task_done_observed')
                closed = self.closure()
                # A callback can consume time. Fresh observation, rather than
                # task.done or a prior loop clock, must precede success.
                now = self.clock()
                if self.first_stop_origin is None and now >= self.bounds.admission:
                    self.request_stop('admission_deadline')
                if self.first_stop_origin is not None:
                    end = self.drain_end_monotonic
                    if end is None or now >= end or closed is None:
                        self.failure('drain', GovernorError('physical_drain_incomplete'))
                        self.cancel_inner_once()
                        self.hard_stop()
                        self.disposition = 'hard_stop_requested' if self.hard_stop_returned else 'hard_stop_failed'
                        return
                if done and closed is True:
                    if getattr(self.owner, 'invalid_reason', None):
                        self.failure('coordinator', GovernorError('coordinator_invalid'))
                    if self.failures:
                        self.request_stop('failure')
                        self.hard_stop()
                        self.disposition = 'failed_physically_closed'
                    else:
                        self.disposition = 'physically_closed'
                    return
                if done and self.first_stop_origin is None:
                    self.request_stop('inner_done_physical_pending')
                if self.failures and self.first_stop_origin is None:
                    self.request_stop('failure')
                if self.first_stop_origin is not None:
                    if not self.normal_cutoff_drain():
                        self.cancel_inner_once()
                    end = self.drain_end_monotonic
                    if end is None or now >= end or closed is None:
                        self.failure('drain', GovernorError('physical_drain_incomplete'))
                        self.hard_stop()
                        self.disposition = 'hard_stop_requested' if self.hard_stop_returned else 'hard_stop_failed'
                        return
                delay = .02
                if self.drain_end_monotonic is not None:
                    delay = min(delay, max(0., self.drain_end_monotonic-now))
                else:
                    delay = min(delay, max(0., self.bounds.admission-now))
                if done:
                    # Waiting on an already-done task would spin and starve
                    # owner finalizers. A bounded async wait supplies a turn.
                    event = asyncio.Event()
                    try:
                        await asyncio.wait_for(event.wait(), timeout=delay)
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.wait({self.inner_task}, timeout=delay)
        except BaseException as exc:
            self.failure('join', exc)
            self.request_stop('join_failure')
            self.cancel_inner_once()
            self.hard_stop()
            self.disposition = 'hard_stop_requested' if self.hard_stop_returned else 'hard_stop_failed'
        finally:
            self.record('governor_v2_join_finished', disposition=self.disposition,
                        inner_done=self.inner_task.done(),
                        physical_closure_observed=self.physically_closed_observed,
                        hard_stop_attempted=self.hard_stop_attempted)
            # A final journal failure cannot turn a formerly normal join into
            # success or bypass its hard-stop disposition.
            if self.failures and not self.hard_stop_attempted:
                self.request_stop('final_journal_failure', record=False)
                self.cancel_inner_once()
                self.hard_stop()
                self.disposition = 'failed_physically_closed' if self.physically_closed_observed else 'hard_stop_requested'


async def govern(owner, coroutine):
    """Drop-in prepared seam for ``govern(self, original_coroutine)``.

    The state remains on the coordinator after return/raise. Pending inner
    work after a hard-stop disposition is intentionally retained, not silently
    cancelled again or represented as physically closed.
    """
    state = None
    try:
        if hasattr(owner, '_arc_paper_governor_v2'):
            raise GovernorError('one_governor_invocation_per_coordinator')
        state = GovernorState(owner, _Bounds.capture(owner.config))
        owner._arc_paper_governor_v2 = state
        state.original_coroutine = coroutine
        now = state.clock()
        if now >= min(state.bounds.admission+state.bounds.drain,
                      state.bounds.whole-state.bounds.teardown):
            raise GovernorError('drain_envelope_already_expired')
        inner_wrapper = state.run_inner(coroutine)
        try:
            state.inner_task = asyncio.create_task(inner_wrapper)
        except BaseException:
            inner_wrapper.close()
            raise
        join_wrapper = state.drive()
        try:
            state.join_task = asyncio.create_task(join_wrapper)
        except BaseException:
            join_wrapper.close()
            raise
        state.start_gate.set()
        while not state.join_task.done():
            try:
                await asyncio.shield(state.join_task)
            except asyncio.CancelledError:
                state.outer_cancel()
        # drive captures failures as data. A direct private join-task cancel is
        # unexpected, but must also leave a real stop disposition.
        if state.join_task.cancelled():
            state.failure('join', GovernorError('protected_join_cancelled'))
            state.request_stop('join_cancelled')
            state.cancel_inner_once()
            state.hard_stop()
        if getattr(owner, 'invalid_reason', None) and not state.failures:
            state.failure('coordinator', GovernorError('coordinator_invalid'))
        if not state.failures and state.closure() is not True:
            state.failure('final_closure', GovernorError('physical_closure_lost'))
        if state.failures and not state.hard_stop_attempted:
            # An outer cancellation/journal failure can arrive after drive's
            # final callback. The caller must enforce the same disposition.
            state.request_stop('final_failure', record=False)
            state.cancel_inner_once()
            state.hard_stop()
            state.disposition = ('hard_stop_failed' if not state.hard_stop_returned else
                'failed_physically_closed' if state.physically_closed_observed else 'hard_stop_requested')
        if state.failures:
            try:
                owner._fail('common_governor_v2_failed')
            except BaseException as exc:
                state.failures.append(('coordinator_fail', exc))
        if state.outer_cancellations:
            raise asyncio.CancelledError()
        if state.failures:
            raise state.failures[0][1]
        if (state.disposition != 'physically_closed' or not state.inner_task.done()
                or not state.physically_closed_observed):
            raise GovernorError('no_complete_physical_disposition')
        return state.inner_outcome.value
    except BaseException as error:
        if state is None:
            # A malformed configuration may preclude a valid GovernorState.
            # Each callback is isolated so stop failure cannot bypass custody
            # or replace the original refusal. Retain secondary failures.
            failures = [('startup', error)]
            for stage, callback in (
                ('coroutine_close', coroutine.close),
                ('stop_event', owner.solver._stop_event.set),
                ('hard_stop_callback', lambda: owner._hard_stop('failed_fleet_drain_unsettled')),
            ):
                try:
                    callback()
                except BaseException as exc:
                    failures.append((stage, exc))
            owner._arc_paper_governor_v2_startup_failures = failures
        elif (state.inner_task is None or state.join_task is None
              or state.disposition is None):
            # Custody may already exist when startup or the orchestration
            # boundary fails. Both task references alone are not a completed
            # disposition (for example, opening the private start gate can
            # fail). Retain them and request the same external failure stop.
            stage = 'orchestration' if state.inner_entered else 'startup'
            state.failure(stage, error)
            state.request_stop(stage+'_failure', record=False)
            state.cancel_inner_once()
            # Cancellation before a Task first enters its wrapper does not
            # close the original coroutine passed as an argument. The start
            # gate proves non-entry here, including an eager task factory.
            if not state.inner_entered:
                state.close_unentered_original()
            state.hard_stop()
            state.disposition = 'hard_stop_requested' if state.hard_stop_returned else 'hard_stop_failed'
        raise
    finally:
        prior_error = sys.exc_info()[1]
        try:
            owner.finish_governor()
        except BaseException as exc:
            if state is not None:
                state.failure('finish_governor', exc)
                state.request_stop('finish_governor_failure', record=False)
                state.cancel_inner_once()
                state.hard_stop()
            if prior_error is not None:
                # Keep the original inner failure or deferred external cancel
                # visible while retaining finalizer failure in state.
                raise prior_error from exc
            raise


class CommonFleetGovernorV2:
    """Optional mixin for a future exclusive builder; currently unintegrated."""
    async def govern(self, coroutine):
        return await govern(self, coroutine)
