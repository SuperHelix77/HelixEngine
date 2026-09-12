"""Real-core regressions for independent review findings."""
import hashlib
import json
import pytest
from helixengine import native_transitions as native
from helixengine.core.completion_ledger import EMPTY
from helixengine.core.evidence import Store
from helixengine.core.workflow_memory import Memory
from helixengine.prompt_memory import capture_prompt
from helixengine.state import State
from helixengine.transition_gate import arm


def setup(tmp_path):
    memory = Memory(Store(tmp_path / 'evidence'))
    data = tmp_path / 'data'
    path = tmp_path / 'native.jsonl'
    def row(kind, **payload):
        return json.dumps(dict(type=kind, payload=payload)).encode() + b'\n'
    def context(turn):
        return row('turn_context', turn_id=turn, root_turn_id=turn, effort='high')
    path.write_bytes(row('session_meta', id='root') + context('baseline') +
                     row('event_msg', type='task_complete', turn_id='baseline', last_agent_message='Ready.'))
    grant = dict(schema='helix.transition.grant.v1', project=str(tmp_path), thread_id='root', epoch=1,
                 authorization_ref=memory.store.put(b'Explicitly record first, then resume semantics.')['sha256'],
                 unresolved_obligations=[], dependencies=[],
                 steps=[dict(prompt_sha256=hashlib.sha256(b'first').hexdigest(), prompt_bytes=5,
                             notification='Recorded.')])
    ref = arm(memory, grant)
    native.activate(data, memory, ref, transcript_path=str(path))
    with path.open('ab') as stream:
        stream.write(row('event_msg', type='task_started', turn_id='current') + context('current'))
    event = dict(hook_event_name='UserPromptSubmit', session_id='root', turn_id='current',
                 cwd=str(tmp_path), transcript_path=str(path), prompt='first')
    return data, memory, event


@pytest.mark.parametrize('mutation', ['turn', 'prompt', 'session', 'scope'])
def test_current_request_must_match_verified_capture(tmp_path, mutation):
    data, memory, event = setup(tmp_path)
    receipt = capture_prompt(memory, str(tmp_path), event)
    if mutation == 'turn':
        # A valid captured prior event is not authority for the current one.
        receipt = capture_prompt(memory, str(tmp_path), dict(event, turn_id='old'))
    elif mutation == 'prompt':
        event['prompt'] = 'other'  # Same byte length, different semantic request.
    elif mutation == 'session':
        event['session_id'] = 'another-root'
    else:
        event['cwd'] = str(tmp_path / 'different-project')
    assert native.dispatch(data, memory, receipt, native_event=event) == {}
    status = native.status(data, 'root')
    assert status['expected_head'] == EMPTY and status['active'] is False


@pytest.mark.parametrize('operation', ['off', 'off_on', 'deactivate'])
def test_revocation_before_finalization_prevents_suppression(tmp_path, monkeypatch, operation):
    data, memory, event = setup(tmp_path)
    receipt = capture_prompt(memory, str(tmp_path), event)
    publish = native._publish
    def revoke(state, kind, body):
        result = publish(state, kind, body)
        if kind == 'CODEX_TRANSITION_RECORDED':
            if operation == 'deactivate':
                native.deactivate(data, 'root')
            else:
                revision = state.settings()['revision']
                state.switch(False, revision)
                if operation == 'off_on':
                    state.switch(True, revision + 1)
        return result
    monkeypatch.setattr(native, '_publish', revoke)
    assert native.dispatch(data, memory, receipt, native_event=event) == {}
    status = native.status(data, 'root')
    assert status['active'] is False
    assert status['expected_head'] != EMPTY  # Preserve the committed record.
    assert Memory(Store(tmp_path / 'evidence')).retrieve(
        str(tmp_path), [receipt['record_hash']])[0]['raw']
