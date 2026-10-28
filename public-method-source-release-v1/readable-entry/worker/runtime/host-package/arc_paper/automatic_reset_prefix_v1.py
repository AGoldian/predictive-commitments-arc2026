# SPDX-License-Identifier: MIT-0
"""Prepared overlay only: source-gated RESET prefix, not installed on import.

The successor loader must select the transformed solver/host and this explicit
overlay before workers. Method references/file hashes are trusted host-loader
evidence, not runtime attestation. No game/model/provider is imported here.
"""
from __future__ import annotations

import ast
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
import hashlib
import json
import math
import os
from pathlib import Path
import threading

from .franzen_host_accounting_v2 import HostStopped

UPSTREAM_MODIFICATION_NOTICE = '# Modified for ARC Prize research, 2026-10-28.\n# This redistributed file has project modifications; exact source changes\n# and original provenance are recorded by the package manifests and patches.\n# Original copyright notices and Apache-2.0 terms are retained.\n'
POLICY_SHA256 = 'eef252ac22a0a6a7da696c5fbbac607e4085b1b9434d8b834f78b64ea71b6165'
SOLVER_SHA256 = {
    'B0': '3247cd61235c5b31d867bbb97b552349e9413a29574cef839d8b0986a8aa01e7',
    'B1': '13a9ec792526ab7a2cedc8857ff8331d9049df307d9a81ceb803287744b9642e',
    'A1': '13a9ec792526ab7a2cedc8857ff8331d9049df307d9a81ceb803287744b9642e',
    'P': '13a9ec792526ab7a2cedc8857ff8331d9049df307d9a81ceb803287744b9642e',
}
HOST_SHA256 = '5d469872723420de6c60319de854cca671fef42ac2c642db8d8981f1b8889455'
B0_ACCOUNTING_SHA256 = 'eef25094f632d4df1851e8d1dcdc91a04ae5333f617cae43af0a6ed215998788'
HOST_SUCCESSOR_MODULE = 'franzen_host_accounting_reset_prefix_v1'
B0_SUCCESSOR_MODULE = 'franzen_b0_accounting_reset_prefix_v1'
ADMISSION_SUCCESSOR_MODULE = 'franzen_fleet_admission_reset_prefix_v1'
B0_ADMISSION_SUCCESSOR_MODULE = 'franzen_b0_admission_reset_prefix_v1'
ADMISSION_SHA256 = 'e67f95d927a72177e831dc813ff9ed239bc42d9ad01b4d1841225dcbb5a9307b'
B0_ADMISSION_SHA256 = '7026899696651e5f73fec08a6a959a1c459f1dbb61f20395e79a14a402d02867'
# Only permitted harness/SDK-facing infrastructure; never game implementations.
INFRASTRUCTURE_SHA256 = {
    'B1': {
        'tool_agent.py': '309f4318d0cf2d545b5b1e81b5aab16e528f8e3f21dc2fb6a4c559a1ec23b7fa',
        'game.py': '267f0b4bdb4d559f6ec7467bbdf325423d6f353847a4383d663cc6e2251675d8',
        'game_api.py': '3b68a570d98c39c761eb07c544535bd3201924ac7eaafea23ac074f03879215c',
    },
    'B0': {
        'tool_agent.py': 'be70d956b971be7e55cd31a22dcc30e904107148e9f7330fe79faeddbe26aee7',
        'game.py': 'a35c6d729d6817272d73ebe56c44ff660616b9ad827e7dc51154bff52df21ff2',
        'game_api.py': '95d9f7e536db73ef03341d51ef9aa610efd87c304b2602ac1e056faa8f8ec6fc',
        'benchmark.py': '737535e879c581cd9c85bfc9dac816d87ad90bd3c6feb8a3f86bb666b0939a3d',
    },
}
CLAIM_AST_SHA256 = 'deee2eaebc4773bdf76cb79f83916bf5b78310ee796de1e12be8ebd004049734'
RESET_AST_SHA256 = 'aee3d881196c2a1c1a5c68882e0a93057b6771ebffffccfa3035e010a92904d2'
_AUTOMATIC = ContextVar('arc_paper_automatic_reset_prefix_v1', default=None)
_LOGICAL = ContextVar('arc_paper_reset_prefix_logical_v1', default=None)


class PrefixError(ValueError):
    """Sticky overlay integrity refusal, safe against broad upstream catches."""


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _replace_once(source, old, new):
    if source.count(old) != 1:
        raise PrefixError('source_anchor_not_unique')
    return source.replace(old, new, 1)


def transform_solver_source(raw, arm):
    """Return separate successor bytes; never edits the input file.

    The original claim/reset bodies and branch order are preserved. The loader
    still has to select this new file and wire the explicit overlay/host hook.
    """
    if arm not in SOLVER_SHA256 or type(raw) is not bytes or _sha(raw) != SOLVER_SHA256[arm]:
        raise PrefixError('solver_source_pin_mismatch')
    text = raw.decode()
    text = _replace_once(text, 'from __future__ import annotations\n',
        'from __future__ import annotations\n\nfrom arc_paper.automatic_reset_prefix_v1 import (\n'
        '    source_warmup_claim, source_execute_claimed_reset, source_game_over_reset,\n)\n')
    text = _replace_once(text, 'if self.solver._claim_warmup_slot():', 'if source_warmup_claim(self):')
    text = _replace_once(text, '            self._execute_auto_reset()\n        try:',
        '            source_execute_claimed_reset(self)\n        try:')
    text = _replace_once(text, '                    self._execute_auto_reset()\n                    continue',
        '                    source_game_over_reset(self)\n                    continue')
    if arm == 'B0':
        text = _replace_once(text, 'from arc_paper.franzen_b0_accounting import ',
                            'from arc_paper.' + B0_SUCCESSOR_MODULE + ' import ')
        text = _replace_once(text, 'from arc_paper.franzen_b0_admission import ',
                            'from arc_paper.' + B0_ADMISSION_SUCCESSOR_MODULE + ' import ')
    else:
        text = _replace_once(text, 'from arc_paper.franzen_host_accounting_v3 import ',
                            'from arc_paper.' + HOST_SUCCESSOR_MODULE + ' import ')
        text = _replace_once(text, 'from arc_paper.franzen_fleet_admission_v2 import ',
                            'from arc_paper.' + ADMISSION_SUCCESSOR_MODULE + ' import ')
    ast.parse(text)
    return (UPSTREAM_MODIFICATION_NOTICE + text).encode()


def transform_host_source(raw):
    """Return a distinct host-v3 successor with mandatory real SDK lease guard.

    A future builder must explicitly redirect every accounting/B0 import to
    that successor module; this function does not mutate globals or install it.
    """
    if type(raw) is not bytes or _sha(raw) != HOST_SHA256:
        raise PrefixError('host_source_pin_mismatch')
    text = _replace_once(raw.decode(), 'from __future__ import annotations\n',
        'from __future__ import annotations\n\nfrom .automatic_reset_prefix_v1 import assert_sdk_dispatch, host_prefix_logical_preflight\n')
    text = _replace_once(text,
        '                        proof = binding.fleet.identity(binding)  # expected stop may still refuse here\n',
        '                        proof = binding.fleet.identity(binding)  # expected stop may still refuse here\n'
        '                        assert_sdk_dispatch(binding, commitment)\n')
    text = _replace_once(text, '    def logical_preflight(self, agent, purpose="main"):\n',
                         '    @host_prefix_logical_preflight\n    def logical_preflight(self, agent, purpose="main"):\n')
    ast.parse(text)
    return text.encode()


def transform_b0_accounting_source(raw):
    """Select the guarded host class through the separate B0 fleet, not B1's.

    The original B0 singleton, batch/leaf logic and terminal wrapper are retained.
    The future loader must select this distinct module at every B0 import seam.
    """
    if type(raw) is not bytes or _sha(raw) != B0_ACCOUNTING_SHA256:
        raise PrefixError('b0_accounting_source_pin_mismatch')
    text = _replace_once(raw.decode(), 'from . import franzen_host_accounting_v3 as bridge\n',
                         'from . import ' + HOST_SUCCESSOR_MODULE + ' as bridge\n')
    ast.parse(text)
    return text.encode()


def transform_admission_source(raw, arm):
    """Explicit distinct helper import selection and pre-worker installation.

    The existing governor is deliberately unchanged here. A separately reviewed
    governor successor must be composed by the future checksum-gated builder.
    """
    expected = B0_ADMISSION_SHA256 if arm == 'B0' else ADMISSION_SHA256
    if arm not in SOLVER_SHA256 or type(raw) is not bytes or _sha(raw) != expected:
        raise PrefixError('admission_source_pin_mismatch')
    text = _replace_once(raw.decode(), 'from __future__ import annotations\n',
        'from __future__ import annotations\n\nfrom .automatic_reset_prefix_v1 import install_for_admission\n')
    if arm == 'B0':
        text = _replace_once(text, 'from . import franzen_b0_accounting as accounting\n',
                            'from . import ' + B0_SUCCESSOR_MODULE + ' as accounting\n')
        text = _replace_once(text, 'from .franzen_host_accounting_v3 import HostStopped\n',
                            'from .franzen_host_accounting_v2 import HostStopped\n')
    else:
        text = _replace_once(text, 'from . import franzen_host_accounting_v3 as accounting\n',
                            'from . import ' + HOST_SUCCESSOR_MODULE + ' as accounting\n')
    text = _replace_once(text, '            solver._arc_paper_fleet_admission = admission\n',
        '            solver._arc_paper_fleet_admission = admission\n'
        '            install_for_admission(admission, journal_path=Path(root) / "automatic-reset-prefix.jsonl")\n')
    ast.parse(text)
    return text.encode()


def transform_infrastructure_source(raw, name, arm):
    """Redirect every whitelisted ToolAgent/GameAPI/Game/B0 Benchmark import.

    There is no arbitrary replacement list or caller-supplied expected digest.
    The common Benchmark orchestration and worker configure imports still need
    explicit successor-loader selection before any SDK factory.
    """
    pins = INFRASTRUCTURE_SHA256.get('B0' if arm == 'B0' else 'B1', {})
    if (arm not in SOLVER_SHA256 or name not in pins or type(raw) is not bytes
            or _sha(raw) != pins[name]):
        raise PrefixError('infrastructure_source_pin_mismatch')
    text = raw.decode()
    host_old = 'franzen_b0_accounting' if arm == 'B0' else 'franzen_host_accounting_v3'
    host_new = B0_SUCCESSOR_MODULE if arm == 'B0' else HOST_SUCCESSOR_MODULE
    admission_old = 'franzen_b0_admission' if arm == 'B0' else 'franzen_fleet_admission_v2'
    admission_new = B0_ADMISSION_SUCCESSOR_MODULE if arm == 'B0' else ADMISSION_SUCCESSOR_MODULE
    if name != 'benchmark.py':
        text = _replace_once(text, 'from arc_paper.' + host_old + ' import ',
                            'from arc_paper.' + host_new + ' import ')
    if name in ('tool_agent.py', 'benchmark.py'):
        text = _replace_once(text, 'from arc_paper.' + admission_old + ' import ',
                            'from arc_paper.' + admission_new + ' import ')
    ast.parse(text)
    return text.encode()


@dataclass(frozen=True)
class SourceMethods:
    """Captured loader evidence, not a certificate against malicious Python."""
    module: object = field(repr=False)
    path: Path
    arm: str
    predecessor_sha256: str
    successor_sha256: str
    solver_type: object = field(repr=False)
    session_type: object = field(repr=False)
    claim: object = field(repr=False)
    reset: object = field(repr=False)
    action: object = field(repr=False)
    claim_code: object = field(repr=False)
    reset_code: object = field(repr=False)
    action_code: object = field(repr=False)

    @classmethod
    def from_loaded(cls, module, path, predecessor, arm):
        expected = transform_solver_source(predecessor, arm)
        path = Path(path).resolve(strict=True)
        if (path.read_bytes() != expected or Path(module.__file__).resolve() != path):
            raise PrefixError('loaded_solver_file_not_successor')
        solver_type, session_type = module.HarnessSolver, module._HarnessGameSession
        claim, reset = solver_type.__dict__['_claim_warmup_slot'], session_type.__dict__['_execute_auto_reset']
        action = session_type.__dict__['_execute_action']
        tree = ast.parse(expected)
        for name, digest in (('_claim_warmup_slot', CLAIM_AST_SHA256), ('_execute_auto_reset', RESET_AST_SHA256)):
            nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
            if len(nodes) != 1 or _sha(ast.dump(nodes[0], include_attributes=False).encode()) != digest:
                raise PrefixError('original_method_ast_changed')
        for method in (claim, reset, action):
            if Path(method.__code__.co_filename).resolve() != path:
                raise PrefixError('captured_method_file_mismatch')
        # Compilation reads trusted source only; it executes no import/class.
        compiled = compile(expected, str(path), 'exec')
        for owner_name, method in (('HarnessSolver', claim), ('_HarnessGameSession', reset),
                                   ('_HarnessGameSession', action)):
            owner_code = next(c for c in compiled.co_consts if hasattr(c, 'co_name') and c.co_name == owner_name)
            expected_code = next(c for c in owner_code.co_consts if hasattr(c, 'co_name') and c.co_name == method.__name__)
            if method.__code__ != expected_code:
                raise PrefixError('captured_method_not_exact_compiled_source')
        return cls(module, path, arm, _sha(predecessor), _sha(expected), solver_type,
                   session_type, claim, reset, action, claim.__code__, reset.__code__, action.__code__)

    def check_solver(self, solver):
        # The host loader and its source DAG remain trusted. Recheck file and
        # exact captured references; no claim about arbitrary globals/.pth.
        raw = self.path.read_bytes()
        if (type(solver) is not self.solver_type
                or _sha(raw) != self.successor_sha256
                or self.module.HarnessSolver is not self.solver_type
                or self.module._HarnessGameSession is not self.session_type
                or self.solver_type.__dict__.get('_claim_warmup_slot') is not self.claim
                or self.session_type.__dict__.get('_execute_auto_reset') is not self.reset
                or self.session_type.__dict__.get('_execute_action') is not self.action
                or self.claim.__code__ is not self.claim_code or self.reset.__code__ is not self.reset_code
                or self.action.__code__ is not self.action_code):
            raise PrefixError('captured_source_owner_changed')

    def check(self, session):
        self.check_solver(session.solver)
        if type(session) is not self.session_type:
            raise PrefixError('captured_session_type_changed')


@dataclass(frozen=True)
class _PreparedSource:
    source: SourceMethods
    policy_bytes: bytes


def prepare_source_methods(solver, source_methods, *, policy_bytes):
    """Explicit actual played-copy hook after configuration, before factories.

    The prospective loader creates SourceMethods from its final gated file. No
    live source/locks are placed on the pristine Benchmark template or copies.
    """
    if (type(source_methods) is not SourceMethods or type(policy_bytes) is not bytes
            or _sha(policy_bytes) != POLICY_SHA256):
        raise PrefixError('missing_source_methods')
    source_methods.check_solver(solver)
    configuration = getattr(solver, '_arc_paper_common_configuration', None)
    if (type(configuration) is not tuple or len(configuration) != 5
            or configuration[0].arm != source_methods.arm
            or configuration[4].stop_event is not solver._stop_event
            or configuration[4]._games or hasattr(solver, '_arc_paper_fleet_admission')
            or hasattr(solver, '_arc_paper_automatic_reset_source')):
        solver._stop_event.set()
        raise PrefixError('source_preparation_not_fresh_played_copy')
    solver._arc_paper_automatic_reset_source = _PreparedSource(source_methods, policy_bytes)


def install_for_admission(coordinator, *, journal_path):
    """Called by the distinct helper after actual coordinator creation."""
    solver, fleet = coordinator.solver, coordinator.accounting
    prepared = getattr(solver, '_arc_paper_automatic_reset_source', None)
    try:
        if type(prepared) is not _PreparedSource or prepared.source.arm != coordinator.config.arm:
            raise PrefixError('missing_prepared_runtime_source')
        source = prepared.source
        source.check_solver(solver)
        overlay = AutomaticResetPrefixOverlay(coordinator, source,
            policy_bytes=prepared.policy_bytes, journal_path=journal_path)
        overlay.install()
        return overlay
    except BaseException:
        fleet.fail('prefix_runtime_installation_failed')


class _Journal:
    def __init__(self, path):
        self.fd = os.open(Path(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        self.failed = False

    def append(self, row):
        if self.failed or self.fd is None:
            raise PrefixError('prefix_journal_unavailable')
        try:
            raw = (json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
            view = memoryview(raw)
            while view:
                written = os.write(self.fd, view)
                if written <= 0:
                    raise OSError('prefix_journal_zero_write')
                view = view[written:]
            os.fsync(self.fd)
        except BaseException:
            self.failed = True
            raise

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)


@dataclass(frozen=True, eq=False)
class _Cause:
    binding: object = field(repr=False)
    cause: str
    ordinal: int
    thread: int
    observed_monotonic: float
    issuer: object = field(repr=False)


@dataclass(frozen=True)
class _LogicalProof:
    overlay: object
    binding: object
    purpose: str
    thread: int


@dataclass
class _Automatic:
    overlay: object
    binding: object
    cause: _Cause
    prefix: bool
    before: object
    lease: object
    allocation: object
    phase: str = 'body_running'
    checked: bool = False
    commitment: object = None
    after: object = None

    @property
    def features_sha256(self):
        return self.allocation.features_sha256

    @property
    def allocation_sha256(self):
        return self.allocation.allocation_sha256


@dataclass(frozen=True)
class _Allocation:
    features_sha256: str
    allocation_sha256: str


class AutomaticResetPrefixOverlay:
    """Explicit callback overlay, using the existing actual coordinator/gate.

    Construction never installs it. A checksum-gated successor must call
    install() once before workers, select transformed solver/host modules and
    retain the normal terminal wrapper. It must also select the separate safe
    cancellation/drain governor. None of those composition choices is automatic.
    """
    def __init__(self, coordinator, source_methods, *, policy_bytes, journal_path):
        if (type(source_methods) is not SourceMethods or type(policy_bytes) is not bytes
                or _sha(policy_bytes) != POLICY_SHA256 or source_methods.arm != coordinator.config.arm):
            raise PrefixError('prefix_policy_or_source_mismatch')
        self.coordinator, self.source = coordinator, source_methods
        self._lock, self._issuer = threading.RLock(), object()
        self._claims, self._warmup_called, self._prefixes, self._busy = {}, set(), {}, {}
        self._terminal_close_attempts = {}
        self._ordinal, self._sequence, self.invalid_reason = 0, 0, None
        self._journal = _Journal(journal_path)
        self._installed = False

    def install(self):
        """Explicit new-loader hook; no import-time or frozen-source mutation."""
        with self._lock:
            c, f = self.coordinator, self.coordinator.accounting
            if (self._installed or getattr(f, '_automatic_reset_prefix_overlay', None) is not None
                    or getattr(c.solver, '_arc_paper_fleet_admission', None) is not c
                    or f.before_exchange != c.before_exchange or f.on_session_close != c.on_session_close
                    or f._agents or c._owners):
                self._fail('overlay_install_not_fresh_or_joined')
            f._automatic_reset_prefix_overlay = self
            f.before_exchange, f.on_session_close = self.before_exchange, self.on_session_close
            self._installed = True

    def _halt(self, reason):
        self.invalid_reason = self.invalid_reason or reason
        c = self.coordinator
        c.invalid_reason = c.invalid_reason or reason
        c.solver._stop_event.set()
        try:
            c.accounting.fail(reason)  # Existing host preserves already known cost.
        except BaseException:
            pass

    def _fail(self, reason):
        self._halt(reason)
        raise PrefixError(self.invalid_reason)

    def _event(self, event, binding, **fields):
        with self._lock:
            self._sequence += 1
            try:
                now = self.coordinator.clock()
                if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
                    raise PrefixError('invalid_prefix_clock')
                self._journal.append(dict(schema_version=1, namespace='automatic-reset-prefix-v1',
                    sequence=self._sequence, event=event, policy_sha256=POLICY_SHA256,
                    predecessor_solver_sha256=self.source.predecessor_sha256,
                    successor_solver_sha256=self.source.successor_sha256,
                    arm=self.source.arm, run_id=binding.anchor.run_id, session_id=binding.session_id,
                    action_episode=binding.ledger.binding.action_episode, monotonic=now,
                    monotonic_ns=round(now * 1e9), **fields))
            except BaseException:
                self._fail('prefix_journal_failed')

    def _owner(self, binding, *, terminal=False):
        c, f = self.coordinator, self.coordinator.accounting
        if (not self._installed or self.invalid_reason or c.invalid_reason
                or getattr(f, '_automatic_reset_prefix_overlay', None) is not self
                or binding.fleet is not f or binding.session.solver is not c.solver
                or getattr(c.solver, '_arc_paper_fleet_admission', None) is not c):
            self._fail('prefix_coordinator_or_accounting_join_changed')
        sid = c._bindings.get(id(binding))
        owner = c._owners.get(sid)
        if owner is None or owner.binding is not binding or owner.closed:
            self._fail('prefix_admission_owner_changed')
        if not terminal:
            f.identity(binding)  # Real direct common-clock/stop/source identity check.
        return sid, owner

    def _binding(self, session, *, terminal=False):
        try:
            self.source.check(session)
            binding = self.coordinator.accounting.binding_for_agent(session.analyzer)
            if binding.session is not session:
                self._fail('prefix_session_owner_changed')
            self._owner(binding, terminal=terminal)
            return binding
        except HostStopped:
            raise
        except BaseException:
            self._fail('prefix_session_or_source_owner_failed')

    def _begun(self, binding, owner):
        try:
            c = self.coordinator
            with c.gate._cv:
                c.gate._guard()
                active = c.gate._owned(owner.lease)
                if (not active.begun or owner.lease.session_id != c._bindings[id(binding)]
                        or active.ticket.boundary.binding_sha256 != binding.boundary_snapshot().binding_sha256
                        or active.ticket.boundary.features_sha256 != owner.feature_sha256
                        or active.ticket.boundary.model_sha256 != c.allocation_sha256):
                    raise PrefixError('unbegun_or_foreign_prefix_lease')
            return owner.lease
        except HostStopped:
            raise
        except BaseException:
            self._fail('absent_foreign_unbegun_lease')

    def _cause(self, binding, cause):
        with self._lock:
            if id(binding.session) in self._claims or id(binding.session) in self._busy:
                self._fail('duplicate_automatic_cause')
            self._ordinal += 1
            permit = _Cause(binding, cause, self._ordinal, threading.get_ident(), self.coordinator.clock(), self._issuer)
            self._claims[id(binding.session)] = permit
            return permit

    def warmup_claim(self, session):
        try:
            binding = self._binding(session)
            with self._lock:
                if id(session) in self._warmup_called:
                    self._fail('warmup_claim_repeated')
                self._warmup_called.add(id(session))
            result = self.source.claim(session.solver)  # Exact original once, including its lock/decrement.
            if type(result) is not bool:
                self._fail('warmup_claim_not_boolean')
            if result:
                self._cause(binding, 'warmup_claim')
            return result
        except HostStopped:
            raise
        except BaseException:
            self._fail('source_warmup_claim_failed')

    def game_over_reset(self, session):
        try:
            binding = self._binding(session)
            current = session._arc_paper_prediction_adapter.current
            if current is None or current.state != 'GAME_OVER' or session.last_engine_action == 'RESET':
                self._fail('public_game_over_source_condition_missing')
            self._cause(binding, 'public_game_over')
            return self.execute_claimed_reset(session)
        except HostStopped:
            raise
        except BaseException:
            self._fail('source_game_over_reset_failed')

    @staticmethod
    def _watermarks(snapshot):
        return dict(binding_sha256=snapshot.binding_sha256, action_sequence=snapshot.action_sequence,
            sdk_calls_executed=snapshot.sdk_calls_executed, taaf_history_commits=snapshot.taaf_history_commits,
            accepted_target_tokens=snapshot.accepted_target_tokens, logical_sequence=snapshot.logical_sequence,
            public_observation_sha256=snapshot.public_observation_sha256)

    def execute_claimed_reset(self, session):
        binding = self._binding(session, terminal=True)
        with self._lock:
            permit = self._claims.pop(id(session), None)
            if (permit is None or permit.binding is not binding or permit.issuer is not self._issuer
                    or permit.thread != threading.get_ident() or _AUTOMATIC.get() is not None):
                self._fail('missing_stale_foreign_source_cause')
        record, token = None, None
        try:
            sid, owner = self._owner(binding)
            before = binding.boundary_snapshot()
            prefix = owner.lease is None
            if prefix:
                if (id(session) in self._prefixes or before.logical_sequence != 0
                        or before.sdk_calls_executed != 0 or before.taaf_history_commits != 0
                        or before.action_sequence != 0 or before.accepted_target_tokens != 0):
                    self._fail('not_first_pending_free_prefix_boundary')
                self.coordinator.before_exchange(binding)  # Original per-arm feature freeze/acquire/begin.
                if self._watermarks(binding.boundary_snapshot()) != self._watermarks(before):
                    self._fail('prefix_boundary_changed_during_admission')
            elif (before.logical_sequence < 1 or owner.logical_sequence + 1 != before.logical_sequence):
                self._fail('automatic_tail_without_actual_logical_owner')
            lease = self._begun(binding, owner)
            record = _Automatic(self, binding, permit, prefix, before, lease,
                                _Allocation(owner.feature_sha256, self.coordinator.allocation_sha256))
            with self._lock:
                self._busy[id(session)] = record
                if prefix:
                    self._prefixes[id(session)] = record
            self._event('admitted', binding, cause=('first_public_game_over' if prefix and permit.cause == 'public_game_over' else permit.cause),
                cause_ordinal=permit.ordinal, cause_monotonic=permit.observed_monotonic,
                prefix=prefix, lease_id=lease.lease_id, features_sha256=record.features_sha256,
                allocation_sha256=record.allocation_sha256,
                before=self._watermarks(before))
            token = _AUTOMATIC.set(record)
            result = self.source.reset(session)  # Whole original body, including its original writes.
            _AUTOMATIC.reset(token)
            token = None
            # Full original body has returned. A cutoff after the actual SDK
            # entry permits terminal settlement, not another action/send.
            after = binding.boundary_snapshot(terminal=True)
            if (not record.checked or record.commitment is None
                    or after.binding_sha256 != before.binding_sha256
                    or after.logical_sequence != before.logical_sequence
                    or after.accepted_target_tokens != before.accepted_target_tokens
                    or after.action_sequence != before.action_sequence + 1
                    or after.sdk_calls_executed != before.sdk_calls_executed + 1
                    or after.taaf_history_commits != before.taaf_history_commits + 1):
                self._fail('automatic_body_not_exactly_one_settled_reset')
            commitment = record.commitment
            rows = binding.ledger.events[before.accounting_sequence:]
            receipts = [r for r in rows if r['event'] == 'action_receipt']
            dispatches = [r for r in rows if r['event'] == 'action_dispatch']
            if (len(dispatches) != 1 or len(receipts) != 1 or dispatches[0]['action'] != 'RESET'
                    or dispatches[0].get('automatic') is not True or receipts[0]['execution'] != 'executed'
                    or receipts[0]['history_committed'] is not True
                    or any(r.get('transition_id') != commitment.transition_id or r.get('commitment_id') != commitment.id
                           for r in (*dispatches, *receipts))):
                self._fail('automatic_receipts_not_exactly_joined')
            record.after, record.phase = after, 'body_finished'
            self._event('body_finished', binding, prefix=prefix, lease_id=lease.lease_id,
                transition_id=commitment.transition_id, commitment_id=commitment.id,
                after=self._watermarks(after))
            return result
        except HostStopped:
            if record is not None:
                if any(r['event'] == 'action_dispatch' for r in
                       binding.ledger.events[record.before.accounting_sequence:]):
                    record.phase = 'failed'
                    self._fail('host_stop_after_actual_sdk_dispatch')
                record.phase = 'refused'
            self._event('refused', binding, reason='host_stop', prefix=bool(record and record.prefix))
            raise
        except BaseException:
            if record is not None:
                record.phase = 'failed'
            self._fail('automatic_prefix_body_or_admission_failed')
        finally:
            if token is not None:
                _AUTOMATIC.reset(token)
            with self._lock:
                self._busy.pop(id(session), None)

    def before_exchange(self, binding):
        try:
            sid, owner = self._owner(binding)
            record = self._prefixes.get(id(binding.session))
            if id(binding.session) in self._busy or id(binding.session) in self._claims:
                self._fail('logical_request_during_automatic_body_or_claim')
            if record is None or record.phase == 'reused':
                return self.coordinator.before_exchange(binding)
            if record.phase != 'body_finished' or record.binding is not binding or owner.lease is not record.lease:
                self._fail('prefix_not_completed_for_logical_reuse')
            current = binding.boundary_snapshot()
            logical = _LOGICAL.get()
            if (current.logical_sequence != 0 or self._watermarks(current) != self._watermarks(record.after)
                    or self._begun(binding, owner) is not record.lease or owner.logical_sequence != 0
                    or owner.feature_sha256 != record.features_sha256
                    or self.coordinator.allocation_sha256 != record.allocation_sha256
                    or logical is None or logical.overlay is not self or logical.binding is not binding
                    or logical.thread != threading.get_ident() or logical.purpose not in ('main', 'summary')):
                self._fail('prefix_reuse_boundary_or_lease_changed')
            self._event('logical_reuse', binding, lease_id=record.lease.lease_id,
                features_sha256=record.features_sha256, allocation_sha256=record.allocation_sha256,
                purpose=logical.purpose, after=self._watermarks(current))
            record.phase = 'reused'  # Bridge performs its second snapshot/start, not this overlay.
        except HostStopped:
            raise
        except BaseException:
            self._fail('prefix_logical_preflight_failed')

    def assert_sdk_dispatch(self, binding, commitment):
        """Actual SDK seam: never calls pending-free boundary during an action."""
        try:
            sid, owner = self._owner(binding)
            c = self.coordinator
            with c.gate._cv:
                c.gate._guard()
                active = c.gate._owned(owner.lease)
                if (not active.begun or owner.lease.session_id != sid
                        or active.ticket.boundary.episode_id != binding.ledger.binding.action_episode
                        or active.ticket.boundary.binding_sha256 != self._binding_digest(binding)
                        or active.ticket.boundary.features_sha256 != owner.feature_sha256
                        or active.ticket.boundary.model_sha256 != c.allocation_sha256):
                    self._fail('sdk_without_actual_begun_owner')
            if binding.session._arc_paper_prediction_adapter.pending is not commitment:
                self._fail('sdk_private_commitment_changed')
            logical = c.accounting._logical[id(binding.agent)]
            automatic = _AUTOMATIC.get()
            if commitment.automatic:
                if (automatic is None or automatic.overlay is not self or automatic.binding is not binding
                        or self._busy.get(id(binding.session)) is not automatic or automatic.checked
                        or automatic.phase != 'body_running' or automatic.lease is not owner.lease
                        or automatic.cause.thread != threading.get_ident()
                        or automatic.features_sha256 != owner.feature_sha256
                        or automatic.allocation_sha256 != c.allocation_sha256
                        or commitment.action != {'name': 'RESET', 'data': {}}):
                    self._fail('sdk_without_private_source_reset_context')
                if automatic.prefix and logical['sequence'] != 0:
                    self._fail('prefix_sdk_after_logical_start')
                automatic.checked, automatic.commitment = True, commitment
            elif automatic is not None:
                self._fail('non_reset_inside_private_automatic_context')
            if not (automatic is not None and automatic.prefix):
                if logical['sequence'] < 1 or logical['sequence'] != owner.logical_sequence + 1:
                    self._fail('sdk_without_existing_logical_exchange')
        except HostStopped:
            raise
        except BaseException:
            self._fail('sdk_lease_guard_failed')

    @staticmethod
    def _binding_digest(binding):
        stable = dict(run_id=binding.anchor.run_id, session_id=binding.session_id,
            action_episode=binding.ledger.binding.action_episode,
            http_agent_id=binding.ledger.binding.http_agent_id,
            http_episode_id=binding.ledger.binding.http_episode_id,
            state_path=str(binding.ledger.binding.canonical_state_path))
        return _sha(json.dumps(stable, sort_keys=True, separators=(',', ':')).encode())

    def _semantic_prefix_session_close(self, binding, failed):
        self._owner(binding, terminal=True)
        record = self._prefixes.get(id(binding.session))
        if id(binding.session) in self._busy or id(binding.session) in self._claims:
            self._fail('close_with_incomplete_automatic_body')
        if record is not None:
            snapshot = binding.boundary_snapshot(terminal=True)
            if snapshot.logical_sequence == 0:
                if record.phase not in ('body_finished', 'refused', 'reused'):
                    self._fail('invalid_prefix_terminal_abort')
                self._event('aborted', binding, lease_id=record.lease.lease_id,
                    reason='no_real_logical_request', after=self._watermarks(snapshot),
                    successful_service=False, capacity_feasible=False)
                record.phase = 'aborted'
            elif record.phase != 'reused':
                self._fail('logical_started_without_completed_prefix_reuse')


    def _terminal_close_identity(self, binding, failed):
        # Physical custody is independent of a valid semantic terminal proof.
        # Retain the actual registered binding and Thread, never a caller flag.
        c, f = self.coordinator, self.coordinator.accounting
        sid, owner = c._joined_owner(binding)
        if (type(failed) is not bool or not self._installed
                or getattr(f, '_automatic_reset_prefix_overlay', None) is not self
                or binding.session.solver is not c.solver
                or getattr(c.solver, '_arc_paper_fleet_admission', None) is not c
                or c._plans.get(id(binding.game)) != sid or sid not in c._workers_started
                or f._sessions.get(id(binding.session)) is not binding
                or id(binding.session) not in f._closed):
            raise PrefixError('prefix_physical_close_identity_failed')
        with self._lock:
            key = id(binding)
            if key in self._terminal_close_attempts:
                raise PrefixError('prefix_physical_close_already_attempted')
            # One entry per genuine original binding; holding binding prevents
            # id reuse. Raw exception objects stay private, never prompt/log text.
            attempt = (binding, [])
            self._terminal_close_attempts[key] = attempt
        return attempt


    def on_session_close(self, binding, failed):
        try:
            attempt = self._terminal_close_identity(binding, failed)
        except BaseException:
            self._fail('prefix_physical_close_identity_failed')
        errors = attempt[1]
        primary, result = None, None
        try:
            self._semantic_prefix_session_close(binding, failed)
        except BaseException as exc:
            primary = exc
            errors.append(('prefix_semantic_close', exc))
            try:
                self._halt('prefix_terminal_close_failed')
            except BaseException as secondary:
                errors.append(('prefix_failure_propagation', secondary))
        finally:
            # The genuine host finally already revoked this exact session.
            # Invoke the unchanged coordinator once even if prefix semantics
            # or sticky failure propagation failed. This grants no settlement.
            try:
                result = self.coordinator.on_session_close(binding,
                    bool(failed or primary is not None))
            except BaseException as exc:
                errors.append(('coordinator_close', exc))
                if primary is None:
                    primary = exc
                try:
                    self._halt('prefix_terminal_close_failed')
                except BaseException as secondary:
                    errors.append(('coordinator_failure_propagation', secondary))
        if primary is not None:
            raise primary
        return result

    def close_journal(self):
        """After the actual governor/session closure only; not a physical stop."""
        with self._lock:
            if (self._busy or self._claims or not self.coordinator.physically_closed()
                    or any(not owner.closed for owner in self.coordinator._owners.values())):
                self._fail('prefix_journal_close_before_actual_owners_closed')
            self._journal.close()


def _overlay(session):
    coordinator = getattr(session.solver, '_arc_paper_fleet_admission', None)
    overlay = getattr(getattr(coordinator, 'accounting', None), '_automatic_reset_prefix_overlay', None)
    if type(overlay) is not AutomaticResetPrefixOverlay or overlay.coordinator is not coordinator:
        session.stop_event.set()
        raise PrefixError('missing_explicit_automatic_prefix_overlay')
    return overlay


def source_warmup_claim(session):
    return _overlay(session).warmup_claim(session)


def source_execute_claimed_reset(session):
    return _overlay(session).execute_claimed_reset(session)


def source_game_over_reset(session):
    return _overlay(session).game_over_reset(session)


def host_prefix_logical_preflight(original):
    """Explicit generated-host decorator carries actual purpose to callback.

    The original logical_preflight body still checks both real snapshots and
    alone emits/advances the logical request after a successful callback.
    """
    @wraps(original)
    def wrapped(fleet, agent, purpose='main'):
        binding = fleet.binding_for_agent(agent)
        overlay = _overlay(binding.session)
        if binding.fleet is not fleet or overlay.coordinator.accounting is not fleet or _LOGICAL.get() is not None:
            fleet.fail('nested_or_foreign_prefix_logical_preflight')
        token = _LOGICAL.set(_LogicalProof(overlay, binding, purpose, threading.get_ident()))
        try:
            return original(fleet, agent, purpose)
        finally:
            _LOGICAL.reset(token)
    return wrapped


def assert_sdk_dispatch(binding, commitment):
    overlay = getattr(binding.fleet, '_automatic_reset_prefix_overlay', None)
    if type(overlay) is not AutomaticResetPrefixOverlay:
        binding.fleet.fail('missing_explicit_sdk_prefix_guard')
    return overlay.assert_sdk_dispatch(binding, commitment)
