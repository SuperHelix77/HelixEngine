import json,re,os,sys,time
os.environ['USE_TF']='0'; os.environ['HF_HUB_OFFLINE']='1'
from laya import Agent
D=json.load(open('l2_set.json')); F=D['funcs']; Qs=D['qs']
KW={'io':r'\b(open|write|read_bytes|read_text|fsync|rename|unlink|mkdir|replace|tempfile|os\.path|Path)\b|\.read\(|\.write\(','raises':r'\braise\b','locking':r'(lock|thread|atomic|exclusive|Event\(|Condition|fsync)'}
a_=Agent('convaiinnovations/laya'); P={k:[] for k in Qs}; t=time.time()
for f in F:
    st=f"{f['file']}\n{f['src'][:1400]}"
    res=a_.predict(st,{k:{"type":"noul","instructions":q} for k,q in Qs.items()})['answers']
    for k in Qs: P[k].append(res[k]['noul'])
print('laya',round((time.time()-t)/len(F),2),'s/func')
def auc(p,y):
    pos=[a for a,b in zip(p,y) if b]; neg=[a for a,b in zip(p,y) if not b]
    if not pos or not neg: return float('nan')
    return sum((a>b)+0.5*(a==b) for a in pos for b in neg)/(len(pos)*len(neg))
def best(p,y):
    return max(((sum((a>=th)==b for a,b in zip(p,y))/len(y)),th) for th in sorted(set(p)))
for k in Qs:
    y=[f['label'][k] for f in F]; kw=[bool(re.search(KW[k],f['src'])) for f in F]
    kacc=sum(a==b for a,b in zip(kw,y))/len(y); a,th=best(P[k],y)
    tp=sum(a_ and b for a_,b in zip(kw,y)); prec=tp/max(1,sum(kw)); rec=tp/max(1,sum(y))
    print(f"{k:8} pos={sum(y):2}/{len(y)}  Laya AUC {auc(P[k],y):.2f} best-acc {a:.2f} (thr {th:.2f}) @0.5 acc {sum((p>=0.5)==b for p,b in zip(P[k],y))/len(y):.2f} | keyword acc {kacc:.2f} P {prec:.2f} R {rec:.2f}")
