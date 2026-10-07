"""Escalation ladder: deterministic -> laya -> local -> micro -> mid -> high, chosen per DECISION (not per task), with automatic de-escalation.
Policy is deterministic arithmetic; models only supply answers. Costs are in relative units (1 unit ~ 1k haiku-class tokens)."""
import os,sys,json,re,subprocess,time,hashlib
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import hcore
try: import claims as hclaims
except Exception: hclaims=None

DEFAULT_LADDER=[
 {'name':'det','model':None,'cost':0.0,'latency':0.0,'p_err':0.15},
 {'name':'laya','model':None,'cost':0.02,'latency':0.1,'p_err':0.10},
 {'name':'local','model':'qwen3:1.7b','cost':0.1,'latency':2.0,'p_err':0.08},
 {'name':'micro','model':'haiku','cost':1.0,'latency':3.0,'p_err':0.05},
 {'name':'mid','model':'sonnet','cost':3.0,'latency':6.0,'p_err':0.02},
 {'name':'high','model':'opus','cost':15.0,'latency':12.0,'p_err':0.01}]

def load_ladder(path=None):
    p=path or os.path.join(os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),'tiers.json')
    try: return json.load(open(p))
    except Exception: return DEFAULT_LADDER

def ev_escalate(p_gain,value,c_model,c_latency=0.0,c_context=0.0):
    """EV = P(delta_q | E,M) * V(delta_q) - C_model - C_latency - C_context. Escalate only if EV > 0."""
    return p_gain*value-c_model-c_latency-c_context

def should_escalate(p_error,c_error,c_escalation):
    """simple form: P(error) * C(error) > C(escalation)"""
    return p_error*c_error>c_escalation

def expected_loss(tier,loss_cost): return tier['p_err']*loss_cost

def choose_tier(loss_cost,acceptable_loss,ladder=None,floor='det',allowed=None):
    """cheapest tier at/above `floor` whose expected loss <= acceptable_loss; else the top tier. Non-monotone use is fine: callers re-enter at the floor each decision."""
    ladder=ladder or load_ladder(); names=[t['name'] for t in ladder]; start=names.index(floor)
    for t in ladder[start:]:
        if allowed and t['name'] not in allowed: continue
        if expected_loss(t,loss_cost)<=acceptable_loss: return t
    return [t for t in ladder if not allowed or t['name'] in allowed][-1]

# ---- micro-escalation ---------------------------------------------------------------------------------------------
def build_micro_prompt(question,claims=(),evidence=(),constraints=(),return_schema=None):
    """a ~150-400 token question packet: this buys a narrow judgment, not an agent."""
    L=['Decide one question from the evidence. No other work.',f'QUESTION: {question}']
    if claims: L.append('CLAIMS: '+' | '.join(str(c) for c in claims))
    if evidence: L.append('EVIDENCE:\n'+'\n'.join(f'- {e}' for e in evidence))
    if constraints: L.append('CONSTRAINTS: '+'; '.join(constraints))
    L.append('Reply ONLY JSON: '+(json.dumps(return_schema) if return_schema else '{"choice":str,"confidence":0-1,"reason":"<=150 words","needs":[str]}'))
    return '\n'.join(L)
def claude_caller(model,prompt,timeout=180):
    r=subprocess.run(['claude','-p',prompt,'--output-format','json','--no-session-persistence','--setting-sources','project','--tools','','--strict-mcp-config','--disable-slash-commands','--model',model,'--effort','low','--system-prompt','Output only the requested JSON.'],capture_output=True,text=True,stdin=subprocess.DEVNULL,timeout=timeout)
    j=json.loads(r.stdout); u=j['usage']
    return j['result'],{'in':u['input_tokens']+u['cache_creation_input_tokens']+u['cache_read_input_tokens'],'out':u['output_tokens']}
def parse_json(t):
    m=re.search(r'\{.*\}',t,re.S)
    if not m: raise ValueError('no JSON object in reply')
    return json.loads(m.group(0))

class Escalator:
    """caller(model,prompt)->(text,usage). Injected so policy is testable without a model."""
    def __init__(s,ladder=None,caller=claude_caller,base='det',trace=None):
        s.ladder=ladder or load_ladder(); s.caller=caller; s.base=base; s.tier=base; s.trace=trace; s.log=[]
    def tier_by_name(s,n): return next(t for t in s.ladder if t['name']==n)
    def micro(s,question,claims=(),evidence=(),constraints=(),return_schema=None,tier=None,loss_cost=10.0,acceptable_loss=0.3):
        t=s.tier_by_name(tier) if tier else choose_tier(loss_cost,acceptable_loss,s.ladder,floor='micro')
        if not t['model']: raise ValueError(f"tier {t['name']} has no model")
        prompt=build_micro_prompt(question,claims,evidence,constraints,return_schema); t0=time.time()
        txt,u=s.caller(t['model'],prompt); d=parse_json(txt)
        rec={'decision_id':'D'+hashlib.sha256((question+str(time.time())).encode()).hexdigest()[:8],'question':question,'chosen':str(d.get('choice',d.get('chosen',''))),
             'confidence':float(d.get('confidence',0.5)),'reason':' '.join(str(d.get('reason','')).split()[:150]),'tier':t['name'],'needs':d.get('needs',[]),
             'usage':u,'cost_units':round(t['cost']*(u['in']+u['out'])/1000,3),'seconds':round(time.time()-t0,2)}
        hcore.decision_receipt(rec); s.tier=t['name']; s.log.append(rec)
        if s.trace: s.trace.escalation(t['name']); s.trace.frontier_turn(u['in'],u['out'],semantic=True,resident=u['in'])
        return rec
    def from_packet(s,step,packet,**kw):
        """turn an ESCALATE:<reason> EvidencePacket into an EscalationRequest + a micro decision"""
        reason=packet['recommended_transition'].split(':',1)[1] if ':' in packet['recommended_transition'] else 'low_confidence'
        q=hcore.escalation_request({'goal_id':packet['goal_id'],'step_id':packet['step_id'],'reason':reason,'evidence':[o['id'] for o in packet['observations']],
             'decision_required':kw.pop('decision_required',f"Step {packet['step_id']} stopped ({reason}). {'; '.join(packet['contradictions']+packet['unresolved'])[:300]} What should happen next?"),'constraints':step.get('invariants',[])})
        ev=[f"{o['id']}: {o['text'][:240]}" for o in packet['observations'][:6]]
        return q,s.micro(q['decision_required'],evidence=ev,constraints=q['constraints'],**kw)
    def de_escalate(s,decision,scope='',session='s0',path=None,root='.',existing=None,evidence_refs=()):
        """promote the decision into canonical memory (via the proposer/decider gate), then drop back to the base tier"""
        prop=hcore.claim_proposal({'proposal_id':'P'+decision['decision_id'],'claim':f"Decision: {decision['question']} -> {decision['chosen']}. {decision['reason']}",'scope':scope or 'decision',
             'proposer':f"escalation:{decision['tier']}",'evidence':list(evidence_refs) or [decision['decision_id']]})
        ex=existing if existing is not None else ([{'claim':c['claim'],'scope':c['scope']} for c in hclaims.all_claims(root,path)] if hclaims else [])
        ok,why=hcore.may_promote_claim(prop,ex)
        cid=None
        if ok and hclaims and decision['confidence']>=0.5: cid=hclaims.add(prop['claim'],'CONFIRMED',prop['scope'],prop['evidence'],[],type='decision',session=session,root=root,path=path)
        s.tier=s.base; return {'promoted':cid,'gate':why if not ok else ('ok' if cid else 'low_confidence'),'tier':s.tier}
