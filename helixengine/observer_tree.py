"""Native child accounting over the existing observer/parser and hook lineage.

No inference, transcript text storage, configuration changes or extra command
wrapper. The private Codex state_5 registry is a version-specific lookup, not a
stable public API; unavailable/changed registries are explicit gaps.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from .chat_observer import ChatObserver, ObserverError, MAX_LINE_BYTES, _USAGE_KEYS


class ObserverTree:
    def __init__(self, root_observer, state, codex_home):
        self.root = root_observer
        self.state = state
        self.home = Path(codex_home).resolve() if codex_home is not None else None
        self.children = {}
        self.next_retry = {}
        self.rotation = 0
        with self.root._db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS tree_state(id INTEGER PRIMARY KEY,
                    event_cursor INTEGER NOT NULL, error TEXT, header_bytes_read INTEGER NOT NULL);
                INSERT OR IGNORE INTO tree_state VALUES(1,0,NULL,0);
                CREATE TABLE IF NOT EXISTS tree_links(child TEXT PRIMARY KEY,parent TEXT NOT NULL,
                    path TEXT, header_sha256 TEXT, error TEXT, snapshot TEXT,
                    import_cursor INTEGER NOT NULL DEFAULT 0, native_parent TEXT);
            ''')
            if 'native_parent' not in {r[1] for r in db.execute('PRAGMA table_info(tree_links)')}:
                db.execute('ALTER TABLE tree_links ADD COLUMN native_parent TEXT')

    def _members(self, db):
        links = [dict(row) for row in db.execute('SELECT * FROM tree_links ORDER BY child')]
        known = {self.root.thread_id}
        for _ in range(len(links)):
            added = {r['child'] for r in links if r['parent'] in known and r['child'] not in known}
            if not added:
                break
            known.update(added)
        return [r for r in links if r['child'] in known and r['child'] != self.root.thread_id]

    def _discover(self):
        with self.root._db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                cursor = db.execute('SELECT event_cursor FROM tree_state WHERE id=1').fetchone()[0]
                with self.state.db() as source:
                    events = source.execute("SELECT id,body FROM events WHERE id>? AND kind IN ('CODEX_SUBAGENTSTART','CODEX_SUBAGENTSTOP') ORDER BY id LIMIT 256", (cursor,)).fetchall()
                for event in events:
                    body = json.loads(event['body'])
                    child, parent = body.get('agent_id'), body.get('session_id')
                    if any(not isinstance(x, str) or not x or '\x00' in x or len(x.encode()) > 512 for x in (child, parent)) or child == parent or child == self.root.thread_id:
                        raise ObserverError('Invalid child lineage event')
                    old = db.execute('SELECT parent FROM tree_links WHERE child=?', (child,)).fetchone()
                    if old and old['parent'] != parent:
                        raise ObserverError('Conflicting child parent binding')
                    if not old:
                        if db.execute('SELECT count(*) FROM tree_links').fetchone()[0] >= 1024:
                            raise ObserverError('Child discovery limit reached; coverage incomplete')
                        db.execute('INSERT INTO tree_links(child,parent) VALUES(?,?)', (child, parent))
                    cursor = event['id']
                db.execute('UPDATE tree_state SET event_cursor=?,error=NULL WHERE id=1', (cursor,))
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise

    def _resolve(self, link):
        if self.home is None:
            raise ObserverError('Codex registry home not established for this attachment')
        registry = self.home / 'state_5.sqlite'
        if not registry.is_file() or registry.is_symlink():
            raise ObserverError('Supported native registry unavailable')
        with sqlite3.connect(registry.as_uri() + '?mode=ro', uri=True, timeout=1) as db:
            row = db.execute('SELECT rollout_path FROM threads WHERE id=?', (link['child'],)).fetchone()
        if not row:
            raise ObserverError('Child rollout not yet registered')
        if not isinstance(row[0], str) or len(row[0].encode()) > 4096:
            raise ObserverError('Invalid child source path')
        original = Path(row[0])
        path = original.resolve(strict=True)
        sessions = (self.home / 'sessions').resolve(strict=True)
        if original.is_symlink() or path != original.absolute() or not path.is_relative_to(sessions) or not path.is_file():
            raise ObserverError('Child source is outside native sessions or symlinked')
        if not path.name.endswith('-' + link['child'] + '.jsonl'):
            raise ObserverError('Child source filename identity mismatch')
        if link['path'] and link['path'] != str(path):
            raise ObserverError('Child source registry binding changed')
        with path.open('rb') as stream:
            identity = os.fstat(stream.fileno())
            header = stream.readline(MAX_LINE_BYTES + 1)
        with self.root._db() as db:
            db.execute('UPDATE tree_state SET header_bytes_read=header_bytes_read+? WHERE id=1', (len(header),))
        if len(header) > MAX_LINE_BYTES or not header.endswith(b'\n'):
            raise ObserverError('Child identity header unavailable or oversized')
        record = json.loads(header)
        payload = record.get('payload', {})
        if record.get('type') != 'session_meta' or payload.get('id') != link['child']:
            raise ObserverError('Native child/parent metadata mismatch')
        native_parent = payload.get('parent_thread_id')
        if native_parent != link['parent']:
            # Native hooks retain the root session for grandchildren too. Bind
            # their immediate parent from native metadata only after its whole
            # previously verified ancestry reaches this observed root.
            if link['parent'] != self.root.thread_id or payload.get('session_id') != self.root.thread_id:
                raise ObserverError('Native child/parent metadata mismatch')
            ancestor, seen = native_parent, {link['child']}
            with self.root._db() as db:
                while ancestor != self.root.thread_id:
                    if not isinstance(ancestor, str) or ancestor in seen or len(seen) > 64:
                        raise ObserverError('Invalid native ancestry')
                    seen.add(ancestor)
                    parent = db.execute('SELECT native_parent,header_sha256 FROM tree_links WHERE child=?', (ancestor,)).fetchone()
                    if not parent or not parent['header_sha256'] or not parent['native_parent']:
                        raise ObserverError('Native parent ancestry not yet verified')
                    ancestor = parent['native_parent']
        # Installed native child metadata retains the root session_id while
        # id is the producing child and parent_thread_id is its actual parent.
        if payload.get('session_id', link['child']) not in (link['child'], link['parent'], self.root.thread_id):
            raise ObserverError('Conflicting native child identity')
        digest = hashlib.sha256(header).hexdigest()
        if link['header_sha256'] and link['header_sha256'] != digest:
            raise ObserverError('Child identity header changed')
        after = path.stat()
        if (identity.st_dev, identity.st_ino) != (after.st_dev, after.st_ino):
            raise ObserverError('Child source replaced during identity validation')
        return path, digest, native_parent, (identity.st_dev, identity.st_ino)

    def _child(self, link):
        if link['child'] not in self.children:
            path, digest, native_parent, identity = self._resolve(link)
            directory = self.root.data_dir / 'child-usage' / hashlib.sha256(link['child'].encode()).hexdigest()
            child = ChatObserver(directory, path, link['child'], from_start=True)
            with child._db() as db:
                bound = db.execute('SELECT file_dev,file_ino FROM observer_state WHERE id=1').fetchone()
                if tuple(bound) != identity:
                    raise ObserverError('Child source changed before observer attachment')
            with self.root._db() as db:
                db.execute('UPDATE tree_links SET path=?,header_sha256=?,native_parent=? WHERE child=?', (str(path), digest, native_parent, link['child']))
            self.children[link['child']] = child
        return self.children[link['child']]

    def _import(self, child, link):
        with self.root._db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                cursor = db.execute('SELECT import_cursor FROM tree_links WHERE child=?', (link['child'],)).fetchone()[0]
                unresolved = [r[0] for r in db.execute("SELECT response_id FROM usage_records WHERE thread_id=? AND (model='UNKNOWN' OR effort='UNKNOWN') LIMIT 32", (link['child'],))]
                with child._db() as source:
                    query = 'SELECT * FROM usage_records WHERE thread_id=? AND (id>?'
                    args = [link['child'], cursor]
                    if unresolved:
                        query += ' OR response_id IN (' + ','.join('?' for _ in unresolved) + ')'
                        args.extend(unresolved)
                    records = source.execute(query + ') ORDER BY id LIMIT 512', args).fetchall()
                names = ('response_id', 'thread_id', 'turn_id', 'event_timestamp', 'model', 'effort', *_USAGE_KEYS)
                for record in records:
                    old = db.execute('SELECT * FROM usage_records WHERE response_id=?', (record['response_id'],)).fetchone()
                    if old and any(old[k] != record[k] and not (k in ('model', 'effort') and old[k] == 'UNKNOWN') for k in names):
                        raise ObserverError('Conflicting cross-thread response identity')
                    if not old:
                        db.execute('INSERT INTO usage_records(' + ','.join(names) + ') VALUES(' + ','.join('?' for _ in names) + ')', tuple(record[k] for k in names))
                    else:
                        db.execute('UPDATE usage_records SET model=?,effort=? WHERE response_id=?', (record['model'], record['effort'], record['response_id']))
                    cursor = max(cursor, record['id'])
                db.execute('UPDATE tree_links SET import_cursor=? WHERE child=?', (cursor, link['child']))
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise

    def scan(self):
        try:
            self._discover()
        except Exception as exc:
            with self.root._db() as db:
                db.execute('UPDATE tree_state SET error=? WHERE id=1', (f'{type(exc).__name__}: {exc}'[:512],))
        with self.root._db() as db:
            members = self._members(db)
        # At most four existing bounded parsers per tick. Closed children remain
        # observable: a lifecycle STOP does not prove final usage was flushed.
        selected = (members[self.rotation:] + members[:self.rotation])[:4]
        self.rotation = (self.rotation + len(selected)) % max(1, len(members))
        for link in selected:
            if time.monotonic() < self.next_retry.get(link['child'], 0):
                continue
            error, snapshot = None, None
            try:
                child = self._child(link)
                snapshot = child.scan()
                self._import(child, link)
                error = snapshot.get('error')
            except Exception as exc:
                error = f'{type(exc).__name__}: {exc}'[:512]
                self.next_retry[link['child']] = time.monotonic() + 5
            with self.root._db() as db:
                db.execute('UPDATE tree_links SET error=?,snapshot=COALESCE(?,snapshot) WHERE child=?',
                           (error, json.dumps(snapshot) if snapshot is not None else None, link['child']))
        return self.snapshot()

    def snapshot(self):
        with self.root._db() as db:
            db.execute('BEGIN')
            members = self._members(db)
            ids = [self.root.thread_id] + [r['child'] for r in members]
            where = ','.join('?' for _ in ids)
            rows = db.execute('SELECT model,effort,count(*) AS responses,' + ','.join('sum('+k+') AS '+k for k in _USAGE_KEYS) +
                              ' FROM usage_records WHERE thread_id IN ('+where+') GROUP BY model,effort', ids).fetchall()
            state = dict(db.execute('SELECT * FROM tree_state WHERE id=1').fetchone())
            children = []
            for link in members:
                snap = json.loads(link['snapshot']) if link['snapshot'] else {}
                children.append({'thread_id': link['child'], 'parent_thread_id': link['native_parent'],
                                 'observed_session_id': link['parent'],
                                 'error': link['error'], 'connected': snap.get('connected'),
                                 'response_count': snap.get('response_count'),
                                 'coverage_complete': snap.get('coverage_complete', False),
                                 'cursor': snap.get('cursor'), 'bytes_read': snap.get('bytes_read'),
                                 'usage': snap.get('usage')})
                imported = db.execute('SELECT count(*) FROM usage_records WHERE thread_id=?', (link['child'],)).fetchone()[0]
                children[-1]['imported_response_count'] = imported
                children[-1]['import_pending'] = None if snap.get('response_count') is None else snap['response_count'] - imported
            return {'scope': 'observed root attachment window plus discovered child histories',
                    'usage': {k: sum(r[k] for r in rows) for k in _USAGE_KEYS},
                    'response_count': sum(r['responses'] for r in rows),
                    'by_model': [dict(r) for r in rows], 'children': children,
                    'child_count': len(children), 'discovery_error': state['error'],
                    'header_bytes_read': state['header_bytes_read'],
                    'whole_workflow_complete': False,
                    'limits': 'Lifecycle-event discovery is not proof of all descendants or billing. '
                              'Missing sources/counters are unknown; no cumulative token_count records summed. '
                              'Child backfill differs from parent attachment window. SQLite I/O is not measured.'}
