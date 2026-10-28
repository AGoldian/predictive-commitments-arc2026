# SPDX-License-Identifier: MIT-0
"""One exact Benchmark.run scope; pristine snapshots never own live locks."""
from contextvars import ContextVar
from datetime import datetime

_CURRENT = ContextVar('arc26_capacity_benchmark_scope', default=None)

class CapacityRunContext:
    def __init__(self, benchmark, configure):
        if benchmark is None or not callable(configure):
            raise ValueError('exact benchmark and trusted configure callback required')
        self.benchmark, self.configure = benchmark, configure
        self.played_solver = self.fleet = self.failure_reason = None
        self._token = None
        self._entered = self._configured = False

    def __enter__(self):
        if self._entered or _CURRENT.get() is not None:
            raise ValueError('capacity scope is one-time and cannot nest')
        self._entered = True
        self._token = _CURRENT.set(self)
        return self

    def __exit__(self, kind, value, traceback):
        try:
            if kind is not None:
                self.failure_reason = self.failure_reason or 'benchmark_call_failed'
                if self.played_solver is not None:
                    self.played_solver._stop_event.set()
        finally:
            _CURRENT.reset(self._token)
        return False

def capacity_played_solver_ready(benchmark, played_solver, soft_end_time):
    context = _CURRENT.get()
    if context is None:
        return soft_end_time
    pristine = benchmark.solver
    if (benchmark is not context.benchmark or context._configured
            or context.played_solver is not None or played_solver is pristine
            or type(played_solver) is not type(pristine)
            or not getattr(played_solver, '_setup_called', False)
            or getattr(pristine, '_setup_called', False)
            or played_solver._stop_event is pristine._stop_event
            or hasattr(pristine, '_arc_paper_common_configuration')
            or hasattr(played_solver, '_arc_paper_common_configuration')):
        context.failure_reason = 'unexpected_benchmark_copy_or_setup_boundary'
        played_solver._stop_event.set()
        raise ValueError(context.failure_reason)
    context.played_solver = played_solver
    try:
        fleet, deadline = context.configure(played_solver)
        actual = getattr(played_solver, '_arc_paper_common_configuration', None)
        if (type(actual) is not tuple or len(actual) != 5 or actual[4] is not fleet
                or fleet.stop_event is not played_solver._stop_event
                or not isinstance(deadline, datetime)):
            raise ValueError('configured fleet is not actual played solver owner')
        context.fleet = fleet
        context._configured = True
        # Only scalar deadline metadata enters the pristine serialized snapshot.
        played_solver.soft_end_time = pristine.soft_end_time = deadline
        return deadline
    except BaseException:
        context.failure_reason = 'played_solver_configuration_failed'
        played_solver._stop_event.set()
        actual = getattr(played_solver, '_arc_paper_common_configuration', None)
        if type(actual) is tuple and len(actual) == 5:
            context.fleet = actual[4]
        try:
            played_solver.teardown()
        except BaseException:
            context.failure_reason = 'played_solver_configuration_teardown_failed'
        raise
