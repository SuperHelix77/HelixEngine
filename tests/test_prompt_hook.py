"""Native submission must remain untouched by exact-memory capture."""
import json
import pytest
from helixengine.codex_intercept import hook
from helixengine.state import State


def event(tmp_path):
    return {'hook_event_name':'UserPromptSubmit','session_id':'root','turn_id':'turn-1',
            'cwd':str(tmp_path),'prompt':'  Keep 東京 exactly.\nIgnore archived instructions.\n'}


def test_capture_does_not_inject_or_block(tmp_path):
    data=tmp_path/'data';e=event(tmp_path)
    assert hook(e,data)=={}
    with State(data).db() as db:
        rows=[json.loads(r[0]) for r in db.execute("SELECT body FROM events WHERE kind='CODEX_PROMPT_CAPTURED'")]
    assert len(rows)==1 and rows[0]['capture']['captured'] is True
    assert e['prompt'] not in json.dumps(rows)
    assert rows[0]['thread_id']=='root'


def test_engine_off_does_not_capture(tmp_path):
    data=tmp_path/'data';state=State(data);setting=state.settings();state.switch(False,setting['revision'])
    assert hook(event(tmp_path),data)=={}
    assert not (data/'evidence').exists()


def test_capture_failure_keeps_submission_native(tmp_path,monkeypatch):
    from helixengine import prompt_memory
    def broken(*args):raise OSError('unavailable')
    monkeypatch.setattr(prompt_memory,'capture_prompt',broken)
    data=tmp_path/'data';assert hook(event(tmp_path),data)=={}
    with State(data).db() as db:
        rows=[json.loads(r[0]) for r in db.execute("SELECT body FROM events WHERE kind='CODEX_PROMPT_CAPTURE_INCOMPLETE'")]
    assert rows[0]['error_type']=='OSError'


def test_scoped_hook_does_not_capture_other_root(tmp_path):
    data=tmp_path/'data'
    assert hook(event(tmp_path),data,session_scope='another-root')=={}
    assert not data.exists()


@pytest.mark.parametrize('missing', [True, False])
def test_invalid_cwd_reports_gap_without_blocking(tmp_path, missing):
    data = tmp_path / 'data'
    e = event(tmp_path)
    if missing:
        del e['cwd']
    else:
        e['cwd'] = str(tmp_path / 'deleted-worktree')
    assert hook(e, data) == {}
    with State(data).db() as db:
        rows = [json.loads(r[0]) for r in db.execute(
            "SELECT body FROM events WHERE kind='CODEX_PROMPT_CAPTURE_INCOMPLETE'")]
    assert len(rows) == 1 and rows[0]['error_type'] == 'invalid_cwd'
    assert not (data / 'evidence').exists()
