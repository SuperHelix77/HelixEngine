"""HELIX deterministic controller (reference scheduler). No model in the loop.
Executes a GoalStep inside its ExecutionEnvelope: plan ops from required evidence, authorize each op, run, record receipts,
check completion, emit one EvidencePacket. Escalates (never guesses) when the envelope is exhausted, evidence is
contradictory/ambiguous, or a required capability is not granted.
"""
import os,sys,json,time,re
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import hcore,hops
try:
    import hmem,claims
except Exception: hmem=claims=None

HOME=os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKT_DIR=os.path.join(HOME,'run','packets')
def pkt_dirs():
    """persistence candidates, first writable wins; failure to persist must never abort an investigation"""
    return [d for d in (os.environ.get('HELIX_PKT_DIR'),PKT_DIR,os.path.join(os.getcwd(),'.helix','packets')) if d]
def persist_packet(pid,obj):
    for d in pkt_dirs():
        try:
            os.makedirs(d,exist_ok=True); p=os.path.join(d,pid+'.json')
            with open(p,'w') as f: json.dump(obj,f,default=str)
            return p
        except OSError: continue
    return None

# requirement kind -> op names it needs (policy checks every one)
KIND_OPS={'callers':['FIND_CALLERS'],'symbol':['READ_SYMBOL'],'callees':['FIND_CALLEES'],'imports':['FIND_IMPORTS'],'tests':['CHECK_TEST'],
          'outline':['OUTLINE'],'memory':['QUERY_MEMORY'],'coverage':['OUTLINE','CHECK_TEST'],'impact':['FIND_CALLERS','READ_SYMBOL']}

class Run:
    def __init__(s,step,root='.',session=None):
        s.step=hcore.goal_step(step); s.env=s.step['envelope']; s.root=root; s.t0=time.time(); s.ops=0; s.raw=0
        s.obs=[]; s.receipts=[]; s.unres=[]; s.contra=[]; s.refs=[]; s.rawstore={}; s.exhausted=False; s.denied=[]; s.n=0
    def left(s):
        b=s.env['budget']
        if s.ops>=b['ops']: return 'ops'
        if time.time()-s.t0>b['seconds']: return 'seconds'
        if s.raw/1e6>b['raw_mb']: return 'raw_mb'
        return None
    def op(s,opname,fn,**args):
        ok,why=hcore.authorize(opname,s.env)
        if not ok: s.denied.append((opname,why)); return None
        lim=s.left()
        if lim: s.exhausted=True; s.unres.append(f'envelope exhausted ({lim}) before {opname}'); return None
        t=time.time(); res=fn(); ms=int((time.time()-t)*1000); s.ops+=1
        try: sz=len(json.dumps(res,default=str))
        except Exception: sz=0
        s.raw+=sz; s.receipts.append({'op':opname,'args':args,'ms':ms,'bytes':sz}); return res
    def observe(s,text,raw=None,ref=None):
        s.n+=1; oid=f'O{s.n}'; s.obs.append({'id':oid,'text':text})
        if raw is not None: s.rawstore[oid]=raw
        if ref: s.refs.append(ref)
        return oid

def _hits(res):
    return [h for h in res['hits'] if h['fn']!='<import>']
def _group(hs):
    g={}
    for h in hs: g.setdefault((h['file'],h['fn']),[]).append(h['line'])
    return g

def _need_callers(r,q):
    name=q['name']; res=r.op('FIND_CALLERS',lambda:hops.callers(name,r.root,q.get('deffile')),name=name,deffile=q.get('deffile'))
    if res is None: return
    if len(res['defs'])>1 and not q.get('deffile'): r.contra.append(f"ambiguous_definition:{name} has {len(res['defs'])} defs ({', '.join(d['file']+':'+str(d['line']) for d in res['defs'][:4])})")
    if not res['defs'] and not res['hits']: r.unres.append(f'{name}: no definition or reference found')
    hs=_hits(res); prod=_group([h for h in hs if not h['test']]); test=_group([h for h in hs if h['test']])
    wr={(h['file'],h['fn']) for h in hs if h.get('wrapper')}
    fmt=lambda g,n:' '.join(f"{os.path.basename(f)}:{fn}{'[wrapper]' if (f,fn) in wr else ''}" for (f,fn) in list(g)[:n])
    r.observe(f"callers({name}) def {','.join(d['file']+':'+str(d['line']) for d in res['defs']) or 'none'}: prod {len(prod)} [{fmt(prod,10)}] test {len(test)} [{fmt(test,6)}]",res,f'ast://callers/{name}')
    if q.get('depth',1)>=2:
        seen=set()
        for (f,fn) in list(prod)[:8]:
            if fn in('<module>',) or (f,fn) in seen: continue
            seen.add((f,fn)); res2=r.op('FIND_CALLERS',lambda:hops.callers(fn,r.root,f),name=fn,deffile=f)
            if res2 is None: break
            h2=_hits(res2); p2=_group([h for h in h2 if not h['test']]); t2=_group([h for h in h2 if h['test']])
            r.observe(f"callers({fn}) [depth2 via {name}]: prod {len(p2)} [{fmt(p2,6)}] test {len(t2)} [{fmt(t2,4)}]",res2,f'ast://callers/{fn}')
    if q.get('bodies'):
        for (f,fn) in list(prod)[:int(q['bodies'])]:
            if fn=='<module>': continue
            sy=r.op('READ_SYMBOL',lambda:hops.symbol(f,fn,int(q.get('cap',24))),file=f,name=fn)
            if sy: r.observe(f"sym {f}:{fn}\n{sy['src']}",sy,f'ast://{f}#{fn}')

def _need_symbol(r,q):
    sy=r.op('READ_SYMBOL',lambda:hops.symbol(q['file'],q['name'],int(q.get('cap',40))),file=q['file'],name=q['name'])
    if sy is None:
        if not r.exhausted and not r.denied: r.unres.append(f"symbol {q['name']} not found in {q['file']}")
        return
    r.observe(f"sym {sy['file']}:{sy['name']} lines {sy['lines'][0]}-{sy['lines'][1]}\n{sy['src']}",sy,f"ast://{q['file']}#{q['name']}")

def _need_callees(r,q):
    cs=r.op('FIND_CALLEES',lambda:hops.callees(q['file'],q['name'],r.root),file=q['file'],name=q['name'])
    if cs is None:
        if not r.exhausted and not r.denied: r.unres.append(f"callees: {q['name']} not found in {q['file']}")
        return
    inrepo=[c for c in cs if c['defs']]; fn=lambda c:f"{c['name']}@{c['defs'][0].split('/')[-1]}"
    uniq=[c for c in inrepo if c['ndefs']==1 and c['kind']=='function']; cls=[c for c in inrepo if c['kind']=='class' and c['ndefs']==1]; amb=[c for c in inrepo if c['ndefs']>1]
    r.observe(f"callees({q['name']}): UNIQUE repo functions ({len(uniq)}): "+' '.join(fn(c) for c in uniq[:20])+f" | CLASSES (constructor calls, not functions) ({len(cls)}): "+(' '.join(fn(c) for c in cls[:10]) or 'none')
              +f" | AMBIGUOUS names defined several times, call target NOT resolved ({len(amb)}): "+(' '.join(f"{c['name']}x{c['ndefs']}" for c in amb[:10]) or 'none')+f" | external/builtin {len(cs)-len(inrepo)}",cs,f"ast://{q['file']}#{q['name']}/callees")

def _need_imports(r,q):
    res=r.op('FIND_IMPORTS',lambda:hops.callers(q['name'],r.root,q.get('deffile')),name=q['name'])
    if res is None: return
    imps=[h for h in res['hits'] if h['fn']=='<import>']; use=_group([h for h in _hits(res) if h['src']!='local'])
    r.observe(f"imports({q['name']}): "+('; '.join(f"{os.path.basename(h['file'])}:{h['line']} from {h['src']}{' [test]' if h['test'] else ''}" for h in imps) or 'none')+(' | uses: '+' '.join(f"{os.path.basename(f)}:{fn}" for (f,fn) in use) if use else ''),res,f"ast://imports/{q['name']}")

def _need_tests(r,q):
    if q.get('deffile'):   # import-resolved: only tests bound to the definition in deffile
        res=r.op('CHECK_TEST',lambda:hops.callers(q['name'],r.root,q['deffile']),name=q['name'],deffile=q['deffile'])
        if res is None: return
        g=_group([h for h in _hits(res) if h['test']]); imp=[h for h in res['hits'] if h['fn']=='<import>' and h['test']]
        impf=sorted({os.path.basename(h['file']) for h in imp}); used={os.path.basename(f) for (f,fn) in g}
        r.observe(f"tests({q['name']}@{q['deffile']}): {len(g)} test fn(s) "+' '.join(f"{os.path.basename(f)}:{fn}" for (f,fn) in list(g)[:8])+(f" | imported by test files: {' '.join(impf)}"+(f" (import-only, no direct use: {' '.join(x for x in impf if x not in used)})" if any(x not in used for x in impf) else '') if impf else ''),res,f"ast://tests/{q['name']}"); return
    tr=r.op('CHECK_TEST',lambda:hops.test_refs(q['name'],r.root),name=q['name'])
    if tr is None: return
    r.observe(f"tests({q['name']}): {len(tr)} reference(s) "+' '.join(f"{os.path.basename(t['file'])}:{t['fn']}" for t in tr[:8]),tr,f"ast://tests/{q['name']}")

def _need_outline(r,q):
    pf=r.op('OUTLINE',lambda:hops.public_functions(q['file']),file=q['file'])
    if pf is None: r.unres.append(f"outline: cannot parse {q['file']}"); return
    r.observe(f"outline({q['file']}) public: "+' '.join((f"{f['owner']}." if f['owner'] else '')+f['name'] for f in pf),pf,f"ast://{q['file']}#outline")

def _need_coverage(r,q):
    pf=r.op('OUTLINE',lambda:hops.public_functions(q['file']),file=q['file'])
    if pf is None: r.unres.append(f"coverage: cannot parse {q['file']}"); return
    un=[];cov=[]
    for f in pf:
        tr=r.op('CHECK_TEST',lambda:hops.test_refs(f['name'],r.root),name=f['name'])
        if tr is None: r.unres.append(f"coverage incomplete at {f['name']}"); break
        (cov if tr else un).append(f)
    dc=hops.def_counts(r.root); lab=lambda f:(f"{f['owner']}." if f['owner'] else '')+f['name']+('*' if dc.get(f['name'],1)>1 else '')
    r.observe(f"coverage({q['file']}) public {len(pf)}: covered {len(cov)}; NOT referenced by any test ({len(un)}): "+' '.join(lab(f) for f in un)+"  [name-based; * = name defined more than once in the repo, so a test mention of the name may refer to another symbol]",{'covered':cov,'uncovered':un},f"ast://{q['file']}#coverage")

def _need_memory(r,q):
    if hmem is None: r.unres.append('memory backend unavailable'); return
    def go():
        out={'claims':[claims.fmt(d) for d in claims.search(q['q'],3)] if claims else [],'passages':[{'seq':p['seq'],'text':p['text'][:240]} for p in hmem.search_passages(q['q'],4)]}
        return out
    res=r.op('QUERY_MEMORY',go,q=q['q'])
    if res is None: return
    r.observe(f"memory({q['q']}): "+' | '.join(res['claims'])+' || '+' | '.join(f"#{p['seq']} {p['text'][:140]}" for p in res['passages']),res,f"hmem://q/{q['q'][:30]}")

def _need_impact(r,q):
    q=dict(q); q.update({'depth':2,'bodies':q.get('bodies',3)}); _need_callers(r,q)

HANDLERS={'callers':_need_callers,'symbol':_need_symbol,'callees':_need_callees,'imports':_need_imports,'tests':_need_tests,'outline':_need_outline,'coverage':_need_coverage,'memory':_need_memory,'impact':_need_impact}

def evaluate(pred,r,n_req,n_done):
    if pred in('all_evidence',None): return n_done>=n_req and not r.unres
    if isinstance(pred,dict) and 'min_observations' in pred: return len(r.obs)>=pred['min_observations'] and not r.unres
    return n_done>=n_req and not r.unres

def run_step(step,root='.',session=None,persist=True):
    r=Run(step,root,session); reqs=r.step['required_evidence']; done=0
    for q in reqs:
        kind=q['kind']
        if kind not in HANDLERS: r.unres.append(f'unknown evidence kind {kind!r}'); continue
        need=KIND_OPS[kind]; miss=[o for o in need if not hcore.authorize(o,r.env)[0]]
        if miss: r.denied.append((kind,f'capability not granted: {miss}')); r.unres.append(f'{kind}: capability not granted ({",".join(miss)})'); continue
        before=len(r.obs)
        try: HANDLERS[kind](r,q)
        except Exception as e: r.unres.append(f'{kind}: {type(e).__name__}: {e}')
        if len(r.obs)>before and not r.exhausted: done+=1
        if r.exhausted: break
    complete=evaluate(r.step['completion_predicate'],r,len(reqs),done)
    # transition decided by deterministic policy, never by a model
    if r.exhausted: trans='ESCALATE:envelope_exhausted'
    elif r.contra: trans='ESCALATE:ambiguity'
    elif r.denied: trans='ESCALATE:missing_capability'
    elif not complete: trans='ESCALATE:low_confidence'
    else: trans='DONE'
    pid=f"EP-{int(r.t0*1000)%10**7}"; comp=done/max(1,len(reqs))
    pkt={'packet_id':pid,'goal_id':step.get('goal_id','G'),'step_id':r.step['step_id'],'observations':r.obs,'evidence_refs':r.refs,'claim_refs':[],'contradictions':r.contra,'unresolved':r.unres,
         'operation_receipts':r.receipts,'confidence':round(1.0 if complete else max(0.0,comp*0.8),2),'completeness':round(comp,2),'raw_backing_refs':[f'raw://{pid}/{o}' for o in r.rawstore],'recommended_transition':trans}
    hcore.evidence_packet(pkt)
    if persist and r.rawstore:
        if persist_packet(pid,{'packet':pkt,'raw':r.rawstore}) is None:
            pkt['raw_backing_refs']=[]; pkt['unresolved'].append('raw evidence not persisted (no writable packet dir); observations above are complete')
    pkt['_stats']={'ops':r.ops,'seconds':round(time.time()-r.t0,3),'raw_bytes':r.raw}
    return pkt

def render(pkt,budget_tokens=None):
    """terse frontier-facing form. Truncates to the envelope's frontier-token budget; overflow stays addressable via raw://."""
    L=[f"{pkt['packet_id']} {pkt['step_id']} [{pkt['recommended_transition']} conf {pkt['confidence']} compl {pkt['completeness']} ops {pkt['_stats']['ops']} {pkt['_stats']['seconds']}s]"]
    for o in pkt['observations']: L.append(f"{o['id']} {o['text']}")
    if pkt['contradictions']: L.append('CONTRADICTIONS: '+'; '.join(pkt['contradictions']))
    if pkt['unresolved']: L.append('UNRESOLVED: '+'; '.join(pkt['unresolved']))
    if pkt['raw_backing_refs']: L.append('raw: hstep raw '+pkt['packet_id']+' Ox  ('+str(len(pkt['raw_backing_refs']))+' backed)')
    out='\n'.join(L); cap=(budget_tokens or 1500)*3.6
    if len(out)>cap: out=out[:int(cap)]+f"\n..[truncated; full packet: hstep raw {pkt['packet_id']}]"
    return out

def fetch_raw(pid,oid=None):
    for dd in pkt_dirs():
        p=os.path.join(dd,pid+'.json')
        if os.path.exists(p):
            d=json.load(open(p)); return d['raw'].get(oid) if oid else d['packet']
    return None
