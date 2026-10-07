"""HELIX Core v0.1 - execution protocol (provider-independent).

Frontier inference defines, adjudicates and revises the loop; HELIX executes it.
Records: GoalGraph, GoalStep, ExecutionEnvelope, EvidencePacket, ClaimProposal, DecisionReceipt, EscalationRequest.
Authority rule: a model (Laya/local/frontier) may PROPOSE; HELIX policy DECIDES. Mutation, claim promotion and
goal completion are never delegated to a proposer.
Nothing in this module may import a model SDK, an adapter, or a memory backend.
"""
import json,hashlib,re

PROTOCOL_VERSION='0.1'
RISK=('low','medium','high')
CLAIM_STATUS=('CONFIRMED','FALSIFIED','OPEN','PROPOSED')
# closed vocabulary of local operations; mutation ops must be granted explicitly in an envelope's `may`
OPS_READONLY=('SEARCH_SYMBOL','READ_SYMBOL','FIND_CALLERS','FIND_CALLEES','FIND_IMPORTS','CHECK_TEST','OUTLINE','QUERY_MEMORY','VERIFY')
OPS_MUTATING=('PATCH_RANGE','RUN_CMD','WRITE_FILE')
OPS=OPS_READONLY+OPS_MUTATING
TRANSITIONS=('DONE','NEXT_STEP','VALIDATE_CLAIM','ESCALATE','RETRY','ABORT')

class ProtocolError(ValueError): pass

def _req(d,path,key,typ):
    if key not in d: raise ProtocolError(f'{path}.{key}: missing')
    if not isinstance(d[key],typ): raise ProtocolError(f'{path}.{key}: expected {typ.__name__}, got {type(d[key]).__name__}')
    return d[key]
def _opt(d,path,key,typ,default):
    v=d.get(key,default)
    if not isinstance(v,typ): raise ProtocolError(f'{path}.{key}: expected {typ.__name__}')
    return v
def _ids(v,path):
    if not all(isinstance(x,str) and x for x in v): raise ProtocolError(f'{path}: ids must be non-empty strings')

def envelope(d,path='envelope'):
    if not isinstance(d,dict): raise ProtocolError(f'{path}: expected object')
    may=_opt(d,path,'may',list,[]); not_=_opt(d,path,'may_not',list,[])
    for o in may+not_:
        if o not in OPS: raise ProtocolError(f'{path}: unknown operation {o!r}')
    if set(may)&set(not_): raise ProtocolError(f'{path}: operation both allowed and forbidden: {sorted(set(may)&set(not_))}')
    b=_opt(d,path,'budget',dict,{})
    out={'may':may,'may_not':not_,'budget':{'ops':int(b.get('ops',40)),'seconds':float(b.get('seconds',120)),'raw_mb':float(b.get('raw_mb',20)),'frontier_tokens':int(b.get('frontier_tokens',1500))},
         'stop_when':_opt(d,path,'stop_when',(str,dict),'all_evidence'),'escalate_when':_opt(d,path,'escalate_when',list,['contradiction','missing_capability','low_confidence','envelope_exhausted'])}
    if min(out['budget'].values())<=0: raise ProtocolError(f'{path}.budget: all limits must be > 0')
    return out

def goal_step(d,path='step'):
    if not isinstance(d,dict): raise ProtocolError(f'{path}: expected object')
    sid=_req(d,path,'step_id',str); obj=_req(d,path,'objective',str)
    if not sid or not obj: raise ProtocolError(f'{path}: step_id and objective must be non-empty')
    req=_opt(d,path,'required_evidence',list,[])
    for i,r in enumerate(req):
        if not isinstance(r,dict) or 'kind' not in r: raise ProtocolError(f'{path}.required_evidence[{i}]: needs {{"kind":...}}')
    risk=_opt(d,path,'risk_class',str,'low')
    if risk not in RISK: raise ProtocolError(f'{path}.risk_class: one of {RISK}')
    dep=_opt(d,path,'depends_on',list,[]); _ids(dep,f'{path}.depends_on')
    return {'step_id':sid,'objective':obj,'depends_on':dep,'known_state_refs':_opt(d,path,'known_state_refs',list,[]),
            'required_evidence':req,'invariants':_opt(d,path,'invariants',list,[]),'completion_predicate':_opt(d,path,'completion_predicate',(str,dict),'all_evidence'),
            'uncertainty_budget':float(_opt(d,path,'uncertainty_budget',(int,float),0.1)),'risk_class':risk,
            'escalation_policy':_opt(d,path,'escalation_policy',dict,{}),'output_schema':_opt(d,path,'output_schema',(str,dict),'evidence_packet'),
            'envelope':envelope(_opt(d,path,'envelope',dict,{'may':list(OPS_READONLY)}),f'{path}.envelope')}

def goal_graph(d):
    if not isinstance(d,dict): raise ProtocolError('graph: expected object')
    steps=[goal_step(s,f'steps[{i}]') for i,s in enumerate(_req(d,'graph','steps',list))]
    ids=[s['step_id'] for s in steps]
    if len(set(ids))!=len(ids): raise ProtocolError('graph.steps: duplicate step_id')
    for s in steps:
        for dep in s['depends_on']:
            if dep not in ids: raise ProtocolError(f"step {s['step_id']}: depends_on unknown step {dep}")
    # acyclicity
    seen={};
    def visit(i,stack=()):
        if i in stack: raise ProtocolError(f'graph: dependency cycle through {i}')
        if seen.get(i): return
        for dep in next(s for s in steps if s['step_id']==i)['depends_on']: visit(dep,stack+(i,))
        seen[i]=True
    for i in ids: visit(i)
    return {'goal_id':_req(d,'graph','goal_id',str),'objective':_req(d,'graph','objective',str),'global_invariants':_opt(d,'graph','global_invariants',list,[]),
            'completion_predicate':_opt(d,'graph','completion_predicate',(str,dict),'all_steps_done'),'steps':steps,'assumptions':_opt(d,'graph','assumptions',list,[]),
            'revision_policy':_opt(d,'graph','revision_policy',(str,dict),'invalidate_dependents')}

def evidence_packet(d):
    for k in('packet_id','goal_id','step_id'): _req(d,'packet',k,str)
    tr=_opt(d,'packet','recommended_transition',str,'DONE')
    if tr.split(':')[0] not in TRANSITIONS: raise ProtocolError(f'packet.recommended_transition: {tr!r}')
    for k in('observations','evidence_refs','claim_refs','contradictions','unresolved','operation_receipts','raw_backing_refs'): _opt(d,'packet',k,list,[])
    for i,o in enumerate(d.get('observations',[])):
        if not isinstance(o,dict) or 'id' not in o or 'text' not in o: raise ProtocolError(f'packet.observations[{i}]: needs id,text')
    for k in('confidence','completeness'):
        v=d.get(k,1.0)
        if not isinstance(v,(int,float)) or not 0<=v<=1: raise ProtocolError(f'packet.{k}: must be in [0,1]')
    return d

def claim_proposal(d):
    """A worker/model PROPOSES; HELIX validates and promotes. status is always PROPOSED here."""
    for k in('proposal_id','claim','scope','proposer'): _req(d,'proposal',k,str)
    if not d['claim'].strip(): raise ProtocolError('proposal.claim: empty')
    if not d.get('evidence'): raise ProtocolError('proposal.evidence: a proposal without evidence cannot be promoted')
    if d.get('status','PROPOSED')!='PROPOSED': raise ProtocolError('proposal.status: proposals are PROPOSED; only HELIX promotes')
    return {**d,'status':'PROPOSED'}

def decision_receipt(d):
    for k in('decision_id','question','chosen','tier'): _req(d,'decision',k,str)
    if not 0<=float(d.get('confidence',0))<=1: raise ProtocolError('decision.confidence: [0,1]')
    if len(re.findall(r'\S+',d.get('reason','')))>150: raise ProtocolError('decision.reason: <=150 words')
    return d

def escalation_request(d):
    for k in('goal_id','step_id','reason','decision_required'): _req(d,'escalation',k,str)
    if d['reason'] not in('contradiction','missing_capability','low_confidence','envelope_exhausted','ambiguity','high_risk'): raise ProtocolError('escalation.reason: unknown')
    _opt(d,'escalation','evidence',list,[]); _opt(d,'escalation','constraints',list,[])
    return d

# ---- policy: who may decide what (proposer/decider split) -------------------------------------
def authorize(op,env):
    """HELIX policy gate for an operation under an envelope. Read-only ops need to be listed in `may`; mutating ops need explicit grant."""
    if op not in OPS: return False,'unknown operation'
    if op in env['may_not']: return False,'forbidden by envelope'
    if op not in env['may']: return False,'not granted by envelope'
    return True,'ok'
def may_promote_claim(proposal,existing_claims,min_evidence=1):
    """deterministic validation + dedup gate. Returns (ok,reason). Laya may rank/propose duplicates; it does not decide."""
    if len(proposal.get('evidence',[]))<min_evidence: return False,'insufficient evidence'
    norm=lambda s:re.sub(r'\W+',' ',s.lower()).strip()
    for c in existing_claims:
        if norm(c['claim'])==norm(proposal['claim']) and c.get('scope','')==proposal.get('scope',''): return False,'duplicate'
    return True,'ok'

# ---- conformance ------------------------------------------------------------------------------
def canonical(o): return json.dumps(o,sort_keys=True,separators=(',',':'))
def protocol_hash():
    spec={'v':PROTOCOL_VERSION,'ops_ro':OPS_READONLY,'ops_mut':OPS_MUTATING,'transitions':TRANSITIONS,'risk':RISK,'claim_status':CLAIM_STATUS,
          'records':['GoalGraph','GoalStep','ExecutionEnvelope','EvidencePacket','ClaimProposal','DecisionReceipt','EscalationRequest']}
    return hashlib.sha256(canonical(spec).encode()).hexdigest()[:16]
