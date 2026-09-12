import hashlib
import json

import pytest

from helixengine import native_transitions as transitions
from helixengine.core.completion_ledger import CompletionLedger, EMPTY
from helixengine.core.evidence import Store
from helixengine.core.workflow_memory import Memory
from helixengine.native_continuity import checkpoint
from helixengine.state import State


def row(kind, **payload):
    return json.dumps({"type": kind, "payload": payload}).encode() + b"\n"


def context(turn, effort="high"):
    return row(
        "turn_context",
        turn_id=turn,
        root_turn_id=turn,
        model="test-model",
        effort=effort,
    )


def start(turn):
    return row("event_msg", type="task_started", turn_id=turn)


def native_event(path, turn="one"):
    return {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "root",
        "turn_id": turn,
        "transcript_path": str(path),
        "cwd": "project",
        "prompt": "first",
    }


def baseline(tmp_path):
    path = tmp_path / "native.jsonl"
    path.write_bytes(
        row("session_meta", id="root")
        + context("semantic-0")
        + row(
            "event_msg",
            type="task_complete",
            turn_id="semantic-0",
            last_agent_message="Ready.",
        )
    )
    return path


def memory(tmp_path):
    return Memory(Store(tmp_path / "evidence"))


def grant(memory, *, project="project", thread_id="root", epoch=1):
    source = {
        "project": project,
        "thread_id": thread_id,
        "epoch": epoch,
        "authorization_ref": "authorization-1",
        "steps": [{"operation": "record"}],
    }
    return memory.store.put(
        json.dumps(source, ensure_ascii=False, separators=(",", ":")).encode()
    )["sha256"]


def capture(*, project="project", thread_id="root", captured=True, event_id="event-1"):
    return {
        "schema": "helix.prompt.capture.receipt.v1",
        "captured": captured,
        "coverage": captured,
        "project": project,
        "thread_id": thread_id,
        "event_id": event_id,
        "record_hash": "b" * 64,
        "source_hash": "c" * 64,
        "bytes": 12,
        "session_id": thread_id,
        "agent_id": None,
        "turn_id": "one",
        "prompt_bytes": 5,
        "prompt_sha256": hashlib.sha256(b"first").hexdigest(),
    }


class Gate:
    def __init__(self, *, state="RECORDED", commit_then_fail=False):
        self.state = state
        self.commit_then_fail = commit_then_fail
        self.calls = []
        self.committed_head = None

    def transition(self, memory, grant_hash, receipt, expected_head):
        self.calls.append((grant_hash, receipt, expected_head))
        if self.commit_then_fail:
            self.committed_head = CompletionLedger(memory).ingest(
                grant_hash,
                receipt["event_id"],
                b"committed-before-controller-failure",
                expected_head=expected_head,
            )["head"]
            raise RuntimeError("state anchor is now uncertain")
        head = hashlib.sha256(
            (expected_head + receipt["event_id"] + self.state).encode()
        ).hexdigest()
        result = {
            "state": self.state,
            "head": head,
            "replayed": False,
            "reason": "fixture",
        }
        if self.state == "RECORDED":
            result["receipt"] = hashlib.sha256((head + "receipt").encode()).hexdigest()
        return result


@pytest.fixture
def native_gate(monkeypatch):
    gate = Gate()
    monkeypatch.setattr(transitions, "transition_gate", gate)
    return gate


def activate(tmp_path, memory_obj, path, grant_hash):
    return transitions.activate(
        tmp_path / "data",
        memory_obj,
        grant_hash,
        transcript_path=str(path),
    )


def test_no_binding_is_native_and_does_not_call_gate(tmp_path, native_gate):
    memory_obj = memory(tmp_path)
    path = baseline(tmp_path)
    assert transitions.dispatch(
        tmp_path / "data",
        memory_obj,
        capture(),
        native_event=native_event(path),
    ) == {}
    assert native_gate.calls == []


def test_success_advances_anchor_and_writes_recoverable_outbox(tmp_path, native_gate):
    memory_obj = memory(tmp_path)
    path = baseline(tmp_path)
    grant_hash = grant(memory_obj)
    activated = activate(tmp_path, memory_obj, path, grant_hash)
    assert activated["expected_head"] == EMPTY
    with path.open("ab") as stream:
        stream.write(start("one") + context("one"))

    receipt = capture()
    response = transitions.dispatch(
        tmp_path / "data",
        memory_obj,
        receipt,
        native_event=native_event(path),
    )
    assert response["continue"] is False
    assert response["stopReason"] == response["systemMessage"]
    assert "RECORDED" in response["stopReason"]
    assert "event-1" not in response["stopReason"]
    assert native_gate.calls[0][2] == EMPTY

    status = transitions.status(tmp_path / "data", "root")
    assert status["active"] is True and status["expected_head"] != EMPTY
    assert status["continuity_anchor"]["pending_turn"] == "one"
    assert status["continuity_anchor"]["bytes_read"] == path.stat().st_size
    with State(tmp_path / "data").db() as db:
        outbox = db.execute(
            "SELECT head, notification_state, capture_refs FROM native_transition_outbox"
        ).fetchone()
        events = [
            row["kind"]
            for row in db.execute("SELECT kind FROM events ORDER BY id")
        ]
        event_body = db.execute(
            "SELECT body FROM events WHERE kind='CODEX_TRANSITION_RECORDED'"
        ).fetchone()["body"]
    assert outbox["head"] == status["expected_head"]
    assert outbox["notification_state"] == "PENDING"
    assert "record_hash" in json.loads(outbox["capture_refs"])
    assert "CODEX_TRANSITION_RECORDED" in events
    assert json.loads(event_body)["native_continuity_bytes_read"] == path.stat().st_size


def test_duplicate_activation_preserves_head(tmp_path, native_gate):
    memory_obj = memory(tmp_path)
    path = baseline(tmp_path)
    grant_hash = grant(memory_obj)
    first = activate(tmp_path, memory_obj, path, grant_hash)
    second = activate(tmp_path, memory_obj, path, grant_hash)
    assert first["expected_head"] == second["expected_head"] == EMPTY
    assert second["continuity_anchor"] == checkpoint(path, "root")


def test_semantic_required_disables_and_next_event_is_native(tmp_path, monkeypatch):
    memory_obj = memory(tmp_path)
    path = baseline(tmp_path)
    grant_hash = grant(memory_obj)
    activate(tmp_path, memory_obj, path, grant_hash)
    with path.open("ab") as stream:
        stream.write(start("one") + context("one"))
    gate = Gate(state="SEMANTIC_REQUIRED")
    monkeypatch.setattr(transitions, "transition_gate", gate)
    result = transitions.dispatch(
        tmp_path / "data", memory_obj, capture(), native_event=native_event(path)
    )
    assert result == {}
    status = transitions.status(tmp_path / "data", "root")
    assert status["active"] is False and status["recovery_required"] is True
    assert status["continuity_anchor"]["pending_turn"] == "one"
    assert transitions.dispatch(
        tmp_path / "data", memory_obj, capture(), native_event=native_event(path)
    ) == {}
    assert len(gate.calls) == 1


def test_captured_false_disables_without_gate_or_continuity_transition(tmp_path, native_gate):
    memory_obj = memory(tmp_path)
    path = baseline(tmp_path)
    grant_hash = grant(memory_obj)
    activate(tmp_path, memory_obj, path, grant_hash)
    with path.open("ab") as stream:
        stream.write(start("one") + context("one"))
    assert transitions.dispatch(
        tmp_path / "data",
        memory_obj,
        capture(captured=False),
        native_event=native_event(path),
    ) == {}
    assert transitions.status(tmp_path / "data", "root")["active"] is False
    assert native_gate.calls == []


def test_off_revision_disables_old_lease_and_on_does_not_revive_it(tmp_path, native_gate):
    memory_obj = memory(tmp_path)
    path = baseline(tmp_path)
    grant_hash = grant(memory_obj)
    activate(tmp_path, memory_obj, path, grant_hash)
    state = State(tmp_path / "data")
    current = state.settings()
    state.switch(False, current["revision"])
    state.switch(True, current["revision"] + 1)
    with path.open("ab") as stream:
        stream.write(start("one") + context("one"))
    assert transitions.dispatch(
        tmp_path / "data", memory_obj, capture(), native_event=native_event(path)
    ) == {}
    status = transitions.status(tmp_path / "data", "root")
    assert status["active"] is False and status["settings_revision"] == 0
    assert native_gate.calls == []


def test_completion_commit_then_controller_failure_quarantines_stale_head(tmp_path, monkeypatch):
    memory_obj = memory(tmp_path)
    path = baseline(tmp_path)
    grant_hash = grant(memory_obj)
    activate(tmp_path, memory_obj, path, grant_hash)
    with path.open("ab") as stream:
        stream.write(start("one") + context("one"))
    gate = Gate(commit_then_fail=True)
    monkeypatch.setattr(transitions, "transition_gate", gate)
    receipt = capture()
    assert transitions.dispatch(
        tmp_path / "data", memory_obj, receipt, native_event=native_event(path)
    ) == {}
    status = transitions.status(tmp_path / "data", "root")
    assert status["active"] is False
    assert status["expected_head"] == EMPTY
    assert status["recovery_required"] is True
    assert gate.committed_head != EMPTY
    assert transitions.dispatch(
        tmp_path / "data", memory_obj, receipt, native_event=native_event(path)
    ) == {}
    assert len(gate.calls) == 1


def test_project_mismatch_keeps_binding_but_never_calls_gate(tmp_path, native_gate):
    memory_obj = memory(tmp_path)
    path = baseline(tmp_path)
    grant_hash = grant(memory_obj)
    activate(tmp_path, memory_obj, path, grant_hash)
    with path.open("ab") as stream:
        stream.write(start("one") + context("one"))
    assert transitions.dispatch(
        tmp_path / "data",
        memory_obj,
        capture(project="other"),
        native_event=native_event(path),
    ) == {}
    assert transitions.status(tmp_path / "data", "root")["active"] is True
    assert native_gate.calls == []


def test_active_replacement_rejected_and_missing_snapshot_disables(tmp_path, native_gate):
    memory_obj = memory(tmp_path)
    path = baseline(tmp_path)
    first = grant(memory_obj, project="project")
    second = grant(memory_obj, project="other")
    activate(tmp_path, memory_obj, path, first)
    with pytest.raises(ValueError, match="different grant"):
        activate(tmp_path, memory_obj, path, second)
    with path.open("ab") as stream:
        stream.write(start("one") + context("one"))
    assert transitions.dispatch(tmp_path / "data", memory_obj, capture()) == {}
    assert transitions.status(tmp_path / "data", "root")["active"] is False
    assert native_gate.calls == []
