"""Token-saving benchmark task generator: read-only code-intelligence tasks over several repos, ground truth by an independent TEXTUAL method
cross-checked with AST (tasks where the two disagree are dropped). Deterministic (seeded)."""
import os,re,ast,json,random,sys,glob
H=os.environ.get('HELIX_HOME',os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0,H+'/lib'); import hops
random.seed(int(os.environ.get('TS_SEED','5')))
SKIP=('docs','examples','build','.git','__pycache__','node_modules','scripts','benchmarks','fixtures','results')
def files(root):
    prod=[];test=[]
    for p in glob.glob(root+'/**/*.py',recursive=True):
        rel=os.path.relpath(p,root)
        if any(s in rel.split(os.sep) for s in SKIP): continue
        (test if (('tests' in rel.split(os.sep)) or os.path.basename(rel).startswith('test_') or rel.endswith('_test.py')) else prod).append(rel)
    return sorted(prod),sorted(test)
def strip_noise(lines):
    """blank out comment lines and docstring/triple-quote blocks (text method must not count mentions)"""
    out=[];inq=None
    for l in lines:
        s=l.strip()
        if inq:
            if inq in l: inq=None
            out.append(''); continue
        for q in('"""',"'''"):
            if s.startswith(q) or s.startswith('r'+q) or s.startswith('f'+q):
                if s.count(q)>=2 and not s.endswith(q*1) is False and s.count(q)%2==0: out.append(''); break
                inq=q; out.append(''); break
        else: out.append('' if s.startswith('#') else l)
    return out
DEF=re.compile(r'^(\s*)(?:async\s+)?def\s+(\w+)\s*\(')
def enclosing(lines,i):
    ind=len(lines[i])-len(lines[i].lstrip())
    for j in range(i-1,-1,-1):
        m=DEF.match(lines[j])
        if m and len(m.group(1))<ind: return m.group(2)
        if lines[j].strip() and not lines[j].startswith((' ','\t')) and not DEF.match(lines[j]) and ind>0: pass
    return '<module>'
class Repo:
    def __init__(s,name,root):
        s.name=name; s.root=root; s.prod,s.test=files(root); s.lines={p:strip_noise(open(os.path.join(root,p)).read().split('\n')) for p in s.prod+s.test}
        s.defs={}
        for p in s.prod:
            for i,l in enumerate(s.lines[p]):
                m=DEF.match(l)
                if m: s.defs.setdefault(m.group(2),[]).append((p,i))
        s.testtext='\n'.join('\n'.join(s.lines[p]) for p in s.test)
    def unique(s,name): return len(s.defs.get(name,[]))==1
def text_callers(r,name):
    out=set()
    rx=re.compile(r'(?<![\w.])(?:\w+\.)*'+re.escape(name)+r'\s*\(')
    rx2=re.compile(r'\b'+re.escape(name)+r'\s*\(')
    for p in r.prod:
        for i,l in enumerate(r.lines[p]):
            if rx2.search(l) and not DEF.match(l) and not l.strip().startswith('@'): out.add(enclosing(r.lines[p],i))
    return out
def ast_callers(r,name,deffile):
    cwd=os.getcwd(); os.chdir(r.root)
    try: res=hops.callers(name,'.',deffile)
    finally: os.chdir(cwd)
    return {h['fn'] for h in res['hits'] if h['fn']!='<import>' and not h['test']}
def make(r,quota=None):
    quota=quota or {'callers':2,'coverage':1,'defparams':1,'importers':1,'docaudit':1,'callees':1,'testcount':1}
    T=[]; names=[n for n in r.defs if r.unique(n) and len(n)>=5 and not n.startswith('__') and not n.startswith('test')]; random.shuffle(names)
    # F1 callers
    for n in names:
        if sum(1 for t in T if t['family']=='callers')>=quota['callers']: break
        p,_=r.defs[n][0]; tc=text_callers(r,n); tc.discard(n)
        if not 1<=len(tc)<=6: continue
        ac=ast_callers(r,n,p); ac.discard(n)
        if tc!=ac or '<module>' in tc: continue
        T.append({'family':'callers','prompt':f"In this repository, which production (non-test) functions call `{n}` (defined in {p})? List the names of the calling functions.",'truth':sorted(tc),'kind':'set'})
    # F2 coverage gap
    cand=[]
    for p in r.prod:
        pub=[m.group(2) for l in r.lines[p] for m in [DEF.match(l)] if m and len(m.group(1))<=4 and not m.group(2).startswith('_') and r.unique(m.group(2))]
        if len(pub)>=6: cand.append((len(pub),p,pub))
    random.shuffle(cand)
    for _,p,pub in cand[:quota['coverage']*4]:
        unc=[n for n in pub if not re.search(r'\b'+n+r'\b',r.testtext)]
        if 1<=len(unc)<=10 and sum(1 for t in T if t['family']=='coverage')<quota['coverage']:
            T.append({'family':'coverage','prompt':f"Which public functions/methods (names not starting with underscore) of {p} are never referenced anywhere under the test files? Consider only functions/methods whose name is defined exactly once in this repository. List the names.",'truth':sorted(unc),'kind':'set','universe':pub})
    # F3 def + params
    for n in names:
        if sum(1 for t in T if t['family']=='defparams')>=quota['defparams']: break
        p,_=r.defs[n][0]; s,t=hops.parse(os.path.join(r.root,p))
        if t is None: continue
        for x in ast.walk(t):
            if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and x.name==n:
                params=[a.arg for a in x.args.args+x.args.kwonlyargs if a.arg not in('self','cls')]
                if len(params)>=2: T.append({'family':'defparams','prompt':f"Where is `{n}` defined (file path) and what are its parameter names (excluding self/cls)?",'truth':params,'file':p,'kind':'params'}); break
    # F4 importers
    for n in names:
        if sum(1 for t in T if t['family']=='importers')>=quota['importers']: break
        p,_=r.defs[n][0]; imp=set()
        for q in r.prod:
            if q==p: continue
            src='\n'.join(r.lines[q])
            if re.search(r'from\s+[\w.]+\s+import\s+(?:\([^)]*\b'+n+r'\b[^)]*\)|[^\n(]*\b'+n+r'\b)',src): imp.add(os.path.basename(q))
        if 1<=len(imp)<=6: T.append({'family':'importers','prompt':f"Which production modules (files) import `{n}` from the module that defines it ({p})? List the file names.",'truth':sorted(imp),'kind':'set'})
    # F5 docstring audit
    cand=[]
    for p in r.prod:
        s,t=hops.parse(os.path.join(r.root,p))
        if t is None: continue
        if any((isinstance(d,ast.Name) and d.id=='overload') or (isinstance(d,ast.Attribute) and d.attr=='overload') for n in ast.walk(t) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) for d in n.decorator_list) or any(isinstance(n,(ast.If,ast.Try)) and any(isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)) for m in n.body) for n in t.body): continue   # stubs / conditional defs make 'has a docstring' ambiguous
        pubs=[n for n in t.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and not n.name.startswith('_')]
        nod=[n.name for n in pubs if not ast.get_docstring(n)]
        if len(pubs)>=5 and 1<=len(nod)<=8: cand.append((p,nod,[n.name for n in pubs]))
    random.shuffle(cand)
    for p,nod,pubs in cand[:quota['docaudit']]: T.append({'family':'docaudit','prompt':f"List the public top-level functions in {p} that have no docstring.",'truth':sorted(nod),'kind':'set','universe':pubs})
    # F6 callees
    for n in names:
        if sum(1 for t in T if t['family']=='callees')>=quota['callees']: break
        p,_=r.defs[n][0]; cs=hops.callees(os.path.join(r.root,p),n,r.root) or []
        inrepo={c['name'] for c in cs if c['defs'] and c['name']!=n and r.unique(c['name'])}
        if 2<=len(inrepo)<=8: T.append({'family':'callees','prompt':f"Which functions defined in this repository does `{n}` (in {p}) call directly? List only repository-defined functions whose name is defined exactly once in this repository.",'truth':sorted(inrepo),'kind':'set'})
    # F7 test count
    for n in names:
        if sum(1 for t in T if t['family']=='testcount')>=quota['testcount']: break
        cnt=0
        for p in r.test:
            s=open(os.path.join(r.root,p)).read()
            try: t=ast.parse(s)
            except Exception: continue
            for x in ast.walk(t):
                if isinstance(x,ast.FunctionDef) and x.name.startswith('test'):
                    seg=ast.get_source_segment(s,x) or ''
                    if re.search(r'\b'+n+r'\b',seg): cnt+=1
        if 2<=cnt<=15: T.append({'family':'testcount','prompt':f"How many test functions (functions whose name starts with `test`) in the test suite reference the identifier `{n}` (as a whole word) in their body? Give the number.",'truth':cnt,'kind':'int'})
    for i,t in enumerate(T): t['id']=f"{r.name}-{t['family']}-{i}"; t['repo']=r.name
    return T
def check(t,ans,repo=None):
    """-> (correct: bool, detail)"""
    if t['kind']=='int': return (re.search(r'(?<![\d.])'+str(t['truth'])+r'(?![\d.])',ans) is not None,'int')
    if t['kind']=='params':
        ok=all(re.search(r'\b'+re.escape(p)+r'\b',ans) for p in t['truth']) and os.path.basename(t['file']) in ans; return ok,'params'
    words=set(re.findall(r'[A-Za-z_]\w*',ans)); truth=set(t['truth'])
    rec=sum(1 for x in truth if (x in words or (('.' in x) and x in ans)))/len(truth)
    universe=set(t.get('universe',[]))|(set(repo.defs) if repo else set())
    claimed=(words&universe)-{x for x in words if x in('def','self')}; prec=len(truth&claimed)/len(claimed) if claimed else (1.0 if rec==1 else 0.0)
    return (rec==1.0 and prec>=0.7),f'recall={rec:.2f} precision={prec:.2f}'
REPOS={'helixengine':'helixengine','helixcontext':'helixcontext','click':'click','requests':'requests'}   # dirs under the work dir created by bench/setup_repos.sh
if __name__=='__main__':
    SP=sys.argv[1]; alltasks=[]
    for name,rel in REPOS.items():
        r=Repo(name,os.path.join(SP,rel)); T=make(r); alltasks+=T; print(name,len(r.prod),'prod',len(r.test),'test ->',len(T),'tasks',{f:sum(1 for t in T if t['family']==f) for f in {t['family'] for t in T}})
    json.dump(alltasks,open(os.path.join(H,'bench',f"ts_tasks{os.environ.get('TS_SET','')}.json"),'w'),indent=1); print('total',len(alltasks))
