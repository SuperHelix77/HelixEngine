"""Retryable exact message delivery over the observer's metadata-only outbox.

No model calls, command execution, interpretation or context injection. A source
line is read only after the observer bound its range/hash in a committed scan.
"""
import hashlib
import os

from .chat_observer import ObserverError, MAX_LINE_BYTES


class StatementDelivery:
    def __init__(self, observer, sink, project):
        self.observer, self.sink = observer, sink
        with observer._db() as db:
            columns = {r[1] for r in db.execute('PRAGMA table_info(statement_delivery_state)')}
            if 'project' not in columns:
                db.execute('ALTER TABLE statement_delivery_state ADD COLUMN project TEXT')
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT project FROM statement_delivery_state WHERE id=1').fetchone()[0]
            if prior is not None and prior != project:
                db.execute('ROLLBACK')
                raise ValueError('Statement memory project binding changed')
            db.execute('UPDATE statement_delivery_state SET project=? WHERE id=1', (project,))
            db.execute('COMMIT')

    def snapshot(self):
        with self.observer._db() as db:
            state = dict(db.execute('SELECT * FROM statement_delivery_state WHERE id=1').fetchone())
            row = db.execute('SELECT count(*) AS total, count(record_hash) AS delivered FROM statement_outbox').fetchone()
            source = db.execute('SELECT coverage_complete,start_cursor,skipped_oversized_lines,malformed_lines '
                                'FROM observer_state WHERE id=1').fetchone()
        return {**state, 'enabled': self.observer.capture_statements,
                'queued': row['total'], 'delivered': row['delivered'],
                'pending': row['total'] - row['delivered'],
                'source_coverage_complete': bool(source['coverage_complete']),
                'source_start_cursor': source['start_cursor'],
                'source_skipped_oversized_lines': source['skipped_oversized_lines'],
                'source_malformed_lines': source['malformed_lines'],
                'coverage': 'recognized visible assistant messages in observed capture windows only',
                'limits': 'No reasoning, user constraints, automatic supersession or complete history. '
                          'Read bytes exclude SQLite and physical I/O; no inference savings inferred.'}

    def drain(self, limit=16):
        if type(limit) is not int or not 1 <= limit <= 16:
            raise ValueError('Statement delivery limit must be 1..16')
        if not self.observer.capture_statements:
            return self.snapshot()
        read_bytes = attempts = 0
        error = None
        with self.observer._lock:
            try:
                with self.observer._db() as db:
                    state = db.execute('SELECT * FROM observer_state WHERE id=1').fetchone()
                    pending = db.execute('SELECT * FROM statement_outbox WHERE record_hash IS NULL '
                                         'ORDER BY source_offset LIMIT ?', (limit,)).fetchall()
                if pending:
                    expected_identity = (state['file_dev'], state['file_ino'])
                    with self.observer.rollout_path.open('rb') as stream:
                        source = os.fstat(stream.fileno())
                        if (source.st_dev, source.st_ino) != expected_identity:
                            raise ObserverError('Statement source replaced')
                        for row in pending:
                            attempts += 1
                            start, size = row['source_offset'], row['source_bytes']
                            if start < 0 or not 0 < size <= MAX_LINE_BYTES or start + size > state['cursor']:
                                raise ObserverError('Invalid statement source range')
                            stream.seek(start)
                            raw = stream.read(size)
                            read_bytes += len(raw)
                            if len(raw) != size or hashlib.sha256(raw).hexdigest() != row['source_sha256']:
                                raise ObserverError('Statement source no longer matches captured bytes')
                            current = self.observer._source_stat()
                            if current is None or (current.st_dev, current.st_ino) != expected_identity:
                                raise ObserverError('Statement source replaced during retrieval')
                            result = self.sink.record(self.observer.thread_id, raw)
                            # Memory commits first. If this acknowledgement fails,
                            # the stable native identity makes retry idempotent.
                            with self.observer._db() as db:
                                db.execute('UPDATE statement_outbox SET record_hash=? WHERE source_offset=? '
                                           'AND source_sha256=?', (result['record_hash'], start, row['source_sha256']))
            except Exception as exc:
                # Never store archived text or an exception payload in telemetry.
                error = type(exc).__name__ + ': statement delivery incomplete; inspect exact source/index'
            finally:
                with self.observer._db() as db:
                    db.execute('UPDATE statement_delivery_state SET bytes_read=bytes_read+?, '
                               'attempts=attempts+?, error=? WHERE id=1', (read_bytes, attempts, error))
        return self.snapshot()
