"""Latency benchmark: TTFT, time-to-first-useful-tool-call, tool-loop latency, wall-clock. Streams `claude -p --output-format stream-json` and timestamps each event.
usage: latency.py CFG TASK TAG   (CFG: A default claude | F helix engine). Reuses chbench.py tasks/checkers (scratchpad)."""
import sys,os,json,time,subprocess,shutil
SP=os.environ.get('HXBENCH_DIR'); H=os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,SP); import chbench
def run(cfg,task,tag):
    d=f'{SP}/lat_{tag}'; shutil.rmtree(d,ignore_errors=True); shutil.copytree(f'{SP}/hx2_base',d)
    q,chk=chbench.Q[task]; env=dict(os.environ); common=['-p',q,'--output-format','stream-json','--verbose','--no-session-persistence']
    if cfg=='A': cmd=['claude']+common+['--permission-mode','acceptEdits','--allowedTools','Read','Grep','Glob']
    else:
        sys.path.insert(0,H); import compose
        pf=f'{SP}/runs/prompt_F.txt'; os.makedirs(f'{SP}/runs',exist_ok=True); open(pf,'w').write(compose.compose('ultra'))
        env.update(CL_RUN_DIR=f'{SP}/runs/{tag}',HELIX_HOME=H,CL_PROMPT=pf); cmd=[f'{H}/bench_cl.sh']+common
    t0=time.time(); p=subprocess.Popen(cmd,cwd=d,env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL,text=True)
    ev=[]
    for line in p.stdout:
        try: j=json.loads(line)
        except Exception: continue
        ev.append((time.time()-t0,j))
    p.wait(); wall=time.time()-t0
    ttft=next((t for t,j in ev if j.get('type')=='assistant'),None)
    first_tool=next((t for t,j in ev if j.get('type')=='assistant' and any(b.get('type')=='tool_use' for b in j['message']['content'])),None)
    res=next((j for t,j in ev if j.get('type')=='result'),{})
    # tool-loop latency: time between a tool_use assistant event and the next event after its tool_result user event
    loop=0.0; last=None
    for t,j in ev:
        if j.get('type')=='assistant' and any(b.get('type')=='tool_use' for b in j['message']['content']): last=t
        elif j.get('type')=='user' and last is not None: loop+=t-last; last=None
    return {'tag':tag,'cfg':cfg,'task':task,'wall':round(wall,1),'ttft':round(ttft,1) if ttft else None,'first_tool_call':round(first_tool,1) if first_tool else None,'tool_loop_s':round(loop,1),'turns':res.get('num_turns'),'ok':bool(chk((res.get('result') or '')))}
if __name__=='__main__': print(json.dumps(run(*sys.argv[1:4])))
