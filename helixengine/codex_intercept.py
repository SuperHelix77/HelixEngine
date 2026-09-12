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

POLICY = 'codex-foreground-v2'
LIMIT = 262144
MAX_COMPOUND_LEAVES = 32


def _simple_route(command):
    """Preserve the original conservative single-command admission rules."""
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


def _compound_route(command):
    """Admit only an unquoted, bounded sequence of independently safe leaves."""
    if not isinstance(command, str) or len(command) > 32768 or '&&' not in command:
        return None
    # Do not guess whether an operator is inside a quote or escaped. A
    # compound command with either form remains native in its entirety.
    if any(char in command for char in "'\\\"()"):
        return None
    leaves = []
    start = 0
    index = 0
    while index < len(command):
        if command.startswith('&&', index):
            source = command[start:index]
            if not source.strip():
                return None
            leaves.append(source)
            start = index + 2
            index = start
            continue
        if command[index] == '&':
            return None
        index += 1
    source = command[start:]
    if not source.strip():
        return None
    leaves.append(source)
    if len(leaves) < 2 or len(leaves) > MAX_COMPOUND_LEAVES:
        return None
    selected = []
    for source in leaves:
        leaf = _simple_route(source.strip())
        if leaf is None:
            return None
        selected.append({**leaf, 'source': source})
    return {'compound': True, 'leaves': selected}


def route(command):
    """Conservative shared router; model identity never changes semantics."""
    selected = _simple_route(command)
    if selected is not None:
        return selected
    return _compound_route(command)


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
    binding.update(
        policy=POLICY,
        route='engine' if selected and enabled else 'native',
        leaf_ordinal=0,
        hook_seconds=time.perf_counter()-started,
    )
    state.event('CODEX_ROUTE', binding)
    if not selected or not enabled:
        return {}
    cwd = event.get('cwd')
    if not isinstance(cwd, str) or not Path(cwd).is_dir():
        return {}
    data_path = str(Path(data_dir).expanduser().resolve())

    def invocation(leaf, ordinal):
        leaf_binding = {**binding, 'leaf_ordinal': ordinal}
        envelope = {
            **leaf,
            'cwd': cwd,
            'data_dir': data_path,
            'binding': leaf_binding,
            'leaf_ordinal': ordinal,
        }
        encoded = base64.urlsafe_b64encode(json.dumps(envelope, separators=(',', ':')).encode()).decode()
        return shlex.join([sys.executable, str(Path(__file__).resolve()), 'execute', encoded])

    if selected.get('compound'):
        guards = []
        resolutions = []
        for ordinal, leaf in enumerate(selected['leaves']):
            command_invocation = invocation(leaf, ordinal)
            resolution = (
                f'[ "$(command -v {shlex.quote(leaf["argv"][0])})" = '
                f'{shlex.quote(leaf["resolved"])} ]'
            )
            resolutions.append(resolution)
            # Each leaf owns a subshell. exec therefore replaces only that
            # leaf's process and cannot consume a following shell && leaf.
            guards.append(
                f'(if {resolution}; then exec {command_invocation}; '
                f'else {leaf["source"]}; fi)'
            )
        # Check every resolution in the caller shell before starting any
        # Engine leaf. This keeps aliases/functions and their shell-state
        # changes (for example cd) on the original whole-chain path.
        rewritten = f'if {" && ".join(resolutions)}; then {" && ".join(guards)}; else {command}; fi'
    else:
        command_invocation = invocation(selected, 0)
        # Resolve inside the original shell, preserving aliases/functions and PATH:
        # if its resolution differs, run the original source unchanged.
        rewritten = f'if [ "$(command -v {shlex.quote(selected["argv"][0])})" = {shlex.quote(selected["resolved"])} ]; then exec {command_invocation}; else {command}; fi'
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
    leaf_ordinal = spec.get('leaf_ordinal', 0)
    if type(leaf_ordinal) is not int or not 0 <= leaf_ordinal < MAX_COMPOUND_LEAVES:
        raise ValueError('Invalid leaf ordinal')
    # A hook's cwd is the thread root in the desktop dispatcher, while an
    # individual tool can explicitly request a different workdir. This is fresh
    # execution, not cached-plan reuse: bind the actual native tool process cwd,
    # retaining the hook context separately. Never chdir to the thread root.
    native_cwd = str(Path.cwd().resolve())
    # Never transform an interactive tool into a buffered foreground job.
    if any(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)) or shutil.which(argv[0]) != spec['resolved']:
        os.execvp(argv[0], argv)
    try:
        from helixengine.runtime import Runtime
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
        binding = {**spec['binding'], 'hook_cwd': spec['cwd'], 'execution_cwd': native_cwd}
        binding_ordinal = binding.get('leaf_ordinal', leaf_ordinal)
        if type(binding_ordinal) is not int or binding_ordinal != leaf_ordinal or not 0 <= binding_ordinal < MAX_COMPOUND_LEAVES:
            raise ValueError('Invalid binding leaf ordinal')
        identity = 'codex:' + binding.get('thread_id', binding.get('agent_id', binding['session_id'])) + ':' + binding.get('tool_use_id', 'UNKNOWN') + ':leaf:' + str(leaf_ordinal)
        origin = {k: binding[k] for k in ('session_id', 'thread_id', 'agent_id',
                  'tool_use_id', 'hook_cwd', 'execution_cwd', 'model') if isinstance(binding.get(k), str) and binding[k]}
        result = runtime.run(argv, native_cwd, kind=spec['kind'], environment_id=identity, native_process_group=True, origin=origin)
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
