# v0.2.0 goal gate

Active user objective, 2026-09-12: a fully functioning installable application
with at least **65% median input and 65% median output savings for each model**.
Capability, agentic workflow and ordinary model-written final answers remain
mandatory. This supersedes the older 75% release threshold for Sol/Luna; it does
not waive any parity or scope requirement. Astra High and XHigh remain separate.
Luna High, Sol High and both Astra efforts must not inherit each other's results.

## Completion evidence required

| Requirement | Evidence required before release | Current disposition |
|---|---|---|
| One Codex integration pattern | Installed-client parent/child dispatch, exact delivered bytes and recovery | Bounded POSIX command cases pass; broader platform/approval behavior incomplete |
| Install, update, remove | Built wheel and clean installation smoke on macOS/Linux/Windows; preserved user config and shortcuts | v0.1 packaging exists; v0.2 managed project setup in development |
| Engine on/off | Actual new-command behavior plus live HUD state | Existing tests pass; preserve through v0.2 integration |
| Memory/reducers/plans | Persistent exact evidence, invalidation, restart, failure and no-rerun checks; costs charged | Core components exist; real lifecycle economics still need qualification |
| Parent/child telemetry | Native lineage, per-response deduplication, complete declared measurement windows | Parent suffix audit passes; historical/full-tree completeness unestablished |
| Economics per model | Fresh paired complete-workflow native receipts over the fixed task cohort; both medians >=65% | No model qualified |
| Capability/workflow/finals | Behavioral, adversarial, recovery and final-author checks on every accepted pair | Finite development checks only; not release parity |
| HUD and current prices | One savings graph per model, separate effort/cohort visibility, complete cost anatomy, explicit unknowns | Research/release HUDs exist; final v0.2 dataset and UI acceptance pending |
| Public delivery | CI, wheel/sdist/checksums, guides and GitHub release; Helix identity; no research ledger bundled | v0.1 exists; v0.2 not published |

Completion means evidence for every row, not a version bump or only green unit
tests. Reject capability regressions, stale evidence, caller-rendered substitute
finals and hidden retries. Report uncached input and effective cost separately
from cached-sensitive total-input percentages. Retain negative task cells in
the declared cohort; do not select an easier cohort to reach the target.

## Evidence correction at goal intake

The ladder prose and a bounded reviewer summary described Astra's 83.07/60.02
varied-coding median too broadly. The actual `astra-varied-coding-v1-20260910`
manifest and audit classify it as **source-only caller transfer**. It is a
mechanism lead, not accepted normal-final release evidence. Luna ACK V5's
98.30/75.04 likewise uses a compact policy JSON answer and a reused development
control; it cannot automatically qualify an ordinary-final cohort.

The clearly identified bounded ordinary-final Astra cold-recovery capsule is
78.29/61.75 (High, one task), not a model median. Sol's indexed maintenance V3
is 66.02/47.99 (one task) and has an uncached-input cost regression. Astra XHigh
maintenance is 32.30/-0.46 (one task). These results do not pass this goal.

Some historical runner paths point into a removed temporary checkout. Retained
receipts can guide architecture; missing source must be recovered from its bound
Git revision or replaced with freshly bound work before rerunning anything.

## Execution order

1. Make the existing shared adapter installable and removable without manual
   research-path edits or permission/trust shortcuts.
2. Close native integration and whole parent/child measurement gaps using offline
   dispatch and recovery probes first.
3. Transfer a measured mechanism into the actual installed lifecycle. Keep model
   effort, semantic freedom and ordinary final authorship intact.
4. Run the smallest fresh preregistered pair that can falsify that transfer. Count
   parent preparation/adjudication and children, not only reduced command bytes.
5. Expand a surviving policy through the fixed cohort, freeze each qualified
   model/effort, and ship only after all release rows have direct evidence.

Do not spend native calls to rediscover a failed source-only/final-shape boundary
or a small-output fixture with no material removable cost. Do not stop useful
independent scrutiny to make a cost result attractive.

## First goal-cycle result

Implemented `helixengine codex install|status|remove --project PATH` for the
existing shared POSIX adapter. Setup preserves unrelated hooks, refuses modified
or unmanaged Helix entries, keeps hash-named backups, uses a cooperative writer
lock and checks original bytes before atomic publication. It does not claim
protection against every uncooperative concurrent writer, write native trust
hashes, or change permissions. Windows hook setup remains explicitly unsupported.

**234 tests passed in 12.16 seconds**, including malformed configuration,
concurrent modification, failed publication, idempotence and removal checks.
An isolated wheel build and an installed-wheel smoke outside the source checkout
passed: setup, status, repeated setup, one actual Engine shell dispatch, and
removal. The installed module resolved inside the fresh venv's site-packages.
This is a packaging/dispatch component check, not a new native model benchmark.

The first build without isolation stopped because the host lacked the `wheel`
dependency. The subsequent standard isolated build succeeded. A bounded worker's
patch submission also failed; the root recovered its proposed patch, corrected
implementation/test defects, and ran the checks. Both failed attempts remain
research overhead; no hosted benchmark call was spent.

The local artifact is still versioned 0.1.0 development source, not a published
v0.2 release. Its wheel SHA-256 is
`cddd931f7ef6f3921e888eb0cdc1ce5866466c30a41343a93fb25eaac9a6efaf`.
Exact smoke/build evidence is retained outside the release package in
`research/v020-release-qualification-20260912/`.
