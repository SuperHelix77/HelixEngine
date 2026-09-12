import json
import pytest
from helixengine.native_continuity import checkpoint, check


def row(kind, **payload):
    return json.dumps({'type': kind, 'payload': payload}).encode() + b'\n'


def context(turn, effort='high'):
    return row('turn_context', turn_id=turn, root_turn_id=turn, model='test-model', effort=effort)


def fixture(tmp_path):
    path = tmp_path / 'native.jsonl'
    path.write_bytes(row('session_meta', id='root') + context('semantic-0') +
                     row('event_msg', type='task_complete', turn_id='semantic-0', last_agent_message='Ready.'))
    return path, checkpoint(path, 'root')


def append(path, raw):
    with path.open('ab') as stream:
        stream.write(raw)


def event(path, turn):
    return dict(hook_event_name='UserPromptSubmit', session_id='root', turn_id=turn,
                transcript_path=str(path))


def start(turn):
    return row('event_msg', type='task_started', turn_id=turn) + context(turn)


def test_stopped_sequence_and_duplicate_fence(tmp_path):
    path, anchor = fixture(tmp_path)
    append(path, start('one'))
    first = check(anchor, event(path, 'one'))
    assert check(first, event(path, 'one')) == first
    append(path, row('event_msg', type='task_complete', turn_id='one', last_agent_message=None) + start('two'))
    second = check(first, event(path, 'two'))
    assert second['pending_turn'] == 'two' and second['bytes_read'] == path.stat().st_size


def test_missed_semantic_turn_invalidates(tmp_path):
    path, anchor = fixture(tmp_path)
    append(path, start('missed') + row('response_item', type='message', role='user', content='Change policy') +
           row('event_msg', type='task_complete', turn_id='missed', last_agent_message='Changed.') + start('next'))
    with pytest.raises(ValueError, match='Unobserved'):
        check(anchor, event(path, 'next'))


@pytest.mark.parametrize('change', ['prefix', 'rollback', 'incomplete', 'context', 'compaction', 'no_start'])
def test_uncertain_continuity_is_rejected(tmp_path, change):
    path, anchor = fixture(tmp_path)
    if change == 'prefix':
        path.write_bytes(path.read_bytes().replace(b'Ready.', b'Other.'))
        append(path, start('one'))
    elif change == 'rollback':
        path.write_bytes(path.read_bytes()[:10])
    elif change == 'incomplete':
        append(path, start('one')[:-1])
    elif change == 'context':
        append(path, row('event_msg', type='task_started', turn_id='one') + context('one', 'low'))
    elif change == 'compaction':
        append(path, row('compacted', summary='shortened') + start('one'))
    else:
        append(path, context('one'))
    with pytest.raises(ValueError):
        check(anchor, event(path, 'one'))


def test_registration_requires_completed_semantic_baseline(tmp_path):
    path = tmp_path / 'fresh.jsonl'
    path.write_bytes(row('session_meta', id='root'))
    with pytest.raises(ValueError, match='No completed'):
        checkpoint(path, 'root')
    append(path, start('pending'))
    with pytest.raises(ValueError, match='not at a completed'):
        checkpoint(path, 'root')
