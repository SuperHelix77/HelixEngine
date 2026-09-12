import hashlib
import json
import sys
import threading

import pytest

from helixengine.core.evidence import Store
from helixengine.core.workflow_memory import Memory
from helixengine.memory_lifecycle import ReceiptMemory
from helixengine.state import State


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _receipt(store, argv, cwd, *, stdout=b"stdout\n", stderr=b"", exit_code=0, **overrides):
    stdout_ref = store.put(stdout)
    stderr_ref = store.put(stderr)
    body = {
        "schema": "helix.command.v1",
        "argv": list(argv),
        "cwd": str(cwd),
        "environment_id": "receipt-memory-test",
        "started_unix": 1.0,
        "finished_unix": 1.001,
        "wall_seconds": 0.001,
        "exit_code": exit_code,
        "timed_out": False,
        "interrupted": False,
        "stdout": stdout_ref,
        "stderr": stderr_ref,
        "changed_watched_files": {},
        "descendant_cleanup": {"attempted": True},
        "limits": "fixture",
    }
    body.update(overrides)
    key = store.put(_json_bytes(body))["sha256"]
    return key, body


def _finish(
    state,
    store,
    cwd,
    *,
    name="run",
    enabled=True,
    origin=None,
    argv=None,
    stdout=b"stdout\n",
    stderr=b"",
    exit_code=0,
    receipt_key=None,
    receipt_overrides=None,
    row_stdout_bytes=None,
    row_stderr_bytes=None,
):
    current = state.settings()
    if current["enabled"] != enabled:
        state.switch(enabled, current["revision"])
    argv = list(argv or ["fixture", name])
    run = state.begin(argv, cwd, origin=origin)
    if receipt_key is None:
        receipt_overrides = dict(receipt_overrides or {})
        receipt_argv = receipt_overrides.pop("argv", argv)
        receipt_cwd = receipt_overrides.pop("cwd", cwd)
        receipt_exit_code = receipt_overrides.pop("exit_code", exit_code)
        receipt_key, receipt_body = _receipt(
            store,
            receipt_argv,
            receipt_cwd,
            stdout=stdout,
            stderr=stderr,
            exit_code=receipt_exit_code,
            **receipt_overrides,
        )
    else:
        receipt_body = None
    row = state.finish(
        run["id"],
        state="COMPLETED" if exit_code == 0 else "FAILED",
        stdout_bytes=len(stdout) if row_stdout_bytes is None else row_stdout_bytes,
        stderr_bytes=len(stderr) if row_stderr_bytes is None else row_stderr_bytes,
        visible_bytes=len(stdout) + len(stderr),
        elapsed_seconds=0.001,
        exit_code=exit_code,
        receipt=receipt_key,
        reducer_status="OFF_PASSTHROUGH",
    )
    return run, row, receipt_key, receipt_body


def _components(tmp_path):
    state = State(tmp_path)
    store = Store(tmp_path / "evidence")
    memory = Memory(store)
    return state, store, memory


def _terminal_events(state, run_id=None):
    with state.db() as db:
        rows = db.execute(
            "SELECT id, kind, body FROM events WHERE kind IN ('RUN_COMPLETED', 'RUN_FAILED') ORDER BY id"
        ).fetchall()
    result = []
    for row in rows:
        body = json.loads(row["body"])
        if run_id is None or body.get("id") == run_id:
            result.append((int(row["id"]), row["kind"], body))
    return result


def _assert_drain_shape(result):
    assert {"processed", "cursor", "backlog", "error", "coverage"} <= set(result)
    assert result["coverage"] == "historical_receipts_only"
    assert type(result["processed"]) is int and result["processed"] >= 0
    assert type(result["cursor"]) is int and result["cursor"] >= 0
    assert type(result["backlog"]) is int and result["backlog"] >= 0
    assert result["error"] is None or isinstance(result["error"], str)


def _assert_status_shape(result):
    assert {"cursor", "backlog", "error"} <= set(result)
    if "coverage" in result:
        assert result["coverage"] == "historical_receipts_only"
    assert type(result["cursor"]) is int and result["cursor"] >= 0
    assert type(result["backlog"]) is int and result["backlog"] >= 0
    assert result["error"] is None or isinstance(result["error"], str)


def test_drain_indexes_completed_and_failed_rows_from_finish_events(tmp_path):
    state, store, memory = _components(tmp_path)
    first = _finish(state, store, tmp_path, name="completed")
    second = _finish(state, store, tmp_path, name="failed", stdout=b"failure\n", exit_code=7)
    terminal = _terminal_events(state)
    assert [kind for _, kind, _ in terminal] == ["RUN_COMPLETED", "RUN_COMPLETED"]
    assert terminal[1][2]["state"] == "FAILED"
    assert first[1]["receipt"] == terminal[0][2]["receipt"]
    assert second[1]["receipt"] == terminal[1][2]["receipt"]
    assert {"id", "receipt", "cwd", "enabled"} <= set(terminal[0][2])

    lifecycle = ReceiptMemory(state, memory)
    result = lifecycle.drain()
    _assert_drain_shape(result)
    assert result["processed"] == 2
    assert result["backlog"] == 0
    assert result["error"] is None
    assert result["cursor"] == terminal[-1][0]

    status = lifecycle.status()
    _assert_status_shape(status)
    assert status["cursor"] == result["cursor"]
    assert status["backlog"] == 0
    assert status["error"] is None
    records = memory.timeline(str(tmp_path), "engine-local", limit=10)
    assert len(records) == 2
    assert {record["event_id"] for record in records} == {
        "engine-run:" + first[0]["id"],
        "engine-run:" + second[0]["id"],
    }


def test_duplicate_drain_is_idempotent_by_run_identity(tmp_path):
    state, store, memory = _components(tmp_path)
    run, _, _, _ = _finish(state, store, tmp_path)
    lifecycle = ReceiptMemory(state, memory)

    first = lifecycle.drain()
    second = lifecycle.drain()
    _assert_drain_shape(first)
    _assert_drain_shape(second)
    assert first["processed"] == 1
    assert second["processed"] == 0
    assert second["cursor"] == first["cursor"]
    assert second["backlog"] == 0
    assert memory.timeline(str(tmp_path), "engine-local")[0]["event_id"] == "engine-run:" + run["id"]


def test_conflicting_redelivery_for_same_run_is_rejected(tmp_path):
    state, store, memory = _components(tmp_path)
    run, row, _, _ = _finish(state, store, tmp_path)
    lifecycle = ReceiptMemory(state, memory)
    first = lifecycle.drain()
    assert first["processed"] == 1 and first["error"] is None

    conflicting_receipt, _ = _receipt(
        store,
        row["argv"],
        row["cwd"],
        stdout=b"different receipt bytes",
        stderr=b"",
        exit_code=row["exit_code"],
    )
    state.event(
        "RUN_COMPLETED",
        {
            **row,
            "receipt": conflicting_receipt,
            "stdout_bytes": len(b"different receipt bytes"),
            "stderr_bytes": 0,
        },
        run=run["id"],
    )
    blocked = lifecycle.drain()
    _assert_drain_shape(blocked)
    assert blocked["processed"] == 0
    assert blocked["cursor"] == first["cursor"]
    assert blocked["backlog"] == 1
    assert "collision" in blocked["error"].lower()
    assert len(memory.timeline(str(tmp_path), "engine-local")) == 1


def test_bounded_drain_cursor_survives_restart(tmp_path):
    state, store, memory = _components(tmp_path)
    runs = [_finish(state, store, tmp_path, name=str(index)) for index in range(3)]
    event_ids = [event_id for event_id, _, _ in _terminal_events(state)]
    lifecycle = ReceiptMemory(state, memory)

    first = lifecycle.drain(limit=2)
    _assert_drain_shape(first)
    assert first["processed"] == 2
    assert first["cursor"] == event_ids[1]
    assert first["backlog"] == 1

    restarted = ReceiptMemory(State(tmp_path), Memory(Store(tmp_path / "evidence")))
    status = restarted.status()
    _assert_status_shape(status)
    assert status["cursor"] == event_ids[1]
    assert status["backlog"] == 1
    second = restarted.drain(limit=16)
    _assert_drain_shape(second)
    assert second["processed"] == 1
    assert second["cursor"] == event_ids[2]
    assert second["backlog"] == 0
    assert len(restarted.memory.timeline(str(tmp_path), "engine-local", limit=10)) == 3


class _FailingMemory:
    def __init__(self, delegate):
        self.delegate = delegate

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def record(self, *args, **kwargs):
        raise RuntimeError("memory unavailable")


def test_memory_failure_keeps_cursor_until_recovery(tmp_path):
    state, store, memory = _components(tmp_path)
    _finish(state, store, tmp_path)
    failing = ReceiptMemory(state, _FailingMemory(memory))
    baseline = failing.status()
    _assert_status_shape(baseline)

    blocked = failing.drain()
    _assert_drain_shape(blocked)
    assert blocked["processed"] == 0
    assert blocked["cursor"] == baseline["cursor"]
    assert blocked["backlog"] == 1
    assert "memory unavailable" in blocked["error"]
    assert failing.status()["cursor"] == baseline["cursor"]

    recovered = ReceiptMemory(state, memory).drain()
    _assert_drain_shape(recovered)
    assert recovered["processed"] == 1
    assert recovered["backlog"] == 0
    assert recovered["error"] is None
    assert len(memory.timeline(str(tmp_path), "engine-local")) == 1


@pytest.mark.parametrize("bad_receipt", ["missing", "corrupt"])
def test_missing_or_corrupt_receipt_blocks_at_event(tmp_path, bad_receipt):
    state, store, memory = _components(tmp_path)
    if bad_receipt == "missing":
        key = hashlib.sha256(b"receipt is absent").hexdigest()
    else:
        key = store.put(b"not-json")["sha256"]
    run, _, _, _ = _finish(state, store, tmp_path, receipt_key=key)
    event_id = _terminal_events(state, run["id"])[0][0]
    lifecycle = ReceiptMemory(state, memory)
    baseline = lifecycle.status()

    blocked = lifecycle.drain()
    _assert_drain_shape(blocked)
    assert blocked["processed"] == 0
    assert blocked["cursor"] == baseline["cursor"]
    assert blocked["cursor"] < event_id
    assert blocked["backlog"] == 1
    assert blocked["error"]
    assert memory.timeline(str(tmp_path), "engine-local") == []

    _finish(state, store, tmp_path, name="later")
    still_blocked = lifecycle.drain()
    assert still_blocked["cursor"] == baseline["cursor"]
    assert still_blocked["processed"] == 0
    assert len(memory.timeline(str(tmp_path), "engine-local")) == 0


@pytest.mark.parametrize("mismatch", ["schema", "cwd", "argv", "exit_code", "stdout_bytes", "stderr_bytes"])
def test_receipt_identity_and_stream_counts_are_validated(tmp_path, mismatch):
    state, store, memory = _components(tmp_path)
    argv = ["fixture", mismatch]
    overrides = {}
    row_stdout_bytes = None
    row_stderr_bytes = None
    if mismatch == "schema":
        overrides["schema"] = "wrong.receipt.v1"
    elif mismatch == "cwd":
        overrides["cwd"] = str(tmp_path / "different-cwd")
    elif mismatch == "argv":
        overrides["argv"] = ["different", "argv"]
    elif mismatch == "exit_code":
        overrides["exit_code"] = 9
    elif mismatch == "stdout_bytes":
        row_stdout_bytes = 99
    else:
        row_stderr_bytes = 99
    _finish(
        state,
        store,
        tmp_path,
        argv=argv,
        stdout=b"out",
        stderr=b"err",
        receipt_overrides=overrides,
        row_stdout_bytes=row_stdout_bytes,
        row_stderr_bytes=row_stderr_bytes,
    )
    lifecycle = ReceiptMemory(state, memory)
    baseline = lifecycle.status()
    result = lifecycle.drain()
    _assert_drain_shape(result)
    assert result["processed"] == 0
    assert result["cursor"] == baseline["cursor"]
    assert result["backlog"] == 1
    assert result["error"]
    assert memory.timeline(str(tmp_path), "engine-local") == []


def test_disabled_rows_advance_cursor_without_memory_indexing(tmp_path):
    state, store, memory = _components(tmp_path)
    run, _, _, _ = _finish(state, store, tmp_path, enabled=False)
    event_id = _terminal_events(state, run["id"])[0][0]
    lifecycle = ReceiptMemory(state, memory)

    result = lifecycle.drain()
    _assert_drain_shape(result)
    assert result["cursor"] == event_id
    assert result["backlog"] == 0
    assert result["error"] is None
    assert memory.timeline(str(tmp_path), "engine-local") == []


def test_origin_attribution_and_metadata_keep_only_receipt_roots(tmp_path):
    state, store, memory = _components(tmp_path)
    hook_cwd = tmp_path / "hook-root"
    execution_cwd = tmp_path / "execution-root"
    hook_cwd.mkdir()
    execution_cwd.mkdir()
    stdout = b"stdout-private-marker-" + (b"S" * 2048)
    stderr = b"stderr-private-marker-" + (b"E" * 2048)
    origin = {
        "session_id": "parent-session",
        "thread_id": "child-thread",
        "agent_id": "child-agent",
        "hook_cwd": str(hook_cwd),
        "execution_cwd": str(execution_cwd),
    }
    run, row, receipt_key, receipt_body = _finish(
        state,
        store,
        execution_cwd,
        name="child",
        argv=["fixture", "child"],
        stdout=stdout,
        stderr=stderr,
        origin=origin,
    )
    assert row["origin"] == origin
    terminal = _terminal_events(state, run["id"])[0]
    assert terminal[1] in {"RUN_COMPLETED", "RUN_FAILED"}
    assert terminal[2]["origin"] == origin
    assert terminal[2]["cwd"] == str(execution_cwd)
    assert terminal[2]["receipt"] == receipt_key
    assert receipt_body["stdout"]["sha256"] in json.dumps(receipt_body)

    result = ReceiptMemory(state, memory).drain()
    assert result["processed"] == 1 and result["error"] is None
    records = memory.timeline(str(hook_cwd), "child-thread")
    assert len(records) == 1
    assert records[0]["event_id"] == "engine-run:" + run["id"]
    raw = memory.retrieve(str(hook_cwd), [records[0]["record_hash"]])[0]["raw"]
    metadata = json.loads(raw)
    assert metadata["schema"] == "helix.memory.execution.v1"
    encoded = raw.decode()
    assert receipt_key in encoded
    assert receipt_body["stdout"]["sha256"] in encoded
    assert receipt_body["stderr"]["sha256"] in encoded
    assert stdout not in raw
    assert stderr not in raw
    assert len(raw) < len(stdout) + len(stderr)


def test_parallel_drains_are_serialized_without_duplicate_records(tmp_path):
    state, store, memory = _components(tmp_path)
    for index in range(8):
        _finish(state, store, tmp_path, name=str(index), stdout=f"row-{index}\n".encode())
    lifecycles = [
        ReceiptMemory(State(tmp_path), Memory(Store(tmp_path / "evidence"))),
        ReceiptMemory(State(tmp_path), Memory(Store(tmp_path / "evidence"))),
    ]
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def drain(lifecycle):
        try:
            barrier.wait(timeout=5)
            results.append(lifecycle.drain(limit=16))
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=drain, args=(lifecycle,)) for lifecycle in lifecycles]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(results) == 2
    for result in results:
        _assert_drain_shape(result)
        assert result["error"] is None
    assert sum(result["processed"] for result in results) == 8
    recovered = Memory(Store(tmp_path / "evidence"))
    records = recovered.timeline(str(tmp_path), "engine-local", limit=20)
    assert len(records) == 8
    assert len({record["event_id"] for record in records}) == 8


def test_runtime_auto_drain_is_best_effort_and_uses_direct_local_attribution(tmp_path, monkeypatch):
    from helixengine.runtime import Runtime

    runtime = Runtime(tmp_path)
    try:
        first = runtime.run(
            [sys.executable, "-c", "import sys;sys.stdout.write('first-command')"],
            tmp_path,
        )
        assert first["exit_code"] == 0
        assert len(runtime.memory.timeline(str(tmp_path), "engine-local")) == 1

        original_record = runtime.memory.record

        def unavailable(*args, **kwargs):
            raise RuntimeError("injected memory failure")

        monkeypatch.setattr(runtime.memory, "record", unavailable)
        result = runtime.run(
            [sys.executable, "-c", "import sys;sys.stdout.write('command-ran')"],
            tmp_path,
        )
        assert result["exit_code"] == 0
        assert result["run"]["state"] == "COMPLETED"
        monkeypatch.setattr(runtime.memory, "record", original_record)
        recovered = ReceiptMemory(runtime.state, runtime.memory).drain()
        assert recovered["processed"] == 1
        assert recovered["error"] is None
        records = runtime.memory.timeline(str(tmp_path), "engine-local")
        assert len(records) == 2
    finally:
        runtime.close()
