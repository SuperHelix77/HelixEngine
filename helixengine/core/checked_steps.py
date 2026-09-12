"""Explicit mandatory argv steps with individual evidence; no shell parsing."""
import json
from .evidence import run


def execute(store,steps,cwd,environment_id,timeout=None,env=None):
    if not isinstance(steps,list) or not steps:
        raise ValueError('Nonempty step list required')
    names=set()
    for step in steps:
        if not isinstance(step,dict) or set(step)!={'name','argv'}:
            raise ValueError('Each step requires name and argv only')
        name,argv=step['name'],step['argv']
        if not isinstance(name,str) or not name or name in names:
            raise ValueError('Unique nonempty step names required')
        names.add(name)
        if not isinstance(argv,list) or not argv or any(not isinstance(a,str) or '\x00' in a for a in argv) or not argv[0]:
            raise ValueError('Nonempty string argv required')
    if timeout is not None and (type(timeout) not in (int,float) or not 0<timeout<float('inf')):
        raise ValueError('Finite positive timeout required')
    results=[]
    for step in steps:
        packet=run(store,step['argv'],cwd,environment_id,timeout=timeout,env=env)
        ok=packet['exit_code']==0 and not packet['timed_out'] and not packet['interrupted']
        results.append({'name':step['name'],'receipt':packet['receipt'],'exit_code':packet['exit_code'],'timed_out':packet['timed_out'],'interrupted':packet['interrupted'],'process_success':ok})
        if not ok:break
    result={'schema':'helix.checked_steps.v1','process_success':len(results)==len(steps) and all(r['process_success'] for r in results),'steps':results,'unexecuted':[s['name'] for s in steps[len(results):]],'scope':'Conjunction of captured mandatory process statuses only; semantic truth and failures masked inside one argv process are not established'}
    receipt=store.put(json.dumps(result,separators=(',',':')).encode())
    return {**result,'sequence_receipt':receipt,'io':dict(store.metrics)}
