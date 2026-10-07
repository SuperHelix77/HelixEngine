"""Weight-only int8 for Laya agents (pure torch; no quantization engine needed). Measured on ft2: 429 MB resident vs 1685 MB fp32,
95.9% acc (same), 100% prediction agreement, mean confidence shift 0.002, ~150 vs ~90 ms/decision.
usage: from int8 import quantize_agent; agent=quantize_agent(Agent('laya/ft2'))"""
import torch,torch.nn as nn,torch.nn.functional as F
class QLinear(nn.Module):
    def __init__(s,lin):
        super().__init__(); w=lin.weight.data.float(); sc=w.abs().amax(1).clamp(min=1e-8)/127
        s.register_buffer('q',(w/sc[:,None]).round().clamp(-127,127).to(torch.int8)); s.register_buffer('sc',sc.to(torch.float16))
        s.bias=None if lin.bias is None else nn.Parameter(lin.bias.data.to(torch.float16),requires_grad=False)
    @property
    def weight(s): return s.sc            # dtype/device stub: laya only inspects it
    def forward(s,x): return F.linear(x,s.q.to(x.dtype)*s.sc.to(x.dtype)[:,None],None if s.bias is None else s.bias.to(x.dtype))
class QEmb(nn.Module):
    def __init__(s,e):
        super().__init__(); w=e.weight.data.float(); sc=w.abs().amax(1).clamp(min=1e-8)/127
        s.register_buffer('q',(w/sc[:,None]).round().clamp(-127,127).to(torch.int8)); s.register_buffer('sc',sc.to(torch.float16)); s.padding_idx=e.padding_idx
    def forward(s,ids): return s.q[ids].to(torch.float16)*s.sc[ids][...,None]
def quantize(m,min_numel=4096):
    n=0
    for name,ch in list(m.named_children()):
        if isinstance(ch,nn.Linear) and ch.weight.numel()>min_numel: setattr(m,name,QLinear(ch)); n+=1
        elif isinstance(ch,nn.Embedding): setattr(m,name,QEmb(ch)); n+=1
        else: n+=quantize(ch,min_numel)
    return n
def quantize_agent(agent):
    agent.model.half(); n=quantize(agent.model); agent.quantized_modules=n; return agent
