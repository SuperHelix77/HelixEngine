"""Immutable named plans with checked snapshots and transactional receipts."""
import json,os,re,sqlite3,time,uuid
from contextlib import contextmanager
from pathlib import Path
from . import checked_steps,evidence,plan_dependencies as dep


def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


@contextmanager
def database(store):
    db=sqlite3.connect(store.root/'plans.sqlite3',isolation_level=None)
    db.execute('PRAGMA synchronous=FULL')
    db.executescript('''CREATE TABLE IF NOT EXISTS plans(id TEXT,version INTEGER,hash TEXT,creation TEXT,PRIMARY KEY(id,version));
    CREATE TABLE IF NOT EXISTS attempts(event_id INTEGER PRIMARY KEY AUTOINCREMENT,attempt_id TEXT UNIQUE,plan_hash TEXT,status TEXT,receipt TEXT);
    CREATE TABLE IF NOT EXISTS successes(plan_hash TEXT PRIMARY KEY,receipt TEXT);''')
    try:yield db
    finally:db.close()


def validate_steps(steps,executables):
    if not isinstance(steps,list) or not steps:raise ValueError('Nonempty steps required')
    names=set()
    for step in steps:
        if not isinstance(step,dict) or set(step)!={'name','argv'}:raise ValueError('Invalid step')
        name,argv=step['name'],step['argv']
        if not isinstance(name,str) or not name or name in names:raise ValueError('Invalid step name')
        names.add(name)
        if not isinstance(argv,list) or not argv or any(not isinstance(x,str) or '\x00' in x for x in argv) or argv[0] not in executables:
            raise ValueError('Unbound executable or invalid argv')


def register(store,plan_id,plan_version,*,cwd,steps,files,executables,env_names=(),environment=None,_rebind=None):
    started=time.perf_counter();cost=dep.metric();before_io=dict(store.metrics)
    if not isinstance(plan_id,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}',plan_id) or type(plan_version) is not int or plan_version<1:
        raise ValueError('Invalid plan identity')
    if not isinstance(files,dict) or not isinstance(executables,dict):raise ValueError('Dependency maps required')
    validate_steps(steps,executables)
    if not isinstance(env_names,(list,tuple)) or len(set(env_names))!=len(env_names) or any(not isinstance(n,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',n) for n in env_names):raise ValueError('Invalid environment names')
    environment=dict(os.environ if environment is None else environment)
    root=Path(cwd).resolve(strict=True)
    manifest={'schema':'helix.named_plan.v1','plan_id':plan_id,'plan_version':plan_version,'cwd':dep.directory(root),'steps':steps,'files':{},'executables':{},'environment':dep.environment_binding(env_names,environment),'runner_modules':{}}
    for name,role in files.items():
        if role not in ('input','script','schema','config'):raise ValueError('Unknown dependency role')
        identity,data=dep.read_file(dep.local_path(root,name),cost)
        archived=store.put(data)
        if archived['sha256']!=identity['sha256']:raise ValueError('Source archive mismatch')
        manifest['files'][name]={'role':role,'identity':identity}
    for name,path in executables.items():
        requested=Path(path).absolute();resolved=requested.resolve(strict=True)
        identity,_=dep.read_file(resolved,cost)
        if not os.access(resolved,os.X_OK):raise ValueError('Executable is not executable')
        manifest['executables'][name]={'requested':str(requested),'resolved':str(resolved),'identity':identity}
    for path in [Path(__file__).resolve(),Path(dep.__file__).resolve(),Path(checked_steps.__file__).resolve(),Path(evidence.__file__).resolve()]:
        identity,_=dep.read_file(path,cost);manifest['runner_modules'][str(path)]=identity['sha256']
    if _rebind is not None:
        if fixed_contract(manifest)!=fixed_contract(_rebind['manifest']):
            raise ValueError('Fixed plan dependencies changed during input rebinding')
        manifest['parent_plan']=_rebind['reference']
        cost['rebind_preflight']=_rebind['cost']
    blob=encode(manifest);ref=store.put(blob)['sha256']
    cost.update(seconds_total=time.perf_counter()-started,manifest_bytes=len(blob),native_input_tokens=None,native_output_tokens=None)
    with database(store) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            prior=db.execute('SELECT hash FROM plans WHERE id=? AND version=?',(plan_id,plan_version)).fetchone()
            if prior and prior[0]!=ref:raise ValueError('Plan identity already bound; use a new version')
            dep.verify(manifest,environment,cost)
            cost['seconds_total']=time.perf_counter()-started
            cost['store_io']={k:store.metrics[k]-before_io[k] for k in before_io}
            if not prior:db.execute('INSERT INTO plans VALUES(?,?,?,?)',(plan_id,plan_version,ref,json.dumps(cost)))
            db.execute('COMMIT')
        except BaseException:db.execute('ROLLBACK');raise
    return {'plan_id':plan_id,'plan_version':plan_version,'plan_hash':ref}


def fixed_contract(manifest):
    result={key:value for key,value in manifest.items() if key not in ('plan_version','parent_plan','files')}
    result['files']={name:({'role':'input'} if binding['role']=='input' else binding) for name,binding in manifest['files'].items()}
    return result


def rebind_inputs(store,reference,new_version,*,environment=None):
    """Explicitly register new data under unchanged logic; never auto-execute."""
    started=time.perf_counter();before=dict(store.metrics);metrics=dep.metric()
    old=load(store,reference)
    if type(new_version) is not int or new_version<=old['plan_version']:
        raise ValueError('A strictly newer version is required')
    environment=dict(os.environ if environment is None else environment)
    fixed={**old,'files':{name:binding for name,binding in old['files'].items() if binding['role']!='input'}}
    dep.verify(fixed,environment,metrics)
    cost={'validation':metrics,'seconds':time.perf_counter()-started,
          'store_io':{k:store.metrics[k]-before[k] for k in before}}
    return register(store,old['plan_id'],new_version,cwd=old['cwd']['path'],steps=old['steps'],
        files={name:binding['role'] for name,binding in old['files'].items()},
        executables={name:binding['requested'] for name,binding in old['executables'].items()},
        env_names=list(old['environment']),environment=environment,
        _rebind={'manifest':old,'reference':reference,'cost':cost})


def load(store,ref):
    if not isinstance(ref,dict) or set(ref)!={'plan_id','plan_version','plan_hash'} or type(ref['plan_version']) is not int:raise ValueError('Invalid plan reference')
    with database(store) as db:row=db.execute('SELECT hash FROM plans WHERE id=? AND version=?',(ref['plan_id'],ref['plan_version'])).fetchone()
    if row is None or row[0]!=ref['plan_hash']:raise ValueError('Unknown plan identity')
    manifest=json.loads(store.get(ref['plan_hash']))
    if manifest.get('schema')!='helix.named_plan.v1' or manifest['plan_id']!=ref['plan_id'] or manifest['plan_version']!=ref['plan_version']:raise ValueError('Manifest identity mismatch')
    return manifest


def creation_cost(store,ref):
    load(store,ref)
    with database(store) as db:return json.loads(db.execute('SELECT creation FROM plans WHERE id=? AND version=?',(ref['plan_id'],ref['plan_version'])).fetchone()[0])


def latest_success(store,ref):
    load(store,ref)
    with database(store) as db:row=db.execute('SELECT receipt FROM successes WHERE plan_hash=?',(ref['plan_hash'],)).fetchone()
    return row[0] if row else None


def invoke(store,ref,*,environment=None,timeout=None):
    before_io=dict(store.metrics)
    started=time.perf_counter();manifest=load(store,ref)
    environment=dict(os.environ if environment is None else environment)
    child_env={n:environment[n] for n in manifest['environment'] if n in environment}
    attempt_id=uuid.uuid4().hex;workspace=store.root/'plan-runs'/attempt_id;workspace.mkdir(parents=True)
    costs={'validation':dep.metric(),'snapshot':{'bytes_written':0},'execution_seconds':0.0,'native_input_tokens':None,'native_output_tokens':None}
    steps=[];error=None;snapshots={}
    try:
        validate_steps(manifest['steps'],manifest['executables'])
        dep.verify(manifest,environment,costs['validation'])
        for name,binding in manifest['files'].items():
            identity,data=dep.read_file(dep.local_path(Path(manifest['cwd']['path']),name),costs['validation'])
            if identity!=binding['identity']:raise ValueError('Source invalidated during snapshot')
            target=dep.local_path(workspace,name);target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(data);target.chmod(binding['identity']['stamp'][-1])
            costs['snapshot']['bytes_written']+=len(data)
            snapshots[name],_=dep.read_file(target,costs['validation'])
            if snapshots[name]['sha256']!=binding['identity']['sha256']:raise ValueError('Snapshot digest mismatch')
        for step in manifest['steps']:
            dep.verify(manifest,environment,costs['validation'],workspace,snapshots)
            argv=[manifest['executables'][step['argv'][0]]['resolved'],*step['argv'][1:]]
            start=time.perf_counter()
            result=None
            try:result=checked_steps.execute(store,[{'name':step['name'],'argv':argv}],workspace,'named-plan:'+ref['plan_hash'],timeout=timeout,env=child_env)
            finally:costs['execution_seconds']+=time.perf_counter()-start
            if result is not None:
                steps.extend(result['steps'])
            else:
                raise ValueError('Mandatory step did not produce a receipt: '+step['name'])
            dep.verify(manifest,environment,costs['validation'],workspace,snapshots)
            if not result['process_success']:raise ValueError('Mandatory step failed: '+step['name'])
        dep.verify(manifest,environment,costs['validation'],workspace,snapshots)
    except Exception as exc:error=type(exc).__name__+': '+str(exc)
    costs['elapsed_before_publication_seconds']=time.perf_counter()-started
    costs['execution_store_io']={k:store.metrics[k]-before_io[k] for k in before_io}
    result={'schema':'helix.plan_attempt.v1','attempt_id':attempt_id,**ref,'status':'FAILED' if error else 'SUCCEEDED','semantic_success':None,'steps':steps,'error':error,'workspace':str(workspace),'costs':costs,'unexecuted':[s['name'] for s in manifest['steps'][len(steps):]],'scope':'Declared dependency snapshots and captured mandatory process statuses; no host sandbox or universal semantic guarantee'}
    publication_start=time.perf_counter();final_validation=None
    blob=encode(result);attempt_hash=store.put(blob)['sha256']
    with database(store) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            # Recheck after cold-object publication and lock acquisition. Cold
            # candidate objects do not confer acceptance; only this DB does.
            if not error:
                final_validation=dep.metric()
                try:dep.verify(manifest,environment,final_validation,workspace,snapshots)
                except Exception as exc:
                    error=type(exc).__name__+': '+str(exc)
                    result.update(status='FAILED',error=error)
                    costs['publication_validation']=final_validation
                    blob=encode(result);attempt_hash=store.put(blob)['sha256']
            db.execute('INSERT INTO attempts(attempt_id,plan_hash,status,receipt) VALUES(?,?,?,?)',(attempt_id,ref['plan_hash'],result['status'],attempt_hash))
            event_id=db.execute('SELECT last_insert_rowid()').fetchone()[0]
            if not error:db.execute('INSERT OR REPLACE INTO successes VALUES(?,?)',(ref['plan_hash'],attempt_hash))
            db.execute('COMMIT')
        except BaseException:db.execute('ROLLBACK');raise
    publication={'seconds':time.perf_counter()-publication_start,'receipt_bytes':len(blob),'validation':final_validation,'scope':'Measured in return value after commit; not self-included in hashed receipt. SQLite and physical I/O unmetered. Final check and commit are not atomic with noncooperating filesystem writers.'}
    return {**result,'attempt_hash':attempt_hash,'event_id':event_id,'publication':publication}


def release_inputs(store,ref,attempt_hash):
    """Caller explicitly releases input paths after all workspace consumers finish.

    Never called by invoke: outputs may reference these paths. Requires exclusive
    workspace ownership, not a hostile-writer sandbox. Original source objects,
    process evidence and task-created output files remain. Partial OS deletion
    failures are reported explicitly, without changing the accepted attempt.
    """
    start=time.perf_counter();before_io=dict(store.metrics);metrics=dep.metric()
    manifest=load(store,ref)
    with database(store) as db:
        row=db.execute('SELECT attempt_id FROM attempts WHERE receipt=? AND plan_hash=? AND status=?',
                       (attempt_hash,ref['plan_hash'],'SUCCEEDED')).fetchone()
    if row is None:raise ValueError('Successful accepted attempt required')
    attempt_id=row[0]
    if not re.fullmatch('[0-9a-f]{32}',attempt_id):raise ValueError('Invalid attempt identity')
    workspace=store.root/'plan-runs'/attempt_id
    if workspace.is_symlink() or workspace.parent.is_symlink():raise ValueError('Symlink workspace')
    targets=[]
    # Validate all sources before deleting any snapshot. Do not require mutable
    # originals to remain present: recovery binds the archived source bytes.
    for name,binding in manifest['files'].items():
        archive=store.get(binding['identity']['sha256'])
        target=dep.local_path(workspace,name)
        identity,data=dep.read_file(target,metrics)
        if data!=archive or identity['stamp'][-1]!=binding['identity']['stamp'][-1]:
            raise ValueError('Snapshot changed; retain workspace for review')
        targets.append((name,target,identity))
    removed=[];errors=[];bytes_removed=0
    for name,target,identity in targets:
        try:
            current,_=dep.read_file(target,metrics)
            if current!=identity:raise ValueError('Snapshot changed during release')
            target.unlink();removed.append(name);bytes_removed+=identity['stamp'][2]
        except (OSError,ValueError) as exc:
            errors.append({'name':name,'error':type(exc).__name__+': '+str(exc)})
            break
    result={'schema':'helix.plan_input_release.v1','attempt_hash':attempt_hash,
        'status':'PARTIAL' if errors else 'RELEASED','removed':removed,
        'bytes_removed':bytes_removed,'errors':errors,'validation':metrics,
        'store_io':{k:store.metrics[k]-before_io[k] for k in before_io},
        'seconds_before_receipt':time.perf_counter()-start,
        'scope':'Explicit caller release after consumers finish; no concurrent writers. Logical bytes; physical I/O unmeasured.'}
    receipt=store.put(encode(result))
    return {**result,'release_receipt':receipt['sha256'],'total_seconds':time.perf_counter()-start}
