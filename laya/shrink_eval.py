import os,sys,csv,json,time,io,copy
os.environ['USE_TF']='0'; os.environ['HF_HUB_OFFLINE']='1'
import torch
from laya import Agent
Q=json.load(open('ft2/questions.json')); Q=Q.get('questions',Q)
rows=[r for n in ('v2_test_newphrase','v2_test_newentity') for r in csv.DictReader(open(n+'.csv'))]
rows=rows[::2]    # 424 rows
def mb(m):
    b=io.BytesIO(); torch.save(m.state_dict(),b); return b.tell()/1e6
def evalv(name,agent):
    P=[];t=time.time()
    for r in rows:
        x=agent.predict(r['text'],Q); k=list(x['answers'])[0]; v=x['answers'][k]; P.append((v['choice'],v['answer_confidence']))
    dt=(time.time()-t)/len(rows); return P,dt
res={}
base=Agent('ft2'); print('device',getattr(base,'device',None))
P0,dt0=evalv('fp32',base); acc=lambda P:sum(p==r['label'] for (p,_),r in zip(P,rows))/len(rows)
print(f"fp32      size {mb(base.model):.0f}MB  acc {100*acc(P0):.1f}%  {dt0*1000:.0f}ms/dec")
for name,fn in (('bf16',lambda a:a.model.to(torch.bfloat16)),('fp16',lambda a:a.model.half())):
    try:
        a=Agent('ft2'); fn(a); P,dt=evalv(name,a); agree=sum(p[0]==q[0] for p,q in zip(P,P0))/len(rows)
        print(f"{name:9} size {mb(a.model):.0f}MB  acc {100*acc(P):.1f}%  agree-with-fp32 {100*agree:.1f}%  {dt*1000:.0f}ms/dec")
    except Exception as e: print(name,'FAILED',type(e).__name__,str(e)[:120])
try:
    a=Agent('ft2'); a.model=a.model.to('cpu').float(); 
    if hasattr(a,'device'): a.device='cpu'
    a.model=torch.ao.quantization.quantize_dynamic(a.model,{torch.nn.Linear},dtype=torch.qint8)
    P,dt=evalv('int8',a); agree=sum(p[0]==q[0] for p,q in zip(P,P0))/len(rows)
    print(f"int8-dyn  size {mb(a.model):.0f}MB  acc {100*acc(P):.1f}%  agree-with-fp32 {100*agree:.1f}%  {dt*1000:.0f}ms/dec (CPU)")
except Exception as e: print('int8 FAILED',type(e).__name__,str(e)[:160])
