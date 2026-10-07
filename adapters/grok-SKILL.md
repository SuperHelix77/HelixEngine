---
name: helix
description: >-
  Use Helix Engine for code investigation in Grok. One local hstep call returns
  callers, callees, tests, coverage, and symbols. This install's memory is
  __HELIX_HOME__/memory.db. Use when locating functions, tracing calls,
  or recalling what Helix stored for this agent.
---

# Helix Engine (Grok)

This agent's engine lives at `__HELIX_HOME__`. Claude Code's engine at `~/.claude-lean` is a different install and a different database.

Set `HELIX_HOME=__HELIX_HOME__` before any Helix command. The launcher is `helix-grok` (it does not replace the `helix` command Claude uses).

## Investigate in one call

From the project you are reading:

```sh
HELIX_HOME=__HELIX_HOME__ helix-grok
# or the binaries directly
HELIX_HOME=__HELIX_HOME__ $HELIX_HOME/bin/hstep need "who calls parse" callers:parse tests:parse
HELIX_HOME=__HELIX_HOME__ $HELIX_HOME/bin/hmem q "terms"
```

`hstep` accepts `callers:NAME`, `callees:NAME`, `tests:NAME`, `coverage:FILE`, `sym:FILE NAME`. `hmem raw N` returns the exact stored text for handle N.

Prefer `hstep` over a chain of grep and file reads when the question is "who calls this", "what tests cover this", or "where is this defined".

## Memory

Hooks archive the session into `__HELIX_HOME__/memory.db` on stop and compact. Query it with `hmem q`. Do not read or write `~/.claude-lean/memory.db`.
