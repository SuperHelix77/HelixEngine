"""Single-agent HELIX scheduler: executes a GoalGraph with the deterministic controller. Frontier defines/adjudicates/revises; HELIX executes.
Multi-agent scheduling is intentionally out of scope for this version."""
import os,sys,json,time
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import hcore,hcontrol,normalize
try: import claims as hclaims
except Exception: hclaims=None

class GraphState:
    def __init__(s,graph): s.g=graph; s.steps={x['step_id']:{'status':'PENDING','packets':[],'transitions':[],'retries':0} for x in graph['steps']}; s.claims=[]; s.escalations=[]; s.pending=[]; s.aborted=False
    @property
    def done(s): return all(v['status'] in('DONE','PARTIAL') for v in s.steps.values())
def _ready(st):
    for x in st.g['steps']:
        sid=x['step_id']
        if st.steps[sid]['status']!='PENDING': continue
        if all(st.steps[d]['status'] in('DONE','PARTIAL') for d in x['depends_on']): yield x
def _promote(st,packet,root,db,session):
    ex=[{'claim':c['claim'],'scope':c['scope']} for c in hclaims.all_claims(root,db)] if hclaims else []
    for p in normalize.claims_from_packet(packet):
        ok,why=hcore.may_promote_claim(p,ex)
        if ok and hclaims:
            cid=hclaims.add(p['claim'],'CONFIRMED',p['scope'],p['evidence'],[],type='measurement',session=session,root=root,path=db,deps=p['deps']); st.claims.append(cid); ex.append({'claim':p['claim'],'scope':p['scope']})
def run_graph(graph,root='.',session='s0',db=None,escalator=None,trace=None,max_retries=1,persist=True):
    g=hcore.goal_graph(graph); st=GraphState(g)
    progress=True
    while progress and not st.aborted:
        progress=False
        for step in list(_ready(st)):
            sid=step['step_id']; rec=st.steps[sid]; cur=dict(step); cur['goal_id']=g['goal_id']
            while True:
                pkt=hcontrol.run_step(cur,root=root,persist=persist); rec['packets'].append(pkt['packet_id']); rec['transitions'].append(pkt['recommended_transition'])
                if trace: trace.local_op(pkt['_stats']['ops'])
                if pkt['recommended_transition']=='DONE': rec['status']='DONE'; _promote(st,pkt,root,db,session); break
                if escalator is None or rec['retries']>=max_retries:   # surface to the frontier boundary
                    rec['status']='ESCALATED'; st.pending.append({'step_id':sid,'packet':pkt['packet_id'],'transition':pkt['recommended_transition'],'contradictions':pkt['contradictions'],'unresolved':pkt['unresolved']}); _promote(st,pkt,root,db,session); break
                q,d=escalator.from_packet(cur,pkt,return_schema={'choice':'retry|accept_partial|abort','evidence_patch':'optional list of replacement required_evidence objects','confidence':'0-1','reason':'<=150 words'},tier='micro')
                st.escalations.append({'step_id':sid,'decision':d['decision_id'],'choice':d['chosen'],'tier':d['tier']}); rec['retries']+=1
                if d['chosen']=='abort': rec['status']='ABORTED'; st.aborted=True; break
                if d['chosen']=='accept_partial': rec['status']='PARTIAL'; _promote(st,pkt,root,db,session); break
                patch=None
                try: patch=json.loads(d.get('raw_patch','null')) if d.get('raw_patch') else None
                except Exception: patch=None
                if patch: cur['required_evidence']=patch
            progress=True
            if st.aborted: break
    return st
def render_state(st):
    """<helix-state>: tiny typed block for mid-work injection at a natural inference boundary (no user-visible turn)"""
    L=['<helix-state>',f"goal={st.g['goal_id']} "+('DONE' if st.done else ('ABORTED' if st.aborted else 'IN_PROGRESS'))]
    for sid,v in st.steps.items(): L.append(f"{sid}={v['status']}"+(f" {','.join(v['packets'][-1:])}" if v['packets'] else '')+(f" via {'>'.join(v['transitions'])}" if len(v['transitions'])>1 else ''))
    if st.claims: L.append('claims='+','.join('C'+c[:6] for c in st.claims[:8]))
    L.append('</helix-state>'); return '\n'.join(L)
def render_escalation(st):
    if not st.pending: return ''
    p=st.pending[0]
    return f"<helix-escalation>\ngoal={st.g['goal_id']} step={p['step_id']} reason={p['transition'].split(':')[-1]}\npacket={p['packet']}\n"+('; '.join(p['contradictions']+p['unresolved'])[:300])+"\ndecision_required: how should step "+p['step_id']+" proceed (retry with different evidence / accept partial / abort)?\n</helix-escalation>"
