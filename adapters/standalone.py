#!/usr/bin/env python3
"""Standalone reference adapter = the conformance runner: executes a GoalGraph with no host (no Claude Code, no Codex).
  standalone.py run GRAPH.json [--root DIR] [--db FILE] [--micro MODEL]     standalone.py preflight "goal text" [--model sonnet]
Every host adapter must reproduce this behaviour through the six host operations."""
import os,sys,json
HOME=os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0,os.path.join(HOME,'lib'))
import hcore,scheduler,preflight,escalate
def main():
    a=sys.argv[1:]
    if not a: sys.exit(__doc__)
    opt=lambda f,d=None: (a[a.index(f)+1] if f in a else d)
    if a[0]=='preflight':
        g,u=preflight.preflight(a[1],model=opt('--model','sonnet')); print(json.dumps(g,indent=1)); sys.stderr.write(f'preflight tokens in={u["in"]} out={u["out"]}\n'); return
    if a[0]=='run':
        g=json.load(open(a[1])); esc=escalate.Escalator() if opt('--micro') else None
        st=scheduler.run_graph(g,root=opt('--root','.'),db=opt('--db'),escalator=esc)
        txt=scheduler.render_state(st)+('\n'+scheduler.render_escalation(st) if st.pending else ''); print(txt)
        os.makedirs(os.path.join(HOME,'run'),exist_ok=True); open(os.path.join(HOME,'run','state.txt'),'w').write(txt)
        sys.exit(0 if st.done else 2)
if __name__=='__main__': main()
