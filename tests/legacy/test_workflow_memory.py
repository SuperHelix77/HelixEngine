import importlib
import pytest
from helixengine.core.evidence import Store


def memory(path):
    return importlib.import_module('helixengine.core.workflow_memory').Memory(Store(path))


def test_latent_fact_survives_restart_and_intervening_events(tmp_path):
    m=memory(tmp_path)
    first=m.record('project','session','1',b'Envelope label: cobalt-731. Preserve leading zero: 000.250.')
    for n in range(2,51):m.record('project','session',str(n),f'Routine task {n} completed'.encode())
    m=memory(tmp_path)
    found=m.search('project','cobalt')
    assert [x['event_id'] for x in found]==['1']
    assert m.retrieve('project',[first['record_hash']])[0]['raw']==b'Envelope label: cobalt-731. Preserve leading zero: 000.250.'


def test_project_isolation_applies_to_search_and_direct_retrieval(tmp_path):
    m=memory(tmp_path);ref=m.record('private','s','1',b'cobalt secret')
    assert m.search('other','cobalt')==[]
    with pytest.raises(ValueError):m.retrieve('other',[ref['record_hash']])


def test_idempotency_and_identity_collision(tmp_path):
    m=memory(tmp_path);a=m.record('p','s','1',b'exact')
    assert m.record('p','s','1',b'exact')==a
    with pytest.raises(ValueError):m.record('p','s','1',b'different')
    assert len(m.timeline('p','s'))==1


def test_binary_evidence_and_corruption(tmp_path):
    m=memory(tmp_path);a=m.record('p','s','1',b'error\xff\x00')
    assert m.retrieve('p',[a['record_hash']])[0]['raw']==b'error\xff\x00'
    (tmp_path/'objects'/a['source_hash']).write_bytes(b'tampered')
    with pytest.raises(ValueError):m.retrieve('p',[a['record_hash']])


def test_search_miss_can_expand_timeline_and_batch_is_all_or_error(tmp_path):
    m=memory(tmp_path);a=m.record('p','s','1',b'violet tag 729')
    assert m.search('p','purple')==[] # Lexical search is not semantic recall.
    assert m.timeline('p','s')[0]['record_hash']==a['record_hash']
    with pytest.raises(ValueError):m.retrieve('p',[a['record_hash'],'0'*64])
    with pytest.raises(ValueError):m.retrieve('p',[a['record_hash']],max_bytes=1)


def test_failed_indexing_rolls_back_event_publication(tmp_path):
    class Unindexable(bytes):
        def decode(self,*args,**kwargs):raise RuntimeError('injected indexing failure')
    m=memory(tmp_path)
    with pytest.raises(RuntimeError):m.record('p','s','1',Unindexable(b'raw is retained'))
    assert m.timeline('p','s')==[]
    with m.db() as db:assert db.execute('SELECT count(*) FROM search').fetchone()[0]==0
    # Retrying the same identity is allowed after failed publication.
    m.record('p','s','1',b'raw is retained')
    assert len(m.search('p','retained'))==1


def test_timeline_pages_do_not_skip_interleaved_projects(tmp_path):
    m=memory(tmp_path)
    for i in range(5):
        m.record('p','s',str(i),b'event')
        m.record('other','s',str(i),b'event')
    first=m.timeline('p','s',limit=2)
    second=m.timeline('p','s',after=first[-1]['ordinal'],limit=3)
    assert [x['event_id'] for x in first+second]==['0','1','2','3','4']


def test_tampered_index_identity_rejected(tmp_path):
    m=memory(tmp_path);m.record('p','s','1',b'evidence')
    with m.db() as db:db.execute("UPDATE events SET session='forged'")
    with pytest.raises(ValueError):m.search('p','evidence')


def test_replay_keeps_exact_text_with_one_shared_provenance_reference(tmp_path):
    import json
    m=memory(tmp_path)
    for i in range(3):m.record('p','s',str(i),f'value 000.{i}'.encode())
    packet=m.replay('p','s')
    assert packet['history']==[{'event_id':str(i),'text':f'value 000.{i}'} for i in range(3)]
    provenance=json.loads(m.store.get(packet['evidence']))
    assert len(provenance['records'])==3 and provenance['project']=='p'
    assert not packet['has_more']
    first=m.replay('p','s',limit=2)
    assert first['has_more']
    assert m.replay('p','s',after=first['next_cursor'])['history']==packet['history'][2:]


def test_replay_rejects_oversize_without_silent_truncation(tmp_path):
    m=memory(tmp_path);m.record('p','s','1',b'large')
    with pytest.raises(ValueError):m.replay('p','s',max_bytes=1)


@pytest.mark.parametrize('mutation',["DELETE FROM search", "UPDATE search SET body='nothing relevant'"])
def test_damaged_search_index_is_not_a_successful_empty_search(tmp_path,mutation):
    m=memory(tmp_path);m.record('p','s','1',b'decisive cobalt')
    with m.db() as db:db.execute(mutation)
    with pytest.raises(ValueError,match='index'):m.search('p','cobalt')


def test_index_rebuild_restores_search_from_verified_sources(tmp_path):
    m=memory(tmp_path);ref=m.record('p','s','1',b'decisive cobalt')
    with m.db() as db:db.execute('DELETE FROM search')
    result=m.rebuild_index('p')
    assert result['records']==1
    assert m.search('p','cobalt')[0]['record_hash']==ref['record_hash']


def test_failed_rebuild_preserves_previous_index(tmp_path):
    m=memory(tmp_path);ref=m.record('p','s','1',b'decisive cobalt')
    (tmp_path/'objects'/ref['source_hash']).write_bytes(b'corrupt')
    with pytest.raises(ValueError):m.rebuild_index('p')
    with m.db() as db:assert db.execute('SELECT body FROM search').fetchone()[0]=='decisive cobalt'
