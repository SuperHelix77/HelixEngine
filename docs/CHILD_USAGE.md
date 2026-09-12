# Parent and child usage observation

When a native rollout is explicitly attached, the research observer now follows
descendants discovered through the **existing shared Codex hooks**. It uses the
same native `token_usage_record` parser as the parent. It invokes no model and
adds no command wrapper or context instructions.

The installed-client integration currently looks up an exact child ID in the
local Codex `state_5.sqlite` registry, read-only. It accepts only a matching
rollout beneath that Codex home's `sessions` directory, checks its native
identity header, and binds the file identity at attachment. This is a
version-specific local integration, not a stable public registry API. Missing
or changed registry schemas, invalid paths and uncertain ancestry produce a
visible gap rather than a guessed source. A custom parent rollout outside a
native sessions hierarchy still supports parent observation, but cannot
automatically locate children.

Native child hooks can retain the root session ID even for grandchildren. The
observer therefore keeps that observed session separate from the immediate
parent ID in the child's native metadata. Nested ancestry must reach the
attached root through already verified parent identities. Unrelated tasks are
not read simply because they exist in the same Codex registry.

## Accounting and recovery

The parent keeps its existing attachment cursor. New child attachments explicitly
read history from byte zero so that a fast child is not missed before discovery.
The HUD labels their sum **observed root window plus discovered child histories**.
These windows can differ; the sum is not a complete-task benchmark denominator.

Native response IDs are globally deduplicated in the root accounting database.
Cumulative `token_count` events are not summed. Model and effort metadata remain
separate, with UNKNOWN retained until native context resolves them. Conflicting
response identities stop that child's import instead of charging twice. A
durable import cursor makes restart/replay idempotent. Missing child counters
remain null, not an assertion of zero use. Prior verified counters survive a
later source failure, with the error shown alongside them.

At most 256 lifecycle events are discovered per tick, and at most four child
parsers each consume their existing bounded scan. Identity discovery is capped
at 1,024 links. Children continue to be watched after a stop notification because
that notification does not prove the final usage record was already flushed.
Per-child metadata databases retain only counters/context metadata; they do not
duplicate raw conversations or the command evidence archive. Header and rollout
read counts are exposed; SQLite/physical I/O and included-plan quota are not
inferred.

An oversized or malformed native record remains a coverage warning. Source
replacement, truncation, parent mismatch or unavailable data never silently
clears an earlier gap. Local files and hashes are not provider billing
attestations. No historical discovery algorithm proves that unrecorded
descendants never existed, so `whole_workflow_complete` remains false until a
separate bounded workflow closes its expected identities and measurement window.

The release-state API exposes `observer_tree` with observed totals, per-model
and per-effort grouping, children, import backlog and source errors. The research
HUD displays the combined observed input/output and child gaps. This is improved
accounting, not evidence of 65/65 savings or capability parity.
