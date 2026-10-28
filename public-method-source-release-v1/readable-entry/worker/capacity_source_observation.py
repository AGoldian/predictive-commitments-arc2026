# SPDX-License-Identifier: MIT-0
"""Bounded observations of one fixed public README; never a source guard.

No alias search, retry, wait, SDK/model import or root/expected-pin override.
The original complete source guard must run independently after observation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

ROOT = Path('/kaggle/input/datasets/dfranzen/taaf-kaggle-source-bundle-copy')
RELATIVE_ROOT = 'datasets/dfranzen/taaf-kaggle-source-bundle-copy'
EXPECTED_SHA = '21abef2e39a887c8ffa024ce87f5cd5614a6dc5e87c9b5edf75db2c9c4295abe'
MAX_READ_BYTES = 4096
MAX_JSON_BYTES = 65536
OUTPUTS = {
    'parent_prelaunch': Path('/kaggle/working/capacity-supervisor/source-preflight-parent.json'),
    'worker_pre_guard': Path('/kaggle/working/capacity-supervisor/source-preflight-worker.json'),
}


def _sha(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _error(exc):
    return {'error_type': type(exc).__name__, 'errno': getattr(exc, 'errno', None)}


def _directory(path):
    try:
        info = path.stat()
        return {'status': 'directory' if stat.S_ISDIR(info.st_mode) else 'not_directory'}
    except FileNotFoundError as exc:
        return dict(status='missing', **_error(exc))
    except OSError as exc:
        return dict(status='stat_error', **_error(exc))


def inspect_readme():
    """A precheck of this instant only; do not cache bytes for the full guard."""
    result = {'relative_public_root': RELATIVE_ROOT,
              'relative_public_file': RELATIVE_ROOT + '/README.dataset.md',
              'root_parent': _directory(ROOT.parent), 'root': _directory(ROOT)}
    path = ROOT / 'README.dataset.md'
    try:
        before = path.stat()
    except FileNotFoundError as exc:
        result['file'] = dict(status='missing', **_error(exc))
        return result
    except OSError as exc:
        result['file'] = dict(status='stat_error', **_error(exc))
        return result
    value = result['file'] = {'status': 'regular_file', 'bytes': before.st_size,
        'stat': {'mode': stat.S_IMODE(before.st_mode), 'device': before.st_dev,
                 'inode': before.st_ino, 'mtime_ns': before.st_mtime_ns}}
    if not stat.S_ISREG(before.st_mode):
        value['status'] = 'not_regular_not_read'
        return result
    if before.st_size > MAX_READ_BYTES:
        value['status'] = 'oversized_not_read'
        return result
    try:
        # O_NONBLOCK avoids blocking on a raced FIFO; regular-file/kernel IO
        # can still stall. The original external supervisor remains the bound.
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or
                    (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                    (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)):
                value['status'] = 'stat_changed_before_read'
                return result
            raw = stream.read(MAX_READ_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > MAX_READ_BYTES:
            value['status'] = 'oversized_read_limited'
        elif ((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) !=
              (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or len(raw) != after.st_size):
            value['status'] = 'stat_changed_during_read'
        else:
            value['sha256'], value['read_bytes'] = hashlib.sha256(raw).hexdigest(), len(raw)
            value['status'] = 'hash_match' if value['sha256'] == EXPECTED_SHA else 'hash_mismatch'
    except OSError as exc:
        value.update(status='read_error', **_error(exc))
    return result


def write_observation(phase, *, manifest_sha256, worker_sha256, supervisor_sha256,
                      helper_sha256, notebook_started_monotonic, whole_deadline_monotonic):
    if phase not in OUTPUTS or not all(_sha(v) for v in
            (manifest_sha256, worker_sha256, supervisor_sha256, helper_sha256)):
        raise ValueError('fixed observation phase and source identity required')
    if (type(notebook_started_monotonic) not in (int, float)
            or type(whole_deadline_monotonic) not in (int, float)
            or whole_deadline_monotonic != notebook_started_monotonic + 31800):
        raise ValueError('unchanged whole envelope required')
    started = time.monotonic()
    if not notebook_started_monotonic <= started < whole_deadline_monotonic:
        raise RuntimeError('source observation outside whole envelope')
    record = {'schema_version': 1, 'phase': phase,
        'prepared_manifest_sha256': manifest_sha256, 'worker_source_sha256': worker_sha256,
        'supervisor_source_sha256': supervisor_sha256, 'helper_source_sha256': helper_sha256,
        'expected_readme_sha256': EXPECTED_SHA, 'max_read_bytes': MAX_READ_BYTES,
        'notebook_started_monotonic': notebook_started_monotonic,
        'whole_deadline_monotonic': whole_deadline_monotonic,
        'started_monotonic': started, 'pid': os.getpid(), 'parent_pid': os.getppid(),
        'isolated_flag': sys.flags.isolated, 'python_version': list(sys.version_info[:3]),
        'python_startup_modules_audited': False, 'recursive_input_listing': False,
        'source_guard_replaced': False, 'observation': inspect_readme(),
        'completed_monotonic': time.monotonic()}
    raw = (json.dumps(record, sort_keys=True, allow_nan=False) + '\n').encode()
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError('source observation output bound exceeded')
    with OUTPUTS[phase].open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    # An observer failure/deadline never bypasses the original source gate.
    if time.monotonic() >= whole_deadline_monotonic:
        raise RuntimeError('source observation exceeded whole envelope')
    return record
