#!/usr/bin/env python3
"""UserPromptSubmit hook: local-first router. Tiny local LLM picks ONE command from a fixed menu (JSON);
deterministic validation + argv exec (no shell). Anything unsure/vague/mutating -> exit 0 = escalate to Claude.
Prefix a prompt with '!' to force Claude. Writes (docgen) only when CL_LOCAL_WRITE=1."""
import sys,os,json,re,glob,subprocess,urllib.request
H=os.environ.get('HELIX_HOME',os.path.dirname(os.path.abspath(__file__))); BIN=H+'/bin'
HOST=os.environ.get('LM_HOST','http://127.0.0.1:11500'); MODEL=os.environ.get('LM_MODEL','qwen3:1.7b')
SYS="""Route a user request to ONE command. Reply JSON only.
cmds: {"cmd":"callers","name":ID,"deffile":PATH|null} who calls/uses a function or where defined;
{"cmd":"summ","files":[PATH]} summarize/describe what a named file does;
{"cmd":"ask","files":[PATH],"q":TEXT} a specific question answerable from named file(s);
{"cmd":"outline","files":[PATH]} list functions/classes of named files;
{"cmd":"sym","file":PATH,"name":ID} show source of a named function;
{"cmd":"docgen","files":[PATH]} add missing docstrings to named files;
{"cmd":"escalate"} EVERYTHING else: fixing, writing, refactoring, running, debugging, multi-step, vague, no concrete file/function, follow-ups like "yes".
Examples:
"list every function that calls digest imported from core/evidence.py" -> {"cmd":"callers","name":"digest","deffile":"core/evidence.py"}
"what does x.py do in one sentence" -> {"cmd":"summ","files":["x.py"]}
"in a/b.py what happens when two edits overlap?" -> {"cmd":"ask","files":["a/b.py"],"q":"what happens when two edits overlap?"}
"show functions in util.py" -> {"cmd":"outline","files":["util.py"]}
"print the code of parse in cfg.py" -> {"cmd":"sym","file":"cfg.py","name":"parse"}
"add docstrings to every function in m.py lacking one" -> {"cmd":"docgen","files":["m.py"]}
"fix the crash in server.py" -> {"cmd":"escalate"}
"refactor this module" -> {"cmd":"escalate"}
"yes go ahead" -> {"cmd":"escalate"}
"run the tests" -> {"cmd":"escalate"}"""
ID=re.compile(r'^[A-Za-z_]\w*$')
def llm(prompt):
    req=urllib.request.Request(HOST+'/api/chat',json.dumps({'model':MODEL,'stream':False,'think':False,'format':'json','options':{'temperature':0,'num_predict':120,'num_ctx':4096},'messages':[{'role':'system','content':SYS},{'role':'user','content':prompt}]}).encode(),{'Content-Type':'application/json'})
    return json.loads(json.load(urllib.request.urlopen(req,timeout=20))['message']['content'])
def resolve(f,cwd):
    if not isinstance(f,str) or not f or '\x00' in f: return None
    p=os.path.realpath(os.path.join(cwd,f))
    if os.path.isfile(p) and p.startswith(os.path.realpath(cwd)+os.sep): return os.path.relpath(p,cwd)
    hits=[h for h in glob.glob(os.path.join(cwd,'**',os.path.basename(f)),recursive=True) if os.path.isfile(h) and h.replace(cwd+os.sep,'').endswith(f.lstrip('./'))]
    return os.path.relpath(hits[0],cwd) if len(hits)==1 else None
def plan(r,cwd):
    """validate router JSON -> argv list or None"""
    if not isinstance(r,dict): return None
    c=r.get('cmd')
    if c=='callers':
        n=r.get('name')
        if not isinstance(n,str) or not ID.match(n): return None
        a=[BIN+'/callers','-l']
        d=r.get('deffile')
        if d:
            if not isinstance(d,str) or not re.match(r'^[\w./-]+$',d): return None
            a+=['-d',d]
        return a+[n,'.']
    if c in('summ','outline','docgen','ask'):
        fs=r.get('files')
        if not isinstance(fs,list) or not fs or len(fs)>5: return None
        fs=[resolve(f,cwd) for f in fs]
        if None in fs: return None
        if c=='docgen':
            return [BIN+'/docgen']+fs if os.environ.get('CL_LOCAL_WRITE')=='1' else None
        if c=='ask':
            q=r.get('q')
            if not isinstance(q,str) or not q.strip(): return None
            return [BIN+'/ask']+fs+['--',q]
        return [BIN+('/summ' if c=='summ' else '/outline')]+fs
    if c=='sym':
        f=resolve(r.get('file'),cwd); n=r.get('name')
        if f and isinstance(n,str) and ID.match(n): return [BIN+'/sym',f,n]
    return None
MUT=re.compile(r'\b(fix|change|edit|rename|delete|remove|refactor|implement|write|create|update|replace|run|execute|install|commit|push|migrate|and then|then)\b',re.I)
def grounded(r,prompt):
    """every target the router names must literally occur in the prompt"""
    low=prompt.lower(); items=[]
    for k in('files',):
        items+=r.get(k) or []
    for k in('file','name','deffile'):
        if r.get(k): items.append(r[k])
    return all(isinstance(i,str) and (i.lower() in low or os.path.basename(i).lower() in low) for i in items) and bool(items)
def decide(prompt,cwd):
    try:
        r=llm(prompt)
        if r.get('cmd')!='docgen' and MUT.search(prompt): return None
        if not grounded(r,prompt): return None
        return plan(r,cwd)
    except Exception: return None
def main():
    p=json.load(sys.stdin); prompt=(p.get('prompt') or '').strip(); cwd=p.get('cwd') or os.getcwd()
    if not prompt or prompt.startswith('!') or len(prompt)>500 or '\n' in prompt: return
    a=decide(prompt,cwd)
    if not a: return
    try: r=subprocess.run(a,cwd=cwd,capture_output=True,text=True,timeout=60)
    except Exception: return
    out=(r.stdout or '').strip()
    if r.returncode or not out: return
    tag=os.path.basename(a[0])
    note=f' (local {MODEL}; prefix ! to use Claude)' if tag in('ask','summ') else ''
    print(json.dumps({'decision':'block','reason':f'[local:{tag}{note}]\n{out}'}))
if __name__=='__main__': main()
