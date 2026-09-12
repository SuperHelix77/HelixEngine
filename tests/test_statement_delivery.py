import hashlib
import json

import pytest

from helixengine.chat_observer import ChatObserver
from helixengine.core.evidence import Store
from helixengine.core.workflow_memory import Memory
from helixengine.statement_delivery import StatementDelivery
from helixengine.statement_memory import StatementMemory


def message(identity='m1', phase='final_answer', text='Corrected: 83/60 was source-only. 文\t\n'):
    return (json.dumps({'type': 'response_item', 'payload': {'type': 'message',
        'role': 'assistant', 'id': identity, 'phase': phase,
        'content': [{'type': 'output_text', 'text': text}]}}, ensure_ascii=False) + '\r\n').encode()


def setup(tmp_path):
    source = tmp_path / 'source.jsonl'
    source.write_bytes(b'')
    observer = ChatObserver(tmp_path / 'observer', source, 'thread', capture_statements=True)
    memory = Memory(Store(tmp_path / 'evidence'))
    delivery = StatementDelivery(observer, StatementMemory(memory, 'project'), 'project')
    return source, observer, memory, delivery


def test_capture_exact_visible_messages_and_ignore_reasoning_and_off(tmp_path):
    source, observer, memory, delivery = setup(tmp_path)
    raw = message()
    with source.open('ab') as out:
        out.write(message('analysis', 'analysis', 'must not archive'))
        out.write(raw)
        out.write(message('note', 'commentary'))
    observer.scan()
    assert delivery.snapshot()['pending'] == 2
    assert delivery.drain()['delivered'] == 2
    refs = memory.timeline('project', 'thread')
    assert memory.retrieve('project', [refs[0]['record_hash']])[0]['raw'] == raw
    with observer._db() as db:
        row = db.execute('SELECT * FROM statement_outbox ORDER BY source_offset LIMIT 1').fetchone()
        assert row['source_sha256'] == hashlib.sha256(raw).hexdigest()
        assert 'raw' not in row.keys()
    observer.capture_statements = False
    with source.open('ab') as out: out.write(message('off'))
    observer.scan()
    assert delivery.drain()['queued'] == 2


def test_failed_memory_commit_ack_retries_without_losing_usage_or_duplication(tmp_path):
    source, observer, memory, delivery = setup(tmp_path)
    source.write_bytes(message())
    observer.scan()
    original = delivery.sink.record

    def committed_but_not_acknowledged(*args):
        original(*args)
        raise OSError('simulated lost acknowledgement')

    delivery.sink.record = committed_but_not_acknowledged
    failed = delivery.drain()
    assert failed['pending'] == 1 and failed['error']
    with source.open('ab') as out:
        out.write((json.dumps({'type': 'token_usage_record', 'payload': {
            'thread_id': 'thread', 'turn_id': 'turn', 'response_id': 'resp',
            'usage': {'input_tokens': 10, 'cached_input_tokens': 0,
                'cache_write_input_tokens': 0, 'output_tokens': 1,
                'reasoning_output_tokens': 0, 'total_tokens': 11}}}) + '\n').encode())
    assert observer.scan()['response_count'] == 1
    delivery.sink.record = original
    assert delivery.drain()['pending'] == 0
    assert len(memory.timeline('project', 'thread')) == 1
    restarted = ChatObserver(tmp_path / 'observer', source, 'thread', capture_statements=True)
    resumed = StatementDelivery(restarted, StatementMemory(memory, 'project'), 'project')
    assert resumed.drain()['delivered'] == 1
    with pytest.raises(ValueError, match='project binding'):
        StatementDelivery(restarted, StatementMemory(memory, 'other'), 'other')


def test_changed_source_cannot_be_indexed_as_observed_statement(tmp_path):
    source, observer, memory, delivery = setup(tmp_path)
    original = message(text='exact evidence')
    source.write_bytes(original)
    observer.scan()
    source.write_bytes(original.replace(b'exact evidence', b'wrong evidence'))
    state = delivery.drain()
    assert state['error'] and state['delivered'] == 0
    assert memory.timeline('project', 'thread') == []


def test_partial_record_and_capture_opt_in(tmp_path):
    source, observer, memory, delivery = setup(tmp_path)
    raw = message()
    source.write_bytes(raw[:-1])
    observer.scan()
    assert delivery.snapshot()['queued'] == 0
    with source.open('ab') as out: out.write(raw[-1:])
    observer.scan()
    assert delivery.drain()['delivered'] == 1
    quiet = ChatObserver(tmp_path / 'quiet', source, 'thread', from_start=True)
    quiet.scan()
    with quiet._db() as db:
        assert db.execute('SELECT count(*) FROM statement_outbox').fetchone()[0] == 0


def test_runtime_statement_delivery_is_opt_in_and_switch_controlled(tmp_path):
    import time
    from helixengine.runtime import Runtime
    source = tmp_path / 'native.jsonl'
    source.write_bytes(b'')
    runtime = Runtime(tmp_path / 'runtime')
    try:
        current = runtime.settings()
        if not current['enabled']:
            runtime.switch(True, current['revision'])
        runtime.attach_chat(source, 'thread', statement_project=tmp_path / 'project')
        with source.open('ab') as out: out.write(message())
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            result = runtime.release_state()['statement_memory']
            if result['delivered'] == 1:
                break
            time.sleep(.02)
        assert result['delivered'] == 1 and result['error'] is None
        runtime.switch(False, runtime.settings()['revision'])
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and runtime.chat_observer.capture_statements:
            time.sleep(.02)
        assert runtime.chat_observer.capture_statements is False
    finally:
        runtime.close()


def test_invalid_visible_message_id_becomes_gap_not_scanner_failure(tmp_path):
    source, observer, memory, delivery = setup(tmp_path)
    source.write_bytes(message().replace(b'"m1"', b'"\\ud800"'))
    result = observer.scan()
    assert result['coverage_complete'] is False
    assert delivery.snapshot()['queued'] == 0


def test_cli_statement_project_requires_observation_and_is_passed_explicitly(tmp_path, monkeypatch):
    from helixengine import cli
    from helixengine.runtime import Runtime
    seen = {}
    def attach(self, path, thread, *, statement_project=None):
        seen.update(path=path, thread=thread, project=statement_project)
    monkeypatch.setattr(Runtime, 'attach_chat', attach)
    monkeypatch.setattr(cli, 'serve', lambda *args: None)
    args = ['--data-dir', str(tmp_path), 'serve', '--research', '--port', '8770',
            '--capture-statements-project', str(tmp_path / 'project')]
    with pytest.raises(ValueError, match='explicit chat'):
        cli.main(args)
    assert cli.main(args + ['--observe-rollout', 'native.jsonl', '--observe-thread', 'thread']) == 0
    assert seen['project'] == str(tmp_path / 'project')
