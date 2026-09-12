#!/usr/bin/env python3
"""Explicit named-plan invocation; no automatic routing or hook installation."""
import argparse
import json
import sys
import time
from pathlib import Path

from .evidence import Store
from . import named_plans


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store',required=True)
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('register').add_argument('spec')
    execute=commands.add_parser('execute-spec')
    execute.add_argument('spec');execute.add_argument('--timeout',type=float)
    rebind=commands.add_parser('rebind-inputs');rebind.add_argument('reference');rebind.add_argument('new_version',type=int)
    run=commands.add_parser('run');run.add_argument('reference');run.add_argument('--timeout',type=float)
    commands.add_parser('receipt').add_argument('sha256')
    args=parser.parse_args(argv)
    start=time.perf_counter();store=Store(args.store)
    try:
        registration=None
        if args.command in ('register','execute-spec'):
            spec=json.loads(Path(args.spec).read_text())
            required={'plan_id','plan_version','cwd','steps','files','executables'}
            if not isinstance(spec,dict) or not required<=set(spec) or set(spec)-required-{'env_names'}:
                raise ValueError('Registration requires identity, cwd, steps, files and executables; optional env_names')
            result=named_plans.register(store,**spec)
            registration=result
            if args.command=='register':
                print(json.dumps(result,separators=(',',':'),allow_nan=False))
                return 0
        elif args.command=='rebind-inputs':
            ref=json.loads(Path(args.reference).read_text())
            result=named_plans.rebind_inputs(store,ref,args.new_version);code=0
        elif args.command=='receipt':
            result=store.receipt(args.sha256);code=0
        if args.command in ('run','execute-spec'):
            ref=registration if registration is not None else json.loads(Path(args.reference).read_text())
            detail=named_plans.invoke(store,ref,timeout=args.timeout)
            # Persist the full returned accounting, including post-commit fields
            # omitted from the immutable attempt. This envelope is not semantic
            # acceptance and its own publication cost is not self-included.
            envelope={'schema':'helix.plan_cli_receipt.v1','result':detail,
                'registration':({'reference':registration,'creation_cost':named_plans.creation_cost(store,registration)}
                                if registration is not None else None),
                'elapsed_before_envelope_seconds':time.perf_counter()-start,
                'store_io_before_envelope':dict(store.metrics),
                'accounting_limits':'Envelope publication, physical I/O and model costs excluded; native tokens unknown.'}
            envelope_hash=store.put(named_plans.encode(envelope))['sha256']
            result={'schema':'helix.plan_cli.v1','status':detail['status'],
                'semantic_success':None,'attempt_hash':detail['attempt_hash'],
                'details':envelope_hash,'event_id':detail['event_id'],
                'workspace':detail['workspace'],
                'steps_completed':len(detail['steps']),
                'steps':[{'name':s['name'],'exit_code':s['exit_code'],'receipt':s['receipt']} for s in detail['steps']],
                'failed_steps':[s['name'] for s in detail['steps'] if not s['process_success']],
                'error_present':detail['error'] is not None}
            if registration is not None:result['plan']=registration
            code=0 if detail['status']=='SUCCEEDED' else 1
    except (OSError,ValueError,TypeError,KeyError) as exc:
        detail={'schema':'helix.plan_cli_error.v1','error_type':type(exc).__name__,
                'error':str(exc),'command':args.command}
        receipt=store.put(named_plans.encode(detail))['sha256']
        result={'schema':'helix.plan_cli.v1','status':'ERROR','details':receipt,
                'error_type':type(exc).__name__}
        code=2
    print(json.dumps(result,separators=(',',':'),allow_nan=False))
    return code


if __name__=='__main__':sys.exit(main())
