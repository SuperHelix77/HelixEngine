from pathlib import Path
import pytest
from helixengine import cli
from helixengine.runtime import Runtime


def test_research_rejects_release_port_and_store(tmp_path):
    with pytest.raises(ValueError, match='different port'):
        cli.main(['--data-dir', str(tmp_path), 'serve', '--research'])
    with pytest.raises(ValueError, match='separate --data-dir'):
        cli.main(['serve', '--research', '--port', '8770'])
    with pytest.raises(ValueError, match='research-only'):
        cli.main(['serve', '--observe-rollout', 'x', '--observe-thread', 'y'])


def test_release_has_no_chat_observer(tmp_path):
    runtime = Runtime(tmp_path, price_fetcher=lambda: b'')
    try:
        snapshot = runtime.release_state()
        assert snapshot['hub_mode'] == 'release'
        assert 'chat_observer' not in snapshot
        assert runtime._chat_thread is None
    finally:
        runtime.close()


def test_research_cli_explicit_attachment(tmp_path, monkeypatch):
    seen = {}
    def attach(self, path, identity):
        seen['attachment'] = (path, identity)
    def serve(runtime, port, browser):
        seen.update(research=runtime.research, port=port, data=runtime.data_dir)
        runtime.close()
    monkeypatch.setattr(Runtime, 'attach_chat', attach)
    monkeypatch.setattr(cli, 'serve', serve)
    assert cli.main(['--data-dir', str(tmp_path), 'serve', '--research', '--port', '8770', '--observe-rollout', 'explicit.jsonl', '--observe-thread', 'exact-id']) == 0
    assert seen == {'attachment': ('explicit.jsonl', 'exact-id'), 'research': True, 'port': 8770, 'data': tmp_path.resolve()}
