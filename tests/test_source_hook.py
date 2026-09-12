"""Source opt-in uses the shared hook without overriding existing transitions."""
import copy
import json

from helixengine.cli import main
from helixengine.codex_intercept import hook
from helixengine.state import State


def event(project):
    return {'hook_event_name': 'UserPromptSubmit', 'session_id': 'root',
            'turn_id': 'turn-1', 'cwd': str(project), 'prompt': 'Fix source.py.'}


def configure(tmp_path, capsys):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'source.py').write_bytes(b'VALUE = "Tokyo"\r\n')
    data = tmp_path / 'engine'
    assert main(['--data-dir', str(data), 'codex', 'source', 'set',
                 '--project', str(project), 'source.py']) == 0
    capsys.readouterr()
    return project, data


def test_cli_configuration_delivers_evidence_without_changing_submission(tmp_path, capsys):
    project, data = configure(tmp_path, capsys)
    submission = event(project)
    before = copy.deepcopy(submission)
    response = hook(submission, data)
    context = response['hookSpecificOutput']['additionalContext']
    assert 'source.py' in context and 'Tokyo' in context
    assert submission == before
    assert response['hookSpecificOutput']['hookEventName'] == 'UserPromptSubmit'
    assert 'continue' not in response
    with State(data).db() as db:
        rows = [json.loads(r[0]) for r in db.execute(
            "SELECT body FROM events WHERE kind='CODEX_SOURCE_CONTEXT_OFFERED'")]
    assert len(rows) == 1
    assert rows[0]['delivery'] == 'hook_response_not_wire_verified'
    assert 'Tokyo' not in json.dumps(rows)
    assert rows[0]['report']['store_io']['object_bytes_written'] == len((project / 'source.py').read_bytes())
    assert rows[0]['report']['preparation_seconds'] >= 0
    assert main(['--data-dir', str(data), 'codex', 'source', 'clear',
                 '--project', str(project)]) == 0
    capsys.readouterr()
    assert hook(submission, data) == {}


def test_engine_off_never_reads_configured_source(tmp_path, capsys, monkeypatch):
    project, data = configure(tmp_path, capsys)
    from helixengine import source_context
    calls = []
    monkeypatch.setattr(source_context, 'prepare', lambda *args: calls.append(args))
    state = State(data)
    state.switch(False, state.settings()['revision'])
    assert hook(event(project), data) == {}
    assert calls == []


def test_recording_response_keeps_priority(tmp_path, capsys, monkeypatch):
    project, data = configure(tmp_path, capsys)
    from helixengine import native_transitions, source_context
    original = {'continue': False, 'stopReason': 'Already recorded'}
    monkeypatch.setattr(native_transitions, 'dispatch', lambda *args, **kwargs: original)
    calls = []
    monkeypatch.setattr(source_context, 'prepare', lambda *args: calls.append(args))
    assert hook(event(project), data) is original
    assert calls == []


def test_missing_source_keeps_native_turn_and_reports_gap(tmp_path, capsys):
    project, data = configure(tmp_path, capsys)
    (project / 'source.py').unlink()
    assert hook(event(project), data) == {}
    with State(data).db() as db:
        assert db.execute("SELECT count(*) FROM events WHERE kind='CODEX_SOURCE_CONTEXT_BYPASSED'").fetchone()[0] == 1


def test_source_opt_in_does_not_leak_to_another_project(tmp_path, capsys):
    project, data = configure(tmp_path, capsys)
    other = tmp_path / 'other'
    other.mkdir()
    assert hook(event(other), data) == {}


def test_child_start_gets_same_source_with_separate_attribution(tmp_path, capsys):
    project, data = configure(tmp_path, capsys)
    child = {'hook_event_name': 'SubagentStart', 'session_id': 'parent',
             'agent_id': 'child', 'cwd': str(project)}
    response = hook(child, data)
    assert response['hookSpecificOutput']['hookEventName'] == 'SubagentStart'
    assert 'Tokyo' in response['hookSpecificOutput']['additionalContext']
    with State(data).db() as db:
        body = json.loads(db.execute(
            "SELECT body FROM events WHERE kind='CODEX_SOURCE_CONTEXT_OFFERED'").fetchone()[0])
    assert body['thread_id'] == 'child' and body['session_id'] == 'parent'
    child['hook_event_name'] = 'SubagentStop'
    assert hook(child, data) == {}


def test_optional_source_failure_does_not_misreport_prompt_capture(tmp_path, capsys, monkeypatch):
    project, data = configure(tmp_path, capsys)
    from helixengine import source_context
    def broken(*args):
        raise OSError('private diagnostic must not enter model context')
    monkeypatch.setattr(source_context, 'prepare', broken)
    assert hook(event(project), data) == {}
    with State(data).db() as db:
        events = list(db.execute('SELECT kind,body FROM events'))
    assert any(kind == 'CODEX_PROMPT_CAPTURED' for kind, _ in events)
    assert not any(kind == 'CODEX_PROMPT_CAPTURE_INCOMPLETE' for kind, _ in events)
    assert any(kind == 'CODEX_SOURCE_CONTEXT_BYPASSED' for kind, _ in events)
    assert 'private diagnostic' not in json.dumps([body for _, body in events])
