"""Dataset v2: diverse Sonnet-written phrasings (tpl/*), criteria kept in the question. Splits: train / test_newphrase / test_newentity / test_both."""
import json,os,random,hashlib,sys,collections
sys.argv=[sys.argv[0],sys.argv[1] if len(sys.argv)>1 else '.']
exec(open('gen_data.py').read().split("def fill(")[0].replace("SRC=sys.argv[1]","SRC=sys.argv[1]"))  # reuse entity lists + T + extra_escalate
class D(dict):
    def __missing__(self,k): return '{'+k+'}'
def fill(t,f,fn,rng):
    try: return t.format_map(D(file=f,fn=fn,dir=os.path.dirname(f) or '.',cond=rng.choice(CONDS),param=rng.choice(PARAMS),thing=rng.choice(THINGS),concept=rng.choice(CONCEPTS)))
    except Exception: return t
def load(l,s):
    p=f'tpl/{l}_{s}.json'; return json.load(open(p)) if os.path.exists(p) else []
Q={"cmd":{"type":"choice","instructions":"Which tool should handle this developer request?","criteria":{"callers":"find who calls or uses a function, or where it is defined","summ":"summarize or describe what a named file does","ask":"answer a specific question about code behaviour in a named file","outline":"list the functions and classes in a file","sym":"show the source code of one named function","docgen":"add missing docstrings to a file","escalate":"anything else: fixing, writing, refactoring, running, debugging, design, chit-chat, vague or follow-up messages, no named file, or a lookup combined with a change"}}}
def build(which_tmpl,which_ent,n_per,seed):
    rng=random.Random(seed); rows=[]
    ef=[f for f in files if split(f)==which_ent]; en=[n for n in fns if split(n)==which_ent]
    for lab,(tr,te) in T.items():
        ts=(tr+load(lab,'train')) if which_tmpl=='train' else (te+load(lab,'test'))
        for i in range(n_per): rows.append((fill(rng.choice(ts),rng.choice(ef),rng.choice(en),rng),lab))
        if lab=='escalate':
            for i in range(int(n_per*1.2)): rows.append((extra_escalate(which_tmpl,rng.choice(ef),rng.choice(en),rng),'escalate'))
    return rows
out={}
for name,(tm,en,n,seed) in {'train':('train','train',420,1),'test_newphrase':('test','train',60,2),'test_newentity':('train','test',60,3),'test_both':('test','test',50,4)}.items():
    rows=list(dict.fromkeys(build(tm,en,n,seed))); out[name]=rows
held=set(r[0] for k in ('test_newphrase','test_newentity','test_both') for r in out[k])
out['train']=[r for r in out['train'] if r[0] not in held]
for name,rows in out.items():
    random.Random(0).shuffle(rows)
    with open(f'v2_{name}.jsonl','w') as f:
        for t,l in rows: f.write(json.dumps({'state':t,'questions':Q,'expected':{'cmd':l}})+'\n')
    with open(f'v2_{name}.csv','w') as f:
        import csv; w=csv.writer(f); w.writerow(['text','label']); w.writerows(rows)
    print(name,len(rows),dict(collections.Counter(r[1] for r in rows)))
