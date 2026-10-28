# Modified 2026-10-28 by ARC Prize research workspace: byte-derived JSON node ceiling; original JSON/history and native policy retained.
# Modified 2026-10-28 by ARC Prize research workspace: mandatory source-owned child custody hooks; upstream terms retained.
"""Lightweight isolated runner for analyzer Python tool calls."""
from __future__ import annotations

import inspect
from arc_paper.bounded_child_io import (BoundsFailure, BoundedChildIO, DEVELOPMENT_PROFILE, ERROR_STAGES,
    validate_inputs, validate_resource_report, encode_json, close_process)
import hashlib
from arc_paper.receipt_integrity import verify_child_receipts
import json
import logging
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import textwrap
import time
from typing import Any, Callable

from inference.utils import frame_diff as _frame_diff_module
from inference.utils import segmentation as _segmentation
from inference.utils import retained_functions as _retained_functions
from inference.utils.grid_utils import ARC_COLOR_CHARS


_SANDBOX_BOOTSTRAP = textwrap.dedent(
    r"""
    # Modified 2026-10-28 by ARC Prize research workspace: byte-derived JSON node ceiling; original JSON/history and native policy retained.
    import ast
    import builtins
    import contextlib
    import io
    import json
    import os
    import sys
    import traceback

    try:
        import resource
    except ImportError:  # pragma: no cover
        resource = None

    COLOR_CHARS = ""

    __SEGMENTATION_SOURCE__

    __FRAME_DIFF_SOURCE__

    __RETAINED_FUNCTIONS_SOURCE__

    HOST_STDOUT = sys.stdout

    SAFE_MODULES = {
        "bisect",
        "collections",
        "copy",
        # pure-Python sequence comparison, no I/O. Measured across 32
        # transcripts it was imported 9 times and USED none of them - the model
        # reaches for it on "compare two things" and then writes the comparison
        # by hand. Allowing it therefore buys robustness, not capability: a
        # stray import line no longer costs the whole snippet.
        "difflib",
        "fractions",
        "functools",
        "heapq",
        "itertools",
        "json",
        "math",
        "operator",
        "random",
        "re",
        "statistics",
        "string",
    }
    # Original enforcement additions: MIT-0; exact CPU-probed source subset.
    import ctypes

    import errno

    import mmap

    import os

    import platform

    import stat

    POLICY_VERSION = "synthetic-cpu-v1"

    SCMP_ACT_ALLOW = 0x7FFF0000

    SCMP_ACT_ERRNO_EPERM = 0x00050000 | errno.EPERM

    SCMP_ACT_KILL_PROCESS = 0x80000000

    SCMP_CMP_EQ = 4

    SCMP_CMP_MASKED_EQ = 7

    SCMP_FLTATR_ACT_BADARCH = 2

    SCMP_FLTATR_CTL_NNP = 3

    SCMP_FLTATR_CTL_TSYNC = 4

    PR_SET_NO_NEW_PRIVS = 38

    PR_GET_NO_NEW_PRIVS = 39

    TRUSTED_SAFE_MODULES = (
        "bisect", "collections", "copy", "difflib", "fractions", "functools", "heapq",
        "itertools", "json", "math", "operator", "random", "re", "statistics", "string",
    )

    COMPUTATION_SYSCALLS = (
        "brk", "munmap", "mremap", "madvise", "futex", "rt_sigaction",
        "rt_sigprocmask", "rt_sigreturn", "sigaltstack", "clock_gettime",
        "clock_getres", "restart_syscall", "sched_yield", "close", "exit", "exit_group",
    )

    class PolicyFailure(RuntimeError):
        def __init__(self, stage: str, error: int | None = None):
            super().__init__(stage)
            self.stage, self.error = stage, error

        def record(self) -> dict:
            result = {"stage": self.stage}
            if self.error is not None:
                result.update(errno=int(self.error), errno_name=errno.errorcode.get(self.error, "UNKNOWN"))
            return result

    class ArgCompare(ctypes.Structure):
        _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_int),
                    ("datum_a", ctypes.c_uint64), ("datum_b", ctypes.c_uint64)]

    class LibVersion(ctypes.Structure):
        _fields_ = [("major", ctypes.c_uint), ("minor", ctypes.c_uint), ("micro", ctypes.c_uint)]

    def policy_rules() -> list[tuple[str, list[tuple[int, int, int, int]]]]:
        '''Declarative rules; syscall numbers are resolved by the loaded library.'''
        rules = [("read", [(0, SCMP_CMP_EQ, 0, 0)]),
                 ("write", [(0, SCMP_CMP_EQ, 1, 0)]),
                 ("write", [(0, SCMP_CMP_EQ, 2, 0)])]
        rules.extend((name, []) for name in COMPUTATION_SYSCALLS)
        # Anonymous maps only, no executable mappings, and no file descriptor.
        rules.append(("mmap", [(2, SCMP_CMP_MASKED_EQ, mmap.PROT_EXEC, 0),
                               (3, SCMP_CMP_MASKED_EQ, mmap.MAP_ANONYMOUS, mmap.MAP_ANONYMOUS),
                               (4, SCMP_CMP_MASKED_EQ, 0xFFFFFFFF, 0xFFFFFFFF)]))
        rules.append(("mprotect", [(2, SCMP_CMP_MASKED_EQ, mmap.PROT_EXEC, 0)]))
        return rules

    def _configure_library(lib):
        signatures = {
            "seccomp_init": ([ctypes.c_uint32], ctypes.c_void_p),
            "seccomp_release": ([ctypes.c_void_p], None),
            "seccomp_attr_set": ([ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32], ctypes.c_int),
            "seccomp_syscall_resolve_name": ([ctypes.c_char_p], ctypes.c_int),
            "seccomp_rule_add_array": ([ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
                                        ctypes.c_uint, ctypes.POINTER(ArgCompare)], ctypes.c_int),
            "seccomp_load": ([ctypes.c_void_p], ctypes.c_int),
            "seccomp_arch_native": ([], ctypes.c_uint32),
            "seccomp_version": ([], ctypes.POINTER(LibVersion)),
        }
        try:
            for name, (args, returns) in signatures.items():
                function = getattr(lib, name)
                function.argtypes, function.restype = args, returns
        except AttributeError:
            raise PolicyFailure("libseccomp_required_symbol_missing") from None

    def load_libseccomp():
        if platform.system() != "Linux":
            raise PolicyFailure("unsupported_os")
        if ctypes.sizeof(ctypes.c_void_p) != 8 or ctypes.sizeof(ctypes.c_long) != 8:
            raise PolicyFailure("unsupported_32_bit_abi")
        for name in ("libseccomp.so.2", "libseccomp.so"):
            try:
                lib = ctypes.CDLL(name, use_errno=True)
            except OSError:
                continue
            _configure_library(lib)
            return lib, name
        raise PolicyFailure("libseccomp_not_loadable")

    def _checked_return(value: int, stage: str):
        if value != 0:
            raise PolicyFailure(stage, -int(value) if value < 0 else int(value))

    def build_filter(lib) -> tuple[object, dict]:
        context = lib.seccomp_init(SCMP_ACT_ERRNO_EPERM)
        if not context:
            raise PolicyFailure("seccomp_init_failed", ctypes.get_errno() or None)
        details = {"default_action": "ERRNO(EPERM)", "native_arch_token": int(lib.seccomp_arch_native()),
                   "resolved_rules": [], "unsupported_optional_syscalls": [],
                   "tsync_requested": True, "no_new_privs_requested": True}
        try:
            for attribute, value in ((SCMP_FLTATR_ACT_BADARCH, SCMP_ACT_KILL_PROCESS),
                                     (SCMP_FLTATR_CTL_NNP, 1), (SCMP_FLTATR_CTL_TSYNC, 1)):
                _checked_return(lib.seccomp_attr_set(context, attribute, value), "seccomp_attribute_failed")
            for name, comparisons in policy_rules():
                number = int(lib.seccomp_syscall_resolve_name(name.encode("ascii")))
                if number < 0:
                    if name in {"read", "write", "exit", "exit_group", "mmap", "mprotect"}:
                        raise PolicyFailure("required_syscall_unresolved")
                    details["unsupported_optional_syscalls"].append(name)
                    continue
                array = (ArgCompare * len(comparisons))(*(ArgCompare(*item) for item in comparisons))
                _checked_return(lib.seccomp_rule_add_array(
                    context, SCMP_ACT_ALLOW, number, len(comparisons), array if comparisons else None),
                    "seccomp_rule_add_failed")
                details["resolved_rules"].append({"syscall": name, "native_number": number,
                                                   "comparisons": [list(item) for item in comparisons]})
        except BaseException:
            lib.seccomp_release(context)
            raise
        version = lib.seccomp_version()
        details["libseccomp_version"] = (f"{version.contents.major}.{version.contents.minor}."
                                        f"{version.contents.micro}" if version else None)
        return context, details

    def close_inherited_descriptors() -> dict:
        '''Trusted single-thread setup: inspect fd numbers only, never fd targets.'''
        try:
            if len(os.listdir("/proc/self/task")) != 1:
                raise PolicyFailure("preload_created_threads")
            if not all(stat.S_ISFIFO(os.fstat(fd).st_mode) for fd in (0, 1, 2)):
                raise PolicyFailure("stdio_must_be_parent_pipes")
            closed = 0
            for name in os.listdir("/proc/self/fd"):
                fd = int(name)
                if fd > 2:
                    try:
                        os.close(fd)
                        closed += 1
                    except OSError as exc:
                        if exc.errno != errno.EBADF:
                            raise
            # listdir's temporary directory fd is already closed before this loop.
            for name in os.listdir("/proc/self/fd"):
                fd = int(name)
                if fd > 2:
                    try:
                        os.fstat(fd)
                    except OSError as exc:
                        if exc.errno == errno.EBADF:
                            continue
                        raise
                    raise PolicyFailure("descriptor_cleanup_incomplete")
        except OSError as exc:
            raise PolicyFailure("descriptor_setup_failed", exc.errno) from None
        return {"closed_fd_count": closed, "remaining_fd_above_2": 0,
                "stdio_verified_as_pipes": True, "single_thread_verified": True}

    def install_filter_in_child(lib, context) -> dict:
        '''Private entry point called only after trusted preload in --_child.'''
        libc = ctypes.CDLL(None, use_errno=True)
        try:
            prctl = libc.prctl
        except AttributeError:
            raise PolicyFailure("prctl_unavailable") from None
        prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        prctl.restype = ctypes.c_int
        if prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            raise PolicyFailure("no_new_privs_set_failed", ctypes.get_errno())
        if prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1:
            raise PolicyFailure("no_new_privs_verification_failed", ctypes.get_errno() or None)
        _checked_return(lib.seccomp_load(context), "seccomp_load_failed")
        return {"policy_installed": True, "no_new_privs_verified_before_load": True}

    _ARC_POLICY_SOURCE_SHA256 = 'a8412effd96184841e5db36f1eebc2498c897063537c6c2b1a05f51237eb4251'
    _ARC_POLICY_FRAGMENT_SHA256 = '2128ea88d37b9d17e1cf0b25d8ff195c173e05b8faf83ff163bbee984c376b1e'

    def _arc_preload_and_install_policy():
        context, library = None, None
        try:
            if tuple(sorted(SAFE_MODULES)) != TRUSTED_SAFE_MODULES:
                raise PolicyFailure("safe_module_inventory_differs")
            for name in TRUSTED_SAFE_MODULES:
                builtins.__import__(name)
            # Complete trusted codec/JSON/native setup before any retained code.
            json.loads(json.dumps({"public_setup_warmup": True}))
            library, library_name = load_libseccomp()
            context, details = build_filter(library)
            descriptor_setup = close_inherited_descriptors()
            installed = install_filter_in_child(library, context)
            library.seccomp_release(context)
            context = None
            return {"schema_version": 1, "status": "installed_before_untrusted_code",
                    "phase": "before_restore_and_exec", "policy_version": POLICY_VERSION,
                    "policy_source_sha256": _ARC_POLICY_SOURCE_SHA256,
                    "policy_fragment_sha256": _ARC_POLICY_FRAGMENT_SHA256,
                    "trusted_safe_modules_preloaded": list(TRUSTED_SAFE_MODULES),
                    "library": library_name, "policy": details,
                    "descriptor_setup": descriptor_setup, **installed,
                    "isolation_certified": False}
        except BaseException as exc:
            failure = (exc.record() if isinstance(exc, PolicyFailure) else
                       {"stage": "unexpected_trusted_setup_failure", "exception_type": type(exc).__name__})
            if context is not None and library is not None:
                library.seccomp_release(context)
            _send({"type": "confinement_failed", "failure": failure,
                   "policy_source_sha256": _ARC_POLICY_SOURCE_SHA256,
                   "policy_fragment_sha256": _ARC_POLICY_FRAGMENT_SHA256})
            os._exit(72)

    import math

    DEVELOPMENT_PROFILE = {
        "max_tool_seconds": 30, "address_space_bytes": 512 * 1024 * 1024,
        "file_size_bytes": 1_000_000, "open_files": 32, "core_bytes": 0,
        "max_code_bytes": 256 * 1024, "max_retained_bytes": 256 * 1024,
        "max_retained_functions": 64, "max_input_bytes": 4 * 1024 * 1024,
        "max_frame_bytes": 1024 * 1024, "max_stdout_bytes": 4 * 1024 * 1024,
        "max_stderr_bytes": 64 * 1024, "max_display_stdout_bytes": 64 * 1024,
        "max_result_bytes": 256 * 1024, "max_json_depth": 32,
        "max_json_nodes": 2_097_152, "max_messages": 256,
    }

    ERROR_STAGES = frozenset({
        "invalid_timeout", "code_limit", "retained_limit", "json_type", "json_depth",
        "json_nodes", "json_bytes", "json_nonfinite", "invalid_json", "frame_limit",
        "stdout_limit", "stderr_limit", "message_limit", "incomplete_frame", "decode_error",
        "deadline", "pipe_io", "resource_setup", "unsupported_resource_platform",
        "display_stdout_limit", "result_limit", "resource_report", "child_exit",
        "unexpected_host_failure", "cleanup_failed",
    })

    class BoundsFailure(RuntimeError):
        def __init__(self, stage, error=None):
            self.stage = stage if stage in ERROR_STAGES else "unexpected_host_failure"
            self.error = error if type(error) is int else None
            super().__init__(self.stage)

        def record(self):
            record = {"stage": self.stage}
            if self.error is not None:
                record.update(errno=self.error, errno_name=errno.errorcode.get(self.error, "UNKNOWN"))
            return record

    def _walk_json(value, profile, max_bytes):
        '''Count before serialization, visiting only exact builtin JSON types.'''
        pending, nodes, string_bytes = [(value, 0)], 0, 0
        while pending:
            item, depth = pending.pop()
            nodes += 1
            if nodes > profile["max_json_nodes"]:
                raise BoundsFailure("json_nodes")
            if depth > profile["max_json_depth"]:
                raise BoundsFailure("json_depth")
            kind = type(item)
            if kind is str:
                if len(item) > max_bytes:
                    raise BoundsFailure("json_bytes")
                string_bytes += len(item.encode("utf-8"))
                if string_bytes > max_bytes:
                    raise BoundsFailure("json_bytes")
            elif kind is float:
                if not math.isfinite(item):
                    raise BoundsFailure("json_nonfinite")
            elif kind is int:
                if item.bit_length() > 4096:
                    raise BoundsFailure("json_bytes")
            elif item is None or kind is bool:
                pass
            elif kind in (list, tuple):
                if len(item) + nodes + len(pending) > profile["max_json_nodes"]:
                    raise BoundsFailure("json_nodes")
                pending.extend((child, depth + 1) for child in item)
            elif kind is dict:
                if 2 * len(item) + nodes + len(pending) > profile["max_json_nodes"]:
                    raise BoundsFailure("json_nodes")
                for key, child in item.items():
                    if type(key) is not str:
                        raise BoundsFailure("json_type")
                    pending.append((key, depth + 1))
                    pending.append((child, depth + 1))
            else:
                raise BoundsFailure("json_type")

    def encode_json(value, profile, max_bytes):
        _walk_json(value, profile, max_bytes)
        encoded = bytearray()
        try:
            for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":")).iterencode(value):
                raw = chunk.encode("utf-8")
                if len(encoded) + len(raw) + 1 > max_bytes:
                    raise BoundsFailure("json_bytes")
                encoded.extend(raw)
        except (ValueError, OverflowError, RecursionError, UnicodeError) as exc:
            raise BoundsFailure("invalid_json") from exc
        encoded.extend(b"\n")
        return bytes(encoded)

    def _scan_json_structure(raw, profile):
        depth, nodes, quoted, escaped, atom = 0, 0, False, False, False
        for byte in raw:
            if quoted:
                if escaped:
                    escaped = False
                elif byte == 92:
                    escaped = True
                elif byte == 34:
                    quoted = False
                continue
            if byte == 34:
                quoted, atom = True, False
                nodes += 1
            elif byte in (123, 91):
                depth += 1
                nodes += 1
                atom = False
                if depth > profile["max_json_depth"]:
                    raise BoundsFailure("json_depth")
            elif byte in (125, 93):
                depth -= 1
                atom = False
            elif byte in (32, 9, 10, 13, 44, 58):
                atom = False
            elif not atom:
                atom = True
                nodes += 1
            if nodes > profile["max_json_nodes"]:
                raise BoundsFailure("json_nodes")

    def decode_json_line(raw, profile, max_bytes):
        if len(raw) > max_bytes:
            raise BoundsFailure("frame_limit")
        _scan_json_structure(raw, profile)
        try:
            text = raw.decode("utf-8")
        except UnicodeError as exc:
            raise BoundsFailure("decode_error") from exc
        try:
            value = json.loads(text, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, RecursionError) as exc:
            raise BoundsFailure("invalid_json") from exc
        _walk_json(value, profile, max_bytes)
        return value

    def validate_inputs(code, retained, timeout, profile):
        if type(timeout) is not int or not 1 <= timeout <= profile["max_tool_seconds"]:
            raise BoundsFailure("invalid_timeout")
        if type(code) is not str or len(code) > profile["max_code_bytes"] or len(code.encode()) > profile["max_code_bytes"]:
            raise BoundsFailure("code_limit")
        if retained is not None:
            if type(retained) not in (list, tuple) or len(retained) > profile["max_retained_functions"]:
                raise BoundsFailure("retained_limit")
            size = 0
            for source in retained:
                if type(source) is not str or len(source) > profile["max_retained_bytes"]:
                    raise BoundsFailure("retained_limit")
                size += len(source.encode())
                if size > profile["max_retained_bytes"]:
                    raise BoundsFailure("retained_limit")

    def _set_limits(timeout_seconds):
        if platform.system() != "Linux" or resource is None:
            raise BoundsFailure("unsupported_resource_platform")
        targets = {
            "RLIMIT_AS": DEVELOPMENT_PROFILE["address_space_bytes"],
            "RLIMIT_CPU": timeout_seconds + 1,
            "RLIMIT_FSIZE": DEVELOPMENT_PROFILE["file_size_bytes"],
            "RLIMIT_NOFILE": DEVELOPMENT_PROFILE["open_files"],
            "RLIMIT_CORE": DEVELOPMENT_PROFILE["core_bytes"],
        }
        report = {"verified": False, "limits": {}}
        for name, maximum in targets.items():
            identifier = getattr(resource, name, None)
            if identifier is None:
                raise BoundsFailure("resource_setup")
            try:
                inherited_soft, inherited_hard = resource.getrlimit(identifier)
                soft = maximum if inherited_soft == resource.RLIM_INFINITY else min(inherited_soft, maximum)
                hard = maximum if inherited_hard == resource.RLIM_INFINITY else min(inherited_hard, maximum)
                resource.setrlimit(identifier, (soft, hard))
                effective_soft, effective_hard = resource.getrlimit(identifier)
            except (OSError, ValueError) as exc:
                raise BoundsFailure("resource_setup", getattr(exc, "errno", None)) from exc
            if not 0 <= effective_soft <= effective_hard <= maximum:
                raise BoundsFailure("resource_setup")
            report["limits"][name] = {"requested_maximum": maximum,
                "soft": effective_soft, "hard": effective_hard}
        report["verified"] = True
        return report


    def _arc_resource_failed(exc):
        _send({"type": "confinement_failed", "failure": exc.record(),
               "policy_source_sha256": _ARC_POLICY_SOURCE_SHA256,
               "policy_fragment_sha256": _ARC_POLICY_FRAGMENT_SHA256})
        os._exit(73)


    class _ArcBoundedStdout(io.StringIO):
        def __init__(self):
            super().__init__()
            self._arc_bytes = 0

        def write(self, value):
            if len(value) > DEVELOPMENT_PROFILE["max_display_stdout_bytes"]:
                raise BoundsFailure("display_stdout_limit")
            self._arc_bytes += len(value.encode("utf-8"))
            if self._arc_bytes > DEVELOPMENT_PROFILE["max_display_stdout_bytes"]:
                raise BoundsFailure("display_stdout_limit")
            return super().write(value)


    def _arc_bounded_result(value):
        encode_json(value, DEVELOPMENT_PROFILE, DEVELOPMENT_PROFILE["max_result_bytes"])
        return value

    SAFE_BUILTINS = {
        # Exception types. Only four were present, so anything narrower than
        # `except Exception` failed at the except clause and took the snippet
        # with it. These are inert classes and expose nothing; SystemExit and
        # KeyboardInterrupt stay out because the sandbox uses them for its own
        # timeout and shutdown handling.
        "ArithmeticError",
        "AssertionError",
        "AttributeError",
        "EOFError",
        "IndexError",
        "KeyError",
        "LookupError",
        "NameError",
        "NotImplementedError",
        "OverflowError",
        "RecursionError",
        "StopIteration",
        "UnboundLocalError",
        "ZeroDivisionError",
        "abs",
        "all",
        "any",
        "ascii",
        "bin",
        "bool",
        "bytearray",
        "bytes",
        "callable",
        "chr",
        "complex",
        "dict",
        "dir",
        "divmod",
        "enumerate",
        "Exception",
        "filter",
        "float",
        "format",
        "frozenset",
        "getattr",
        "hasattr",
        "hash",
        "hex",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "map",
        "max",
        "min",
        "next",
        "oct",
        "ord",
        "pow",
        "print",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "slice",
        "sorted",
        "str",
        "sum",
        "tuple",
        "TypeError",
        "type",
        "ValueError",
        "RuntimeError",
        "zip",
    }


    def _send(payload):
        HOST_STDOUT.write(encode_json(payload, DEVELOPMENT_PROFILE, DEVELOPMENT_PROFILE["max_frame_bytes"]).decode("utf-8"))
        HOST_STDOUT.flush()


    def _recv():
        raw = sys.stdin.buffer.readline(DEVELOPMENT_PROFILE["max_input_bytes"] + 1)
        if not raw or not raw.endswith(b"\n"):
            raise BoundsFailure("incomplete_frame")
        value = decode_json_line(raw, DEVELOPMENT_PROFILE, DEVELOPMENT_PROFILE["max_input_bytes"])
        if type(value) is not dict:
            raise BoundsFailure("json_type")
        return value


    class FrameView:
        def __init__(self, *, ascii, step, level, shape, grid):
            self.ascii = ascii
            self.step = step
            self.level = level
            self.shape = tuple(shape)
            self._grid = grid
            self._segmentation = None

        @property
        def segmentation(self):
            if self._segmentation is None:
                self._segmentation = segment_layer(self._grid, COLOR_CHARS)
            return self._segmentation

        def __str__(self):
            rows, cols = self.shape
            return f"AsciiFrameView(level={self.level}, step={self.step}, shape={rows}x{cols})"

        __repr__ = __str__


    class HistoryEntryView:
        def __init__(self, *, action, frame, result=None):
            self.action = action
            self.frame = frame
            self.result = dict(result) if isinstance(result, dict) else {}

        def __str__(self):
            return f"AsciiHistoryEntryView(action={self.action!r}, frame={self.frame})"

        __repr__ = __str__


    class TransitionView:
        def __init__(self, *, action, before_frame, after_frame, result):
            self.action = action
            self.before_frame = before_frame
            self.after_frame = after_frame
            self.frame = after_frame
            self.result = dict(result) if isinstance(result, dict) else {}

        def __str__(self):
            return (
                "ActionTransitionView("
                f"action={self.action!r}, "
                f"before_frame={self.before_frame}, "
                f"after_frame={self.after_frame})"
            )

        __repr__ = __str__


    def _frame_from_payload(payload):
        if not isinstance(payload, dict):
            return None
        return FrameView(
            ascii=str(payload.get("ascii", "")),
            step=int(payload.get("step", 0)),
            level=int(payload.get("level", 0)),
            shape=payload.get("shape", [0, 0]),
            grid=payload.get("grid", []),
        )


    def _history_from_payload(payload):
        items = []
        for entry in payload or []:
            if not isinstance(entry, dict):
                continue
            items.append(
                HistoryEntryView(
                    action=str(entry.get("action", "")),
                    frame=_frame_from_payload(entry.get("frame")),
                    result=entry.get("result"),
                )
            )
        return items


    def _transitions_from_history(history):
        transitions = []
        for index, entry in enumerate(history):
            action = str(getattr(entry, "action", "") or "").strip()
            if not action:
                continue
            before_frame = history[index - 1].frame if index > 0 else None
            transitions.append(
                TransitionView(
                    action=action,
                    before_frame=before_frame,
                    after_frame=entry.frame,
                    result=entry.result,
                )
            )
        return transitions


    def _json_safe(value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item) for item in value]
        return str(value)


    def _sanitize_exception(exc):
        extracted = traceback.extract_tb(exc.__traceback__)
        user_frames = [frame for frame in extracted if frame.filename == "<python_tool>"]
        lines = ["Traceback (most recent call last):"]
        for frame in user_frames or extracted[-1:]:
            lines.append(f'  File "<python_tool>", line {frame.lineno}, in {frame.name}')
        lines.append(f"{exc.__class__.__name__}: {exc}")
        return "\n".join(lines)


    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = str(name or "").split(".", 1)[0]
        if root not in SAFE_MODULES:
            raise ImportError(f"Module '{name}' is not allowed in the sandbox.")
        return builtins.__import__(name, globals, locals, fromlist, level)





    def _normalize_actions(actions):
        if isinstance(actions, str):
            items = [actions]
        elif isinstance(actions, dict):
            items = [actions]
        elif isinstance(actions, (list, tuple)):
            items = list(actions)
        else:
            raise TypeError(
                "action(actions) expects a string, an action object, or a list of action strings/objects."
            )
        if not items:
            raise ValueError("action(actions) requires at least one action.")

        normalized = []
        for index, item in enumerate(items, start=1):
            if isinstance(item, str):
                action_name = item.strip()
                if not action_name:
                    raise ValueError(f"Action {index} is empty.")
                normalized.append({"action": action_name})
                continue
            if isinstance(item, dict):
                action_name = str(item.get("action", "")).strip()
                if not action_name:
                    raise ValueError(f"Action {index} is missing an `action` field.")
                entry = {"action": action_name}
                if action_name.upper() == "MOUSE" and ("x" in item or "y" in item):
                    raise ValueError(
                        f"Action {index} uses legacy MOUSE x/y fields; use row and col."
                    )
                if "row" in item:
                    entry["row"] = item.get("row")
                if "col" in item:
                    entry["col"] = item.get("col")
                normalized.append(entry)
                continue
            raise TypeError(f"Action {index} must be a string or a dict.")
        return normalized


    def main():
        try:
            _set_limits(DEVELOPMENT_PROFILE["max_tool_seconds"])
            initial = _recv()
            validate_inputs(initial.get("code"), initial.get("kept_functions"),
                            initial.get("timeout_seconds"), DEVELOPMENT_PROFILE)
        except BoundsFailure as exc:
            _arc_resource_failed(exc)
        global COLOR_CHARS
        COLOR_CHARS = str(initial.get("color_chars") or "")
        timeout_seconds = max(1, int(initial.get("timeout_seconds", 30)))
        sandbox_cwd = str(initial.get("sandbox_cwd", "")).strip()
        if sandbox_cwd:
            os.chdir(sandbox_cwd)
        try:
            _arc_resource_report = _set_limits(timeout_seconds)
        except BoundsFailure as exc:
            _arc_resource_failed(exc)
        _arc_confinement = _arc_preload_and_install_policy()
        _arc_confinement["resource_limits"] = _arc_resource_report
        _send({"type": "confinement_ready", "confinement": _arc_confinement})

        action_results = []
        stdout = _ArcBoundedStdout()
        runtime_globals = {
            "__builtins__": {
                name: getattr(builtins, name)
                for name in SAFE_BUILTINS
            },
            "result": None,
        }
        runtime_globals["__builtins__"]["__import__"] = _safe_import
        _animation_views = []

        def frame_diff(before=None, after=None):
            # Object-level diff between two frames. Defaults: previous_frame -> current_frame.
            # Returns only what changed; unchanged objects are omitted.
            if before is None:
                before = runtime_globals.get("previous_frame")
            if after is None:
                after = runtime_globals.get("current_frame")
            if before is None or after is None:
                return {"error": "need two frames (no previous_frame available?)"}
            if before.shape != after.shape:
                return {"changed_cell_count": -1, "note": "frame shapes differ; full redraw",
                        "before_shape": before.shape, "after_shape": after.shape}
            return compute_frame_diff(
                before._grid,
                after._grid,
                before.segmentation.get("nodes", []),
                after.segmentation.get("nodes", []),
            )

        def _refresh_state(state_payload):
            current_frame = _frame_from_payload(state_payload.get("current_frame"))
            history = _history_from_payload(state_payload.get("history"))
            last_action_call_result = state_payload.get("last_action_call_result")
            action_result = (
                dict(last_action_call_result) if isinstance(last_action_call_result, dict) else {}
            )
            # action_echo is printed by action(), then removed from its return value.
            # Keep the exposed call result identical across subsequent inspections.
            action_result.pop("action_echo", None)
            transitions = _transitions_from_history(history)
            last_transition = transitions[-1] if transitions else None

            runtime_globals["current_frame"] = current_frame
            runtime_globals["latest_frame"] = current_frame
            runtime_globals["history"] = history
            runtime_globals["transitions"] = transitions
            runtime_globals["last_transition"] = last_transition
            runtime_globals["previous_frame"] = (
                last_transition.before_frame if last_transition is not None else None
            )
            runtime_globals["last_action_frame"] = (
                last_transition.after_frame if last_transition is not None else None
            )
            runtime_globals["last_action"] = last_transition.action if last_transition is not None else None
            runtime_globals["frame_diff"] = frame_diff
            runtime_globals["valid_actions"] = [str(item) for item in state_payload.get("valid_actions", [])]
            runtime_globals["death_ledger"] = state_payload.get("death_ledger") or {"attempts": []}
            runtime_globals["last_action_call_result"] = action_result

        # Both refusals derive from BaseException, not Exception, so a
        # defensive `except Exception:` around action(...) - which models write
        # routinely - cannot swallow them. A refusal means the action did not
        # run at all, so the snippet's assumed state is already wrong and every
        # line after it rests on a false premise. One run treated 1500
        # consecutive refusals as proof that every cell on the board was inert.
        # StaleStateActionError below is deliberately catchable: it reports a
        # belief that MAY be stale rather than a verdict on the action.
        class KnownNoOpActionError(BaseException):
            pass  # raised INSTEAD of executing an action already proven inert here

        class KnownDeathActionError(BaseException):
            pass  # raised INSTEAD of executing an action that ended a prior attempt

        # Raised INSTEAD of executing an action this snippet has already run
        # from this exact board. Buggy loop code can spend a whole life bar
        # getting nowhere - a cursor that wraps turns RIGHT into a short cycle,
        # a mistaken `while pos < j: LEFT` walks away from its target forever -
        # and the terminal latch only stops that once the game actually ends,
        # measured at 20 to 30 wasted actions. BaseException like the two above:
        # the shape that produces these loops is `try: action(...) except
        # Exception:` inside a while, which would otherwise swallow the verdict
        # and keep going. No override slot: the snippet is not reading the
        # refusal, its code is running, and writing a new snippet IS the
        # response - the map is rebuilt per execution.
        class RepeatedActionInStateError(BaseException):
            pass

        # Raised when a PREVIOUS action in this snippet changed nothing, and the
        # snippet then tries to act again. Deliberately a plain Exception, not
        # BaseException: unlike the two refusals above this is a warning about
        # the snippet's beliefs rather than a verdict on the action, and a model
        # that has re-read current_frame may legitimately want to proceed.
        class StaleStateActionError(Exception):
            pass

        runtime_globals["KnownNoOpActionError"] = KnownNoOpActionError
        runtime_globals["KnownDeathActionError"] = KnownDeathActionError
        runtime_globals["StaleStateActionError"] = StaleStateActionError
        runtime_globals["RepeatedActionInStateError"] = RepeatedActionInStateError
        # armed when an action changes nothing; scoped to THIS snippet because
        # the closure is rebuilt per execution, so no reset path can be missed
        _stale_state: list[str] = []

        # Raised when a snippet tries to act after the attempt or level ended.
        # Derives from BaseException, not Exception, so a defensive
        # `try: action(...) except Exception:` around the call - which models
        # write routinely - cannot swallow it. Continuing to execute a path
        # computed against a board that no longer exists is never correct.
        class TerminalStateActionError(BaseException):
            pass

        runtime_globals["TerminalStateActionError"] = TerminalStateActionError
        # latched when an action reports a terminal result; scoped to THIS
        # snippet because these closures are rebuilt for every execution, so
        # no reset path can be missed and the next snippet always starts clear
        _terminal_state = []

        _TERMINAL_DETAIL = {
            "game_over": (
                "the previous action reported game_over. The level has been reset to its "
                "start, so the board you planned against is gone and this action was not "
                "executed. The next turn begins from the new state."
            ),
            "level_completed": (
                "the previous action reported level_completed. A new level has been loaded, "
                "so the board you planned against is gone and this action was not executed. "
                "The next turn begins from the new state."
            ),
            "run_complete": (
                "the previous action reported run_complete. The run is finished and this "
                "action was not executed."
            ),
        }

        def action(actions, *, prediction=None):
            if _terminal_state:
                raise TerminalStateActionError(_TERMINAL_DETAIL[_terminal_state[0]])
            normalized_actions = _normalize_actions(actions)
            if len(normalized_actions) != 1:
                raise ValueError('Prediction pilot accepts exactly one action per call.')
            _send({
                "type": "action",
                "actions": normalized_actions,
                "prediction": prediction,
                # the solver decides precedence: a known death or a known no-op
                # is a sharper message than "your state may be stale", and it
                # carries a concrete override
                "stale_after": _stale_state[0] if _stale_state else None,
            })
            reply = _recv()
            if reply.get("type") == "action_error":
                raise RuntimeError(str(reply.get("error", "action failed")))
            if reply.get("type") != "action_result":
                raise RuntimeError("Invalid action response from sandbox host.")
            action_result = reply.get("action_result") or {}
            action_results.append(action_result)
            # Cached animations describe the previous action. Invalidate the
            # existing views so aliases also refresh, even if a guard raises.
            for view in _animation_views:
                view.invalidate()
            _refresh_state(reply.get("state") or {})
            if action_result.get("stop_reason") == "reset_not_first":
                raise RuntimeError(str(action_result.get("stop_detail")))
            if action_result.get("stop_reason") == "stale_state":
                raise StaleStateActionError(
                    str(action_result.get("stop_detail") or "stale state")
                )
            if action_result.get("stop_reason") == "known_death":
                raise KnownDeathActionError(
                    str(action_result.get("stop_detail") or "known fatal action was not executed.")
                )
            if action_result.get("stop_reason") == "repeated_action_in_state":
                raise RepeatedActionInStateError(
                    str(action_result.get("stop_detail") or "")
                    or "this action was already run from this board in this snippet"
                )
            if action_result.get("stop_reason") == "known_noop":
                # nothing executed and no action was spent; halt the snippet so
                # the model re-plans instead of continuing on a false premise
                raise KnownNoOpActionError(
                    str(action_result.get("stop_detail") or "known no-op action was not executed.")
                )
            for _flag in ("run_complete", "done", "level_completed", "game_over"):
                if action_result.get(_flag):
                    # `done` means the run was won; report it as run_complete
                    _terminal_state.append(
                        "run_complete" if _flag == "done" else _flag
                    )
                    break
            _echo = action_result.pop("action_echo", None)
            if _echo:
                # into the snippet's own stdout, so a loop can see what its
                # call did without waiting for the next turn's opener
                print(_echo)
            gameplay_changed = action_result.get("gameplay_changed")
            if gameplay_changed is True:
                # a real change means the snippet's beliefs are current again
                del _stale_state[:]
            if gameplay_changed is False and action_result.get("executed"):
                _executed = action_result.get("executed_actions")
                _name = (
                    _executed[-1]
                    if isinstance(_executed, list) and _executed
                    else action_result.get("action_display")
                    or action_result.get("action_name")
                    or "?"
                )
                # Arm rather than raise. The action executed and changed
                # nothing, which is often exactly what the snippet went looking
                # for - it printed the board before, and wants to print it
                # after. Killing it here throws away the second half of the
                # measurement AND the batch stop's own trace, which is computed
                # and then discarded. So let the snippet finish observing, and
                # stop it only if it tries to ACT on the stale belief.
                if not _stale_state:
                    _stale_state.append(str(_name))
            return action_result

        def _animation_fetch(kind):
            _send({"type": "animation", "request": {"kind": kind}})
            reply = _recv()
            if reply.get("type") == "animation_error":
                raise RuntimeError(str(reply.get("error", "animation failed")))
            if reply.get("type") != "animation_result":
                raise RuntimeError("Invalid animation response from sandbox host.")
            payload = reply.get("animation")
            if kind != "frames":
                return payload or {}
            return [
                FrameView(
                    ascii=item.get("ascii", ""),
                    step=item.get("step", 0),
                    level=item.get("level", 0),
                    shape=item.get("shape", (0, 0)),
                    grid=item.get("grid", ()),
                )
                for item in (payload or [])
            ]

        runtime_globals["action"] = action
        if initial.get("animation_enabled"):
            # Globals rather than attributes on last_transition: after a death
            # the harness appends a RESET entry, so last_transition is the
            # reset and not the action that animated. The record is simply
            # "the last executed action that animated", and naming it that way
            # removes the mismatch. Empty when the last executed action
            # returned a single frame.
            class _LazyAnimation:
                def __init__(self, kind, empty):
                    self._kind = kind
                    self._empty = empty
                    self._value = None

                def _get(self):
                    if self._value is None:
                        self._value = _animation_fetch(self._kind) or self._empty
                    return self._value

                def invalidate(self):
                    self._value = None

                def __len__(self):
                    return len(self._get())

                def __iter__(self):
                    return iter(self._get())

                def __getitem__(self, key):
                    return self._get()[key]

                def __bool__(self):
                    return bool(self._get())

                def __contains__(self, key):
                    return key in self._get()

                def keys(self):
                    return self._get().keys()

                def get(self, key, default=None):
                    return self._get().get(key, default)

                def __repr__(self):
                    return repr(self._get())

            runtime_globals["last_animation_frames"] = _LazyAnimation("frames", [])
            runtime_globals["last_animation_timeline"] = _LazyAnimation("timeline", {})
            _animation_views.extend((runtime_globals["last_animation_frames"],
                                     runtime_globals["last_animation_timeline"]))

        _refresh_state(initial.get("state") or {})

        _persistence_enabled = bool(initial.get("persistence_enabled"))
        _retention_options = {
            "retain_imports": bool(initial.get("retain_imports")),
            "repair_hints": bool(initial.get("repair_hints")),
        }
        _kept_pool = {}
        _retention_rejected = []
        _available_names = set(runtime_globals) | set(runtime_globals["__builtins__"])
        if _persistence_enabled:
            _before_restore = dict(runtime_globals)
            try:
                _kept_pool, _retention_rejected = restore_functions(
                    initial.get("kept_functions") or [], runtime_globals, _available_names,
                    **_retention_options)
            except Exception:
                # Optional cache maintenance must never prevent this snippet running.
                runtime_globals.clear()
                runtime_globals.update(_before_restore)
                _kept_pool = {}
                _retention_rejected = [{"name": "all", "reason": "restoration failed; redefine needed functions"}]

        def _collect_retention_payload():
            if not _persistence_enabled:
                return {}
            try:
                kept, rejected = collect_functions(
                    _code_text, _kept_pool, runtime_globals, _available_names,
                    **_retention_options)
                return {
                    "keepable_functions": [{"name": n, "source": src} for n, src in kept.items()],
                    "retention_rejected": _retention_rejected + rejected,
                }
            except Exception:
                # Bookkeeping failures may drop helpers, but must never replace
                # the snippet's original error/output or replay its actions.
                return {"keepable_functions": [], "retention_rejected": [
                    {"name": "all", "reason": "retention failed; redefine needed functions"}]}

        try:
            _code_text = str(initial.get("code", ""))
            _tree = ast.parse(_code_text, "<python_tool>")
            _last_expr = None
            if _tree.body and isinstance(_tree.body[-1], ast.Expr):
                _last_expr = ast.Expression(_tree.body[-1].value)
                ast.copy_location(_last_expr, _tree.body[-1])
                _tree.body = _tree.body[:-1]
            with contextlib.redirect_stdout(stdout):
                if _tree.body:
                    exec(compile(_tree, "<python_tool>", "exec"), runtime_globals, runtime_globals)
                if _last_expr is not None:
                    _value = eval(compile(_last_expr, "<python_tool>", "eval"), runtime_globals, runtime_globals)
                    if _value is not None:
                        print(repr(_value))
                        if runtime_globals.get("result") is None:
                            runtime_globals["result"] = _value
            _send(
                {
                    "type": "final",
                    **_collect_retention_payload(),
                    "stdout": stdout.getvalue(),
                    "result": _arc_bounded_result(runtime_globals.get("result")),
                    "action_results": _json_safe(action_results),
                }
            )
        except (
            KnownNoOpActionError,
            RepeatedActionInStateError,
            KnownDeathActionError,
            TerminalStateActionError,
            Exception,
        ) as exc:
            # The three refusals derive from BaseException so a model's own
            # `except Exception:` cannot swallow them - but THIS handler is the
            # same construct, so without naming them explicitly they escaped it
            # too, killed the child process, and the host reported a bare
            # "Sandbox process exited unexpectedly". The refusal messages - the
            # action name, that nothing was spent, how to override - were built
            # and then never delivered. They stop the snippet either way; the
            # point is that the model is told why.
            _send(
                {
                    "type": "error",
                    **_collect_retention_payload(),
                    "error": _sanitize_exception(exc),
                    "stdout": stdout.getvalue(),
                    "action_results": _json_safe(action_results),
                }
            )


    if __name__ == "__main__":
        main()
    """
).replace("__RETAINED_FUNCTIONS_SOURCE__\n", inspect.getsource(_retained_functions)).replace(
    "__SEGMENTATION_SOURCE__\n", inspect.getsource(_segmentation)
).replace(
    "__FRAME_DIFF_SOURCE__\n", inspect.getsource(_frame_diff_module)
)


_ARC_POLICY_SOURCE_SHA256 = 'a8412effd96184841e5db36f1eebc2498c897063537c6c2b1a05f51237eb4251'
_ARC_POLICY_FRAGMENT_SHA256 = '2128ea88d37b9d17e1cf0b25d8ff195c173e05b8faf83ff163bbee984c376b1e'
_ARC_CHILD_BOOTSTRAP_SHA256 = '27de5d1b31740b087ebdd8ea3ddeb978f5badeafda52dd71c344954a5b6edd84'

def _arc_confinement_ready_record(message, timeout_seconds):
    record = message.get("confinement")
    if not isinstance(record, dict):
        return None
    if not validate_resource_report(record.get("resource_limits"), timeout_seconds, DEVELOPMENT_PROFILE):
        return None
    descriptors = record.get("descriptor_setup")
    policy = record.get("policy")
    if not isinstance(descriptors, dict) or not isinstance(policy, dict):
        return None
    if not (record.get("status") == "installed_before_untrusted_code"
            and record.get("phase") == "before_restore_and_exec"
            and record.get("policy_source_sha256") == _ARC_POLICY_SOURCE_SHA256
            and record.get("policy_fragment_sha256") == _ARC_POLICY_FRAGMENT_SHA256
            and record.get("policy_version") == "synthetic-cpu-v1"
            and policy.get("default_action") == "ERRNO(EPERM)"
            and policy.get("tsync_requested") is True
            and policy.get("no_new_privs_requested") is True
            and record.get("policy_installed") is True
            and record.get("no_new_privs_verified_before_load") is True
            and record.get("isolation_certified") is False
            and type(descriptors.get("remaining_fd_above_2")) is int
            and descriptors.get("remaining_fd_above_2") == 0
            and descriptors.get("stdio_verified_as_pipes") is True
            and descriptors.get("single_thread_verified") is True):
        return None
    # The first pipe message is emitted by trusted bootstrap code before any
    # retained-function restoration. It is a setup report, not a certificate.
    return {"resource_limits": record["resource_limits"], "policy_version": record["policy_version"],
            "phase": record["phase"], "library": record.get("library"),
            "libseccomp_version": policy.get("libseccomp_version"),
            "native_arch_token": policy.get("native_arch_token"),
            "descriptor_setup": {key: descriptors.get(key) for key in
                ("closed_fd_count", "remaining_fd_above_2", "stdio_verified_as_pipes", "single_thread_verified")},
            "no_new_privs_verified_before_load": True,
            "trusted_safe_modules_preloaded": list(record.get("trusted_safe_modules_preloaded") or [])}


log = logging.getLogger(__name__)


def _sanitize_host_error_text(text: str) -> str:
    """What the MODEL is told when the sandbox process dies.

    Deliberately fixed: the child's traceback carries host paths and internals
    that have no business in the model's context. But the text was previously
    read and thrown away entirely, so a crash left no trace anywhere - the one
    thing that knows what went wrong said nothing. It now goes to the harness
    log instead, where it is useful and nobody is prompted by it.
    """
    detail = str(text or "").strip()
    if detail:
        log.warning(
            "sandbox process died; stderr follows:\n%s",
            detail[-4000:],
        )
    return "Sandbox process exited unexpectedly."


def _sandbox_env() -> dict[str, str]:
    # Fixed public values only; do not read or copy parent environment entries.
    # -I ignores Python environment controls, including PYTHONHASHSEED. Keep
    # the baseline isolation flags and do not claim effective hash determinism.
    return {
        "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
        "HOME": "/tmp", "TMPDIR": "/tmp", "PATH": "/usr/bin:/bin",
        "LC_ALL": "C.UTF-8", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
    }


def _send_json_line(handle: Any, payload: dict[str, Any]) -> None:
    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    handle.flush()


def _kill_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        try:
            process.kill()
        except OSError:
            pass


def _wait_for_process_exit(process: subprocess.Popen[str], *, timeout: float = 1.0) -> None:
    try:
        process.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        _kill_process_group(process)
    except OSError:
        return

    try:
        process.wait(timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        pass


from arc_paper.inference_child_witness_v1 import verify_child_observer, ChildReceiptError
from arc_paper.franzen_host_accounting_v2 import HostStopped

def run_sandboxed_python(
    *,
    code: str,
    timeout_seconds: int,
    initial_state: dict[str, Any],
    action_handler: Callable[..., dict[str, Any]],
    animation_handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    kept_functions: list[str] | None = None,
    retain_imports: bool = False,
    repair_hints: bool = False,
    receipt_observer=None,
) -> dict[str, Any]:
    receipt_observer = verify_child_observer(receipt_observer)
    process = channel = None
    pending_results, host_action_results = [], []
    resource_failure = None
    started = time.monotonic()
    deadline = started + (timeout_seconds if type(timeout_seconds) is int and 1 <= timeout_seconds <= DEVELOPMENT_PROFILE["max_tool_seconds"] else 0)
    try:
        host_confinement_record = {
            "schema_version": 1, "required": True, "gate_passed": False,
            "status": "awaiting_ready_report", "isolation_certified": False,
            "policy_source_sha256": _ARC_POLICY_SOURCE_SHA256,
            "policy_fragment_sha256": _ARC_POLICY_FRAGMENT_SHA256,
            "child_environment": "fixed_public_whitelist",
            "python_hash_seed_control_effective": False,
        }

        def _arc_confinement_result(payload):
            record = dict(host_confinement_record)
            if record["status"] == "awaiting_ready_report":
                record["status"] = "missing_ready_report"
            record["tool_error"] = bool(payload.get("error"))
            record["resource_bounds"] = {
                "profile": dict(DEVELOPMENT_PROFILE), "requires_external_supervisor": True,
                "synchronous_callback_deadline_enforced": False,
                "setup_verified": bool(record.get("trusted_setup_report", {}).get("resource_limits", {}).get("verified")),
                "failure": resource_failure or (record.get("failure") if record.get("failure", {}).get("stage") in ERROR_STAGES else None),
            }
            result = {**payload, "confinement": record}
            pending_results.append(result)
            return result

        receipt_observer.observe("sandbox_entered", timeout_seconds=timeout_seconds,
            profile_sha256=hashlib.sha256(json.dumps(DEVELOPMENT_PROFILE,sort_keys=True,separators=(",", ":")).encode()).hexdigest(),
            bootstrap_sha256=_ARC_CHILD_BOOTSTRAP_SHA256)
        validate_inputs(code, kept_functions, timeout_seconds, DEVELOPMENT_PROFILE)
        if hashlib.sha256(_SANDBOX_BOOTSTRAP.encode("utf-8")).hexdigest() != _ARC_CHILD_BOOTSTRAP_SHA256:
            host_confinement_record["status"] = "child_bootstrap_source_mismatch"
            return _arc_confinement_result({"error": "Sandbox child bootstrap source hash differs.",
                                            "stdout": "", "action_results": []})

        with tempfile.TemporaryDirectory(prefix="rgb_python_tool_") as sandbox_dir:
            initial_payload_bytes = encode_json({'code': code, 'kept_functions': list(kept_functions or []), 'persistence_enabled': kept_functions is not None, 'retain_imports': retain_imports, 'repair_hints': repair_hints, 'animation_enabled': animation_handler is not None, 'timeout_seconds': timeout_seconds, 'sandbox_cwd': sandbox_dir, 'state': initial_state, 'color_chars': ARC_COLOR_CHARS}, DEVELOPMENT_PROFILE, DEVELOPMENT_PROFILE["max_input_bytes"])
            receipt_observer.observe("spawn_intent")
            try:
                process = subprocess.Popen(
                    [sys.executable, "-I", "-S", "-c", _SANDBOX_BOOTSTRAP],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=False,
                    cwd=sandbox_dir,
                    env=_sandbox_env(),
                    start_new_session=True,
                    close_fds=True,
                )
            except OSError as error:
                receipt_observer.observe("spawn_failed", error=error)
                return _arc_confinement_result({
                    "error": "Sandbox process could not start.",
                    "stdout": "",
                    "action_results": [],
                })
            receipt_observer.observe("spawn_returned", process=process)
            assert process.stdin is not None
            assert process.stdout is not None
            assert process.stderr is not None

            channel = BoundedChildIO(process, deadline, DEVELOPMENT_PROFILE)

            channel.send_encoded(initial_payload_bytes)

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BoundsFailure("deadline")

                message = channel.recv_message()
                if message is None:
                    stderr = ""
                    return _arc_confinement_result({
                        "error": _sanitize_host_error_text(stderr),
                        "stdout": "",
                        "action_results": list(host_action_results),
                    })

            

                if not isinstance(message, dict):
                    host_confinement_record["status"] = "invalid_message_object"
                    return _arc_confinement_result({"error": "Sandbox confinement gate failed.",
                                                    "stdout": "", "action_results": []})
                msg_type = str(message.get("type", "")).strip()
                if not host_confinement_record["gate_passed"]:
                    ready = (_arc_confinement_ready_record(message, timeout_seconds)
                             if msg_type == "confinement_ready" else None)
                    if ready is None:
                        receipt_observer.observe("setup_observed", gate_passed=False,status="mandatory_child_setup_failed",setup=None)
                        host_confinement_record["status"] = "mandatory_child_setup_failed"
                        failure = message.get("failure") if msg_type == "confinement_failed" else None
                        if isinstance(failure, dict):
                            host_confinement_record["failure"] = {
                                key: failure[key] for key in ("stage", "errno", "errno_name", "exception_type")
                                if key in failure and isinstance(failure[key], (str, int))}
                        return _arc_confinement_result({"error": "Sandbox confinement gate failed.",
                                                        "stdout": "", "action_results": []})
                    host_confinement_record.update(status="trusted_bootstrap_ready_report_received",
                                                    gate_passed=True, trusted_setup_report=ready)
                    receipt_observer.observe("setup_observed", gate_passed=True,status=host_confinement_record["status"],setup=ready)
                    continue
                if msg_type in {"confinement_ready", "confinement_failed"}:
                    host_confinement_record["status"] = "unexpected_duplicate_setup_message"
                    return _arc_confinement_result({"error": "Sandbox returned a duplicate setup message.",
                                                    "stdout": "", "action_results": list(host_action_results)})
                if msg_type == "animation":
                    if animation_handler is None:
                        channel.send_json({"type": "animation_error",
                             "error": "Animation frames are not available in this session."})
                        continue
                    try:
                        channel.check_deadline()
                        animation_payload = animation_handler(dict(message.get("request") or {}))
                    except Exception:  # noqa: BLE001
                        channel.send_json({"type": "animation_error",
                             "error": "animation failed in sandbox host."})
                        continue
                    channel.send_json({"type": "animation_result", "animation": animation_payload})
                    continue
                if msg_type == "action":
                    try:
                        # the message carries more than the action list: stale_after
                        # tells the solver a previous action in this snippet changed
                        # nothing, which it weighs after its own guards
                        channel.check_deadline()
                        action_result_payload = action_handler(
                            list(message.get("actions") or []),
                            stale_after=message.get("stale_after"),
                            prediction=message.get("prediction"),
                        )
                    except Exception:  # noqa: BLE001
                        channel.send_json({
                                "type": "action_error",
                                "error": "action failed in sandbox host.",
                            })
                        continue
                    raw_action_result = action_result_payload.get("action_result") or {}
                    if isinstance(raw_action_result, dict):
                        host_action_results.append(dict(raw_action_result))
                    channel.send_json({
                            "type": "action_result",
                            "action_result": raw_action_result,
                            "state": action_result_payload.get("state") or {},
                        })
                    continue

                if msg_type in {"final", "error"}:
                    validate_inputs("", [item.get("source") for item in message.get("keepable_functions", [])], timeout_seconds, DEVELOPMENT_PROFILE)
                    encode_json(message.get("result"), DEVELOPMENT_PROFILE, DEVELOPMENT_PROFILE["max_result_bytes"])
                    displayed = message.get("stdout", "")
                    if type(displayed) is not str or len(displayed.encode("utf-8")) > DEVELOPMENT_PROFILE["max_display_stdout_bytes"]:
                        raise BoundsFailure("display_stdout_limit")
                    channel.finish()
                    verified = verify_child_receipts(message.get("action_results"), host_action_results)
                    if not verified["valid"]:
                        return _arc_confinement_result({"stdout": "", "result": None, "error": verified["error"],
                                "action_results": verified["action_results"], "keepable_functions": [],
                                "receipt_integrity_error": True})
                    return _arc_confinement_result({
                        "stdout": str(message.get("stdout", "") or ""),
                        "result": message.get("result"),
                        "error": str(message.get("error", "") or ""),
                        "action_results": verified["action_results"],
                        "keepable_functions": list(message.get("keepable_functions") or []),
                        **({"retention_rejected": message.get("retention_rejected", [])}
                           if kept_functions is not None else {}),
                    })

                return _arc_confinement_result({
                    "error": "Sandbox process returned an unknown message type.",
                    "stdout": "",
                    "action_results": list(host_action_results),
                })
    except (HostStopped, ChildReceiptError):
        raise
    except BoundsFailure as exc:
        resource_failure = exc.record()
        return _arc_confinement_result({"error": "Sandbox resource bound failed: " + exc.stage,
            "stdout": "", "action_results": list(host_action_results)})
    except Exception:
        resource_failure = {"stage": "unexpected_host_failure"}
        return _arc_confinement_result({"error": "Sandbox host failed closed.",
            "stdout": "", "action_results": list(host_action_results)})
    finally:
        original_error = sys.exc_info()[1]
        cleanup = None
        cleanup_error = None
        channel_observed = ({key: getattr(channel,key) for key in
            ("stdout_bytes","stderr_bytes","messages","stdout_eof","stderr_eof")} if channel is not None else None)
        try:
            cleanup = (channel.close_and_reap() if channel is not None else
                       close_process(process) if process is not None else
                       {"reaped": True, "pipes_closed": True, "returncode": None})
            for result in pending_results:
                bounds = result["confinement"]["resource_bounds"]
                bounds.update(cleanup=cleanup, elapsed_seconds=time.monotonic() - started,
                    completion_within_io_bounds=resource_failure is None)
                if not cleanup["reaped"] or not cleanup["pipes_closed"]:
                    bounds.update(failure={"stage": "cleanup_failed"}, completion_within_io_bounds=False)
                    result["error"] = "Sandbox cleanup failed closed."
                log.info("ARC_PAPER_CHILD_CONFINEMENT %s", json.dumps(result["confinement"], sort_keys=True, allow_nan=False))

        except BaseException as caught:
            cleanup_error = caught
            if original_error is None:
                raise
        finally:
            terminal_error = original_error or cleanup_error
            state = locals().get("host_confinement_record", {})
            try:
                receipt_observer.observe("sandbox_finished",cleanup=cleanup,channel=channel_observed,
                    error_type=type(terminal_error).__name__ if terminal_error is not None else None,
                    cleanup_error_type=type(cleanup_error).__name__ if cleanup_error is not None else None,
                    gate_passed=state.get("gate_passed",False),status=state.get("status","unavailable"),
                    resource_failure=resource_failure,elapsed_seconds=time.monotonic()-started)
            except BaseException:
                if terminal_error is None:
                    raise
