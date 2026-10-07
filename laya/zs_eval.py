"""zs_eval.py CKPT [OUT.json]: zero-shot battery. Nothing here appears in zs1_train."""
import os,sys,json,re,csv,time
os.environ['USE_TF']='0'; os.environ['HF_HUB_OFFLINE']='1'
H=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,H+'/lib')
from laya import Agent
ck=sys.argv[1]; out=sys.argv[2] if len(sys.argv)>2 else None; a=Agent(ck)
def auc(p,y):
    pos=[x for x,b in zip(p,y) if b]; neg=[x for x,b in zip(p,y) if not b]
    return sum((x>z)+0.5*(x==z) for x in pos for z in neg)/(len(pos)*len(neg)) if pos and neg else float('nan')
def noul(state,q,instr): return a.predict(state,{q:{'type':'noul','instructions':instr}})['answers'][q]['noul']
R={'ckpt':ck}; t0=time.time()
# 1) held-out instructions over held-out packages
rows=[json.loads(l) for l in open('zs1_eval_heldq.jsonl')]; by={}
for r in rows:
    q=list(r['questions'])[0]; p=noul(r['state'],q,r['questions'][q]['instructions']); by.setdefault(r['meta']['q'],([],[]))[0].append(p); by[r['meta']['q']][1].append(r['expected'][q])
R['heldout_instr']={k:{'n':len(v[1]),'acc':round(sum((p>=0.5)==y for p,y in zip(*v))/len(v[1]),3),'auc':round(auc(*v),3)} for k,v in by.items()}
R['heldout_instr_macro']={'acc':round(sum(x['acc'] for x in R['heldout_instr'].values())/len(by),3),'auc':round(sum(x['auc'] for x in R['heldout_instr'].values())/len(by),3)}
# 2) code relevance (held-out packages)
rel=[json.loads(l) for l in open('zs1_eval_rel.jsonl')]; P=[];Y=[]
for r in rel: q='rel'; P.append(noul(r['state'],q,r['questions'][q]['instructions'])); Y.append(r['expected'][q])
R['code_relevance']={'n':len(Y),'acc':round(sum((p>=0.5)==y for p,y in zip(P,Y))/len(Y),3),'auc':round(auc(P,Y),3)}
# 3) memory reranking on the real transcript QA (different domain, never trained on)
import hmem
STOP=set('what which how many did the was were is are of in to for and a an on at by with from that this it its does do when who why'.split())
kw=lambda q:' '.join(w for w in re.findall(r"[A-Za-z0-9_.\-/%]+",q) if w.lower() not in STOP)
def window(t,q,w=900):
    best=-1
    for x in re.findall(r'[A-Za-z0-9_.\-/%]{3,}',q):
        i=t.lower().find(x.lower())
        if i>=0 and (best<0 or i<best): best=i
    s=max(0,best-200) if best>=0 else 0; return re.sub(r'\s+',' ',t[s:s+w])
rr={}
for tag,db,qa in [x for x in (('A','cb/slice.db','cb/qa.json'),('B','cb/sliceB.db','cb/qaB.json')) if os.path.exists(x[1]) and os.path.exists(x[2])]:   # optional: needs your own archived transcript slices
    hmem.DB=os.path.abspath(db); QA=json.load(open(qa)); rows_=[]
    for x in QA:
        cands=hmem.search(kw(x['q']),20,path=hmem.DB); sc=[]
        for c in cands: sc.append((noul(window(hmem.raw(c['id'],path=hmem.DB),x['q']),'ans','This passage contains the answer to: '+x['q']),c['seq']))
        sc.sort(reverse=True); rows_.append(([c['seq'] for c in cands],[s for _,s in sc],x['ev']))
    rr[tag]={f'k{k}':{'bm25':sum(any(e in b[:k] for e in ev) for b,_,ev in rows_),'rerank':sum(any(e in l[:k] for e in ev) for _,l,ev in rows_)} for k in (1,3,5)}; rr[tag]['n']=len(QA)
R['memory_rerank']=rr
# 4) Sonnet-labelled L2 (io/raises/locking on 80 HelixEngine functions)
D=json.load(open('l2_set.json')); F=D['funcs']; Qs={'io':'Does this function perform file or disk I/O?','raises':'Does this function validate inputs or state and raise an exception on invalid input?','locking':'Is this function concerned with locks, threads, concurrency or atomicity?'}
l2={}
for k,q in Qs.items():
    P=[noul(f"{f['file']}\n{f['src'][:1400]}",k,q) for f in F]; y=[f['label'][k] for f in F]; l2[k]={'auc':round(auc(P,y),3),'acc@0.5':round(sum((p>=0.5)==b for p,b in zip(P,y))/len(y),3)}
R['l2_sonnet_labelled']=l2
# 5) routing regression (ft2 routing test set; same schema)
rt=[json.loads(l) for l in open('v2_test_newphrase.jsonl')][::2]; ok=0
for r in rt:
    x=a.predict(r['state'],r['questions']); ok+=x['answers']['cmd']['choice']==r['expected']['cmd']
R['routing_newphrase']={'n':len(rt),'acc':round(ok/len(rt),3)}
R['seconds']=round(time.time()-t0)
print(json.dumps(R,indent=1)); 
if out: json.dump(R,open(out,'w'),indent=1)
