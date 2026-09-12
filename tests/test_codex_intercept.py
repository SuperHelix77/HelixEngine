import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from helixengine.codex_intercept import hook, route
from helixengine.runtime import Runtime
from helixengine.state import State


def test_router_preserves_unknown_and_shell_semantics():
    for command in ['echo hi', 'git status; touch x', 'rg "$HOME" x', 'pytest --pdb', 'pytest -s', 'git diff | head', 'python3 script.py', 'pytest *.py', 'pytest\nwhoami']:
        assert route(command) is None
    assert route('git status --short')['kind'] == 'generic'
    assert route('python3 -m pytest -q')['kind'] == 'pytest'


def test_router_compound_is_strict_and_preserves_leaf_spelling():
    selected = route('git status --short  &&  git diff --stat')
    assert [leaf['source'] for leaf in selected['leaves']] == [
        'git status --short  ',
        '  git diff --stat',
    ]
    for command in [
        'git status ' + 'x' * 32750 + ' && git status',
        'git status && echo unknown',
        'git status || git diff',
        'git status ; git diff',
        'git status | git diff',
        'git status > out && git diff',
        'FOO=bar git status && git diff',
        'git "status && still quoted" && git diff',
        "git 'status && still quoted' && git diff",
        'git status && git diff &&& git log',
    ]:
        assert route(command) is None


def _fake_rg(bin_dir, marker, fail_arg=None):
    executable = bin_dir / 'rg'
    failure = '' if fail_arg is None else f'\nif sys.argv[1] == {fail_arg!r}: sys.exit(7)\n'
    executable.write_text(
        '#!' + sys.executable + '\n'
        'import os, pathlib, sys\n'
        'pathlib.Path(os.environ["HELIX_CHAIN_MARKER"]).open("a").write(sys.argv[1] + "\\n")\n'
        'sys.stdout.write(sys.argv[1] + "\\n")\n' + failure
    )
    executable.chmod(0o755)
    return marker


def test_compound_engine_leaves_run_once_in_order_with_bounded_identity(tmp_path, monkeypatch):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    marker = tmp_path / 'order'
    _fake_rg(bin_dir, marker)
    monkeypatch.setenv('PATH', str(bin_dir) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('HELIX_CHAIN_MARKER', str(marker))
    event = {
        'hook_event_name': 'PreToolUse',
        'tool_name': 'Bash',
        'session_id': 'parent-session',
        'agent_id': 'child-thread',
        'turn_id': 'turn-1',
        'tool_use_id': 'same-tool-use',
        'cwd': str(tmp_path),
        'tool_input': {'command': 'rg first && rg second'},
    }
    rewritten = hook(event, tmp_path / 'data')['hookSpecificOutput']['updatedInput']['command']
    assert rewritten.count('command -v') == 4
    proc = subprocess.run(['/bin/sh', '-c', rewritten], cwd=tmp_path, capture_output=True)
    assert proc.returncode == 0
    assert proc.stdout == b'first\nsecond\n' and proc.stderr == b''
    assert marker.read_text() == 'first\nsecond\n'

    state = State(tmp_path / 'data').snapshot()
    assert state['total_runs'] == 2
    with State(tmp_path / 'data').db() as db:
        executed = [
            json.loads(row['body'])
            for row in db.execute(
                "SELECT body FROM events WHERE kind='CODEX_EXECUTED' ORDER BY id"
            )
        ]
    assert [item['leaf_ordinal'] for item in executed] == [0, 1]
    assert all(item['thread_id'] == 'child-thread' for item in executed)
    assert all(item['tool_use_id'] == 'same-tool-use' for item in executed)
    runtime = Runtime(tmp_path / 'data')
    try:
        identities = {
            runtime.store.receipt(row['receipt'])['environment_id']
            for row in state['runs']
        }
    finally:
        runtime.close()
    assert identities == {
        'codex:child-thread:same-tool-use:leaf:0',
        'codex:child-thread:same-tool-use:leaf:1',
    }


def test_compound_engine_keeps_shell_short_circuit_on_nonzero_leaf(tmp_path, monkeypatch):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    marker = tmp_path / 'order'
    _fake_rg(bin_dir, marker, fail_arg='first')
    monkeypatch.setenv('PATH', str(bin_dir) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('HELIX_CHAIN_MARKER', str(marker))
    event = {
        'hook_event_name': 'PreToolUse',
        'tool_name': 'Bash',
        'session_id': 'session',
        'tool_use_id': 'tool',
        'cwd': str(tmp_path),
        'tool_input': {'command': 'rg first && rg second'},
    }
    rewritten = hook(event, tmp_path / 'data')['hookSpecificOutput']['updatedInput']['command']
    proc = subprocess.run(['/bin/sh', '-c', rewritten], cwd=tmp_path, capture_output=True)
    assert proc.returncode == 7 and proc.stdout == b'first\n' and proc.stderr == b''
    assert marker.read_text() == 'first\n'
    assert State(tmp_path / 'data').snapshot()['total_runs'] == 1


def test_compound_function_resolution_falls_back_as_one_native_chain(tmp_path):
    event = {
        'hook_event_name': 'PreToolUse',
        'tool_name': 'Bash',
        'session_id': 'session',
        'tool_use_id': 'tool',
        'cwd': str(tmp_path),
        'tool_input': {'command': 'git status && git diff'},
    }
    output = hook(event, tmp_path / 'data')
    rewritten = output['hookSpecificOutput']['updatedInput']['command']
    (tmp_path / 'sub').mkdir()
    shell = (
        'git() { if [ "$1" = status ]; then cd sub; printf ready > relative.txt; '
        'else cat relative.txt; fi; }; ' + rewritten
    )
    proc = subprocess.run(['/bin/sh', '-c', shell], cwd=tmp_path, capture_output=True)
    assert proc.returncode == 0 and proc.stdout == b'ready' and proc.stderr == b''
    assert (tmp_path / 'sub' / 'relative.txt').read_text() == 'ready'
    assert State(tmp_path / 'data').snapshot()['total_runs'] == 0


def test_compound_unknown_leaf_remains_entirely_native(tmp_path, monkeypatch):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    marker = tmp_path / 'native'
    _fake_rg(bin_dir, marker)
    monkeypatch.setenv('PATH', str(bin_dir) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('HELIX_CHAIN_MARKER', str(marker))
    command = 'rg first && printf second'
    event = {
        'hook_event_name': 'PreToolUse',
        'tool_name': 'Bash',
        'session_id': 'session',
        'cwd': str(tmp_path),
        'tool_input': {'command': command},
    }
    assert hook(event, tmp_path / 'data') == {}
    proc = subprocess.run(['/bin/sh', '-c', command], cwd=tmp_path, capture_output=True)
    assert proc.returncode == 0 and proc.stdout == b'first\nsecond' and proc.stderr == b''
    assert marker.read_text() == 'first\n'
    assert State(tmp_path / 'data').snapshot()['total_runs'] == 0


def test_shared_adapter_records_parent_child_without_model_specific_rewrite(tmp_path):
    for model in ['gpt-6-astra', 'gpt-5.6-luna']:
        event = {'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'session_id': 'child', 'tool_use_id':'one', 'cwd':str(tmp_path), 'model':model, 'tool_input':{'command':'git status --short'}}
        output = hook(event,tmp_path/'data')
        assert output['hookSpecificOutput']['permissionDecision']=='allow'
        assert 'codex_intercept.py' in output['hookSpecificOutput']['updatedInput']['command']
    hook({'hook_event_name':'SubagentStart','session_id':'parent','agent_id':'child'},tmp_path/'data')
    events=State(tmp_path/'data').snapshot()['events']
    assert any(x['kind']=='CODEX_SUBAGENTSTART' for x in events)


def test_alias_or_function_resolution_uses_native_command(tmp_path):
    out=hook({'hook_event_name':'PreToolUse','tool_name':'Bash','session_id':'x','cwd':str(tmp_path),'tool_input':{'command':'git status --short'}},tmp_path/'data')
    command=out['hookSpecificOutput']['updatedInput']['command']
    proc=subprocess.run(['/bin/sh','-c','git() { printf CUSTOM_NATIVE; }; '+command],cwd=tmp_path,capture_output=True)
    assert proc.returncode==0 and proc.stdout==b'CUSTOM_NATIVE'
    assert State(tmp_path/'data').snapshot()['total_runs']==0


def test_on_packet_reaches_cli_off_raw_and_recovery_exact(tmp_path):
    data=tmp_path/'data'
    argv=[sys.executable,'-m','helixengine','--data-dir',str(data),'run','--',sys.executable,'-c',"import sys; print('repeat'*10000);sys.stderr.write('diagnostic\\n');sys.exit(7)"]
    on=subprocess.run(argv,capture_output=True)
    assert on.returncode==7 and on.stderr==b''
    packet=json.loads(on.stdout)
    state=State(data);row=state.snapshot()['runs'][0]
    assert len(on.stdout)==row['visible_bytes'] < row['stdout_bytes']
    runtime=Runtime(data)
    try:
        receipt=runtime.store.receipt(row['receipt'])
        assert runtime.store.get(receipt['stdout']['sha256'])==b'repeat'*10000+b'\n'
        assert runtime.store.get(receipt['stderr']['sha256'])==b'diagnostic\n'
        current=state.settings();state.switch(False,current['revision'])
        off=subprocess.run(argv,capture_output=True)
        assert off.returncode==7 and off.stdout==b'repeat'*10000+b'\n' and off.stderr==b'diagnostic\n'
    finally:runtime.close()


def test_storage_denial_before_execution_preserves_native_command(tmp_path, monkeypatch):
    import base64
    from helixengine import codex_intercept as intercept
    import helixengine.runtime as runtime_module
    monkeypatch.chdir(tmp_path)
    argv=['git','status','--short']
    spec={'argv':argv,'cwd':str(tmp_path),'resolved':intercept.shutil.which('git'),'data_dir':str(tmp_path/'denied')}
    encoded=base64.urlsafe_b64encode(json.dumps(spec).encode()).decode()
    def denied(*args,**kwargs):raise PermissionError('sandbox storage unavailable')
    class NativeExec(Exception):pass
    calls=[]
    def native(file,args):
        calls.append((file,args));raise NativeExec()
    monkeypatch.setattr(runtime_module,'Runtime',denied)
    monkeypatch.setattr(intercept.os,'execvp',native)
    with pytest.raises(NativeExec):intercept.execute(encoded)
    assert calls==[('git',argv)]


def test_comments_native_and_other_input_fields_retained(tmp_path):
    assert route('git status # note') is None
    event={'hook_event_name':'PreToolUse','tool_name':'Bash','session_id':'x','cwd':str(tmp_path),
           'tool_input':{'command':'git status --short','timeout_ms':900,'tty':False}}
    rewritten=hook(event,tmp_path/'data')['hookSpecificOutput']['updatedInput']
    assert rewritten['timeout_ms']==900 and rewritten['tty'] is False


@pytest.mark.parametrize('failure',['archive','receipt','finish','packet'])
def test_completed_command_survives_publication_failure_once(tmp_path, monkeypatch, failure):
    runtime=Runtime(tmp_path/'data')
    marker=tmp_path/'executions'
    argv=[sys.executable,'-c',"import pathlib,sys;p=pathlib.Path(sys.argv[1]);p.write_text(p.read_text()+'x' if p.exists() else 'x');print('data'*2000);sys.stderr.write('err');sys.exit(7)",str(marker)]
    def broken(*args,**kwargs):raise OSError('injected publication failure')
    if failure=='archive':monkeypatch.setattr(runtime.store,'put',broken)
    elif failure=='receipt':monkeypatch.setattr(runtime.store,'receipt',broken)
    elif failure=='finish':monkeypatch.setattr(runtime.state,'finish',broken)
    try:
        result=runtime.run(argv,tmp_path)
        if failure=='packet':monkeypatch.setattr(runtime.store,'get',broken)
        out,err=runtime.visible_output(result)
        assert result['exit_code']==7 and marker.read_text()=='x'
        if failure!='finish':assert out==b'data'*2000+b'\n' and err==b'err'
        assert result.get('publication_error') or result.get('delivery_error')
    finally:runtime.close()


@pytest.mark.skipif(os.name!='posix',reason='POSIX native process group')
@pytest.mark.parametrize('leaf_count', [1, 2])
def test_intercept_preserves_stdin_environment_and_native_group(tmp_path,monkeypatch,leaf_count):
    import base64
    import signal
    import time
    from helixengine import codex_intercept as ci
    bin_dir=tmp_path/'bin';bin_dir.mkdir();exe=bin_dir/'rg'
    exe.write_text('#!'+sys.executable+'\nimport os,sys,json\nprint(json.dumps([os.getcwd(),os.environ.get("HELIX_NATIVE_TEST"),sys.stdin.read(),os.getpgrp()]))\n')
    exe.chmod(0o755)
    monkeypatch.setenv('PATH',str(bin_dir)+os.pathsep+os.environ['PATH'])
    monkeypatch.setenv('HELIX_NATIVE_TEST','exact value')
    event={'hook_event_name':'PreToolUse','tool_name':'Bash','session_id':'parent','agent_id':'child','cwd':str(tmp_path),'tool_input':{'command':' && '.join(['rg needle'] * leaf_count)}}
    command=hook(event,tmp_path/'data')['hookSpecificOutput']['updatedInput']['command']
    p=subprocess.Popen(['/bin/sh','-c',command],cwd=tmp_path,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    out,err=p.communicate(b'exact stdin\n',timeout=5)
    assert p.returncode==0 and err==b''
    values = [json.loads(line) for line in out.splitlines()]
    assert values == [[str(tmp_path),'exact value','exact stdin\n' if i == 0 else '',p.pid] for i in range(leaf_count)]
    events=State(tmp_path/'data').snapshot()
    with State(tmp_path/'data').db() as db:
        row=db.execute("SELECT body FROM events WHERE kind='CODEX_EXECUTED'").fetchone()
    assert json.loads(row['body'])['thread_id']=='child'


def test_session_scope_includes_children_excludes_other_sessions(tmp_path):
    base={'hook_event_name':'PreToolUse','tool_name':'Bash','cwd':str(tmp_path),'tool_input':{'command':'git status --short'}}
    assert hook({**base,'session_id':'other'},tmp_path/'unused','parent')=={}
    assert not (tmp_path/'unused').exists()
    out=hook({**base,'session_id':'parent','agent_id':'child'},tmp_path/'data','parent')
    assert out['hookSpecificOutput']['updatedInput']['command']
