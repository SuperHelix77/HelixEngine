import json
import os
from pathlib import Path

import pytest

from helixengine.chat_observer import ChatObserver, MAX_SCAN_BYTES, ObserverError


THREAD = "thread-target"


def append_record(path, record, *, newline=True):
    raw = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with Path(path).open("ab") as stream:
        stream.write(raw)
        if newline:
            stream.write(b"\n")


def context(turn_id="turn-1", *, thread_id=THREAD, model="gpt-fixture", effort="high"):
    payload = {"turn_id": turn_id, "model": model, "effort": effort}
    if thread_id is not None:
        payload["thread_id"] = thread_id
    return {"timestamp": "2026-09-12T10:00:00Z", "type": "turn_context", "payload": payload}


def usage_record(
    response_id="response-1",
    *,
    thread_id=THREAD,
    turn_id="turn-1",
    input_tokens=100,
    cached_input_tokens=20,
    cache_write_input_tokens=5,
    output_tokens=12,
    reasoning_output_tokens=3,
    total_tokens=112,
    timestamp="2026-09-12T10:00:01Z",
):
    usage = {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "cache_write_input_tokens": cache_write_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_output_tokens,
        "total_tokens": total_tokens,
    }
    return {
        "timestamp": timestamp,
        "type": "token_usage_record",
        "payload": {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "response_id": response_id,
            "usage": usage,
            # Native rollouts also carry cumulative counters.  The observer
            # must not use these fields for aggregation.
            "turn_token_usage": {"input_tokens": 999999, "output_tokens": 999999},
            "thread_token_usage": {"input_tokens": 888888, "output_tokens": 888888},
        },
    }


def test_first_attach_is_eof_partial_writes_are_incremental_and_restart_is_durable(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    append_record(rollout, usage_record("historical"))
    observer = ChatObserver(tmp_path / "observer", rollout, THREAD)

    initial = observer.snapshot()
    assert initial["response_count"] == 0
    assert initial["usage"]["total_tokens"] == 0
    assert initial["cursor"] == rollout.stat().st_size
    assert initial["connected"] is True
    assert initial["bytes_read"] == min(64, initial["cursor"]) + 1
    assert initial["start_cursor"] == initial["cursor"]

    record = usage_record("response-1")
    raw = json.dumps(record, separators=(",", ":")).encode()
    with rollout.open("ab") as stream:
        stream.write(raw[:-1])
    observer.scan()
    assert observer.snapshot()["response_count"] == 0

    with rollout.open("ab") as stream:
        stream.write(raw[-1:] + b"\n")
    scanned = observer.scan()
    assert scanned["response_count"] == 1
    assert scanned["usage"] == {
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "cache_write_input_tokens": 5,
        "output_tokens": 12,
        "reasoning_output_tokens": 3,
        "total_tokens": 112,
    }

    restarted = ChatObserver(tmp_path / "observer", rollout, THREAD)
    assert restarted.snapshot()["response_count"] == 1
    assert restarted.snapshot()["usage"]["total_tokens"] == 112


def test_context_model_effort_thread_filter_and_cumulative_event_are_bounded(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    rollout.touch()
    observer = ChatObserver(tmp_path / "observer", rollout, THREAD)
    append_record(rollout, context())
    append_record(rollout, usage_record())
    append_record(rollout, usage_record("other", thread_id="other-thread"))
    append_record(
        rollout,
        {
            "type": "event_msg",
            "payload": {
                "text": "PRIVATE MESSAGE SHOULD NEVER BE RETAINED",
                "usage": {"input_tokens": 1000000, "output_tokens": 1000000},
            },
        },
    )
    snapshot = observer.scan()

    assert snapshot["model"] == "gpt-fixture"
    assert snapshot["effort"] == "high"
    assert snapshot["response_count"] == 1
    assert snapshot["usage"]["input_tokens"] == 100
    assert snapshot["usage"]["output_tokens"] == 12
    assert snapshot["usage"]["reasoning_output_tokens"] == 3
    assert snapshot["usage"]["total_tokens"] == 112
    assert snapshot["recent"] == [
        {
            "timestamp": "2026-09-12T10:00:01Z",
            "response_id": "response-1",
            "model": "gpt-fixture",
            "usage": snapshot["recent"][0]["usage"],
        }
    ]

    append_record(
        rollout,
        {
            "type": "inference",
            "payload": {"reasoning": "PRIVATE REASONING SHOULD NEVER BE RETAINED"},
        },
    )
    observer.scan()
    for stored in (observer.db_path, *observer.db_path.parent.glob(observer.db_path.name + "-*")):
        assert b"PRIVATE" not in stored.read_bytes()


def test_duplicate_response_is_idempotent_and_conflict_is_atomic(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    rollout.touch()
    observer = ChatObserver(tmp_path / "observer", rollout, THREAD)
    append_record(rollout, usage_record())
    observer.scan()
    before = observer.snapshot()

    append_record(rollout, usage_record())
    duplicate = observer.scan()
    assert duplicate["response_count"] == 1
    assert duplicate["cursor"] > before["cursor"]

    conflict_offset = duplicate["cursor"]
    append_record(rollout, usage_record(output_tokens=13, total_tokens=113))
    with pytest.raises(ObserverError, match="conflicting response_id"):
        observer.scan()
    failed = observer.snapshot()
    assert failed["response_count"] == 1
    assert failed["cursor"] == conflict_offset
    assert failed["error"] == "conflicting response_id"


def test_invalid_counters_roll_back_cursor_and_records(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    rollout.touch()
    observer = ChatObserver(tmp_path / "observer", rollout, THREAD)
    start = observer.snapshot()["cursor"]
    append_record(rollout, usage_record("valid"))
    append_record(rollout, usage_record("invalid", cached_input_tokens=101))

    with pytest.raises(ObserverError, match="invalid token usage counters"):
        observer.scan()
    snapshot = observer.snapshot()
    assert snapshot["response_count"] == 0
    assert snapshot["cursor"] == start
    assert snapshot["usage"]["total_tokens"] == 0


def test_malformed_gap_survives_clean_scan_and_restart(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    rollout.touch()
    observer = ChatObserver(tmp_path / "observer", rollout, THREAD)
    rollout.write_bytes(b'{"type":"token_usage_record",BROKEN}\n')
    snapshot = observer.scan()
    assert snapshot["malformed_lines"] == 1
    assert snapshot["coverage_complete"] is False
    assert "malformed" in snapshot["error"]
    append_record(rollout, usage_record())
    restarted = ChatObserver(tmp_path / "observer", rollout, THREAD)
    snapshot = restarted.scan()
    assert snapshot["response_count"] == 1
    assert snapshot["malformed_lines"] == 1
    assert snapshot["coverage_complete"] is False
    assert "malformed" in restarted.scan()["error"]


def test_unavailable_attachment_cannot_claim_coverage_of_skipped_history(tmp_path):
    rollout = tmp_path / "not-yet-created.jsonl"
    observer = ChatObserver(tmp_path / "observer", rollout, THREAD)
    assert observer.snapshot()["coverage_complete"] is False
    append_record(rollout, usage_record("before-readable"))
    snapshot = observer.scan()
    assert snapshot["response_count"] == 0
    assert snapshot["start_cursor"] == rollout.stat().st_size
    assert snapshot["initial_source_missing"] is True
    append_record(rollout, usage_record("after-readable"))
    snapshot = ChatObserver(tmp_path / "observer", rollout, THREAD).scan()
    assert snapshot["response_count"] == 1
    assert snapshot["coverage_complete"] is False
    assert "source unavailable at attachment" in snapshot["error"]


def test_attach_inside_record_skips_suffix_and_keeps_gap_after_restart(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    raw = json.dumps(usage_record("in-progress")).encode()
    rollout.write_bytes(raw[:80])
    observer = ChatObserver(tmp_path / "observer", rollout, THREAD)
    assert observer.snapshot()["start_cursor"] == 80
    with rollout.open("ab") as stream:
        stream.write(raw[80:] + b"\n")
    append_record(rollout, usage_record("next"))
    snapshot = ChatObserver(tmp_path / "observer", rollout, THREAD).scan()
    assert snapshot["response_count"] == 1
    assert snapshot["malformed_lines"] == 0
    assert snapshot["initial_partial_line"] is True
    assert snapshot["coverage_complete"] is False
    assert "attached within a record" in snapshot["error"]


def test_legacy_unknown_boundary_is_not_guessed_on_restart(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    rollout.touch()
    observer = ChatObserver(tmp_path / "observer", rollout, THREAD)
    append_record(rollout, usage_record())
    observer.scan()
    with observer._db() as db:
        # Emulate the nullable migrated value from an older database.
        db.execute("UPDATE observer_state SET start_cursor=NULL")
    snapshot = ChatObserver(tmp_path / "observer", rollout, THREAD).scan()
    assert snapshot["start_cursor"] is None
    assert snapshot["response_count"] == 1
    assert snapshot["coverage_complete"] is False
    assert "attachment boundary unknown" in snapshot["error"]


def test_successful_scans_charge_anchor_reads_including_idle_checks(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    rollout.touch()
    observer = ChatObserver(tmp_path / "observer", rollout, THREAD)
    append_record(rollout, usage_record())
    snapshot = observer.scan()
    assert snapshot["bytes_read"] == rollout.stat().st_size + 64
    idle = observer.scan()
    assert idle["bytes_read"] - snapshot["bytes_read"] == 128


def test_oversized_line_is_skipped_without_unbounded_read_or_text_retention(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    rollout.touch()
    observer = ChatObserver(tmp_path / "observer", rollout, THREAD)
    secret = b"BIG PRIVATE MESSAGE SHOULD NOT ENTER SQLITE"
    with rollout.open("ab") as stream:
        stream.write(b'{"type":"event_msg","payload":{"text":"')
        stream.write(secret)
        stream.write(b"x" * (MAX_SCAN_BYTES + 100_000))
        stream.write(b'"}}\n')

    snapshot = observer.scan()
    assert snapshot["response_count"] == 0
    assert snapshot["bytes_read"] <= MAX_SCAN_BYTES
    assert snapshot["cursor"] < rollout.stat().st_size
    assert snapshot["coverage_complete"] is False
    assert snapshot["skipped_oversized_lines"] == 1
    restarted = ChatObserver(tmp_path / "observer", rollout, THREAD)
    snapshot = restarted.scan()
    assert snapshot["coverage_complete"] is False
    assert snapshot["skipped_oversized_lines"] == 1
    for stored in (observer.db_path, *observer.db_path.parent.glob(observer.db_path.name + "-*")):
        assert secret not in stored.read_bytes()


@pytest.mark.parametrize("mode", ["truncate", "replace"])
def test_truncation_or_replacement_fails_explicitly_without_resetting_counts(tmp_path, mode):
    rollout = tmp_path / "rollout.jsonl"
    rollout.touch()
    observer = ChatObserver(tmp_path / "observer", rollout, THREAD)
    append_record(rollout, usage_record())
    observer.scan()
    before = observer.snapshot()

    if mode == "truncate":
        with rollout.open("r+b") as stream:
            stream.truncate(0)
    else:
        replacement = tmp_path / "replacement.jsonl"
        replacement.write_bytes(b"replacement\n")
        os.replace(replacement, rollout)

    expected = "truncated" if mode == "truncate" else "replaced"
    with pytest.raises(ObserverError, match=expected):
        observer.scan()
    after = observer.snapshot()
    assert after["response_count"] == before["response_count"] == 1
    assert after["usage"]["total_tokens"] == before["usage"]["total_tokens"]
    assert after["cursor"] == before["cursor"]
    assert after["connected"] is False
