# Offline budget admission before native experiments

## Purpose and boundary

The research goal remains 65% median input and output savings for every model,
with capability/workflow preservation and normal model-written final answers.
This utility removes an avoidable research cost: spending native calls to test
an intervention whose declared unchanged segments already exceed its budget.

`scripts/native_budget_gate.py` performs arithmetic over supplied native segment
counters. The researcher explicitly identifies which observed segments a
proposed intervention leaves fixed. The program does not decide which work is
semantic, removable, safe, or sufficient. Reported output includes reasoning;
reasoning must not be charged again.

For either axis, with control cost C, target saving S and declared fixed sum F:

    allowed candidate cost = C × (1 − S)
    remaining replacement budget = C × (1 − S) − F

A negative remainder rules out the target **under those fixed-segment
assumptions**. A nonnegative remainder merely leaves room for a candidate. It
does not authorize inference, establish parity, or predict the missing work's
cost. Re-entry, retries, retrieval, setup and coordination still need accounting.
Changing the assumptions requires an explicit new design, not relabeling a
necessary segment as free. No model is invoked by this utility.

## Two applications to retained native receipts

| Task and declared unchanged segments | Fixed input | Fixed output | Input budget left at 65% | Output budget left at 65% |
|---|---:|---:|---:|---:|
| Sol dependencies: edit-producing segment and final | 36,994 | 1,011 | 10,638.20 | -134.60 |
| Astra recording: initial semantic turn and final | 37,067 | 252 | 18,662.80 | 67.55 |

Source counters come from the native rollout segment receipts, not visible-text
estimates. The Sol control totals 136,092 input / 2,504 output; Astra control
totals 159,228 / 913. Candidate segment totals reconcile to their cumulative
native counters. Exact JSON inputs and output receipts are retained alongside
the original research bundles as `BUDGET_GATE_INPUT.json` and
`BUDGET_GATE_RESULT.json`.

**Sol decision:** A routing-only experiment preserving the observed edit and
normal final cannot reach the output target, even if all other work became free.
Do not run it merely to rediscover this bound. This is not proof that Sol or the
task has an irreducible model-level limit.

**Astra decision:** Exact recovery is not ruled out, but its observed 202-token
selection segment must fit within 67.55 output tokens with all replacement
costs charged. The already implemented shorter installed launcher reduces
serialized bytes from 474 to 304. That byte change is not a native token
measurement and cannot satisfy the gate on its own.

## Next falsifier, without another paid pair

Audit whether an ordinary short read can return the exact caller-bound
materialized observations **while validating their binding at read time**.
Validation before advertising a mutable filename is insufficient: a later
read may see changed bytes. Any implementation must return the bytes it
actually verified, preserve the recording head/grant/epoch and original
authorization, reject uncertain publication and stale state, and retain exact
Memory fallback. It must not repair or re-execute a historical effect merely to
serve a read.

Keep historical text out of higher-trust hook instructions. The existing
navigation-only recovery contract remains intact until a compatible actual
tool-result delivery path is proven. The model retains semantic review, raw
retrieval and its normal final. No file-read shortcut or new authority is
activated by this document.

## Verification and use

Run `python3 scripts/native_budget_gate.py input.json`, or supply JSON on stdin.
Exit 2 means ruled out under the supplied fixed segments, exit 0 means not ruled
out, and exit 1 means invalid input. Exit 0 is never authorization for a model
call. The input shape is documented by the two retained input files and the
focused tests.

All 22 focused tests pass, including exact budget equality, a decimal just
above equality, invalid/duplicate fields, non-finite numbers, empty fixed sets,
and the three CLI exit paths. Root review found that default JSON float parsing
rounded a very precise target down before exact comparison; parsing decimal
numbers directly closes that false-admission case. The actual Sol and Astra
inputs produced the decisions above, with input/script/result hashes retained
in `BUDGET_GATE_RECEIPT.json`. No additional hosted benchmark was launched.

## Research claims and limits

This is a deterministic experiment-screening aid. It does not establish 90%
cheaper benchmarking, task economics, model-wide parity or a release median.
The root and the bounded implementation worker consume research inference;
zero benchmark invocations is not zero research cost.
