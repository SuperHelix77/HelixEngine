"""Bounded ingestion of native assistant statements into workflow memory.

This module admits only explicitly attributed assistant message events.  The
native JSON line is the archived evidence; parsed fields are validation and
identity metadata only.  No statement is treated as current instructions or
semantic truth.
"""

import json


MAX_LINE_BYTES = 64 * 1024
MAX_ID_BYTES = 512
CLASSIFICATION = "historical_attributed_statement"
AUTHORITY = "historical attributed statement; not semantic truth/current instructions"
METRICS_SCOPE = (
    "shared logical application counters; deltas may include concurrent work; "
    "SQLite and physical I/O unmeasured"
)


def _identity(value, label, *, bounded=False):
    if type(value) is not str or not value or "\x00" in value:
        raise ValueError(f"Invalid {label}")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"Invalid {label}") from exc
    if bounded and len(encoded) > MAX_ID_BYTES:
        raise ValueError(f"Invalid {label}")
    return value


def _reject_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def _objects_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _numeric_delta(before, after):
    if not isinstance(before, dict) or not isinstance(after, dict):
        return {}
    result = {}
    for key, old in before.items():
        new = after.get(key)
        if isinstance(old, bool) or isinstance(new, bool):
            continue
        if isinstance(old, (int, float)) and isinstance(new, (int, float)):
            result[key] = new - old
    return result


class StatementMemory:
    """Persist bounded, native assistant message lines in an existing Memory."""

    def __init__(self, memory, project):
        if not callable(getattr(memory, "record", None)):
            raise ValueError("Memory record capability required")
        self.memory = memory
        self.project = _identity(project, "project")

    def _parse(self, raw_line):
        if type(raw_line) is not bytes:
            raise ValueError("Exact native JSON bytes required")
        if len(raw_line) > MAX_LINE_BYTES:
            raise ValueError("Native JSON line exceeds 64 KiB")
        try:
            record = json.loads(
                raw_line.decode("utf-8"),
                object_pairs_hook=_objects_without_duplicates,
                parse_constant=_reject_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
            raise ValueError("Malformed native JSON line") from exc
        if type(record) is not dict or record.get("type") != "response_item":
            raise ValueError("Unsupported native response item")

        message = record.get("payload")
        if type(message) is not dict or message.get("type") != "message":
            raise ValueError("Unsupported native message payload")
        if message.get("role") != "assistant":
            raise ValueError("Unsupported native message role")
        phase = message.get("phase")
        if phase not in ("commentary", "final_answer"):
            raise ValueError("Unsupported or ambiguous native message phase")
        message_id = _identity(message.get("id"), "native message id", bounded=True)

        content = message.get("content")
        if type(content) is not list or not content:
            raise ValueError("Native message content must be nonempty output_text")
        for item in content:
            if type(item) is not dict or item.get("type") != "output_text":
                raise ValueError("Mixed or unsupported native message content")
            text = item.get("text")
            if type(text) is not str or not text or "\x00" in text:
                raise ValueError("Native output_text must be a nonempty string")
        return message_id, phase

    def record(self, thread_id, raw_line):
        """Admit one exact native JSON line and return its memory reference."""
        thread_id = _identity(thread_id, "thread id", bounded=True)
        message_id, phase = self._parse(raw_line)
        event_id = "native-statement:" + thread_id + ":" + message_id

        memory_metrics = getattr(self.memory, "metrics", None)
        before_memory = dict(memory_metrics) if isinstance(memory_metrics, dict) else {}
        store = getattr(self.memory, "store", None)
        store_metrics = getattr(store, "metrics", None)
        before_store = dict(store_metrics) if isinstance(store_metrics, dict) else {}

        reference = self.memory.record(
            self.project,
            thread_id,
            event_id,
            raw_line,
            global_identity=True,
        )

        after_memory = getattr(self.memory, "metrics", None)
        after_store_metrics = getattr(store, "metrics", None)
        return {
            **reference,
            "classification": CLASSIFICATION,
            "authority": AUTHORITY,
            "message_id": message_id,
            "phase": phase,
            "metrics": {
                "memory": _numeric_delta(before_memory, after_memory),
                "store": _numeric_delta(before_store, after_store_metrics),
                "scope": METRICS_SCOPE,
            },
        }
