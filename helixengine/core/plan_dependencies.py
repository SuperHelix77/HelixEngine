"""Declared dependency checks and stable read snapshots, not a host sandbox."""
import hashlib,os,stat,time
from pathlib import Path


def digest(data):return hashlib.sha256(data).hexdigest()


def stamp(s):
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,stat.S_IMODE(s.st_mode)]


def local_path(root,name):
    if not isinstance(name,str) or not name or '\x00' in name or any(x in ('','.','..') for x in name.replace('\\','/').split('/')):
        raise ValueError('Invalid relative dependency path')
    p=Path(name)
    if p.is_absolute() or not p.parts or any(x in ('.','..') for x in p.parts):
        raise ValueError('Invalid relative dependency path')
    result=root/p
    for part in [result,*list(result.parents)[:len(p.parts)-1]]:
        if part.is_symlink():raise ValueError('Symlink dependency not admitted')
    return result


def read_file(path,metrics):
    start=time.perf_counter()
    initial=path.stat(follow_symlinks=False)
    if stat.S_ISLNK(initial.st_mode) or getattr(initial,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0):raise ValueError("Reparse/symlink dependency rejected")
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_BINARY",0))
    data=b''
    try:
        before=os.fstat(fd)
        if stamp(initial)!=stamp(before):raise ValueError('Dependency identity changed before read')
        if not stat.S_ISREG(before.st_mode):raise ValueError('Dependency is not a regular file')
        with os.fdopen(fd,'rb',closefd=False) as f:data=f.read()
        after=os.fstat(fd)
        if stamp(before)!=stamp(after) or stamp(after)!=stamp(path.stat(follow_symlinks=False)):
            raise ValueError('Dependency changed during read')
    finally:os.close(fd)
    metrics['bytes_read']+=len(data);metrics['bytes_hashed']+=len(data)
    identity={'sha256':digest(data),'stamp':stamp(after)}
    metrics['seconds']+=time.perf_counter()-start
    return identity,data


def metric():return {'bytes_read':0,'bytes_hashed':0,'seconds':0.0}


def directory(path):
    st=path.stat()
    if not stat.S_ISDIR(st.st_mode):raise ValueError('Working directory missing')
    return {'path':str(path),'identity':[st.st_dev,st.st_ino,stat.S_IMODE(st.st_mode)]}


def environment_binding(names,environment):
    return {n:{'present':n in environment,'sha256':digest(environment[n].encode()) if n in environment else None} for n in names}


def verify(manifest,environment,metrics,workspace=None,snapshot_stamps=None):
    root=Path(manifest['cwd']['path'])
    if directory(root)!=manifest['cwd']:raise ValueError('Working directory invalidated')
    if environment_binding(manifest['environment'],environment)!=manifest['environment']:
        raise ValueError('Environment invalidated')
    for name,binding in manifest['files'].items():
        got,_=read_file(local_path(root,name),metrics)
        if got!=binding['identity']:raise ValueError('Declared dependency invalidated: '+name)
        if workspace is not None:
            current,_=read_file(local_path(workspace,name),metrics)
            if current!=snapshot_stamps[name]:raise ValueError('Snapshot invalidated: '+name)
    for name,binding in manifest['executables'].items():
        requested=Path(binding['requested'])
        if str(requested.resolve(strict=True))!=binding['resolved']:
            raise ValueError('Executable resolution invalidated: '+name)
        got,_=read_file(Path(binding['resolved']),metrics)
        if got!=binding['identity']:raise ValueError('Executable invalidated: '+name)
    for path,expected in manifest['runner_modules'].items():
        got,_=read_file(Path(path),metrics)
        if got['sha256']!=expected:raise ValueError('Runner invalidated')
