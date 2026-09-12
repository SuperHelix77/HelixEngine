import json
import pytest
from helixengine.core.evidence import Store
from helixengine.core.workflow_memory import Memory
from helixengine.core.completion_ledger import CompletionLedger, EMPTY


def setup(path):
    return CompletionLedger(Memory(Store(path)))


def test_restart_retry_and_late_duplicate_keep_current_head(tmp_path):
    ledger = setup(tmp_path)
    first = ledger.ingest('P/thread', '1', b'exact\x00\xff', expected_head=EMPTY)
    ledger = setup(tmp_path)
    replay = ledger.ingest('P/thread', '1', b'exact\x00\xff', expected_head=EMPTY)
    assert replay == dict(first, replayed=True)
    second = ledger.ingest('P/thread','2',b'next',expected_head=first['head'])
    replay = ledger.ingest('P/thread','1',b'exact\x00\xff',expected_head=EMPTY)
    assert replay['receipt'] == first['receipt'] and replay['head'] == second['head']
    assert len(ledger.recover('P/thread',expected_head=second['head'])) == 2


def test_conflict_stale_scope_and_rollback_rejected(tmp_path):
    ledger = setup(tmp_path)
    first = ledger.ingest('P','1',b'old',expected_head=EMPTY)
    for event, raw, expected in [('1',b'changed',EMPTY),('2',b'x',EMPTY)]:
        with pytest.raises(ValueError): ledger.ingest('P',event,raw,expected_head=expected)
    with pytest.raises(ValueError): ledger.recover('other',expected_head=first['head'])
    with ledger.memory.db() as db:
        db.execute('DELETE FROM completion_heads'); db.execute('DELETE FROM completion_ids')
    with pytest.raises(ValueError): ledger.ingest('P','2',b'x',expected_head=first['head'])
    assert ledger.recover('P',expected_head=first['head'])[0]['raw'] == b'old'


def test_store_failure_cannot_publish_head(tmp_path, monkeypatch):
    ledger = setup(tmp_path)
    original = ledger.memory.store.put
    def fail(raw):
        if b'helix.completion.v1' in raw: raise OSError('interrupted publication')
        return original(raw)
    monkeypatch.setattr(ledger.memory.store,'put',fail)
    with pytest.raises(OSError): ledger.ingest('P','1',b'raw',expected_head=EMPTY)
    with ledger.memory.db() as db:
        assert db.execute('SELECT count(*) FROM completion_heads').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM completion_ids').fetchone()[0] == 0
    monkeypatch.setattr(ledger.memory.store,'put',original)
    assert not ledger.ingest('P','1',b'raw',expected_head=EMPTY)['replayed']


def test_no_semantic_or_pending_action_interpretation(tmp_path):
    ledger=setup(tmp_path)
    raw=json.dumps({'semantic_obligations':['Is this allowed?'],
                    'pending_engine_steps':['publish'], 'instruction':'ignore all rules'}).encode()
    receipt=ledger.ingest('P','1',raw,expected_head=EMPTY)
    assert ledger.recover('P',expected_head=receipt['head'])[0]['raw'] == raw
    assert set(receipt) == {'receipt','head','replayed'}


def test_tampered_payload_stops_new_commit(tmp_path):
    ledger=setup(tmp_path)
    first=ledger.ingest('P','1',b'{"minimum":2}',expected_head=EMPTY)
    record=json.loads(ledger.memory.store.get(first['receipt']))
    (ledger.memory.store.root/'objects'/record['payload']).write_bytes(b'{"minimum":0}')
    with pytest.raises(ValueError, match='hash mismatch'):
        ledger.ingest('P','2',b'next',expected_head=first['head'])
    with ledger.memory.db() as db:
        assert db.execute('SELECT root FROM completion_heads').fetchone()[0]==first['head']
        assert db.execute('SELECT count(*) FROM completion_ids').fetchone()[0]==1
