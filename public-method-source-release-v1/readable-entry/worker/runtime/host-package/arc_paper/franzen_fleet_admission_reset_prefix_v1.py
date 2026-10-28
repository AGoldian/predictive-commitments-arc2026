# SPDX-License-Identifier: MIT-0
"""Explicit v3 accounting/clock selection; frozen queue policy is inherited.

The actual post-copy played solver must be configured before SDK factories.
No hook or clock is installed merely by importing this module.
"""
from __future__ import annotations

from .automatic_reset_prefix_v1 import install_for_admission
from .common_fleet_governor_v2 import govern as _reset_prefix_govern

from functools import wraps
from pathlib import Path
import time

from . import franzen_host_accounting_reset_prefix_v1 as accounting
from . import franzen_fleet_admission as policy
from .franzen_fleet_admission import CommonFleetConfig, common_mode, host_admitted_play_one
from .fleet_gate import GateBroken


class FleetAdmission(policy.FleetAdmission):
    async def govern(self, coroutine):
        try:
            return await _reset_prefix_govern(self, coroutine)
        finally:
            overlay = self.accounting._automatic_reset_prefix_overlay
            if self.physically_closed():
                try:
                    overlay.close_journal()
                except BaseException:
                    self._fail("prefix_journal_finalize_failed")
                    raise

    """The same queue policy, bound to the explicit configured host clock."""
    def __init__(self, solver, games, config, accounting_fleet, *, log_root, hard_stop,
                 models=None, clock=None, priority_module=None):
        joined_clock = accounting_fleet.common_clock(solver, config)
        if clock is not None and clock is not joined_clock:
            accounting_fleet.fail('admission_clock_differs_from_configured_clock')
        super().__init__(solver, games, config, accounting_fleet, log_root=log_root,
            hard_stop=hard_stop, models=models, clock=joined_clock, priority_module=priority_module)
        try:
            accounting_fleet.join_common_admission(self, solver, config, joined_clock)
        except BaseException:
            self.finish_governor()
            raise


def configure_common_fleet(solver, *, config, log_root, hard_stop, models=None,
                           sdk_verifier=None, clock=time.monotonic):
    """Only the actual played solver, after pristine copies and before factories."""
    config.validate()
    if not callable(hard_stop) or hasattr(solver, '_arc_paper_common_configuration'):
        raise ValueError('fresh played solver and explicit real hard-stop callback required')
    kwargs = {'log_root': Path(log_root) / 'accounting', 'stop_event': solver._stop_event}
    if sdk_verifier is not None:
        kwargs['sdk_verifier'] = sdk_verifier
    fleet = accounting.configure_fleet(**kwargs)
    solver._arc_paper_common_configuration = (config, Path(log_root), hard_stop, models, fleet)
    fleet.prepare_common_clock(solver, config, clock)
    return fleet


def common_agent_mode(agent):
    owner = accounting._FLEET._agents.get(id(agent))
    return owner is not None and owner[0] is agent and common_mode(owner[1].solver)


def host_admitted_run_games(original):
    """Select the v3 singleton and clock join; original solver owns task/drain code."""
    @wraps(original)
    async def wrapped(solver, games):
        if not common_mode(solver):
            return await original(solver, games)
        config, root, hard_stop, models, fleet = solver._arc_paper_common_configuration
        try:
            if fleet is not accounting._FLEET:
                fleet.fail('common_runtime_singleton_differs')
            if fleet.stop_event.is_set():
                raise GateBroken('fleet_stopped_before_worker_registration')
            admission = FleetAdmission(solver, games, config, fleet, log_root=root,
                hard_stop=hard_stop, models=models)
            solver._arc_paper_fleet_admission = admission
            install_for_admission(admission, journal_path=Path(root) / "automatic-reset-prefix.jsonl")
            return await admission.govern(original(solver, games))
        except BaseException:
            solver._stop_event.set()
            raise
    return wrapped
