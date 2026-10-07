import sys,os,json
sys.path.insert(0,os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__))))); import route
cwd=sys.argv[1]; os.environ['CL_LOCAL_WRITE']='1'
CASES=[("In helixengine/, list every function that calls `digest` (the function imported from core/evidence.py). Reply as file:function, one per line.",'callers'),
("In helixengine/core/literal_edits.py, what does compile_edits do when two edits overlap? One sentence.",'ask'),
("Add a one-line docstring to every function in helixengine/pricing.py that lacks one. Change nothing else.",'docgen'),
("Summarize helixengine/core/renderer.py in one sentence.",'summ'),
("Which functions call put in helixengine?",'callers'),
("show me the source of compile_edits in literal_edits.py",'sym'),
("list functions in core/line_index.py",'outline'),
("what does helixengine/core/verification.py do?",'summ'),
("fix the bug in runtime.py where run() hangs",None),("refactor evidence.py to use dataclasses",None),("yes, go ahead",None),
("run the tests and tell me what fails",None),("why is the server slow?",None),("write a new module for caching",None),
("explain how the whole engine works",None),("rename digest to content_hash everywhere",None),("what does it do?",None),("summarize renderer.py and then fix its bug",None),("delete helixengine/core/renderer.py",None),("tell me about the evidence module",None),("who calls it?",None),("what is a sha256 digest?",None),("summarize all the files",None),("what does runtime.py do and rename run to execute",None),("describe helixengine/core/copy_handles.py",'summ'),("where is verify_index used?",'callers'),("update the README to mention the new flag",None)]
ok=fr=miss=0
for p,exp in CASES:
    a=route.decide(p,cwd); got=os.path.basename(a[0]) if a else None
    good=(got==exp); ok+=good
    if got and not exp: fr+=1
    if exp and not got: miss+=1
    print('OK ' if good else 'BAD',repr(exp),'->',repr(got),'|',p[:60])
print(f'accuracy {ok}/{len(CASES)}  false-route(should escalate but routed)={fr}  missed-route={miss}')
