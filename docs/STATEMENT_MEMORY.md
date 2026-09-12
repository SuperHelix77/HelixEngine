# Exact visible-statement memory

Research chat observation can optionally archive visible assistant commentary
and final answers into the **existing Engine memory/evidence store**:

```sh
helixengine --data-dir ~/.helixengine-research serve --research --port 8770 \
  --observe-rollout /absolute/native/rollout.jsonl --observe-thread THREAD_ID \
  --capture-statements-project /absolute/project
```

This opt-in is distinct from metadata-only observation. The ordinary Engine
on/off switch pauses statement capture and delivery as well as automatic command
receipt indexing. It does not delete existing evidence. Only the explicitly
attached root and verified descendants use this project scope; the project
string is logical filtering, not access control. Changing a persisted capture
project is rejected rather than relabeling existing historical records.

The installed native format must expose `response_item` / assistant `message`
with `phase=commentary` or `phase=final_answer` and supported text content.
Reasoning records, hidden reasoning, tool output copies, user/developer messages,
and ambiguous message phases are not captured by this component. A final answer
is a historical model statement, not proof that a task passed. No inference,
summarizer, relevance ranking, automatic correction inference or context
injection is performed.

One observer scan commits a small outbox containing only original line ranges,
hashes and message identities. A separate bounded delivery reads and verifies
those bytes and archives the exact JSON line, including exact text/Unicode and
line endings. Memory commits before delivery acknowledgement. A crash between
them replays the stable native identity idempotently; changed content under the
same identity is a conflict. Memory failures retain pending work and do not
prevent independent usage observation or execute a command again.

Source replacement, changed bytes and unavailable history remain errors. The
64 KiB native-record parser bound still applies; oversized/malformed source
warnings remain in observer coverage. Existing root observation cursors are not
rewound. Newly discovered children can have different observation windows.
Messages seen while capture is OFF are not later recovered automatically. This
is therefore **recognized visible messages in captured windows**, not complete
research memory or a lossless replacement for the native conversation.

Use existing `memory search`, `timeline`, `retrieve` and `replay` for access. A
later correction is another exact statement; this layer does not silently
supersede an earlier one. Current constraints and semantic interpretation remain
with the agent. Historical content never becomes newly authoritative developer
instructions through this feature.

The research HUD/API reports root statement counts, pending deliveries, source
read bytes and errors. Child snapshots expose their own statement status. Byte
counters exclude SQLite/physical I/O; indexing and storage cost still exist.
No native input/output or quota saving follows solely from successful capture.
Qualification must compare the complete future workflow against Engine-only
retrieval, including the cost of consuming or recovering historical evidence.
