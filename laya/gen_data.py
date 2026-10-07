"""Synthetic routing dataset for Laya. Splits: train / test_newphrase (unseen templates) / test_newentity (unseen files+fns)."""
import ast,glob,os,random,hashlib,csv,sys
random.seed(7)
SRC=sys.argv[1]  # dir containing helixengine/ package
files=[os.path.relpath(p,SRC) for p in glob.glob(SRC+'/helixengine/**/*.py',recursive=True) if '__pycache__' not in p]
fns=set()
for p in glob.glob(SRC+'/helixengine/**/*.py',recursive=True):
    for n in ast.walk(ast.parse(open(p).read())):
        if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and not n.name.startswith('__'): fns.add(n.name)
files+=['src/api/users.ts','lib/auth.go','utils.js','app/models.py','main.rs','server/routes.py','cli.py','tools/build.sh','pkg/store.go','web/app.js','handlers.rb','core/engine.cpp','test_cache.py','config/loader.py','Makefile','lib/parse.ts']
fns|={'parse_config','load_user','send_email','render_page','hash_password','fetch_rows','merge_dicts','retry','validate_token','build_index','flush_cache','handle_request','compute_score','normalize_path','open_db'}
files=sorted(set(files)); fns=sorted(fns)
def split(x): return 'test' if int(hashlib.md5(x.encode()).hexdigest(),16)%4==0 else 'train'
base=lambda f:os.path.basename(f)
CONDS=['two edits overlap','the input is empty','the file is missing','the timeout is zero','the cache is stale','the digest does not match','a lock is already held','the list is empty','the token has expired','the response is not valid JSON']
PARAMS=['chunk_bytes','limit','timeout','max_bytes','retries','fanout','port','ttl']
THINGS=['caching layer','retry decorator','logging wrapper','CLI flag','rate limiter','config parser','unit test','health endpoint','migration script','dark mode toggle']
CONCEPTS=['a sha256 digest','a mutex','idempotency','a bloom filter','dependency injection','a race condition','eventual consistency','a monad']
T={
'callers':(['who calls {fn}?','where is {fn} used','find every caller of {fn}','list all functions that call {fn}','which functions reference {fn} in {dir}','where is {fn} defined and who uses it','show usages of {fn}','what calls {fn} in this repo','find all references to {fn}','list the callers of {fn} as file:function','which code depends on {fn}','trace where {fn} gets called'],
 ['who uses {fn}?','locate the definition of {fn} and its call sites','call sites of {fn}, please','what invokes {fn}']),
'summ':(['summarize {file}','what does {file} do?','give me an overview of {file}','describe {file} briefly','tl;dr of {file}','explain {file} in one sentence','what is the purpose of {file}','sum up {file}','give a short description of {file}','what is {file} for','quick summary of {file}','briefly, what does {file} contain'],
 ['can you summarise {file} for me','overview please: {file}','{file} - what is it about?','in a sentence, what is {file}']),
'ask':(['in {file}, what happens when {cond}?','what error does {fn} raise in {file}?','what is the default {param} of {fn}?','how does {fn} in {file} handle the case where {cond}?','what does {fn} return in {file}?','in {file}, what is the default {param}?','what exception is raised in {file} if {cond}?','in {file} what does {fn} do when {cond}','which {param} does {fn} take in {file}','what is the value of {param} in {file}?'],
 ['according to {file}, what occurs if {cond}?','what does {fn} in {file} give back?','tell me the default {param} used by {fn} ({file})','when {cond}, what does the code in {file} do?']),
'outline':(['list the functions in {file}','show the structure of {file}','what classes does {file} define','outline {file}','table of contents for {file}','list all function names in {file}','what functions are in {file}','show me the symbols in {file}','enumerate the classes and functions of {file}','give me the skeleton of {file}'],
 ['which functions does {file} have','map out {file}: names only','function index for {file}','symbols defined in {file}?']),
'sym':(['show the source of {fn} in {file}','print the code for {fn}','let me see {fn} in {file}','display the {fn} function','show me {fn}','print {fn} from {file}','what does the code of {fn} look like','give me the implementation of {fn}','view the body of {fn} in {file}','dump the source of {fn}'],
 ['i want to read {fn} ({file})','open up {fn} for me','source for {fn}, please','show {fn}']),
'docgen':(['add docstrings to {file}','document all functions in {file}','write the missing docstrings in {file}','docstring every function in {file}','fill in the docstrings for {file}','add a docstring to every function in {file} that lacks one','generate docstrings for {file}','make sure every function in {file} has a docstring','add missing docstrings in {file}','document {file}'],
 ['please docstring {file}','put docstrings on all the undocumented functions in {file}','{file} needs docstrings, add them','missing docstrings in {file} -- fix that']),
'escalate':(['fix the bug in {file} where {fn}() hangs','refactor {file} to use dataclasses','rename {fn} to {fn}_v2 everywhere','write a new {thing}','run the tests and tell me what fails','why is it slow?','yes, go ahead','ok do it','looks good, continue','what is {concept}?','explain how the whole system works','implement a {thing} in {file}','delete {file}','update the README to mention the new flag','commit these changes','add a {thing} and write tests','summarize {file} and then fix its bug','who calls {fn}? then rename it','what does it do?','who calls it?','summarize all the files','tell me about the project','make it faster','why does {fn} fail?','debug the crash in {file}','optimize {fn}','review my changes','undo that','thanks!','can you help me with something?','deploy to production','install the dependencies','what should we do next?','what does {file} do and also rename {fn}?','create a {thing}','move {fn} into {file}','fix the failing test','explain the architecture decisions','plan the migration','is this a good design?'],
 ['hmm, fix {fn}','continue','sounds right, apply it','what is {concept} and when should I use it?','rewrite {file} in a cleaner style','add error handling to {fn}','run {file}','the build is broken, help','compare {fn} with the alternative approach','why is {file} so long?'])}
VERB_TR=['fix','refactor','rename','delete','optimize','rewrite','remove','move','implement','test','debug','clean up','merge','split','port to rust','profile','harden','deprecate']
VERB_TE=['repair','simplify','replace','extend','speed up','restructure','patch','revert']
PRE=['please ','','can you ','i need you to ','go ahead and ','now ']
def extra_escalate(ts,f,fn,rng):
    V=VERB_TR if ts=='train' else VERB_TE; v=rng.choice(V); tgt=rng.choice([f,fn,fn+'() in '+f,'the '+fn+' function','everything in '+f])
    kind=rng.random()
    if kind<0.55: return rng.choice(PRE)+v+' '+tgt
    base=rng.choice(['summarize '+f,'who calls '+fn,'show the source of '+fn,'what does '+f+' do','list the functions in '+f,'document '+f])
    return base+rng.choice([' and then ',' and also ',', then ',' and after that '])+v+' it'
def fill(t,f,fn,rng):
    return t.format(file=f,fn=fn,dir=os.path.dirname(f) or '.',cond=rng.choice(CONDS),param=rng.choice(PARAMS),thing=rng.choice(THINGS),concept=rng.choice(CONCEPTS))
def build(which_tmpl,which_ent,n_per,seed):
    rng=random.Random(seed); rows=[]
    ents_f=[f for f in files if split(f)==which_ent]; ents_n=[n for n in fns if split(n)==which_ent]
    for lab,(tr,te) in T.items():
        ts=tr if which_tmpl=='train' else te
        for i in range(n_per):
            t=rng.choice(ts); rows.append((fill(t,rng.choice(ents_f),rng.choice(ents_n),rng),lab))
        if lab=='escalate':
            for i in range(int(n_per*1.6)): rows.append((extra_escalate(which_tmpl,rng.choice(ents_f),rng.choice(ents_n),rng),'escalate'))
    return rows
OUT=sys.argv[2] if len(sys.argv)>2 else '.'
for name,(tm,en,n,seed) in {'train':('train','train',260,1),'test_newphrase':('test','train',50,2),'test_newentity':('train','test',50,3),'test_both':('test','test',40,4)}.items():
    rows=list(dict.fromkeys(build(tm,en,n,seed)))
    if name=='train':
        held=set(r[0] for r in build('test','train',50,2)+build('train','test',50,3)+build('test','test',40,4)); rows=[r for r in rows if r[0] not in held]
    random.Random(0).shuffle(rows)
    with open(f'{OUT}/{name}.csv','w',newline='') as f: w=csv.writer(f); w.writerow(['text','label']); w.writerows(rows)
    print(name,len(rows),{l:sum(1 for r in rows if r[1]==l) for l in T})
