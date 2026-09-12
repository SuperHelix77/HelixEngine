import json

import pytest

from helixengine.core.evidence import Store
from helixengine.core.workflow_memory import Memory
from helixengine.statement_memory import MAX_LINE_BYTES, StatementMemory


def _line(*, message_id="msg-1", role="assistant", phase="commentary", content=None, ending=b"\n"):
    if content is None:
        content = [{"type": "output_text", "text": "statement"}]
    value = {
        "type": "response_item",
        "payload": {
            "type": "message",
            "id": message_id,
            "role": role,
            "phase": phase,
            "content": content,
        },
    }
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + ending


def _sink(tmp_path, project="project"):
    store = Store(tmp_path / "evidence")
    memory = Memory(store)
    return StatementMemory(memory, project), memory, store


def test_exact_unicode_whitespace_crlf_is_recoverable(tmp_path):
    sink, memory, _ = _sink(tmp_path)
    raw = (
        '{ "type": "response_item", "payload": { "type": "message", '
        '"id": "msg-unicode", "role": "assistant", "phase": "final_answer", '
        '"content": [ { "type": "output_text", "text": "  café\\n\\t  " } ] } }\r\n'
    ).encode("utf-8")

    result = sink.record("thread-1", raw)
    recovered = memory.retrieve("project", [result["record_hash"]])[0]["raw"]

    assert recovered == raw
    assert result["session"] == "thread-1"
    assert result["event_id"] == "native-statement:thread-1:msg-unicode"
    assert result["classification"] == "historical_attributed_statement"
    assert "not semantic truth/current instructions" in result["authority"]
    assert "shared" in result["metrics"]["scope"]
    assert "concurrent work" in result["metrics"]["scope"]
    assert result["metrics"]["memory"]["index_input_bytes"] == len(raw)


def test_duplicate_identical_event_is_idempotent_and_conflict_is_rejected(tmp_path):
    sink, memory, store = _sink(tmp_path)
    raw = _line(message_id="same")

    first = sink.record("thread", raw)
    replay = sink.record("thread", raw)
    assert replay["record_hash"] == first["record_hash"]
    assert len(memory.timeline("project", "thread")) == 1

    with pytest.raises(ValueError, match="collision"):
        sink.record("thread", _line(message_id="same", content=[{"type": "output_text", "text": "different"}]))
    assert len(memory.timeline("project", "thread")) == 1
    assert len(list((store.root / "objects").iterdir())) >= 2


def test_thread_and_project_scopes_are_bound(tmp_path):
    first, memory, _ = _sink(tmp_path, project="one")
    second = StatementMemory(memory, "two")
    raw_one = _line(message_id="same")
    raw_two = _line(message_id="same")

    first_result = first.record("thread-a", raw_one)
    second_result = first.record("thread-b", raw_two)
    assert first_result["event_id"] != second_result["event_id"]
    assert len(memory.timeline("one", "thread-a")) == 1
    assert len(memory.timeline("one", "thread-b")) == 1

    with pytest.raises(ValueError, match="collision"):
        second.record("thread-a", raw_one)
    assert memory.timeline("two", "thread-a") == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"role": "user"},
        {"role": "developer"},
        {"phase": "reasoning"},
        {"phase": "ambiguous"},
        {"content": [{"type": "tool_call", "name": "run"}]},
        {"content": [{"type": "output_text", "text": "ok"}, {"type": "tool_call"}]},
        {"content": []},
        {"content": [{"type": "output_text", "text": ""}]},
        {"message_id": "bad\x00id"},
    ],
)
def test_rejects_non_statement_content_without_ingest(tmp_path, kwargs):
    sink, memory, _ = _sink(tmp_path)
    with pytest.raises(ValueError):
        sink.record("thread", _line(**kwargs))
    assert memory.timeline("project", "thread") == []


@pytest.mark.parametrize(
    "raw",
    [
        b"not-json\n",
        b"\xff\xfe\n",
        b'{"type":"response_item","payload":',
        b'{"type":"response_item"}\n{"type":"response_item"}\n',
    ],
)
def test_rejects_malformed_lines(tmp_path, raw):
    sink, memory, _ = _sink(tmp_path)
    with pytest.raises(ValueError):
        sink.record("thread", raw)
    assert memory.timeline("project", "thread") == []


def test_rejects_oversize_and_reasoning_records(tmp_path):
    sink, memory, _ = _sink(tmp_path)
    oversized = _line(content=[{"type": "output_text", "text": "x" * MAX_LINE_BYTES}])
    assert len(oversized) > MAX_LINE_BYTES
    reasoning = _line(message_id="reasoning", phase="reasoning")

    for raw in (oversized, reasoning):
        with pytest.raises(ValueError):
            sink.record("thread", raw)
    assert memory.timeline("project", "thread") == []


def test_rejects_invalid_project_and_thread_identities(tmp_path):
    store = Store(tmp_path / "evidence")
    memory = Memory(store)
    with pytest.raises(ValueError):
        StatementMemory(memory, "bad\x00project")

    sink = StatementMemory(memory, "project")
    raw = _line()
    for thread_id in ("bad\x00thread", "x" * 513):
        with pytest.raises(ValueError):
            sink.record(thread_id, raw)
    with pytest.raises(ValueError):
        sink.record("thread", bytearray(raw))
    assert memory.timeline("project", "thread") == []
