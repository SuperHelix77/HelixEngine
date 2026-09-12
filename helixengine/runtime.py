"""Application runtime: explicit command execution, evidence, and telemetry.

This module is deliberately local and deterministic.  It does not invoke a
model, install a hook, intercept Codex activity, or claim universal parity.
"""

import base64
import json
import math
import threading
import time
from pathlib import Path

from . import release_data
from .core import named_plans
from .core.completion_ledger import CompletionLedger
from .core.evidence import CapturePublicationError, Store, capture, packet
from .core.workflow_memory import Memory
from .pricing import Prices, estimate
from .state import State


# Conservative byte heuristics, not a claim of native token economics. Returning
# complete raw output avoids marginal projection/retrieval costs without turning
# off Engine capture or removing any information from the model.
OUTPUT_ADMISSION_MIN_RAW_BYTES = 2048
OUTPUT_ADMISSION_MIN_SAVINGS_BYTES = 512
OUTPUT_ADMISSION_MIN_SAVINGS_PERCENT = 20
APP_VERSION = "0.1.0"
RELEASE_VERSION = "0.1.0-preview.1"
PRICE_REFRESH_SECONDS = 120


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def _read_limited(path, limit):
    path = Path(path)
    data = path.read_bytes()
    if len(data) > limit:
        raise ValueError("File exceeds configured evidence limit")
    return data


class Runtime:
    """Own one state database and one content-addressed evidence store."""

    def __init__(self, data_dir=None, *, price_fetcher=None, reducer=None):
        self.data_dir = Path(data_dir or "~/.helixengine").expanduser().resolve()
        self.state = State(self.data_dir)
        self.store = Store(self.data_dir / "evidence")
        self.memory = Memory(self.store)
        self.completions = CompletionLedger(self.memory)
        self.prices = Prices(fetcher=price_fetcher) if price_fetcher is not None else Prices()
        self.reducer = reducer or packet
        self.csrf_token = __import__("secrets").token_urlsafe(32)
        self._price_lock = threading.Lock()
        self._price_next_attempt = 0.0
        self._price_thread = None
        # One-shot commands must remain local and must not leave an active
        # TLS worker behind at interpreter shutdown.  The HTTP server opts in
        # explicitly because its lifecycle can join the worker on close.
        self._pricing_enabled = False
        self._closed = False
        self.research = False
        self.chat_observer = None
        self._chat_stop = threading.Event()
        self._chat_thread = None
        self._chat_error = None

    def attach_chat(self, rollout, thread_id):
        """Observe native metadata only; never intercept or initiate inference."""
        from .chat_observer import ChatObserver
        if self.chat_observer is not None:
            raise ValueError("A chat is already attached")
        self.chat_observer = ChatObserver(self.data_dir, rollout, thread_id)

        def watch():
            while not self._chat_stop.is_set():
                try:
                    self.chat_observer.scan()
                    self._chat_error = None
                except Exception as exc:
                    self._chat_error = type(exc).__name__
                self._chat_stop.wait(1)

        self._chat_thread = threading.Thread(target=watch, name="helix-chat-observer", daemon=True)
        self._chat_thread.start()

    def _telemetry(self, kind, body, run=None):
        return self.state.event(kind, body, run=run)

    def enable_pricing(self):
        """Allow official pricing refreshes for a server-owned runtime."""
        with self._price_lock:
            if self._closed:
                raise RuntimeError("Runtime is closed")
            self._pricing_enabled = True

    def close(self):
        """Close the runtime and join any server-owned pricing worker."""
        self._chat_stop.set()
        if self._chat_thread is not None:
            self._chat_thread.join(timeout=5)
        with self._price_lock:
            self._pricing_enabled = False
            self._closed = True
            worker = self._price_thread
        if worker is not None and worker is not threading.current_thread():
            # The official fetch has a bounded timeout.  Joining keeps
            # interpreter shutdown out of an in-flight TLS operation.
            worker.join()

    def _maybe_refresh_prices(self):
        with self._price_lock:
            if not self._pricing_enabled or self._closed:
                return
        now = time.time()
        with self._price_lock:
            if now < self._price_next_attempt:
                return
            self._price_next_attempt = now + PRICE_REFRESH_SECONDS
            if self._price_thread is not None and self._price_thread.is_alive():
                return
            self._price_thread = threading.Thread(
                target=self.prices.refresh,
                name="helix-pricing-refresh",
                daemon=False,
            )
            self._price_thread.start()

    def _release(self):
        release_root = Path(release_data.__file__).resolve().parent / "release_evidence"
        release = release_data.project(_read_limited, release_root)
        price_state = self.prices.state()
        rates = price_state.get("rates") if price_state.get("fresh") else None
        for lane in release.get("lanes", []):
            costs = {}
            arms = {arm.get("arm"): arm for arm in lane.get("arms", [])}
            model_rates = rates.get(lane.get("model")) if isinstance(rates, dict) else None
            if model_rates:
                for arm_name in ("off", "on"):
                    usage = arms.get(arm_name, {}).get("usage")
                    if usage:
                        costs[arm_name] = estimate(usage, model_rates)
            lane["costs"] = costs
        return release

    def release_state(self):
        started = time.perf_counter()
        self._maybe_refresh_prices()
        state = self.state.snapshot()
        price_state = self.prices.state()
        observed = time.time()
        result = {
            "schema": "helix.app.v1",
            "app_version": APP_VERSION,
            "hub_mode": "research" if self.research else "release",
            "observed_at": observed,
            "settings": state["settings"],
            "csrf_token": self.csrf_token,
            "runs": state["runs"],
            "events": state["events"],
            "usages": state["usages"],
            "total_runs": state["total_runs"],
            "run_view_limit": state["run_view_limit"],
            "storage": state["storage"],
            "release": self._release(),
            "pricing": price_state,
            "observer": {
                "last_scan": observed,
                "last_scan_seconds": time.perf_counter() - started,
                "logical_file_bytes_read": self.store.metrics.get("object_bytes_read", 0),
                "error": None,
            },
        }
        if self.chat_observer is not None:
            result["chat_observer"] = self.chat_observer.snapshot()
            result["chat_observer"]["worker_error"] = self._chat_error
        try:
            result['receipt_memory'] = self.memory_status()
        except Exception as exc:
            result['receipt_memory'] = {'coverage': 'UNKNOWN', 'error': f'{type(exc).__name__}: {exc}'}
        return result

    def settings(self):
        return self.state.settings()

    def switch(self, enabled, revision):
        return self.state.switch(enabled, revision)

    @staticmethod
    def _validate_kind(kind):
        if kind not in ("generic", "pytest", "compiler"):
            raise ValueError("Unknown command kind")

    def run(self, argv, cwd=None, *, kind="generic", timeout=None, environment_id="helix-cli", native_process_group=False, origin=None):
        """Run one native command and retain exact raw streams.

        The setting is copied into the run before the child starts.  Reduction
        is attempted at most once after capture; a reducer error keeps the raw
        receipt and marks a safe fallback instead of rerunning the command.
        """
        self._validate_kind(kind)
        if type(timeout) not in (type(None), int, float) or (
            timeout is not None and (timeout <= 0 or not math.isfinite(timeout))
        ):
            raise ValueError("Finite positive timeout required")
        if (
            not isinstance(argv, (list, tuple))
            or not argv
            or any(not isinstance(arg, str) or "\x00" in arg for arg in argv)
            or not argv[0]
        ):
            raise ValueError("Nonempty string argv required")
        argv = list(argv)
        if cwd is None:
            cwd = Path.cwd()
        cwd = Path(cwd).expanduser().resolve(strict=True)
        if not cwd.is_dir():
            raise ValueError("Working directory required")
        row = self.state.begin(list(argv), cwd, origin)
        run_id = row["id"]
        started = time.perf_counter()

        def on_start(pid, stdout_path, stderr_path):
            self.state.mark_running(run_id, pid)

        def on_progress(stdout_bytes, stderr_bytes):
            self.state.progress(run_id, stdout_bytes, stderr_bytes)

        captured = {}
        try:
            receipt_key = capture(
                self.store,
                list(argv),
                cwd,
                environment_id,
                timeout=timeout,
                on_start=on_start,
                on_progress=on_progress,
                completed_result=captured,
                native_process_group=native_process_group,
            )
        except CapturePublicationError as exc:
            try:
                self.state.fail_without_receipt(run_id, str(exc),
                    elapsed_seconds=time.perf_counter() - started)
            except Exception:
                pass
            return {**exc.result, "run": row, "receipt": None,
                    "packet_receipt": None, "publication_error": str(exc)}
        except BaseException as exc:
            # No retry: a launch or observer failure is itself the terminal
            # observation for this requested command.
            self.state.fail_without_receipt(
                run_id,
                f"{type(exc).__name__}: {exc}",
                elapsed_seconds=time.perf_counter() - started,
            )
            raise

        try:
            receipt = self.store.receipt(receipt_key)
        except Exception as exc:
            return {**captured, "run": row, "receipt": receipt_key,
                    "packet_receipt": None, "publication_error": str(exc)}
        stdout_bytes = receipt["stdout"]["bytes"]
        stderr_bytes = receipt["stderr"]["bytes"]
        raw_bytes = stdout_bytes + stderr_bytes
        enabled = bool(row["enabled"])
        reducer_status = "OFF_PASSTHROUGH"
        packet_key = None
        visible_bytes = raw_bytes
        reducer_error = None
        if enabled:
            if raw_bytes < OUTPUT_ADMISSION_MIN_RAW_BYTES:
                reducer_status = "BYPASSED_SMALL_OUTPUT"
            else:
                try:
                    projection = self.reducer(self.store, receipt_key, kind)
                    projection_blob = _json_bytes(projection)
                    packet_bytes = len(projection_blob)
                    savings_bytes = raw_bytes - packet_bytes
                    if packet_bytes >= raw_bytes:
                        reducer_status = "BYPASSED_SMALL_OUTPUT"
                    elif (
                        savings_bytes >= OUTPUT_ADMISSION_MIN_SAVINGS_BYTES
                        and savings_bytes * 100
                        >= raw_bytes * OUTPUT_ADMISSION_MIN_SAVINGS_PERCENT
                    ):
                        packet_key = self.store.put(projection_blob)["sha256"]
                        visible_bytes = packet_bytes
                        reducer_status = "REDUCED"
                    else:
                        reducer_status = "BYPASSED_MARGINAL_GAIN"
                except Exception as exc:
                    # The captured receipt is authoritative and remains available.
                    reducer_status = "FAILED_FALLBACK_RAW"
                    reducer_error = f"{type(exc).__name__}: {exc}"

        exit_code = receipt["exit_code"]
        terminal_state = (
            "COMPLETED"
            if exit_code == 0 and not receipt["timed_out"] and not receipt.get("interrupted", False)
            else "FAILED"
        )
        # Keep the completed result available if final telemetry cannot commit.
        raw_stdout = captured["stdout"]
        raw_stderr = captured["stderr"]
        publication_error = None
        try:
            row = self.state.finish(
                run_id,
                state=terminal_state,
                stdout_bytes=stdout_bytes,
                stderr_bytes=stderr_bytes,
                visible_bytes=visible_bytes,
                elapsed_seconds=receipt["wall_seconds"],
                exit_code=exit_code,
                receipt=receipt_key,
                reducer_status=reducer_status,
                packet_receipt=packet_key,
                timed_out=receipt["timed_out"],
                interrupted=receipt.get("interrupted", False),
                error=reducer_error or receipt.get("launch_error"),
            )
        except Exception as exc:
            publication_error = f"Telemetry publication failed: {type(exc).__name__}: {exc}"
        memory_result = None
        if enabled and publication_error is None:
            # Completion is already durable. Indexing/recovery can never repeat
            # the command or change its exit status/delivered evidence.
            try:
                memory_result = self.memory_sync()
            except Exception as exc:
                memory_result = {'error': f'{type(exc).__name__}: {exc}',
                                 'coverage': 'UNKNOWN'}
        return {
            "run": row,
            "receipt": receipt_key,
            "packet_receipt": packet_key,
            "stdout": raw_stdout,
            "stderr": raw_stderr,
            "publication_error": publication_error,
            "memory": memory_result,
            "exit_code": exit_code,
            "timed_out": receipt["timed_out"],
            "interrupted": receipt.get("interrupted", False),
        }

    def memory_sync(self, limit=16):
        from .memory_lifecycle import ReceiptMemory
        result = ReceiptMemory(self.state, self.memory).drain(limit)
        try:
            self._telemetry('MEMORY_RECEIPTS_SYNCED', result)
        except Exception:
            # Durable cursor/status is still available. No execution recovery.
            result['telemetry_error'] = 'Memory sync telemetry unavailable'
        return result

    def memory_status(self):
        from .memory_lifecycle import ReceiptMemory
        return ReceiptMemory(self.state, self.memory).status()

    def retrieve(self, receipt, stream, start=None, end=None):
        return self.store.retrieve(receipt, stream, start, end)

    def visible_output(self, result):
        """Deliver the selected packet; retain raw streams in the evidence store."""
        packet_ref = result.get("packet_receipt")
        if packet_ref:
            try:
                return self.store.get(packet_ref), b""
            except Exception as exc:
                # The operation already ran. Deliver captured bytes, never retry.
                result["delivery_error"] = f"{type(exc).__name__}: {exc}"
                try:
                    self.state.event("PACKET_DELIVERY_FAILED", {"receipt": packet_ref,
                        "error": result["delivery_error"]}, run=result["run"]["id"])
                except Exception:
                    pass
        return result["stdout"], result["stderr"]

    def usage_import(self, run_id, receipt_json):
        raw = Path(receipt_json).expanduser().read_bytes()
        source_ref = self.store.put(raw)["sha256"]
        try:
            document = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (ValueError, TypeError) as exc:
            raise ValueError("Usage receipt JSON is invalid") from exc
        if not isinstance(document, dict):
            raise ValueError("Usage receipt must be an object")
        usage = document.get("usage") if isinstance(document.get("usage"), dict) else document
        usage = dict(usage)
        if "model" not in usage and isinstance(document.get("model"), str):
            usage["model"] = document["model"]
        validated = self.state.validate_usage(usage)
        result = self.state.usage(run_id, source_ref, validated)
        self._telemetry(
            "USAGE_IMPORT_OBSERVED",
            {"run": run_id, "source_hash": source_ref, "replayed": result["replayed"]},
            run=run_id,
        )
        return result

    @staticmethod
    def _memory_bytes(value):
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        raise ValueError("Memory records require exact UTF-8 text or bytes")

    def memory_record(self, project, session, event_id, raw):
        raw = self._memory_bytes(raw)
        started = time.perf_counter()
        result = self.memory.record(project, session, event_id, raw)
        self._telemetry(
            "MEMORY_RECORDED",
            {
                "project": project,
                "session": session,
                "event_id": event_id,
                "bytes": len(raw),
                "record_hash": result["record_hash"],
                "elapsed_seconds": time.perf_counter() - started,
            },
        )
        return result

    def memory_search(self, project, query, limit=10):
        started = time.perf_counter()
        result = self.memory.search(project, query, limit)
        self._telemetry(
            "MEMORY_SEARCHED",
            {
                "project": project,
                "query": query,
                "limit": limit,
                "records": len(result),
                "elapsed_seconds": time.perf_counter() - started,
            },
        )
        return result

    def memory_timeline(self, project, session, after=0, limit=50):
        started = time.perf_counter()
        result = self.memory.timeline(project, session, after=after, limit=limit)
        self._telemetry(
            "MEMORY_TIMELINE_READ",
            {
                "project": project,
                "session": session,
                "after": after,
                "limit": limit,
                "records": len(result),
                "elapsed_seconds": time.perf_counter() - started,
            },
        )
        return result

    def memory_retrieve(self, project, record_hashes, max_bytes=1048576):
        started = time.perf_counter()
        result = self.memory.retrieve(project, record_hashes, max_bytes=max_bytes)
        self._telemetry(
            "MEMORY_RETRIEVED",
            {
                "project": project,
                "records": len(result),
                "bytes": sum(len(item["raw"]) for item in result),
                "max_bytes": max_bytes,
                "elapsed_seconds": time.perf_counter() - started,
            },
        )
        return result

    def memory_replay(self, project, session, after=0, limit=50, max_bytes=1048576):
        started = time.perf_counter()
        result = self.memory.replay(project, session, after=after, limit=limit, max_bytes=max_bytes)
        self._telemetry(
            "MEMORY_REPLAYED",
            {
                "project": project,
                "session": session,
                "after": after,
                "limit": limit,
                "records": len(result["history"]),
                "max_bytes": max_bytes,
                "elapsed_seconds": time.perf_counter() - started,
            },
        )
        return result

    def plan_register(self, spec):
        required = {"plan_id", "plan_version", "cwd", "steps", "files", "executables"}
        if not isinstance(spec, dict) or not required <= set(spec) or set(spec) - required - {"env_names"}:
            raise ValueError("Registration requires identity, cwd, steps, files and executables; optional env_names")
        result = named_plans.register(self.store, **spec)
        self._telemetry("PLAN_REGISTERED", result)
        return result

    def plan_run(self, reference, timeout=None):
        started = time.perf_counter()
        result = named_plans.invoke(self.store, reference, timeout=timeout)
        self._telemetry(
            "PLAN_INVOKED",
            {
                "plan_hash": reference.get("plan_hash"),
                "attempt_hash": result.get("attempt_hash"),
                "status": result.get("status"),
                "elapsed_seconds": time.perf_counter() - started,
            },
        )
        return result

    def plan_rebind(self, reference, new_version):
        result = named_plans.rebind_inputs(self.store, reference, new_version)
        self._telemetry("PLAN_REBOUND", result)
        return result


def jsonable_memory(value):
    """Convert exact memory bytes into explicit UTF-8/base64 JSON fields."""
    if isinstance(value, bytes):
        try:
            return {"text": value.decode("utf-8")}
        except UnicodeDecodeError:
            return {"base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, list):
        return [jsonable_memory(item) for item in value]
    if isinstance(value, dict):
        return {key: jsonable_memory(item) for key, item in value.items()}
    return value


__all__ = ["APP_VERSION", "RELEASE_VERSION", "Runtime", "jsonable_memory"]
