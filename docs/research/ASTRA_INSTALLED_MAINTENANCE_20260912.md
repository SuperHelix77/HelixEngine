# Astra High: installed maintenance pair, 2026-09-12

**OBSERVED: no economic qualification.** Both arms passed the 94-case independent evaluator and protected-file checks, produced byte-identical repairs, and supplied normal model-written final answers. Both used five native model segments and seven commands. Every observed command used native passthrough; the enabled arm executed zero Engine commands. This is one known development task, not general capability parity or a model median.

| Counter | Control | Engine enabled | Saving |
|---|---:|---:|---:|
| Total input | 106,458 | 106,628 | -0.16% |
| Cached input | 92,032 | 80,256 | — |
| Uncached input | 14,426 | 26,372 | -82.81% |
| Output | 1,453 | 1,782 | -22.64% |
| Reported reasoning output (subset) | 50 | 56 | — |
| Wall seconds | 61.60 | 67.04 | — |

The small total-input difference is not a causal Engine compression effect. Cache differences and different generated probes remain visible confounds. Neither arm spawned a child. Unique native per-response counters sum exactly to the corresponding CLI turn totals. No paid retries were made. Control retained passive hooks; this is not an uninstalled baseline.

## Observable cost anatomy

Both arms read 27,699 source/test bytes in completed tool events. The supplied-test output was only 98 bytes. Source text remained exact, and generated novel probes remained available. The extra-probe segment used 800 output tokens in control and 1,119 with Engine enabled; its command text was 2,263 versus 3,059 bytes. These are observed segments and visible code sizes, not an attribution of hidden reasoning.

| Model segment | Control input / output | Enabled input / output | Visible action |
|---|---:|---:|---|
| 1 | 15,921 / 92 | 15,896 / 110 | Locate task files |
| 2 | 16,111 / 111 | 16,103 / 96 | Read source/tests and status in a batch |
| 3 | 24,103 / 343 | 24,060 / 354 | Apply patch and execute supplied tests |
| 4 | 24,520 / 800 | 24,488 / 1,119 | Generate/execute additional probes and review diff |
| 5 | 25,803 / 107 | 26,081 / 103 | Normal final answer |

**INFERRED:** more pytest output filtering cannot materially address this trace. The next candidate must reduce repeated setup/context exposure or deterministic probe scaffolding while retaining semantic test choice, adequacy review and normal model-authored completion. Broader shell routing alone is infrastructure, not a demonstrated route to 65/65.

**CONDITIONAL bound:** 65% input saving permits 37,260.3 input tokens against this control. If two future calls each retained the observed roughly 15.9k initial charge, only about 5.4k combined tokens would remain for added evidence/history. This is a planning bound, not proof that the initial charge is irreducible or that a two-call policy preserves capability. A new native comparison requires a concrete candidate and offline gates first. Do not force the control to do unnecessary work.

## Installation and wire evidence

Installed wheel from Engine commit `64ab3d38382e4076eb46e146d4b98a71fd8abc5f`; SHA256 `5ab120196d21b5c9c8ab50003c4796d70ccf1c5cc95df8c911d2176cdff86263`. The runner uses the installed package, isolated HOME/CODEX_HOME, neutralized Git overrides and explicit local certifi/pytest dependencies. Offline loopback verified 9,101 raw bytes versus 3,461 packet bytes in the actual next request, plus exact raw recovery. This output fixture was not imposed on either native arm. The native model directly fixed the bug and never emitted that failing baseline command.

Failed offline attempts are retained separately. They exposed user-site dependency leakage, a receipt-selection defect, and a distinction between final tool-event output and complete wire output. A mistaken baseline-count assertion was corrected against retained output. None is hidden or counted as a free successful attempt. Root/worker inference, offline execution, storage, retrieval and recovery are outside the paired task counters; total effective cost and included-plan quota saving remain unknown.

## Control final answer

Updated only `workflow_memory.py`:

- Added `match_mode='all'` after `limit`; `any` uses OR between quoted literal tokens.
- Invalid modes raise `ValueError`, including for empty queries.
- Preserved existing validation, project isolation, ordering, limits, evidence references, and corruption checks.

All 23 supplied tests passed. Additional checks passed for operator-like queries, Unicode, exact evidence, and corruption outside the result limit. `git diff --check` passed.

No unresolved issues.

## Engine-enabled final answer

Updated `Memory.search` in `workflow_memory.py` with `match_mode='all'` after `limit`. `any` uses OR between quoted literal tokens; invalid modes raise `ValueError`, including for empty queries.

Existing validation, integrity checks, project isolation, ordering, limits, and evidence references remain intact. Only `workflow_memory.py` changed.

Validation: 23 supplied tests and 97 additional edge-case checks passed; `git diff --check` passed. No unresolved issues.

## Release disposition

Retain this negative result. Do not replace prior scoped wins or promote this case into a seven-cell median. Capability tests are finite; v0.2 remains unqualified until the full functionality and per-model median gates are verified.
