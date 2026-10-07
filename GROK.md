# HELIX Engine for Grok Build

This guide is for humans and Grok agents installing HELIX into **Grok Build**. It installs a Grok host adapter and code-investigation tools, not a replacement model or a fully native HELIX-controlled Grok agent loop.

**Status:** Experimental adapter. Do not treat usage savings, raw decode throughput, or semantic-turn fusion as proven from installation alone.

## Prerequisites

- Grok Build CLI, logged in: https://x.ai/cli (verify with `grok --version`).
- Git, zsh, Python 3.9+ with SQLite FTS5.
- Optional `rtk` (macOS: `brew install rtk`) for compatible output filtering.
- **Claude Code is not required.** Grok uses a separate HELIX memory database.

## Install (does not modify Claude)

```sh
git clone https://github.com/SuperHelix77/HelixEngine.git ~/.grok/helix-engine
cd ~/.grok/helix-engine
./install.sh --grok
```

If a checkout already exists, inspect changes before updating. Do not overwrite its local `memory.db`.

The installer creates or updates:
- `~/.local/bin/helix-grok` — a launcher for the real **Grok CLI**, not Claude;
- `~/.grok/hooks/helix.json` — Grok-specific hooks (refuses foreign files, backs up its own);
- `~/.grok/skills/helix/SKILL.md` — the HELIX skill with the actual install path;
- a separate memory database in this checkout after an eligible session is consolidated.

It does **not** replace `~/.local/bin/helix` or edit `~/.claude/settings.json`. Installation needs no model/API inference.

## Validate the installation

```sh
grok --version
helix-grok --version
helix-grok doctor
helix-grok hooks print
python3 -m unittest -v tests.test_engine
```

From the relevant project directory, run `helix-grok` to start Grok. Open Grok's `/hooks` panel, reload with `r` or start a new session, and verify the HELIX hook source. Grok can also load hooks from Claude settings and project directories; **check for duplicate hook registrations** before interpreting timing or quota observations.

Ask Grok to read its HELIX skill and answer a bounded code-investigation question. The semantic tools can also be called explicitly:

```sh
HELIX_HOME="$HOME/.grok/helix-engine" "$HOME/.grok/helix-engine/bin/hstep" need "who calls parse" callers:parse tests:parse
HELIX_HOME="$HOME/.grok/helix-engine" "$HOME/.grok/helix-engine/bin/hmem" q "past project decisions"
```

`hstep` returns a bounded, typed evidence packet; `hmem` searches this Grok install's memory.

## Grok-specific hook semantics

Grok Build differs from Claude Code:

- **Passive SessionStart stdout is ignored by Grok.** HELIX restores a bounded project capsule once via the first eligible **Bash PreToolUse** hook. Grok receives that `additionalContext` **after the tool result**, not before its first model inference. For earlier recall, ask `hmem q` explicitly.
- `run_terminal_command`, `read_file`, `search_replace`, and `grep` normalize to HELIX host tool names. Grok's published PreToolUse hook matches the shell category `Bash`.
- Transcript conversion runs only at `Stop`, `PreCompact`, and `SessionEnd`, not on every tool call.
- Ingestion uses **source-transcript-specific watermarks**; retrieval remains project-scoped, preventing a previous session's higher sequence number from suppressing a new session's initial records.
- The Grok adapter explicitly sets `HELIX_MEM_DB` to this checkout's `memory.db`. Intentional Grok-only customization uses `HELIX_GROK_MEM_DB`. It does not share Claude's `~/.claude-lean/memory.db`.
- Optional runtime-hook failures fail open to avoid breaking a host turn; hook **installation failures** should surface as errors. Inspect actual hook output rather than assuming success means the model saw the capsule.

Grok hook specification: https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/10-hooks.md

## Troubleshooting

| Symptom | Action |
|---|---|
| `hook not executed: required env var(s) not set` | Reinstall with `helix-grok hooks install`; HELIX hook commands use absolute paths without `$VAR` references. Reload `/hooks`. |
| `helix-grok` not found | Add `~/.local/bin` to PATH. |
| Grok CLI missing | Install/sign in to Grok Build. The launcher never falls back to Claude. |
| No capsule on first assistant response | Expected: Grok ignores passive SessionStart stdout. Use `hmem q` or wait for the first shell tool result. |
| Memory empty or wrong project | Verify `HELIX_HOME` and the Grok checkout's `memory.db`. Fresh installs have no archived history yet. |
| Extra or duplicate hook calls | Inspect `/hooks` for Grok, Claude, and project hooks. |
| No tool rewrite | Not all operations have an equivalence contract; shell interception is conservative. `hstep` remains a separate explicit tool. |

## Remove safely

```sh
helix-grok hooks uninstall
cd ~/.grok/helix-engine
./uninstall.sh
```

The Grok HELIX skill may be removed separately after confirming it is HELIX-generated. Back up `memory.db` before deleting the checkout; it contains private conversation history. Do not commit local `memory.db`, session archives, checkpoints, private Laya training data, or credentials.

## Measuring performance

To validate a Grok efficiency gain, compare matched workloads using full model-request counts, real tool calls, cached/uncached input, output tokens, wall time, and verified correctness. A continuous Thinking UI episode is not proof of one underlying frontier inference.