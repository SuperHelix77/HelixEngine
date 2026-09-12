# Compound routing: cost boundary and shell-state falsifier

## Decision

Do not broaden native command interception merely to raise its activation
count. The [fresh Sol pair](SOL_SOURCE_NATIVE_PAIR_20260913.md) contains a real
routing gap, but only 2,539 bytes of candidate shell output. Its edit-producing
segment alone exceeds the entire 65%-saving output budget. Command capture
coverage and whole-task economics are separate requirements.

The next routing implementation requires both a materially reducible output
surface and a demonstrated semantics-preserving execution boundary. Neither
claim follows from recognizing an additional command name.

## Naive nested-shell capture fails offline

One tempting universal adapter executes the complete original command as
`shell -c source` inside Engine. It preserves shell grammar without a new
parser, but does not automatically preserve the original caller's shell state.

Six synthetic local zsh comparisons produced three mismatches:

| Existing caller state / command | Direct execution versus nested shell |
|---|---|
| Caller-defined function | Different: nested shell cannot find the function |
| Unexported variable | Different: nested shell loses the value |
| `nounset` shell option | Different: native error becomes successful empty output |
| Exported variable | Equal in this probe |
| Failure short-circuit | Equal in this probe |
| Quoted heredoc | Equal in this probe |

**OBSERVED:** These are six deterministic process comparisons with no hosted
model calls. The setup represents state established before interception. They
falsify a naive extra-shell transformation, not the existing conservative
adapter. Passing the latter three cases does not establish general shell parity.
The current adapter guards executable resolution and leaves unsupported syntax
native; these tests do not justify weakening that behavior.

The harness never executes archived model-authored commands. It uses synthetic
fixtures and five-second process timeouts. Evidence is retained under
`research/compound-shell-boundary-20260913` in the enclosing workspace.

- Probe SHA-256:
  `5a027df78d7bad7379c09c5e69bca57427abb4e541f9e3531360c33475e8478c`
- Result SHA-256:
  `b56e5efbe93d702311510da649cba0efe6e008f6ac34208b86309a50373c5a52`

## Required gates before changing execution

An independent Luna audit replayed all eight saved command records through
`route()` as data: both their recorded shell wrappers and extracted command
payloads returned native fallback. It executed no archived commands. Besides
heredocs and compound quotes, blocked leaves include `pwd`, `sed`, `shasum`,
`python -m py_compile`, and the glob-bearing search command. The replay's current
PATH did not resolve `python`; this is not evidence about resolution during the
original model run. Its payload syntax already explains candidate fallback.

The existing 25 interceptor tests passed. They cover bounded cwd/environment,
short-circuit, stdin and execute-once behavior, but not arbitrary heredocs or a
direct cancellation case in that test file. The separate runtime's coverage
must not be inferred from this narrowly scoped test review.

Independent audit SHA-256:
`a91c367b067a6b57d7123e970470813ec1978da9134a7d420596572966f11b3d`.
Its retained path is `research/compound-route-audit-20260913/evidence.md`.

Any proposed replacement must preserve command ordering, shell-local state,
working directory, environment, short-circuiting, quoted data and heredocs,
exit status, cancellation ownership, permissions, and execute-once behavior.
Telemetry or memory failure after execution must never rerun the command.
Exact retrieval must remain available and must not recursively reduce itself.

First qualify the exact transformation offline, then verify what reaches the
next native model request. A new hosted economic pair is justified only after
the remaining measured cost could plausibly meet the preregistered objective.
The six-case test does not close those broader gates.

No routing code or production configuration changes accompany this audit.
No model median, self-activation or v0.2 qualification is claimed.
