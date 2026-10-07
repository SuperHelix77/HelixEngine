"""Post-tool semantic reduction: tool output -> tiny typed receipt BEFORE the frontier sees it (rtk compresses bytes; this compresses meaning).
Every receipt declares what was dropped and keeps the exact raw addressable (handle supplied by the caller)."""
import re,json
RE_PYTEST_SUM=re.compile(r'(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed|warnings?)',re.I)
RE_UNITTEST=re.compile(r'^(FAIL|ERROR): (\S+) \(([^)]+)\)',re.M)
RE_GREP=re.compile(r'^([^\s:][^:\n]*):(\d+):(.*)$')
RE_COMPILER=re.compile(r'^(?P<f>[^\s:]+):(?P<l>\d+)(?::(?P<c>\d+))?:\s*(?P<sev>error|warning|fatal error)[:\s]\s*(?P<m>.*)$',re.M)
RE_TRACE=re.compile(r'Traceback \(most recent call last\):.*?\n(?P<last>\w[\w.]*(?:Error|Exception|Warning)[^\n]*)',re.S)
class Receipt:
    def __init__(s,kind,text,loss,facts=None): s.kind=kind; s.text=text; s.loss=loss; s.facts=facts or {}
    def render(s,handle=None): return f"[{s.kind}] {s.text}"+(f"\n(dropped: {s.loss}; exact: {handle})" if handle else f"\n(dropped: {s.loss})")
def detect(out,cmd=''):
    c=cmd.lower()
    if re.search(r'\bpytest\b|unittest|\btest\b',c) or RE_UNITTEST.search(out) or re.search(r'^=+ .*(passed|failed).* =+$',out,re.M) or re.search(r'^Ran \d+ tests?',out,re.M): return 'tests'
    if RE_COMPILER.search(out): return 'compiler'
    st=out.strip()
    if st[:1] in '{[':
        try: json.loads(st); return 'json'
        except Exception: pass
    lines=[l for l in out.split('\n') if l.strip()]
    if len(lines)>=8 and sum(1 for l in lines if RE_GREP.match(l))/len(lines)>0.8: return 'grep'
    if out.startswith('diff --git') or re.search(r'^@@ .* @@',out,re.M): return 'diff'
    if RE_TRACE.search(out): return 'traceback'
    return 'generic'
def r_tests(out):
    fails=[(k,n,m) for k,n,m in RE_UNITTEST.findall(out)]
    ran=re.search(r'^Ran (\d+) tests?',out,re.M); sums={k.lower():int(n) for n,k in RE_PYTEST_SUM.findall(out)}
    pyfail=re.findall(r'^FAILED (\S+::\S+)(?: - (.*))?$',out,re.M)
    msgs=re.findall(r'^(E\s+.*|AssertionError.*|\w+Error:.*)$',out,re.M)
    items=[f"{n} ({m})" for k,n,m in fails]+[f"{t}{(' - '+m) if m else ''}" for t,m in pyfail]
    head=(f"ran {ran.group(1)}" if ran else ', '.join(f'{v} {k}' for k,v in sums.items()) or 'test run')
    status='FAILED' if items or sums.get('failed') or re.search(r'^FAILED|^FAIL',out,re.M) else ('OK' if re.search(r'\bOK\b|passed',out) else 'unknown')
    body=f"{status}; {head}; failing: "+('; '.join(items[:12]) if items else 'none listed')
    first=[m.strip() for m in msgs[:4]]
    if first: body+=" | key errors: "+' / '.join(x[:140] for x in first)
    return Receipt('tests',body,'passing-test output, full tracebacks, timing',{'failing':[i.split(' ')[0] for i in items],'status':status})
def r_compiler(out):
    ds=[m.groupdict() for m in RE_COMPILER.finditer(out)]; err=[d for d in ds if 'error' in d['sev']]; wr=[d for d in ds if d['sev']=='warning']
    fm=lambda d:f"{d['f']}:{d['l']} {d['m'][:100]}"
    return Receipt('compiler',f"{len(err)} error(s), {len(wr)} warning(s): "+'; '.join(fm(d) for d in err[:10])+(f" | warnings: {len(wr)} (first: {fm(wr[0])})" if wr else ''),'warnings detail, notes, source excerpts',{'errors':[(d['f'],int(d['l'])) for d in err]})
def _schema(v,depth=0):
    if isinstance(v,dict): return '{'+', '.join(f"{k}:{_schema(x,depth+1) if depth<2 else '..'}" for k,x in list(v.items())[:14])+(', …' if len(v)>14 else '')+'}'
    if isinstance(v,list): return f"[{len(v)}×{_schema(v[0],depth+1) if v and depth<2 else ''}]"
    return type(v).__name__
def r_json(out):
    v=json.loads(out); samp=json.dumps(v,separators=(',',':'))[:160]
    return Receipt('json',f"schema {_schema(v)} | sample {samp}",'values beyond the sample; all but first array element',{'type':type(v).__name__})
def r_grep(out):
    by={}
    for l in out.split('\n'):
        m=RE_GREP.match(l)
        if m: by.setdefault(m.group(1),[]).append((int(m.group(2)),m.group(3).strip()))
    parts=[f"{f}:{','.join(str(n) for n,_ in h[:8])}{'…' if len(h)>8 else ''} ({len(h)})" for f,h in by.items()]
    return Receipt('grep',f"{sum(len(h) for h in by.values())} hits in {len(by)} files: "+' | '.join(parts[:25])+(f" | +{len(parts)-25} files" if len(parts)>25 else ''),'matched line text (line numbers kept)',{'files':list(by)})
def r_diff(out):
    files=re.findall(r'^diff --git a/(\S+)',out,re.M); add=len(re.findall(r'^\+[^+]',out,re.M)); rm=len(re.findall(r'^-[^-]',out,re.M)); hunks=re.findall(r'^@@ .*? @@ ?(.*)$',out,re.M)
    return Receipt('diff',f"{len(files)} file(s) +{add}/-{rm}: "+', '.join(files[:12])+(' | hunks: '+'; '.join(h[:50] for h in hunks[:8]) if hunks else ''),'changed line contents',{'files':files})
def r_trace(out):
    m=RE_TRACE.search(out); frames=re.findall(r'File "([^"]+)", line (\d+), in (\w+)',out)
    return Receipt('traceback',f"{m.group('last')[:200]} | at "+' <- '.join(f"{f.split('/')[-1]}:{l} {fn}" for f,l,fn in frames[-3:][::-1]),'intermediate frames and source lines',{'error':m.group('last')[:80]})
REDUCERS={'tests':r_tests,'compiler':r_compiler,'json':r_json,'grep':r_grep,'diff':r_diff,'traceback':r_trace}
def reduce(out,cmd='',min_chars=600):
    """returns Receipt or None (None = leave output as is: small, generic, or reducer produced something not smaller)."""
    if len(out)<min_chars: return None
    k=detect(out,cmd); fn=REDUCERS.get(k)
    if not fn: return None
    try: r=fn(out)
    except Exception: return None
    return r if len(r.text)<len(out)*0.6 else None
