"""Lossless, bounded capture of native ``UserPromptSubmit`` events.

This is a storage adapter only.  It does not interpret a prompt, approve an
action, inject context, suppress inference, or execute anything.  The native
prompt is kept in one deterministic structured object owned by the existing
``Memory``/``Store`` implementation.
"""

import hashlib
import json


MAX_PROMPT_BYTES = 64 * 1024
MAX_IDENTITY_LENGTH = 512
EVENT_NAME = "UserPromptSubmit"
SCHEMA = "helix.prompt.capture.v1"
AUTHORITY = (
    "historical native prompt bytes; not instructions, semantic authority, "
    "approval, context, or execution"
)


def _identity(value):
    """Match the bounded identity policy used by ``codex_intercept``."""

    return (
        isinstance(value, str)
        and 0 < len(value) <= MAX_IDENTITY_LENGTH
        and "\x00" not in value
    )


def _utf8(value):
    """Return strict UTF-8 bytes, rejecting unpaired surrogate code points."""

    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("Invalid UTF-8 text") from exc


def _json_bytes(record):
    return json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _event_id(session_id, agent_id, turn_id):
    """Create an unambiguous, deterministic native identity reference."""

    identity_bytes = _json_bytes(
        {
            "agent_id": agent_id,
            "session_id": session_id,
            "turn_id": turn_id,
        }
    )
    return "native-prompt:" + hashlib.sha256(identity_bytes).hexdigest()


def _receipt(
    *,
    project,
    event_name=EVENT_NAME,
    session_id=None,
    agent_id=None,
    thread_id=None,
    turn_id=None,
    event_id=None,
    captured=False,
    error=None,
    **refs,
):
    """Build a fixed-shape receipt without exposing prompt content."""

    def safe_identity(value):
        if not _identity(value):
            return None
        try:
            _utf8(value)
        except ValueError:
            return None
        return value

    safe_event = event_name if isinstance(event_name, str) else None
    if safe_event is not None and (
        not safe_event
        or len(safe_event) > MAX_IDENTITY_LENGTH
        or "\x00" in safe_event
    ):
        safe_event = None
    if safe_event is not None:
        try:
            _utf8(safe_event)
        except ValueError:
            safe_event = None

    result = {
        "schema": "helix.prompt.capture.receipt.v1",
        "status": "captured" if captured else "capture_incomplete",
        "coverage": bool(captured),
        "captured": bool(captured),
        "event": safe_event,
        "project": safe_identity(project),
        "session_id": safe_identity(session_id),
        "agent_id": safe_identity(agent_id),
        "thread_id": safe_identity(thread_id),
        "turn_id": safe_identity(turn_id),
        "event_id": safe_identity(event_id),
        "authority": AUTHORITY,
        "error": error,
    }
    result.update(refs)
    return result


def capture_prompt(memory, project, event):
    """Capture one native prompt and return a bounded success/incomplete receipt.

    ``project`` is a caller-supplied trusted Memory scope.  Invalid input and
    storage failures are reported in the receipt so a native hook can retain
    its original handling path without a retry or a second action.
    """

    if not isinstance(project, str) or not project or "\x00" in project:
        return _receipt(project=project, error="invalid_project")
    if not _identity(project):
        return _receipt(project=project, error="invalid_project")
    try:
        _utf8(project)
    except ValueError:
        return _receipt(project=project, error="invalid_project")

    if not isinstance(event, dict):
        return _receipt(project=project, error="malformed_event")
    if event.get("hook_event_name") != EVENT_NAME:
        return _receipt(
            project=project,
            event_name=event.get("hook_event_name"),
            error="unsupported_event",
        )

    session_id = event.get("session_id")
    turn_id = event.get("turn_id")
    if session_id is None or turn_id is None:
        return _receipt(
            project=project,
            session_id=session_id,
            turn_id=turn_id,
            error="missing_identity",
        )
    if not _identity(session_id) or not _identity(turn_id):
        return _receipt(
            project=project,
            session_id=session_id if isinstance(session_id, str) else None,
            turn_id=turn_id if isinstance(turn_id, str) else None,
            error="invalid_identity",
        )

    agent_id = event.get("agent_id")
    if agent_id is not None and not _identity(agent_id):
        return _receipt(
            project=project,
            session_id=session_id,
            agent_id=agent_id if isinstance(agent_id, str) else None,
            turn_id=turn_id,
            error="invalid_identity",
        )
    try:
        _utf8(session_id)
        _utf8(turn_id)
        if agent_id is not None:
            _utf8(agent_id)
    except ValueError:
        return _receipt(
            project=project,
            session_id=session_id,
            agent_id=agent_id,
            turn_id=turn_id,
            error="invalid_identity",
        )

    prompt = event.get("prompt")
    if not isinstance(prompt, str):
        return _receipt(
            project=project,
            session_id=session_id,
            agent_id=agent_id,
            thread_id=agent_id or session_id,
            turn_id=turn_id,
            error="invalid_prompt",
        )
    try:
        prompt_bytes = _utf8(prompt)
    except ValueError:
        return _receipt(
            project=project,
            session_id=session_id,
            agent_id=agent_id,
            thread_id=agent_id or session_id,
            turn_id=turn_id,
            error="invalid_prompt_encoding",
        )
    if len(prompt_bytes) > MAX_PROMPT_BYTES:
        return _receipt(
            project=project,
            session_id=session_id,
            agent_id=agent_id,
            thread_id=agent_id or session_id,
            turn_id=turn_id,
            error="oversized_prompt",
        )

    thread_id = agent_id or session_id
    event_id = _event_id(session_id, agent_id, turn_id)
    prompt_hash = hashlib.sha256(prompt_bytes).hexdigest()
    archived = {
        "agent_id": agent_id,
        "authority": AUTHORITY,
        "event": EVENT_NAME,
        "project": project,
        "prompt": prompt,
        "prompt_bytes": len(prompt_bytes),
        "prompt_sha256": prompt_hash,
        "root_session_id": session_id,
        "schema": SCHEMA,
        "session_id": session_id,
        "thread_id": thread_id,
        "turn_id": turn_id,
    }
    try:
        raw = _json_bytes(archived)
        if not callable(getattr(memory, "record", None)):
            raise ValueError("Memory record capability required")
        reference = memory.record(
            project,
            thread_id,
            event_id,
            raw,
            global_identity=True,
        )
        if not isinstance(reference, dict):
            raise ValueError("Invalid Memory reference")
        required = ("record_hash", "source_hash", "bytes")
        if (
            any(key not in reference for key in required)
            or not all(
                isinstance(reference[key], str)
                and len(reference[key]) == 64
                and all(character in "0123456789abcdef" for character in reference[key])
                for key in ("record_hash", "source_hash")
            )
            or type(reference["bytes"]) is not int
            or reference["bytes"] != len(raw)
        ):
            raise ValueError("Incomplete Memory reference")
    except ValueError as exc:
        if "collision" in str(exc).lower():
            error = "identity_collision"
        else:
            error = "storage_failure"
        return _receipt(
            project=project,
            session_id=session_id,
            agent_id=agent_id,
            thread_id=thread_id,
            turn_id=turn_id,
            event_id=event_id,
            error=error,
        )
    except Exception:
        return _receipt(
            project=project,
            session_id=session_id,
            agent_id=agent_id,
            thread_id=thread_id,
            turn_id=turn_id,
            event_id=event_id,
            error="storage_failure",
        )

    return _receipt(
        project=project,
        session_id=session_id,
        agent_id=agent_id,
        thread_id=thread_id,
        turn_id=turn_id,
        event_id=event_id,
        captured=True,
        prompt_bytes=len(prompt_bytes),
        prompt_sha256=prompt_hash,
        record_hash=reference["record_hash"],
        source_hash=reference["source_hash"],
        bytes=reference["bytes"],
    )
