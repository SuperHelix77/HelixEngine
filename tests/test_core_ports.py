import importlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from helixengine.core.completion_ledger import CompletionLedger, EMPTY
from helixengine.core.evidence import Store, capture
from helixengine.core.line_index import build, retrieve
from helixengine.core import plan_dependencies as dep
from helixengine.core.workflow_memory import Memory


def test_windows_stamp_ignores_only_synthetic_execute_bits(monkeypatch):
    fields = dict(st_dev=1, st_ino=2, st_size=3, st_mtime_ns=4, st_ctime_ns=5)
    path_stat = SimpleNamespace(**fields, st_mode=0o100777)
    fd_stat = SimpleNamespace(**fields, st_mode=0o100666)
    monkeypatch.setattr(dep, 'WINDOWS', True)
    assert dep.stamp(path_stat) == dep.stamp(fd_stat)
    for field in fields:
        changed = SimpleNamespace(**{**fields, field: 999}, st_mode=fd_stat.st_mode)
        assert dep.stamp(path_stat) != dep.stamp(changed)
    assert dep.stamp(path_stat) != dep.stamp(SimpleNamespace(**fields, st_mode=0o100444))
    monkeypatch.setattr(dep, 'WINDOWS', False)
    assert dep.stamp(path_stat) != dep.stamp(fd_stat)


def test_all_copied_core_ports_import_as_package():
    for name in (
        "checked_steps",
        "completion_ledger",
        "copy_handles",
        "evidence",
        "line_index",
        "literal_edits",
        "locking",
        "named_plans",
        "plan_cli",
        "plan_dependencies",
        "renderer",
        "verification",
        "workflow_memory",
    ):
        assert importlib.import_module("helixengine.core." + name)


def test_store_preserves_exact_binary_evidence_and_detects_tamper(tmp_path):
    store = Store(tmp_path / "evidence")
    raw = b"\xff\x00first\r\nsecond\x00"
    source = store.put(raw)["sha256"]
    assert store.get(source) == raw
    (store.root / "objects" / source).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        store.get(source)


def test_capture_calls_cleanup_and_keeps_child_once(tmp_path):
    store = Store(tmp_path / "evidence")
    events = []

    def started(pid, stdout, stderr):
        events.append(("start", pid))

        def cleanup():
            events.append("cleanup")

        return cleanup

    receipt = capture(
        store,
        [sys.executable, "-c", "print('captured')"],
        tmp_path,
        "core-test",
        on_start=started,
    )
    assert events[0][0] == "start" and events[-1] == "cleanup"
    assert store.receipt(receipt)["exit_code"] == 0
    assert store.get(store.receipt(receipt)["stdout"]["sha256"]) == b"captured" + os.linesep.encode()
    assert store.receipt(receipt)["descendant_cleanup"]["attempted"] is True


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group regression")
def test_capture_kills_delayed_writer_after_parent_exit(tmp_path):
    store = Store(tmp_path / "evidence")
    marker = tmp_path / "escaped-writer"
    delayed = (
        "import pathlib,time; time.sleep(0.35); "
        "pathlib.Path(__import__('sys').argv[1]).write_text('escaped', encoding='utf-8')"
    )
    parent = (
        "import subprocess,sys,time; "
        "subprocess.Popen([sys.executable,'-c',sys.argv[2],sys.argv[1]]); "
        "print('parent', flush=True); time.sleep(0.05)"
    )
    receipt_key = capture(
        store,
        [sys.executable, "-u", "-c", parent, str(marker), delayed],
        tmp_path,
        "descendant-regression",
    )
    receipt = store.receipt(receipt_key)
    assert store.get(receipt["stdout"]["sha256"]) == b"parent\n"
    assert receipt["descendant_cleanup"]["forced"] is True
    time.sleep(0.55)
    assert not marker.exists()


def test_line_index_binds_source_and_memory_search_is_literal(tmp_path):
    store = Store(tmp_path / "evidence")
    raw = b"alpha\noperator OR token\nomega\n"
    source = store.put(raw)["sha256"]
    index = build(store, source, chunk_bytes=256, fanout=2)
    selected, receipt = retrieve(store, index, source, 2, 2)
    assert selected == b"operator OR token\n"
    assert receipt["source_sha256"] == source
    memory = Memory(store)
    record = memory.record("p", "s", "e", b"operator OR token")
    assert memory.search("p", "operator OR")[0]["record_hash"] == record["record_hash"]
    with memory.db() as db:
        db.execute("UPDATE search SET body='corrupt' WHERE rowid=1")
    with pytest.raises(ValueError, match="Search index does not match"):
        memory.search("p", "operator")


def test_completion_ledger_duplicate_delivery_is_idempotent(tmp_path):
    memory = Memory(Store(tmp_path / "evidence"))
    ledger = CompletionLedger(memory)
    first = ledger.ingest("scope", "event", b"result", expected_head=EMPTY)
    replay = ledger.ingest("scope", "event", b"result", expected_head=first["head"])
    assert first["replayed"] is False and replay["replayed"] is True
    with pytest.raises(ValueError, match="Conflicting"):
        ledger.ingest("scope", "event", b"different", expected_head=first["head"])


def test_dependency_port_rejects_traversal_and_symlink(tmp_path):
    assert dep.local_path(tmp_path, "folder/file.txt") == tmp_path / "folder/file.txt"
    for name in ("./file.txt", "folder/../file.txt", "folder//file.txt", "file.txt/"):
        with pytest.raises(ValueError):
            dep.local_path(tmp_path, name)
    (tmp_path / "target").write_text("x")
    (tmp_path / "link").symlink_to(tmp_path / "target")
    with pytest.raises(ValueError, match="Symlink"):
        dep.local_path(tmp_path, "link")
