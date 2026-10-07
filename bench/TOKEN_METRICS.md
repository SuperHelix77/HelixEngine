# Helix Core token-saving metrics (final code, Laya NOT involved)

Baseline = default Claude Code (Read/Grep/Glob), same model, same tasks. Helix L2 = `helix` engine: one shell tool, static ultra-terse prompt, `hstep` investigations, semantic reduction, rtk. L1 = engine with basic helpers only (no `hstep`).
Tasks: read-only code-intelligence questions over 4 repos (HelixEngine, HelixContext, click, requests), 7 families; truth by an independent textual method cross-checked with AST. Correctness: blind LLM judge, same rubric for every condition. CI: 95% bootstrap over tasks. Baseline n=1/task, L2 n=3/task.

| set | input+cache (95% CI) | cache write | cache read | output (95% CI) | total tokens (95% CI) | list cost | turns | wall | correct | correct answers / M tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| dev, 32 tasks, L2 | 94.7% (93.7..95.7) | 95.7% | 94.4% | 45.3% (31.2..57.4) | 94.4% (93.3..95.4) | $4.50 -> $0.32 (92.8%) | 11% | 24% | 69% -> 95% | 5.7 -> 139.6 |
| dev, 32 tasks, L1 | 95.2% (94.1..96.1) | 94.7% | 95.3% | 47.5% (30.8..59.7) | 94.9% (93.7..95.9) | $4.50 -> $0.35 (92.2%) | 12% | 32% | 69% -> 75% | 5.7 -> 120.7 |
| round-2, 28 tasks, L2 | 94.9% (93.8..95.8) | 95.7% | 94.6% | 40.8% (26.8..52.2) | 94.5% (93.3..95.5) | $3.90 -> $0.29 (92.6%) | 14% | 32% | 93% -> 95% | 7.5 -> 140.8 |
| round-2, 28 tasks, L1 | 95.9% (95.4..96.5) | 95.0% | 96.2% | 52.1% (41.8..60.2) | 95.7% (95.0..96.3) | $3.90 -> $0.27 (93.1%) | 19% | 37% | 93% -> 84% | 7.5 -> 156.0 |

## How to read this (limits)
- "dev" tasks were used to find and fix defects; "round-2" was a fresh seed whose FIRST pass (pre-fix) scored 75/84 = 89% for L2. Fixes generic to the failures were then applied and everything re-run, so round-2 is **not** a clean hold-out any more; the final numbers describe the shipped code.
- Defects found and fixed this way: string references in tests (mock.patch paths) missed; conditional module-level defs missed; callees mixed classes/ambiguous names; task definitions that asked for unique names without saying so; an `@overload`-stub docaudit task (dropped).
- Output savings are modest (41-45%): default Claude is already terse on these small tasks. Input+cache savings (~95%) are the robust result.
- Savings are on tokens/list cost reported by the CLI. They are not a measurement of your subscription meter (cache pricing, weighting and quota rules differ).
- L1 (basic helpers) is nearly as cheap as L2; `hstep` mainly buys correctness on the dev set (75% -> 95%), less so on round-2 (84% -> 95%).

## Long-session carrying cost (modeled on this session's real transcript, 427 model steps)
No compaction 46,487,279 carried tokens | native compaction @40k: 8,664,800 (81.4% less) | Helix memory (capsule + 12-unit window + lookups): 2,103,846.0 (95.5% less; 76% less than native compaction). Assumptions in `bench/carry_model.py`.

## Other measured results
Latency (n=2/cell): wall-clock 50.4s -> 15.6s (-69%) on 3 chain tasks. Two successive compactions: iterated summary 14 -> 5 correct on early facts (later slice 12 wrong); archive+capsule 22 / 27 correct. Memory vs summary on held-out transcript slice: 29 vs 11 correct of 31.
