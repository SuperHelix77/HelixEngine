import copy, sqlite3, sys
import pytest
from helixengine.core.evidence import Store, run
from helixengine.core.verification import verify, publish


def fixture(tmp_path):
    store = Store(tmp_path/'store')
    candidate = run(store, [sys.executable, '-c', 'print("____ test_copy ____\\nE  expected 000.100\\nFAILED test_copy\\n==== 1 failed in 0.1s ====")'], tmp_path, 'fixture', kind='pytest')
    return store, candidate


@pytest.mark.parametrize('mutation', ['exit', 'text', 'counts', 'omissions', 'span', 'hash'])
def test_verifier_rejects_corruption(tmp_path, mutation):
    store, candidate = fixture(tmp_path)
    assert verify(store, candidate)['verified']
    if mutation == 'exit': candidate['exit_code'] = 9
    elif mutation == 'text': candidate['streams']['stdout']['diagnostics'][0]['text'] = 'E  expected 0.1'
    elif mutation == 'counts': candidate['streams']['stdout']['summary_candidates'] = []
    elif mutation == 'omissions': candidate['streams']['stdout']['diagnostics'] = []
    elif mutation == 'span': candidate['streams']['stdout']['failure_section_index'][0]['end'] = 1
    elif mutation == 'hash': candidate['raw']['stdout'] = {'sha256': '0'*64, 'bytes': 1}
    with pytest.raises(ValueError): verify(store, candidate)


def test_failed_publication_does_not_replace_state(tmp_path):
    store, candidate = fixture(tmp_path)
    first = publish(store, 'latest', candidate, 0)
    bad = copy.deepcopy(candidate); bad['exit_code'] = 22
    with pytest.raises(ValueError): publish(store, 'latest', bad, 1)
    with pytest.raises(ValueError): publish(store, 'latest', candidate, 0)
    with sqlite3.connect(store.root/'accepted.sqlite3') as db:
        assert db.execute('SELECT revision,object FROM accepted WHERE name=?', ('latest',)).fetchone() == (1, first['packet_sha256'])
    assert publish(store, 'latest', candidate, 1)['revision'] == 2


def test_explicit_omission_is_not_claimed_complete(tmp_path):
    store = Store(tmp_path/'store')
    candidate = run(store, [sys.executable, '-c', 'print("ERROR " + "x"*20000)'], tmp_path, 'fixture')
    assert verify(store, candidate)['verified']
    candidate.pop('retrieval_required')
    with pytest.raises(ValueError): verify(store, candidate)


def test_unicode_separator_uses_same_lines_as_exact_retrieval(tmp_path):
    store = Store(tmp_path/'store')
    text = 'note\u2028still same source line\nERROR exact=000.100'
    candidate = run(store, [sys.executable, '-c', f'print({text!r})'], tmp_path, 'fixture')
    assert verify(store,candidate)['verified']
    assert candidate['streams']['stdout']['diagnostics'][0]['line']==2
    assert store.retrieve(candidate['receipt'],start=2,end=2)['text']=='ERROR exact=000.100\n'


@pytest.mark.parametrize('field,value', [('exit_code',False),('exit_code',0.0),('timed_out',0),('interrupted',0)])
def test_metadata_types_cannot_be_coerced(tmp_path,field,value):
    store,candidate=fixture(tmp_path)
    candidate[field]=value
    with pytest.raises(ValueError):verify(store,candidate)


def test_nested_numeric_types_are_exact(tmp_path):
    store,candidate=fixture(tmp_path)
    candidate['streams']['stdout']['failure_section_index'][0]['start']=True
    with pytest.raises(ValueError):verify(store,candidate)


def test_boolean_omission_is_not_integer_count(tmp_path):
    store,candidate=fixture(tmp_path)
    candidate['streams']['stdout']['diagnostic_lines_omitted']=False
    with pytest.raises(ValueError):verify(store,candidate)


def test_type_corruption_preserves_accepted_state(tmp_path):
    store,candidate=fixture(tmp_path)
    first=publish(store,'latest',candidate,0)
    invalid=copy.deepcopy(candidate);invalid['exit_code']=False
    with pytest.raises(ValueError):publish(store,'latest',invalid,1)
    with pytest.raises(ValueError):publish(store,'latest',candidate,True)
    with sqlite3.connect(store.root/'accepted.sqlite3') as db:
        assert db.execute('SELECT revision,object FROM accepted WHERE name=?',('latest',)).fetchone()==(1,first['packet_sha256'])
