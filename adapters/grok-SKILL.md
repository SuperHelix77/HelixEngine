---
name: helix
description: >-
  Use Helix Engine for code investigation in Grok. One local hstep call returns
  callers, callees, tests, coverage, and symbols. This install's memory is
  __HELIX_HOME__/memory.db. Use when locating functions, tracing calls,
  or recalling prior HELIX evidence.
---

# Helix Engine (Grok Build)

This agent's engine lives at `__HELIX_HOME__`. Claude Code's engine is a
separate installation and **must not share this memory database**.

## Start Grok

`helix-grok` launches **Grok Build**, not Claude Code. Start it in the
workspace you intend to inspect. The host hooks are installed separately.

```sh
helix-grok
HELIX_HOME="__HELIX_HOME__" "__HELIX_HOME__/bin/hstep" need "who calls parse" callers:parse tests:parse
HELIX_HOME="__HELIX_HOME__" "__HELIX_HOME__/bin/hmem" q "terms"
```

`hstep` accepts `callers:NAME`, `callees:NAME`, `tests:NAME`,
`coverage:FILE`, and `sym:FILE NAME`. `hmem raw N` recovers exact evidence.
Prefer `hstep` over repetitive grep/read chains when the question is
deterministically answerable.

## Memory and hook semantics

Hooks archive the session to `__HELIX_HOME__/memory.db` on Stop/PreCompact/
SessionEnd. Grok ignores passive SessionStart stdout; a bounded prior capsule
is delivered after the **first Bash tool result** if available. It cannot be
injected before the first model inference. For immediate recall, query
`hmem q` explicitly. Never use `~/.claude-lean/memory.db`.

Follow the complete setup and smoke-test instructions in
`__HELIX_HOME__/GROK.md`. Tool hooks do not, by themselves, mean the entire
Grok agent loop runs under HELIX's deterministic scheduler.
