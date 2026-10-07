#!/usr/bin/env python3
"""Grok host adapter for Helix Engine.

Grok's hook JSON uses camelCase and its own tool names. This normalizes one
event into the Claude Code shape and hands it to adapters/claude_code.py with
HELIX_HOME pointed at this install. Claude Code's copy is a different directory
and a different memory.db.
"""
import json, os, re, sys, subprocess
from urllib.parse import quote

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ['HELIX_HOME'] = HOME
os.environ['HELIX_FOR_GROK'] = '1'
os.environ.setdefault('HELIX_MEM_DB', os.path.join(HOME, 'memory.db'))

TOOL_ALIAS = {
    'run_terminal_command': 'Bash',
    'read_file': 'Read',
    'search_replace': 'Edit',
    'grep': 'Grep',
}
USER_QUERY = re.compile(r'<user_query>\s*(.*?)\s*</user_query>', re.S)


def _load():
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _user_text(content):
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get('type') == 'text':
                parts.append(block.get('text') or '')
        content = '\n'.join(parts)
    if not isinstance(content, str):
        return ''
    match = USER_QUERY.search(content)
    if match:
        return match.group(1).strip()
    if '<system-reminder>' in content or content.startswith('You are Grok'):
        return ''
    return content.strip()[:4000]


def _claude_transcript(src, dest):
    """Rewrite a Grok chat_history.jsonl into the Claude JSONL Helix ingests."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(src) as inp, open(dest, 'w') as out:
        for line in inp:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = row.get('type')
            if kind == 'user':
                text = _user_text(row.get('content'))
                if not text:
                    continue
                out.write(json.dumps({'type': 'user', 'message': {'content': text}}) + '\n')
            elif kind == 'assistant':
                blocks = []
                text = row.get('content')
                if isinstance(text, str) and text.strip():
                    blocks.append({'type': 'text', 'text': text})
                for call in row.get('tool_calls') or []:
                    args = call.get('arguments')
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {'raw': args[:600]}
                    if not isinstance(args, dict):
                        args = {}
                    blocks.append({'type': 'tool_use', 'name': call.get('name') or '', 'input': args})
                if blocks:
                    out.write(json.dumps({'type': 'assistant', 'message': {'content': blocks}}) + '\n')
            elif kind == 'tool_result':
                body = row.get('content') or ''
                if not isinstance(body, str):
                    body = json.dumps(body)[:4000]
                out.write(json.dumps({'type': 'user', 'message': {'content': [{'type': 'tool_result', 'content': body[:8000]}]}}) + '\n')


def _find_transcript(event):
    path = event.get('transcript_path') or event.get('transcriptPath') or ''
    if path and os.path.exists(path):
        return path
    session = event.get('sessionId') or event.get('session_id') or os.environ.get('GROK_SESSION_ID') or ''
    cwd = event.get('cwd') or event.get('workspaceRoot') or os.getcwd()
    if not session:
        return ''
    root = os.path.expanduser('~/.grok/sessions')
    direct = os.path.join(root, quote(cwd, safe=''), session, 'chat_history.jsonl')
    if os.path.exists(direct):
        return direct
    if not os.path.isdir(root):
        return ''
    for name in os.listdir(root):
        cand = os.path.join(root, name, session, 'chat_history.jsonl')
        if os.path.exists(cand):
            return cand
    return ''


def _looks_like_grok(path):
    try:
        with open(path) as handle:
            first = handle.readline()
    except OSError:
        return False
    try:
        row = json.loads(first) if first else {}
    except json.JSONDecodeError:
        return False
    return row.get('type') in ('system', 'user', 'assistant', 'tool_result', 'reasoning') and 'message' not in row


def normalize(event):
    cwd = event.get('cwd') or event.get('workspaceRoot') or os.getcwd()
    event['cwd'] = cwd
    name = event.get('tool_name') or event.get('toolName') or ''
    event['tool_name'] = TOOL_ALIAS.get(name, name)
    tool_input = event.get('tool_input') if isinstance(event.get('tool_input'), dict) else None
    if tool_input is None and isinstance(event.get('toolInput'), dict):
        tool_input = event['toolInput']
    if event['tool_name'] == 'Bash' and isinstance(tool_input, dict):
        event['tool_input'] = {'command': tool_input.get('command') or ''}
    elif isinstance(tool_input, dict):
        event['tool_input'] = tool_input
    src = _find_transcript(event)
    if src and _looks_like_grok(src):
        session = event.get('sessionId') or event.get('session_id') or 'session'
        safe = re.sub(r'[^A-Za-z0-9_.-]', '_', session)[:80]
        dest = os.path.join(HOME, 'run', 'grok-transcripts', safe + '.jsonl')
        try:
            _claude_transcript(src, dest)
            event['transcript_path'] = dest
        except OSError:
            event['transcript_path'] = src
    elif src:
        event['transcript_path'] = src
    return event


def _python():
    if os.path.exists('/usr/bin/python3'):
        return '/usr/bin/python3'
    return sys.executable


def hook_commands():
    """Absolute paths only. Grok refuses a hook whose command references an unset $VAR."""
    py = _python()
    adapter = os.path.join(HOME, 'adapters', 'grok.py')

    def command(event, timeout):
        text = f'{py} {adapter} {event}'
        if '$' in text:
            raise RuntimeError('grok hook command must not contain $')
        return {'type': 'command', 'command': text, 'timeout': timeout}

    return {
        'hooks': {
            'SessionStart': [{'matcher': 'startup|resume|clear|compact', 'hooks': [command('SessionStart', 15)]}],
            'PreToolUse': [{'matcher': 'Bash', 'hooks': [command('PreToolUse', 10)]}],
            'PreCompact': [{'hooks': [command('PreCompact', 20)]}],
            'Stop': [{'hooks': [command('Stop', 20)]}],
            'SessionEnd': [{'hooks': [command('SessionEnd', 20)]}],
        }
    }


def _dump(payload):
    return json.dumps(payload, indent=2) + '\n'


def _backup(path):
    import time
    import shutil
    shutil.copy(path, f"{path}.bak-helix-{time.strftime('%Y%m%d%H%M%S')}")


def _ours(path):
    try:
        payload = json.load(open(path))
    except (OSError, json.JSONDecodeError):
        return False
    commands = []
    for groups in (payload.get('hooks') or {}).values():
        for group in groups:
            for hook in group.get('hooks') or []:
                commands.append(hook.get('command') or '')
    return bool(commands) and all('adapters/grok.py' in command for command in commands)


def install_hooks(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = _dump(hook_commands())
    if os.path.exists(path):
        if open(path).read() == text:
            return path
        if not _ours(path):
            raise SystemExit(f'refuse to replace {path}: it is not a Helix Grok hook file')
        _backup(path)
    with open(path, 'w') as handle:
        handle.write(text)
    return path


def uninstall_hooks(path):
    if not os.path.exists(path):
        return path
    if not _ours(path):
        raise SystemExit(f'refuse to remove {path}: it is not a Helix Grok hook file')
    _backup(path)
    os.remove(path)
    return path


def skill_text():
    src = os.path.join(HOME, 'adapters', 'grok-SKILL.md')
    return open(src).read().replace('__HELIX_HOME__', HOME)


def install_skill(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = skill_text()
    if os.path.exists(path):
        if open(path).read() == text:
            return path
        _backup(path)
    with open(path, 'w') as handle:
        handle.write(text)
    return path


def _flag(argv, name, default):
    if name in argv:
        return argv[argv.index(name) + 1]
    return default


def _hooks_cli(argv):
    sub = argv[0] if argv and not argv[0].startswith('--') else 'print'
    path = _flag(argv, '--hooks', os.path.expanduser('~/.grok/hooks/helix.json'))
    if sub == 'print':
        print(_dump(hook_commands()), end='')
        return 0
    if sub == 'install':
        print('hooks installed into', install_hooks(path))
        return 0
    if sub == 'uninstall':
        print('removed', uninstall_hooks(path))
        return 0
    sys.exit('usage: helix grok hooks [print|install|uninstall] [--hooks FILE]')


def _skill_cli(argv):
    sub = argv[0] if argv and not argv[0].startswith('--') else 'print'
    path = _flag(argv, '--skill', os.path.expanduser('~/.grok/skills/helix/SKILL.md'))
    if sub == 'print':
        print(skill_text(), end='')
        return 0
    if sub == 'install':
        print('skill installed into', install_skill(path))
        return 0
    sys.exit('usage: helix grok skill [print|install] [--skill FILE]')


def main():
    argv = sys.argv[1:]
    if argv[:1] == ['hooks']:
        return _hooks_cli(argv[1:])
    if argv[:1] == ['skill']:
        return _skill_cli(argv[1:])
    if argv[:1] == ['install']:
        hooks = install_hooks(_flag(argv, '--hooks', os.path.expanduser('~/.grok/hooks/helix.json')))
        skill = install_skill(_flag(argv, '--skill', os.path.expanduser('~/.grok/skills/helix/SKILL.md')))
        print('hooks installed into', hooks)
        print('skill installed into', skill)
        return 0
    event = normalize(_load())
    proc = subprocess.run(
        [sys.executable, os.path.join(HOME, 'adapters', 'claude_code.py'), *sys.argv[1:]],
        input=json.dumps(event).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.stdout:
        sys.stdout.buffer.write(proc.stdout)
    if proc.stderr:
        sys.stderr.buffer.write(proc.stderr)
    return proc.returncode


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write(f'helix grok adapter: {type(exc).__name__}: {exc}\n')
        sys.exit(0)
