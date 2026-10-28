# SPDX-License-Identifier: MIT-0
"""Explicit trusted B1/A1/P loader. Byte/source checks are not remote attestation."""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import MappingProxyType

POLICY_SHA256 = 'eef252ac22a0a6a7da696c5fbbac607e4085b1b9434d8b834f78b64ea71b6165'
PREFIX_SHA256 = '63890808464c7df57e51cf0d97ce0a2a27ca65e10e1e71840626a8e309c79fb6'
GOVERNOR_SHA256 = '3cb63ac4dae7c69ec62a38d3eb7de84710d292774d1dded3e44799213c3fd26d'



TRANSPORT_PROFILE = 'bounded-json-byte-derived-nodes-v2'
DEVELOPMENT_PROFILE_SHA256 = '7a0ffd3305f144cc3e17e01aeabe89bc04cfa52b651ce5efe24d1b490db35301'
BOUNDS_SHA256 = '22dcf677a5eab3aca6a902919fa7bca2988d1cd4d4be2507c61213d6516419aa'

class LoaderError(ValueError):
    pass


def _need(value, reason):
    if not value:
        raise LoaderError(reason)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _file(root, relative):
    root = Path(root).resolve(strict=True)
    path = root / relative
    _need(type(relative) is str and relative and not Path(relative).is_absolute()
          and '..' not in Path(relative).parts, 'unsafe_loader_path')
    _need(not path.is_symlink() and path.resolve(strict=True).is_relative_to(root), 'loader_path_escape')
    return path


PROFILE = 'learned-child-witness-runtime-v1'
PROOF_FIELDS = ('profile', 'arm', 'policy_sha256', 'prefix_module_sha256', 'governor_source_sha256', 'loader_source_sha256', 'predecessor_solver_sha256', 'successor_solver_sha256', 'host_module', 'admission_module', 'transport_profile', 'development_profile_sha256')
SOLVER_PATH = 'ARC3-Inference/inference/framework/solver.py'
PREDECESSOR_PATH = 'runtime/patched-source/' + SOLVER_PATH
POLICY_PATH = 'configs/automatic-reset-prefix-policy-v1.json'
MODULES = ('allocation', 'automatic_reset_prefix_v1', 'bounded_child_io', 'capacity_runtime', 'common_fleet_governor_v2', 'evidence_history', 'fleet_gate', 'franzen_fleet_admission', 'franzen_fleet_admission_reset_prefix_v1', 'franzen_fleet_admission_v2', 'franzen_host_accounting', 'franzen_host_accounting_reset_prefix_v1', 'franzen_host_accounting_v2', 'franzen_host_accounting_v3', 'franzen_prediction_runtime', 'governor_trace_v2', 'host_accounting', 'learned_host_model_binding_v1', 'paired_model_loader', 'prediction_adapter', 'predictions', 'receipt_integrity', 'reset_prefix_arm_loader_v1', 'reset_prefix_integrity_v1', 'inference_child_witness_v1')


class RuntimeLoader:
    def __init__(self, trusted, source, runtime, final_source):
        self.trusted, self.source = Path(trusted).resolve(strict=True), Path(source).resolve(strict=True)
        _need(runtime.get('transport_profile')==TRANSPORT_PROFILE and runtime.get('development_profile_sha256')==DEVELOPMENT_PROFILE_SHA256,'explicit_transport_profile_required')
        # Fresh private copies: callers cannot silently mutate the checked inventory.
        self.runtime = MappingProxyType({k: runtime[k] for k in PROOF_FIELDS})
        self.modules = MappingProxyType(dict(runtime['final_module_sha256']))
        self.final_source = MappingProxyType(dict(final_source))
        self.prepared = False
        _need(set(self.modules) == set(('arc_paper/__init__.py', 'arc_paper/allocation.py', 'arc_paper/automatic_reset_prefix_v1.py', 'arc_paper/bounded_child_io.py', 'arc_paper/capacity_runtime.py', 'arc_paper/common_fleet_governor_v2.py', 'arc_paper/evidence_history.py', 'arc_paper/fleet_gate.py', 'arc_paper/franzen_fleet_admission.py', 'arc_paper/franzen_fleet_admission_reset_prefix_v1.py', 'arc_paper/franzen_fleet_admission_v2.py', 'arc_paper/franzen_host_accounting.py', 'arc_paper/franzen_host_accounting_reset_prefix_v1.py', 'arc_paper/franzen_host_accounting_v2.py', 'arc_paper/franzen_host_accounting_v3.py', 'arc_paper/franzen_prediction_runtime.py', 'arc_paper/governor_trace_v2.py', 'arc_paper/host_accounting.py', 'arc_paper/learned_host_model_binding_v1.py', 'arc_paper/paired_model_loader.py', 'arc_paper/prediction_adapter.py', 'arc_paper/predictions.py', 'arc_paper/receipt_integrity.py', 'arc_paper/reset_prefix_arm_loader_v1.py', 'arc_paper/reset_prefix_integrity_v1.py', 'arc_paper/inference_child_witness_v1.py')), 'exact_runtime_module_inventory_required')
        _need(runtime['schema_version'] == 1 and self.runtime['profile'] == PROFILE
              and type(self.runtime['arm']) is str
              and self.runtime['arm'] in ('B1', 'A1', 'P')
              and runtime['policy_path'] == POLICY_PATH
              and self.runtime['host_module'] == 'arc_paper.franzen_host_accounting_reset_prefix_v1'
              and self.runtime['admission_module'] == 'arc_paper.franzen_fleet_admission_reset_prefix_v1',
              'unexpected_loader_policy')
        _need(self.runtime['policy_sha256'] == POLICY_SHA256
              and self.runtime['prefix_module_sha256'] == PREFIX_SHA256
              and self.runtime['governor_source_sha256'] == GOVERNOR_SHA256,
              'unreviewed_loader_components')
        _need(self.final_source[SOLVER_PATH] == self.runtime['successor_solver_sha256'], 'solver_inventory_mismatch')
        self.verify()

    def verify(self):
        for name, digest in self.final_source.items():
            _need(_sha(_file(self.source, name).read_bytes()) == digest, 'loaded_source_checksum_mismatch')
        for name, digest in self.modules.items():
            _need(_sha(_file(self.trusted / 'runtime/host-package', name).read_bytes()) == digest,
                  'loaded_module_checksum_mismatch')
        for name, field in (('automatic_reset_prefix_v1', 'prefix_module_sha256'),
                            ('common_fleet_governor_v2', 'governor_source_sha256'),
                            ('reset_prefix_arm_loader_v1', 'loader_source_sha256')):
            _need(self.modules['arc_paper/' + name + '.py'] == self.runtime[field], 'module_proof_mismatch')
        _need(_sha(_file(self.trusted, POLICY_PATH).read_bytes()) == self.runtime['policy_sha256'],
              'policy_checksum_mismatch')
        _need(_sha(_file(self.trusted, PREDECESSOR_PATH).read_bytes()) == self.runtime['predecessor_solver_sha256'],
              'predecessor_solver_checksum_mismatch')

        _need(self.runtime['transport_profile']==TRANSPORT_PROFILE and self.runtime['development_profile_sha256']==DEVELOPMENT_PROFILE_SHA256,'explicit_transport_profile_required')
        _need(self.modules['arc_paper/bounded_child_io.py']==BOUNDS_SHA256,'transport_bounds_source_required')
        bounds=self.checked_module('arc_paper.bounded_child_io')
        _need(_sha(json.dumps(bounds.DEVELOPMENT_PROFILE,sort_keys=True,separators=(',',':'),allow_nan=False).encode())==DEVELOPMENT_PROFILE_SHA256,'loaded_transport_profile_changed')

    def checked_module(self, name):
        module = importlib.import_module(name)
        relative = 'arc_paper/__init__.py' if name == 'arc_paper' else name.replace('.', '/') + '.py'
        actual = Path(module.__file__).resolve(strict=True)
        expected = _file(self.trusted / 'runtime/host-package', relative)
        _need(actual == expected and _sha(actual.read_bytes()) == self.modules[relative], 'imported_module_origin_mismatch')
        return module

    def prepare(self, played_solver):
        """Actual CapacityRunContext callback, after configuration before factories."""
        try:
            _need(not self.prepared, 'source_preparation_reused')
            self.verify()
            module = sys.modules.get(type(played_solver).__module__)
            _need(module is not None, 'actual_solver_module_missing')
            path = _file(self.source, SOLVER_PATH)
            prefix = self.checked_module('arc_paper.automatic_reset_prefix_v1')
            source = prefix.SourceMethods.from_loaded(module, path,
                _file(self.trusted, PREDECESSOR_PATH).read_bytes(), self.runtime['arm'])
            prefix.prepare_source_methods(played_solver, source,
                policy_bytes=_file(self.trusted, POLICY_PATH).read_bytes())
            self.verify()
            self.prepared = True
            self.checked_module("arc_paper.inference_child_witness_v1").install_for_configured_fleet(played_solver,loader=self)
            return dict(schema_version=1, **self.runtime, source_methods_prepared=True,
                        actual_played_solver=True, source_prepared_before_factories=True)
        except BaseException:
            played_solver._stop_event.set()
            configuration = getattr(played_solver, '_arc_paper_common_configuration', None)
            if type(configuration) is tuple and len(configuration) == 5:
                try:
                    configuration[4].fail('reset_prefix_loader_preparation_failed')
                except BaseException:
                    pass  # Sticky fleet failure is retained; preserve the original refusal.
            raise


def bootstrap(trusted, source, runtime, final_source):
    """Call at the explicit cell-10 host import seam, before unpickling solver."""
    fresh = ('inference.framework.solver', 'inference.agent.tool_agent', 'taaf.game', 'taaf.game_api')
    for name in fresh + tuple('arc_paper.' + n for n in MODULES if n != 'reset_prefix_arm_loader_v1'):
        _need(name not in sys.modules, 'runtime_loaded_before_checksum_gate')
    loader = RuntimeLoader(trusted, source, runtime, final_source)
    loader.checked_module('arc_paper')
    for name in MODULES:
        loader.checked_module('arc_paper.' + name)
    loader.verify()
    return loader
