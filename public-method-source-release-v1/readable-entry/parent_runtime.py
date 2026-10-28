# SPDX-License-Identifier: MIT-0
"""One source-pinned learned worker under the actual dedicated supervisor CLI."""
from pathlib import Path
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import subprocess
import sys
import time


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False) + '\n').encode()


def write(path, value):
    raw = encoded(value)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(descriptor, view)
            need(count > 0, 'parent_receipt_short_write')
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return sha(raw)


def identity(pid):
    with Path('/proc/' + str(pid) + '/stat').open('rb') as stream:
        raw = stream.read(4097)
    need(len(raw) <= 4096, 'parent_proc_bound')
    end = raw.rfind(b')')
    fields = raw[end + 2:].split()
    need(end > 0 and len(fields) >= 20 and fields[0] not in (b'Z', b'X'), 'parent_proc_identity')
    return dict(pid=pid, ppid=int(fields[1]), start_time=int(fields[19]))


def load(name, path, expected):
    need(not path.is_symlink() and sha(path.read_bytes()) == expected, 'parent_import_source_pin')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observe_versions():
    versions = {}
    for name in ('numpy', 'requests', 'torch', 'sglang', 'transformers', 'triton', 'flashinfer-python', 'cuda-python'):
        try:
            value = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            value = None
        need(value is None or type(value) is str and len(value) <= 128, 'parent_version_bound')
        versions[name] = value
    return dict(schema_version=1, observed_monotonic=time.monotonic(), python_version=sys.version.split()[0],
        installed_distribution_versions=versions, serving_packages_explicitly_imported=False,
        prior_version_attestation_copied=False, python_startup_modules_audited=False,
        scope='new fixed-whitelist host metadata; actual serving observations belong to worker')


def request_stop(path):
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    except FileExistsError:
        return
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(b'parent absolute boundary or custody failure\n')
        stream.flush()
        os.fsync(stream.fileno())


def run_parent(first, early_ref, plan_path, plan_sha256):
    """No injected launch callbacks: tests replace OS/process infrastructure only."""
    need(type(first) in (int, float), 'original_first_clock_required')
    plan_path = Path(plan_path)
    need(sha(plan_path.read_bytes()) == plan_sha256, 'parent_plan_pin')
    plan = json.loads(plan_path.read_bytes())
    trusted, private = Path(plan['trusted_root']), Path(plan['private_root'])
    early = json.loads(Path(early_ref['path']).read_bytes())
    need(sha(Path(early_ref['path']).read_bytes()) == early_ref['sha256']
         and early['first_code_monotonic'] == first
         and early['observer_identity'] == identity(os.getpid()), 'same_original_notebook_parent_required')
    whole, work = first + 31800., first + 31770.
    need(first <= time.monotonic() < first + 3600., 'parent_startup_expired')
    worker_root = trusted / 'worker'
    config = trusted / 'run-config.json'
    # Verify the delivered worker's exact closed source set before importing even its pure control module.
    closure = worker_root / 'package-checksums.json'
    need(sha(closure.read_bytes()) == plan['worker_closure_sha256'], 'parent_worker_closure_pin')
    inventory = json.loads(closure.read_bytes())['files_sha256']
    paths = list(worker_root.rglob('*'))
    need(not any(path.is_symlink() for path in paths)
         and {str(path.relative_to(worker_root)) for path in paths if path.is_file()}
             == set(inventory) | {'package-checksums.json'}, 'parent_worker_closed_set')
    for name, digest in inventory.items():
        need(sha((worker_root / name).read_bytes()) == digest, 'parent_worker_member_pin')
    need(type(plan['arm']) is str and plan['arm'] in ('A1','P'), 'explicit_parent_arm_required')
    control_name = 'official_worker_control.py'
    control = load('_learned_parent_control', worker_root / control_name, plan['control_sha256'])
    value, _ = control.load_run_config(config, plan['run_config_sha256'], trusted=worker_root,
        worker_path=worker_root / 'worker.py', package_manifest_sha256=plan['package_manifest_sha256'],
        runtime_manifest_sha256=plan['runtime_manifest_sha256'], profile_sha256=plan['runtime_profile_sha256'])
    need(value['arm'] == plan['arm'] and value['protocol_sha256'] == plan['protocol_sha256'], 'parent_config_method_join')
    write(private / 'host-versions-observed.json', observe_versions())
    observer = load('_learned_parent_source_observer', worker_root / 'capacity_source_observation.py', plan['observer_sha256'])
    parent_observation = observer.write_observation('parent_prelaunch', manifest_sha256=plan['package_manifest_sha256'],
        worker_sha256=plan['worker_sha256'], supervisor_sha256=plan['supervisor_sha256'],
        helper_sha256=plan['observer_sha256'], notebook_started_monotonic=first, whole_deadline_monotonic=whole)
    need(parent_observation['phase'] == 'parent_prelaunch' and parent_observation['pid'] == os.getpid()
         and parent_observation['notebook_started_monotonic'] == first
         and parent_observation['whole_deadline_monotonic'] == whole, 'parent_observer_clock_identity_join')
    need(time.monotonic() < first + 3600. and time.monotonic() + 27300 + 150 + 120 <= work,
         'complete_inference_reserves_unavailable')
    stop = worker_root / 'request-stop'
    worker_args = [str(worker_root / 'worker.py'), str(first), str(whole), str(stop),
                   plan['package_manifest_sha256'], str(config), plan['run_config_sha256']]
    need(len(worker_args) == 7, 'worker_script_and_six_positional_arguments_required')
    command = [sys.executable, '-I', '-B', str(worker_root / 'session_supervisor.py'),
        '--work-seconds', str(work - time.monotonic()), '--cleanup-seconds', '30',
        '--whole-deadline-monotonic', str(whole), '--stdout', str(private / 'worker.stdout'),
        '--stderr', str(private / 'worker.stderr'), '--report', str(private / 'supervisor.json'),
        '--stop-file', str(stop), '--max-stream-bytes', '16777216', '--cwd', '/kaggle/working', '--',
        sys.executable, '-I', '-B', *worker_args]
    intent = dict(schema_version=1, namespace='official-learned-parent-launch-v1', arm=value['arm'],
        first_code_monotonic=first, work_deadline_monotonic=work, whole_deadline_monotonic=whole,
        outer_cleanup_seconds=30, first_code_ref=early_ref, parent_plan_sha256=plan_sha256,
        package_manifest_sha256=plan['package_manifest_sha256'], worker_closure_sha256=plan['worker_closure_sha256'],
        worker_sha256=plan['worker_sha256'], supervisor_sha256=plan['supervisor_sha256'],
        run_config_sha256=plan['run_config_sha256'], fit_custody=plan['fit_custody'],
        parent_identity=identity(os.getpid()), scientific_eligibility_evaluated=False,
        pre_code_platform_startup_measured=False)
    write(private / 'launch-intent.json', intent)
    process, supervisor_identity, returncode, wait_returned, errors = None, None, None, False, []
    try:
        with (private / 'supervisor.stdout').open('xb') as out, (private / 'supervisor.stderr').open('xb') as err:
            process = subprocess.Popen(command, stdout=out, stderr=err, stdin=subprocess.DEVNULL, close_fds=True)
            try:
                supervisor_identity = identity(process.pid)
                need(supervisor_identity['ppid'] == os.getpid(), 'supervisor_parent_identity_mismatch')
                write(private / 'launch-owned.json', dict(**intent, supervisor_identity=supervisor_identity,
                      observed_monotonic=time.monotonic()))
            except BaseException:
                request_stop(stop)
                raise
            try:
                returncode = process.wait(timeout=max(.001, work - time.monotonic()))
                wait_returned = True
            except subprocess.TimeoutExpired:
                request_stop(stop)
                returncode = process.wait(timeout=max(.001, whole - time.monotonic()))
                wait_returned = True
    except BaseException as error:
        errors.append(type(error).__name__)
        if process is not None:
            request_stop(stop)
            if not wait_returned and time.monotonic() < whole:
                try:
                    returncode = process.wait(timeout=max(.001, whole - time.monotonic()))
                    wait_returned = True
                except BaseException as secondary:
                    errors.append(type(secondary).__name__)
    report = None
    try:
        raw = (private / 'supervisor.json').read_bytes()
        need(len(raw) <= 262144, 'supervisor_report_bound')
        report = json.loads(raw)
        need(report['effective_whole_deadline_monotonic'] == whole
             and report['effective_work_deadline_monotonic'] <= work
             and report['cleanup_seconds'] == 30, 'supervisor_absolute_clock_join')
        need(supervisor_identity is not None, 'supervisor_identity_required')
        roots = [node for node in report['owned_processes']
                 if node['parent_pid_when_claimed'] == supervisor_identity['pid']]
        need(len(roots) == 1 and all(type(roots[0][k]) is int and roots[0][k] > 0 for k in ('pid', 'start_time'))
             and roots[0]['reaped_by_supervisor'] is True, 'single_reaped_owned_worker_required')
        raw_observation = (private / 'source-preflight-worker.json').read_bytes()
        need(len(raw_observation) <= 65536, 'worker_observer_bound')
        worker_observation = json.loads(raw_observation)
        need(worker_observation['phase'] == 'worker_pre_guard'
             and worker_observation['pid'] == roots[0]['pid']
             and worker_observation['parent_pid'] == supervisor_identity['pid']
             and worker_observation['prepared_manifest_sha256'] == plan['package_manifest_sha256']
             and worker_observation['worker_source_sha256'] == plan['worker_sha256']
             and worker_observation['supervisor_source_sha256'] == plan['supervisor_sha256']
             and worker_observation['helper_source_sha256'] == plan['observer_sha256']
             and worker_observation['notebook_started_monotonic'] == first
             and worker_observation['whole_deadline_monotonic'] == whole,
             'actual_worker_observer_source_clock_custody_join')
        need(returncode == 0 and wait_returned and time.monotonic() <= whole
             and report['status'] == 'worker_completed_and_descendants_cleaned'
             and all(report[k] is True for k in ('completed', 'subreaper_verified', 'pidfd_verified',
                 'launch_gate_verified', 'worker_reaped', 'cleanup_complete', 'pipes_closed',
                 'no_owned_descendants_remaining', 'no_waitable_children_remaining'))
             and report['worker_returncode'] == 0 and report['errors'] == [], 'supervisor_failed_or_unsettled')
    except BaseException as error:
        errors.append(type(error).__name__)
    result = dict(**intent, launched_supervisor_pid=process.pid if process else None,
        observed_supervisor_identity=supervisor_identity, actual_supervisor_returncode=returncode,
        wait_returned=wait_returned, observed_return_monotonic=time.monotonic(),
        source_clock_custody_join_pass=not errors, errors=errors,
        scientific_result=False, target_costs_reconciled=False,
        scope='source/config/first-clock and dedicated-supervisor return joins; separate full run inspection required')
    write(private / 'parent-return.json', result)
    need(not errors, 'learned_parent_failed_or_censored_preserve_all_output')
    return result
