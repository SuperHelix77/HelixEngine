"""Read-only observation of one explicit Codex rollout.

The observer is deliberately separate from :mod:`helixengine.state`.  It
stores only the small native usage receipt and context metadata needed by a
research HUD; it never starts a command, calls a model, edits Codex
configuration, or retains rollout text.
"""

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import stat
import threading
import time


MAX_SCAN_BYTES = 1_000_000
"""Maximum number of rollout bytes consumed by one :meth:`ChatObserver.scan`."""

MAX_LINE_BYTES = 64 * 1024
"""Complete JSON lines larger than this are skipped without JSON decoding."""

RECENT_LIMIT = 20
_READ_CHUNK_BYTES = 64 * 1024
_ANCHOR_BYTES = 64
_CONTENT_BUDGET = MAX_SCAN_BYTES - (3 * _ANCHOR_BYTES)
_UNKNOWN = "UNKNOWN"
_USAGE_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
_DB_NAME = "chat_observer.sqlite3"
_MAX_ID_BYTES = 512
_MAX_METADATA_BYTES = 256


class ObserverError(ValueError):
    """An explicit observer/source error that is safe to show in the HUD."""


def _text(value, label, *, limit=_MAX_ID_BYTES):
    if (
        type(value) is not str
        or not value
        or "\x00" in value
        or len(value.encode("utf-8")) > limit
    ):
        raise ObserverError(f"invalid {label}")
    return value


def _metadata(value, default=_UNKNOWN):
    if type(value) is str and value and "\x00" not in value:
        if len(value.encode("utf-8")) <= _MAX_METADATA_BYTES:
            return value
    return default


def _timestamp(value):
    if type(value) is str and "\x00" not in value and len(value.encode("utf-8")) <= _MAX_METADATA_BYTES:
        return value
    if type(value) in (int, float) and math.isfinite(value):
        return value
    return None


def _timestamp_json(value):
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _identity_from_stat(source):
    return int(source.st_dev), int(source.st_ino)


class ChatObserver:
    """Observe one explicitly supplied rollout file for one thread.

    Construction creates or reopens ``chat_observer.sqlite3`` below
    ``data_dir``.  A new attachment records the current file end as its
    cursor, so existing rollout history is never backfilled.  Subsequent
    scans consume only newline-terminated records from that cursor.

    ``snapshot()`` has this stable shape::

        {
            "connected": bool,
            "last_scan": float | None,
            "bytes_read": int,
            "error": str | None,
            "model": str,
            "effort": str,
            "thread_id": str,
            "usage": {six native token totals},
            "response_count": int,
            "attached_at": float,
            "recent": [{"timestamp", "response_id", "model", "usage"}],
            "cursor": int,
        }

    The database contains no message, tool-call, summary, reasoning, or raw
    JSON payload columns.
    """

    def __init__(self, data_dir, rollout_path, thread_id, *, from_start=False, capture_statements=False):
        if type(from_start) is not bool:
            raise ObserverError('Boolean history opt-in required')
        if type(capture_statements) is not bool:
            raise ObserverError('Boolean statement capture opt-in required')
        self.capture_statements = capture_statements
        self.from_start = from_start
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.rollout_path = Path(rollout_path).expanduser().resolve()
        self.thread_id = _text(thread_id, "thread id")
        self.db_path = self.data_dir / _DB_NAME
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def _schema(db):
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS observer_state(
                id INTEGER PRIMARY KEY CHECK(id = 1),
                rollout_path TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                attached_at REAL NOT NULL,
                last_scan REAL,
                cursor INTEGER NOT NULL CHECK(cursor >= 0),
                bytes_read INTEGER NOT NULL CHECK(bytes_read >= 0),
                file_dev INTEGER,
                file_ino INTEGER,
                anchor TEXT,
                skipping_line INTEGER NOT NULL CHECK(skipping_line IN (0, 1)),
                seen INTEGER NOT NULL CHECK(seen IN (0, 1)),
                connected INTEGER NOT NULL CHECK(connected IN (0, 1)),
                error TEXT,
                fatal INTEGER NOT NULL CHECK(fatal IN (0, 1)),
                coverage_complete INTEGER NOT NULL DEFAULT 1 CHECK(coverage_complete IN (0, 1)),
                skipped_oversized_lines INTEGER NOT NULL DEFAULT 0 CHECK(skipped_oversized_lines >= 0),
                model TEXT NOT NULL,
                effort TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS turn_contexts(
                turn_id TEXT PRIMARY KEY,
                thread_id TEXT,
                model TEXT NOT NULL,
                effort TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage_records(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                response_id TEXT NOT NULL UNIQUE,
                thread_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                event_timestamp TEXT,
                model TEXT NOT NULL,
                effort TEXT NOT NULL,
                input_tokens INTEGER NOT NULL CHECK(input_tokens >= 0),
                cached_input_tokens INTEGER NOT NULL CHECK(cached_input_tokens >= 0),
                cache_write_input_tokens INTEGER NOT NULL CHECK(cache_write_input_tokens >= 0),
                output_tokens INTEGER NOT NULL CHECK(output_tokens >= 0),
                reasoning_output_tokens INTEGER NOT NULL CHECK(reasoning_output_tokens >= 0),
                total_tokens INTEGER NOT NULL CHECK(total_tokens >= 0)
            );
            CREATE INDEX IF NOT EXISTS usage_records_turn_idx
                ON usage_records(thread_id, turn_id);
            CREATE TABLE IF NOT EXISTS statement_outbox(
                source_offset INTEGER PRIMARY KEY,
                source_bytes INTEGER NOT NULL,
                source_sha256 TEXT NOT NULL,
                message_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                record_hash TEXT
            );
            CREATE TABLE IF NOT EXISTS statement_delivery_state(
                id INTEGER PRIMARY KEY CHECK(id=1),
                bytes_read INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                error TEXT
            );
            INSERT OR IGNORE INTO statement_delivery_state(id) VALUES(1);
            """
        )
        columns = {item[1] for item in db.execute("PRAGMA table_info(observer_state)")}
        if "coverage_complete" not in columns:
            db.execute(
                "ALTER TABLE observer_state ADD COLUMN coverage_complete INTEGER NOT NULL DEFAULT 1"
            )
        if "skipped_oversized_lines" not in columns:
            db.execute(
                "ALTER TABLE observer_state ADD COLUMN skipped_oversized_lines INTEGER NOT NULL DEFAULT 0"
            )
        for name, declaration in (
            ("start_cursor", "INTEGER"),
            ("malformed_lines", "INTEGER NOT NULL DEFAULT 0"),
            ("initial_partial_line", "INTEGER NOT NULL DEFAULT 0"),
            ("initial_source_missing", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in columns:
                db.execute(f"ALTER TABLE observer_state ADD COLUMN {name} {declaration}")
        # Older databases did not retain the attachment boundary or durable
        # malformed-line counts. Do not infer complete coverage from them.
        db.execute(
            "UPDATE observer_state SET coverage_complete=0 WHERE start_cursor IS NULL"
        )

    def _partial_boundary(self, cursor, read_counter):
        if cursor == 0:
            return False
        with self.rollout_path.open("rb") as stream:
            stream.seek(cursor - 1)
            last = stream.read(1)
        read_counter[0] += len(last)
        if not last:
            raise ObserverError("rollout source truncated")
        return last != b"\n"

    def _source_stat(self):
        try:
            source = os.stat(self.rollout_path)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ObserverError("rollout source unavailable") from exc
        if not stat.S_ISREG(source.st_mode):
            raise ObserverError("rollout source is not a regular file")
        return source

    def _anchor(self, cursor, read_counter=None):
        if cursor <= 0:
            return None
        width = min(_ANCHOR_BYTES, cursor)
        try:
            with self.rollout_path.open("rb") as stream:
                stream.seek(cursor - width)
                raw = stream.read(width)
        except OSError as exc:
            raise ObserverError("rollout source unavailable") from exc
        if read_counter is not None:
            read_counter[0] += len(raw)
        if len(raw) != width:
            raise ObserverError("rollout source truncated")
        return hashlib.sha256(raw).hexdigest()

    def _initialize(self):
        with self._lock, self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            self._schema(db)
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT * FROM observer_state WHERE id=1").fetchone()
                if row is not None:
                    if row["rollout_path"] != str(self.rollout_path) or row["thread_id"] != self.thread_id:
                        raise ObserverError("observer database is bound to another rollout or thread")
                    db.execute("COMMIT")
                    return

                source = self._source_stat()
                attached_at = time.time()
                if source is None:
                    cursor = 0
                    file_dev = file_ino = anchor = None
                    seen = connected = 0
                    error = "rollout unavailable"
                else:
                    cursor = 0 if self.from_start else int(source.st_size)
                    file_dev, file_ino = _identity_from_stat(source)
                    bootstrap_reads = [0]
                    anchor = self._anchor(cursor, bootstrap_reads)
                    seen = connected = 1
                    error = None
                db.execute(
                    """
                    INSERT INTO observer_state(
                        id, rollout_path, thread_id, attached_at, last_scan,
                        cursor, bytes_read, file_dev, file_ino, anchor,
                        skipping_line, seen, connected, error, fatal, model, effort
                    ) VALUES(1, ?, ?, ?, NULL, ?, 0, ?, ?, ?, 0, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        str(self.rollout_path),
                        self.thread_id,
                        attached_at,
                        cursor,
                        file_dev,
                        file_ino,
                        anchor,
                        seen,
                        connected,
                        error,
                        _UNKNOWN,
                        _UNKNOWN,
                    ),
                )
                if source is not None and bootstrap_reads[0]:
                    partial = self._partial_boundary(cursor, bootstrap_reads)
                    db.execute(
                        """UPDATE observer_state SET bytes_read=?, start_cursor=?,
                            skipping_line=?, initial_partial_line=?, coverage_complete=?,
                            error=? WHERE id=1""",
                        (bootstrap_reads[0], cursor, int(partial), int(partial),
                         int(not partial), "coverage incomplete: attached within a record" if partial else None),
                    )
                elif source is not None:
                    db.execute("UPDATE observer_state SET start_cursor=0 WHERE id=1")
                else:
                    db.execute("""UPDATE observer_state SET initial_source_missing=1,
                        coverage_complete=0 WHERE id=1""")
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    @staticmethod
    def _source_identity_changed(row, source):
        if not bool(row["seen"]):
            return False
        old = (row["file_dev"], row["file_ino"])
        new = _identity_from_stat(source)
        return old != new

    def _validate_anchor(self, row, read_counter=None):
        if row["anchor"] is None:
            return
        if self._anchor(int(row["cursor"]), read_counter) != row["anchor"]:
            raise ObserverError("rollout source replaced")

    def _parse_context(self, record):
        payload = record.get("payload")
        if not isinstance(payload, dict):
            return None
        source_thread = payload.get("thread_id")
        if source_thread is not None and source_thread != self.thread_id:
            return None
        turn_id = payload.get("turn_id")
        if type(turn_id) is not str or not turn_id or "\x00" in turn_id:
            return None
        return {
            "turn_id": _text(turn_id, "turn id"),
            "thread_id": self.thread_id if source_thread == self.thread_id else None,
            "model": _metadata(payload.get("model")),
            "effort": _metadata(payload.get("effort")),
        }

    def _parse_usage(self, record):
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("thread_id") != self.thread_id:
            return None
        thread_id = _text(payload.get("thread_id"), "thread id")
        turn_id = _text(payload.get("turn_id"), "turn id")
        response_id = _text(payload.get("response_id"), "response id")
        usage = payload.get("usage")
        if not isinstance(usage, dict) or set(usage) != set(_USAGE_KEYS):
            raise ObserverError("invalid token usage record")
        values = {}
        for key in _USAGE_KEYS:
            value = usage.get(key)
            if type(value) is not int or value < 0:
                raise ObserverError("invalid token usage counters")
            values[key] = value
        if values["cached_input_tokens"] + values["cache_write_input_tokens"] > values["input_tokens"]:
            raise ObserverError("invalid token usage counters")
        if values["reasoning_output_tokens"] > values["output_tokens"]:
            raise ObserverError("invalid token usage counters")
        if values["total_tokens"] != values["input_tokens"] + values["output_tokens"]:
            raise ObserverError("invalid token usage counters")
        return {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "response_id": response_id,
            "timestamp": _timestamp(record.get("timestamp")),
            "usage": values,
        }

    def _parse_line(self, raw):
        exact_raw = raw
        raw = raw.rstrip(b"\r\n")
        if not raw:
            return "ignore", None
        try:
            record = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError):
            return "malformed", None
        if not isinstance(record, dict):
            return "ignore", None
        record_type = record.get("type")
        if record_type == "turn_context":
            return "context", self._parse_context(record)
        if record_type == "token_usage_record":
            return "usage", self._parse_usage(record)
        if record_type == 'response_item' and self.capture_statements:
            message = record.get('payload')
            if (isinstance(message, dict) and message.get('type') == 'message'
                    and message.get('role') == 'assistant'
                    and message.get('phase') in ('commentary', 'final_answer')):
                message_id = message.get('id')
                try:
                    _text(message_id, 'statement id')
                except (ObserverError, UnicodeError):
                    return 'malformed', None
                return 'statement', {'source_bytes': len(exact_raw),
                    'source_sha256': hashlib.sha256(exact_raw).hexdigest(),
                    'message_id': message_id, 'phase': message['phase']}
        # event_msg and every other native record are intentionally ignored;
        # in particular, their cumulative token counters are never summed.
        return "ignore", None

    def _read_incremental(self, cursor, skipping_line, read_counter=None):
        contexts = []
        records = []
        statements = []
        malformed = 0
        skipped_lines = 0
        consumed = 0
        committed = cursor
        line = bytearray()
        oversized = bool(skipping_line)
        try:
            with self.rollout_path.open("rb") as stream:
                stream.seek(cursor)
                while consumed < _CONTENT_BUDGET:
                    chunk = stream.read(min(_READ_CHUNK_BYTES, _CONTENT_BUDGET - consumed))
                    if not chunk:
                        break
                    chunk_start = cursor + consumed
                    consumed += len(chunk)
                    if read_counter is not None:
                        read_counter[0] += len(chunk)
                    position = 0
                    while position < len(chunk):
                        newline = chunk.find(b"\n", position)
                        end = len(chunk) if newline < 0 else newline + 1
                        piece = chunk[position:end]
                        absolute_end = chunk_start + end
                        has_newline = newline >= 0
                        if oversized:
                            if has_newline:
                                committed = absolute_end
                                oversized = False
                            else:
                                committed = absolute_end
                        elif len(line) + len(piece) > MAX_LINE_BYTES:
                            skipped_lines += 1
                            line.clear()
                            oversized = True
                            if has_newline:
                                committed = absolute_end
                                oversized = False
                            else:
                                committed = absolute_end
                        else:
                            line.extend(piece)
                            if has_newline:
                                committed = absolute_end
                                kind, parsed = self._parse_line(bytes(line))
                                if kind == "context" and parsed is not None:
                                    contexts.append(parsed)
                                elif kind == "usage" and parsed is not None:
                                    records.append(parsed)
                                elif kind == "malformed":
                                    malformed += 1
                                elif kind == 'statement':
                                    statements.append({**parsed, 'source_offset': absolute_end - len(line)})
                                line.clear()
                        position = end
        except OSError as exc:
            raise ObserverError("rollout source unavailable") from exc
        return {
            "contexts": contexts,
            "records": records,
            "statements": statements,
            "malformed": malformed,
            "skipped_lines": skipped_lines,
            "consumed": consumed,
            "cursor": committed,
            "skipping_line": oversized,
        }

    @staticmethod
    def _context_row(db, turn_id):
        return db.execute(
            "SELECT model, effort FROM turn_contexts WHERE turn_id=?",
            (turn_id,),
        ).fetchone()

    def _apply(self, db, parsed, row):
        for statement in parsed.get('statements', []):
            names = ('source_offset', 'source_bytes', 'source_sha256', 'message_id', 'phase')
            old = db.execute('SELECT * FROM statement_outbox WHERE source_offset=?',
                             (statement['source_offset'],)).fetchone()
            if old and any(old[key] != statement[key] for key in names):
                raise ObserverError('Statement source binding conflict')
            db.execute('INSERT OR IGNORE INTO statement_outbox(' + ','.join(names) + ') VALUES(?,?,?,?,?)',
                       tuple(statement[key] for key in names))
        current_model = row["model"]
        current_effort = row["effort"]
        for context in parsed["contexts"]:
            old = db.execute(
                "SELECT thread_id, model, effort FROM turn_contexts WHERE turn_id=?",
                (context["turn_id"],),
            ).fetchone()
            if old is None:
                model = context["model"]
                effort = context["effort"]
                db.execute(
                    "INSERT INTO turn_contexts(turn_id, thread_id, model, effort) VALUES(?, ?, ?, ?)",
                    (context["turn_id"], context["thread_id"], model, effort),
                )
            else:
                model = context["model"] if context["model"] != _UNKNOWN else old["model"]
                effort = context["effort"] if context["effort"] != _UNKNOWN else old["effort"]
                db.execute(
                    "UPDATE turn_contexts SET thread_id=?, model=?, effort=? WHERE turn_id=?",
                    (
                        context["thread_id"] or old["thread_id"],
                        model,
                        effort,
                        context["turn_id"],
                    ),
                )
            if model != _UNKNOWN:
                current_model = model
            if effort != _UNKNOWN:
                current_effort = effort
            db.execute(
                """
                UPDATE usage_records SET model=?, effort=?
                WHERE thread_id=? AND turn_id=?
                """,
                (model, effort, self.thread_id, context["turn_id"]),
            )

        for record in parsed["records"]:
            context = self._context_row(db, record["turn_id"])
            model = context["model"] if context is not None else _UNKNOWN
            effort = context["effort"] if context is not None else _UNKNOWN
            usage = record["usage"]
            old = db.execute(
                """
                SELECT thread_id, turn_id, event_timestamp, input_tokens,
                       cached_input_tokens, cache_write_input_tokens,
                       output_tokens, reasoning_output_tokens, total_tokens
                FROM usage_records WHERE response_id=?
                """,
                (record["response_id"],),
            ).fetchone()
            if old is not None:
                same = (
                    old["thread_id"] == record["thread_id"]
                    and old["turn_id"] == record["turn_id"]
                    and old["event_timestamp"] == _timestamp_json(record["timestamp"])
                    and all(old[key] == usage[key] for key in _USAGE_KEYS)
                )
                if not same:
                    raise ObserverError("conflicting response_id")
                # An earlier scan may have seen the receipt before its
                # turn_context.  Refresh only whitelisted derived metadata.
                db.execute(
                    "UPDATE usage_records SET model=?, effort=? WHERE response_id=?",
                    (model, effort, record["response_id"]),
                )
                if model != _UNKNOWN:
                    current_model = model
                if effort != _UNKNOWN:
                    current_effort = effort
                continue
            db.execute(
                """
                INSERT INTO usage_records(
                    response_id, thread_id, turn_id, event_timestamp,
                    model, effort, input_tokens, cached_input_tokens,
                    cache_write_input_tokens, output_tokens,
                    reasoning_output_tokens, total_tokens
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["response_id"],
                    record["thread_id"],
                    record["turn_id"],
                    _timestamp_json(record["timestamp"]),
                    model,
                    effort,
                    usage["input_tokens"],
                    usage["cached_input_tokens"],
                    usage["cache_write_input_tokens"],
                    usage["output_tokens"],
                    usage["reasoning_output_tokens"],
                    usage["total_tokens"],
                ),
            )
            if model != _UNKNOWN:
                current_model = model
            if effort != _UNKNOWN:
                current_effort = effort
        return current_model, current_effort

    def _mark_error(self, message, *, read_bytes=0, fatal=True):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute(
                    """
                    UPDATE observer_state SET connected=0, error=?, fatal=?,
                        bytes_read=bytes_read+?, last_scan=? WHERE id=1
                    """,
                    (message, int(fatal), read_bytes, time.time()),
                )
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def scan(self):
        """Consume at most one bounded suffix and return :meth:`snapshot`.

        A partial ordinary line remains at its original cursor until its
        newline arrives.  Once a line exceeds :data:`MAX_LINE_BYTES`, it is
        discarded incrementally and never decoded as one large object.
        """

        with self._lock:
            read_counter = [0]
            try:
                with self._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    try:
                        row = db.execute("SELECT * FROM observer_state WHERE id=1").fetchone()
                        if row is None:
                            raise ObserverError("observer state is missing")
                        if row["fatal"]:
                            raise ObserverError(row["error"] or "observer halted")
                        now = time.time()
                        source = self._source_stat()
                        if source is None:
                            db.execute(
                                "UPDATE observer_state SET connected=0, error=?, last_scan=? WHERE id=1",
                                ("rollout unavailable", now),
                            )
                            db.execute("COMMIT")
                            return self.snapshot()
                        if self._source_identity_changed(row, source):
                            raise ObserverError("rollout source replaced")
                        if int(source.st_size) < int(row["cursor"]):
                            raise ObserverError("rollout source truncated")
                        if not row["seen"]:
                            cursor = int(source.st_size)
                            anchor = self._anchor(cursor, read_counter)
                            partial = self._partial_boundary(cursor, read_counter)
                            file_dev, file_ino = _identity_from_stat(source)
                            db.execute(
                                """
                                UPDATE observer_state SET connected=1,
                                    fatal=0, seen=1, cursor=?, file_dev=?, file_ino=?,
                                    anchor=?, bytes_read=bytes_read+?, last_scan=?,
                                    start_cursor=?, skipping_line=?, initial_partial_line=?,
                                    coverage_complete=?, error=? WHERE id=1
                                """,
                                (cursor, file_dev, file_ino, anchor, read_counter[0], now,
                                 cursor, int(partial), int(partial), 0,
                                 "coverage incomplete: source unavailable at attachment"),
                            )
                            db.execute("COMMIT")
                            return self.snapshot()

                        self._validate_anchor(row, read_counter)
                        parsed = self._read_incremental(
                            int(row["cursor"]), bool(row["skipping_line"]), read_counter
                        )
                        after = self._source_stat()
                        if after is None:
                            raise ObserverError("rollout unavailable")
                        if _identity_from_stat(after) != _identity_from_stat(source):
                            raise ObserverError("rollout source replaced")
                        if int(after.st_size) < int(parsed["cursor"]):
                            raise ObserverError("rollout source truncated")
                        # Recheck the old anchor after the read to avoid
                        # committing bytes from an in-place replacement.
                        self._validate_anchor(row, read_counter)
                        new_anchor = row["anchor"]
                        if parsed["cursor"] != int(row["cursor"]):
                            new_anchor = self._anchor(parsed["cursor"], read_counter)
                        model, effort = self._apply(db, parsed, row)
                        coverage_incomplete = (
                            not bool(row["coverage_complete"]) or parsed["skipped_lines"] > 0
                            or parsed["malformed"] > 0
                        )
                        gaps = []
                        if row["start_cursor"] is None:
                            gaps.append("attachment boundary unknown")
                        if row["initial_partial_line"]:
                            gaps.append("attached within a record")
                        if row["initial_source_missing"]:
                            gaps.append("source unavailable at attachment")
                        if row["skipped_oversized_lines"] + parsed["skipped_lines"]:
                            gaps.append("oversized rollout line skipped")
                        if row["malformed_lines"] + parsed["malformed"]:
                            gaps.append("malformed rollout line skipped")
                        error = "coverage incomplete: " + "; ".join(gaps or ["prior gap"]) if coverage_incomplete else None
                        db.execute(
                            """
                            UPDATE observer_state SET connected=1, error=?, fatal=0,
                                last_scan=?, cursor=?, bytes_read=bytes_read+?,
                                file_dev=?, file_ino=?, anchor=?, skipping_line=?,
                                seen=1, coverage_complete=?,
                                skipped_oversized_lines=skipped_oversized_lines+?,
                                malformed_lines=malformed_lines+?,
                                model=?, effort=? WHERE id=1
                            """,
                            (
                                error,
                                now,
                                parsed["cursor"],
                                read_counter[0],
                                int(after.st_dev),
                                int(after.st_ino),
                                new_anchor,
                                int(parsed["skipping_line"]),
                                int(not coverage_incomplete),
                                parsed["skipped_lines"],
                                parsed["malformed"],
                                model,
                                effort,
                            ),
                        )
                        db.execute("COMMIT")
                    except BaseException:
                        db.execute("ROLLBACK")
                        raise
            except ObserverError as exc:
                message = str(exc)
                if message != "observer state is missing":
                    self._mark_error(
                        message,
                        read_bytes=read_counter[0],
                        fatal=message != "rollout unavailable",
                    )
                raise
            except (OSError, sqlite3.Error) as exc:
                # Storage failures are visible and do not move the source
                # cursor.  Keep the error bounded and free of rollout text.
                with self._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    try:
                        db.execute(
                            "UPDATE observer_state SET connected=0, error=?, last_scan=? WHERE id=1",
                            ("observer storage failure", time.time()),
                        )
                        db.execute("COMMIT")
                    except BaseException:
                        db.execute("ROLLBACK")
                        raise
                raise ObserverError("observer storage failure") from exc
            return self.snapshot()

    def snapshot(self):
        """Return the durable, metadata-only observer projection."""

        with self._lock, self._db() as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            try:
                row = db.execute("SELECT * FROM observer_state WHERE id=1").fetchone()
                if row is None:
                    raise ObserverError("observer state is missing")
                totals = db.execute(
                    """
                    SELECT COUNT(*) AS response_count,
                        COALESCE(SUM(input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                        COALESCE(SUM(cache_write_input_tokens), 0) AS cache_write_input_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
                        COALESCE(SUM(total_tokens), 0) AS total_tokens
                    FROM usage_records WHERE thread_id=?
                    """,
                    (self.thread_id,),
                ).fetchone()
                recent = []
                for item in db.execute(
                    """
                    SELECT event_timestamp, response_id, model,
                        input_tokens, cached_input_tokens, cache_write_input_tokens,
                        output_tokens, reasoning_output_tokens, total_tokens
                    FROM usage_records WHERE thread_id=? ORDER BY id DESC LIMIT ?
                    """,
                    (self.thread_id, RECENT_LIMIT),
                ):
                    recent.append(
                        {
                            "timestamp": json.loads(item["event_timestamp"])
                            if item["event_timestamp"] is not None
                            else None,
                            "response_id": item["response_id"],
                            "model": item["model"],
                            "usage": {key: item[key] for key in _USAGE_KEYS},
                        }
                    )
                result = {
                    "connected": bool(row["connected"]),
                    "last_scan": row["last_scan"],
                    "bytes_read": int(row["bytes_read"]),
                    "error": row["error"],
                    "model": row["model"],
                    "effort": row["effort"],
                    "thread_id": row["thread_id"],
                    "usage": {
                        key: int(totals[key])
                        for key in _USAGE_KEYS
                    },
                    "response_count": int(totals["response_count"]),
                    "attached_at": row["attached_at"],
                    "recent": recent,
                    "cursor": int(row["cursor"]),
                    "coverage_complete": bool(row["coverage_complete"]),
                    "skipped_oversized_lines": int(row["skipped_oversized_lines"]),
                    "malformed_lines": int(row["malformed_lines"]),
                    "start_cursor": row["start_cursor"],
                    "initial_partial_line": bool(row["initial_partial_line"]),
                    "initial_source_missing": bool(row["initial_source_missing"]),
                }
                db.execute("COMMIT")
                return result
            except BaseException:
                db.execute("ROLLBACK")
                raise


__all__ = [
    "ChatObserver",
    "MAX_LINE_BYTES",
    "MAX_SCAN_BYTES",
    "ObserverError",
]
