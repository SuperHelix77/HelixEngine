import json
from helixengine.cli import main
from helixengine.core.evidence import Store
from helixengine.core.workflow_memory import Memory


def spec(tmp_path):
    data = tmp_path / 'data'
    memory = Memory(Store(data / 'evidence'))
    authority = memory.store.put(b'Caller authorizes recording only; new requests remain semantic.')['sha256']
    grant = dict(schema='helix.transition.grant.v1', project=str(tmp_path), thread_id='native-root',
                 epoch=1, authorization_ref=authority, unresolved_obligations=[], dependencies=[],
                 recording=dict(max_events=10, max_payload_bytes=2048, notification='Recorded.'))
    path = tmp_path / 'grant.json'
    path.write_text(json.dumps(grant))
    return data, memory, path, grant


def test_cli_arm_stores_grant_without_native_activation(tmp_path, capsys):
    data, memory, path, grant = spec(tmp_path)
    assert main(['--data-dir', str(data), 'transition', 'arm', str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['native_activated'] is False
    assert json.loads(memory.store.get(result['grant_hash'])) == grant


def test_cli_native_activation_requires_explicit_transcript(tmp_path, capsys):
    data, _, path, _ = spec(tmp_path)
    assert main(['--data-dir', str(data), 'transition', 'arm', str(path), '--activate-native']) == 2
    assert '--transcript' in capsys.readouterr().err


def test_cli_rejects_ambiguous_authorization_json(tmp_path, capsys):
    data, _, path, _ = spec(tmp_path)
    path.write_text('{"unresolved_obligations":["review"],"unresolved_obligations":[]}')
    assert main(['--data-dir', str(data), 'transition', 'arm', str(path)]) == 2
    assert 'Duplicate' in capsys.readouterr().err
