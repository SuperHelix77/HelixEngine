"""Conservative native transcript fence for opt-in recording transitions.

The caller pins an idle thread snapshot. Between accepted recording turns only
the inspected native stopped-turn sequence is admitted. Unknown schemas, missing
events and changes expand back to native inference. This is not a semantic
classifier or protection against a hostile owner rewriting all trusted state.
"""
import hashlib
import json
import os
from pathlib import Path
import stat

MAX_TRANSCRIPT_BYTES = 4 * 1024 * 1024
SCHEMA = 'helix.native.continuity.v1'


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate transcript field')
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError('Nonfinite transcript field')


def _rows(raw):
    if not raw or not raw.endswith(b'\n'):
        raise ValueError('Incomplete native transcript')
    rows = []
    for line in raw.splitlines():
        row = json.loads(line, object_pairs_hook=_unique, parse_constant=_nonfinite)
        if not isinstance(row, dict) or not isinstance(row.get('payload'), dict):
            raise ValueError('Unsupported native transcript record')
        rows.append(row)
    return rows


def _read(path):
    if not isinstance(path, (str, Path)):
        raise ValueError('Native transcript path missing')
    path = Path(path).expanduser()
    if not path.is_absolute() or path.is_symlink():
        raise ValueError('Explicit regular transcript path required')
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('Regular transcript required')
        raw = stream.read(MAX_TRANSCRIPT_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > MAX_TRANSCRIPT_BYTES:
        raise ValueError('Transcript exceeds bounded continuity reader')
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(raw) != after.st_size:
        raise ValueError('Transcript changed during read')
    return str(path.resolve()), raw, (after.st_dev, after.st_ino)


def _context(payload):
    result = dict(payload)
    turn = result.pop('turn_id', None)
    if not isinstance(turn, str) or not turn:
        raise ValueError('Native turn context identity missing')
    if result.get('root_turn_id') == turn:
        result['root_turn_id'] = '@current-root-turn'
    return hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _anchor(path, raw, identity, thread_id, context_hash, pending_turn):
    return dict(schema=SCHEMA, path=path, bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(), device=identity[0], inode=identity[1],
                thread_id=thread_id, context_hash=context_hash, pending_turn=pending_turn,
                bytes_read=len(raw))


def checkpoint(path, thread_id):
    """Pin a caller-selected idle native thread after an ordinary semantic turn.

    Registration is explicit; a fresh or in-flight thread cannot be declared
    semantically resolved from a filename or an incomplete transcript.
    """
    path, raw, identity = _read(path)
    rows = _rows(raw)
    if rows[0].get('type') != 'session_meta' or rows[0]['payload'].get('id') != thread_id:
        raise ValueError('Native thread identity mismatch')
    contexts = [r['payload'] for r in rows if r.get('type') == 'turn_context']
    if not contexts:
        raise ValueError('No completed native semantic turn to bind')
    context = contexts[-1]
    tail = rows[-1]
    if tail.get('type') != 'event_msg' or tail['payload'].get('type') != 'task_complete' or (
            tail['payload'].get('turn_id') != context.get('turn_id')):
        raise ValueError('Native thread is not at a completed-turn fence')
    return _anchor(path, raw, identity, thread_id, _context(context), None)


def check(anchor, native_event):
    """Require an unchanged prefix and exactly the qualified stopped-turn delta."""
    if not isinstance(anchor, dict) or anchor.get('schema') != SCHEMA:
        raise ValueError('Missing native continuity anchor')
    if not isinstance(native_event, dict) or native_event.get('hook_event_name') != 'UserPromptSubmit':
        raise ValueError('Native submission event required')
    thread_id = native_event.get('agent_id') or native_event.get('session_id')
    current = native_event.get('turn_id')
    if thread_id != anchor.get('thread_id') or not isinstance(current, str) or not current:
        raise ValueError('Native event identity mismatch')
    path, raw, identity = _read(native_event.get('transcript_path'))
    if path != anchor.get('path') or list(identity) != [anchor.get('device'), anchor.get('inode')]:
        raise ValueError('Native transcript identity changed')
    size = anchor.get('bytes')
    if type(size) is not int or size < 1 or size > len(raw) or (
            hashlib.sha256(raw[:size]).hexdigest() != anchor.get('sha256')):
        raise ValueError('Native transcript prefix changed or rolled back')
    suffix = raw[size:]
    if not suffix and anchor.get('pending_turn') == current:
        return dict(anchor, bytes_read=len(raw))
    rows = _rows(suffix)
    pending = anchor.get('pending_turn')
    if pending is not None:
        completion = rows.pop(0)
        body = completion['payload']
        if completion.get('type') != 'event_msg' or body.get('type') != 'task_complete' or (
                body.get('turn_id') != pending or 'last_agent_message' not in body or
                body['last_agent_message'] is not None):
            raise ValueError('Previous recording turn did not finish mechanically')
        if set(body) - {'type', 'turn_id', 'last_agent_message', 'started_at', 'completed_at', 'duration_ms'}:
            raise ValueError('Unsupported completion fields')
    if len(rows) != 2:
        raise ValueError('Unobserved native work or unsupported event sequence')
    start, context = rows
    if start.get('type') != 'event_msg' or start['payload'].get('type') != 'task_started' or (
            start['payload'].get('turn_id') != current):
        raise ValueError('Current native turn start fence missing')
    if set(start['payload']) - {'type', 'turn_id', 'started_at', 'model_context_window', 'collaboration_mode_kind'}:
        raise ValueError('Unsupported native turn-start fields')
    if context.get('type') != 'turn_context' or context['payload'].get('turn_id') != current:
        raise ValueError('Current native context fence missing')
    if _context(context['payload']) != anchor.get('context_hash'):
        raise ValueError('Native instructions, model or execution context changed')
    return _anchor(path, raw, identity, thread_id, anchor['context_hash'], current)
