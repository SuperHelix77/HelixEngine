import os,random
import pytest
from helixengine.core.evidence import Store
from helixengine.core.line_index import build, retrieve

NATIVE_NEWLINE=os.linesep


def test_exact_ranges_across_nodes_and_binary_lines(tmp_path):
    s = Store(tmp_path);raw = b''.join((b'\xff\x00'+str(i).encode()+b'\r\n') for i in range(1000))+b'last'
    source = s.put(raw)['sha256'];index = build(s, source, chunk_bytes=256, fanout=2)
    rng = random.Random(319)
    for _ in range(100):
        a = rng.randint(1, 1100);b = a+rng.randint(0, 200)
        got, _ = retrieve(s, index, source, a, b)
        assert got == b''.join(raw.splitlines(keepends=True)[a-1:b])
    assert retrieve(s,index,source)[0] == raw


@pytest.mark.parametrize('raw', [b'', b'a', b'a\r\nb\rc\n', b'x'*100000+b'\nlast'], ids=['empty','single-byte','mixed-newlines','oversized-line'])
def test_empty_and_oversized_lines(tmp_path, raw):
    s = Store(tmp_path);source=s.put(raw)['sha256'];index=build(s,source,chunk_bytes=256)
    assert retrieve(s,index,source)[0] == raw


def test_hash_and_generation_fail_closed(tmp_path):
    s = Store(tmp_path);source=s.put(b'original\n')['sha256'];index=build(s,source)
    with pytest.raises(ValueError):retrieve(s,index,'0'*64)
    (s.root/'objects'/source).write_bytes(b'changed\n')
    with pytest.raises(ValueError):retrieve(s,index,source)


def test_read_reduction_discloses_index_build_cost(tmp_path):
    s=Store(tmp_path);raw=b'line\n'*1000000;source=s.put(raw)['sha256']
    before=dict(s.metrics);index=build(s,source)
    assert s.metrics['object_bytes_read']-before['object_bytes_read']>=len(raw)
    reader=Store(tmp_path);got,receipt=retrieve(reader,index,source,500000,500000)
    assert got==b'line\n'
    assert receipt['io']['object_bytes_read']<25000
    assert s.metrics['index_bytes_parsed']==len(raw)


def test_wrong_index_content_cannot_pass_source_verification(tmp_path):
    import json
    from helixengine.core.line_index import encode, verify_index
    s=Store(tmp_path);original=s.put(b'original\n')['sha256'];other=s.put(b'different\n')['sha256']
    index=build(s,other);root=json.loads(s.get(index));root['source_sha256']=original
    forged=s.put(encode(root))['sha256']
    with pytest.raises(ValueError):verify_index(s,forged,original)


def test_receipt_retrieval_binds_index_to_correct_stream(tmp_path):
    import sys
    from helixengine.core.evidence import run
    s=Store(tmp_path/'s');p=run(s,[sys.executable,'-c','print("first\\nsecond\\nthird")'],tmp_path,'test')
    index=build(s,p['raw']['stdout']['sha256'])
    assert s.retrieve(p['receipt'],start=2,end=2,index=index)['text']==f'second{NATIVE_NEWLINE}'
    with pytest.raises(ValueError):s.retrieve(p['receipt'],stream='stderr',index=index)
