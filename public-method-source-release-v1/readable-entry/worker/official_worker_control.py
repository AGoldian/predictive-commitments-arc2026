# SPDX-License-Identifier: MIT-0
"""Pure trusted configuration boundary; no SDK/model/setup imports or fitting."""
import hashlib
import json
import math
import os
from pathlib import Path
import stat

TRANSPORT_PROFILE = 'bounded-json-byte-derived-nodes-v2'
DEVELOPMENT_PROFILE_SHA256 = '7a0ffd3305f144cc3e17e01aeabe89bc04cfa52b651ce5efe24d1b490db35301'
SAVED_GAMES = ('g50t-5849a774', 'dc22-fdcac232', 'ft09-0d8bbf25', 'ls20-9607627b')
TIMING = dict(whole_seconds=31800, worker_work_seconds=31770, outer_cleanup_seconds=30,
             startup_seconds=3600, gameplay_seconds=27300, worker_readiness_seconds=60,
             drain_seconds=150, teardown_seconds=120)
REQUESTS = dict(http_timeout_seconds=120, main_max_output_tokens=12288,
                summary_max_output_tokens=8192, tail_default_max_output_tokens=12288)
OUTPUTS = frozenset(('paired-models.json', 'ordered-development-rows.json',
    'support-diagnostics.json', 'constant-controls.json', 'original-dispositions.json'))
FIT_FIELDS = frozenset(('pair_path', 'expected_pair_sha256', 'association_path',
    'expected_association_sha256'))
PUBLIC_PAIR_SHA256 = 'cccc2ffbaaf223ce1a284af1afd2405f58fca4cafeee4b12692678bd33f4b6ed'
PUBLIC_ASSOCIATION_SHA256 = 'cbfda2a62341ff1b9e0038b41a8dbf8f9edfa76140bdbded88c7c0986644fe89'
READER = 'b96fefa05b2eba74d761bd79aeb150a7215b9e165570db48cce2c7332b31b3c3'
FIELDS = frozenset(('schema_version', 'namespace', 'arm', 'seed', 'saved_game_ids', 'maximum_capacity',
    'timing', 'requests', 'protocol_sha256', 'package_manifest_sha256', 'worker_sha256',
    'runtime_manifest_sha256', 'runtime_profile_sha256', 'fit', 'aggregate_target_token_bank'))


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def hash_value(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def pinned(path, expected, maximum=262144):
    need(hash_value(expected), 'trusted_hash_required')
    path = Path(path)
    need(path.is_absolute() and path.resolve(strict=True) == path, 'canonical_config_artifact_required')
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'regular_bounded_config_artifact_required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        need(stat.S_ISREG(opened.st_mode) and opened.st_size <= maximum
             and (opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino), 'opened_config_artifact_changed')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    need(identity(opened) == identity(after) and len(raw) == opened.st_size <= maximum
         and digest(raw) == expected, 'config_artifact_changed_or_hash_mismatch')
    return raw


def document(raw):
    def unique(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate_configuration_key')
            result[key] = value
        return result
    value = json.loads(raw.decode(), object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_configuration')))
    # Also refuses overflowing exponent literals parsed as infinity.
    json.dumps(value, allow_nan=False)
    return value


def load_run_config(path, expected_sha256, *, trusted, worker_path,
                    package_manifest_sha256, runtime_manifest_sha256, profile_sha256):
    """Host pins are authority; this is not eligibility or launch permission."""
    trusted, worker_path = Path(trusted), Path(worker_path)
    value = document(pinned(path, expected_sha256))
    need(type(value) is dict and set(value) == FIELDS, 'exact_run_configuration_required')
    need(type(value['schema_version']) is int and value['schema_version'] == 1
         and value['namespace'] == 'official-public-pair-entry-config-v1', 'configuration_schema_required')
    arm = value['arm']
    need(type(arm) is str and arm in ('A1', 'P'), 'explicit_supported_arm_required')
    need(type(value['seed']) is int and value['seed'] == 101
         and value['saved_game_ids'] == list(SAVED_GAMES) and type(value['maximum_capacity']) is int
         and value['maximum_capacity'] == 2, 'fixed_saved_roster_seed_maximum_capacity_required')
    for field, expected in (('timing', TIMING), ('requests', REQUESTS)):
        need(type(value[field]) is dict and set(value[field]) == set(expected)
             and all(type(value[field][k]) is int and value[field][k] == n for k, n in expected.items()),
             'fixed_' + field + '_required')
    need(value['aggregate_target_token_bank'] is None, 'no_aggregate_token_bank_implemented')
    need(hash_value(value['protocol_sha256']) and value['package_manifest_sha256'] == package_manifest_sha256
         and value['runtime_manifest_sha256'] == runtime_manifest_sha256
         and value['runtime_profile_sha256'] == profile_sha256[arm], 'trusted_source_association_required')
    pinned(trusted / 'build-manifest.json', package_manifest_sha256, 4_000_000)
    pinned(worker_path, value['worker_sha256'], 2_000_000)
    runtime_manifest = document(pinned(trusted / 'runtime-manifest.json', runtime_manifest_sha256, 4_000_000))
    need(runtime_manifest.get('transport_profile')==TRANSPORT_PROFILE and runtime_manifest.get('development_profile_sha256')==DEVELOPMENT_PROFILE_SHA256,'runtime_transport_profile_required')
    need(runtime_manifest.get('deployment_profile') == 'official-learned-dynamic-fleet-v1', 'official_source_profile_required')
    runtime = document(pinned(trusted / 'runtime-profiles' / (arm + '.json'), profile_sha256[arm]))
    need(runtime.get('arm') == arm and runtime.get('profile') == 'learned-child-witness-runtime-v1',
         'selected_runtime_profile_mismatch')
    fit = value['fit']
    need(type(fit) is dict and set(fit) == FIT_FIELDS, 'exact_public_pair_arguments_required')
    need(fit['expected_pair_sha256'] == PUBLIC_PAIR_SHA256
         and fit['expected_association_sha256'] == PUBLIC_ASSOCIATION_SHA256,
         'exact_published_pair_pins_required')
    pair, association = Path(fit['pair_path']), Path(fit['association_path'])
    need(pair == trusted.parent / 'fit' / 'paired-models.json'
         and association == trusted.parent / 'fit' / 'association.json',
         'public_deployment_paths_required')
    pinned(pair, PUBLIC_PAIR_SHA256)
    pinned(association, PUBLIC_ASSOCIATION_SHA256, 16384)
    return value, runtime


def validate_envelope(started, deadline, now):
    need(all(type(x) in (int, float) and math.isfinite(x) for x in (started, deadline, now))
         and deadline == started + TIMING['whole_seconds'] and started <= now < started + TIMING['startup_seconds'],
         'invalid_or_expired_learned_envelope')
