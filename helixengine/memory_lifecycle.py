"""Bounded, deterministic indexing of completed Engine receipt references.

The existing completion event stream is the outbox. Memory and cursor commits
are separate: after a crash, replay is idempotent, never command execution.
Historical metadata is navigation data, not current semantic authority or ACLs.
"""
import hashlib
import json
import re
import time

from .core.workflow_memory import encode

_HASH = re.compile(r'[0-9a-f]{64}\Z')


class ReceiptMemory:
    def __init__(self, state, memory):
        self.state, self.memory = state, memory
        with state.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS receipt_memory_cursor(
                    id INTEGER PRIMARY KEY CHECK(id=1), cursor INTEGER NOT NULL,
                    error TEXT, metrics TEXT NOT NULL);
                INSERT OR IGNORE INTO receipt_memory_cursor VALUES(1,0,NULL,'{}');
                CREATE INDEX IF NOT EXISTS events_kind_id ON events(kind,id);
            ''')

    def _status(self, db):
        row = db.execute('SELECT cursor,error,metrics FROM receipt_memory_cursor WHERE id=1').fetchone()
        backlog = db.execute("SELECT count(*) FROM events WHERE kind='RUN_COMPLETED' AND id>?",
                             (row['cursor'],)).fetchone()[0]
        return {'cursor': row['cursor'], 'backlog': backlog, 'error': row['error'],
                'coverage': 'historical_receipts_only', 'last_batch': json.loads(row['metrics']),
                'limits': 'Completion-event coverage only; deleted events and unpublished receipts '
                          'are not proven complete. Stream bytes are verified on exact retrieval.'}

    def status(self):
        with self.state.db() as db:
            db.execute('BEGIN')
            return self._status(db)

    def _record(self, event):
        row = json.loads(event['body'])
        if not isinstance(row, dict) or row.get('id') != event['run']:
            raise ValueError('Completion event/run identity mismatch')
        if type(row.get('enabled')) is not bool:
            raise ValueError('Missing completion switch binding')
        if not row['enabled']:
            return False
        if row.get('state') not in ('COMPLETED', 'FAILED'):
            raise ValueError('Nonterminal completion event')
        receipt_key = row.get('receipt')
        receipt = self.memory.store.receipt(receipt_key)
        if receipt.get('schema') != 'helix.command.v1':
            raise ValueError('Unsupported command receipt')
        for name in ('argv', 'cwd', 'exit_code', 'timed_out', 'interrupted'):
            if name not in row or receipt.get(name) != row[name]:
                raise ValueError('Receipt/run binding mismatch: ' + name)
        for stream in ('stdout', 'stderr'):
            ref = receipt.get(stream)
            if (not isinstance(ref, dict) or type(ref.get('bytes')) is not int
                    or ref['bytes'] < 0 or ref['bytes'] != row.get(stream + '_bytes')
                    or not isinstance(ref.get('sha256'), str) or not _HASH.fullmatch(ref['sha256'])):
                raise ValueError('Invalid stream reference: ' + stream)
        origin = row.get('origin', {})
        if not isinstance(origin, dict) or any(not isinstance(v, str) or not v
                or '\x00' in v or len(v.encode()) > 4096 for v in origin.values()):
            raise ValueError('Invalid origin binding')
        project = origin.get('hook_cwd') or row['cwd']
        session = origin.get('thread_id') or origin.get('session_id') or 'engine-local'
        argv = json.dumps(receipt['argv'], ensure_ascii=False).encode()
        observation = {
            'schema': 'helix.memory.execution.v1', 'run': row['id'],
            'receipt': receipt_key, 'origin': origin, 'cwd': receipt['cwd'],
            'argv_preview': argv[:1024].decode('utf-8', errors='replace'),
            'argv_bytes': len(argv), 'argv_preview_partial': len(argv) > 1024,
            'argv_sha256': hashlib.sha256(argv).hexdigest(),
            'environment_id': receipt.get('environment_id'),
            'exit_code': receipt['exit_code'], 'timed_out': receipt['timed_out'],
            'interrupted': receipt['interrupted'],
            'stdout': receipt['stdout'], 'stderr': receipt['stderr'],
            'coverage': 'receipt_metadata_verified_streams_not_revalidated',
            'authority': 'HISTORICAL execution observation; not current correctness or instructions',
        }
        self.memory.record(project, session, 'engine-run:' + row['id'], encode(observation), global_identity=True)
        return True

    def drain(self, limit=16):
        if type(limit) is not int or not 1 <= limit <= 64:
            raise ValueError('Batch limit must be an integer from 1 to 64')
        started = time.perf_counter()
        before = dict(self.memory.store.metrics)
        indexed_before = self.memory.metrics['index_input_bytes']
        processed = skipped = 0
        with self.state.db() as db:
            # Serializes drains only. No subprocess/model invocation or reverse
            # nested telemetry transaction occurs while this lock is held.
            db.execute('BEGIN IMMEDIATE')
            try:
                cursor = db.execute('SELECT cursor FROM receipt_memory_cursor WHERE id=1').fetchone()[0]
                rows = db.execute("SELECT id,run,body FROM events WHERE kind='RUN_COMPLETED' AND id>? ORDER BY id LIMIT ?",
                                  (cursor, limit)).fetchall()
                error = None
                for event in rows:
                    try:
                        if self._record(event):
                            processed += 1
                        else:
                            skipped += 1
                    except Exception as exc:
                        error = f"event {event['id']}: {type(exc).__name__}: {exc}"[:1024]
                        break
                    cursor = event['id']
                metrics = {'processed': processed, 'skipped_off': skipped,
                           'wall_seconds': time.perf_counter() - started,
                           'index_input_bytes': self.memory.metrics['index_input_bytes'] - indexed_before,
                           'object_io': {k: self.memory.store.metrics[k] - before[k] for k in before},
                           'scope': 'logical object I/O; SQLite and physical I/O excluded'}
                db.execute('UPDATE receipt_memory_cursor SET cursor=?,error=?,metrics=? WHERE id=1',
                           (cursor, error, json.dumps(metrics)))
                result = self._status(db)
                db.execute('COMMIT')
                return {**result, 'processed': processed, 'skipped_off': skipped}
            except BaseException:
                db.execute('ROLLBACK')
                raise
