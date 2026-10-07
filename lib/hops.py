"""Helix local semantic operations: deterministic, typed receipts. No model here."""
import os,ast,re
SKIP={'.git','node_modules','__pycache__','.venv','venv','dist','build'}
def pyfiles(root='.'):
    for r,ds,fs in os.walk(root):
        ds[:]=[d for d in ds if d not in SKIP]
        for f in sorted(fs):
            if f.endswith('.py'): yield os.path.relpath(os.path.join(r,f))
def is_test(p):
    parts=p.split(os.sep); b=os.path.basename(p)
    return 'tests' in parts or 'test' in parts or b.startswith('test_') or b.endswith('_test.py') or b=='conftest.py'
_PC={}
def parse(p):
    """mtime-keyed parse cache: a controller run touches each file once"""
    try:
        m=os.stat(p).st_mtime_ns; c=_PC.get(p)
        if c and c[0]==m: return c[1],c[2]
        s=open(p).read(); t=ast.parse(s); _PC[p]=(m,s,t); return s,t
    except Exception: return None,None
def _enclosing(tree):
    """map node id -> nearest enclosing function name"""
    m={}
    def walk(n,enc):
        for c in ast.iter_child_nodes(n):
            e=enc
            if isinstance(c,(ast.FunctionDef,ast.AsyncFunctionDef)): e=c.name
            m[id(c)]=enc if not isinstance(c,(ast.FunctionDef,ast.AsyncFunctionDef)) else c.name
            walk(c,e)
    walk(tree,None); return m
def _walk_scoped(tree):
    """yield (node, nearest enclosing FunctionDef or None)"""
    def go(n,f):
        for c in ast.iter_child_nodes(n):
            nf=c if isinstance(c,(ast.FunctionDef,ast.AsyncFunctionDef)) else f
            yield c,nf if not isinstance(c,(ast.FunctionDef,ast.AsyncFunctionDef)) else f
            yield from go(c,nf)
    yield from go(tree,None)
_LN={}
def _local_names(fn):
    k=id(fn)
    if k in _LN: return _LN[k]
    names={a.arg for a in fn.args.args+fn.args.kwonlyargs+fn.args.posonlyargs}
    if fn.args.vararg: names.add(fn.args.vararg.arg)
    if fn.args.kwarg: names.add(fn.args.kwarg.arg)
    def go(n):
        for c in ast.iter_child_nodes(n):
            if isinstance(c,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Lambda)): continue
            if isinstance(c,ast.Name) and isinstance(c.ctx,(ast.Store,ast.Del)): names.add(c.id)
            go(c)
    go(fn); _LN[k]=names; return names
def callers(name,root='.',deffile=None):
    """receipt: {'defs':[{file,line}], 'hits':[{file,line,fn,kind,test,wrapper,snippet,src}]}"""
    defs=[];hits=[]
    for p in pyfiles(root):
        s,t=parse(p)
        if t is None or name not in s: continue
        L=s.split('\n'); bound=False; mods=set(); src='local'; dl=[]; alias={}
        for n in ast.walk(t):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name==name: dl.append(n.lineno)
            if isinstance(n,ast.ImportFrom):
                for a in n.names:
                    if (a.asname or a.name)==name: bound=True; src='.'*n.level+(n.module or '')
                    else: mods.add(a.asname or a.name); alias[a.asname or a.name]=a.name
            if isinstance(n,ast.Import):
                for a in n.names: mods.add((a.asname or a.name).split('.')[0]); alias[(a.asname or a.name).split('.')[0]]=a.name.split('.')[-1]
        if dl: bound=True
        if deffile:
            stem=os.path.splitext(os.path.basename(deffile))[0]
            modmatch=any(v==stem for v in alias.values())
            if not ((dl and p.endswith(deffile)) or (not dl and src!='local' and src.rstrip('.').split('.')[-1]==stem) or (not dl and modmatch)): continue
        for ln in dl: defs.append({'file':p,'line':ln})
        for n,fnode in _walk_scoped(t):
            ok=(isinstance(n,ast.Name) and n.id==name and bound and not isinstance(n.ctx,ast.Store)) or \
               (isinstance(n,ast.Attribute) and n.attr==name and isinstance(n.value,ast.Name) and (n.value.id in mods or (dl and n.value.id in ('self','cls'))))
            if not ok: continue
            if isinstance(n,ast.Attribute) and deffile and n.value.id in mods:   # module attribute must resolve to the defining module
                if alias.get(n.value.id,n.value.id)!=os.path.splitext(os.path.basename(deffile))[0]: continue
            if isinstance(n,ast.Name) and fnode is not None and name in _local_names(fnode): continue   # shadowed by a local/param
            if any(n.lineno==d for d in dl): continue
            hits.append({'file':p,'line':n.lineno,'fn':fnode.name if fnode is not None else '<module>','test':is_test(p),'snippet':L[n.lineno-1].strip()[:110],'src':src})
        for n in ast.walk(t):   # import lines
            if isinstance(n,ast.ImportFrom) and any((a.asname or a.name)==name for a in n.names):
                hits.append({'file':p,'line':n.lineno,'fn':'<import>','test':is_test(p),'snippet':L[n.lineno-1].strip()[:110],'src':src})
    # wrapper flag: enclosing fn whose body is a single call to name
    cache={}
    for h in hits:
        if h['fn'] in('<module>','<import>'): h['wrapper']=False; continue
        key=h['file']
        if key not in cache: cache[key]=parse(key)
        s,t=cache[key]; w=False
        for n in ast.walk(t):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==h['fn']:
                body=[b for b in n.body if not(isinstance(b,ast.Expr) and isinstance(getattr(b,'value',None),ast.Constant))]
                if len(body)==1 and isinstance(body[0],(ast.Return,ast.Expr)) and isinstance(getattr(body[0],'value',None),ast.Call):
                    f=body[0].value.func; w=(isinstance(f,ast.Name) and f.id==name) or (isinstance(f,ast.Attribute) and f.attr==name)
        h['wrapper']=w
    return {'defs':defs,'hits':hits}
def symbol(file,name,cap=30):
    s,t=parse(file)
    if t is None: return None
    L=s.split('\n')
    for n in ast.walk(t):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name==name:
            a=n.decorator_list[0].lineno if n.decorator_list else n.lineno; b=n.end_lineno
            body=[f'{i}:{L[i-1]}' for i in range(a,min(b,a+cap-1)+1)]
            if b>a+cap-1: body.append(f'..({b-(a+cap-1)} more lines; sym {file} {name})')
            return {'file':file,'name':name,'lines':(a,b),'src':'\n'.join(body)}
    return None
def enclosing_symbol(file,fn):
    return symbol(file,fn)

def callees(file,name,root='.'):
    """names called inside function `name` of `file`; each marked with repo definition files (name-resolved, best effort)"""
    s,t=parse(file)
    if t is None: return None
    node=None
    for n in ast.walk(t):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name: node=n; break
    if node is None: return None
    called={}
    for n in ast.walk(node):
        if isinstance(n,ast.Call):
            f=n.func; nm=f.id if isinstance(f,ast.Name) else (f.attr if isinstance(f,ast.Attribute) else None)
            if nm: called.setdefault(nm,n.lineno)
    defs={}; kinds={}
    for p in pyfiles(root):
        ss,tt=parse(p)
        if tt is None: continue
        for n in ast.walk(tt):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name in called:
                defs.setdefault(n.name,[]).append(f'{p}:{n.lineno}'); kinds.setdefault(n.name,set()).add('class' if isinstance(n,ast.ClassDef) else 'function')
    return [{'name':k,'line':v,'defs':defs.get(k,[]),'kind':('/'.join(sorted(kinds[k])) if k in kinds else None),'ndefs':len(defs.get(k,[]))} for k,v in called.items()]

def def_counts(root='.'):
    """repo-wide count of function/class definitions per name (for flagging shared names)"""
    cnt={}
    for p in pyfiles(root):
        ss,tt=parse(p)
        if tt is None: continue
        for n in ast.walk(tt):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)): cnt[n.name]=cnt.get(n.name,0)+1
    return cnt

def _toplevel(stmts):
    """top-level definitions including those under if/try/with at module level (conditional imports/fallbacks are still module-level API)"""
    for n in stmts:
        if isinstance(n,(ast.If,ast.Try,ast.With)):
            for blk in (n.body,getattr(n,'orelse',[]),*[h.body for h in getattr(n,'handlers',[])],getattr(n,'finalbody',[])): yield from _toplevel(blk)
        else: yield n
def public_functions(file):
    s,t=parse(file)
    if t is None: return None
    out=[]
    for n in _toplevel(t.body):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and not n.name.startswith('_'): out.append({'name':n.name,'line':n.lineno,'owner':None})
        if isinstance(n,ast.ClassDef) and not n.name.startswith('_'):
            for m in n.body:
                if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)) and not m.name.startswith('_'): out.append({'name':m.name,'line':m.lineno,'owner':n.name})
    return out

def _code_text(src):
    """source with comment lines and triple-quoted docstring blocks removed (string literals in code stay: mock.patch('pkg.f') is a real reference)"""
    out=[];inq=None
    for l in src.split('\n'):
        s_=l.strip()
        if inq:
            if inq in l: inq=None
            continue
        if s_.startswith(('"""',"'''")):
            q=s_[:3]
            if s_.count(q)<2: inq=q
            continue
        if s_.startswith('#'): continue
        out.append(l)
    return '\n'.join(out)

def test_refs(name,root='.'):
    """test functions referencing `name` (call, attribute or import). Over-approximate: any Name/Attribute with that name in a test file."""
    out={}
    for p in pyfiles(root):
        if not is_test(p): continue
        s,t=parse(p)
        if t is None or name not in s: continue
        for n,f in _walk_scoped(t):
            if (isinstance(n,ast.Name) and n.id==name) or (isinstance(n,ast.Attribute) and n.attr==name):
                out.setdefault((p,f.name if f is not None else '<module>'),[]).append(n.lineno)
            elif isinstance(n,ast.ImportFrom) and any(a.name==name for a in n.names):   # import-only reference still counts as a reference
                out.setdefault((p,'<import>'),[]).append(n.lineno)
        if not any(k[0]==p for k in out):     # no AST reference in this file: a string reference (mock.patch path, parametrize id, getattr name) still counts
            import re as _re
            hit=[i for i,l in enumerate(_code_text(s).split('\n'),1) if _re.search(r'\b'+_re.escape(name)+r'\b',l)]
            if hit: out[(p,'<string-ref>')]=hit
    return [{'file':k[0],'fn':k[1],'lines':v} for k,v in out.items()]
