import hashlib
import pytest
from helixengine.core.evidence import Store
from helixengine.core.renderer import assemble,publish


def plan(operations):return {'schema':'helix.copy.v1','operations':operations}
def ref(key,start,end):return {'source_sha256':key,'start_byte':start,'end_byte':end}


def test_exact_copy_binary_and_numeric_spelling(tmp_path):
    s=Store(tmp_path/'s');raw=b'\xff\x00 amount=000.100\r\n';key=s.put(raw)['sha256']
    out,r=assemble(s,plan([ref(key,0,len(raw)),{'literal_utf8':'\n'},ref(key,3,19)]))
    assert out==raw+b'\n'+raw[3:19]
    assert r['source_sha256']==[key]


@pytest.mark.parametrize('operation',[{'source_sha256':'0'*64,'start_byte':-1,'end_byte':2},{'source_sha256':'0'*64,'start_byte':False,'end_byte':2},{'path':'/tmp/a'},{'execute':'anything'}])
def test_invalid_plans_cannot_execute_or_read_paths(tmp_path,operation):
    with pytest.raises(ValueError):assemble(Store(tmp_path),plan([operation]))


def test_failed_late_operation_leaves_destination_unchanged(tmp_path):
    s=Store(tmp_path/'s');key=s.put(b'valid')['sha256'];dest=tmp_path/'output';dest.write_bytes(b'old')
    with pytest.raises(ValueError):publish(s,plan([ref(key,0,5),ref(key,0,6)]),dest,hashlib.sha256(b'old').hexdigest())
    assert dest.read_bytes()==b'old'


def test_publication_requires_matching_prior_version(tmp_path):
    s=Store(tmp_path/'s');dest=tmp_path/'output';p=plan([{'literal_utf8':'new'}])
    publish(s,p,dest)
    with pytest.raises(ValueError):publish(s,p,dest)
    assert dest.read_bytes()==b'new'
    publish(s,plan([{'literal_utf8':'next'}]),dest,hashlib.sha256(b'new').hexdigest())
    assert dest.read_bytes()==b'next'


def test_tampered_source_and_output_budget_rejected(tmp_path):
    s=Store(tmp_path/'s');key=s.put(b'original')['sha256']
    with pytest.raises(ValueError):assemble(s,plan([ref(key,0,8)]),max_output_bytes=3)
    (s.root/'objects'/key).write_bytes(b'tampered')
    with pytest.raises(ValueError):assemble(s,plan([ref(key,0,8)]))
