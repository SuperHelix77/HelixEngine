#!/usr/bin/env bash
# Helix Engine installer. Idempotent. It NEVER edits ~/.claude/settings.json (use `helix hooks install` for that, explicitly).
#   ./install.sh [--prefix DIR] [--no-link] [--skip-checks] [--with-local-models] [--with-laya]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; PREFIX="$HOME/.local/bin"; LINK=1; CHECKS=1; LOCAL=0; LAYA=0
while [ $# -gt 0 ]; do case "$1" in
  --prefix) PREFIX="$2"; shift 2;; --no-link) LINK=0; shift;; --skip-checks) CHECKS=0; shift;;
  --with-local-models) LOCAL=1; shift;; --with-laya) LAYA=1; shift;;
  -h|--help) sed -n '2,3p' "$0"; exit 0;; *) echo "unknown option $1"; exit 2;; esac; done
ok(){ printf '  [ok]   %s\n' "$*"; }; warn(){ printf '  [warn] %s\n' "$*"; }; die(){ printf '  [FAIL] %s\n' "$*"; exit 1; }
echo "Helix Engine $(cat "$HERE/VERSION") -> $HERE"
if [ "$CHECKS" = 1 ]; then
  echo "Preflight:"
  command -v zsh >/dev/null && ok "zsh" || die "zsh is required (the launcher is a zsh script)"
  command -v python3 >/dev/null || die "python3 is required"
  python3 - <<'PY' || die "Python 3.9+ with sqlite FTS5 is required"
import sys,sqlite3
assert sys.version_info>=(3,9)
c=sqlite3.connect(':memory:'); c.execute('create virtual table t using fts5(a)')
PY
  ok "python3 $(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])') with sqlite FTS5"
  command -v claude >/dev/null && ok "claude CLI ($(claude --version 2>/dev/null | head -1))" || die "Claude Code CLI not found. Install it first: https://docs.claude.com/en/docs/claude-code and run 'claude' once to log in"
  command -v rtk >/dev/null && ok "rtk $(rtk --version 2>/dev/null | head -1)" || warn "rtk not found: engine still works, with smaller savings. macOS: brew install rtk"
  command -v ollama >/dev/null && ok "ollama (optional, for local models)" || warn "ollama not found (optional; only needed for ask/summ/docgen local-model tools)"
  [ "$(uname)" = Darwin ] && ok "macOS" || warn "non-macOS: sandboxed benchmarks (sandbox-exec) and some paths are macOS-only; the engine itself is portable"
fi
RTK="$(command -v rtk || true)"
python3 - "$HERE" "$RTK" <<'PY'
import sys,json
here,rtk=sys.argv[1],sys.argv[2]; s=open(here+'/settings.json.template').read()
if rtk: s=s.replace('__RTK__',rtk); out=json.loads(s)
else: out=json.loads(s); out['hooks']={}
json.dump(out,open(here+'/settings.json','w'),indent=2); open(here+'/settings.json','a').write('\n')
PY
ok "generated settings.json (profile used by 'helix' only; your ~/.claude/settings.json is untouched)"
mkdir -p "$HERE/run"; chmod +x "$HERE/helix" "$HERE"/bin/* "$HERE"/*.sh "$HERE"/adapters/*.py "$HERE/helix_doctor.py" 2>/dev/null || true
if [ "$LINK" = 1 ]; then mkdir -p "$PREFIX"; ln -sf "$HERE/helix" "$PREFIX/helix"; ok "linked $PREFIX/helix"
  case ":$PATH:" in *":$PREFIX:"*) ;; *) warn "$PREFIX is not on your PATH. Add:  export PATH=\"$PREFIX:\$PATH\"";; esac; fi
if [ "$LOCAL" = 1 ]; then
  command -v ollama >/dev/null || die "--with-local-models needs ollama (brew install ollama)"
  "$HERE/lmup.sh"; OLLAMA_HOST=127.0.0.1:11500 ollama pull qwen3:1.7b && ok "local model qwen3:1.7b ready on private port 11500 (your default ollama is untouched)"
fi
if [ "$LAYA" = 1 ]; then
  python3 -m venv "$HERE/venv"; "$HERE/venv/bin/pip" install -q laya && ok "laya installed in $HERE/venv (checkpoints download on first use, ~0.8 GB)"
fi
echo; echo "Done. Next:"; echo "  helix doctor          # verify the install"; echo "  helix                 # start a lean Helix session"; echo "  helix hooks print     # see what 'helix hooks install' would add to ~/.claude/settings.json"
[ "$CHECKS" = 1 ] && { echo; "$HERE/helix" doctor || true; }
exit 0
