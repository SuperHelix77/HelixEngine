# Installing Helix Engine

## 1. Prerequisites
| Need | Required? | Notes |
|---|---|---|
| macOS (Apple Silicon recommended) | recommended | The engine is portable Python/zsh; the sandboxed benchmark runner uses macOS `sandbox-exec`. Linux works for the engine, untested for the rest. |
| zsh | yes | the `helix` launcher is a zsh script (default shell on macOS) |
| Python 3.9+ with sqlite FTS5 | yes | the macOS system Python (3.9) is enough; `install.sh` checks FTS5 |
| Claude Code CLI, logged in | yes | https://docs.claude.com/en/docs/claude-code ; run `claude` once to sign in. Helix uses your own plan. |
| rtk | recommended | `brew install rtk`. Without it Helix still works with smaller savings. |
| Ollama | optional | only for the local `ask` / `summ` / `docgen` tools |
| Python venv + `laya` (+torch) | optional | only for the experimental Laya components (~0.8 GB checkpoint download) |

## 2. Install
```sh
git clone https://github.com/SuperHelix77/HelixEngine.git ~/helix-engine
cd ~/helix-engine
./install.sh
```
`install.sh` runs preflight checks, generates `settings.json` (the profile used by `helix` only), creates `run/`, links `~/.local/bin/helix`, and runs `helix doctor`. It does **not** touch `~/.claude/settings.json`.

Options: `--prefix DIR` (link elsewhere) | `--no-link` | `--skip-checks` | `--with-local-models` (starts a *private* Ollama on port 11500 and pulls `qwen3:1.7b`; your normal Ollama is untouched) | `--with-laya` (creates `./venv` and installs `laya`).

If `~/.local/bin` is not on your PATH: `echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc`.

## 3. Verify
```sh
helix doctor            # offline invariants: no per-turn injecting hooks, protocol hash, adapter snippet, rtk, local server
helix doctor --live     # also runs one real session and checks that nothing is injected per turn (uses a few hundred tokens)
python3 -m unittest tests.test_engine     # 100+ tests
```

## 4. Use
```sh
helix                              # interactive lean session (static ultra-terse prompt, one shell tool)
helix -p "which functions call parse() in src/?"     # one-shot
helix --terse full | lite | off    # terse level (default ultra), or HELIX_TERSE=...
CL_MODEL=haiku helix               # pick the model (default sonnet)
helix --handle -p "..."            # answers as @N handles of exact tool output (print mode)
```
Inside a session the model has: `hstep need "objective" callers:NAME tests:NAME coverage:FILE ...` (one call = one typed investigation packet), `outline`, `sym`, `callers`, `inv`, `ed`/`ins`/`rep`, `raw N A-B` (exact recovery of anything that was compressed), `hmem q "terms"` (memory), and optionally `ask`/`summ`/`docgen`.
Goal graphs: `helix preflight "goal"` (one frontier call -> validated GoalGraph) and `helix graph run G.json`.

## 5. Apply Helix to your normal Claude Code (optional, explicit, reversible)
Nothing above changes your default `claude`. To add rtk rewriting, capsule restore at session start (resume/clear/compact), and memory consolidation at PreCompact/Stop to **your** `~/.claude/settings.json`:
```sh
helix hooks print                  # see exactly what would be merged (writes nothing)
helix hooks install                # merges; backs up to settings.json.bak-helix-<timestamp>; idempotent; keeps your other hooks
helix hooks uninstall              # removes only Helix's entries (another backup is made)
```
`helix hooks install --settings /path/to/settings.json` targets a different file (e.g. a project's `.claude/settings.json`).

## 6. Optional: local models
```sh
./install.sh --with-local-models   # or: helix lm-up && OLLAMA_HOST=127.0.0.1:11500 ollama pull qwen3:1.7b
helix lm-down                      # stops only the private server on :11500
```
The local model writes docstrings (`docgen --verify` rejects hallucinated identifiers), answers narrow questions (`ask`), and summarizes (`summ`). Its answers are not checked by Claude; the docstrings were ~20% wrong in our evaluation, so review them.

## 7. Optional: Laya experiments
`./install.sh --with-laya`, then see `laya/` (data generators, evaluators, training wrapper with MPS cache release, int8 helper). Experimental; nothing in the core requires it.

## 8. Reproduce the benchmarks
See `bench/README.md` (regenerate the report from included raw results with no API calls, or re-run the campaign on your own plan).

## Troubleshooting
- `helix: command not found` -> add `~/.local/bin` to PATH (see step 2).
- `claude: command not found` / not logged in -> install and run `claude` once.
- `You've hit your session limit` in benchmark runs -> your plan's usage limit; the runner stops and records nothing; wait for the reset.
- `rtk rewrite` seems to do nothing -> rtk exits with code 3 when it rewrites; Helix accepts 0 and 3. Check `rtk rewrite "git status"`.
- `hmem` or doctor errors on a read-only/sandboxed database -> reads never need write access; if you see a write error, update to this version.
- MPS out-of-memory while training Laya -> stop other GPU-heavy processes (e.g. a stuck Ollama server), then rerun `laya/train_rounds.sh` (it resumes after finished rounds).
- Python < 3.9 -> install a newer Python and set `HELIX_PYTHON=/path/to/python3`.

## Uninstall
`./uninstall.sh` (removes the link), `helix hooks uninstall` (if you installed hooks), then `rm -rf ~/helix-engine` (this also deletes your local `memory.db`).
