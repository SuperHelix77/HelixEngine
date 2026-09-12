import hashlib
import json

from helixengine.core.evidence import Store
from helixengine.core.workflow_memory import Memory
from helixengine.prompt_memory import MAX_PROMPT_BYTES, capture_prompt


def _event(prompt="hello", **overrides):
    event = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "root-session",
        "turn_id": "turn-1",
        "prompt": prompt,
    }
    event.update(overrides)
    return event


def _memory(tmp_path):
    return Memory(Store(tmp_path / "evidence"))


def _archived(memory, receipt):
    raw = memory.retrieve("project", [receipt["record_hash"]])[0]["raw"]
    return json.loads(raw), raw


def test_exact_prompt_recovery_survives_restart(tmp_path):
    prompt = "  café\u00a0\n\t終わり  "
    memory = _memory(tmp_path)
    first = capture_prompt(memory, "project", _event(prompt))

    assert first["coverage"] is True and first["captured"] is True
    archived, raw = _archived(memory, first)
    assert archived["prompt"] == prompt
    assert archived["prompt"].encode("utf-8") == prompt.encode("utf-8")
    assert archived["prompt_sha256"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert archived["session_id"] == "root-session"
    assert archived["turn_id"] == "turn-1"

    restarted = _memory(tmp_path)
    recovered = restarted.retrieve("project", [first["record_hash"]])[0]["raw"]
    assert recovered == raw
    assert json.loads(recovered)["prompt"] == prompt


def test_duplicate_identical_prompt_is_a_no_op(tmp_path):
    memory = _memory(tmp_path)
    event = _event("same")
    first = capture_prompt(memory, "project", event)
    second = capture_prompt(memory, "project", event)

    assert second["coverage"] is True and second["captured"] is True
    assert second["record_hash"] == first["record_hash"]
    assert second["source_hash"] == first["source_hash"]
    assert len(memory.timeline("project", "root-session")) == 1


def test_changed_prompt_under_native_identity_is_incomplete_collision(tmp_path):
    memory = _memory(tmp_path)
    capture_prompt(memory, "project", _event("first"))
    result = capture_prompt(memory, "project", _event("changed"))

    assert result["coverage"] is False
    assert result["captured"] is False
    assert result["status"] == "capture_incomplete"
    assert result["error"] == "identity_collision"
    assert len(memory.timeline("project", "root-session")) == 1


def test_missing_identity_is_explicitly_incomplete(tmp_path):
    memory = _memory(tmp_path)
    result = capture_prompt(memory, "project", _event(session_id=None))

    assert result["coverage"] is False
    assert result["captured"] is False
    assert result["error"] == "missing_identity"
    assert memory.timeline("project", "root-session") == []


def test_invalid_surrogate_prompt_is_not_archived(tmp_path):
    memory = _memory(tmp_path)
    result = capture_prompt(memory, "project", _event("bad\ud800"))

    assert result["coverage"] is False
    assert result["captured"] is False
    assert result["error"] == "invalid_prompt_encoding"
    assert memory.timeline("project", "root-session") == []


def test_unicode_whitespace_and_child_attribution_are_preserved(tmp_path):
    memory = _memory(tmp_path)
    prompt = "\u2003lead\u00a0middle\n\tend\u3000"
    result = capture_prompt(
        memory,
        "project",
        _event(prompt, session_id="parent-session", agent_id="child-agent", turn_id="child-turn"),
    )

    archived, _ = _archived(memory, result)
    assert archived["prompt"] == prompt
    assert archived["root_session_id"] == "parent-session"
    assert archived["session_id"] == "parent-session"
    assert archived["agent_id"] == "child-agent"
    assert archived["thread_id"] == "child-agent"
    assert archived["turn_id"] == "child-turn"
    assert len(memory.timeline("project", "child-agent")) == 1


def test_oversized_prompt_is_not_archived(tmp_path):
    memory = _memory(tmp_path)
    result = capture_prompt(memory, "project", _event("x" * (MAX_PROMPT_BYTES + 1)))

    assert result["coverage"] is False
    assert result["captured"] is False
    assert result["error"] == "oversized_prompt"
    assert memory.timeline("project", "root-session") == []


def test_storage_failure_keeps_capture_incomplete(tmp_path):
    memory = _memory(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("injected storage failure")

    memory.record = fail
    result = capture_prompt(memory, "project", _event("retained by native path"))

    assert result["coverage"] is False
    assert result["captured"] is False
    assert result["status"] == "capture_incomplete"
    assert result["error"] == "storage_failure"
