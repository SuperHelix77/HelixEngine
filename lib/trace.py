"""Execution trace + derived metrics (frontier semantic turns per goal is a first-class metric, not just tokens).
One Trace per (goal, condition). Append-only JSONL; summary() is pure."""
import json,time,os
FIELDS=('correct','completion_time','frontier_calls','frontier_semantic_turns','frontier_input_tokens','frontier_output_tokens','cache_read','cache_write',
        'local_model_calls','local_tool_operations','resident_context_peak','resident_context_mean','memory_retrievals','raw_fallbacks','rediscovery_events',
        'claims_reused','stale_claim_errors','falsified_path_repetitions','semantic_substitutions','semantic_substitution_failures','escalations_by_tier','usage_meter_delta')
class Trace:
    def __init__(s,goal_id,condition=''):
        s.goal_id=goal_id; s.condition=condition; s.t0=time.time(); s.d={k:0 for k in FIELDS}; s.d['escalations_by_tier']={}; s.d['correct']=None; s._ctx=[]
    def frontier_turn(s,input_tokens=0,output_tokens=0,cache_read=0,cache_write=0,semantic=True,resident=None):
        d=s.d; d['frontier_calls']+=1; d['frontier_semantic_turns']+=1 if semantic else 0
        d['frontier_input_tokens']+=input_tokens; d['frontier_output_tokens']+=output_tokens; d['cache_read']+=cache_read; d['cache_write']+=cache_write
        if resident is not None: s._ctx.append(resident); d['resident_context_peak']=max(s._ctx); d['resident_context_mean']=round(sum(s._ctx)/len(s._ctx),1)
    def local_op(s,n=1): s.d['local_tool_operations']+=n
    def local_model(s,n=1): s.d['local_model_calls']+=n
    def retrieval(s,raw_fallback=False,rediscovery=False): s.d['memory_retrievals']+=1; s.d['raw_fallbacks']+=1 if raw_fallback else 0; s.d['rediscovery_events']+=1 if rediscovery else 0
    def claim_reused(s,n=1,stale_error=False,falsified_repeat=False): s.d['claims_reused']+=n; s.d['stale_claim_errors']+=1 if stale_error else 0; s.d['falsified_path_repetitions']+=1 if falsified_repeat else 0
    def substitution(s,failed=False): s.d['semantic_substitutions']+=1; s.d['semantic_substitution_failures']+=1 if failed else 0
    def escalation(s,tier): e=s.d['escalations_by_tier']; e[tier]=e.get(tier,0)+1
    def finish(s,correct): s.d['correct']=bool(correct); s.d['completion_time']=round(time.time()-s.t0,2); return s.summary()
    def summary(s): return {'goal_id':s.goal_id,'condition':s.condition,**s.d}
    def save(s,path):
        with open(path,'a') as f: f.write(json.dumps(s.summary())+'\n')
def load(path): return [json.loads(l) for l in open(path) if l.strip()]
def compression(baseline,helix):
    """Frontier Turn Compression, Context Compression, token-turn exposure. Not billing: cache, output pricing and tool cost are not modelled."""
    ratio=lambda a,b:(a/b) if b else float('inf')
    exp=lambda t:t['frontier_semantic_turns']*(t['resident_context_mean'] or 0)
    return {'frontier_turn_compression':round(ratio(baseline['frontier_semantic_turns'],helix['frontier_semantic_turns']),2),
            'context_compression':round(ratio(baseline['resident_context_mean'],helix['resident_context_mean']),2),
            'token_turn_exposure_ratio':round(ratio(exp(baseline),exp(helix)),1)}
def useful_work_efficiency(traces,allowance_field='frontier_input_tokens'):
    ok=sum(1 for t in traces if t['correct']); spent=sum(t[allowance_field]+t['frontier_output_tokens'] for t in traces)
    return round(ok/spent*1e6,3) if spent else float('inf')   # correct goals per million frontier tokens
