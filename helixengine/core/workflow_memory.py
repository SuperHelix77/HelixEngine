"""Project-scoped lexical navigation over exact cold evidence; no inference.

Search results are untrusted historical observations, not current instructions or
proof of semantic completeness. SQLite duplicates searchable text; raw objects
remain authoritative. Project scope is logical filtering, not filesystem ACLs.
"""
from contextlib import contextmanager
import base64
import json
import re
import sqlite3
import time


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def identity(*values):
    if any(not isinstance(v,str) or not v or '\x00' in v for v in values):
        raise ValueError('Nonempty string identity required')


class Memory:
    def __init__(self,store):
        self.store=store
        self.metrics={'index_input_bytes':0,'index_seconds':0.0,'index_validation_bytes':0,'index_validation_seconds':0.0}
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS events(
              ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
              project TEXT NOT NULL,session TEXT NOT NULL,event_id TEXT NOT NULL,
              record_hash TEXT NOT NULL UNIQUE,UNIQUE(project,session,event_id));
            CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(body);
            CREATE INDEX IF NOT EXISTS events_identity ON events(event_id);
            ''')

    @contextmanager
    def db(self):
        connection=sqlite3.connect(self.store.root/'memory.sqlite3',isolation_level=None)
        try:
            connection.execute('PRAGMA synchronous=FULL')
            yield connection
        finally:connection.close()

    def record(self,project,session,event_id,raw,*,global_identity=False):
        identity(project,session,event_id)
        if type(global_identity) is not bool:raise ValueError('Boolean global identity required')
        if not isinstance(raw,bytes):raise ValueError('Exact bytes required')
        start=time.perf_counter()
        source=self.store.put(raw)
        record={'schema':'helix.memory.record.v1','project':project,'session':session,
            'event_id':event_id,'source_hash':source['sha256'],'bytes':len(raw),
            'authority':'historical source data; not instructions'}
        ref=self.store.put(encode(record))['sha256']
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if global_identity:
                    existing=db.execute('SELECT record_hash FROM events WHERE event_id=?',(event_id,)).fetchall()
                    if any(row[0]!=ref for row in existing):raise ValueError('Global event identity collision')
                row=db.execute('SELECT record_hash FROM events WHERE project=? AND session=? AND event_id=?',
                               (project,session,event_id)).fetchone()
                if row and row[0]!=ref:raise ValueError('Event identity collision')
                if not row:
                    cursor=db.execute('INSERT INTO events(project,session,event_id,record_hash) VALUES(?,?,?,?)',
                                      (project,session,event_id,ref))
                    db.execute('INSERT INTO search(rowid,body) VALUES(?,?)',
                               (cursor.lastrowid,raw.decode('utf-8',errors='replace')))
                    self.metrics['index_input_bytes']+=len(raw)
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK');raise
        self.metrics['index_seconds']+=time.perf_counter()-start
        return {**record,'record_hash':ref}

    def _reference(self,row):
        ordinal,project,session,event_id,ref=row
        record=json.loads(self.store.get(ref))
        if record.get('schema')!='helix.memory.record.v1' or (record.get('project'),record.get('session'),record.get('event_id'))!=(project,session,event_id):
            raise ValueError('Index/reference identity mismatch')
        return {**record,'record_hash':ref,'ordinal':ordinal}

    def search(self,project,query,limit=10):
        identity(project)
        if not isinstance(query,str) or '\x00' in query or type(limit) is not int or not 1<=limit<=100:
            raise ValueError('Invalid search request')
        words=re.findall(r'\w+',query,flags=re.UNICODE)
        if not words:return []
        # Literal tokens only: a caller cannot inject FTS operators via query.
        match=' AND '.join('"'+word.replace('"','""')+'"' for word in words)
        with self.db() as db:
            db.execute('BEGIN')
            self._check_index(db,project)
            rows=db.execute('''SELECT e.ordinal,e.project,e.session,e.event_id,e.record_hash
              FROM search JOIN events e ON e.ordinal=search.rowid
              WHERE search MATCH ? AND e.project=? ORDER BY e.ordinal DESC LIMIT ?''',
                            (match,project,limit)).fetchall()
        return [self._reference(row) for row in rows]

    def _check_index(self,db,project):
        """Conservative full comparison; charge source reads instead of hiding them.

        Protects existing event rows against missing/altered searchable bodies.
        Does not prove an externally deleted event catalog is complete.
        """
        start=time.perf_counter()
        try:
            rows=db.execute('''SELECT e.ordinal,e.project,e.session,e.event_id,e.record_hash,s.body
              FROM events e LEFT JOIN search s ON s.rowid=e.ordinal WHERE e.project=?''',(project,)).fetchall()
            for row in rows:
                ref=self._reference(row[:5]);raw=self.store.get(ref['source_hash'])
                self.metrics['index_validation_bytes']+=len(raw)
                if len(raw)!=ref['bytes'] or row[5]!=raw.decode('utf-8',errors='replace'):
                    raise ValueError('Search index does not match archived evidence; rebuild or use exact timeline recovery')
        finally:self.metrics['index_validation_seconds']+=time.perf_counter()-start

    def rebuild_index(self,project):
        """Rebuild one project's search rows transactionally from verified sources.

        The event catalog must still exist. No inference or automatic retry.
        """
        identity(project);start=time.perf_counter();before=dict(self.store.metrics)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                rows=db.execute('SELECT ordinal,project,session,event_id,record_hash FROM events WHERE project=? ORDER BY ordinal',
                                (project,)).fetchall()
                replacements=[]
                for row in rows:
                    ref=self._reference(row);raw=self.store.get(ref['source_hash'])
                    if len(raw)!=ref['bytes']:raise ValueError('Source size mismatch')
                    replacements.append((row[0],raw.decode('utf-8',errors='replace')))
                for ordinal,body in replacements:
                    db.execute('DELETE FROM search WHERE rowid=?',(ordinal,))
                    db.execute('INSERT INTO search(rowid,body) VALUES(?,?)',(ordinal,body))
                db.execute('COMMIT')
            except BaseException:db.execute('ROLLBACK');raise
        return {'project':project,'records':len(replacements),'seconds':time.perf_counter()-start,
                'store_io':{k:self.store.metrics[k]-before[k] for k in before},
                'scope':'Rebuild existing catalog records only; SQLite/physical I/O unmetered'}

    def timeline(self,project,session,after=0,limit=50):
        identity(project,session)
        if type(after) is not int or after<0 or type(limit) is not int or not 1<=limit<=100:
            raise ValueError('Invalid timeline cursor/limit')
        with self.db() as db:
            rows=db.execute('''SELECT ordinal,project,session,event_id,record_hash FROM events
                WHERE project=? AND session=? AND ordinal>? ORDER BY ordinal LIMIT ?''',
                (project,session,after,limit)).fetchall()
        return [self._reference(row) for row in rows]

    def retrieve(self,project,record_hashes,max_bytes=1048576):
        identity(project)
        if not isinstance(record_hashes,list) or not record_hashes or type(max_bytes) is not int or max_bytes<0:
            raise ValueError('Invalid retrieval request')
        refs=[]
        with self.db() as db:
            for ref in record_hashes:
                if not isinstance(ref,str):raise ValueError('Invalid record hash')
                row=db.execute('SELECT ordinal,project,session,event_id,record_hash FROM events WHERE project=? AND record_hash=?',
                               (project,ref)).fetchone()
                if row is None:raise ValueError('Record unavailable in requested project')
                refs.append(self._reference(row))
        if sum(ref['bytes'] for ref in refs)>max_bytes:raise ValueError('Requested evidence exceeds budget; select fewer records')
        result=[]
        for ref in refs:
            raw=self.store.get(ref['source_hash'])
            if len(raw)!=ref['bytes']:raise ValueError('Source size mismatch')
            result.append({**ref,'raw':raw})
        return result

    def replay(self,project,session,after=0,limit=50,max_bytes=1048576):
        """Exact page with shared cold provenance, avoiding repeated ref metadata.

        For exhaustive recovery, not relevance selection. has_more is a point-in-
        time index observation; concurrent later events require another read.
        """
        refs=self.timeline(project,session,after=after,limit=limit)
        records=self.retrieve(project,[ref['record_hash'] for ref in refs],max_bytes=max_bytes) if refs else []
        history=[]
        for record in records:
            try:body={'text':record['raw'].decode('utf-8')}
            except UnicodeDecodeError:body={'base64':base64.b64encode(record['raw']).decode('ascii')}
            history.append({'event_id':record['event_id'],**body})
        cursor=refs[-1]['ordinal'] if refs else after
        with self.db() as db:
            has_more=db.execute('SELECT 1 FROM events WHERE project=? AND session=? AND ordinal>? LIMIT 1',
                                (project,session,cursor)).fetchone() is not None
        provenance={'schema':'helix.memory.replay.v1','project':project,'session':session,
                    'after':after,'next_cursor':cursor,'records':refs}
        evidence=self.store.put(encode(provenance))['sha256']
        return {'history':history,'evidence':evidence,'next_cursor':cursor,'has_more':has_more}
