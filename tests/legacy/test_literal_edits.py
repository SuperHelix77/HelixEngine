import hashlib
import json
import pytest
from helixengine.core.evidence import Store
from helixengine.core.literal_edits import assemble, compile_edits, parse


def run(tmp_path, raw, edits):
    store = Store(tmp_path); key = store.put(raw)['sha256']
    return assemble(store, key, json.dumps({'edits': edits}))


def test_simultaneous_edits_not_cascading_and_bytes_preserved(tmp_path):
    raw = 'é = 1\r\nx = 2\ntrailing\x00\xff'.encode('utf-8')
    out, r = run(tmp_path, raw, [{'old': 'é = 1', 'new': 'x = 2'}, {'old': 'x = 2', 'new': 'é = 3'}])
    assert out == 'x = 2\r\né = 3\ntrailing\x00\xff'.encode('utf-8')
    assert r['copied_bytes'] + r['literal_bytes'] == len(out)


def test_full_replacement_delete_and_noop(tmp_path):
    assert run(tmp_path / 'full', b'old', [{'old': 'old', 'new': 'complete new file'}])[0] == b'complete new file'
    assert run(tmp_path / 'empty', b'old', [{'old': 'old', 'new': ''}])[0] == b''
    assert run(tmp_path / 'same', b'\x00\xff', [])[0] == b'\x00\xff'


@pytest.mark.parametrize('raw,edits', [
    (b'abc', [{'old': 'missing', 'new': 'x'}]),
    (b'ab ab', [{'old': 'ab', 'new': 'x'}]),
    (b'aaa', [{'old': 'aa', 'new': 'x'}]),
    (b'abc', [{'old': 'ab', 'new': 'x'}, {'old': 'bc', 'new': 'y'}]),
    (b'abc', [{'old': 'a', 'new': 'x'}, {'old': 'a', 'new': 'y'}]),
    (b'abc', [{'old': '', 'new': 'x'}]),
    (b'abc', [{'old': 'a', 'new': 3}]),
    (b'abc', [{'old': 'a', 'new': 'b', 'execute': True}]),
])
def test_ambiguous_or_invalid_edit_rejected_without_publish(tmp_path, raw, edits):
    with pytest.raises(ValueError): run(tmp_path, raw, edits)
    assert not (tmp_path / 'result.py').exists()


@pytest.mark.parametrize('text', ['{"edits":[],"edits":[]}', '{"edits":[{"old":"a","old":"b","new":"c"}]}', '{"edits":NaN}'])
def test_strict_json(text):
    with pytest.raises(ValueError): parse(text)


def test_stale_and_corrupt_source_and_output_limit(tmp_path):
    raw = b'old'; h = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError): compile_edits(b'changed', h, {'edits': []})
    store = Store(tmp_path); key = store.put(raw)['sha256']
    with pytest.raises(ValueError): assemble(store, key, '{"edits":[]}', max_output_bytes=1)
    (tmp_path / 'objects' / key).write_bytes(b'changed')
    with pytest.raises(ValueError): assemble(store, key, '{"edits":[]}')
