"""ts_run.py: token-saving metrics campaign runner.
 configs: A = default claude (Read/Grep/Glob) | L1 = engine, basic helpers (no hstep) | L2 = full Helix (hstep, semantic reduction, ultra terse)
 usage: ts_run.py SP CONFIG REPS [parallel]   -> bench/ts_results/CONFIG__TASK__REP.json (skips existing)"""
import os,sys,json,subprocess,shutil,time,concurrent.futures as cf
H=os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0,H+'/bench'); sys.path.insert(0,H)
import ts_tasks,compose
SP,CFG,REPS=sys.argv[1],sys.argv[2],int(sys.argv[3]); PAR=int(sys.argv[4]) if len(sys.argv)>4 else 6
RES=H+f"/bench/ts_results{os.environ.get('TS_SET','')}{os.environ.get('TS_OUT','')}"; os.makedirs(RES,exist_ok=True); WORK=os.path.join(SP,'ts_work'); os.makedirs(WORK,exist_ok=True)
TASKS=[t for t in json.load(open(H+f"/bench/ts_tasks{os.environ.get('TS_SET','')}.json")) if not os.environ.get('TS_ONLY') or t['id'] in os.environ['TS_ONLY'].split(',')]; REPO={n:ts_tasks.Repo(n,os.path.join(SP,rel)) for n,rel in ts_tasks.REPOS.items()}
BASIC='x(c)=zsh. 1 call, chain a;b;c. Find: outline F..[nodoc] | sym F NAME | callers [-l list] [-d DEFFILE] NAME [dir] | raw N [A-B]. Edit: ed F A-B NEW [A-B NEW].. | ins F N T | rep F OLD NEW. Free local LLM: docgen F.. | ask F.. -- Q | summ F...'
def prompt_file(cfg):
    p=f'{WORK}/prompt_{cfg}.txt'
    if cfg=='L1': open(p,'w').write(open(H+'/terse/ultra.txt').read().strip()+' '+BASIC)
    else: open(p,'w').write(compose.compose('ultra'))
    return p
LIMIT_HIT=False
def run(cfg,t,rep):
    global LIMIT_HIT
    if LIMIT_HIT: return {'err':'limit already hit; skipped','id':t['id'],'cfg':cfg}
    out=f"{RES}/{cfg}__{t['id']}__{rep}.json"
    if os.path.exists(out): return json.load(open(out))
    d=f"{WORK}/{cfg}_{t['id']}_{rep}"; shutil.rmtree(d,ignore_errors=True); shutil.copytree(os.path.join(SP,ts_tasks.REPOS[t['repo']]),d,ignore=shutil.ignore_patterns('.git','__pycache__','docs','.helix'))
    common=['-p',t['prompt']+' Answer briefly.','--output-format','json','--no-session-persistence']; env=dict(os.environ)
    if cfg=='A': cmd=['claude']+common+['--permission-mode','acceptEdits','--allowedTools','Read','Grep','Glob']
    else: env.update(HELIX_HOME=H,CL_RUN_DIR=f'{WORK}/runs/{cfg}_{t["id"]}_{rep}',CL_PROMPT=prompt_file(cfg),HELIX_PKT_DIR=d+'/.hpk'); cmd=[f'{H}/bench_cl.sh']+common
    t0=time.time(); r=subprocess.run(cmd,cwd=d,env=env,capture_output=True,text=True,stdin=subprocess.DEVNULL,timeout=900); wall=time.time()-t0
    try: j=json.loads(r.stdout)
    except Exception: return {'err':(r.stdout+r.stderr)[:300],'id':t['id'],'cfg':cfg}
    u=j['usage']; ans=j.get('result') or ''
    if ('session limit' in ans.lower() or 'usage limit' in ans.lower() or 'rate limit' in ans.lower()) and u['output_tokens']==0: LIMIT_HIT=True; return {'err':'USAGE LIMIT: '+ans[:80],'id':t['id'],'cfg':cfg}
    ok,det=ts_tasks.check(t,ans,REPO[t['repo']])
    rec={'cfg':cfg,'id':t['id'],'repo':t['repo'],'family':t['family'],'rep':rep,'turns':j['num_turns'],'input':u['input_tokens'],'cache_write':u['cache_creation_input_tokens'],'cache_read':u['cache_read_input_tokens'],
         'output':u['output_tokens'],'cost_usd':j.get('total_cost_usd'),'api_ms':j.get('duration_api_ms'),'wall_s':round(wall,1),'correct':bool(ok),'detail':det,'answer':ans[:300]}
    json.dump(rec,open(out,'w')); return rec
if __name__=='__main__':
    jobs=[(CFG,t,r) for t in TASKS for r in range(1,REPS+1)]; done=0
    with cf.ThreadPoolExecutor(PAR) as ex:
        for rec in ex.map(lambda a:run(*a),jobs):
            done+=1
            if 'err' in rec: print('ERR',rec['id'],rec['err'][:100])
    print(CFG,'done',done)
