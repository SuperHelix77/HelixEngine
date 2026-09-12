# First native interception pilot: coverage miss

**OBSERVED — not a Helix savings result.** One new GPT-5.6 Luna High coding
fixture was run with interception OFF and ON. Both produced repairs that passed
all five independent semantic probes and nine visible tests, preserved contract
tests, and authored ordinary prose final answers. Neither arm spawned children.
The candidate produced **zero Engine executions**: all its commands contained
compound shell syntax which the conservative router correctly left native.

| Native counters | OFF | ON | Raw delta (less is positive) |
|---|---:|---:|---:|
| Total input | 96,334 | 79,839 | 17.12% |
| Cached input | 79,360 | 62,208 | 21.61% |
| Uncached input | 16,974 | 17,631 | -3.87% |
| Output, including reasoning | 1,939 | 1,937 | 0.10% |
| Reported reasoning output | 925 | 914 | 1.19% |
| Native model segments | 6 | 5 | — |
| Commands | 4 | 3 | — |
| Engine executions | 0 | 0 | — |
| Wall seconds | 48.77 | 48.60 | — |

These deltas are descriptive run variation, not attributable optimization.
Per-response native receipts reconcile exactly with each CLI turn total. No
runner relaunch occurred. The built-in hosted provider retained its own default
transport retry behavior; no native error events or stderr were observed. This
does not prove the service performed no internal retry.

## What failed

The candidate issued its test and inspection in one command:

```sh
python3 -m pytest -v test_reducer.py && git diff -- reducer.py test_reducer.py TASK_PROMPT.txt && git status --short
```

The shared router recognized only simple argv commands. Its refusal of `&&`
preserved shell behavior but excluded the useful interception surface. Asking
Luna to split commands would change the workflow and pay model instruction cost;
the correction belongs at the same shared backend boundary.

Two runner defects also need correction before another paid pair:

* The installed client persisted workspace trust metadata during the first arm.
  The recorded configuration hashes therefore differ. Task, source, tests,
  model, effort, hook, and runner hashes match, but the raw configuration gate
  remains failed; do not silently waive it.
* The disposable workspace had no Git repository. Both models attempted ordinary
  Git inspection and received Git usage errors. That artificial noise is not a
  legitimate target for claiming product savings. A future fixture should be an
  initialized, identically committed repository.

## Offline findings before the native pair

The runner was tested through the actual installed CLI against a bounded local
mock: one command, two provider requests, a native final message, and exact raw
recovery. The candidate's wire tool-output representation was 2,400 bytes versus
17,548 bytes. This is solely a delivery component check, with zero hosted model
calls. The earlier implementation passed 199 application tests.

The fixture's unrepaired starter failed 5/5 independent probes; an independently
constructed correct implementation passed them and all nine visible tests.
Review caught and fixed missing-child-identity accounting, and narrowed the
unsupported zero-transport-retry claim. Fixture/reviewer agent work is additional
research expenditure, not free work and not included in the paired task table.

## Implemented bounded correction

Admit only AND-only chains whose every leaf independently satisfies the existing
simple-command policy. Preserve each original leaf and the original shell's
`&&` execution. Re-evaluate executable/alias resolution at each leaf; keep a
leaf's `exec` inside a subshell so it cannot swallow the remainder. Keep every
other compound command native. Bind per-leaf receipts to the original thread and
tool identity plus a leaf ordinal. The same rule applies to parents and children,
independent of model.

`codex-foreground-v2` implements this in the existing adapter. The full application
suite passes **205 tests**, including exactly-once order, nonzero short circuit,
whole-chain function fallback with a working-directory mutation, unknown-leaf
fallback, quoted syntax rejection, and one/two-leaf stdin/environment/process
group preservation. Oversized chains remain native.

The actual installed CLI also passed a zero-hosted-call compound wire check:
one native tool call, two ordered Engine executions, 32,400 exact raw bytes and
3,454 bytes delivered to the next mock model request. Both leaf packets occur
exactly once in command order; both raw objects recover exactly. This is a
delivery-component result, not economic or semantic parity evidence.

The CLI's completed-command event had an empty aggregate in this compound probe,
although the next request contained both packets. Initial report generation
incorrectly required those surfaces to match. The report was recovered directly
from the existing request and Engine objects without executing either command
again. Future accounting must distinguish CLI display events from actual request
payload evidence.

Continuing qualification includes cancellation across platforms and broader
shell/tool coverage. No new hosted pair was launched after this correction.
The following remain the required boundaries: exactly-once order, nonzero short circuit, alias/function
fallback, unknown-leaf all-native behavior, quoted `&&`, stdin/environment/cwd,
process-group cancellation, raw short-output identity and exact recovery. No new
native benchmark is justified until this survives local tests and actual native
wire dispatch, and the runner's Git/configuration defects are corrected.

## Research overhead audit

The six observed research agents, including nested delegates, consumed 5,405,839
reported input tokens: 5,120,000 cached and 285,839 uncached, plus 58,923 output
tokens (34,125 reported reasoning tokens included in output). These are additional
to the paired task, not part of either arm's apparent saving. Unique native
response IDs were summed by actual thread. Root research usage remains unknown
because the existing parent observer has partial coverage; total project cost
is therefore incomplete.

This cycle did **not** demonstrate the user's research-efficiency target. Nested
delegation and repeated model-mediated integration expanded the cost markedly.
The root stopped further delegation, took over the bounded final checks, and
published `RESEARCH_OVERHEAD_AUDIT` in the research HUD. Future bounded worker
contracts should explicitly prohibit subdelegation and require escalation to the
root before expanding scope. No intelligence or savings qualification follows
from this operational correction.

## Qualification

Normal final authorship and these finite behavioral checks passed. General
intelligence/workflow parity, cohort medians, monetary/quota savings, and v0.2
release qualification remain unestablished. The research HUD event is
`BENCHMARK_REJECTED`, classification `COVERAGE_MISS_NOT_HELIX_SAVINGS`.

An additional, explicitly post-hoc check found that the native repair's empty
batch returns the original state and aliases its event mapping. The candidate
returns independent mappings. This exposes a gap in the finite checker against
the task's new-state wording, not evidence of general candidate superiority.
The extra observation is preserved separately from the preregistered checks.

The corrected future preparation was tested offline: a committed Git fixture
supports ordinary status/diff, predeclared project trust stops configuration
drift, and two debug prompt renders match after excluding only top-level message
IDs and creation timestamps. Raw debug outputs are retained. An initial raw-byte
equality assertion included those dynamic fields; adjudication was recovered
from saved outputs rather than rerunning model inference.

The frozen raw results, native segment receipts, visible commands, final answers,
fixture sources, hashes and adjudication remain in the private research workspace
under `research/interception-native-pilot-20260912/`. They are not release data.
