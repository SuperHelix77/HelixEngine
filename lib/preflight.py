"""Frontier preflight: ONE call converts a broad goal into a validated GoalGraph (5-10 typed step contracts).
The frontier states WHAT evidence is needed and WHEN a step is complete - never shell commands."""
import os,sys,json,re
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import hcore,hcontrol
from escalate import claude_caller
KINDS=sorted(hcontrol.HANDLERS)
SPEC=f"""Convert the GOAL into a GoalGraph as JSON. 5-10 steps. State what evidence each step needs and when it is complete; do NOT write shell commands.
Schema: {{"goal_id":str,"objective":str,"global_invariants":[str],"completion_predicate":"all_steps_done","steps":[{{"step_id":"S1","objective":str,"depends_on":[step_id],
"required_evidence":[{{"kind":one of {KINDS},"name"|"file"|"q":..., "deffile":optional path, "depth":optional int, "bodies":optional int}}],
"invariants":[str],"completion_predicate":"all_evidence","risk_class":"low|medium|high","envelope":{{"may":[subset of {list(hcore.OPS_READONLY)}],"budget":{{"ops":int,"seconds":int,"frontier_tokens":int}}}}}}]}}
Evidence kinds: callers{{name,deffile?,depth?,bodies?}} impact{{name,deffile?}} symbol{{file,name}} callees{{file,name}} imports{{name,deffile?}} tests{{name,deffile?}} outline{{file}} coverage{{file}} memory{{q}}.
Steps must be read-only unless the goal explicitly requires a change. Reply with ONLY the JSON."""
def check(graph):
    g=hcore.goal_graph(graph)
    for s in g['steps']:
        for i,r in enumerate(s['required_evidence']):
            if r['kind'] not in hcontrol.HANDLERS: raise hcore.ProtocolError(f"step {s['step_id']} required_evidence[{i}]: unsupported kind {r['kind']!r} (supported: {KINDS})")
    return g
def preflight(goal,context='',model='sonnet',caller=claude_caller,retries=1):
    prompt=f"{SPEC}\n\nGOAL: {goal}"+(f"\nCONTEXT: {context}" if context else ''); usage={'in':0,'out':0}; err=None
    for attempt in range(retries+1):
        txt,u=caller(model,prompt if not err else prompt+f"\n\nYour previous reply was invalid: {err}\nFix it and reply with ONLY the JSON.")
        usage['in']+=u['in']; usage['out']+=u['out']
        try:
            m=re.search(r'\{.*\}',txt,re.S); g=check(json.loads(m.group(0))); return g,usage
        except (ValueError,hcore.ProtocolError,AttributeError) as e: err=str(e)[:300]
    raise hcore.ProtocolError(f'preflight failed after {retries+1} attempt(s): {err}')
