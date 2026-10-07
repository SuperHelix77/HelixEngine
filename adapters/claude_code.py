#!/usr/bin/env python3
"""HELIX host adapter for Claude Code. Thin: it maps hook events onto helix-core operations and decides NONE of the policy.
Host operations: inject_context, intercept_tool, observe_boundary (consolidate). Reads the hook JSON on stdin, writes the hook JSON on stdout.
  python3 adapters/claude_code.py SessionStart|PreToolUse|PreCompact|Stop|SessionEnd|UserPromptSubmit
Print the settings snippet (never writes settings): python3 adapters/claude_code.py --print-settings"""
import os,sys,json,hashlib,subprocess
HOME=os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,os.path.join(HOME,'lib'))
import hmem,consolidate,intercept
def project_key(cwd): return 'p-'+hashlib.sha256(os.path.abspath(cwd).encode()).hexdigest()[:10]
def db_path(): return os.environ.get('HELIX_MEM_DB',os.path.join(HOME,'memory.db'))
def out(o): print(json.dumps(o))
def ctx_state(): 
    p=os.path.join(HOME,'run','ctx.json')
    try: return json.load(open(p))
    except Exception: return {}
def inject_context(event,text): out({'hookSpecificOutput':{'hookEventName':event,'additionalContext':text}})
def on_session_start(p):
    """once per session start/resume/clear/compact: the capsule replaces replayed history. Never per turn."""
    key=project_key(p.get('cwd','.')); t=consolidate.session_start_context(key,db_path())
    if t: inject_context('SessionStart','HELIX MEMORY (addressable; query with hmem q / hmem raw N):\n'+t)
def on_pre_tool_use(p):
    if p.get('tool_name')!='Bash': return
    ti=p.get('tool_input') or {}; cmd=ti.get('command','')
    new,sub=intercept.apply_bash(ti,ctx_state())
    if sub: 
        intercept.Ledger(os.path.join(HOME,'run','substitutions.jsonl')).record(sub)
        out({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'allow','updatedInput':new,'permissionDecisionReason':f"HELIX substitution: {sub['equivalence']}; loss: {sub['loss']}; fallback: {sub['fallback']}"}})
    else: intercept.Ledger(os.path.join(HOME,'run','substitutions.jsonl')).observe_request(cmd)
def on_boundary(p):
    """PreCompact / Stop / SessionEnd: archive + promote BEFORE any lossy compaction"""
    tp=p.get('transcript_path')
    if tp and os.path.exists(tp): consolidate.consolidate(tp,project_key(p.get('cwd','.')),db=db_path(),root=p.get('cwd','.'))
def on_user_prompt(p):
    """mid-work injection: only when scheduler state CHANGED since last emission (never a per-turn constant)"""
    sp=os.path.join(HOME,'run','state.txt'); mp=os.path.join(HOME,'run','state.emitted')
    try: txt=open(sp).read()
    except OSError: return
    h=hashlib.sha256(txt.encode()).hexdigest()[:12]
    if os.path.exists(mp) and open(mp).read().strip()==h: return
    open(mp,'w').write(h); inject_context('UserPromptSubmit',txt)
DISPATCH={'SessionStart':on_session_start,'PreToolUse':on_pre_tool_use,'PreCompact':on_boundary,'Stop':on_boundary,'SessionEnd':on_boundary,'UserPromptSubmit':on_user_prompt}
def default_py(): return os.environ.get('HELIX_PYTHON') or ('/usr/bin/python3' if os.path.exists('/usr/bin/python3') else sys.executable)
def settings_snippet(py=None):
    py=py or default_py()
    c=lambda ev:{'type':'command','command':f'{py} {os.path.join(HOME,"adapters","claude_code.py")} {ev}','timeout':20}
    return {'hooks':{'SessionStart':[{'matcher':'resume|clear|compact','hooks':[c('SessionStart')]}],'PreToolUse':[{'matcher':'Bash','hooks':[c('PreToolUse')]}],
                     'PreCompact':[{'hooks':[c('PreCompact')]}],'Stop':[{'hooks':[c('Stop')]}],'UserPromptSubmit':[{'hooks':[c('UserPromptSubmit')]}]}}
MARK='adapters/claude_code.py'
def _rtk():
    import shutil; return shutil.which('rtk')
def wanted_hooks():
    h=settings_snippet()['hooks']; r=_rtk()
    if r: h['PreToolUse'][0]['hooks'].insert(0,{'type':'command','command':f'{r} hook claude','timeout':5})
    return h
def _ours(cmd): return MARK in cmd or cmd.endswith(' hook claude')
def install_hooks(path,print_only=False):
    """merge Helix hooks into a Claude settings file: backup first, idempotent, never touches other hooks"""
    s=json.load(open(path)) if os.path.exists(path) else {}
    hk=s.setdefault('hooks',{})
    for ev,groups in wanted_hooks().items():
        cur=hk.setdefault(ev,[])
        for g in groups:
            tgt=next((x for x in cur if x.get('matcher')==g.get('matcher')),None)
            if tgt is None: cur.append(g); continue
            for h in g['hooks']:
                if not any(y.get('command')==h['command'] for y in tgt['hooks']): tgt['hooks'].append(h)
    if print_only: return json.dumps(s,indent=2)
    if os.path.exists(path):
        import time,shutil; shutil.copy(path,f"{path}.bak-helix-{time.strftime('%Y%m%d%H%M%S')}")
    os.makedirs(os.path.dirname(path) or '.',exist_ok=True); json.dump(s,open(path,'w'),indent=2); return path
def uninstall_hooks(path):
    s=json.load(open(path)); hk=s.get('hooks',{}); n=0
    for ev in list(hk):
        for g in hk[ev]:
            keep=[h for h in g['hooks'] if not _ours(h.get('command',''))]; n+=len(g['hooks'])-len(keep); g['hooks']=keep
        hk[ev]=[g for g in hk[ev] if g['hooks']]
        if not hk[ev]: del hk[ev]
    if not hk: s.pop('hooks',None)
    import time,shutil; shutil.copy(path,f"{path}.bak-helix-{time.strftime('%Y%m%d%H%M%S')}"); json.dump(s,open(path,'w'),indent=2); return n
def main():
    a=sys.argv[1:]
    if a[:1]==['--print-settings']: print(json.dumps(settings_snippet(),indent=1)); return
    if a[:1]==['hooks']:
        sub=(a[1] if len(a)>1 and not a[1].startswith('--') else 'print'); path=a[a.index('--settings')+1] if '--settings' in a else os.path.expanduser('~/.claude/settings.json')
        if sub=='print': print(json.dumps(wanted_hooks(),indent=1)); return
        if sub=='install': print('hooks installed into',install_hooks(path),'(backup alongside; undo: helix hooks uninstall)'); return
        if sub=='uninstall': print('removed',uninstall_hooks(path),'Helix hook entries from',path); return
        sys.exit('usage: helix hooks [print|install|uninstall] [--settings FILE]')
    ev=a[0] if a else ''
    try: p=json.load(sys.stdin)
    except Exception: p={}
    fn=DISPATCH.get(ev or p.get('hook_event_name',''))
    if fn:
        try: fn(p)
        except Exception as e: sys.stderr.write(f'helix adapter {ev}: {type(e).__name__}: {e}\n')   # a hook must never break the host session
if __name__=='__main__': main()
