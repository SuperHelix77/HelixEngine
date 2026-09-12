#!/usr/bin/env python3
"""Lossless command evidence with bounded, explicitly partial projections."""

import argparse
import base64
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _validate_argv(argv):
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(arg, str) or "\x00" in arg for arg in argv)
        or not argv[0]
    ):
        raise ValueError("Nonempty string argv required")


class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        (self.root / "objects").mkdir(parents=True, exist_ok=True)
        self.metrics = {
            "object_bytes_read": 0,
            "object_bytes_written": 0,
            "object_bytes_hashed": 0,
            "object_read_operations": 0,
            "staging_bytes_read": 0,
            "staging_bytes_written": 0,
            "projection_bytes_parsed": 0,
        }

    def put(self, data):
        if not isinstance(data, bytes):
            raise ValueError("Evidence objects require exact bytes")
        key = digest(data)
        self.metrics["object_bytes_hashed"] += len(data)
        path = self.root / "objects" / key
        if path.is_symlink():
            raise ValueError("Evidence object symlink is not accepted")
        if path.exists():
            existing = path.read_bytes()
            self.metrics["object_bytes_read"] += len(existing)
            self.metrics["object_read_operations"] += 1
            self.metrics["object_bytes_hashed"] += len(existing)
            if digest(existing) != key:
                raise ValueError("Existing evidence object is corrupt")
        else:
            fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".helix-object-")
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
                self.metrics["object_bytes_written"] += len(data)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return {"sha256": key, "bytes": len(data)}

    def get(self, key):
        if not isinstance(key, str) or not _DIGEST.fullmatch(key):
            raise ValueError("Invalid evidence digest")
        path = self.root / "objects" / key
        if path.is_symlink():
            raise ValueError("Evidence object symlink is not accepted")
        data = path.read_bytes()
        self.metrics["object_bytes_read"] += len(data)
        self.metrics["object_read_operations"] += 1
        self.metrics["object_bytes_hashed"] += len(data)
        if digest(data) != key:
            raise ValueError("Evidence hash mismatch; do not trust the projection")
        return data

    def receipt(self, key):
        value = json.loads(self.get(key))
        if not isinstance(value, dict):
            raise ValueError("Evidence receipt must be an object")
        return value

    def retrieve_many(self, key, ranges, stream="stdout"):
        """Retrieve ordered inclusive spans from one verified source snapshot."""
        if stream not in ("stdout", "stderr"):
            raise ValueError("Invalid evidence stream")
        if not isinstance(ranges, list) or not ranges:
            raise ValueError("At least one range is required")
        for start, end in ranges:
            if (
                type(start) is not int
                or type(end) is not int
                or start < 1
                or end < start
            ):
                raise ValueError("Invalid 1-based inclusive line range")
        receipt = self.receipt(key)
        source = receipt[stream]
        raw = self.get(source["sha256"])
        lines = raw.splitlines(keepends=True)
        if any(end > len(lines) for _, end in ranges):
            raise ValueError("Range exceeds evidence lines")
        spans = []
        for start, end in ranges:
            selected = b"".join(lines[start - 1 : end])
            try:
                body = {"text": selected.decode("utf-8")}
            except UnicodeDecodeError:
                body = {"base64": base64.b64encode(selected).decode("ascii")}
            spans.append(
                {
                    "range_1based": [start, end],
                    "bytes": len(selected),
                    "sha256": digest(selected),
                    **body,
                }
            )
        return {
            "schema": "helix.evidence.ranges.v1",
            "receipt": key,
            "stream": stream,
            "source": source,
            "spans": spans,
            "io": dict(self.metrics),
            "io_scope": "application object bytes; entire source verified once per call; output hashing, metadata, physical traffic and CPU unmeasured",
        }

    def retrieve(self, key, stream="stdout", start=None, end=None, index=None):
        if stream not in ("stdout", "stderr"):
            raise ValueError("Invalid evidence stream")
        if start is None and end is not None:
            raise ValueError("End requires a starting line")
        if start is not None and (type(start) is not int or start < 1):
            raise ValueError("Invalid 1-based inclusive line range")
        if end is not None and (type(end) is not int or end < start):
            raise ValueError("Invalid 1-based inclusive line range")
        receipt = self.receipt(key)
        source = receipt[stream]
        if index is not None:
            from .line_index import retrieve as indexed_retrieve

            raw, _ = indexed_retrieve(self, index, source["sha256"], 1 if start is None else start, end)
        else:
            raw = self.get(source["sha256"])
            if start is not None:
                lines = raw.splitlines(keepends=True)
                if end is not None and end > len(lines):
                    raise ValueError("Range exceeds evidence lines")
                raw = b"".join(lines[start - 1 : end])
        try:
            body = {"text": raw.decode("utf-8")}
        except UnicodeDecodeError:
            body = {"base64": base64.b64encode(raw).decode("ascii")}
        return {
            "receipt": key,
            "stream": stream,
            "range_1based": [start, end],
            "sha256": digest(raw),
            "bytes": len(raw),
            "io": dict(self.metrics),
            "io_scope": "application object/staging byte counts, not physical SSD traffic; OS metadata and cache traffic unmeasured",
            **body,
        }


ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def reduce_stream(raw, kind, limit=8):
    """Create a lossy projection; exact bytes remain in the raw receipt."""
    if kind not in ("generic", "pytest", "compiler"):
        raise ValueError("Unknown reducer kind")
    lines = [line.decode("utf-8", errors="replace") for line in raw.splitlines()]
    view = [ANSI.sub("", line) for line in lines]
    result = {"lines": len(lines), "projection_only": True}
    diagnostics = []
    counts = []
    sections = []
    for number, line in enumerate(view, 1):
        if kind == "pytest":
            if re.search(r"\b\d+ (?:passed|failed|error|errors|skipped|xfailed|xpassed)\b", line) and (
                " in " in line or line.startswith("=")
            ):
                counts.append({"line": number, "text": line})
            if re.match(r"^(?:FAILED|ERROR)\s", line) or re.match(r"^E\s+", line):
                diagnostics.append({"line": number, "text": line})
            if re.match(r"^_{3,}.+_{3,}$", line):
                sections.append({"start": number, "header": line})
        elif kind == "compiler":
            if re.search(r"(?:^|\s)(?:fatal error|error|warning):", line):
                diagnostics.append({"line": number, "text": line})
        elif re.search(r"(?i)\b(error|failed|failure|warning|exception|panic)\b", line):
            diagnostics.append({"line": number, "text": line})
    for number, section in enumerate(sections):
        section["end"] = sections[number + 1]["start"] - 1 if number + 1 < len(sections) else len(lines)
    result.update(
        summary_candidates=counts[-2:],
        diagnostics=diagnostics[:limit],
        diagnostic_lines_omitted=max(0, len(diagnostics) - limit),
        failure_section_index=sections[:limit],
        failure_sections_omitted=max(0, len(sections) - limit),
    )
    if not diagnostics and not counts:
        result["preview"] = [
            {"line": number + 1, "text": view[number]}
            for number in sorted(
                set(range(min(2, len(view)))) | set(range(max(0, len(view) - 2), len(view)))
            )
        ]
    return result


def packet(store, key, kind="generic", max_bytes=6000):
    if type(max_bytes) is not int or max_bytes < 1400:
        raise ValueError("Packet budget too small for provenance and retrieval contract")
    receipt = store.receipt(key)
    packet_value = {
        "schema": "helix.evidence.v1",
        "receipt": key,
        "store": str(store.root),
        "command": receipt["argv"],
        "cwd": receipt["cwd"],
        "environment_id": receipt["environment_id"],
        "exit_code": receipt["exit_code"],
        "timed_out": receipt["timed_out"],
        "interrupted": receipt.get("interrupted", False),
        "wall_seconds": receipt["wall_seconds"],
        "raw": {stream: receipt[stream] for stream in ("stdout", "stderr")},
        "kind": kind,
        "coverage": "partial typed projection; originals retained losslessly; missing detail must be retrieved",
        "streams": {
            stream: reduce_stream(store.get(receipt[stream]["sha256"]), kind)
            for stream in ("stdout", "stderr")
        },
        "changed_watched_files": receipt["changed_watched_files"],
    }
    store.metrics["projection_bytes_parsed"] += sum(receipt[stream]["bytes"] for stream in ("stdout", "stderr"))
    packet_value["middleware_io"] = dict(store.metrics)
    packet_value["io_scope"] = "application object/staging bytes; physical disk, metadata and cache traffic unmeasured"

    def encoded():
        return json.dumps(packet_value, ensure_ascii=False, separators=(",", ":")).encode()

    if len(encoded()) > max_bytes:
        packet_value["streams"] = {
            stream: {"lines": packet_value["streams"][stream]["lines"], "projection_omitted_due_to_budget": True}
            for stream in ("stdout", "stderr")
        }
        packet_value["retrieval_required"] = True
    if len(encoded()) > max_bytes:
        packet_value.pop("command", None)
        packet_value.pop("cwd", None)
        packet_value.pop("changed_watched_files", None)
        packet_value["metadata_in_receipt"] = True
    if len(encoded()) > max_bytes:
        raise ValueError("Metadata exceeds packet budget; raw receipt remains available")
    return packet_value


def stop_tree(child, force=False, process_group_id=None):
    """Terminate the managed foreground process group created by capture.

    ``process_group_id`` is captured immediately after spawn.  Looking up a
    group from an already exited parent can race with parent reaping and leave
    a delayed writer alive, so cleanup never derives the identity from an
    exited child when capture supplied one.
    """
    if child is None:
        return "not_started"
    if not force and child.poll() is not None:
        return "already_exited"
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(child.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if child.poll() is None:
            child.kill()
            return "signal_sent"
        return "signal_sent" if result.returncode == 0 else "parent_already_exited_unverified"
    group_id = process_group_id
    if group_id is None:
        try:
            group_id = os.getpgid(child.pid)
        except ProcessLookupError:
            return "already_gone"
    if type(group_id) is not int or group_id <= 0:
        return "unavailable"
    try:
        os.killpg(group_id, signal.SIGKILL)
    except ProcessLookupError:
        return "already_gone"
    except PermissionError:
        return "permission_denied"
    return "signal_sent"


def _safe_progress(callback, stdout_path, stderr_path):
    if callback is None:
        return
    try:
        callback(stdout_path.stat().st_size, stderr_path.stat().st_size)
    except Exception:
        # Telemetry must not change child execution semantics.
        return


class CapturePublicationError(RuntimeError):
    """A command completed but evidence publication failed; never execute again."""

    def __init__(self, cause, stdout, stderr, exit_code, timed_out, interrupted, staging):
        super().__init__(f"Evidence publication failed: {type(cause).__name__}: {cause}")
        self.result = dict(stdout=stdout, stderr=stderr, exit_code=exit_code,
                           timed_out=timed_out, interrupted=interrupted,
                           recovery_staging=str(staging))


def capture(
    store,
    argv,
    cwd,
    environment_id,
    timeout=None,
    watch=(),
    env=None,
    on_start=None,
    on_progress=None,
    poll_interval=0.05,
    completed_result=None,
    native_process_group=False,
):
    """Execute exactly one argv without a shell and retain both raw streams.

    ``on_start`` may return a cleanup callable.  Callback failures are
    observation failures and never cause a retry or a second child.  A launch
    error still receives a command receipt with null ``exit_code``.
    """
    _validate_argv(argv)
    if type(timeout) not in (type(None), int, float) or (
        timeout is not None and (timeout <= 0 or not math.isfinite(timeout))
    ):
        raise ValueError("Finite positive timeout required")
    if not isinstance(environment_id, str) or not environment_id or "\x00" in environment_id:
        raise ValueError("Environment identity required")
    cwd = Path(cwd).expanduser().resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError("Working directory required")
    watch_paths = [Path(item) if Path(item).is_absolute() else cwd / item for item in watch]

    def snapshot():
        result = {}
        for path in watch_paths:
            try:
                result[str(path)] = digest(path.read_bytes()) if path.is_file() else None
            except OSError:
                result[str(path)] = None
        return result

    before = snapshot()
    started = time.time()
    staging = store.root / "runs" / uuid.uuid4().hex
    staging.mkdir(parents=True, exist_ok=False)
    stdout_path = staging / "stdout"
    stderr_path = staging / "stderr"
    started_json = json.dumps({"argv": argv, "cwd": str(cwd), "started_unix": started}, ensure_ascii=False)
    (staging / "started.json").write_text(started_json, encoding="utf-8")
    store.metrics["staging_bytes_written"] += len(started_json.encode())
    timed_out = False
    interrupted = False
    exit_code = None
    launch_error = None
    child = None
    cleanup = None
    process_group_id = None
    cleanup_info = {
        "attempted": False,
        "forced": not native_process_group,
        "method": "native-owned-process-group" if native_process_group else "windows-taskkill-tree" if os.name == "nt" else "posix-process-group",
        "status": "not_started",
        "reasons": [],
        "parent_exit_observed": None,
        "scope": "native-owned-process-group" if native_process_group else "managed-foreground-process-group",
    }

    def request_cleanup(reason):
        if child is None:
            return
        if native_process_group:
            # Remain in Codex's process group: its cancellation must reach the
            # original command and descendants even if this wrapper is SIGKILLed.
            # Never kill the caller's whole group from inside the wrapper.
            if child.poll() is None:
                child.kill()
                cleanup_info["attempted"] = True
            cleanup_info["status"] = "native_group_owner_responsible"
            cleanup_info["reasons"].append(reason)
            return
        cleanup_info["attempted"] = True
        cleanup_info["reasons"].append(reason)
        cleanup_info["parent_exit_observed"] = child.poll() is not None
        status = stop_tree(child, force=True, process_group_id=process_group_id)
        cleanup_info["status"] = status

    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            popen_kwargs = {
                "cwd": str(cwd),
                "stdout": stdout,
                "stderr": stderr,
                "env": env,
            }
            if os.name == "nt":
                popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            else:
                popen_kwargs["start_new_session"] = not native_process_group
            try:
                child = subprocess.Popen(argv, **popen_kwargs)
            except OSError as exc:
                launch_error = f"{type(exc).__name__}: {exc}"
            else:
                if os.name == "nt":
                    process_group_id = child.pid
                else:
                    # start_new_session creates a new group whose leader is
                    # the child.  Retain the identity before normal parent
                    # exit can make a later lookup invalid.
                    try:
                        process_group_id = os.getpgid(child.pid)
                    except OSError:
                        process_group_id = child.pid
                try:
                    if on_start is not None:
                        candidate = on_start(child.pid, stdout_path, stderr_path)
                        if callable(candidate):
                            cleanup = candidate
                except Exception:
                    # A broken observer cannot alter the one child invocation.
                    cleanup = None
                deadline = None if timeout is None else time.monotonic() + timeout
                while True:
                    _safe_progress(on_progress, stdout_path, stderr_path)
                    if deadline is None:
                        wait_for = poll_interval
                    else:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            timed_out = True
                            request_cleanup("timeout")
                            exit_code = child.wait()
                            break
                        wait_for = min(poll_interval, remaining)
                    try:
                        exit_code = child.wait(timeout=wait_for)
                        break
                    except subprocess.TimeoutExpired:
                        continue
                    except KeyboardInterrupt:
                        interrupted = True
                        request_cleanup("interrupt")
                        exit_code = child.wait()
                        break
        finally:
            if child is not None:
                # Always force cleanup after the parent is observed, including
                # normal exit.  A managed foreground command may have left a
                # descendant holding an output descriptor; killing the saved
                # group makes the retained byte snapshot immutable.  Detached
                # sessions/background daemons remain outside this scope.
                if not cleanup_info["attempted"] or cleanup_info["status"] in {
                    "permission_denied",
                    "unavailable",
                    "parent_already_exited_unverified",
                }:
                    request_cleanup("capture-finally")
                if child.poll() is None:
                    child.wait()
            if cleanup is not None:
                try:
                    cleanup()
                except Exception:
                    pass
    _safe_progress(on_progress, stdout_path, stderr_path)
    stdout_bytes = stdout_path.read_bytes()
    stderr_bytes = stderr_path.read_bytes()
    if completed_result is not None:
        completed_result.update(stdout=stdout_bytes, stderr=stderr_bytes,
            exit_code=exit_code, timed_out=timed_out, interrupted=interrupted,
            recovery_staging=str(staging))
    store.metrics["staging_bytes_read"] += len(stdout_bytes) + len(stderr_bytes)
    store.metrics["staging_bytes_written"] += len(stdout_bytes) + len(stderr_bytes)
    try:
        stdout_ref = store.put(stdout_bytes)
        stderr_ref = store.put(stderr_bytes)
        finished = time.time()
        after = snapshot()
        receipt = {
            "schema": "helix.command.v1",
            "argv": list(argv),
            "cwd": str(cwd),
            "environment_id": environment_id,
            "started_unix": started,
            "finished_unix": finished,
            "wall_seconds": round(finished - started, 6),
            "exit_code": exit_code,
            "timed_out": timed_out,
            "interrupted": interrupted,
            "stdout": stdout_ref,
            "stderr": stderr_ref,
            "changed_watched_files": {
                path: {"before": before[path], "after": after[path]}
                for path in before
                if before[path] != after[path]
            },
            "descendant_cleanup": cleanup_info,
            "limits": ("Native caller owns process-group lifecycle. " if native_process_group else "") + "stdout/stderr bytes retained separately; cross-stream interleaving is not recorded; watched-file changes only; standalone capture forces managed-group descendant cleanup, while native-group capture delegates group lifecycle to the caller; detached sessions/background daemons are outside this capture; environment label is caller supplied, not a full environment attestation",
        }
        if launch_error is not None:
            receipt["launch_error"] = launch_error
        key = store.put(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")).encode())["sha256"]
        staged = json.dumps({"receipt": key, "staging_copies_retained": True}, separators=(",", ":"))
        (staging / "receipt.json").write_text(staged, encoding="utf-8")
        store.metrics["staging_bytes_written"] += len(staged.encode())
        return key
    except Exception as exc:
        raise CapturePublicationError(exc, stdout_bytes, stderr_bytes, exit_code,
                                      timed_out, interrupted, staging) from exc



def run(store, argv, cwd, environment_id, kind="generic", timeout=None, watch=(), env=None):
    return packet(store, capture(store, argv, cwd, environment_id, timeout, watch, env), kind)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    subcommands = parser.add_subparsers(dest="op", required=True)
    command = subcommands.add_parser("run")
    command.add_argument("--cwd", default=".")
    command.add_argument("--environment-id", default="unspecified")
    command.add_argument("--kind", choices=["generic", "pytest", "compiler"], default="generic")
    command.add_argument("--timeout", type=float)
    command.add_argument("--watch", action="append", default=[])
    command.add_argument("argv", nargs=argparse.REMAINDER)
    get = subcommands.add_parser("get")
    get.add_argument("receipt")
    get.add_argument("--stream", choices=["stdout", "stderr"], default="stdout")
    get.add_argument("--start", type=int)
    get.add_argument("--end", type=int)
    many = subcommands.add_parser("get-many")
    many.add_argument("receipt")
    many.add_argument("--stream", choices=["stdout", "stderr"], default="stdout")
    many.add_argument("--range", dest="ranges", nargs=2, type=int, action="append", required=True, metavar=("START", "END"))
    args = parser.parse_args()
    store = Store(args.store)
    if args.op == "run":
        argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
        if not argv:
            raise ValueError("A command argv is required")
        result = run(store, argv, args.cwd, args.environment_id, args.kind, args.timeout, args.watch)
    elif args.op == "get-many":
        result = store.retrieve_many(args.receipt, args.ranges, args.stream)
    else:
        result = store.retrieve(args.receipt, args.stream, args.start, args.end)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if args.op == "run":
        code = result["exit_code"]
        sys.exit(124 if result["timed_out"] else 128 - code if isinstance(code, int) and code < 0 else code or 1)


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    main()
