# SPDX-License-Identifier: MIT-0
"""Decode a host-pinned pair only; no fitting, eligibility or deployment permit."""
from pathlib import Path
import hashlib
import json
import os
import stat

from arc_paper import allocation
from arc_paper import franzen_fleet_admission as admission

MAXIMUM_ARTIFACT_BYTES = 262144
ALLOCATION_SHA256 = '661f17f8b5636f63af8dcf4fc3bbbfc9aaf37bd4241c2f649d7640d8dc407bd7'
ADMISSION_SHA256 = '9091e8ada88dbe626793ed0a2402ddfa83f773b9bf63d8ade8bc625e56ccd4f4'
FIELDS = frozenset(('names', 'means', 'scales', 'coefficients', 'intercept',
                    'training_sha256', 'training_rows', 'l2', 'iterations', 'learning_rate'))
ARRAYS = ('names', 'means', 'scales', 'coefficients')


class ModelLoadError(ValueError):
    pass


def need(condition, code):
    if not condition:
        raise ModelLoadError(code)


def read_pinned(path, expected_sha256, maximum):
    need(type(expected_sha256) is str and len(expected_sha256) == 64
         and all(c in '0123456789abcdef' for c in expected_sha256), 'expected_sha256_required')
    path = Path(path)
    need(path.is_absolute(), 'absolute_artifact_path_required')
    try:
        need(path.resolve(strict=True) == path, 'symlink_or_noncanonical_path')
        before = path.lstat()
        need(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'regular_bounded_file_required')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            need(stat.S_ISREG(opened.st_mode) and opened.st_size <= maximum
                 and (opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino), 'opened_file_changed')
            raw = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        need(identity(opened) == identity(after) and len(raw) == opened.st_size <= maximum,
             'file_changed_or_bound')
        need(hashlib.sha256(raw).hexdigest() == expected_sha256, 'artifact_sha256_mismatch')
        return raw
    except (OSError, RuntimeError):
        raise ModelLoadError('pinned_file_unavailable') from None


def load_model_pair(path, *, expected_sha256):
    """Return the exact dict-of-immutable-models accepted by FleetAdmission.

    The trusted host must supply the expected hash before its fleet begins and
    separately join reader eligibility, training rows, fit and run association.
    This artifact loader cannot establish any of those scientific facts.
    """
    raw = read_pinned(path, expected_sha256, MAXIMUM_ARTIFACT_BYTES)
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def nonfinite(_):
        raise ModelLoadError('nonfinite_json')
    try:
        document = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError):
        raise ModelLoadError('invalid_json') from None
    need(type(document) is dict and set(document) == {'A1', 'P'}, 'exact_model_pair_required')
    read_pinned(Path(allocation.__file__), ALLOCATION_SHA256, 524288)
    read_pinned(Path(admission.__file__), ADMISSION_SHA256, 524288)
    need(admission.ProgressModel is allocation.ProgressModel, 'actual_model_type_required')
    models = {}
    for arm in ('A1', 'P'):
        item = document[arm]
        need(type(item) is dict and set(item) == FIELDS, 'exact_model_fields_required')
        need(all(type(item[name]) is list for name in ARRAYS), 'json_model_arrays_required')
        values = dict(item)
        for name in ARRAYS:
            values[name] = tuple(values[name])
        models[arm] = allocation.ProgressModel(**values)
    try:
        validated, _ = admission._models(models, 'P')
    except (ValueError, TypeError, OverflowError):
        raise ModelLoadError('invalid_frozen_model_pair') from None
    # _models requires an exact dict on the later admission revalidation.
    # Its immutable dataclass objects are preserved; no parameter is refitted.
    return dict(validated)
