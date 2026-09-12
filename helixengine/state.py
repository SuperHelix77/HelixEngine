"""Durable application state for the local Helix Engine.

The database contains operational observations only. Raw command output and
receipts live in the content-addressed evidence store; SQLite keeps the small,
queryable index and the revisioned switch.
"""

from contextlib import contextmanager
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_USAGE_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)
_RUN_STATES = {"STARTING", "RUNNING", "COMPLETED", "FAILED"}


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _identity(value, label):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"{label} must be a nonempty string")


class State:
    """SQLite-WAL state with append-only event records."""

    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "telemetry.sqlite3"
        with self.db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings(
                    id INTEGER PRIMARY KEY,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
                    revision INTEGER NOT NULL CHECK(revision >= 0)
                );
                INSERT OR IGNORE INTO settings VALUES(1, 1, 0);
                CREATE TABLE IF NOT EXISTS events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    at REAL NOT NULL,
                    kind TEXT NOT NULL,
                    run TEXT,
                    body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs(
                    id TEXT PRIMARY KEY,
                    updated REAL NOT NULL,
                    body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usages(
                    run TEXT PRIMARY KEY,
                    source_hash TEXT UNIQUE NOT NULL,
                    body TEXT NOT NULL
                );
                """
            )

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    def settings(self):
        with self.db() as db:
            row = db.execute("SELECT enabled, revision FROM settings WHERE id=1").fetchone()
        if row is None:
            raise RuntimeError("Settings row is missing")
        return {"enabled": bool(row[0]), "revision": int(row[1])}

    def switch(self, enabled, revision):
        """Compare-and-set the optimization switch.

        A stale caller receives ``ValueError`` and cannot mutate the setting.
        Active runs retain the setting copied by :meth:`begin`.
        """
        if type(enabled) is not bool or type(revision) is not int or revision < 0:
            raise ValueError("Boolean enabled and nonnegative integer revision required")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT enabled, revision FROM settings WHERE id=1").fetchone()
                if row is None:
                    raise RuntimeError("Settings row is missing")
                if int(row[1]) != revision:
                    raise ValueError("Settings changed; refresh before retrying")
                current = bool(row[0])
                if current != enabled:
                    db.execute(
                        "UPDATE settings SET enabled=?, revision=revision+1 WHERE id=1",
                        (int(enabled),),
                    )
                    self._event(
                        db,
                        "OPTIMIZATIONS_CHANGED",
                        None,
                        {"enabled": enabled, "previous_revision": revision},
                    )
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        return self.settings()

    @staticmethod
    def _validate_argv(argv):
        if (
            not isinstance(argv, list)
            or not argv
            or any(not isinstance(arg, str) or "\x00" in arg for arg in argv)
            or not argv[0]
        ):
            raise ValueError("Nonempty string argv required")
        return list(argv)

    def begin(self, argv, cwd):
        argv = self._validate_argv(argv)
        cwd = str(cwd)
        _identity(cwd, "cwd")
        run_id = uuid.uuid4().hex
        setting = self.settings()
        row = {
            "id": run_id,
            "argv": argv,
            "cwd": cwd,
            "state": "STARTING",
            "enabled": setting["enabled"],
            "settings_revision": setting["revision"],
            "started": time.time(),
            "stdout_bytes": 0,
            "stderr_bytes": 0,
        }
        self.update(row, "RUN_STARTED")
        return row

    @staticmethod
    def _event(db, kind, run, body):
        db.execute(
            "INSERT INTO events(at, kind, run, body) VALUES(?, ?, ?, ?)",
            (time.time(), kind, run, _json(body)),
        )

    def event(self, kind, body, run=None):
        """Append one bounded observation without changing a run row."""
        _identity(kind, "event kind")
        if run is not None:
            _identity(run, "run id")
        _json(body)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._event(db, kind, run, body)
                event_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                db.execute("COMMIT")
                return int(event_id)
            except BaseException:
                db.execute("ROLLBACK")
                raise

    @staticmethod
    def _write_locked(db, row):
        db.execute(
            "UPDATE runs SET updated=?, body=? WHERE id=?",
            (time.time(), _json(row), row["id"]),
        )

    @staticmethod
    def _load_row(db, run_id):
        row = db.execute("SELECT body FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown run")
        return json.loads(row[0])

    def update(self, row, kind=None):
        if not isinstance(row, dict):
            raise ValueError("Run row must be an object")
        _identity(row.get("id"), "run id")
        if row.get("state") not in _RUN_STATES:
            raise ValueError("Unknown run state")
        raw = _json(row)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute(
                    """
                    INSERT INTO runs(id, updated, body) VALUES(?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET updated=excluded.updated, body=excluded.body
                    """,
                    (row["id"], time.time(), raw),
                )
                if kind:
                    self._event(db, kind, row["id"], row)
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def mark_running(self, run_id, pid=None):
        _identity(run_id, "run id")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = self._load_row(db, run_id)
                if row["state"] == "STARTING":
                    row["state"] = "RUNNING"
                    if type(pid) is int and pid > 0:
                        row["pid"] = pid
                    self._write_locked(db, row)
                    self._event(db, "RUN_RUNNING", run_id, row)
                db.execute("COMMIT")
                return row
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def progress(self, run_id, stdout_bytes, stderr_bytes):
        _identity(run_id, "run id")
        if (
            type(stdout_bytes) is not int
            or stdout_bytes < 0
            or type(stderr_bytes) is not int
            or stderr_bytes < 0
        ):
            raise ValueError("Nonnegative byte counts required")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = self._load_row(db, run_id)
                if row["state"] in ("COMPLETED", "FAILED"):
                    db.execute("COMMIT")
                    return row
                row["stdout_bytes"] = stdout_bytes
                row["stderr_bytes"] = stderr_bytes
                row["live_observed_at"] = time.time()
                self._write_locked(db, row)
                db.execute("COMMIT")
                return row
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def finish(
        self,
        run_id,
        *,
        state,
        stdout_bytes,
        stderr_bytes,
        visible_bytes,
        elapsed_seconds,
        exit_code,
        receipt,
        reducer_status,
        packet_receipt=None,
        timed_out=False,
        interrupted=False,
        error=None,
    ):
        _identity(run_id, "run id")
        if state not in ("COMPLETED", "FAILED"):
            raise ValueError("Finished run must be COMPLETED or FAILED")
        counts = (stdout_bytes, stderr_bytes, visible_bytes)
        if any(type(value) is not int or value < 0 for value in counts):
            raise ValueError("Nonnegative byte counts required")
        if type(elapsed_seconds) not in (int, float) or elapsed_seconds < 0:
            raise ValueError("Nonnegative elapsed time required")
        if exit_code is not None and (type(exit_code) is not int or isinstance(exit_code, bool)):
            raise ValueError("Exit code must be an integer or null")
        if receipt is not None and (not isinstance(receipt, str) or not _DIGEST.fullmatch(receipt)):
            raise ValueError("Receipt must be a SHA-256 reference or null")
        if packet_receipt is not None and (
            not isinstance(packet_receipt, str) or not _DIGEST.fullmatch(packet_receipt)
        ):
            raise ValueError("Packet receipt must be a SHA-256 reference or null")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = self._load_row(db, run_id)
                row.update(
                    {
                        "state": state,
                        "stdout_bytes": stdout_bytes,
                        "stderr_bytes": stderr_bytes,
                        "visible_bytes": visible_bytes,
                        "elapsed_seconds": float(elapsed_seconds),
                        "exit_code": exit_code,
                        "receipt": receipt,
                        "reducer_status": reducer_status,
                        "timed_out": bool(timed_out),
                        "interrupted": bool(interrupted),
                        "finished": time.time(),
                    }
                )
                if packet_receipt is not None:
                    row["packet_receipt"] = packet_receipt
                if error is not None:
                    row["error"] = str(error)
                self._write_locked(db, row)
                self._event(db, "RUN_COMPLETED", run_id, row)
                db.execute("COMMIT")
                return row
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def fail_without_receipt(self, run_id, error, *, elapsed_seconds=0.0):
        """Record a launch/observer failure without retrying the child."""
        return self.finish(
            run_id,
            state="FAILED",
            stdout_bytes=0,
            stderr_bytes=0,
            visible_bytes=0,
            elapsed_seconds=elapsed_seconds,
            exit_code=None,
            receipt=None,
            reducer_status="FAILED_NO_RECEIPT",
            error=error,
        )

    def get_run(self, run_id):
        _identity(run_id, "run id")
        with self.db() as db:
            row = db.execute("SELECT body FROM runs WHERE id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row is not None else None

    @staticmethod
    def validate_usage(body):
        if not isinstance(body, dict) or not isinstance(body.get("model"), str) or not body["model"]:
            raise ValueError("Model identity required")
        for key in _USAGE_KEYS:
            if type(body.get(key)) is not int or body[key] < 0:
                raise ValueError("Nonnegative integer native counters required")
        if body["cached_input_tokens"] + body["cache_write_input_tokens"] > body["input_tokens"]:
            raise ValueError("Invalid input token subsets")
        if body["reasoning_output_tokens"] > body["output_tokens"]:
            raise ValueError("Invalid output token subset")
        return dict(body)

    def usage(self, run, source_hash, body):
        """Import counters once, accepting an exact duplicate as a replay."""
        _identity(run, "run id")
        if not isinstance(source_hash, str) or not _DIGEST.fullmatch(source_hash):
            raise ValueError("Raw receipt SHA-256 required")
        body = self.validate_usage(body)
        encoded = json.dumps(body, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if db.execute("SELECT 1 FROM runs WHERE id=?", (run,)).fetchone() is None:
                    raise ValueError("Unknown run")
                old = db.execute("SELECT source_hash, body FROM usages WHERE run=?", (run,)).fetchone()
                if old is not None:
                    if old[0] != source_hash or old[1] != encoded:
                        raise ValueError("Conflicting usage import for run")
                    result = {**body, "run": run, "source_hash": source_hash, "replayed": True}
                    db.execute("COMMIT")
                    return result
                other = db.execute("SELECT run FROM usages WHERE source_hash=?", (source_hash,)).fetchone()
                if other is not None:
                    raise ValueError("Raw receipt already bound to another run")
                db.execute(
                    "INSERT INTO usages(run, source_hash, body) VALUES(?, ?, ?)",
                    (run, source_hash, encoded),
                )
                self._event(
                    db,
                    "USAGE_IMPORTED",
                    run,
                    {**body, "run": run, "source_hash": source_hash},
                )
                db.execute("COMMIT")
                return {**body, "run": run, "source_hash": source_hash, "replayed": False}
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def storage(self):
        """Return measured application object counts/bytes when available."""
        root = self.directory / "evidence" / "objects"
        total = 0
        objects = 0
        if root.is_dir():
            for path in root.iterdir():
                if path.is_file() and not path.is_symlink() and _DIGEST.fullmatch(path.name):
                    try:
                        total += path.stat().st_size
                        objects += 1
                    except OSError:
                        continue
        return {"bytes": total, "objects": objects}

    def snapshot(self):
        with self.db() as db:
            runs = [
                json.loads(row[0])
                for row in db.execute("SELECT body FROM runs ORDER BY updated DESC LIMIT 100")
            ]
            events = [
                dict(row)
                for row in db.execute(
                    "SELECT id, at, kind, run FROM events ORDER BY id DESC LIMIT 100"
                )
            ]
            usages = []
            for row in db.execute("SELECT run, source_hash, body FROM usages ORDER BY run"):
                body = json.loads(row["body"])
                if not isinstance(body, dict):
                    raise ValueError("Stored usage body is not an object")
                # The SQLite columns are the canonical binding.  Imported
                # receipt metadata cannot replace them in a public snapshot.
                body.pop("run", None)
                body.pop("source_hash", None)
                usages.append({**body, "run": row["run"], "source_hash": row["source_hash"]})
            total = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        return {
            "settings": self.settings(),
            "runs": runs,
            "events": events,
            "usages": usages,
            "total_runs": int(total),
            "run_view_limit": 100,
            "storage": self.storage(),
        }

    def doctor(self):
        checks = {}
        try:
            with self.db() as db:
                checks["sqlite"] = db.execute("SELECT 1").fetchone()[0] == 1
                checks["wal"] = db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
            checks["directory"] = self.directory.is_dir()
            checks["evidence_directory"] = (self.directory / "evidence" / "objects").is_dir()
            checks["schema"] = True
        except (OSError, sqlite3.Error):
            checks["schema"] = False
        return {"ok": all(checks.values()), "checks": checks, "path": str(self.path)}


__all__ = ["State"]
