import json
from pathlib import Path
from shutil import copytree
from helixengine import release_data


def read(path, limit):
    raw = path.read_bytes()
    if len(raw) > limit:
        raise ValueError('Too large')
    return raw


def test_public_evidence_retains_rejection_and_qualification_limits():
    state = release_data.project(read)
    assert len(state['lanes']) == 6 and state['problems'] == []
    assert state['model_wide_parity'] is False and state['release_medians'] is None
    assert any(lane['state'].startswith('REJECTED') for lane in state['lanes'])
    installed = next(lane for lane in state['lanes'] if lane['id'] == 'astra-high-installed-maintenance')
    assert installed['state'] == 'NO_ECONOMIC_QUALIFICATION'
    assert installed['savings']['input_tokens'] < 0 and installed['savings']['output_tokens'] < 0
    assert all(arm['engine_runs'] == 0 for arm in installed['arms'])
    for lane in state['lanes']:
        assert lane['model_wide_parity'] is False
        assert lane['release_median'] is None


def test_tampered_capsule_is_withdrawn(tmp_path):
    root = tmp_path/'capsules'
    copytree(Path(release_data.__file__).parent/'release_evidence', root)
    index = json.loads((root/'index.json').read_text())
    (root/index['lanes'][0]['file']).write_text('{}')
    state = release_data.project(read, root)
    assert len(state['lanes']) == len(index['lanes']) - 1
    assert state['problems'][0]['error'] == 'Evidence capsule changed'


def test_missing_or_invalid_index_does_not_break_application(tmp_path):
    assert release_data.project(read,tmp_path)['problems']
    (tmp_path/'index.json').write_text('{"lanes": null, "version":"invalid"}')
    state = release_data.project(read,tmp_path)
    assert not state['lanes'] and state['problems']
