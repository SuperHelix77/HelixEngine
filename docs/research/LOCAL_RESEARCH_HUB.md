# Isolated research HUD

The immutable v0.1.0 release remains on port 8769 and its existing data directory. This development branch supports a research instance on port 8770 with a separate database and evidence store. It does not update the installed release or Codex configuration.

From this checkout:

```sh
python -m helixengine --data-dir ~/.helixengine-research serve --research --port 8770 --observe-rollout /absolute/path/to/one-rollout.jsonl --observe-thread EXACT_THREAD_ID
```

Observation is opt-in, local and read-only. It begins at attachment, uses native per-response counters, and retains whitelisted metadata rather than conversation or reasoning text. It does not intercept inference or authorize execution. Unknown model metadata remains unknown until the source supplies it. Reasoning tokens are included in output, not an additional charge. Native usage is distinct from routed command telemetry and historical paired benchmark capsules.

Route suitable foreground commands to the same research store:

```sh
python -m helixengine --data-dir ~/.helixengine-research run --kind pytest -- python -m pytest -q tests/test_research_hub.py
```

Exact raw output remains retrievable. Use targeted checks for changed contracts, reuse unchanged verified checks, and expand coverage on a new failure or unresolved risk. No heuristic skipping of required tests, lower model effort, altered final-answer format, or reduced semantic review is authorized by this mode.

Savings targets are paired cohort medians: 65/65, then 75/75, with 90/90 aspirational. Capability and workflow gates take precedence. Observation alone does not establish savings or included-plan quota consumption. Full current-chat savings and general model parity remain unmeasured.
