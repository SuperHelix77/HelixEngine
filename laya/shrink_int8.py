import os,sys,csv,json,time,io
os.environ['USE_TF']='0'; os.environ['HF_HUB_OFFLINE']='1'
import torch,torch.nn as nn,torch.nn.functional as F
from laya import Agent
Q=json.load(open('ft2/questions.json')); Q=Q.get('questions',Q)
rows=[r for n in ('v2_test_newphrase','v2_test_newentity') for r in csv.DictReader(open(n+'.csv'))][::2]
class QLinear(nn.Module):
    def __init__(s,lin):
        super().__init__(); w=lin.weight.data.float(); sc=w.abs().amax(1).clamp(min=1e-8)/127
        s.register_buffer('q',(w/sc[:,None]).round().clamp(-127,127).to(torch.int8)); s.register_buffer('sc',sc.to(torch.float16))
        s.bias=None if lin.bias is None else nn.Parameter(lin.bias.data.to(torch.float16),requires_grad=False)
    @property
    def weight(s): return s.sc   # dtype/device stub for callers that only inspect it
    def forward(s,x): return F.linear(x,s.q.to(x.dtype)*s.sc.to(x.dtype)[:,None],None if s.bias is None else s.bias.to(x.dtype))
class QEmb(nn.Module):
    def __init__(s,e):
        super().__init__(); w=e.weight.data.float(); sc=w.abs().amax(1).clamp(min=1e-8)/127
        s.register_buffer('q',(w/sc[:,None]).round().clamp(-127,127).to(torch.int8)); s.register_buffer('sc',sc.to(torch.float16)); s.padding_idx=e.padding_idx
    def forward(s,ids): return s.q[ids].to(torch.float16)*s.sc[ids][...,None]
def quant(m,skip=()):
    n=0
    for name,ch in list(m.named_children()):
        if isinstance(ch,nn.Linear) and ch.weight.numel()>4096: setattr(m,name,QLinear(ch)); n+=1
        elif isinstance(ch,nn.Embedding): setattr(m,name,QEmb(ch)); n+=1
        else: n+=quant(ch)
    return n
def mb(m): b=io.BytesIO(); torch.save(m.state_dict(),b); return b.tell()/1e6
def evalv(agent):
    P=[];t=time.time()
    for r in rows:
        x=agent.predict(r['text'],Q); k=list(x['answers'])[0]; v=x['answers'][k]; P.append((v['choice'],v['answer_confidence']))
    return P,(time.time()-t)/len(rows)
acc=lambda P:sum(p==r['label'] for (p,_),r in zip(P,rows))/len(rows)
b=Agent('ft2'); P0,dt0=evalv(b)
a=Agent('ft2'); a.model.half(); n=quant(a.model); a.model.half() if False else None
print('quantized modules',n)
try:
    P,dt=evalv(a); agree=sum(p[0]==q[0] for p,q in zip(P,P0))/len(rows)
    cd=sum(abs(p[1]-q[1]) for p,q in zip(P,P0))/len(rows)
    print(f"fp32 base  acc {100*acc(P0):.1f}%  {dt0*1000:.0f}ms")
    print(f"int8 w-only size {mb(a.model):.0f}MB  acc {100*acc(P):.1f}%  agree {100*agree:.1f}%  mean|conf diff| {cd:.3f}  {dt*1000:.0f}ms/dec")
except Exception as e: print('FAILED',type(e).__name__,str(e)[:200])
