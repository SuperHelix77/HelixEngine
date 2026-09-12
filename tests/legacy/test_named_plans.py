import importlib.util,json,os,sys
from pathlib import Path
import pytest
from helixengine.core.evidence import Store

NATIVE_NEWLINE=os.linesep


def _write_text(path,text):
    path.write_text(text,encoding='utf-8')


def api():
    assert importlib.util.find_spec('helixengine.core.named_plans') is not None, 'named-plan API not implemented'
    from helixengine.core import named_plans
    return named_plans


def setup(tmp_path,code='from pathlib import Path;print(Path("input.txt").read_text())'):
    root=tmp_path/'project';root.mkdir()
    _write_text(root/'input.txt','000.250')
    _write_text(root/'job.py',code)
    _write_text(root/'schema.json','{"type":"string"}')
    _write_text(root/'config.json','{"mode":"exact"}')
    store=Store(tmp_path/'store')
    opts=dict(cwd=root,steps=[{'name':'job','argv':['python','-I','-S','job.py']}],files={'input.txt':'input','job.py':'script','schema.json':'schema','config.json':'config'},executables={'python':sys.executable},env_names=['HELIX_TEST'],environment={'HELIX_TEST':'secret-test-value'})
    ref=api().register(store,'sample',1,**opts)
    return store,root,opts,ref


def test_identity_is_immutable_and_versions_coexist(tmp_path):
    s,root,opts,ref=setup(tmp_path)
    assert ref['plan_id']=='sample' and ref['plan_version']==1 and len(ref['plan_hash'])==64
    assert api().register(s,'sample',1,**opts)==ref
    _write_text(root/'input.txt','changed')
    with pytest.raises(ValueError,match='identity'):api().register(s,'sample',1,**opts)
    other=api().register(s,'sample',2,**opts)
    assert other['plan_hash']!=ref['plan_hash']
    assert api().load(s,ref)['plan_version']==1
    assert 'secret-test-value' not in s.get(ref['plan_hash']).decode()


def test_exact_execution_and_success_publication(tmp_path):
    s,root,opts,ref=setup(tmp_path)
    r=api().invoke(s,ref,environment=opts['environment'])
    assert r['status']=='SUCCEEDED' and r['semantic_success'] is None
    assert api().latest_success(s,ref)==r['attempt_hash']
    assert s.retrieve(r['steps'][0]['receipt'])['text']==f'000.250{NATIVE_NEWLINE}'
    assert r['costs']['validation']['bytes_read']>0
    assert r['costs']['snapshot']['bytes_written']>0
    assert r['costs']['native_input_tokens'] is None
    assert api().creation_cost(s,ref)['bytes_hashed']>0


@pytest.mark.parametrize('file',['input.txt','job.py','schema.json','config.json'])
def test_changed_declared_file_fails_before_execution(tmp_path,file):
    s,root,opts,ref=setup(tmp_path)
    _write_text(root/file,'changed')
    r=api().invoke(s,ref,environment=opts['environment'])
    assert r['status']=='FAILED' and r['steps']==[]
    assert api().latest_success(s,ref) is None


def test_environment_is_bound_and_only_declared_values_reach_child(tmp_path):
    s,root,opts,ref=setup(tmp_path,'import os;print(os.environ.get("HELIX_TEST"));print(os.environ.get("UNDECLARED_SECRET"))')
    r=api().invoke(s,ref,environment={'HELIX_TEST':'changed'})
    assert r['status']=='FAILED' and not r['steps']
    r=api().invoke(s,ref,environment={**opts['environment'],'UNDECLARED_SECRET':'do-not-inherit'})
    assert r['status']=='SUCCEEDED'
    assert s.retrieve(r['steps'][0]['receipt'])['text']==f'secret-test-value{NATIVE_NEWLINE}None{NATIVE_NEWLINE}'


def test_changed_executable_is_rejected(tmp_path):
    s,root,opts,ref=setup(tmp_path)
    exe=tmp_path/'executable';exe.write_bytes(Path(sys.executable).resolve().read_bytes());exe.chmod(0o700)
    opts['executables']={'python':str(exe)}
    ref=api().register(s,'copy-exe',1,**opts)
    exe.write_bytes(b'changed')
    r=api().invoke(s,ref,environment=opts['environment'])
    assert r['status']=='FAILED' and not r['steps']


def test_tampered_manifest_cannot_execute(tmp_path):
    s,root,opts,ref=setup(tmp_path)
    (s.root/'objects'/ref['plan_hash']).write_bytes(b'{}')
    with pytest.raises(ValueError):api().invoke(s,ref,environment=opts['environment'])


def test_nonzero_step_keeps_last_success_and_retains_failure(tmp_path):
    s,root,opts,ref=setup(tmp_path)
    first=api().invoke(s,ref,environment=opts['environment'])
    # Same immutable plan, later failure caused by a task-owned external condition.
    # This tests publication, not undeclared-dependency applicability.
    _write_text(root/'job.py','import sys;print("failed evidence");sys.exit(7)')
    bad=api().register(s,'sample',2,**opts)
    r=api().invoke(s,bad,environment=opts['environment'])
    assert r['status']=='FAILED' and r['steps'][0]['exit_code']==7
    assert api().latest_success(s,ref)==first['attempt_hash']
    assert api().latest_success(s,bad) is None
    assert s.retrieve(r['steps'][0]['receipt'])['text']==f'failed evidence{NATIVE_NEWLINE}'


def test_original_edit_between_steps_invalidates_even_if_restored(tmp_path):
    s,root,opts,ref=setup(tmp_path)
    path=str(root/'input.txt')
    _write_text(root/'job.py','from pathlib import Path\np=Path('+repr(path)+')\nb=p.read_bytes()\np.write_bytes(b"other")\np.write_bytes(b)\n')
    opts['steps'].append({'name':'must-not-run','argv':['python','-c','from pathlib import Path;Path("bad").touch()']})
    ref=api().register(s,'race',1,**opts)
    r=api().invoke(s,ref,environment=opts['environment'])
    assert r['status']=='FAILED' and len(r['steps'])==1
    assert not (Path(r['workspace'])/'bad').exists()
    assert api().latest_success(s,ref) is None


def test_snapshot_change_is_not_published(tmp_path):
    s,root,opts,ref=setup(tmp_path,'from pathlib import Path;Path("input.txt").write_text("mutated",encoding="utf-8")')
    r=api().invoke(s,ref,environment=opts['environment'])
    assert r['status']=='FAILED' and api().latest_success(s,ref) is None
    assert (root/'input.txt').read_text()=='000.250'


def test_timeout_cannot_publish_success(tmp_path):
    s,root,opts,ref=setup(tmp_path,'import time;time.sleep(10)')
    r=api().invoke(s,ref,environment=opts['environment'],timeout=.05)
    assert r['status']=='FAILED' and r['steps'][0]['timed_out']


def test_invalid_later_step_and_symlink_are_rejected_at_registration(tmp_path):
    s,root,opts,ref=setup(tmp_path)
    opts['steps'].append({'name':'invalid','argv':['unbound-executable']})
    with pytest.raises(ValueError):api().register(s,'invalid',1,**opts)
    opts['steps'].pop()
    (root/'link').symlink_to(root/'input.txt');opts['files']['link']='input'
    with pytest.raises(ValueError):api().register(s,'symlink',1,**opts)


@pytest.mark.parametrize('name',[None,1,'./input.txt','folder/../input.txt','folder//file','input.txt/'])
def test_dependency_paths_require_canonical_strings(tmp_path,name):
    from helixengine.core import plan_dependencies as dep
    with pytest.raises(ValueError):dep.local_path(tmp_path,name)


def test_database_context_closes_connection(tmp_path):
    import sqlite3
    s=Store(tmp_path/'store')
    with api().database(s) as db:assert db.execute('SELECT 1').fetchone()==(1,)
    with pytest.raises(sqlite3.ProgrammingError):db.execute('SELECT 1')


def test_source_changed_while_archiving_attempt_cannot_publish_success(tmp_path,monkeypatch):
    s,root,opts,ref=setup(tmp_path)
    first=api().invoke(s,ref,environment=opts['environment'])
    put=s.put
    def change_on_receipt(data):
        result=put(data)
        if b'"schema":"helix.plan_attempt.v1"' in data:
            _write_text(root/'input.txt','changed during publication')
        return result
    monkeypatch.setattr(s,'put',change_on_receipt)
    result=api().invoke(s,ref,environment=opts['environment'])
    assert result['status']=='FAILED'
    assert api().latest_success(s,ref)==first['attempt_hash']
    assert s.receipt(result['attempt_hash'])['status']=='FAILED'


def test_registration_rechecks_dependency_closure(tmp_path,monkeypatch):
    s,root,opts,ref=setup(tmp_path)
    put=s.put
    def change_on_manifest(data):
        result=put(data)
        if b'"schema":"helix.named_plan.v1"' in data:
            _write_text(root/'input.txt','changed during registration')
        return result
    monkeypatch.setattr(s,'put',change_on_manifest)
    with pytest.raises(ValueError,match='invalidated'):
        api().register(s,'new-plan',1,**opts)
    with api().database(s) as db:
        assert db.execute('SELECT count(*) FROM plans WHERE id=?',('new-plan',)).fetchone()[0]==0


def test_declared_sources_recoverable_after_original_removed(tmp_path):
    s,root,opts,ref=setup(tmp_path)
    manifest=api().load(s,ref)
    expected=(root/'input.txt').read_bytes()
    (root/'input.txt').unlink()
    assert s.get(manifest['files']['input.txt']['identity']['sha256'])==expected


def test_release_explicitly_finished_workspace_inputs_keeps_outputs(tmp_path):
    s,root,opts,ref=setup(tmp_path,'from pathlib import Path;Path("output.txt").write_text("answer",encoding="utf-8");print("ok")')
    result=api().invoke(s,ref,environment=opts['environment'])
    workspace=Path(result['workspace'])
    assert (workspace/'input.txt').exists() # Invocation never implicitly cleans.
    released=api().release_inputs(s,ref,result['attempt_hash'])
    assert released['status']=='RELEASED' and released['bytes_removed']>0
    assert not (workspace/'input.txt').exists()
    assert (workspace/'output.txt').read_text()=='answer'
    assert s.get(api().load(s,ref)['files']['input.txt']['identity']['sha256'])==b'000.250'


def test_release_rejects_changed_snapshot_before_any_deletion(tmp_path):
    s,root,opts,ref=setup(tmp_path)
    result=api().invoke(s,ref,environment=opts['environment'])
    workspace=Path(result['workspace']);_write_text(workspace/'schema.json','changed')
    with pytest.raises(ValueError):api().release_inputs(s,ref,result['attempt_hash'])
    assert (workspace/'input.txt').exists()


def test_release_rejects_failed_attempt(tmp_path):
    s,root,opts,ref=setup(tmp_path,'raise RuntimeError("failure")')
    result=api().invoke(s,ref,environment=opts['environment'])
    with pytest.raises(ValueError):api().release_inputs(s,ref,result['attempt_hash'])
    assert (Path(result['workspace'])/'input.txt').exists()


def test_release_rejects_corrupt_archive_without_deletion(tmp_path):
    s,root,opts,ref=setup(tmp_path)
    result=api().invoke(s,ref,environment=opts['environment'])
    key=api().load(s,ref)['files']['input.txt']['identity']['sha256']
    (s.root/'objects'/key).write_bytes(b'corrupt')
    with pytest.raises(ValueError):api().release_inputs(s,ref,result['attempt_hash'])
    assert (Path(result['workspace'])/'config.json').exists()


def test_release_partial_filesystem_failure_is_reported(tmp_path,monkeypatch):
    s,root,opts,ref=setup(tmp_path)
    result=api().invoke(s,ref,environment=opts['environment'])
    original=Path.unlink
    def fail_input(path,*args,**kwargs):
        if path.name=='input.txt':raise PermissionError('test denial')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'unlink',fail_input)
    release=api().release_inputs(s,ref,result['attempt_hash'])
    assert release['status']=='PARTIAL' and release['errors']
    assert release['removed']==['config.json']
    assert api().latest_success(s,ref)==result['attempt_hash']


def test_explicit_input_rebind_preserves_old_plan_and_executes_new_data(tmp_path):
    s,root,opts,ref=setup(tmp_path)
    old=api().load(s,ref)
    _write_text(root/'input.txt','000.750')
    new=api().rebind_inputs(s,ref,2,environment=opts['environment'])
    assert new['plan_version']==2 and new['plan_hash']!=ref['plan_hash']
    assert api().load(s,ref)==old
    result=api().invoke(s,new,environment=opts['environment'])
    assert result['status']=='SUCCEEDED'
    assert s.retrieve(result['steps'][0]['receipt'])['text']==f'000.750{NATIVE_NEWLINE}'


@pytest.mark.parametrize('name',['job.py','config.json','schema.json'])
def test_input_rebind_refuses_changed_logic_dependencies(tmp_path,name):
    s,root,opts,ref=setup(tmp_path)
    _write_text(root/name,'changed')
    with pytest.raises(ValueError):api().rebind_inputs(s,ref,2,environment=opts['environment'])
    with api().database(s) as db:
        assert db.execute('SELECT count(*) FROM plans').fetchone()[0]==1


def test_input_rebind_refuses_changed_environment_and_old_version(tmp_path):
    s,root,opts,ref=setup(tmp_path)
    with pytest.raises(ValueError):api().rebind_inputs(s,ref,2,environment={'HELIX_TEST':'different'})
    with pytest.raises(ValueError):api().rebind_inputs(s,ref,1,environment=opts['environment'])


def test_input_rebind_rechecks_logic_changed_during_registration(tmp_path,monkeypatch):
    from helixengine.core import plan_dependencies as dep
    s,root,opts,ref=setup(tmp_path)
    original=dep.read_file
    def change_logic(path,metrics):
        result=original(path,metrics)
        if path==root/'input.txt':_write_text(root/'job.py','print("different logic")')
        return result
    monkeypatch.setattr(dep,'read_file',change_logic)
    with pytest.raises(ValueError):api().rebind_inputs(s,ref,2,environment=opts['environment'])
    with api().database(s) as db:
        assert db.execute('SELECT count(*) FROM plans').fetchone()[0]==1
