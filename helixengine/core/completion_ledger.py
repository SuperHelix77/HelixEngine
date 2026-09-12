"""Idempotent completion ingestion, not a semantic gate or effect executor.

Caller retains the expected head outside this mutable index. This protects against
index rollback only while that trusted head survives. No hostile-host guarantee.
Raw records use existing CAS; SQLite commits identity and head together. Orphan CAS
objects after failure are harmless but charged. No automatic model invocation.
"""
import hashlib
import json
from .workflow_memory import encode, identity

EMPTY = '0' * 64


class CompletionLedger:
    def __init__(self, memory):
        self.memory = memory
        with memory.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS completion_heads(
                    scope TEXT PRIMARY KEY, root TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS completion_ids(
                    scope TEXT NOT NULL, event TEXT NOT NULL, root TEXT NOT NULL,
                    PRIMARY KEY(scope,event));
            ''')

    def _chain(self, root, scope):
        rows = []
        seen = set()
        while root != EMPTY:
            if root in seen:
                raise ValueError('Cycle')
            seen.add(root)
            record = json.loads(self.memory.store.get(root))
            if record.get('schema') != 'helix.completion.v1' or record.get('scope') != scope:
                raise ValueError('Completion scope/schema mismatch')
            raw = self.memory.store.get(record['payload'])
            if len(raw) != record['bytes']:
                raise ValueError('Completion length mismatch')
            rows.append((root, record, raw))
            root = record['parent']
        return rows

    def ingest(self, scope, event, raw, *, expected_head, sequence=None):
        """Persist exact completed-interaction data; never interpret it as authority.

        Retry may use original parent or current head. Conflicting reuse rejects.
        Return both historical receipt and current head; do not reset caller head
        to an older replay receipt. Prior records are verified before any commit.
        """
        identity(scope, event, expected_head)
        if not isinstance(raw, bytes):
            raise ValueError('Exact bytes required')
        if sequence is not None and (type(sequence) is not int or sequence<1):
            raise ValueError('Invalid sequence')
        with self.memory.db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT root FROM completion_heads WHERE scope=?', (scope,)).fetchone()
                head = row[0] if row else EMPTY
                chain = self._chain(head, scope)
                by_event = {r['event']: (key, r) for key, r, _ in chain}
                if len(by_event) != len(chain):
                    raise ValueError('Duplicate committed identity')
                indexed = dict(db.execute('SELECT event,root FROM completion_ids WHERE scope=?', (scope,)))
                if indexed != {e: k for e, (k, _) in by_event.items()}:
                    raise ValueError('Completion index mismatch')
                prior = by_event.get(event)
                if sequence is not None:
                    ordinal=next((len(chain)-i for i,(_,r,_) in enumerate(chain) if r['event']==event),len(chain)+1)
                    if sequence!=ordinal:raise ValueError('Sequence gap or conflicting replay ordinal')
                if prior:
                    key, record = prior
                    if record['payload'] != hashlib.sha256(raw).hexdigest():
                        raise ValueError('Conflicting completed interaction')
                    if expected_head not in (head, record['parent']):
                        raise ValueError('Stale retry binding')
                    result = {'receipt': key, 'head': head, 'replayed': True}
                else:
                    if expected_head != head:
                        raise ValueError('Stale completion head')
                    payload = self.memory.store.put(raw)['sha256']
                    record = dict(schema='helix.completion.v1', scope=scope,
                                  event=event, parent=head, payload=payload, bytes=len(raw))
                    key = self.memory.store.put(encode(record))['sha256']
                    # Prior chain was verified in this transaction. Validate the
                    # new objects without rereading the entire prefix a second
                    # time. This is snapshot validation, not protection against
                    # a hostile process modifying CAS concurrently with commit.
                    if self.memory.store.get(key) != encode(record) or self.memory.store.get(payload) != raw:
                        raise ValueError('Completion readback mismatch')
                    db.execute('INSERT INTO completion_ids VALUES(?,?,?)', (scope,event,key))
                    db.execute('INSERT INTO completion_heads VALUES(?,?) ON CONFLICT(scope) DO UPDATE SET root=excluded.root', (scope,key))
                    result = {'receipt': key, 'head': key, 'replayed': False}
                db.execute('COMMIT')
                return result
            except BaseException:
                db.execute('ROLLBACK')
                raise

    def recover(self, scope, *, expected_head):
        """Index-free exact replay from caller-pinned root, like an epoch read.

        Does not silently rebuild the mutable head or execute stored actions.
        """
        identity(scope, expected_head)
        return [{'receipt': key, 'event': record['event'], 'raw': raw}
                for key, record, raw in reversed(self._chain(expected_head, scope))]
