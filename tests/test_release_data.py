import json
import hashlib
from pathlib import Path
from shutil import copytree
from helixengine import release_data


def read(path, limit):
    raw = path.read_bytes()
    if len(raw) > limit:
        raise ValueError('Too large')
    return raw


def write_lane(root, lane):
    root.mkdir()
    raw = json.dumps(lane).encode()
    (root/'lane.json').write_bytes(raw)
    (root/'index.json').write_text(json.dumps({
        'version': 'test',
        'lanes': [{'file': 'lane.json', 'sha256': hashlib.sha256(raw).hexdigest()}],
    }))


def unpaired_lane(**updates):
    lane = {
        'id': 'unpaired-route-failure',
        'model': 'gpt-6-astra',
        'state': 'UNPAIRED_ROUTE_FAILURE',
        'model_wide_parity': False,
        'release_median': None,
        'paired_tasks': 0,
        'arms': [{
            'arm': 'on',
            'usage': {
                'input_tokens': 120,
                'cached_input_tokens': 40,
                'cache_write_input_tokens': 0,
                'output_tokens': 8,
                'reasoning_output_tokens': 2,
            },
        }],
    }
    lane.update(updates)
    return lane


def test_public_evidence_retains_rejection_and_qualification_limits():
    state = release_data.project(read)
    index = json.loads((Path(release_data.__file__).parent/'release_evidence'/'index.json').read_text())
    assert len(state['lanes']) == len(index['lanes']) and state['problems'] == []
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


def test_valid_unpaired_route_failure_has_no_delta(tmp_path):
    root = tmp_path/'capsules'
    write_lane(root, unpaired_lane())
    state = release_data.project(read, root)
    assert state['problems'] == []
    lane = state['lanes'][0]
    assert [arm['arm'] for arm in lane['arms']] == ['on']
    assert lane['savings'] is None


def test_unpaired_route_failure_discards_supplied_savings(tmp_path):
    root = tmp_path/'capsules'
    write_lane(root, unpaired_lane(savings={'input_tokens': 99, 'output_tokens': 88, 'uncached_input_tokens': 77}))
    state = release_data.project(read, root)
    assert state['lanes'][0]['savings'] is None


def test_missing_arm_in_other_state_is_rejected(tmp_path):
    root = tmp_path/'capsules'
    write_lane(root, unpaired_lane(state='BOUNDED_DEVELOPMENT_CANDIDATE'))
    state = release_data.project(read, root)
    assert state['lanes'] == []
    assert state['problems'][0]['error'] == 'Incomplete pair'


def test_unpaired_failure_rejects_empty_or_complete_pair(tmp_path):
    on = unpaired_lane()['arms'][0]
    for name, arms in [('empty', []), ('paired', [on, {**on, 'arm': 'off'}])]:
        root = tmp_path/name
        write_lane(root, unpaired_lane(arms=arms))
        result = release_data.project(read, root)
        assert result['lanes'] == [] and result['problems'][0]['error'] == 'Incomplete pair'


def test_unpaired_route_failure_requires_strict_zero_integer_paired_tasks(tmp_path):
    for paired_tasks in (False, True, '0', 0.0, None, 1):
        root = tmp_path/f'capsules-{str(paired_tasks).lower()}'
        write_lane(root, unpaired_lane(paired_tasks=paired_tasks))
        state = release_data.project(read, root)
        assert state['lanes'] == []
        assert state['problems'][0]['error'] == 'Incomplete pair'
