# Sol High: native source preparation pair

## Verdict

**OBSERVED:** One fresh control-first pair on the dependency scheduler fixture
saved **32.96% total input and 22.00% output**, with **1.86% uncached-input
savings**. Both implementations passed the same independent finite oracle and
returned normal model-written final answers. **Workflow parity and causal
attribution remain unestablished.** This does not qualify 65/65, a model median,
self-activation, or v0.2 release.

## Boundary and measurement

Both arms used native `gpt-5.6-sol` at High effort, ordinary tools, identical
task/protected fixture bytes, and separate homes, stores and working directories.
No client base replacement, forced single turn, caller-rendered final, reduced
tool access or model-effort change was used. The candidate enabled Engine and
caller-configured source preparation through the shared native hook. The control
disabled optimizations. Hook trust was established through the native CLI UI.

| Native receipt counter | Control | Helix | Saving |
|---|---:|---:|---:|
| Input | 136,092 | 91,240 | 32.96% |
| Cached input | 119,552 | 75,008 | 37.26% |
| Uncached input | 16,540 | 16,232 | 1.86% |
| Output | 2,504 | 1,953 | 22.00% |
| Reasoning output, included in output | 634 | 679 | -7.10% |
| Model segments | 7 | 5 | — |
| Native shell commands | 5 | 3 | — |
| Engine command executions | 0 | 0 | — |
| Arm elapsed seconds, including preflight | 76.275 | 62.386 | — |

Final cumulative native usage matches the sum of individual segment usage in
each saved rollout. Cached reads are not uncached-input savings, monetary savings
or included-plan quota savings. Provider retries remain unknown; the runner
performed zero hosted-task retries. Two hosted tasks comprised twelve model
segments, not two model requests. Parent and worker research costs are outside
these task totals; no combined research-efficiency percentage is established.

An earlier preflight failed because the runner expected a newly started thread's
rollout file to exist immediately. It consumed 17.288 seconds, issued no
`turn/start`, and has preserved evidence under `preflight-failed-v1`. The runner
now validates the future path at startup and requires the file after completion.
The failed preflight is not silently counted as a successful arm.

## What reached the model and what executed

**OBSERVED:** Candidate native history contains the source packet as a developer
transport message at rollout line 11, including the exact initial source hash.
The control has no such source message. The hook recorded three files, 677 raw
bytes archived and 1,848 UTF-8 bytes of context. This proves native-history
presence for this task; it is not a fresh outgoing-wire capture or whole-session
coverage claim. Separate loopback wire proofs are documented in
[the boundary audit](NATIVE_EDIT_SOURCE_BOUNDARY_20260913.md).

All three candidate commands received native routes. The first combined `pwd`,
Git status and source reading; the second combined unittest with a new Python
probe via heredoc; the third combined compilation, protected-file hashing and
source reading. These are outside the adapter's admitted compound command
grammar. Engine did not execute or reduce their results. A previously successful
simple-unittest transport gate cannot be credited for savings in this pair.

Candidate Sol reread the supplied source. Control Sol additionally read the
orchestration skill in two commands. Control also ran 500 seeded random graph
cases, comparing against all possible orderings for each graph; candidate Sol
ran a smaller hand-crafted probe set. These observable differences are material.
The trace does not establish that source preparation caused them, nor that less
investigation preserved equivalent error-discovery capability.

Both working directories inherited the enclosing repository's Git root. Git
status exposed parent workspace paths. This is a fixture isolation defect,
retained in the evidence rather than retroactively removed from the baseline.
The pair also has fixed control-first order and no replication.

## Behavioral checks and remaining parity boundary

Both completed implementations passed the independent oracle: **735 graph
cases, 16 invalid-input cases, and 751 nonmutation checks**, with zero failures.
The oracle's source binding matches each final implementation. Both protected
files match their original exact bytes. Both models reported observed results
in ordinary prose and retained access to tools and new probes.

This supports finite artifact behavior, not complete capability or workflow
parity. In particular, independently testing the final artifacts does not make
the models' differing investigation breadth equivalent. No semantic review or
probe will be deleted to improve the ratio.

## Next decision: offline first

**INFERRED:** Two measured residuals deserve analysis before another native call:
source rereading despite delivery, and compound commands bypassing execution.
The pair does not justify a new memory system, kernel or broad model sweep.

For routing, replay the exact captured commands against the admission logic and
identify unsupported leaves. Preserve shell ordering, failure short-circuiting,
heredoc semantics, working directory, exit status and execute-once behavior.
Do not split arbitrary shell syntax or substitute previous probe conclusions.
An adapter improvement must first survive offline valid/failure/cancellation
tests and actual next-request delivery checks. Retaining raw output is correct
when a projection costs more or removes necessary evidence.

Before any new causal pair, isolate the Git roots, freeze identical instruction
surfaces, retain unrestricted novel probes and preregister what parity is being
tested. Engine source preparation stays opt-in. Root self-activation is **not
qualified** by this result; supported existing behavior remains unchanged.

## Evidence identities

Exact local bundle: `research/sol-source-native-pair-20260913` in the enclosing
research workspace. It retains fixture, preregistration, offline gates, executed
runner versions, failed preflight, native rollouts, commands, events, finals,
oracle outputs and reconciliation. Private raw histories are not release assets.

- Reconciliation SHA-256:
  `1646300416e663aebf457a9bac64f7e50f90d0a25cfb72c72bed86472b697035`
- Installed wheel SHA-256:
  `6d9eaef44371632e442e1b8435e36a8a5faaaf9e79e86890f88d85f2d54afacd`
- Independent oracle SHA-256:
  `6c080fb574d44a54d911ca69b86d5687634bba7c78a8853ece0b8901d8d3de6e`
- Control implementation SHA-256:
  `381fc6bc03b7b71e588c67397d22f398a4dae762d1ca859b9870d4eb86aa40ab`
- Candidate implementation SHA-256:
  `79d8c6cc3aa800ba7316028bde090a4f59337d371932486f37c4333d6a8a76d0`

No implementation change, production configuration change, release promotion or
new self-optimization accompanies this adjudication.
