"""zs1: zero-shot generalization corpus for Laya. Train on 10 code-property instructions + code relevance + routing slice;
evaluate on 8 HELD-OUT instructions over HELD-OUT packages (and relevance over held-out packages)."""
import ast,glob,os,random,json,re,sys,importlib.util
random.seed(11)
TRAIN_PKGS=['transformers','torch','sympy','pandas','scipy','sklearn','networkx','numpy','pygments','setuptools','chromadb','sentence_transformers','huggingface_hub','mlx_lm','pydantic','rich','fsspec','aiohttp','fastapi','anyio','anthropic']
EVAL_PKGS=['pip','urllib3','requests','httpx','httpcore','starlette','uvicorn','jinja2','click','yaml','tqdm','markdown_it','packaging','filelock','tiktoken','tokenizers','h11']
def pkgdir(n):
    s=importlib.util.find_spec(n); return list(s.submodule_search_locations)[0] if s and s.submodule_search_locations else None
def functions(pkg,limit):
    d=pkgdir(pkg); out=[]
    if not d: return out
    files=[f for f in glob.glob(d+'/**/*.py',recursive=True) if '/tests/' not in f and '/test_' not in f and 'vendor' not in f.split(pkg)[0]]
    random.shuffle(files)
    for f in files:
        try: src=open(f).read(); t=ast.parse(src)
        except Exception: continue
        for n in ast.walk(t):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                L=n.end_lineno-n.lineno+1
                if 4<=L<=40 and not n.name.startswith('__'):
                    seg=ast.get_source_segment(src,n)
                    if seg and len(seg)<=1500: out.append({'pkg':pkg,'file':os.path.relpath(f,d),'node':n,'src':seg,'doc':ast.get_docstring(n)})
        if len(out)>=limit*3: break
    random.shuffle(out); return out[:limit]
def calls(n):
    for c in ast.walk(n):
        if isinstance(c,ast.Call):
            f=c.func
            if isinstance(f,ast.Name): yield (None,f.id)
            elif isinstance(f,ast.Attribute): yield ((f.value.id if isinstance(f.value,ast.Name) else None),f.attr)
FILE_OPS={'open','read_text','write_text','read_bytes','write_bytes','unlink','mkdir','rename','remove','makedirs','rmtree','copyfile','listdir','fsync','copy2','replace','touch','rmdir'}
LOCKS={'Lock','RLock','Semaphore','Event','Condition','Thread','ThreadPoolExecutor','Barrier','BoundedSemaphore','acquire','release'}
NET={'socket','urllib','requests','http','httpx','aiohttp','urlopen','urlretrieve','ssl'}
RE_FN={'compile','match','search','sub','findall','finditer','split','fullmatch','subn'}
def feat(n):
    cs=list(calls(n)); names={c[1] for c in cs}; bases={c[0] for c in cs if c[0]}
    nodes=list(ast.walk(n)); params=[a.arg for a in n.args.args if a.arg not in('self','cls')]+[a.arg for a in n.args.kwonlyargs]
    ret_val=any(isinstance(x,ast.Return) and x.value is not None and not (isinstance(x.value,ast.Constant) and x.value.value is None) for x in nodes)
    isgen=any(isinstance(x,(ast.Yield,ast.YieldFrom)) for x in nodes)
    return {
     'raise':any(isinstance(x,ast.Raise) for x in nodes),'loop':any(isinstance(x,(ast.For,ast.While,ast.AsyncFor)) for x in nodes),
     'recursion':n.name in names,'async':isinstance(n,ast.AsyncFunctionDef),'defaults':bool(n.args.defaults) or any(d is not None for d in n.args.kw_defaults),
     'try':any(isinstance(x,ast.Try) for x in nodes),'decorated':bool(n.decorator_list),'many_params':len(params)>=4,'long':(n.end_lineno-n.lineno+1)>20,'noreturn':(not ret_val) and not isgen,
     'io':bool(names&FILE_OPS),'regex':('re' in bases and bool(names&RE_FN)),'generator':isgen,
     'lock':bool(names&LOCKS) or 'threading' in bases or any(isinstance(x,ast.With) and any('lock' in ast.dump(i.context_expr).lower() for i in x.items) for x in nodes),
     'subprocess':('subprocess' in bases) or 'Popen' in names or ('os' in bases and bool(names&{'system','popen','execv','spawnl'})),
     'network':bool(bases&NET) or bool(names&{'urlopen','urlretrieve','getaddrinfo','create_connection','gethostbyname'}),
     'comprehension':any(isinstance(x,(ast.ListComp,ast.DictComp,ast.SetComp,ast.GeneratorExp)) for x in nodes),'global':any(isinstance(x,(ast.Global,ast.Nonlocal)) for x in nodes)}
TQ={ # TRAIN instructions (3 phrasings each)
 'raise':["Does this function raise an exception?","Can this code raise an error on some path?","Is there a raise statement in this function?"],
 'loop':["Does this code contain a loop?","Is there a for or while loop in this function?","Does the function iterate with a loop construct?"],
 'recursion':["Is this function recursive?","Does the function call itself?","Does this code recurse?"],
 'async':["Is this an async function?","Is this function declared with async def?","Does this define a coroutine?"],
 'defaults':["Does the function have default parameter values?","Are any parameters optional with defaults?","Does the signature include default arguments?"],
 'try':["Does this code use try/except?","Is there exception handling in this function?","Does the function catch exceptions?"],
 'decorated':["Is this function decorated?","Does the function have decorators applied?","Is there an @decorator above this function?"],
 'many_params':["Does this function take four or more parameters?","Is the parameter list long (4+ parameters)?","Does it have at least four arguments besides self?"],
 'long':["Is this function longer than 20 lines?","Does the function body exceed twenty lines?","Is this a long function (over 20 lines)?"],
 'noreturn':["Does this function never return a value?","Does the function only return None or nothing?","Is this function called purely for side effects?"]}
HQ={ # HELD-OUT instructions (never seen in training)
 'io':["Does this function perform file or disk I/O?","Does this code read from or write to the filesystem?","Does the function touch files or directories?"],
 'regex':["Does this function use regular expressions?","Is a regex pattern matched or substituted here?","Does the code rely on the re module for pattern matching?"],
 'generator':["Is this function a generator?","Does this function use yield?","Does the function produce values lazily with yield?"],
 'lock':["Does this code deal with locks, threads or concurrency?","Is any synchronization primitive or thread used here?","Is this function concerned with thread safety or concurrent execution?"],
 'subprocess':["Does this function launch an external process?","Does the code run a shell command or subprocess?","Is another program executed from this function?"],
 'network':["Does this function perform network access?","Does the code open sockets or make HTTP requests?","Is there any network communication in this function?"],
 'comprehension':["Does this function use a list, dict or set comprehension?","Is a comprehension or generator expression used?","Does the code build collections with comprehensions?"],
 'global':["Does this function use global or nonlocal variables?","Is a global or nonlocal statement present?","Does the function rebind names outside its own scope?"]}
def qrow(state,qid,text,label): return {'state':state,'questions':{qid:{'type':'noul','instructions':text}},'expected':{qid:label}}
def build():
    tr=[];ev=[]
    for p in TRAIN_PKGS:
        for f in functions(p,170): f['feat']=feat(f['node']); tr.append(f)
    for p in EVAL_PKGS:
        for f in functions(p,10**6): f['feat']=feat(f['node']); ev.append(f)
    print('train fns',len(tr),'eval fns',len(ev))
    train=[]
    for q,phr in TQ.items():
        pos=[f for f in tr if f['feat'][q]]; neg=[f for f in tr if not f['feat'][q]]; k=min(230,len(pos),len(neg))
        for f,lab in [(x,True) for x in random.sample(pos,k)]+[(x,False) for x in random.sample(neg,k)]:
            qs={q:{'type':'noul','instructions':random.choice(phr)}}; ex={q:lab}
            for q2 in random.sample([x for x in TQ if x!=q],2): qs[q2]={'type':'noul','instructions':random.choice(TQ[q2])}; ex[q2]=f['feat'][q2]
            train.append({'state':f['pkg']+'/'+f['file']+'\n'+f['src'],'questions':qs,'expected':ex})
    held=[]; stats={}
    for q,phr in HQ.items():
        pos=[f for f in ev if f['feat'][q]]; neg=[f for f in ev if not f['feat'][q]]; k=min(80,len(pos),len(neg)); stats[q]=(len(pos),len(neg))
        for f,lab in [(x,True) for x in random.sample(pos,k)]+[(x,False) for x in random.sample(neg,k)]: held.append({**qrow(f['pkg']+'/'+f['file']+'\n'+f['src'],q,random.choice(phr),lab),'meta':{'q':q,'pkg':f['pkg']}})
    print('held-out per question (pos,neg available):',stats)
    # relevance: docstring first sentence -> docstring-stripped code
    def strip_doc(src):
        try:
            t=ast.parse(src); n=t.body[0]
            if ast.get_docstring(n) is not None and isinstance(n.body[0],ast.Expr):
                lines=src.split('\n'); a=n.body[0].lineno-1; b=n.body[0].end_lineno; return '\n'.join(lines[:a]+lines[b:])
        except Exception: pass
        return src
    RT=["This code implements: {q}","The following code does what is described here: {q}","Is this the code for: {q}"]
    def rel(pool,n):
        docs=[f for f in pool if f['doc'] and len(f['doc'].split('\n')[0])>25]; random.shuffle(docs); rows=[]
        for f in docs[:n]:
            q=re.sub(r'\s+',' ',f['doc'].split('\n')[0]).strip()[:140]; code=strip_doc(f['src'])
            same=[g for g in pool if g is not f and g['file']==f['file']]; other=random.choice(same) if same else random.choice(pool)
            rows.append(qrow(f['pkg']+'/'+f['file']+'\n'+code,'rel',random.choice(RT).format(q=q),True))
            rows.append(qrow(other['pkg']+'/'+other['file']+'\n'+strip_doc(other['src']),'rel',random.choice(RT).format(q=q),False))
        return rows
    train+=rel(tr,800); relev=rel(ev,150)
    return train,held,relev
if __name__=='__main__':
    train,held,relev=build()
    rt=[json.loads(l) for l in open('v2_train.jsonl')]; random.shuffle(rt); train+=rt[:1200]
    random.shuffle(train)
    for name,rows in (('zs1_train',train),('zs1_eval_heldq',held),('zs1_eval_rel',relev)):
        with open(name+'.jsonl','w') as f:
            for r in rows: f.write(json.dumps(r)+'\n')
        print(name,len(rows))
