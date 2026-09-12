"""One opt-in Codex hook adapter. No inference, approvals, or semantic gating.

Unknown shell syntax uses native execution. Admitted foreground commands use
Engine capture; TTYs and changed command resolution use native execution.
"""
import base64
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import sys
import time

# Support the version-bound script path from the native hook without PYTHONPATH
# changes leaking into executed commands.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

POLICY = 'codex-foreground-v1'
LIMIT = 262144


def route(command):
    """Conservative shared router; model identity never changes semantics."""
    if os.name != 'posix':
        return None
    if not isinstance(command, str) or not command or len(command) > 32768:
        return None
    if any(c in command for c in '\n\r\x00$`;&|<>*?[]{}~#'):
        return None
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if not argv or any('helixengine' in arg for arg in argv):
        return None
    name = Path(argv[0]).name
    kind = 'generic'
    if name in ('pytest', 'py.test') or (name in ('python', 'python3') and argv[1:3] == ['-m', 'pytest']):
        if any(x in argv for x in ('--pdb', '--trace', '-s', '--capture=no')):
            return None
        kind = 'pytest'
    elif name == 'git':
        if len(argv) < 2 or argv[1] not in ('status', 'diff', 'log', 'show', 'ls-files'):
            return None
        # A pager is interactive and cannot be captured transparently.
        if any(x in argv for x in ('--paginate', '-p')):
            return None
    elif name not in ('rg', 'grep'):
        return None
    resolved = shutil.which(argv[0])
    if not resolved:
        return None
    return {'argv': argv, 'kind': kind, 'resolved': resolved}


def _identity(value):
    return isinstance(value, str) and 0 < len(value) <= 512 and '\x00' not in value


def hook(event, data_dir, session_scope=None):
    from helixengine.state import State
    started = time.perf_counter()
    if not isinstance(event, dict) or not _identity(event.get('session_id')):
        return {}
    if session_scope is not None and event['session_id'] != session_scope:
        return {}
    state = State(data_dir)
    kind = event.get('hook_event_name')
    binding = {key: event[key] for key in ('session_id', 'turn_id', 'tool_use_id', 'model', 'agent_id') if _identity(event.get(key))}
    # Native child hooks retain the parent session_id; agent_id is the child.
    binding['thread_id'] = binding.get('agent_id', binding['session_id'])
    if kind in ('SubagentStart', 'SubagentStop'):
        state.event('CODEX_' + kind.upper(), binding)
        return {}
    if kind != 'PreToolUse' or event.get('tool_name') != 'Bash':
        return {}
    tool_input = event.get('tool_input')
    command = tool_input.get('command') if isinstance(tool_input, dict) else None
    selected = route(command)
    enabled = state.settings()['enabled']
    binding.update(policy=POLICY, route='engine' if selected and enabled else 'native', hook_seconds=time.perf_counter()-started)
    state.event('CODEX_ROUTE', binding)
    if not selected or not enabled:
        return {}
    cwd = event.get('cwd')
    if not isinstance(cwd, str) or not Path(cwd).is_dir():
        return {}
    envelope = {**selected, 'cwd': cwd, 'data_dir': str(Path(data_dir).expanduser().resolve()), 'binding': binding}
    encoded = base64.urlsafe_b64encode(json.dumps(envelope, separators=(',', ':')).encode()).decode()
    invocation = shlex.join([sys.executable, str(Path(__file__).resolve()), 'execute', encoded])
    # Resolve inside the original shell, preserving aliases/functions and PATH:
    # if its resolution differs, run the original source unchanged.
    rewritten = f'if [ "$(command -v {shlex.quote(selected["argv"][0])})" = {shlex.quote(selected["resolved"])} ]; then exec {invocation}; else {command}; fi'
    # "allow" is required by the native rewrite protocol. This is not a
    # PermissionRequest hook and must never grant sandbox escalation.
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'allow', 'updatedInput': {**tool_input, 'command': rewritten}}}


def execute(encoded):
    if len(encoded) > LIMIT:
        raise ValueError('Envelope too large')
    spec = json.loads(base64.b64decode(encoded, altchars=b'-_', validate=True))
    argv = spec['argv']
    if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or '\x00' in x for x in argv):
        raise ValueError('Invalid argv')
    if Path.cwd().resolve() != Path(spec['cwd']).resolve():
        raise ValueError('Native cwd changed')
    # Never transform an interactive tool into a buffered foreground job.
    if any(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)) or shutil.which(argv[0]) != spec['resolved']:
        os.execvp(argv[0], argv)
    from helixengine.runtime import Runtime
    try:
        runtime = Runtime(spec['data_dir'])
    except Exception:
        # Preparation failed before a command was started. Preserve the native
        # operation under its existing permissions; never broaden the sandbox.
        os.execvp(argv[0], argv)
    previous_term = signal.getsignal(signal.SIGTERM)
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        binding = spec['binding']
        identity = 'codex:' + binding.get('thread_id', binding.get('agent_id', binding['session_id'])) + ':' + binding.get('tool_use_id', 'UNKNOWN')
        result = runtime.run(argv, spec['cwd'], kind=spec['kind'], environment_id=identity, native_process_group=True)
        if result.get('publication_error'):
            sys.stderr.write('Helix: evidence/telemetry publication incomplete; raw result retained; no retry.\n')
        try:
            runtime.state.event('CODEX_EXECUTED', {**binding, 'run': result['run']['id']}, run=result['run']['id'])
        except Exception:
            # Execution already completed. Never rerun it to repair attribution.
            sys.stderr.write('Helix: command receipt saved; Codex attribution failed.\n')
        stdout, stderr = runtime.visible_output(result)
        if result.get('delivery_error'):
            sys.stderr.write('Helix: packet unavailable; delivering captured raw output; no retry.\n')
        sys.stdout.buffer.write(stdout); sys.stdout.buffer.flush()
        sys.stderr.buffer.write(stderr); sys.stderr.buffer.flush()
        code = result.get('exit_code')
        return 128 + abs(code) if isinstance(code, int) and code < 0 else code if isinstance(code, int) else 1
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        try:
            runtime.close()
        except Exception:
            sys.stderr.write('Helix: cleanup failed after command; no retry.\n')


def main():
    if len(sys.argv) == 3 and sys.argv[1] == 'execute':
        return execute(sys.argv[2])
    if len(sys.argv) not in (3, 4) or sys.argv[1] != 'hook':
        raise ValueError('Use hook DATA_DIR or execute ENVELOPE')
    raw = sys.stdin.buffer.read(LIMIT + 1)
    if len(raw) > LIMIT:
        return 0
    try:
        result = hook(json.loads(raw), sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)
    except Exception:
        # Hook failures must not trigger a second command or authorize anything.
        result = {}
    if result:
        print(json.dumps(result, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
