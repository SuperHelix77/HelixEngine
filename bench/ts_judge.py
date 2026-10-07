"""ts_judge.py: blind LLM judge for ts_results (same rubric for every condition; judge sees prompt, truth, answer - never the condition)."""
import os,sys,json,glob,re,subprocess,hashlib
H=os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); RES=H+f"/bench/ts_results{os.environ.get('TS_SET','')}{os.environ.get('TS_OUT','')}"
TASKS={t['id']:t for t in json.load(open(H+f"/bench/ts_tasks{os.environ.get('TS_SET','')}.json"))}
RUBRIC=("You grade answers to code-analysis questions. TRUTH is authoritative. Mark CORRECT iff the answer's conclusion identifies EVERY item in TRUTH (exact function/file names or the exact number) "
 "and does not assert additional items as members of the requested set. Explanations, caveats, and mentioning other names while explaining are fine; a hedged or missing conclusion is INCORRECT. "
 "Output ONLY a JSON list of {\"i\":int,\"v\":\"CORRECT\"|\"INCORRECT\"}.")
def judge_batch(items):
    p=RUBRIC+"\n"+json.dumps([{'i':i,'question':x['prompt'],'truth':x['truth'],'answer':x['answer']} for i,x in enumerate(items)])
    r=subprocess.run(['claude','-p',p,'--output-format','json','--no-session-persistence','--setting-sources','project','--tools','','--strict-mcp-config','--disable-slash-commands','--model','sonnet','--effort','low','--system-prompt','Output only valid JSON.'],capture_output=True,text=True,stdin=subprocess.DEVNULL,timeout=900)
    return {x['i']:x['v'] for x in json.loads(re.search(r'\[.*\]',json.loads(r.stdout)['result'],re.S).group(0))}
def main():
    files=[f for f in sorted(glob.glob(RES+'/*__*__*.json')) if not os.path.basename(f).startswith('judge')]
    todo=[]
    for f in files:
        r=json.load(open(f))
        if 'judged' in r or 'err' in r: continue
        t=TASKS[r['id']]; r['_f']=f; r['prompt']=t['prompt']; r['truth']=t['truth']; todo.append(r)
    for k in range(0,len(todo),25):
        B=todo[k:k+25]; V=judge_batch([{'prompt':x['prompt'],'truth':x['truth'],'answer':x['answer']} for x in B])
        for i,x in enumerate(B):
            f=x.pop('_f'); x.pop('prompt'); x.pop('truth'); x['judged']=V.get(i,'INCORRECT'); json.dump(x,open(f,'w'))
    print('judged',len(todo))
if __name__=='__main__': main()
