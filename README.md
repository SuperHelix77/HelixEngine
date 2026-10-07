# Helix Engine

A local semantic execution runtime for coding agents, built around one idea: **frontier-model inference should be the escalation path, not the default loop.** Helix runs a lean Claude Code session whose tool results are typed, bounded and lossless-recoverable, answers multi-step code investigations locally in one call, and keeps history in an addressable memory instead of replaying it.

> This repository replaces the earlier Helix Engine v0.1.0 (a local command-execution / receipts app). The old code is preserved at tag `v0.1.0` and branch `legacy-v0.1.0`.

## What it does

| Layer | What | Where |
|---|---|---|
| Lean session | one rtk-backed shell tool, ~230-token static ultra-terse prompt, no per-turn injection (`helix doctor --live` enforces it) | `helix`, `sh_mcp.py`, `compose.py`, `terse/` |
| Tool output | rtk byte compression + **semantic receipts** (tests, compiler errors, grep, JSON, diffs) with declared loss and exact `raw N` recovery | `lib/reduce.py`, `sh_mcp.py` |
| Code intelligence | import/def/scope-resolved callers, callees, tests, coverage; `hstep` = one call -> one typed EvidencePacket | `lib/hops.py`, `lib/hcontrol.py`, `bin/hstep` |
| Core protocol | GoalGraph / GoalStep / ExecutionEnvelope / EvidencePacket / ClaimProposal / DecisionReceipt; deterministic controller that escalates instead of guessing | `PROTOCOL.md`, `lib/hcore.py` |
| Memory | lossless SQLite+FTS5 archive, passage retrieval, capsule restore, claim ledger (STALE on dependency change, SUPERSEDED) | `lib/hmem.py`, `lib/claims.py`, `bin/hmem` |
| Autonomy | frontier preflight -> GoalGraph, single-agent scheduler, EV-based escalation ladder with micro-escalation and de-escalation, pre-tool interception under equivalence contracts | `lib/preflight.py`, `scheduler.py`, `escalate.py`, `intercept.py` |
| Host adapters | Claude Code hook adapter and a Grok Build adapter (both opt-in, reversible), standalone reference adapter | `adapters/` |
| Local models (optional) | private Ollama on a separate port for `ask`/`summ`/`docgen` (verified docstrings); optional Laya decision-model experiments | `bin/`, `laya/` |

Multi-agent scheduling is intentionally not implemented in this version.

## Install (short)
```sh
git clone https://github.com/SuperHelix77/HelixEngine.git ~/helix-engine
cd ~/helix-engine && ./install.sh        # checks prerequisites, generates settings, links `helix`
helix doctor                              # verify
helix                                     # start a lean Helix session
./install.sh --grok                       # optional: Grok hooks + helix-grok, leaves `helix` alone
```
Full instructions, prerequisites, the Grok install, optional components and troubleshooting: **[INSTALL.md](INSTALL.md)**.

## Measured results
Final Helix Core (Laya not involved), 60 code-investigation tasks over 4 repos (HelixEngine v0.1.0, HelixContext, click, requests), default Claude Code as baseline, blind-judged correctness, bootstrap CIs over tasks. Full tables, per-family and per-repo breakdowns: [`bench/TOKEN_METRICS.md`](bench/TOKEN_METRICS.md); raw runs and a no-API report regenerator: [`bench/`](bench/README.md).

| | dev set (32 tasks) | round 2 (28 tasks) |
|---|---|---|
| input + cache tokens | **-94.7%** (CI 93.7..95.7) | **-94.9%** (93.8..95.8) |
| total tokens | -94.4% | -94.5% |
| output tokens | -45% | -41% |
| list cost | $4.50 -> $0.32 | $3.90 -> $0.29 |
| frontier turns / wall-clock | -11% / -24% | -14% / -32% |
| correct (blind judge) | 69% -> 95% | 93% -> 95% |
| correct answers per million tokens | 5.7 -> 140 | 7.5 -> 141 |

Also measured: long-session carrying cost modeled on a real 425-step transcript (-95.5% vs no compaction, -76% vs native compaction); memory-vs-summary question answering on held-out transcript slices (29 vs 11 correct of 31; after two compactions early facts 22 vs 5 of 30); chain-task wall-clock -69% (n=2).

### Read the limits
- Output savings are modest (41-45%) on the broad suite; default Claude is already terse on small tasks. Input+cache (~95%) is the robust result. 95% on *all* of input/output/cache is **not** met.
- "dev" tasks were used to find and fix defects. Round 2 was a fresh seed whose first pass scored 75/84 (89%); fixes generic to its failures were then applied and everything re-run, so round 2 is not a clean hold-out.
- Baseline is n=1 per task; the task families favour code navigation. Numbers are CLI token counts and list cost, **not** your subscription meter.
- The adapter hooks are tested against synthetic hook payloads and in one real session; they are opt-in (`helix hooks install`).
- Laya (a non-generative decision model) is optional and experimental: zero-shot it was no better than rules for code classification and worse than BM25 for reranking; a fine-tuned router reached 98.4% on unseen phrasings. A zero-shot training run did not complete (GPU memory), so nothing here depends on Laya.

## Privacy
Memory lives in `memory.db` on your machine (git-ignored). Nothing is uploaded anywhere. Benchmarks here use only public repositories.

## Status and license
Release candidate `0.2.0-rc1` (see `CHANGELOG.md`). Tests: `python3 -m unittest tests.test_engine`. No license has been selected for this repository yet, so all rights are reserved until one is added.
