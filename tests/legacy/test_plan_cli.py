import json
import os
import subprocess
import sys
from pathlib import Path
import helixengine

from .test_named_plans import setup


CLI='helixengine.core.plan_cli'


def call(store,*args):
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(Path(helixengine.__file__).resolve().parent.parent)
    result=subprocess.run([sys.executable,'-m',CLI,'--store',str(store.root),*args],cwd=store.root,env=environment,capture_output=True,text=True)
    return result,json.loads(result.stdout)


def reference(tmp_path,ref):
    path=tmp_path/'ref.json';path.write_text(json.dumps(ref));return str(path)


def test_cli_success_receipt_and_exact_expansion(tmp_path,monkeypatch):
    s,root,opts,ref=setup(tmp_path)
    monkeypatch.setenv('HELIX_TEST',opts['environment']['HELIX_TEST'])
    proc,packet=call(s,'run',reference(tmp_path,ref))
    assert proc.returncode==0 and packet['status']=='SUCCEEDED'
    assert packet['semantic_success'] is None
    assert len(proc.stdout.encode())<1800
    assert packet['steps'][0]['exit_code']==0 and packet['workspace']
    proc,detail=call(s,'receipt',packet['attempt_hash'])
    assert proc.returncode==0 and detail['steps'][0]['exit_code']==0
    assert s.retrieve(detail['steps'][0]['receipt'])['text']=='000.250\n'


def test_cli_invalidation_is_nonzero_and_does_not_run(tmp_path,monkeypatch):
    s,root,opts,ref=setup(tmp_path)
    monkeypatch.setenv('HELIX_TEST',opts['environment']['HELIX_TEST'])
    (root/'input.txt').write_text('changed')
    proc,packet=call(s,'run',reference(tmp_path,ref))
    assert proc.returncode==1 and packet['status']=='FAILED'
    assert packet['steps_completed']==0
    assert packet['attempt_hash']


def test_cli_unknown_reference_reports_error(tmp_path):
    s,root,opts,ref=setup(tmp_path)
    ref['plan_hash']='0'*64
    proc,packet=call(s,'run',reference(tmp_path,ref))
    assert proc.returncode==2 and packet['status']=='ERROR'


def test_cli_register_creates_immutable_reference_without_running(tmp_path):
    s,root,opts,ref=setup(tmp_path)
    spec={k:v for k,v in opts.items() if k!='environment'}
    spec.update(cwd=str(root),plan_id='cli-plan',plan_version=1,env_names=[])
    path=tmp_path/'spec.json';path.write_text(json.dumps(spec))
    proc,created=call(s,'register',str(path))
    assert proc.returncode==0 and created['plan_id']=='cli-plan'
    assert not (s.root/'plan-runs').exists()


def test_cli_rebinds_inputs_without_execution(tmp_path,monkeypatch):
    from helixengine.core import named_plans
    s,root,opts,ref=setup(tmp_path)
    monkeypatch.setenv('HELIX_TEST',opts['environment']['HELIX_TEST'])
    (root/'input.txt').write_text('000.750')
    proc,new=call(s,'rebind-inputs',reference(tmp_path,ref),'2')
    assert proc.returncode==0 and new['plan_version']==2
    assert named_plans.load(s,new)['parent_plan']==ref
    assert named_plans.creation_cost(s,new)['rebind_preflight']['validation']['bytes_read']>0
    assert not (s.root/'plan-runs').exists()
