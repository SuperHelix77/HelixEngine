import itertools
import hashlib
import pytest
from helixengine.core.evidence import Store
from helixengine.core import copy_handles as h
from helixengine.core import renderer


def fixture(tmp_path):
    store = Store(tmp_path/'store')
    raw = b'\xff\x00amount=000.250\r\npermit=false\n'
    key = store.put(raw)['sha256']
    mapping = {str(i): {'source_sha256': key, 'start_byte': start, 'end_byte': end}
               for i,(start,end) in enumerate([(0,2),(2,18),(18,len(raw))])}
    ref, receipt = h.freeze(store, mapping)
    return store, raw, key, mapping, ref, receipt


def test_all_short_selections_equal_explicit_plans_including_order_and_duplicates(tmp_path):
    store, raw, key, mapping, ref, creation = fixture(tmp_path)
    assert creation['store_io']['object_bytes_read'] == len(raw)
    for n in range(4):
        for sequence in itertools.product(mapping, repeat=n):
            selection = [*sequence, {'literal_utf8': '\nexact 000.100'}]
            expected = {'schema':'helix.copy.v1', 'operations':[
                *[mapping[k] for k in sequence], {'literal_utf8':'\nexact 000.100'}]}
            assert h.expand(store, ref, selection) == expected
            actual, receipt = h.assemble(store, ref, selection)
            assert actual == renderer.assemble(store, expected)[0]
            assert receipt['selection_io']['object_bytes_read'] >= creation['catalog_bytes']


def test_failed_selection_and_late_literal_encoding_leave_destination_unchanged(tmp_path):
    store, _, _, _, ref, _ = fixture(tmp_path)
    dest=tmp_path/'dest';dest.write_bytes(b'old')
    digest=hashlib.sha256(b'old').hexdigest()
    for selection in [['0','missing'],['0',{'literal_utf8':'\ud800'}]]:
        with pytest.raises((ValueError,UnicodeError)):
            h.publish(store, ref, selection, dest, digest)
        assert dest.read_bytes()==b'old'


@pytest.mark.parametrize('selection', [[True], [0], [{'path':'/tmp/private'}], [{'execute':'anything'}], [{'sha256':'0'*64}]])
def test_invalid_selection_cannot_supply_paths_code_or_catalog_authority(tmp_path, selection):
    store, _, _, _, ref, _ = fixture(tmp_path)
    with pytest.raises(ValueError): h.assemble(store,ref,selection)


@pytest.mark.parametrize('target', ['catalog','source'])
def test_tampered_catalog_or_selected_source_rejected(tmp_path,target):
    store, _, key, _, ref, _ = fixture(tmp_path)
    (store.root/'objects'/(ref['sha256'] if target=='catalog' else key)).write_bytes(b'tampered')
    with pytest.raises(ValueError):h.assemble(store,ref,['0'])


def test_limits_and_destination_identity_preserved(tmp_path):
    store, _, _, _, ref, _ = fixture(tmp_path)
    with pytest.raises(ValueError):h.assemble(store,ref,['0','1'],max_operations=1)
    with pytest.raises(ValueError):h.assemble(store,ref,['0'],max_output_bytes=1)
    dest=tmp_path/'dest';h.publish(store,ref,['0'],dest)
    with pytest.raises(ValueError):h.publish(store,ref,['1'],dest)
    assert dest.read_bytes()==b'\xff\x00'


def test_generations_are_explicit_and_do_not_silently_remap_handles(tmp_path):
    store, raw, _, mapping, old, _ = fixture(tmp_path)
    mapping['0']=mapping['1']
    new,_=h.freeze(store,mapping)
    assert old!=new
    assert h.assemble(store,old,['0'])[0]==raw[:2]
    assert h.assemble(store,new,['0'])[0]==raw[2:18]


def test_bad_range_never_publishes_catalog(tmp_path):
    store=Store(tmp_path/'store');key=store.put(b'a')['sha256']
    before=set((store.root/'objects').iterdir())
    with pytest.raises(ValueError):h.freeze(store,{'x':{'source_sha256':key,'start_byte':0,'end_byte':2}})
    assert set((store.root/'objects').iterdir())==before


def test_caller_completion_does_not_require_model_generated_glue_or_hash(tmp_path):
    store,raw,_,_,ref,_=fixture(tmp_path)
    dest=tmp_path/'dest'
    response='["2","0",{"literal_utf8":"!"}]'
    receipt=h.complete_response(store,ref,response,dest)
    assert dest.read_bytes()==raw[18:]+raw[:2]+b'!'
    assert receipt['response_sha256']==hashlib.sha256(response.encode()).hexdigest()
    assert receipt['semantic_success'] is None


@pytest.mark.parametrize('response', ['```json\n["0"]\n```', '["0",NaN]',
    '[{"literal_utf8":"safe","literal_utf8":"changed"}]', '{"sha256":"forged"}', '["unknown"]'])
def test_bad_response_never_silently_repaired_or_published(tmp_path,response):
    store,_,_,_,ref,_=fixture(tmp_path)
    dest=tmp_path/'dest'
    with pytest.raises(ValueError):h.complete_response(store,ref,response,dest)
    assert not dest.exists()
