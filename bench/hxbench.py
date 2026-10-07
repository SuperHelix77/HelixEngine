import subprocess,shutil,json,sys,os,ast,re
SP=os.environ.get('HXBENCH_DIR',os.path.dirname(os.path.abspath(__file__))); H=os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TASKS={
 'T1':"In helixengine/, list every function that calls `digest` (the function imported from core/evidence.py). Reply as file:function, one per line.",
 'T2':"In helixengine/core/literal_edits.py, what does compile_edits do when two edits overlap? One sentence.",
 'T4':"Summarize helixengine/core/renderer.py in one sentence.",
 'T3':"Add a one-line docstring to every function in helixengine/pricing.py that lacks one. Change nothing else.",
}
GT={('evidence','get'),('evidence','put'),('evidence','retrieve'),('evidence','retrieve_many'),('evidence','snapshot'),('line_index','retrieve'),('line_index','verify_index'),}
FP={'freeze','environment_binding','read_file'}
def run(cfg,task,tag):
    d=f'{SP}/hxw_{tag}'; shutil.rmtree(d,ignore_errors=True); shutil.copytree(f'{SP}/hx_base',d)
    q=TASKS[task]; common=['-p',q,'--output-format','json','--no-session-persistence']
    if cfg=='A':
        cmd=['claude']+common+['--permission-mode','acceptEdits','--allowedTools','Read','Grep','Glob','Edit','Write']
        env=dict(os.environ)
    else:
        env=dict(os.environ); env['CL_RUN_DIR']=f'{SP}/runs/{tag}'; shutil.rmtree(env['CL_RUN_DIR'],ignore_errors=True); env['CL_PROMPT']={'L5':f'{H}/prompt.txt','U1':f'{H}/prompt.txt','U3':f'{H}/prompt_handle.txt'}.get(cfg,f'{H}/prompt.txt')
        cmd=[f'{H}/bench_cl.sh']+common
    r=subprocess.run(cmd,cwd=d,env=env,capture_output=True,text=True,stdin=subprocess.DEVNULL,timeout=600)
    try: j=json.loads(r.stdout)
    except Exception: return {'tag':tag,'err':(r.stdout+r.stderr)[:300]}
    u=j['usage']; res=j.get('result') or ''; raw_reply=res
    if cfg!='A' and '@' in res:
        e=subprocess.run(['python3',f'{H}/expand.py',env['CL_RUN_DIR']],input=res,capture_output=True,text=True); res=e.stdout
    ok=None
    if task=='T1':
        found={(f,fn) for f,fn in GT if re.search(r'\b'+fn+r'\b',res)}
        fp=[x for x in FP if re.search(r'\b'+x+r'\b',res)]
        ok=f'recall {len(found)}/{len(GT)} fp={len(fp)}'
    elif task=='T4': ok=bool(re.search(r'copy|assembl|byte|source|plan',res,re.I)) and len(res)<600
    elif task=='T2': ok=bool(re.search('overlap',res,re.I) and re.search('error|raise|reject|ambig|fail',res,re.I))
    elif task=='T3':
        s=open(f'{d}/helixengine/pricing.py').read(); o=open(f'{SP}/hx_base/helixengine/pricing.py').read().split('\n')
        try:
            t=ast.parse(s); fn=[n for n in ast.walk(t) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
            doc=all(ast.get_docstring(n) for n in fn)
            it=iter(s.split('\n')); keep=all(any(l==x for x in it) for l in o)
            ok=f'docs={doc} orig_kept={keep}'
        except SyntaxError as e: ok=f'SYNTAXERR {e.lineno}'
    return {'tag':tag,'cfg':cfg,'task':task,'turns':j['num_turns'],'in':u['input_tokens'],'cc':u['cache_creation_input_tokens'],'cr':u['cache_read_input_tokens'],'out':u['output_tokens'],'cost':round(j['total_cost_usd'],4),'ok':ok,'model':list(j['modelUsage'])[0],'reply':raw_reply[:60].replace('\n',' | '),'res':res.replace('\n',' | ')[:300]}
if __name__=='__main__':
    cfg,task,tag=sys.argv[1:4]; print(json.dumps(run(cfg,task,tag)))
