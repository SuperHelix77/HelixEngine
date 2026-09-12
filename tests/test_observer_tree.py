import json
from pathlib import Path
import sqlite3
import time

from helixengine.chat_observer import ChatObserver
from helixengine.observer_tree import ObserverTree
from helixengine.state import State


def append(path, value):
    with path.open('ab') as stream:
        stream.write(json.dumps(value).encode() + b'\n')


def usage(thread, response='response', count=100):
    return {'type': 'token_usage_record', 'payload': {'thread_id': thread,
        'turn_id': thread + '-turn', 'response_id': response,
        'usage': {'input_tokens': count, 'cached_input_tokens': 20,
                  'cache_write_input_tokens': 0, 'output_tokens': 10,
                  'reasoning_output_tokens': 5, 'total_tokens': count + 10}}}


def fixture(tmp_path):
    home = tmp_path / 'codex'
    sessions = home / 'sessions'
    sessions.mkdir(parents=True)
    parent = sessions / 'rollout-root.jsonl'
    parent.touch()
    root = ChatObserver(tmp_path / 'engine', parent, 'root')
    state = State(tmp_path / 'engine')
    with sqlite3.connect(home / 'state_5.sqlite') as db:
        db.execute('CREATE TABLE threads(id TEXT PRIMARY KEY,rollout_path TEXT)')
    return home, root, state, ObserverTree(root, state, home)


def add_child(home, state, child='child', parent='root', count=100, response='child-response', metadata_parent=None):
    path = home / 'sessions' / ('rollout-' + child + '.jsonl')
    append(path, {'type': 'session_meta', 'payload': {'id': child, 'session_id': 'root',
            'parent_thread_id': metadata_parent or parent, 'base_instructions': 'private sentinel never retained'}})
    append(path, {'type': 'turn_context', 'payload': {'turn_id': child + '-turn', 'model': 'luna', 'effort': 'high'}})
    append(path, usage(child, response, count))
    append(path, {'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'total_token_usage': {'input_tokens': 999999}}}})
    with sqlite3.connect(home / 'state_5.sqlite') as db:
        db.execute('INSERT INTO threads VALUES(?,?)', (child, str(path)))
    state.event('CODEX_SUBAGENTSTART', {'session_id': parent, 'agent_id': child})
    return path


def test_backfill_and_live_child_costs_merge_without_cumulative_or_duplicate_charges(tmp_path):
    home, root, state, tree = fixture(tmp_path)
    append(root.rollout_path, usage('root', 'root-response', 200))
    root.scan()
    path = add_child(home, state)
    result = tree.scan()
    assert result['usage']['input_tokens'] == 300 and result['response_count'] == 2
    assert result['children'][0]['usage']['input_tokens'] == 100
    assert result['children'][0]['import_pending'] == 0
    append(path, usage('child', 'child-response'))  # same native response replay
    tree.scan()
    append(path, usage('child', 'next-response', 150))
    result = tree.scan()
    assert result['usage']['input_tokens'] == 450 and result['response_count'] == 3
    assert result['whole_workflow_complete'] is False
    with root._db() as db:
        assert db.execute("SELECT count(*) FROM usage_records WHERE thread_id='child'").fetchone()[0] == 2
        assert 'private sentinel' not in '\n'.join(db.iterdump())
    restarted = ObserverTree(ChatObserver(root.data_dir, root.rollout_path, 'root'), state, home)
    assert restarted.scan()['usage']['input_tokens'] == 450


def test_out_of_order_grandchild_discovery_and_unrelated_thread_exclusion(tmp_path):
    home, root, state, tree = fixture(tmp_path)
    add_child(home, state, 'grandchild', 'child', response='grand')
    assert tree.scan()['child_count'] == 0
    add_child(home, state, 'child', response='child')
    add_child(home, state, 'unrelated', 'other-root', response='other')
    result = tree.scan()
    assert result['child_count'] == 2 and result['response_count'] == 2
    assert {r['thread_id'] for r in result['children']} == {'child', 'grandchild'}
    assert 'unrelated' not in tree.children


def test_native_root_scoped_hook_keeps_actual_grandchild_parent(tmp_path):
    home, root, state, tree = fixture(tmp_path)
    add_child(home, state, 'child', response='child')
    add_child(home, state, 'grandchild', 'root', metadata_parent='child', response='grand')
    result = tree.scan()
    assert result['response_count'] == 2
    grand = next(r for r in result['children'] if r['thread_id'] == 'grandchild')
    assert grand['parent_thread_id'] == 'child' and grand['observed_session_id'] == 'root'
    assert grand['error'] is None


def test_missing_registry_and_metadata_mismatch_are_unknown_not_zero_usage(tmp_path):
    home, root, state, tree = fixture(tmp_path)
    state.event('CODEX_SUBAGENTSTART', {'session_id': 'root', 'agent_id': 'missing'})
    add_child(home, state, 'wrong', metadata_parent='other-parent')
    result = tree.scan()
    assert result['child_count'] == 2
    assert all(c['error'] and c['usage'] is None for c in result['children'])
    assert result['response_count'] == 0


def test_cross_thread_conflicting_response_id_does_not_double_count(tmp_path):
    home, root, state, tree = fixture(tmp_path)
    append(root.rollout_path, usage('root', 'collision'))
    root.scan()
    add_child(home, state, response='collision')
    result = tree.scan()
    assert result['usage']['input_tokens'] == 100 and result['response_count'] == 1
    assert 'cross-thread' in result['children'][0]['error']
    assert result['children'][0]['import_pending'] == 1


def test_registry_path_escape_does_not_read_external_file(tmp_path):
    home, root, state, tree = fixture(tmp_path)
    outside = tmp_path / 'secret'
    outside.write_text('must not read')
    with sqlite3.connect(home / 'state_5.sqlite') as db:
        db.execute('INSERT INTO threads VALUES(?,?)', ('bad', str(outside)))
    state.event('CODEX_SUBAGENTSTART', {'session_id': 'root', 'agent_id': 'bad'})
    result = tree.scan()
    assert result['header_bytes_read'] == 0
    assert result['children'][0]['usage'] is None
    assert 'outside' in result['children'][0]['error']


def test_deleted_child_source_keeps_prior_receipts_but_exposes_gap(tmp_path):
    home, root, state, tree = fixture(tmp_path)
    path = add_child(home, state)
    assert tree.scan()['response_count'] == 1
    path.unlink()
    result = tree.scan()
    assert result['response_count'] == 1
    assert result['children'][0]['connected'] is False and result['children'][0]['error']


def test_default_parent_attachment_still_excludes_existing_history(tmp_path):
    path = tmp_path / 'parent.jsonl'
    append(path, usage('root'))
    parent = ChatObserver(tmp_path / 'engine', path, 'root')
    parent.scan()
    assert parent.snapshot()['response_count'] == 0


def test_late_model_metadata_updates_import_without_charging_response_twice(tmp_path):
    home, root, state, tree = fixture(tmp_path)
    path = add_child(home, state)
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(b''.join(line for line in lines if json.loads(line).get('type') != 'turn_context'))
    first = tree.scan()
    assert first['by_model'][0]['model'] == 'UNKNOWN'
    append(path, {'type': 'turn_context', 'payload': {'turn_id': 'child-turn', 'model': 'luna', 'effort': 'high'}})
    later = tree.scan()
    assert later['response_count'] == 1 and later['usage']['input_tokens'] == 100
    assert later['by_model'][0]['model'] == 'luna'


def test_runtime_automatically_follows_child_from_existing_hook_events(tmp_path):
    from helixengine.runtime import Runtime
    home, root, state, tree = fixture(tmp_path)
    add_child(home, state)
    runtime = Runtime(root.data_dir)
    try:
        runtime.attach_chat(root.rollout_path, 'root')
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = runtime.release_state().get('observer_tree', {})
            if result.get('response_count') == 1:
                break
            time.sleep(.02)
        assert result['usage']['input_tokens'] == 100
        assert result['children'][0]['parent_thread_id'] == 'root'
        assert result['worker_error'] is None
    finally:
        runtime.close()
