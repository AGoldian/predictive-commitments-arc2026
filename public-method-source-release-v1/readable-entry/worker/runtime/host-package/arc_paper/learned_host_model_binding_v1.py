# SPDX-License-Identifier: MIT-0
"""Trusted-host content joins before C2 configuration; no producer attestation.

The future host supplies pins after reviewing the actual pinned reader's fit
invocation and retained streams. JSON eligibility fields alone grant nothing.
"""
import hashlib
import json
import math
from pathlib import Path
import time

from . import paired_model_loader as pair
from . import reset_prefix_arm_loader_v1 as source_loader
from . import franzen_fleet_admission_reset_prefix_v1 as admission

PAIR_LOADER_SHA256 = 'c491a1046ad727c3c705d065ad5ebb54211b17ef2147b9764bd81acc4e7aee54'
ARM_LOADER_SHA256 = '22b726de7aa2a7894c926fa0288c0154251fda12f27d9ae1130f54ec438d467e'
ADMISSION_SHA256 = '7683e151dec0e029f84b2a6a1ca7d7eaf4f3db5072ac441a676ca35ae153f8b6'
READER_CLOSURE_SHA256 = 'b96fefa05b2eba74d761bd79aeb150a7215b9e165570db48cce2c7332b31b3c3'
ELIGIBILITY_POLICY_SHA256 = '84e62f4e332ff1a7381ac87038cb7fb0161a259fedfacc177c1b20d11e514d56'
METHOD_RECORD_SHA256 = '452cecfe71096d50eb3f9ec88d82bcbcdfe2c92184ef911d702e8f9ddbd67305'
OUTPUTS = frozenset(('paired-models.json', 'ordered-development-rows.json',
    'support-diagnostics.json', 'constant-controls.json', 'original-dispositions.json'))
FOLDS = frozenset(('closed_actual_runtime', 'actual_component_result',
    'external_parent_origin_freeze_native', 'prospective_reader_numerical_policy',
    'actual_worker_threads_and_clock', 'ordered_source_component_replay', 'source_owned_child_coverage'))
MAXIMUM_FILE_BYTES = 64_000_000
MAXIMUM_TOTAL_BYTES = 128_000_000


class BindingError(ValueError):
    pass


def need(condition, reason):
    if not condition:
        raise BindingError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def document(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate_binding_json_key')
            result[key] = value
        return result
    def nonfinite(_):
        raise BindingError('nonfinite_binding_json')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError):
        raise BindingError('invalid_binding_json') from None


def reader_fit_models(*, pair_path, expected_pair_sha256, inspection_path,
                      expected_inspection_sha256, expected_output_sha256):
    """Join actual reader-v5 fit outputs to host pins; never refit or rescue."""
    need(type(expected_output_sha256) is dict and set(expected_output_sha256) == OUTPUTS,
         'all_reader_fit_output_pins_required')
    need(expected_output_sha256['paired-models.json'] == expected_pair_sha256,
         'pair_host_pin_mismatch')
    inspection_path, pair_path = Path(inspection_path), Path(pair_path)
    need(pair_path == inspection_path.parent / 'paired-models.json', 'pair_reader_directory_mismatch')
    inspection_raw = pair.read_pinned(inspection_path, expected_inspection_sha256, MAXIMUM_FILE_BYTES)
    inspection = document(inspection_raw)
    need(type(inspection) is dict and inspection.get('schema_version') == 1
         and inspection.get('namespace') == 'collection-actual-run-inspection-v1'
         and inspection.get('mode') == 'fit'
         and inspection.get('status') == 'eligible_full_original_prefix_proven_suffix'
         and inspection.get('fit_eligible') is inspection.get('rows_written') is inspection.get('models_written') is True
         and inspection.get('failure_codes') == [], 'reader_fit_refused')
    folds = inspection.get('folds')
    need(type(folds) is dict and set(folds) == FOLDS
         and all(type(v) is dict and v == {'pass': True} for v in folds.values()), 'complete_reader_folds_required')
    facts = inspection.get('output_files')
    need(type(facts) is dict and set(facts) == OUTPUTS, 'exact_reader_fit_outputs_required')
    raw, total = {}, len(inspection_raw)
    for name in sorted(OUTPUTS):
        item = facts[name]
        need(type(item) is dict and set(item) == {'bytes', 'sha256'}
             and type(item['bytes']) is int and 0 < item['bytes'] <= MAXIMUM_FILE_BYTES
             and item['sha256'] == expected_output_sha256[name], 'reader_output_host_pin_mismatch')
        raw[name] = pair.read_pinned(inspection_path.parent / name, expected_output_sha256[name],
                                    pair.MAXIMUM_ARTIFACT_BYTES if name == 'paired-models.json' else MAXIMUM_FILE_BYTES)
        total += len(raw[name])
        need(len(raw[name]) == item['bytes'] and total <= MAXIMUM_TOTAL_BYTES, 'reader_output_bytes_or_total_bound')
    rows = document(raw['ordered-development-rows.json'])
    need(type(rows) is list and 2 <= len(rows) <= 4096, 'original_ordered_rows_required')
    digest = hashlib.sha256(canonical(rows)).hexdigest()
    support, controls = (document(raw[name]) for name in ('support-diagnostics.json', 'constant-controls.json'))
    need(type(support) is dict and support.get('schema_version') == 1
         and support.get('namespace') == 'collection-fit-matrix-support-v2'
         and support.get('source_rows_sha256') == digest and support.get('row_count') == len(rows)
         and support.get('both_classes') is True and support.get('policy_sha256') == METHOD_RECORD_SHA256
         and support.get('eligibility_policy_sha256') == ELIGIBILITY_POLICY_SHA256
         and support.get('c8_role') == 'descriptive_only_no_fit_or_publication_gate', 'reader_support_row_join')
    need(type(controls) is dict and controls.get('schema_version') == 1
         and controls.get('diagnostic') == 'constant_probability_representation_negative_control'
         and controls.get('source_rows_sha256') == digest and controls.get('training_rows') == len(rows)
         and controls.get('analysis_only') is True and controls.get('scientific_result') is False
         and controls.get('policy_performance_estimate') is False
         and controls.get('models_exported') is controls.get('source_rows_modified') is False
         and controls.get('absolute_equivalence_tolerance') == 1e-12, 'mandatory_controls_row_join')
    cases = controls.get('cases')
    need(type(cases) is list and len(cases) == 3, 'all_mandatory_constant_cases_required')
    for case, probability in zip(cases, (.25, .5, .75)):
        need(type(case) is dict and case.get('constant_probability') == probability
             and case.get('training_rows') == len(rows), 'mandatory_constant_case_join')
        value = case.get('max_abs_training_probability_difference')
        need(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
             and case.get('equivalent_within_absolute_tolerance') is (value <= 1e-12)
             and (probability != .5 or value <= 1e-12), 'mandatory_constant_half_refusal')
    need(document(raw['original-dispositions.json']) == inspection.get('original_dispositions'),
         'original_dispositions_reader_join')
    models = pair.load_model_pair(pair_path, expected_sha256=expected_pair_sha256)
    need(all(m.training_sha256 == digest and m.training_rows == len(rows) for m in models.values()),
         'models_original_row_join')
    return models


def configure_model_bound_fleet(solver, *, loader, config, log_root, hard_stop,
                               pair_path=None, expected_pair_sha256=None, inspection_path=None,
                               expected_inspection_sha256=None, expected_output_sha256=None,
                               expected_reader_closure_sha256=None,
                               sdk_verifier=None, clock=time.monotonic):
    """Before factories: bind host-pinned models, configure actual owner, prepare."""
    for module, digest in ((pair, PAIR_LOADER_SHA256), (source_loader, ARM_LOADER_SHA256),
                           (admission, ADMISSION_SHA256)):
        pair.read_pinned(Path(module.__file__), digest, 524288)
    need(type(loader) is source_loader.RuntimeLoader and not loader.prepared
         and type(config) is admission.CommonFleetConfig and type(config.arm) is str
         and config.arm in ('B1', 'A1', 'P') and loader.runtime['arm'] == config.arm,
         'actual_arm_loader_and_configuration_required')
    need(not hasattr(solver, '_arc_paper_common_configuration'), 'fresh_played_copy_required')
    config.validate()
    loader.verify()
    inputs = (pair_path, expected_pair_sha256, inspection_path, expected_inspection_sha256,
              expected_output_sha256, expected_reader_closure_sha256)
    if config.arm == 'B1':
        need(all(value is None for value in inputs), 'b1_has_no_learned_artifacts')
        models = None
    else:
        need(all(value is not None for value in inputs), 'trusted_reader_fit_pins_required')
        need(expected_reader_closure_sha256 == READER_CLOSURE_SHA256, 'selected_reader_closure_required')
        models = reader_fit_models(pair_path=pair_path, expected_pair_sha256=expected_pair_sha256,
            inspection_path=inspection_path, expected_inspection_sha256=expected_inspection_sha256,
            expected_output_sha256=expected_output_sha256)
    loader.verify()
    fleet = admission.configure_common_fleet(solver, config=config, log_root=log_root,
        hard_stop=hard_stop, models=models, sdk_verifier=sdk_verifier, clock=clock)
    preparation = loader.prepare(solver)
    return fleet, dict(source_preparation=preparation, paired_model_sha256=expected_pair_sha256,
        inspection_sha256=expected_inspection_sha256,
        reader_closure_sha256=expected_reader_closure_sha256,
        output_sha256=dict(expected_output_sha256) if expected_output_sha256 is not None else {},
        authority_scope='trusted_host_content_pins_and_operator_custody')


# Public deployment uses the already reviewed fixed pair. Scientific DEV fitting
# and configure_model_bound_fleet above retain their original full-data contract.
PUBLIC_MODEL_PAIR_SHA256 = 'cccc2ffbaaf223ce1a284af1afd2405f58fca4cafeee4b12692678bd33f4b6ed'
PUBLIC_ASSOCIATION_SHA256 = 'cbfda2a62341ff1b9e0038b41a8dbf8f9edfa76140bdbded88c7c0986644fe89'
PUBLIC_TRAINING_ROWS_SHA256 = '1d475d7e6de0a863f64268e7a1baab42cec62390a32d265333fe67ecfce04053'
PUBLIC_REVIEW_SHA256 = 'c5174556685d8fef8baf5efa6d574f3970b3472301ba17f93082ac481e0a4b8f'


def public_pair_models(*, pair_path, expected_pair_sha256, association_path,
                       expected_association_sha256):
    """Load fixed published parameters; no new eligibility test or refitting."""
    need(type(expected_pair_sha256) is str and type(expected_association_sha256) is str
         and expected_pair_sha256 == PUBLIC_MODEL_PAIR_SHA256
         and expected_association_sha256 == PUBLIC_ASSOCIATION_SHA256,
         'exact_published_pair_and_association_required')
    pair.read_pinned(Path(pair.__file__), PAIR_LOADER_SHA256, 524288)
    pair_path, association_path = Path(pair_path), Path(association_path)
    need(pair_path == association_path.parent / 'paired-models.json'
         and association_path.name == 'association.json', 'public_pair_directory_join')
    association = document(pair.read_pinned(association_path, PUBLIC_ASSOCIATION_SHA256, 16384))
    need(type(association) is dict and association.get('schema_version') == 1
         and association.get('namespace') == 'public-fitted-allocation-association-v1'
         and association.get('model') == dict(path='paired-models.json', bytes=6096,
                                             sha256=PUBLIC_MODEL_PAIR_SHA256)
         and association.get('original_reader_closure_sha256') == READER_CLOSURE_SHA256
         and association.get('original_independent_review_sha256') == PUBLIC_REVIEW_SHA256
         and association.get('canonical_training_rows_sha256') == PUBLIC_TRAINING_ROWS_SHA256,
         'published_review_content_association_required')
    models = pair.load_model_pair(pair_path, expected_sha256=PUBLIC_MODEL_PAIR_SHA256)
    need(all(m.training_sha256 == PUBLIC_TRAINING_ROWS_SHA256 and m.training_rows == 16
             for m in models.values()), 'published_pair_training_identity')
    return models


def configure_public_model_bound_fleet(solver, *, loader, config, log_root, hard_stop,
                                      pair_path, expected_pair_sha256, association_path,
                                      expected_association_sha256,
                                      sdk_verifier=None, clock=time.monotonic):
    """Official-only fixed public pair before genuine fleet configuration."""
    for module, digest in ((pair, PAIR_LOADER_SHA256), (source_loader, ARM_LOADER_SHA256),
                           (admission, ADMISSION_SHA256)):
        pair.read_pinned(Path(module.__file__), digest, 524288)
    need(type(loader) is source_loader.RuntimeLoader and not loader.prepared
         and type(config) is admission.CommonFleetConfig and type(config.arm) is str
         and config.arm in ('A1', 'P') and loader.runtime['arm'] == config.arm,
         'actual_public_arm_loader_and_configuration_required')
    need(not hasattr(solver, '_arc_paper_common_configuration'), 'fresh_played_copy_required')
    config.validate()
    loader.verify()
    models = public_pair_models(pair_path=pair_path, expected_pair_sha256=expected_pair_sha256,
        association_path=association_path, expected_association_sha256=expected_association_sha256)
    loader.verify()
    fleet = admission.configure_common_fleet(solver, config=config, log_root=log_root,
        hard_stop=hard_stop, models=models, sdk_verifier=sdk_verifier, clock=clock)
    preparation = loader.prepare(solver)
    return fleet, dict(namespace='public-fitted-allocation-binding-v1',
        source_preparation=preparation, paired_model_sha256=PUBLIC_MODEL_PAIR_SHA256,
        public_association_sha256=PUBLIC_ASSOCIATION_SHA256,
        original_reader_closure_sha256=READER_CLOSURE_SHA256,
        authority_scope='source_pinned_published_parameters_and_trusted_operator_release_association')
