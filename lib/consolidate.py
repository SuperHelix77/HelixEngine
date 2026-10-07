"""Proactive memory consolidation: BEFORE native compaction, classify state hot/warm/cold, promote durable information to memory,
turn raw material into handles, drop transient context. Native lossy summarization becomes the emergency fallback, not the persistence mechanism.
hot  = still needed verbatim next turn (recent window, user directives, unresolved errors)   -> stays in the capsule/context
warm = durable conclusions (assistant decisions/results, claims)                              -> claim ledger + hot index
cold = raw tool I/O                                                                          -> lossless archive, addressable by #seq handle only"""
import os,sys,re,json
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import hmem,capsule
try: import claims as hclaims
except Exception: hclaims=None
def classify(units,window=12):
    last=units[-1]['seq'] if units else 0; hot=[];warm=[];cold=[]
    for u in units:
        recent=u['seq']>last-window
        err=u['kind']=='result' and capsule.CUE_PROB.search(u['text'][:600]) is not None and recent
        if u['kind']=='user' or recent or err: hot.append(u['seq'])
        elif u['kind']=='assistant' and (capsule.CUE_DEC.search(u['text']) or capsule.CUE_FACT.search(u['text'])): warm.append(u['seq'])
        else: cold.append(u['seq'])
    return {'hot':hot,'warm':warm,'cold':cold}
def consolidate(transcript,session,db=None,root='.',budget_tokens=1200,out_dir=None):
    """incremental: only units newer than the stored watermark are ingested; returns stats and writes capsule.<session>.txt"""
    db=db or hmem.DB; units=hmem.units_from_transcript(transcript)
    done=int(hmem.meta_get(session,'last_seq',-1,db)); new=[u for u in units if u['seq']>done]
    n=hmem.ingest(new,session=session,path=db) if new else 0
    if units: hmem.meta_set(session,'last_seq',units[-1]['seq'],db)
    cl=hclaims.all_claims(root,db,session=None) if hclaims else []
    cap=capsule.build_map(units,claim_list=cl,claim_cap=18) if units else ''
    # budget: trim claim hot index first (claims are retrievable), then phases
    while len(cap)/3.6>budget_tokens and '\n PHASES' not in cap[:0]:
        lines=cap.split('\n'); i=next((k for k,l in enumerate(lines) if l.startswith(' C') and ' | ' in l),None)
        if i is None: break
        parts=lines[i].split(' | ')
        if len(parts)<=3: break
        lines[i]=' | '.join(parts[:-2]); cap='\n'.join(lines)
    od=out_dir or os.path.dirname(db) or '.'; path=os.path.join(od,f'capsule.{session}.txt'); open(path,'w').write(cap)
    cls=classify(units)
    return {'ingested':n,'total_units':len(units),'hot':len(cls['hot']),'warm':len(cls['warm']),'cold':len(cls['cold']),'capsule_chars':len(cap),'capsule_path':path}
def session_start_context(session,db=None,out_dir=None,max_chars=5000):
    od=out_dir or os.path.dirname(db or hmem.DB) or '.'; p=os.path.join(od,f'capsule.{session}.txt')
    if not os.path.exists(p): return ''
    t=open(p).read(); return t[:max_chars]
