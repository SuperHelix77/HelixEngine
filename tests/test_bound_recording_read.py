"""Real controller/history/artifact checks; no model invocation."""
import os
from pathlib import Path
import runpy

import pytest

from helixengine import native_transitions as native, transition_gate as gate
from helixengine.core.completion_ledger import EMPTY
from helixengine.core.evidence import Store
from helixengine.core.workflow_memory import Memory
from helixengine.prompt_memory import capture_prompt
from helixengine.state import State


pytestmark = pytest.mark.skipif(os.name != "posix", reason="Bound artifact needs POSIX locking")
fixtures = runpy.run_path(str(Path(__file__).with_name("test_recording_materialization.py")))


def recorded(tmp_path, *, dependency=False):
    memory, target, grant, transcript = fixtures["setup"](tmp_path)
    if dependency:
        dep = tmp_path / "policy.txt"
        dep.write_bytes(b"policy")
        grant["dependencies"] = [{"path": str(dep), "sha256": memory.store.put(b"policy")["sha256"]}]
    ref = gate.arm(memory, grant)
    data = tmp_path / "data"
    native.activate(data, memory, ref, transcript_path=str(transcript))
    request, capture = fixtures["event"](memory, transcript)
    assert native.dispatch(data, memory, capture, native_event=request)["continue"] is False
    expected = b"existing\n" + request["prompt"].encode() + b"\n"
    return memory, target, ref, data, transcript, expected


def test_read_returns_exact_bound_snapshot_without_publication(tmp_path, monkeypatch):
    from helixengine import recording_artifact
    memory, target, ref, data, _, expected = recorded(tmp_path)
    before = native.status(data, "root")
    def forbidden(*args, **kwargs):
        pytest.fail("A recovery read must not publish or repair")
    monkeypatch.setattr(recording_artifact, "publish", forbidden)
    payload, receipt = native.read_recording(data, memory, "root")
    assert payload == expected == target.read_bytes()
    assert receipt["grant_hash"] == ref
    assert receipt["transition_head"] == before["expected_head"]
    assert receipt["thread_id"] == "root" and receipt["epoch"] == 1
    assert receipt["semantic_approval"] is False and receipt["recorded_events"] == 1
    assert receipt["store_io"]["object_bytes_read"] > 0
    assert native.status(data, "root") == before


def test_semantic_reentry_off_and_restart_preserve_historical_read(tmp_path):
    memory, target, _, data, transcript, expected = recorded(tmp_path)
    turn = "semantic"
    with transcript.open("ab") as stream:
        stream.write(fixtures["row"]("event_msg", type="task_complete", turn_id="record-1", last_agent_message=None))
        stream.write(fixtures["row"]("event_msg", type="task_started", turn_id=turn) + fixtures["context"](turn))
    request = dict(hook_event_name="UserPromptSubmit", session_id="root", turn_id=turn,
                   cwd=str(tmp_path), transcript_path=str(transcript),
                   prompt="Now interpret the earlier history.")
    capture = capture_prompt(memory, str(tmp_path), request)
    assert native.dispatch(data, memory, capture, native_event=request) == {}
    assert native.status(data, "root")["last_failure"] == "semantic_required"
    settings = State(data)
    settings.switch(False, settings.settings()["revision"])
    fresh = Memory(Store(tmp_path / "evidence"))
    assert native.read_recording(data, fresh, "root")[0] == expected
    assert target.read_bytes() == expected


@pytest.mark.parametrize("failure", ["stale_file", "wrong_head", "in_flight", "uncertain", "wrong_thread"])
def test_failed_read_does_not_repair_or_advance_state(tmp_path, failure):
    memory, target, _, data, _, _ = recorded(tmp_path)
    if failure == "stale_file":
        target.write_bytes(b"changed file")
    elif failure in {"wrong_head", "in_flight", "uncertain"}:
        values = {"wrong_head": ("expected_head", EMPTY), "in_flight": ("in_flight", 1),
                  "uncertain": ("blocked", 1)}
        column, value = values[failure]
        with State(data).db() as db:
            db.execute(f"UPDATE native_transition_bindings SET {column}=? WHERE thread_id='root'", (value,))
    before = native.status(data, "root")
    file_before = target.read_bytes()
    with pytest.raises((ValueError, RuntimeError)):
        native.read_recording(data, memory, "other" if failure == "wrong_thread" else "root")
    assert target.read_bytes() == file_before
    assert native.status(data, "root") == before


def test_changed_dependency_during_read_rejects_snapshot(tmp_path, monkeypatch):
    from helixengine import recording_artifact
    memory, target, _, data, _, expected = recorded(tmp_path, dependency=True)
    read = recording_artifact.read_verified
    def changed(*args):
        result = read(*args)
        (tmp_path / "policy.txt").write_bytes(b"new policy")
        return result
    monkeypatch.setattr(recording_artifact, "read_verified", changed)
    before = native.status(data, "root")
    with pytest.raises(ValueError, match="dependency changed"):
        native.read_recording(data, memory, "root")
    assert native.status(data, "root") == before and target.read_bytes() == expected


def test_grant_thread_cannot_be_rebound_by_read_argument(tmp_path):
    memory, _, ref, data, _, _ = recorded(tmp_path)
    head = native.status(data, "root")["expected_head"]
    with pytest.raises(ValueError, match="thread mismatch"):
        gate.read_recording(memory, ref, head, thread_id="different")


@pytest.mark.parametrize("which", ["grant", "initial"])
def test_corrupt_cold_evidence_cannot_be_replaced_by_matching_live_file(tmp_path, which):
    memory, target, ref, data, _, expected = recorded(tmp_path)
    grant = gate._read_grant(memory, ref)
    corrupt = ref if which == "grant" else grant["materialization"]["initial_sha256"]
    (memory.store.root / "objects" / corrupt).write_bytes(b"corrupted cold evidence")
    before = native.status(data, "root")
    with pytest.raises(ValueError):
        native.read_recording(data, memory, "root")
    assert native.status(data, "root") == before and target.read_bytes() == expected
