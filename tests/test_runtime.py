from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import threading
import time

import pytest

from helixengine.runtime import Runtime


def command(code, *args):
    return [sys.executable, "-u", "-c", code, *map(str, args)]


def test_off_passthrough_and_on_reducer_failure_do_not_rerun(tmp_path):
    runtime = Runtime(tmp_path)
    runtime.switch(False, runtime.settings()["revision"])
    off = runtime.run(
        command("import sys;sys.stdout.buffer.write(b'OUT\\x00\\n');sys.stderr.buffer.write(b'ERR\\n');sys.exit(7)"),
        tmp_path,
    )
    assert off["stdout"] == b"OUT\x00\n"
    assert off["stderr"] == b"ERR\n"
    assert off["exit_code"] == 7
    assert off["run"]["reducer_status"] == "OFF_PASSTHROUGH"

    marker = tmp_path / "executions"
    runtime.switch(True, runtime.settings()["revision"])

    def failing_reducer(*args):
        raise RuntimeError("reducer fixture failure")

    runtime.reducer = failing_reducer
    on = runtime.run(
        command(
            "import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.write_text(p.read_text()+'x' if p.exists() else 'x'); print('x'*4000); sys.exit(7)",
            marker,
        ),
        tmp_path,
    )
    assert marker.read_text() == "x"
    assert on["exit_code"] == 7
    assert on["run"]["reducer_status"] == "FAILED_FALLBACK_RAW"
    assert on["run"]["visible_bytes"] == on["run"]["stdout_bytes"] + on["run"]["stderr_bytes"]
    assert len(runtime.state.snapshot()["runs"]) == 2


def test_on_reduces_only_when_projection_is_smaller(tmp_path):
    runtime = Runtime(tmp_path)
    result = runtime.run(command("print('warning\\n'*10000)"), tmp_path, kind="generic")
    row = result["run"]
    assert row["enabled"] is True
    assert row["stdout_bytes"] > row["visible_bytes"]
    assert row["reducer_status"] == "REDUCED"
    assert row["packet_receipt"]


def test_small_binary_output_keeps_exact_streams_without_projection(tmp_path):
    def must_not_parse(*args):
        raise AssertionError('Small output should not pay projection/retrieval overhead')

    runtime = Runtime(tmp_path, reducer=must_not_parse)
    try:
        result = runtime.run(command("import sys;sys.stdout.buffer.write(b'A\\x00B\\n');sys.stderr.buffer.write(b'failure\\n');sys.exit(7)"), tmp_path)
        assert runtime.visible_output(result) == (b'A\x00B\n', b'failure\n')
        assert result['exit_code'] == 7
        assert result['run']['reducer_status'] == 'BYPASSED_SMALL_OUTPUT'
        assert result['run']['enabled'] is True
        receipt = runtime.store.receipt(result['receipt'])
        assert runtime.store.get(receipt['stdout']['sha256']) == b'A\x00B\n'
    finally:
        runtime.close()


@pytest.mark.parametrize('raw_size,packet_size,admitted', [
    (2050, 1639, False),  # Proportional gain alone does not cover fixed overhead.
    (5000, 4400, False),  # Fixed gain alone can still be marginal.
    (2048, 1536, True),
    (3000, 2400, True),
])
def test_marginal_projection_keeps_raw_and_material_projection_is_delivered(tmp_path, raw_size, packet_size, admitted):
    calls = []
    def projection(*args):
        calls.append(True)
        return {'p': 'x' * (packet_size - 8)}

    runtime = Runtime(tmp_path, reducer=projection)
    try:
        result = runtime.run(command("import sys;sys.stdout.write('a'*int(sys.argv[1]))", raw_size), tmp_path)
        out, err = runtime.visible_output(result)
        assert calls == [True] and err == b'' and result['exit_code'] == 0
        assert result['run']['enabled'] is True
        if admitted:
            assert len(out) == packet_size and result['run']['reducer_status'] == 'REDUCED'
        else:
            assert out == b'a' * raw_size
            assert result['run']['reducer_status'] == 'BYPASSED_MARGINAL_GAIN'
            assert result['packet_receipt'] is None
    finally:
        runtime.close()


def test_live_progress_and_timeout_are_observed(tmp_path):
    runtime = Runtime(tmp_path)
    release = tmp_path / "release-child"
    # Hold the child in its observable running phase until the test releases it.
    # A fixed sleep / three-second join races slow Windows receipt publication.
    code = (
        "import pathlib,sys,time;print('ready'*400,flush=True);"
        "release=pathlib.Path(sys.argv[1]);deadline=time.monotonic()+15\n"
        "while not release.exists() and time.monotonic()<deadline: time.sleep(.02)\n"
        "assert release.exists(), 'test did not release child'\n"
        "print('done')"
    )
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(runtime.run, command(code, release), tmp_path, timeout=20)
            saw_running = False
            try:
                deadline = time.monotonic() + 10
                while not future.done() and time.monotonic() < deadline:
                    rows = runtime.state.snapshot()["runs"]
                    if rows and rows[0]["state"] == "RUNNING" and rows[0]["stdout_bytes"] > 0:
                        saw_running = True
                        break
                    time.sleep(0.02)
            finally:
                release.touch()
            # Propagate worker exceptions; do not inspect an unfinished result dict.
            result = future.result(timeout=25)
            assert saw_running
            assert result["exit_code"] == 0
            assert result["stdout"].splitlines()[-1] == b"done"
            assert result["run"]["state"] == "COMPLETED"

        timed = runtime.run(command("import time;time.sleep(10)"), tmp_path, timeout=0.1)
        assert timed["timed_out"] is True
        assert timed["run"]["state"] == "FAILED"
        assert timed["run"]["reducer_status"] in {"REDUCED", "BYPASSED_SMALL_OUTPUT"}
    finally:
        runtime.close()


def test_memory_and_usage_imports_are_real_and_telemetred(tmp_path):
    runtime = Runtime(tmp_path)
    run = runtime.run(command("print('observation')"), tmp_path)
    receipt_path = tmp_path / "usage.json"
    receipt_path.write_text(
        json.dumps(
            {
                "model": "fixture-model",
                "input_tokens": 100,
                "cached_input_tokens": 10,
                "cache_write_input_tokens": 5,
                "output_tokens": 8,
                "reasoning_output_tokens": 2,
            }
        )
    )
    imported = runtime.usage_import(run["run"]["id"], receipt_path)
    replayed = runtime.usage_import(run["run"]["id"], receipt_path)
    assert imported["replayed"] is False and replayed["replayed"] is True

    record = runtime.memory_record("project", "session", "event-1", b"exact historical evidence")
    found = runtime.memory_search("project", "historical evidence")
    recovered = runtime.memory_retrieve("project", [record["record_hash"]])
    assert found[0]["record_hash"] == record["record_hash"]
    assert recovered[0]["raw"] == b"exact historical evidence"
    kinds = [event["kind"] for event in runtime.state.snapshot()["events"]]
    assert "USAGE_IMPORTED" in kinds and "MEMORY_RECORDED" in kinds
    assert "MEMORY_SEARCHED" in kinds and "MEMORY_RETRIEVED" in kinds


def test_release_costs_use_one_model_rate_table_without_network(tmp_path):
    calls = []

    def no_network():
        calls.append(True)
        raise AssertionError("one-shot release inspection must not refresh pricing")

    runtime = Runtime(tmp_path, price_fetcher=no_network)
    rates = {
        model: {"short": [1.0, 2.0, 3.0, 4.0], "long": [5.0, 6.0, 7.0, 8.0]}
        for model in ("gpt-5.6-sol", "gpt-6-astra", "gpt-5.6-terra", "gpt-5.6-luna")
    }
    runtime.prices.rates = rates
    runtime.prices.checked = runtime.prices.clock()
    release = runtime._release()
    lane = next(item for item in release["lanes"] if item["model"] == "gpt-5.6-sol")
    assert lane["costs"]["off"] == {"short": 0.361969, "long": 1.137665}
    assert lane["costs"]["on"] == {"short": 0.182799, "long": 0.595251}
    runtime.release_state()
    assert calls == []
    assert runtime._price_thread is None
    runtime.close()
