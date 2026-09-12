"""Bounded exact-source assembly. No execution of model-supplied code or paths.

A caller supplies a validated plan and destination. Hash-bound byte ranges preserve
source versions. Publication uses caller expected-destination bytes as a stale
write check under an advisory lock; cooperating writers must use the same lock.
"""
import hashlib,os,tempfile
from .locking import exclusive_lock
from pathlib import Path


def assemble(store, plan, max_output_bytes=10_000_000, max_operations=1024):
    if not isinstance(plan,dict) or set(plan)!={'schema','operations'} or plan['schema']!='helix.copy.v1':
        raise ValueError('Invalid copy plan schema')
    operations=plan['operations']
    if not isinstance(operations,list) or len(operations)>max_operations:
        raise ValueError('Operation limit exceeded')
    cache={};parts=[];total=0
    for op in operations:
        if not isinstance(op,dict):raise ValueError('Invalid operation')
        if set(op)=={'source_sha256','start_byte','end_byte'}:
            start,end=op['start_byte'],op['end_byte']
            if type(start) is not int or type(end) is not int or start<0 or end<start:
                raise ValueError('Invalid half-open byte range')
            key=op['source_sha256']
            if key not in cache:cache[key]=store.get(key)
            source=cache[key]
            if end>len(source):raise ValueError('Range exceeds exact source')
            part=source[start:end]
        elif set(op)=={'literal_utf8'} and isinstance(op['literal_utf8'],str):
            part=op['literal_utf8'].encode('utf-8')
        else:raise ValueError('Unknown operation; paths and executable expressions are forbidden')
        total+=len(part)
        if total>max_output_bytes:raise ValueError('Output limit exceeded')
        parts.append(part)
    raw=b''.join(parts)
    return raw,{'schema':'helix.copy.receipt.v1','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'source_sha256':list(cache),'operations':len(operations),'io':dict(store.metrics),'scope':'Exact byte assembly only; caller must validate semantic selection and count plan generation, retrieval and rendering costs'}


def publish(store,plan,destination,expected_sha256=None,**limits):
    """expected_sha256=None means require an absent destination, not overwrite-any."""
    raw,receipt=assemble(store,plan,**limits)
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    lock=destination.with_name(destination.name+'.helix-lock')
    with exclusive_lock(lock):
        if destination.is_symlink():raise ValueError('Symlink destination is not accepted')
        before=destination.read_bytes() if destination.exists() else None
        observed=hashlib.sha256(before).hexdigest() if before is not None else None
        if observed!=expected_sha256:raise ValueError('Destination changed; nothing published')
        fd,temp=tempfile.mkstemp(dir=destination.parent,prefix='.helix-copy-')
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.replace(temp,destination)
        finally:
            if os.path.exists(temp):os.unlink(temp)
    receipt['publication_io']={'prior_destination_bytes_read':len(before) if before is not None else 0,'destination_bytes_written':len(raw),'metadata_and_physical_disk_unmeasured':True}
    receipt['publication']='atomic replacement; cooperative advisory lock; parent directory fsync and hostile concurrent writers are outside guarantee'
    return receipt
