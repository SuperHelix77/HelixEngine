# Observer coverage audit — 2026-09-12

## Measured finding

OBSERVED: a read-only suffix audit matched all 229 stored parent usage receipts
in its captured window. Eight records exceeded the live reader's 64 KiB line
limit: five `event_msg` and three `compacted` records. None was a
`token_usage_record`. No malformed record or record above the audit's 4 MiB
limit was encountered. The audit read 8,584,696 bytes and did not retain message
text. It compared input, cached input and output counters for each stored ID.

The suffix starts from the conservative lower bound `cursor - bytes_read`,
aligned to the next complete line. The old database did not save its exact
attachment offset. This is **not full-history reconciliation** and must not
clear the live coverage warning. The metadata-only artifact is retained locally
at `research/observer-coverage-20260912/SUFFIX_AUDIT.json` in the research
workspace, outside bundled release data.

## Correctness fixes

A bounded Luna High review independently identified malformed-line and delayed
source-attachment gaps. The root integrated these findings and checked related
initialization and I/O behavior:

- Malformed-line counts and incomplete coverage now persist through clean scans
  and restarts. A later successful scan cannot erase an earlier gap.
- New attachments retain the source byte boundary. Migrated databases retain
  an unknown boundary; historical completeness is not inferred.
- Attaching within a record skips the partial suffix and records the gap.
- An initially unavailable rollout cannot later skip to EOF and claim complete
  coverage of the interval when it was unavailable.
- Successful scans charge their anchor/integrity reads as well as payload reads.
  An idle scan against a nonempty source currently reads 128 anchor bytes.
- The HUD displays the observation start byte and skipped oversized/malformed
  record counts. Unknown legacy boundaries stay visible.

The live reader remains bounded to one scan budget and stores only whitelisted
metadata. Oversized records are still conservatively skipped. Duplicate native
response IDs remain idempotent; conflicting counters still fail atomically.
Neither model execution nor normal final-answer behavior changes.

## Verification and limits

**217 tests passed in 12.07 seconds**, executed through Engine. Twelve focused
observer tests passed before the full suite. Added checks cover durable malformed
gaps, delayed file creation, partial-record attachment, legacy unknown boundaries,
and accounting for integrity reads. Oversized-gap persistence is also checked
after restart.

No native economic benchmark was launched. The parent and the single completed
reviewer still incurred research inference costs; these are not zero-cost work.
The next economic comparison must include parent preparation/adjudication,
subagent calls, failed attempts, test execution, recovery and evidence retrieval.
Independent review that finds another defect is useful work; duplicate setup and
nested redelegation are the avoidable targets.

This changes reporting correctness, not the product's interception boundary.
Tool-result interception is not pre-inference suppression, and neither this audit
nor the tests establish universal parity or v0.2 release qualification.
