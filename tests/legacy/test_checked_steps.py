import os,sys,json
import pytest
from helixengine.core.evidence import Store
from helixengine.core.checked_steps import execute

NATIVE_NEWLINE=os.linesep


def step(name,code):return {'name':name,'argv':[sys.executable,'-c',code]}


def test_failure_is_not_masked_and_next_step_never_runs(tmp_path):
 s=Store(tmp_path/'s')
 r=execute(s,[step('check','import sys;print("verification failed");sys.exit(7)'),step('later','from pathlib import Path;Path("should_not_exist").write_text("ran",encoding="utf-8")')],tmp_path,'test')
 assert not r['process_success'] and r['steps'][0]['exit_code']==7
 assert r['unexecuted']==['later'] and not (tmp_path/'should_not_exist').exists()
 assert s.retrieve(r['steps'][0]['receipt'])['text']==f'verification failed{NATIVE_NEWLINE}'
 assert json.loads(s.get(r['sequence_receipt']['sha256']))['process_success'] is False


def test_all_success_preserves_individual_evidence(tmp_path):
 s=Store(tmp_path/'s');r=execute(s,[step('a','print("000.250")'),step('b','print("false")')],tmp_path,'test')
 assert r['process_success'] and not r['unexecuted']
 assert [s.retrieve(x['receipt'])['text'] for x in r['steps']]==[f'000.250{NATIVE_NEWLINE}',f'false{NATIVE_NEWLINE}']


def test_invalid_later_step_has_no_early_side_effect(tmp_path):
 with pytest.raises(ValueError):execute(Store(tmp_path/'s'),[step('a','from pathlib import Path;Path("early").touch()'),{'name':'b','argv':[]}],tmp_path,'test')
 assert not (tmp_path/'early').exists()


def test_timeout_stops_sequence(tmp_path):
 r=execute(Store(tmp_path/'s'),[step('wait','import time;time.sleep(10)'),step('b','print("bad")')],tmp_path,'test',timeout=.05)
 assert not r['process_success'] and r['steps'][0]['timed_out'] and r['unexecuted']==['b']


def test_semantic_failure_with_zero_exit_is_outside_guarantee(tmp_path):
 r=execute(Store(tmp_path/'s'),[step('broken_checker','print("AssertionError")')],tmp_path,'test')
 assert r['process_success']  # An explicit counterexample to interpreting this as semantic PASS.
 assert 'semantic' in r['scope']
