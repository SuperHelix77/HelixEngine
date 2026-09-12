import hashlib

import pytest

from helixengine.state import State


def usage(model="fixture"):
    return {
        "model": model,
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "cache_write_input_tokens": 5,
        "output_tokens": 12,
        "reasoning_output_tokens": 3,
    }


def test_revisioned_switch_binds_new_runs_only(tmp_path):
    state = State(tmp_path)
    first = state.begin(["tool", "arg"], tmp_path)
    assert first["enabled"] is True and first["settings_revision"] == 0
    changed = state.switch(False, 0)
    assert changed == {"enabled": False, "revision": 1}
    second = state.begin(["tool", "arg"], tmp_path)
    assert second["enabled"] is False and second["settings_revision"] == 1
    with pytest.raises(ValueError, match="Settings changed"):
        state.switch(True, 0)
    assert state.settings() == changed


def test_usage_import_is_validated_and_idempotent(tmp_path):
    state = State(tmp_path)
    run = state.begin(["tool"], tmp_path)["id"]
    source = hashlib.sha256(b"raw receipt").hexdigest()
    imported = {**usage(), "run": "forged", "source_hash": "forged"}
    first = state.usage(run, source, imported)
    replay = state.usage(run, source, imported)
    assert first["replayed"] is False and replay["replayed"] is True
    snapshot = state.snapshot()
    assert len(snapshot["usages"]) == 1
    assert snapshot["usages"][0]["run"] == run
    assert snapshot["usages"][0]["source_hash"] == source
    assert [event["kind"] for event in snapshot["events"]].count("USAGE_IMPORTED") == 1
    with pytest.raises(ValueError, match="Conflicting"):
        state.usage(run, source, {**usage(), "output_tokens": 13})

    other = state.begin(["tool"], tmp_path)["id"]
    with pytest.raises(ValueError, match="already bound"):
        state.usage(other, source, usage())
    with pytest.raises(ValueError, match="Nonnegative"):
        state.usage(run, "a" * 64, {**usage(), "input_tokens": -1})


def test_run_completion_retains_receipt_and_live_progress(tmp_path):
    state = State(tmp_path)
    run = state.begin(["tool"], tmp_path)
    state.mark_running(run["id"], 123)
    state.progress(run["id"], 8, 2)
    finished = state.finish(
        run["id"],
        state="FAILED",
        stdout_bytes=8,
        stderr_bytes=2,
        visible_bytes=10,
        elapsed_seconds=0.25,
        exit_code=7,
        receipt="a" * 64,
        reducer_status="OFF_PASSTHROUGH",
    )
    assert finished["state"] == "FAILED"
    assert finished["exit_code"] == 7
    assert finished["receipt"] == "a" * 64
    assert state.get_run(run["id"])["stdout_bytes"] == 8
    assert state.snapshot()["total_runs"] == 1
