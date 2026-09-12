import json
import os
from pathlib import Path
import sys
import threading
import time

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


def test_live_progress_and_timeout_are_observed(tmp_path):
    runtime = Runtime(tmp_path)
    holder = {}

    def work():
        holder["result"] = runtime.run(
            command("import sys,time;print('ready'*400,flush=True);time.sleep(.35);print('done')"),
            tmp_path,
        )

    thread = threading.Thread(target=work)
    thread.start()
    saw_running = False
    deadline = time.monotonic() + 2
    while thread.is_alive() and time.monotonic() < deadline:
        rows = runtime.state.snapshot()["runs"]
        if rows and rows[0]["state"] == "RUNNING" and rows[0]["stdout_bytes"] > 0:
            saw_running = True
            break
        time.sleep(0.02)
    thread.join(3)
    assert saw_running
    assert holder["result"]["run"]["state"] == "COMPLETED"

    timed = runtime.run(command("import time;time.sleep(10)"), tmp_path, timeout=0.1)
    assert timed["timed_out"] is True
    assert timed["run"]["state"] == "FAILED"
    assert timed["run"]["reducer_status"] in {"REDUCED", "BYPASSED_SMALL_OUTPUT"}


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
