# Bounded recording transitions (development)

Helix can decide that a model call is unnecessary when the next action follows
mechanically from an explicitly armed recording contract. It does not decide
that arbitrary prose is unimportant, or infer permission from words like ACK.

The current action is **record exact data and issue a mechanical notification**.
It performs no shell commands, edits, approvals or semantic decisions. Ordinary
model-written final answers remain on the native path.

## Admission contract

An explicit caller arms a grant bound to a project, native thread, epoch,
authorization evidence and declared file dependencies. The grant requires an
explicit empty list of unresolved obligations. This declaration must represent
the actual user-authorized workflow; an empty list and an evidence hash are not
proof that the caller interpreted the task correctly.

Two exclusive modes are supported: exact expected steps, or a recording lease
for previously unknown observations. A lease accepts only a strict JSON envelope
with `schema: "helix.observation.v1"`, the current `epoch`, the next integer
`sequence`, and a string `payload`. The envelope is a data-ingestion protocol.
Instructions quoted inside payload remain historical data. Ordinary requests,
extra fields, duplicate keys, wrong sequence or changed epoch cannot silently
be classified as observations.

Exact native capture must succeed before transition acceptance. Grants and
records use the existing evidence store and completion chain. Identical native
delivery can replay; conflicting bytes cannot. A new semantic prompt invalidates
the lease. Historical records, dependency hashes and the externally retained
completion head are checked before accepting subsequent data.

## Native binding

`helixengine transition arm grant.json` stores a grant without activating a
native hook. Explicit `--activate-native --transcript PATH` also binds the
shared hook to a completed native semantic-turn checkpoint. `transition status
THREAD_ID` inspects the binding; `transition deactivate THREAD_ID` removes its
eligibility. Hook setup/trust is a separate prerequisite. None of these commands
changes a model's reasoning effort or installs a second interception pattern.

The native checker requires the unchanged transcript prefix and the observed
stopped-turn sequence through the current turn's start/context fence. Missing
hook work, compaction, changed model/instructions/context, prefix mutation or
rollback cannot silently preserve eligibility. An ON/OFF settings revision also
invalidates the binding. Missing proof expands to native inference.

Completion records and external heads are durable; a notification being prepared
or returned is not proof that a desktop client displayed or acknowledged it.
An uncertain cross-database commit must be quarantined rather than silently
resetting a head or repeating execution. The local owner remains part of the
trust boundary; this is not protection against coherent rewriting of all
trusted state by a hostile host.

## Semantic re-entry and exact recovery

Recorded observations may be absent from Codex's native transcript. On the next
native turn, the shared adapter supplies a fixed recovery notice and read-only
`memory replay` argv arrays for that thread's prior recording scopes. No payload,
summary or archived instruction is injected as developer context. Replay returns
exact historical data; it does not grant current authority. Follow `next_cursor`
while `has_more` is true, and reduce the page limit if its byte budget is exceeded.
The advertised command uses isolated Python and the hook's absolute package root
so the task directory cannot substitute a same-named module for recovery.

This recovery notice remains available after deactivation or Engine OFF because
turning optimization off cannot restore already omitted history. OFF captures no
new prompt. Invalid child identity cannot inherit its parent's recovery scope.
Malformed metadata produces a fixed recovery-gap warning, never silent assurance
that the transcript is complete. The bounded locator supports up to 2,048 outbox
records and eight project scopes; exceeding a limit also reports a gap.

The notice currently repeats on native turns: no delivery/compaction ACK exists
that would justify silently assuming it remains resident. Its repeated input and
subsequent retrieval cost belong in complete-workflow accounting. Exact recovery
is available; a real model's appropriate use of it still needs qualification.

## Costs and qualification

The current limits are 256 events and a 4 MiB native transcript snapshot. Exact
capture accepts at most 64 KiB of UTF-8 prompt, including envelope overhead.
Full-prefix and prior-record validation may repeat reads; these costs must be
included rather than described as constant-time operation. The gate is a bounded
development implementation, not a general-purpose semantic classifier.

Offline hostile tests and auth-free native protocol probes precede hosted
benchmarks. They cannot establish model intelligence parity, full desktop
coverage, seven-task median savings or included-plan quota ratios. A candidate
must still pass the normal-answer capability and economic gates before release.
