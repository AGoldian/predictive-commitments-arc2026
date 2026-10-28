# SPDX-License-Identifier: MIT-0
"""Bounded trusted-host pipe transport; no filter, game or SDK operations."""
from __future__ import annotations

from collections import deque
import errno
import json
import math
import os
import selectors
import signal
import subprocess
import time


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
    """Count before serialization, visiting only exact builtin JSON types."""
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


def validate_resource_report(record, timeout, profile):
    if type(record) is not dict or record.get("verified") is not True:
        return False
    expected = {"RLIMIT_AS": profile["address_space_bytes"], "RLIMIT_CPU": timeout + 1,
        "RLIMIT_FSIZE": profile["file_size_bytes"], "RLIMIT_NOFILE": profile["open_files"],
        "RLIMIT_CORE": profile["core_bytes"]}
    limits = record.get("limits")
    if type(limits) is not dict or set(limits) != set(expected):
        return False
    for name, maximum in expected.items():
        entry = limits[name]
        if type(entry) is not dict or entry.get("requested_maximum") != maximum:
            return False
        soft, hard = entry.get("soft"), entry.get("hard")
        if type(soft) is not int or type(hard) is not int or not 0 <= soft <= hard <= maximum:
            return False
    return True


def close_process(process):
    record = {"reaped": False, "pipes_closed": False, "returncode": None}
    try:
        try:
            running = process.poll() is None
        except OSError:
            running = True
        if running:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                try:
                    process.kill()
                except OSError:
                    pass
        try:
            record["returncode"] = process.wait(timeout=1)
            record["reaped"] = True
        except (OSError, subprocess.TimeoutExpired):
            pass
    finally:
        closed = True
        for name in ("stdin", "stdout", "stderr"):
            stream = getattr(process, name, None)
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    closed = False
        record["pipes_closed"] = closed
    return record


class BoundedChildIO:
    def __init__(self, process, deadline, profile=None):
        self.process, self.deadline = process, deadline
        self.profile = dict(DEVELOPMENT_PROFILE if profile is None else profile)
        self.selector = selectors.DefaultSelector()
        self.stdout_buffer, self.stderr_tail, self.lines = bytearray(), bytearray(), deque()
        self.stdout_bytes = self.stderr_bytes = self.messages = 0
        self.stdout_eof = self.stderr_eof = False
        try:
            for name in ("stdin", "stdout", "stderr"):
                os.set_blocking(getattr(process, name).fileno(), False)
            self.selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            self.selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        except BaseException as exc:
            self.selector.close()
            if isinstance(exc, OSError):
                raise BoundsFailure("pipe_io", exc.errno) from exc
            raise

    def check_deadline(self):
        if time.monotonic() >= self.deadline:
            raise BoundsFailure("deadline")

    def _read(self, stream, name):
        try:
            data = os.read(stream.fileno(), 16384)
        except BlockingIOError:
            return
        except OSError as exc:
            raise BoundsFailure("pipe_io", exc.errno) from exc
        if not data:
            self.selector.unregister(stream)
            if name == "stdout":
                self.stdout_eof = True
                if self.stdout_buffer:
                    raise BoundsFailure("incomplete_frame")
            else:
                self.stderr_eof = True
            return
        if name == "stderr":
            self.stderr_bytes += len(data)
            if self.stderr_bytes > self.profile["max_stderr_bytes"]:
                raise BoundsFailure("stderr_limit")
            self.stderr_tail.extend(data)
            del self.stderr_tail[:-4000]
            return
        self.stdout_bytes += len(data)
        if self.stdout_bytes > self.profile["max_stdout_bytes"]:
            raise BoundsFailure("stdout_limit")
        self.stdout_buffer.extend(data)
        while b"\n" in self.stdout_buffer:
            offset = self.stdout_buffer.index(10) + 1
            if offset > self.profile["max_frame_bytes"]:
                raise BoundsFailure("frame_limit")
            self.messages += 1
            if self.messages > self.profile["max_messages"]:
                raise BoundsFailure("message_limit")
            self.lines.append(bytes(self.stdout_buffer[:offset]))
            del self.stdout_buffer[:offset]
        if len(self.stdout_buffer) >= self.profile["max_frame_bytes"]:
            raise BoundsFailure("frame_limit")

    def _pump(self, pending=None, poll_interval=None):
        self.check_deadline()
        try:
            remaining = max(0, self.deadline - time.monotonic())
            events = self.selector.select(remaining if poll_interval is None else min(remaining, poll_interval))
            for key, _ in events:
                if key.data == "stdin":
                    try:
                        count = os.write(key.fileobj.fileno(), pending[:16384])
                    except BlockingIOError:
                        continue
                    pending = pending[count:]
                else:
                    self._read(key.fileobj, key.data)
        except OSError as exc:
            raise BoundsFailure("pipe_io", exc.errno) from exc
        return pending

    def send_encoded(self, raw):
        self.check_deadline()
        if len(raw) > self.profile["max_input_bytes"]:
            raise BoundsFailure("json_bytes")
        pending = memoryview(raw)
        self.selector.register(self.process.stdin, selectors.EVENT_WRITE, "stdin")
        try:
            while pending:
                pending = self._pump(pending)
        finally:
            self.selector.unregister(self.process.stdin)

    def send_json(self, value):
        self.check_deadline()
        self.send_encoded(encode_json(value, self.profile, self.profile["max_input_bytes"]))

    def recv_message(self):
        while not self.lines:
            self.check_deadline()
            if self.stdout_eof:
                return None
            self._pump()
        return decode_json_line(self.lines.popleft(), self.profile, self.profile["max_frame_bytes"])

    def finish(self):
        while self.process.poll() is None or not (self.stdout_eof and self.stderr_eof):
            self._pump(poll_interval=0.05)
        if self.lines or self.process.returncode != 0:
            raise BoundsFailure("child_exit")

    def close_and_reap(self):
        """No unbounded drain. All stdio and selector handles close even on error."""
        try:
            record = close_process(self.process)
            record.update(stdout_bytes=self.stdout_bytes, stderr_bytes=self.stderr_bytes)
        finally:
            self.selector.close()
            self.lines.clear()
            self.stdout_buffer.clear()
            self.stderr_tail.clear()
        return record
