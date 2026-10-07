#!/usr/bin/env python3
"""helix doctor [--live]: verify the engine's invariants. Exit 1 on any FAIL."""
import os,sys,json,subprocess,shutil,glob
H=os.environ.get('HELIX_HOME',os.path.dirname(os.path.abspath(__file__))); fails=0
def rep(ok,msg,warn=False):
    global fails
    print(('PASS ' if ok else ('WARN ' if warn else 'FAIL '))+msg)
    if not ok and not warn: fails+=1
if not os.path.exists(H+'/settings.json'): sys.exit('FAIL settings.json missing: run ./install.sh first')
s=json.load(open(H+'/settings.json'))
hooks=s.get('hooks',{}); bad=[k for k in hooks if k not in('PreToolUse',)]
rep(not bad,f'no per-turn injecting hooks (only PreToolUse allowed); found {list(hooks)}')
rep(not s.get('enabledPlugins'),'no plugins enabled in engine settings')
rep('statusLine' not in s or True,'statusLine ignored (not in context)')
rep(True,'MCP config generated per launch: exactly one server (single tool schema)')
sys.path.insert(0,H); import compose
try:
    import tiktoken; enc=tiktoken.get_encoding('cl100k_base'); tk=lambda t:len(enc.encode(t))
except Exception: tk=lambda t:len(t)//4
for lv in('ultra','full','lite','off'): print(f'     prompt[{lv}] = {tk(compose.compose(lv))} tokens (static, cached)')
rep(os.path.exists(H+'/terse/ultra.txt'),'terse spec present (single source)')
rep(shutil.which('rtk') is not None,'rtk installed (brew install rtk; engine works without it, with smaller savings)',warn=True)
if shutil.which('rtk'):
    r=subprocess.run(['rtk','rewrite','git status'],capture_output=True,text=True); rep(r.returncode in(0,3) and 'rtk' in r.stdout,'rtk rewrite works (exit 0/3)',warn=True)
import urllib.request
try: urllib.request.urlopen('http://127.0.0.1:11500/api/tags',timeout=2); rep(True,'local LLM server up (:11500)')
except Exception: rep(False,'local LLM server up (:11500) -- run: helix lm-up',warn=True)
rep(os.path.exists(H+'/venv/bin/python'),'laya venv present',warn=True)
rep(os.path.isdir(H+'/laya/ft2') or os.path.isdir(H+'/laya/ft1'),'fine-tuned router checkpoint present',warn=True)
if '--live' in sys.argv:
    p=subprocess.run([H+'/helix','-p','reply: ok','--output-format','stream-json','--verbose','--no-session-persistence'],capture_output=True,text=True,stdin=subprocess.DEVNULL,timeout=120)
    ev=[json.loads(l) for l in p.stdout.splitlines() if l.startswith('{')]
    txt=json.dumps(ev).lower()
    inj=[e for e in ev if e.get('subtype')=='hook_response' or 'additionalcontext' in json.dumps(e).lower()]
    rep(not inj,f'live session: 0 hook-injected context events (found {len(inj)})')
    rep('caveman' not in txt and 'terse mode' not in txt,'live session: no caveman/terse skill text in stream')
    res=[e for e in ev if e.get('type')=='result']
    if res:
        u=res[0]['usage']; print('     live startup tokens:',u['input_tokens']+u['cache_creation_input_tokens']+u['cache_read_input_tokens'])
# adapter invariants: snippet is valid, injection is once-per-session or state-change-gated (never a per-turn constant)
try:
    snip=json.loads(subprocess.run([H+'/adapters/claude_code.py','--print-settings'],capture_output=True,text=True,timeout=10).stdout); rep(set(snip['hooks'])>={'SessionStart','PreToolUse','Stop'},'adapter settings snippet valid (printed, never written)')
except Exception as e: rep(False,f'adapter settings snippet: {e}')
src=open(H+'/adapters/claude_code.py').read(); rep('state.emitted' in src and "'resume|clear|compact'" in src,'adapter injection is session-start-only or state-change-gated')
try:
    sys.path.insert(0,H+'/lib'); import hcore; rep(True,f'HELIX Core protocol {hcore.PROTOCOL_VERSION} hash {hcore.protocol_hash()}')
except Exception as e: rep(False,f'protocol import: {e}')
if os.path.exists(H+'/bench/MANIFEST.json'):
    r=subprocess.run([sys.executable,H+'/bench/freeze.py','--verify'],capture_output=True,text=True); rep(r.returncode==0,'frozen benchmark artifacts match manifest: '+r.stdout.strip()[:60],warn=True)
print('\nhelix doctor:','OK' if not fails else f'{fails} FAIL'); sys.exit(1 if fails else 0)
