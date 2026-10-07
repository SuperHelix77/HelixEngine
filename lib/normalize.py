"""Claim normalization: local, deterministic conversion of observations into typed claims with provenance, dependencies and state.
No frontier tokens spent on writing memory. (A local-model refinement can sit on top; the deterministic form is the reference.)"""
import re,os,sys
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
RULES=[
 (re.compile(r'^callers\((?P<n>[\w.]+)\) def (?P<d>[^:\s]+):(?P<l>\d+)[^:]*: prod (?P<p>\d+) \[(?P<pl>.*?)\] test (?P<t>\d+)'),
  lambda m:(f"{m['n']} ({m['d']}) has {m['p']} production caller(s)" +(f" [{m['pl']}]" if m['p']!='0' else '')+f" and {m['t']} test caller(s)",[f"symbol://{m['d']}#{m['n']}"])),
 (re.compile(r'^coverage\((?P<f>[^)]+)\) public (?P<n>\d+): covered (?P<c>\d+); NOT referenced by any test \((?P<u>\d+)\): (?P<names>[^\[]*)'),
  lambda m:(f"{m['u']} of {m['n']} public functions in {m['f']} are not referenced by any test: {m['names'].strip()}",[f"file://{m['f']}"])),
 (re.compile(r'^imports\((?P<n>[\w.]+)\): (?P<rest>.*)'),lambda m:(f"imports of {m['n']}: {m['rest'][:200]}",[])),
 (re.compile(r'^tests\((?P<n>[\w.]+)(?:@(?P<d>[^)]+))?\): (?P<rest>.*)'),lambda m:(f"tests referencing {m['n']}: {m['rest'][:200]}",[f"symbol://{m['d']}#{m['n']}"] if m['d'] else [])),
 (re.compile(r'^callees\((?P<n>[\w.]+)\): (?P<rest>.*)'),lambda m:(f"callees of {m['n']}: {m['rest'][:200]}",[])),
]
def claims_from_packet(packet,scope=''):
    """-> list of ClaimProposal-shaped dicts (status PROPOSED), evidence = raw backing refs; deps feed dependency-driven invalidation."""
    out=[]; refs=packet.get('raw_backing_refs',[])
    for o in packet.get('observations',[]):
        head=o['text'].split('\n')[0]
        for rx,fn in RULES:
            m=rx.match(head)
            if m:
                text,deps=fn(m.groupdict()); ev=[r for r in refs if r.endswith('/'+o['id'])] or [f"{packet['packet_id']}#{o['id']}"]
                out.append({'proposal_id':f"{packet['packet_id']}-{o['id']}",'claim':text,'scope':scope or f"{packet['goal_id']}/{packet['step_id']}",'proposer':'helix:normalize','evidence':ev,'deps':deps,'status':'PROPOSED'}); break
    return out
