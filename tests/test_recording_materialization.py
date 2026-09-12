"""No inference: real capture, ledger, controller, and artifact boundary."""
import json
import os
import stat

import pytest

from helixengine import native_transitions as native, transition_gate as gate
from helixengine.core.completion_ledger import EMPTY
from helixengine.core.evidence import Store
from helixengine.core.workflow_memory import Memory
from helixengine.prompt_memory import capture_prompt


pytestmark = pytest.mark.skipif(os.name != "posix", reason="Bound artifact publication requires POSIX locking/dirfd; other platforms fail closed")


def row(kind, **payload):
    return json.dumps(dict(type=kind, payload=payload)).encode() + b"\n"


def context(turn):
    return row("turn_context", turn_id=turn, root_turn_id=turn, effort="high")


def setup(tmp_path):
    tmp_path = tmp_path.resolve()
    memory = Memory(Store(tmp_path / "evidence"))
    target = tmp_path / "observations.jsonl"
    target.write_bytes(b"existing\n")
    grant = dict(
        schema=gate.GRANT_SCHEMA, project=str(tmp_path), thread_id="root", epoch=1,
        authorization_ref=memory.store.put(b"Caller grants exclusive exact append to named artifact.")["sha256"],
        unresolved_obligations=[], dependencies=[],
        recording=dict(max_events=3, max_payload_bytes=4096, notification="Recorded."),
        materialization=dict(path=str(target), initial_sha256=memory.store.put(b"existing\n")["sha256"],
                             initial_bytes=9, format="exact-prompt-append-v1", write_authority="exclusive"),
    )
    transcript = tmp_path / "rollout.jsonl"
    transcript.write_bytes(row("session_meta", id="root") + context("baseline") +
                          row("event_msg", type="task_complete", turn_id="baseline", last_agent_message="Ready."))
    return memory, target, grant, transcript


def event(memory, transcript, *, sequence=1, prior=False, payload="İris\u00a0東京 Ϟ-17 9007199254740993"):
    turn = f"record-{sequence}"
    if prior:
        with transcript.open("ab") as stream:
            stream.write(row("event_msg", type="task_complete", turn_id=f"record-{sequence-1}", last_agent_message=None))
    with transcript.open("ab") as stream:
        stream.write(row("event_msg", type="task_started", turn_id=turn) + context(turn))
    prompt = json.dumps(dict(schema="helix.observation.v1", epoch=1, sequence=sequence, payload=payload), ensure_ascii=False)
    native_event = dict(hook_event_name="UserPromptSubmit", session_id="root", turn_id=turn,
                        cwd=str(transcript.parent), transcript_path=str(transcript), prompt=prompt)
    return native_event, capture_prompt(memory, str(transcript.parent), native_event)


def test_native_stops_only_after_exact_artifact_and_ordinary_request_resumes(tmp_path):
    memory, target, grant, transcript = setup(tmp_path)
    ref = gate.arm(memory, grant)
    data = tmp_path / "data"
    native.activate(data, memory, ref, transcript_path=str(transcript))
    expected = b"existing\n"
    for sequence in (1, 2):
        request, capture = event(memory, transcript, sequence=sequence, prior=sequence > 1)
        expected += request["prompt"].encode() + b"\n"
        assert native.dispatch(data, memory, capture, native_event=request)["continue"] is False
        assert target.read_bytes() == expected
        head = native.status(data, "root")["expected_head"]
        # Explicit exact-byte reconciliation cannot append an event twice.
        gate.materialize_recording(memory, ref, head)
        assert target.read_bytes() == expected
    request, _ = event(memory, transcript, sequence=3, prior=True)
    request["prompt"] = "Now interpret the records in a normal answer."
    capture = capture_prompt(memory, str(transcript.parent), request)
    assert native.dispatch(data, memory, capture, native_event=request) == {}
    assert target.read_bytes() == expected


@pytest.mark.parametrize("failure", ["stale_file", "after_write", "dependency_change"])
def test_uncertain_artifact_never_certifies_completion(tmp_path, monkeypatch, failure):
    from helixengine import recording_artifact
    memory, target, grant, transcript = setup(tmp_path)
    dep = tmp_path / "policy.txt"
    dep.write_bytes(b"policy")
    grant["dependencies"] = [dict(path=str(dep), sha256=memory.store.put(b"policy")["sha256"])]
    ref = gate.arm(memory, grant)
    data = tmp_path / "data"
    native.activate(data, memory, ref, transcript_path=str(transcript))
    request, capture = event(memory, transcript)
    publish = recording_artifact.publish
    def altered(*args):
        result = publish(*args)
        if failure == "after_write":
            raise OSError("Simulated failure after atomic file publication")
        dep.write_bytes(b"changed")
        return result
    if failure == "stale_file":
        target.write_bytes(b"another writer")
    else:
        monkeypatch.setattr(recording_artifact, "publish", altered)
    assert native.dispatch(data, memory, capture, native_event=request) == {}
    status = native.status(data, "root")
    assert status["active"] is False and status["expected_head"] == EMPTY
    warning = native.reentry_context(data, "root")["hookSpecificOutput"]["additionalContext"]
    assert "repeating any append" in warning
    after = target.read_bytes()
    assert after == (b"another writer" if failure == "stale_file" else b"existing\n" + request["prompt"].encode() + b"\n")
    # Restart/delivery retry cannot secretly replay uncertain effects.
    assert native.dispatch(data, Memory(Store(tmp_path / "evidence")), capture, native_event=request) == {}
    assert target.read_bytes() == after


@pytest.mark.parametrize("mutation", ["authority", "scope", "missing", "initial", "steps", "pending", "dependency"])
def test_bad_materialization_contract_rejected_at_arm(tmp_path, mutation):
    memory, target, grant, _ = setup(tmp_path)
    if mutation == "authority":
        grant["materialization"]["write_authority"] = "assumed"
    elif mutation == "scope":
        grant["materialization"]["path"] = str(tmp_path.parent / "other")
    elif mutation == "missing":
        target.unlink()
    elif mutation == "initial":
        target.write_bytes(b"different")
    elif mutation == "steps":
        grant.pop("recording")
        grant["steps"] = []
    elif mutation == "pending":
        grant["unresolved_obligations"] = ["Unresolved output format"]
    else:
        grant["dependencies"] = [dict(path=str(target), sha256=grant["materialization"]["initial_sha256"])]
    with pytest.raises((ValueError, OSError)):
        gate.arm(memory, grant)


def test_recovered_matching_file_requires_successful_file_fsync(tmp_path, monkeypatch):
    from helixengine import recording_artifact
    memory, target, grant, transcript = setup(tmp_path)
    ref = gate.arm(memory, grant)
    data = tmp_path / "data"
    native.activate(data, memory, ref, transcript_path=str(transcript))
    request, capture = event(memory, transcript)
    after = b"existing\n" + request["prompt"].encode() + b"\n"
    # A caller recovery write can match the desired bytes without proving
    # durability. Directory fsync alone must not authorize suppression.
    target.write_bytes(after)
    original = recording_artifact.os.fsync
    identity = target.stat()
    attempts = []
    def fail_file(fd):
        current = os.fstat(fd)
        if stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
            attempts.append(fd)
            raise OSError("Injected file fsync failure")
        return original(fd)
    monkeypatch.setattr(recording_artifact.os, "fsync", fail_file)
    assert native.dispatch(data, memory, capture, native_event=request) == {}
    assert attempts, "Failure must come from the materialized target fsync"
    assert native.status(data, "root")["active"] is False
    assert target.read_bytes() == after
