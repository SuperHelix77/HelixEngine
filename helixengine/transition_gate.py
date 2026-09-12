"""Exact prompt transition gate with optional caller-bound materialization.

This module records already-captured native prompts against an immutable grant.
The recording decision has no semantic classifier or model call. The separate
materialize_recording helper performs only explicitly granted exact file work;
the native controller owns its completion/failure fence. The caller owns the expected completion-ledger head; the
mutable ledger index is used only by ``CompletionLedger.ingest`` for its
idempotent publication protocol.
"""

import hashlib
import json
import os
import re
from pathlib import Path

from .core.completion_ledger import CompletionLedger, EMPTY
from .prompt_memory import (
    AUTHORITY as CAPTURE_AUTHORITY,
    EVENT_NAME,
    MAX_PROMPT_BYTES,
    _event_id,
)


GRANT_SCHEMA = "helix.transition.grant.v1"
RECORD_SCHEMA = "helix.transition.record.v1"
MAX_STEPS = 256
MAX_DEPENDENCIES = 256
MAX_NOTIFICATION_CHARS = 512
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_GRANT_COMMON_FIELDS = {
    "schema",
    "project",
    "thread_id",
    "epoch",
    "authorization_ref",
    "unresolved_obligations",
    "dependencies",
}
_GRANT_MODES = ({"steps"}, {"recording"}, {"recording", "materialization"})
_CAPTURE_FIELDS = {
    "agent_id",
    "authority",
    "event",
    "project",
    "prompt",
    "prompt_bytes",
    "prompt_sha256",
    "root_session_id",
    "schema",
    "session_id",
    "thread_id",
    "turn_id",
}
_RECORD_BASE_FIELDS = {
    "schema",
    "state",
    "action",
    "grant_hash",
    "project",
    "thread_id",
    "session_id",
    "agent_id",
    "turn_id",
    "native_event_id",
    "ordinal",
    "capture_record",
    "prompt_sha256",
    "prompt_bytes",
}
_RECORDING_ROW_FIELDS = _RECORD_BASE_FIELDS | {
    "epoch",
    "sequence",
    "payload_sha256",
    "payload_bytes",
    "notification",
}


def _encode(value):
    """Encode one deterministic UTF-8 JSON object."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _is_digest(value):
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _text(value, label, *, empty=False):
    if not isinstance(value, str) or (not empty and not value) or "\x00" in value:
        raise ValueError(f"Invalid {label}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"Invalid {label}") from exc
    return value


def _utf8_text(value, label, *, empty=False):
    if not isinstance(value, str) or (not empty and not value):
        raise ValueError(f"Invalid {label}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"Invalid {label}") from exc
    return value


def _optional_text(value, label):
    if value is not None:
        _text(value, label)
    return value


def _digest(value, label):
    if not _is_digest(value):
        raise ValueError(f"Invalid {label}")
    return value


def _dependency_digest(path):
    """Read one declared regular file and return its current SHA-256."""

    candidate = Path(path)
    if not candidate.is_absolute() or candidate.is_symlink() or not candidate.is_file():
        raise ValueError("Dependency source unavailable")
    try:
        before = candidate.stat()
        data = candidate.read_bytes()
        after = candidate.stat()
    except OSError as exc:
        raise ValueError("Dependency source unavailable") from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
    ):
        raise ValueError("Dependency changed during read")
    return hashlib.sha256(data).hexdigest()


def _validate_grant(memory, grant, *, stored=False):
    """Validate a grant and return the canonical object without mutating input."""

    if not isinstance(grant, dict):
        raise ValueError("Grant object required")
    keys = set(grant)
    if not stored and "schema" not in keys:
        grant = {"schema": GRANT_SCHEMA, **grant}
        keys = set(grant)
    if grant.get("schema") != GRANT_SCHEMA:
        raise ValueError("Invalid grant schema")
    mode_fields = keys - _GRANT_COMMON_FIELDS
    if mode_fields not in _GRANT_MODES or not _GRANT_COMMON_FIELDS <= keys:
        raise ValueError("Grant modes are exclusive")

    obligations = grant["unresolved_obligations"]
    if type(obligations) is not list or obligations != []:
        raise ValueError("unresolved_obligations must be exactly empty")

    _text(grant["project"], "grant project")
    _text(grant["thread_id"], "grant thread_id")
    if type(grant["epoch"]) is not int or grant["epoch"] < 0:
        raise ValueError("Invalid grant epoch")

    authorization_ref = _digest(grant["authorization_ref"], "authorization_ref")
    try:
        # The bytes are evidence only.  Never parse or interpret them.
        memory.store.get(authorization_ref)
    except Exception as exc:
        raise ValueError("Authorization evidence unavailable") from exc

    if "steps" in grant:
        steps = grant["steps"]
        if not isinstance(steps, list) or len(steps) > MAX_STEPS:
            raise ValueError("Invalid grant steps")
        for step in steps:
            if not isinstance(step, dict) or set(step) != {
                "prompt_sha256",
                "prompt_bytes",
                "notification",
            }:
                raise ValueError("Invalid grant step")
            _digest(step["prompt_sha256"], "step prompt_sha256")
            if (
                type(step["prompt_bytes"]) is not int
                or step["prompt_bytes"] < 0
                or step["prompt_bytes"] > MAX_PROMPT_BYTES
            ):
                raise ValueError("Invalid step prompt_bytes")
            notification = _text(step["notification"], "step notification", empty=True)
            if len(notification) > MAX_NOTIFICATION_CHARS:
                raise ValueError("Step notification is too long")
    else:
        recording = grant["recording"]
        if not isinstance(recording, dict) or set(recording) != {
            "max_events",
            "max_payload_bytes",
            "notification",
        }:
            raise ValueError("Invalid recording lease")
        if (
            type(recording["max_events"]) is not int
            or not 1 <= recording["max_events"] <= MAX_STEPS
        ):
            raise ValueError("Invalid recording max_events")
        if (
            type(recording["max_payload_bytes"]) is not int
            or not 0 <= recording["max_payload_bytes"] <= MAX_PROMPT_BYTES
        ):
            raise ValueError("Invalid recording max_payload_bytes")
        notification = _text(recording["notification"], "recording notification", empty=True)
        if len(notification) > MAX_NOTIFICATION_CHARS:
            raise ValueError("Recording notification is too long")

    dependencies = grant["dependencies"]
    if not isinstance(dependencies, list) or len(dependencies) > MAX_DEPENDENCIES:
        raise ValueError("Invalid grant dependencies")
    seen_paths = set()
    for dependency in dependencies:
        if not isinstance(dependency, dict) or set(dependency) != {"path", "sha256"}:
            raise ValueError("Invalid dependency")
        path = _text(dependency["path"], "dependency path")
        if not os.path.isabs(path) or path in seen_paths:
            raise ValueError("Invalid dependency path")
        seen_paths.add(path)
        expected = _digest(dependency["sha256"], "dependency sha256")
        if _dependency_digest(path) != expected:
            raise ValueError("Dependency hash mismatch")

    if "materialization" in grant:
        target = grant["materialization"]
        if not isinstance(target, dict) or set(target) != {
            "path", "initial_sha256", "initial_bytes", "format", "write_authority"
        }:
            raise ValueError("Invalid materialization binding")
        if target["format"] != "exact-prompt-append-v1" or target["write_authority"] != "exclusive":
            raise ValueError("Explicit exclusive exact-append authority required")
        path = Path(_text(target["path"], "materialization path"))
        project = Path(grant["project"])
        if not path.is_absolute() or not project.is_absolute() or ".." in path.parts:
            raise ValueError("Absolute project-bound materialization path required")
        if not path.is_relative_to(project) or path == project or str(path) in seen_paths:
            raise ValueError("Materialization must be inside project and separate from dependencies")
        _digest(target["initial_sha256"], "materialization initial root")
        if type(target["initial_bytes"]) is not int or not 0 <= target["initial_bytes"] <= 1024 * 1024:
            raise ValueError("Materialization initial bytes exceed bound")
        initial = memory.store.get(target["initial_sha256"])
        if len(initial) != target["initial_bytes"]:
            raise ValueError("Materialization initial source mismatch")
        if not stored:
            from .recording_artifact import verify
            try:
                verify(str(path), initial)
            except Exception as exc:
                raise ValueError("Materialization initial file cannot be verified") from exc

    return grant


def _steps(grant):
    return grant.get("steps", [])


def _recording(grant):
    return grant.get("recording")


def arm(memory, grant):
    """Validate and persist one immutable grant, returning its CAS hash."""

    normalized = _validate_grant(memory, grant)
    return memory.store.put(_encode(normalized))["sha256"]


def _read_grant(memory, grant_hash):
    _digest(grant_hash, "grant hash")
    raw = memory.store.get(grant_hash)
    try:
        grant = json.loads(raw)
    except (TypeError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid grant encoding") from exc
    if _encode(grant) != raw:
        raise ValueError("Grant is not canonical")
    return _validate_grant(memory, grant, stored=True)


def _capture_body(memory, project, record_hash, thread_id):
    """Recover and verify an exact prompt-memory record."""

    _digest(record_hash, "capture record")
    records = memory.retrieve(project, [record_hash])
    if len(records) != 1:
        raise ValueError("Capture record unavailable")
    reference = records[0]
    raw = reference["raw"]
    try:
        body = json.loads(raw)
    except (TypeError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid capture encoding") from exc
    if _encode(body) != raw or not isinstance(body, dict) or set(body) != _CAPTURE_FIELDS:
        raise ValueError("Capture is not canonical")
    if body["schema"] != "helix.prompt.capture.v1":
        raise ValueError("Invalid capture schema")
    if body["authority"] != CAPTURE_AUTHORITY or body["event"] != EVENT_NAME:
        raise ValueError("Invalid capture authority")
    if body["project"] != project or body["thread_id"] != thread_id:
        raise ValueError("Capture project or thread mismatch")
    _text(body["project"], "capture project")
    _text(body["session_id"], "capture session_id")
    _optional_text(body["agent_id"], "capture agent_id")
    _text(body["thread_id"], "capture thread_id")
    _text(body["turn_id"], "capture turn_id")
    if body["root_session_id"] != body["session_id"]:
        raise ValueError("Capture session provenance mismatch")
    if body["thread_id"] != (body["agent_id"] or body["session_id"]):
        raise ValueError("Capture native thread mismatch")
    prompt = body["prompt"]
    _utf8_text(prompt, "capture prompt", empty=True)
    prompt_bytes = prompt.encode("utf-8")
    if (
        type(body["prompt_bytes"]) is not int
        or body["prompt_bytes"] != len(prompt_bytes)
        or body["prompt_bytes"] > MAX_PROMPT_BYTES
    ):
        raise ValueError("Capture prompt size mismatch")
    prompt_hash = hashlib.sha256(prompt_bytes).hexdigest()
    if body["prompt_sha256"] != prompt_hash:
        raise ValueError("Capture prompt hash mismatch")
    if reference["record_hash"] != record_hash:
        raise ValueError("Capture record mismatch")
    if reference["project"] != project or reference["session"] != thread_id:
        raise ValueError("Memory reference identity mismatch")
    if type(reference["bytes"]) is not int or reference["bytes"] != len(raw):
        raise ValueError("Capture record size mismatch")
    expected_event = _event_id(body["session_id"], body["agent_id"], body["turn_id"])
    if reference["event_id"] != expected_event:
        raise ValueError("Capture native identity mismatch")
    return {
        "record_hash": record_hash,
        "source_hash": reference["source_hash"],
        "bytes": reference["bytes"],
        "project": body["project"],
        "thread_id": body["thread_id"],
        "session_id": body["session_id"],
        "agent_id": body["agent_id"],
        "turn_id": body["turn_id"],
        "native_event_id": expected_event,
        "prompt_sha256": body["prompt_sha256"],
        "prompt_bytes": body["prompt_bytes"],
        "prompt": prompt,
    }


def _capture_from_receipt(memory, grant, receipt):
    if not isinstance(receipt, dict):
        raise ValueError("Capture receipt required")
    if receipt.get("schema") != "helix.prompt.capture.receipt.v1":
        raise ValueError("Invalid capture receipt schema")
    if (
        receipt.get("status") != "captured"
        or type(receipt.get("coverage")) is not bool
        or receipt["coverage"] is not True
        or type(receipt.get("captured")) is not bool
        or receipt["captured"] is not True
        or receipt.get("error") is not None
    ):
        raise ValueError("Capture is incomplete")
    if receipt.get("project") != grant["project"]:
        raise ValueError("Capture project mismatch")
    if receipt.get("thread_id") != grant["thread_id"]:
        raise ValueError("Capture thread mismatch")
    if receipt.get("event") != EVENT_NAME or receipt.get("authority") != CAPTURE_AUTHORITY:
        raise ValueError("Invalid capture receipt provenance")
    record_hash = _digest(receipt.get("record_hash"), "capture record")
    if type(receipt.get("prompt_bytes")) is not int or type(receipt.get("bytes")) is not int:
        raise ValueError("Invalid capture receipt sizes")
    _digest(receipt.get("prompt_sha256"), "capture prompt hash")
    _digest(receipt.get("source_hash"), "capture source hash")
    capture = _capture_body(memory, grant["project"], record_hash, grant["thread_id"])
    for key in (
        "project",
        "thread_id",
        "session_id",
        "agent_id",
        "turn_id",
        "event_id",
        "prompt_sha256",
        "prompt_bytes",
        "source_hash",
        "bytes",
    ):
        if key == "event_id":
            expected = capture["native_event_id"]
        elif key in capture:
            expected = capture[key]
        else:
            continue
        if receipt.get(key) != expected:
            raise ValueError(f"Capture receipt {key} mismatch")
    return capture


def _strict_observation(prompt):
    """Parse the explicitly armed four-field observation envelope.

    ``json.loads`` is tightened with duplicate-key and nonfinite-number
    rejection.  The resulting payload is data only; this function never
    interprets its text.
    """

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate observation key")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError("Nonfinite observation number")

    try:
        envelope = json.loads(
            prompt,
            object_pairs_hook=pairs,
            parse_constant=nonfinite,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid observation envelope") from exc
    if not isinstance(envelope, dict) or set(envelope) != {
        "schema",
        "epoch",
        "sequence",
        "payload",
    }:
        raise ValueError("Invalid observation fields")
    if envelope["schema"] != "helix.observation.v1":
        raise ValueError("Invalid observation schema")
    if type(envelope["epoch"]) is not int:
        raise ValueError("Invalid observation epoch")
    if type(envelope["sequence"]) is not int:
        raise ValueError("Invalid observation sequence")
    _utf8_text(envelope["payload"], "observation payload", empty=True)
    payload_bytes = envelope["payload"].encode("utf-8")
    return {
        "schema": envelope["schema"],
        "epoch": envelope["epoch"],
        "sequence": envelope["sequence"],
        "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "payload_bytes": len(payload_bytes),
    }


def _ledger_scope(grant_hash):
    return "helix.transition:" + grant_hash


def _ledger_event(grant_hash, native_event_id):
    return grant_hash + ":" + native_event_id


def _record_body(
    grant_hash,
    capture,
    ordinal,
    *,
    action,
    state,
    notification=None,
    reason=None,
    observation=None,
):
    body = {
        "schema": RECORD_SCHEMA,
        "state": state,
        "action": action,
        "grant_hash": grant_hash,
        "project": capture["project"],
        "thread_id": capture["thread_id"],
        "session_id": capture["session_id"],
        "agent_id": capture["agent_id"],
        "turn_id": capture["turn_id"],
        "native_event_id": capture["native_event_id"],
        "ordinal": ordinal,
        "capture_record": capture["record_hash"],
        "prompt_sha256": capture["prompt_sha256"],
        "prompt_bytes": capture["prompt_bytes"],
    }
    if action == "record":
        body["notification"] = notification
        if observation is not None:
            body.update(
                epoch=observation["epoch"],
                sequence=observation["sequence"],
                payload_sha256=observation["payload_sha256"],
                payload_bytes=observation["payload_bytes"],
            )
    else:
        body["reason"] = reason
    return body


def _validate_history_row(memory, grant, grant_hash, entry, expected_ordinal):
    raw = entry["raw"]
    try:
        body = json.loads(raw)
    except (TypeError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid transition record encoding") from exc
    if _encode(body) != raw or not isinstance(body, dict):
        raise ValueError("Transition record is not canonical")
    action = body.get("action")
    recording = _recording(grant)
    if action == "record":
        expected_fields = (
            _RECORDING_ROW_FIELDS if recording else _RECORD_BASE_FIELDS | {"notification"}
        )
        if set(body) != expected_fields:
            raise ValueError("Invalid record fields")
        if body.get("state") != "RECORDED":
            raise ValueError("Invalid recorded state")
        notification = _text(body["notification"], "record notification", empty=True)
        if len(notification) > MAX_NOTIFICATION_CHARS:
            raise ValueError("Record notification is too long")
        if recording:
            if (
                type(body["epoch"]) is not int
                or type(body["sequence"]) is not int
                or body["epoch"] != grant["epoch"]
                or body["sequence"] != expected_ordinal
            ):
                raise ValueError("Recording epoch or sequence mismatch")
            _digest(body["payload_sha256"], "record payload hash")
            if (
                type(body["payload_bytes"]) is not int
                or body["payload_bytes"] < 0
                or body["payload_bytes"] > recording["max_payload_bytes"]
            ):
                raise ValueError("Invalid record payload size")
            if notification != recording["notification"]:
                raise ValueError("Recording notification mismatch")
    elif action == "invalidate":
        if set(body) != _RECORD_BASE_FIELDS | {"reason"}:
            raise ValueError("Invalid invalidation fields")
        expected_reason = "invalid_observation" if recording else "unrecognized_prompt"
        if body.get("state") != "INVALIDATED" or body.get("reason") != expected_reason:
            raise ValueError("Invalid invalidation state")
        notification = None
    else:
        raise ValueError("Invalid transition action")
    if body.get("schema") != RECORD_SCHEMA or body.get("grant_hash") != grant_hash:
        raise ValueError("Transition grant binding mismatch")
    if body.get("project") != grant["project"] or body.get("thread_id") != grant["thread_id"]:
        raise ValueError("Transition scope binding mismatch")
    if type(body.get("ordinal")) is not int or body["ordinal"] != expected_ordinal:
        raise ValueError("Transition ordinal mismatch")
    _text(body["session_id"], "record session_id")
    _optional_text(body["agent_id"], "record agent_id")
    _text(body["turn_id"], "record turn_id")
    _text(body["native_event_id"], "record native_event_id")
    if body["native_event_id"] != _event_id(
        body["session_id"], body["agent_id"], body["turn_id"]
    ):
        raise ValueError("Transition native identity mismatch")
    record_hash = _digest(body["capture_record"], "transition capture record")
    _digest(body["prompt_sha256"], "transition prompt hash")
    if type(body["prompt_bytes"]) is not int or body["prompt_bytes"] < 0:
        raise ValueError("Invalid transition prompt size")
    capture = _capture_body(memory, grant["project"], record_hash, grant["thread_id"])
    for key in (
        "project",
        "thread_id",
        "session_id",
        "agent_id",
        "turn_id",
        "native_event_id",
        "prompt_sha256",
        "prompt_bytes",
    ):
        if body[key] != capture[key]:
            raise ValueError("Transition capture binding mismatch")
    if action == "record":
        if recording:
            observation = _strict_observation(capture["prompt"])
            if (
                observation["epoch"] != body["epoch"]
                or observation["sequence"] != body["sequence"]
                or observation["epoch"] != grant["epoch"]
                or observation["sequence"] != expected_ordinal
                or observation["payload_sha256"] != body["payload_sha256"]
                or observation["payload_bytes"] != body["payload_bytes"]
            ):
                raise ValueError("Recording payload binding mismatch")
        else:
            steps = _steps(grant)
            step = steps[expected_ordinal - 1] if expected_ordinal <= len(steps) else None
            if step is None or (
                body["prompt_sha256"] != step["prompt_sha256"]
                or body["prompt_bytes"] != step["prompt_bytes"]
                or notification != step["notification"]
            ):
                raise ValueError("Transition step binding mismatch")
    elif expected_ordinal > (
        recording["max_events"] if recording else len(_steps(grant))
    ):
        raise ValueError("Invalidation is past grant cursor")
    if entry["event"] != _ledger_event(grant_hash, body["native_event_id"]):
        raise ValueError("Transition ledger event mismatch")
    return body, capture, notification


def _recover_history(memory, grant, grant_hash, expected_head):
    ledger = CompletionLedger(memory)
    entries = ledger.recover(_ledger_scope(grant_hash), expected_head=expected_head)
    if len(entries) > MAX_STEPS:
        raise ValueError("Transition history exceeds bound")
    rows = []
    by_native = {}
    invalidated = False
    cursor = 0
    for ordinal, entry in enumerate(entries, 1):
        if invalidated:
            raise ValueError("Transition follows terminal invalidation")
        body, capture, notification = _validate_history_row(
            memory, grant, grant_hash, entry, ordinal
        )
        native_id = body["native_event_id"]
        if native_id in by_native:
            raise ValueError("Duplicate native transition identity")
        by_native[native_id] = {
            "body": body,
            "capture": capture,
            "notification": notification,
            "receipt": entry["receipt"],
            "raw": entry["raw"],
        }
        rows.append(by_native[native_id])
        if body["action"] == "record":
            cursor += 1
        else:
            invalidated = True
    limit = grant["recording"]["max_events"] if _recording(grant) else len(_steps(grant))
    if cursor > limit:
        raise ValueError("Transition cursor exceeds grant")
    return ledger, rows, by_native, cursor, invalidated


def materialize_recording(memory, grant_hash, expected_head):
    """Complete one explicitly bound artifact from verified cold records.

    The controller calls this only after recording and while its durable
    in-flight fence is held. This is not a transaction with either database;
    any uncertain publication must disable suppression and expose recovery.
    A caller must have established exclusive write authority, not inferred a
    filename or a promise from model prose. Captured text remains data.
    """
    from .recording_artifact import publish
    grant = _read_grant(memory, grant_hash)
    target = grant.get("materialization")
    if target is None:
        raise ValueError("No bound materialization")
    _, rows, _, _, invalidated = _recover_history(memory, grant, grant_hash, expected_head)
    if invalidated or not rows:
        raise ValueError("Materialization requires valid recorded history")
    initial = memory.store.get(target["initial_sha256"])
    pieces = [entry["capture"]["prompt"].encode("utf-8") + b"\n" for entry in rows]
    before = initial + b"".join(pieces[:-1])
    after = before + pieces[-1]
    result = publish(target["path"], before, after)
    return {**result, "grant_hash": grant_hash, "transition_head": expected_head}


def _result(state, head, *, replayed=False, reason, receipt=None, notification=None, include_receipt=False, include_notification=False):
    result = {"state": state, "head": head, "replayed": bool(replayed), "reason": reason}
    if include_receipt:
        result["receipt"] = receipt
    if include_notification:
        result["notification"] = notification
    return result


def _semantic(head, reason, *, replayed=False, receipt=None):
    return _result(
        "SEMANTIC_REQUIRED",
        head,
        replayed=replayed,
        reason=reason,
        receipt=receipt,
        include_receipt=receipt is not None,
    )


def _ingest(ledger, scope, event, raw, expected_head):
    try:
        return ledger.ingest(scope, event, raw, expected_head=expected_head), None
    except ValueError as exc:
        message = str(exc).lower()
        if "conflicting" in message or "payload" in message:
            return None, "capture_conflict"
        if "stale" in message or "head" in message or "sequence" in message:
            return None, "stale_expected_head"
        if "hash mismatch" in message or "corrupt" in message or "index" in message:
            return None, "history_corrupt"
        return None, "ledger_rejected"
    except Exception:
        return None, "ledger_rejected"


def transition(memory, grant_hash, capture_receipt, expected_head):
    """Record one exact captured prompt against a grant.

    A malformed or unavailable capture returns ``SEMANTIC_REQUIRED`` and does
    not consume a step.  An otherwise valid prompt that does not match the
    current step records one terminal ``INVALIDATED`` row, allowing the native
    caller to continue its ordinary model path while refusing later grant
    steps.  No result from this function dispatches a notification or invokes a
    model.
    """

    _digest(expected_head, "expected head")
    if not _is_digest(grant_hash):
        return _semantic(expected_head, "invalid_grant")
    try:
        grant = _read_grant(memory, grant_hash)
    except Exception as exc:
        reason = "dependencies_changed" if "dependency" in str(exc).lower() else "invalid_grant"
        return _semantic(expected_head, reason)

    try:
        ledger, rows, by_native, cursor, invalidated = _recover_history(
            memory, grant, grant_hash, expected_head
        )
    except Exception:
        return _semantic(expected_head, "history_corrupt")

    try:
        capture = _capture_from_receipt(memory, grant, capture_receipt)
    except Exception:
        return _semantic(expected_head, "invalid_capture")

    prior = by_native.get(capture["native_event_id"])
    if prior is not None:
        if (
            prior["capture"]["record_hash"] != capture["record_hash"]
            or prior["capture"]["prompt_sha256"] != capture["prompt_sha256"]
            or prior["capture"]["prompt_bytes"] != capture["prompt_bytes"]
        ):
            return _semantic(expected_head, "capture_conflict")
        ingest_result, ingest_reason = _ingest(
            ledger,
            _ledger_scope(grant_hash),
            _ledger_event(grant_hash, capture["native_event_id"]),
            prior["raw"],
            expected_head,
        )
        if ingest_result is None:
            return _semantic(expected_head, ingest_reason)
        if prior["body"]["action"] == "invalidate":
            return _semantic(
                ingest_result["head"],
                "grant_invalidated",
                replayed=ingest_result["replayed"],
                receipt=ingest_result["receipt"],
            )
        return _result(
            "RECORDED",
            ingest_result["head"],
            replayed=ingest_result["replayed"],
            reason="recorded",
            receipt=ingest_result["receipt"],
            notification=prior["notification"],
            include_receipt=True,
            include_notification=True,
        )

    if invalidated:
        return _semantic(expected_head, "grant_invalidated")
    recording = _recording(grant)
    limit = recording["max_events"] if recording else len(_steps(grant))
    if cursor >= limit:
        return _semantic(expected_head, "grant_complete")

    ordinal = cursor + 1

    def invalidate(reason):
        body = _record_body(
            grant_hash,
            capture,
            ordinal,
            action="invalidate",
            state="INVALIDATED",
            reason=reason,
        )
        result, ingest_reason = _ingest(
            ledger,
            _ledger_scope(grant_hash),
            _ledger_event(grant_hash, capture["native_event_id"]),
            _encode(body),
            expected_head,
        )
        if result is None:
            return _semantic(expected_head, ingest_reason)
        return _semantic(
            result["head"],
            reason,
            replayed=result["replayed"],
            receipt=result["receipt"],
        )

    if recording:
        try:
            observation = _strict_observation(capture["prompt"])
        except Exception:
            return invalidate("invalid_observation")
        if (
            observation["epoch"] != grant["epoch"]
            or observation["sequence"] != ordinal
            or observation["payload_bytes"] > recording["max_payload_bytes"]
        ):
            return invalidate("invalid_observation")
        body = _record_body(
            grant_hash,
            capture,
            ordinal,
            action="record",
            state="RECORDED",
            notification=recording["notification"],
            observation=observation,
        )
        result, reason = _ingest(
            ledger,
            _ledger_scope(grant_hash),
            _ledger_event(grant_hash, capture["native_event_id"]),
            _encode(body),
            expected_head,
        )
        if result is None:
            return _semantic(expected_head, reason)
        return _result(
            "RECORDED",
            result["head"],
            replayed=result["replayed"],
            reason="recorded",
            receipt=result["receipt"],
            notification=recording["notification"],
            include_receipt=True,
            include_notification=True,
        )

    step = _steps(grant)[cursor]
    if (
        capture["prompt_sha256"] == step["prompt_sha256"]
        and capture["prompt_bytes"] == step["prompt_bytes"]
    ):
        body = _record_body(
            grant_hash,
            capture,
            ordinal,
            action="record",
            state="RECORDED",
            notification=step["notification"],
        )
        result, reason = _ingest(
            ledger,
            _ledger_scope(grant_hash),
            _ledger_event(grant_hash, capture["native_event_id"]),
            _encode(body),
            expected_head,
        )
        if result is None:
            return _semantic(expected_head, reason)
        return _result(
            "RECORDED",
            result["head"],
            replayed=result["replayed"],
            reason="recorded",
            receipt=result["receipt"],
            notification=step["notification"],
            include_receipt=True,
            include_notification=True,
        )

    return invalidate("unrecognized_prompt")
