import json
import os
from pathlib import Path
import subprocess
import sys

from helixengine.runtime import Runtime
import helixengine


def test_index_failure_preserves_command_then_recovery_never_executes_it(tmp_path, monkeypatch):
    runtime = Runtime(tmp_path / 'data')
    marker = tmp_path / 'marker'
    original = runtime.memory.record

    def failed_index(*args, **kwargs):
        raise OSError('index unavailable')

    monkeypatch.setattr(runtime.memory, 'record', failed_index)
    result = runtime.run([sys.executable, '-c',
        "from pathlib import Path; import sys; p=Path(sys.argv[1]); p.write_text(p.read_text()+'x' if p.exists() else 'x'); print('exact result'); sys.exit(7)",
        str(marker)], tmp_path, origin={'session_id': 'parent', 'thread_id': 'child',
                                      'agent_id': 'child', 'hook_cwd': str(tmp_path)})
    assert marker.read_text() == 'x' and result['exit_code'] == 7
    assert runtime.visible_output(result) == (b'exact result\n', b'')
    assert result['memory']['error'] and result['memory']['backlog'] == 1
    monkeypatch.setattr(runtime.memory, 'record', original)
    runtime.close()
    restored = Runtime(tmp_path / 'data')
    assert restored.memory_sync()['processed'] == 1
    assert restored.memory_sync()['processed'] == 0
    assert marker.read_text() == 'x'
    rows = restored.memory.timeline(str(tmp_path), 'child')
    assert len(rows) == 1
    observation = json.loads(restored.store.get(rows[0]['source_hash']))
    assert observation['receipt'] == result['receipt']
    assert observation['origin']['session_id'] == 'parent'
    assert observation['origin']['agent_id'] == 'child'
    assert restored.release_state()['receipt_memory']['backlog'] == 0
    restored.close()


def test_switch_off_retains_evidence_without_automatic_memory_indexing(tmp_path):
    runtime = Runtime(tmp_path / 'data')
    runtime.switch(False, runtime.settings()['revision'])
    result = runtime.run([sys.executable, '-c', "print('raw')"], tmp_path)
    assert result['memory'] is None and result['receipt']
    assert runtime.visible_output(result) == (b'raw\n', b'')
    report = runtime.memory_sync()
    assert report['processed'] == 0 and report['skipped_off'] == 1
    assert runtime.memory.timeline(str(tmp_path), 'engine-local') == []
    runtime.close()


def test_memory_commit_before_cursor_commit_replays_without_duplicate(tmp_path, monkeypatch):
    runtime = Runtime(tmp_path / 'data')
    original = runtime.memory.record

    def committed_then_interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError('interrupted after memory commit')

    monkeypatch.setattr(runtime.memory, 'record', committed_then_interrupted)
    result = runtime.run([sys.executable, '-c', "print('once')"], tmp_path)
    assert result['memory']['cursor'] == 0 and result['memory']['error']
    assert len(runtime.memory.timeline(str(tmp_path), 'engine-local')) == 1
    runtime.close()
    restored = Runtime(tmp_path / 'data')
    report = restored.memory_sync()
    assert report['error'] is None and report['backlog'] == 0
    assert report['last_batch']['index_input_bytes'] == 0
    assert len(restored.memory.timeline(str(tmp_path), 'engine-local')) == 1
    assert restored.state.snapshot()['total_runs'] == 1
    restored.close()


def test_same_execution_cannot_be_redelivered_under_another_thread(tmp_path):
    runtime = Runtime(tmp_path / 'data')
    result = runtime.run([sys.executable, '-c', "print('once')"], tmp_path,
                         origin={'thread_id': 'first'})
    assert result['memory']['error'] is None
    row = {**result['run'], 'origin': {'thread_id': 'second'}}
    runtime.state.event('RUN_COMPLETED', row, run=row['id'])
    report = runtime.memory_sync()
    assert report['backlog'] == 1 and 'collision' in report['error']
    assert len(runtime.memory.timeline(str(tmp_path), 'first')) == 1
    assert runtime.memory.timeline(str(tmp_path), 'second') == []
    runtime.close()


def test_memory_cli_exposes_durable_status_and_no_execution_recovery(tmp_path):
    runtime = Runtime(tmp_path / 'data')
    runtime.memory_sync = lambda: None  # Simulate interruption before ingestion.
    result = runtime.run([sys.executable, '-c', "print('retained')"], tmp_path)
    runtime.close()
    base = [sys.executable, '-m', 'helixengine', '--data-dir', str(tmp_path / 'data'), 'memory']
    # Exercise the same distribution that pytest imported, including installed
    # wheel/sdist checks from outside the repository.
    env = {**os.environ, 'PYTHONPATH': str(Path(helixengine.__file__).resolve().parents[1])}
    status = subprocess.run(base + ['status'], cwd=tmp_path, env=env, capture_output=True, check=True, text=True)
    assert json.loads(status.stdout)['backlog'] == 1
    sync = subprocess.run(base + ['sync', '--limit', '1'], cwd=tmp_path, env=env, capture_output=True, check=True, text=True)
    assert json.loads(sync.stdout)['processed'] == 1
    restored = Runtime(tmp_path / 'data')
    assert restored.state.snapshot()['total_runs'] == 1
    assert restored.store.retrieve(result['receipt'], 'stdout')['text'] == 'retained\n'
    restored.close()
