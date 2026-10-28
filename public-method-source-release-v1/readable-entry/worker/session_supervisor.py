# SPDX-License-Identifier: MIT-0
"""Dedicated Linux subreaper for one trusted worker; never a kernel-wide killer.

Invoke in a fresh subprocess. The worker may spawn ordinary descendants/new
sessions. This is a process lifecycle governor, not a sandbox or memory quota.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import json
import math
import os
from pathlib import Path
import platform
import selectors
import signal
import subprocess
import sys
import tempfile
import time


PR_SET_CHILD_SUBREAPER = 36
PR_GET_CHILD_SUBREAPER = 37
PROC_READ_BYTES = 262144
MAX_PROCESSES = 4096
MAX_THREADS_PER_PROCESS = 4096
READ_CHUNK = 16384
POLL_SECONDS = 0.05
ERROR_STAGES = frozenset({"dedicated_process_required", "unsupported_platform",
    "invalid_configuration", "subreaper_set", "subreaper_get", "subreaper_not_verified",
    "pidfd_unavailable", "existing_children", "multiple_supervisor_threads",
    "proc_unavailable", "proc_limit", "process_inventory_limit", "spawn_failed",
    "private_output_setup", "pipe_io", "private_output_io", "signal_failed",
    "launch_gate", "close_failed", "unexpected_failure", "cleanup_deadline", "report_io"})


class SupervisorFailure(RuntimeError):
    def __init__(self, stage, error=None):
        self.stage = stage if stage in ERROR_STAGES else "unexpected_failure"
        self.error = error if type(error) is int else None
        super().__init__(self.stage)

    def record(self):
        result = {"stage": self.stage}
        if self.error is not None:
            result["errno"] = self.error
            result["errno_name"] = errno.errorcode.get(self.error, "UNKNOWN")
        return result


def parse_stat(text):
    """Parse only PID/PPID/state/start time; comm may contain spaces/parentheses."""
    end = text.rfind(")")
    if end < 0:
        raise SupervisorFailure("proc_unavailable")
    try:
        pid = int(text[:text.index("(")].strip())
        fields = text[end + 1:].split()
        return {"pid": pid, "ppid": int(fields[1]), "state": fields[0],
                "start_time": int(fields[19])}
    except (ValueError, IndexError):
        raise SupervisorFailure("proc_unavailable") from None


def _read(path):
    with path.open("rb") as stream:
        data = stream.read(PROC_READ_BYTES + 1)
    if len(data) > PROC_READ_BYTES:
        raise SupervisorFailure("proc_limit")
    return data.decode("ascii", errors="replace")


class LinuxProcesses:
    def __init__(self, proc_root=Path("/proc")):
        self.root = Path(proc_root)

    def identity(self, pid):
        try:
            return parse_stat(_read(self.root / str(pid) / "stat"))
        except (FileNotFoundError, ProcessLookupError):
            return None
        except OSError as exc:
            raise SupervisorFailure("proc_unavailable", exc.errno) from None

    def threads(self, pid):
        try:
            result = []
            with os.scandir(self.root / str(pid) / "task") as entries:
                for entry in entries:
                    if entry.name.isdecimal():
                        result.append(entry.name)
                        if len(result) > MAX_THREADS_PER_PROCESS:
                            raise SupervisorFailure("proc_limit")
            return result
        except (FileNotFoundError, ProcessLookupError):
            return []
        except OSError as exc:
            raise SupervisorFailure("proc_unavailable", exc.errno) from None

    def children(self, pid, start_time):
        before = self.identity(pid)
        if before is None or before["start_time"] != start_time:
            return []
        result = set()
        for tid in self.threads(pid):
            try:
                text = _read(self.root / str(pid) / "task" / tid / "children")
            except (FileNotFoundError, ProcessLookupError):
                continue
            except OSError as exc:
                raise SupervisorFailure("proc_unavailable", exc.errno) from None
            try:
                result.update(int(item) for item in text.split())
            except ValueError:
                raise SupervisorFailure("proc_unavailable") from None
            if len(result) > MAX_PROCESSES:
                raise SupervisorFailure("process_inventory_limit")
        after = self.identity(pid)
        return sorted(result) if after is not None and after["start_time"] == start_time else []


def setup_linux(processes):
    if platform.system() != "Linux":
        raise SupervisorFailure("unsupported_platform")
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise SupervisorFailure("pidfd_unavailable")
    own = processes.identity(os.getpid())
    if own is None:
        raise SupervisorFailure("proc_unavailable")
    if len(processes.threads(own["pid"])) != 1:
        raise SupervisorFailure("multiple_supervisor_threads")
    if processes.children(own["pid"], own["start_time"]):
        raise SupervisorFailure("existing_children")
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.restype = ctypes.c_int
    if prctl(PR_SET_CHILD_SUBREAPER, ctypes.c_ulong(1), ctypes.c_ulong(0),
             ctypes.c_ulong(0), ctypes.c_ulong(0)) != 0:
        raise SupervisorFailure("subreaper_set", ctypes.get_errno())
    verified = ctypes.c_int(0)
    if prctl(PR_GET_CHILD_SUBREAPER, ctypes.byref(verified), ctypes.c_ulong(0),
             ctypes.c_ulong(0), ctypes.c_ulong(0)) != 0:
        raise SupervisorFailure("subreaper_get", ctypes.get_errno())
    if verified.value != 1:
        raise SupervisorFailure("subreaper_not_verified")
    try:
        descriptor = os.pidfd_open(own["pid"], 0)
        try:
            signal.pidfd_send_signal(descriptor, 0, None, 0)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise SupervisorFailure("pidfd_unavailable", exc.errno) from None
    return own


class OwnedTree:
    def __init__(self, processes, own, report):
        self.processes, self.own, self.report = processes, own, report
        self.nodes = {}
        self.discovery_complete = True
        self.no_waitable_children = False

    def claim(self, pid, parent):
        before = self.processes.identity(pid)
        if before is None or before["ppid"] != parent["pid"]:
            return
        parent_now = self.processes.identity(parent["pid"])
        if parent_now is None or parent_now["start_time"] != parent["start_time"]:
            return
        key = (pid, before["start_time"])
        if key in self.nodes:
            return
        if len(self.nodes) >= MAX_PROCESSES:
            raise SupervisorFailure("process_inventory_limit")
        descriptor = None
        try:
            descriptor = os.pidfd_open(pid, 0)
            after = self.processes.identity(pid)
            # Confirm current ancestry after opening the stable process handle.
            if (after is None or after["start_time"] != before["start_time"]
                or after["ppid"] != parent["pid"]
                or pid not in self.processes.children(parent["pid"], parent["start_time"])):
                os.close(descriptor)
                return
            self.nodes[key] = {"pid": pid, "start_time": before["start_time"],
                "parent_pid_when_claimed": parent["pid"], "pidfd": descriptor,
                "stop_sent": False, "kill_sent": False, "reaped_by_supervisor": False,
                "returncode": None}
        except ProcessLookupError:
            if descriptor is not None:
                os.close(descriptor)
        except OSError as exc:
            if descriptor is not None:
                os.close(descriptor)
            raise SupervisorFailure("pidfd_unavailable", exc.errno) from None

    def active(self):
        result = []
        for key, node in self.nodes.items():
            current = self.processes.identity(node["pid"])
            if current is not None and current["start_time"] == key[1]:
                result.append(node)
        return result

    def discover(self, deadline):
        pending = [self.own] + self.active()
        enqueued = {(node["pid"], node["start_time"]) for node in pending}
        visited = set()
        while pending:
            if time.monotonic() >= deadline:
                self.discovery_complete = False
                return
            parent = pending.pop()
            key = (parent["pid"], parent["start_time"])
            if key in visited:
                continue
            visited.add(key)
            for pid in self.processes.children(*key):
                self.claim(pid, parent)
            for child_key, node in self.nodes.items():
                if child_key not in enqueued:
                    pending.append(node)
                    enqueued.add(child_key)
        self.discovery_complete = True

    def send(self, signum):
        field = "stop_sent" if signum == signal.SIGSTOP else "kill_sent"
        # Stable handles remain attributable even if proc visibility is lost;
        # never fall back to a bare PID or process-group signal.
        for node in self.nodes.values():
            if node[field]:
                continue
            try:
                signal.pidfd_send_signal(node["pidfd"], signum, None, 0)
                node[field] = True
            except ProcessLookupError:
                pass
            except OSError as exc:
                raise SupervisorFailure("signal_failed", exc.errno) from None

    def reap(self, worker):
        self.no_waitable_children = False
        for _ in range(MAX_PROCESSES + 1):
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                self.no_waitable_children = True
                return
            except InterruptedError:
                continue
            except OSError as exc:
                raise SupervisorFailure("proc_unavailable", exc.errno) from None
            if pid == 0:
                return
            returncode = os.waitstatus_to_exitcode(status)
            matches = [node for node in self.nodes.values() if node["pid"] == pid
                       and not node["reaped_by_supervisor"]]
            if matches:
                matches[-1].update(reaped_by_supervisor=True, returncode=returncode)
            else:
                self.report["unobserved_adopted_children_reaped"] += 1
            self.report["children_reaped"] += 1
            if worker is not None and pid == worker.pid:
                worker.returncode = returncode
                self.report.update(worker_returncode=returncode, worker_reaped=True)

    def close(self):
        self.report["owned_processes"] = [{key: value for key, value in node.items() if key != "pidfd"}
                                          for node in self.nodes.values()]
        for node in self.nodes.values():
            try:
                os.close(node["pidfd"])
            except OSError as exc:
                self.report["errors"].append(SupervisorFailure("close_failed", exc.errno).record())


def _private_file(path):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(descriptor, "wb", buffering=0)


def _pump(selector, files, report, cap, timeout):
    capped = False
    try:
        ready = selector.select(max(0, timeout))
    except OSError as exc:
        raise SupervisorFailure("pipe_io", exc.errno) from None
    for key, _ in ready:
        name = key.data
        try:
            data = os.read(key.fd, READ_CHUNK)
        except BlockingIOError:
            continue
        except OSError as exc:
            raise SupervisorFailure("pipe_io", exc.errno) from None
        if not data:
            selector.unregister(key.fd)
            continue
        stream = report["streams"][name]
        stream["observed_bytes"] += len(data)
        remaining = max(0, cap - stream["written_bytes"])
        selected = data[:remaining]
        try:
            if selected:
                written = files[name].write(selected)
                stream["written_bytes"] += written
                if written != len(selected):
                    raise SupervisorFailure("private_output_io")
        except OSError as exc:
            raise SupervisorFailure("private_output_io", exc.errno) from None
        if len(data) > remaining:
            stream["truncated"] = True
            capped = True
    return capped


def _save(path, report):
    descriptor, temporary = tempfile.mkstemp(prefix=".supervisor-report-", dir=Path(path).parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def run_supervised(command, *, work_seconds, cleanup_seconds, stdout_path, stderr_path,
                   report_path, stop_file=None, max_stream_bytes=16777216, cwd=None,
                   env=None, dedicated_process=False, whole_deadline_monotonic=None):
    """Only use from a fresh dedicated subprocess, never the notebook kernel.

    env=None inherits without inspecting/logging values. Only the trusted worker
    receives that environment; its generated solver children need their own gate.
    """
    started = time.monotonic()
    report = {"schema_version": 1, "status": "failed_closed", "completed": False,
        "subreaper_verified": False, "pidfd_verified": False, "worker_launched": False,
        "launch_gate_verified": False,
        "worker_reaped": False, "worker_returncode": None, "stop_reason": "setup_failed",
        "work_deadline_reached": False, "worker_requested_stop": False,
        "output_cap_reached": False, "external_signal_received": False,
        "cleanup_complete": False, "cleanup_deadline_reached": False,
        "no_owned_descendants_remaining": False, "no_waitable_children_remaining": False,
        "children_reaped": 0, "unobserved_adopted_children_reaped": 0,
        "owned_processes": [], "errors": [], "pipes_closed": False,
        "streams": {name: {"observed_bytes": 0, "written_bytes": 0, "truncated": False}
                    for name in ("stdout", "stderr")},
        "work_seconds": work_seconds if type(work_seconds) in (int, float) and math.isfinite(work_seconds) else None,
        "cleanup_seconds": cleanup_seconds if type(cleanup_seconds) in (int, float) and math.isfinite(cleanup_seconds) else None,
        "max_stream_bytes": max_stream_bytes if type(max_stream_bytes) is int else None,
        "whole_deadline_monotonic": whole_deadline_monotonic if type(whole_deadline_monotonic) in (int, float) and math.isfinite(whole_deadline_monotonic) else None,
        "environment_values_logged": False, "command_values_logged": False,
        "supervisor_isolation_certified": False,
        "limitations": ["Requires a fresh dedicated supervisor with only this worker tree.",
            "No memory/CPU/device quota or security isolation is supplied by this governor.",
            "Kernel/proc or private-file IO can stall; SIGKILL or platform termination can interrupt cleanup.",
            "Cleanup failure or unreadable process ancestry is an explicit failed result.",
            "An absolute whole deadline includes prior notebook setup; it is not a kernel hard realtime guarantee."]}
    worker = tree = selector = None
    files, old_handlers, requested_signal = {}, {}, []
    gate_read = gate_write = None
    work_deadline = cleanup_deadline = started
    whole_deadline = started
    try:
        if not dedicated_process:
            raise SupervisorFailure("dedicated_process_required")
        if (not command or not all(type(item) is str for item in command)
            or type(work_seconds) not in (int, float) or not math.isfinite(work_seconds) or work_seconds <= 0
            or type(cleanup_seconds) not in (int, float) or not math.isfinite(cleanup_seconds) or cleanup_seconds <= 0
            or (whole_deadline_monotonic is not None and
                (type(whole_deadline_monotonic) not in (int, float) or not math.isfinite(whole_deadline_monotonic)))
            or type(max_stream_bytes) is not int or max_stream_bytes < 1
            or len({Path(path).resolve() for path in (stdout_path, stderr_path, report_path)}) != 3
            or (stop_file is not None and (Path(stop_file).exists() or Path(stop_file).is_symlink()
                or Path(stop_file).resolve() in {Path(path).resolve() for path in
                                               (stdout_path, stderr_path, report_path)}))):
            raise SupervisorFailure("invalid_configuration")
        work_deadline = started + work_seconds
        whole_deadline = work_deadline + cleanup_seconds
        if whole_deadline_monotonic is not None:
            whole_deadline = min(whole_deadline, whole_deadline_monotonic)
            work_deadline = min(work_deadline, whole_deadline - cleanup_seconds)
        report.update(supervisor_entry_monotonic=started, effective_work_deadline_monotonic=work_deadline,
                      effective_whole_deadline_monotonic=whole_deadline)
        if time.monotonic() >= work_deadline:
            report.update(work_deadline_reached=True, stop_reason="work_deadline")
            return report
        processes = LinuxProcesses()
        own = setup_linux(processes)
        report.update(subreaper_verified=True, pidfd_verified=True)
        tree = OwnedTree(processes, own, report)
        for signum in (signal.SIGINT, signal.SIGTERM):
            old_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, lambda number, frame: requested_signal.append(number))
        try:
            files["stdout"] = _private_file(stdout_path)
            files["stderr"] = _private_file(stderr_path)
        except OSError as exc:
            raise SupervisorFailure("private_output_setup", exc.errno) from None
        selector = selectors.DefaultSelector()
        report["status"] = "running"
        _save(report_path, report)
        checkpoint_at = time.monotonic() + 5
        if time.monotonic() >= work_deadline:
            report.update(work_deadline_reached=True, stop_reason="work_deadline")
        else:
            try:
                gate_read, gate_write = os.pipe()
                # Only this trusted stdlib shim runs until stable ownership is
                # established. It execs the original command in the same PID.
                gated_command = [sys.executable, "-I", "-S", str(Path(__file__).resolve()),
                                 "--gated-worker", str(gate_read), "--", *command]
                worker = subprocess.Popen(gated_command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
                    pass_fds=(gate_read,), start_new_session=True, bufsize=0)
                os.close(gate_read)
                gate_read = None
            except OSError as exc:
                raise SupervisorFailure("spawn_failed", exc.errno) from None
            report["worker_launched"] = True
            for name in ("stdout", "stderr"):
                stream = getattr(worker, name)
                os.set_blocking(stream.fileno(), False)
                selector.register(stream.fileno(), selectors.EVENT_READ, name)
            tree.claim(worker.pid, own)
            if not any(node["pid"] == worker.pid for node in tree.nodes.values()):
                raise SupervisorFailure("launch_gate")
            if time.monotonic() >= work_deadline or requested_signal or (stop_file is not None and Path(stop_file).exists()):
                report.update(work_deadline_reached=time.monotonic() >= work_deadline,
                              external_signal_received=bool(requested_signal),
                              worker_requested_stop=stop_file is not None and Path(stop_file).exists())
                report["stop_reason"] = ("external_signal" if requested_signal else
                    "worker_requested_stop" if report["worker_requested_stop"] else "work_deadline")
            else:
                try:
                    if os.write(gate_write, b"1") != 1:
                        raise SupervisorFailure("launch_gate")
                except OSError as exc:
                    raise SupervisorFailure("launch_gate", exc.errno) from None
                report["launch_gate_verified"] = True
            os.close(gate_write)
            gate_write = None
            if report["launch_gate_verified"]:
                report["stop_reason"] = "worker_exit"
            while worker.returncode is None and report["launch_gate_verified"]:
                tree.discover(work_deadline)
                tree.reap(worker)
                if requested_signal:
                    report.update(external_signal_received=True, stop_reason="external_signal")
                    break
                if stop_file is not None and Path(stop_file).exists():
                    report.update(worker_requested_stop=True, stop_reason="worker_requested_stop")
                    break
                remaining = work_deadline - time.monotonic()
                if remaining <= 0:
                    report.update(work_deadline_reached=True, stop_reason="work_deadline")
                    break
                if _pump(selector, files, report, max_stream_bytes, min(POLL_SECONDS, remaining)):
                    report.update(output_cap_reached=True, stop_reason="output_cap")
                    break
                if time.monotonic() >= checkpoint_at:
                    report["elapsed_seconds"] = time.monotonic() - started
                    try:
                        _save(report_path, report)
                    except OSError as exc:
                        raise SupervisorFailure("report_io", exc.errno) from None
                    checkpoint_at = time.monotonic() + 5
    except SupervisorFailure as exc:
        report["errors"].append(exc.record())
        report["stop_reason"] = "supervisor_failure"
    except Exception:
        report["errors"].append({"stage": "unexpected_failure"})
        report["stop_reason"] = "supervisor_failure"
    finally:
        cleanup_started = time.monotonic()
        cleanup_deadline = min(whole_deadline,
                               cleanup_started + cleanup_seconds) if tree is not None else cleanup_started
        report["effective_cleanup_deadline_monotonic"] = cleanup_deadline
        for descriptor in (gate_read, gate_write):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError as exc:
                    report["errors"].append(SupervisorFailure("close_failed", exc.errno).record())
        empty_scans = 0
        if tree is not None:
            # Even if a stalled OS operation consumed the reserve, attempt the
            # already-attributed stable handles once before declaring failure.
            for signum in (signal.SIGSTOP, signal.SIGKILL):
                try:
                    tree.send(signum)
                except SupervisorFailure as exc:
                    report["errors"].append(exc.record())
            while time.monotonic() < cleanup_deadline:
                # A failed rescan must still attempt to stop/kill already-owned
                # stable handles. Each operation gets independent cleanup effort.
                for operation in (lambda: tree.discover(cleanup_deadline),
                    lambda: tree.send(signal.SIGSTOP),
                    lambda: tree.discover(cleanup_deadline),
                    lambda: tree.send(signal.SIGSTOP),
                    lambda: tree.send(signal.SIGKILL), lambda: tree.reap(worker)):
                    try:
                        operation()
                    except SupervisorFailure as exc:
                        if exc.record() not in report["errors"]:
                            report["errors"].append(exc.record())
                try:
                    if selector is not None:
                        if _pump(selector, files, report, max_stream_bytes, 0):
                            report.update(output_cap_reached=True, stop_reason="output_cap")
                    active = tree.active()
                    direct = tree.processes.children(tree.own["pid"], tree.own["start_time"])
                    empty = (not active and not direct and tree.no_waitable_children and tree.discovery_complete
                             and (selector is None or not selector.get_map()))
                    empty_scans = empty_scans + 1 if empty else 0
                    if empty_scans >= 2:
                        report.update(cleanup_complete=True, no_owned_descendants_remaining=True,
                                      no_waitable_children_remaining=True)
                        break
                except SupervisorFailure as exc:
                    if exc.record() not in report["errors"]:
                        report["errors"].append(exc.record())
                time.sleep(min(POLL_SECONDS, max(0, cleanup_deadline - time.monotonic())))
            if not report["cleanup_complete"]:
                report["cleanup_deadline_reached"] = True
                report["errors"].append({"stage": "cleanup_deadline"})
            tree.close()
        elif not report["worker_launched"]:
            report.update(cleanup_complete=True, no_owned_descendants_remaining=True,
                          no_waitable_children_remaining=True)
        closables = []
        if worker is not None:
            for name in ("stdout", "stderr"):
                stream = getattr(worker, name)
                if stream is not None:
                    closables.append(stream)
        if selector is not None:
            closables.append(selector)
        closables.extend(files.values())
        report["pipes_closed"] = True
        for stream in closables:
            try:
                stream.close()
            except OSError as exc:
                report["pipes_closed"] = False
                report["errors"].append(SupervisorFailure("close_failed", exc.errno).record())
        for signum, previous in old_handlers.items():
            signal.signal(signum, previous)
        report.update(completed=True, elapsed_seconds=time.monotonic() - started,
                      cleanup_elapsed_seconds=time.monotonic() - cleanup_started)
        success = (report["subreaper_verified"] and report["launch_gate_verified"] and report["worker_reaped"]
            and report["worker_returncode"] == 0 and report["stop_reason"] == "worker_exit"
            and report["cleanup_complete"] and not report["errors"])
        report["status"] = "worker_completed_and_descendants_cleaned" if success else "stopped_or_failed_closed"
        try:
            _save(report_path, report)
        except (OSError, ValueError, TypeError):
            report["errors"].append({"stage": "report_io"})
            report["status"] = "stopped_or_failed_closed"
    return report


def main():
    if sys.argv[1:2] == ["--gated-worker"]:
        try:
            descriptor = int(sys.argv[2])
            command = sys.argv[4:]
            allowed = os.read(descriptor, 1)
            os.close(descriptor)
            if allowed != b"1" or sys.argv[3:4] != ["--"] or not command:
                raise SystemExit(78)
            os.execvp(command[0], command)
        except (OSError, ValueError, IndexError):
            raise SystemExit(78) from None
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-seconds", type=float, required=True)
    parser.add_argument("--cleanup-seconds", type=float, default=30)
    parser.add_argument("--whole-deadline-monotonic", type=float)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--stderr", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--max-stream-bytes", type=int, default=16777216)
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    result = run_supervised(command, work_seconds=args.work_seconds, cleanup_seconds=args.cleanup_seconds,
        stdout_path=args.stdout, stderr_path=args.stderr, report_path=args.report,
        stop_file=args.stop_file, max_stream_bytes=args.max_stream_bytes, cwd=args.cwd,
        dedicated_process=True, whole_deadline_monotonic=args.whole_deadline_monotonic)
    print(json.dumps({key: result[key] for key in
        ("status", "worker_returncode", "stop_reason", "cleanup_complete", "elapsed_seconds")}, sort_keys=True))
    raise SystemExit(0 if result["status"] == "worker_completed_and_descendants_cleaned" else 2)


if __name__ == "__main__":
    main()
