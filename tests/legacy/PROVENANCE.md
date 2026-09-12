# Legacy core regression provenance

This directory carries the standalone-package regression lane for the original
Helix core. The imported tests are bounded evidence for the current
`helixengine.core` package; they do not establish parity with the original
453-test research tree or with research-only modules.

## Source binding

- Repository: `https://github.com/SuperHelix77/HelixContext`
- Requested and used source pin: `ce443b4457f05477ccc62ea8486d0a877d0c80a6`.
  The release branch `refs/heads/Helix-Output` and tag
  `refs/tags/v0.1.0-preview.1` also resolved to that commit at import time.
- Resolved commit tree: `75e2830aad65fb1239a81c8701e33e821169281f`
- Source acquisition: each file was read through the GitHub Contents API at
  the resolved commit and decoded from the API's base64 response. No local
  research clone was used.

The Git blob SHA-1 and raw source SHA-256 commitments are:

| Source file | Git blob SHA-1 | Raw SHA-256 |
| --- | --- | --- |
| `test_checked_steps.py` | `ef5a0d53233dc4b9f13548ff60fe086589d8b006` | `c00b3524922aa69eae81282bdacbbdc3e6f2a8c46c1a96139a8e80d4215149fd` |
| `test_completion_ledger.py` | `c1887e47a2cadb378614c7bbf4745116269a9741` | `9c881b9bd31b3e2624de1c34ecb3e9f33708a41b78d9c1af04bf0ede51aec3a4` |
| `test_copy_handles.py` | `ed0d96a296e678629725d57580822ba3ae8932bd` | `d9dcf592083129524c5fddc0fd9974333900f6ef01a29dc50e2c1e9d79b011a0` |
| `test_evidence.py` | `36ade6d55c6929fe7eb946f1f686c1b308f04ee1` | `2dc2087725a26aeb1296111f4c9512382bc56a492c42f783d42f269b8b764a81` |
| `test_line_index.py` | `68903a4ea22f11671d82eed3744c922d6cb3510d` | `168209813755470379581eda172ac02cbefdf29973a2b7afad9eea41dd2e9dc7` |
| `test_literal_edits.py` | `60e0e3b9731c635f643d737ac29a6d188b84268d` | `ad4937333969537a1ac4dd6f664dbebe03ad52a4c2d8cdb7a6549ba1eb08c462` |
| `test_named_plans.py` | `84f1b67191e0361d70319818562787bc5d013674` | `02fc075e32d71ced6c396db3fad389089a330bdb5fd5bfee943db7562b45da5e` |
| `test_plan_cli.py` | `06764501a0851541449e435e41a92b573921f303` | `219a7ee285532cb19eba1b01c753d6028fc504010508998f3d90e02c13d072f9` |
| `test_renderer.py` | `dcc197e698296e04f1445a5de7b242ee6b814d96` | `747d9987984d42ee6fc70cfa0be16778675f5e089c2260bf2a0f5a069124b41b` |
| `test_verification.py` | `00c56b673690afa5cd4bdc2b853eee548f5e2d1b` | `bdc2e0e775fcad427decbb5b7604840b272e915cf7afd3afb373dadec14a9e62` |
| `test_workflow_memory.py` | `bae56c23502b501ac6de44546481ef03d31ae6cd` | `f00cc0b00bf1afe76d2a866c845d5b7255e7954178febbf2659d21a2bf37d92f` |

## Port adaptations

All 11 requested source files are present under `tests/legacy/`. The only
changes are package qualification of imports to `helixengine.core`, package
qualification of the two dynamically imported helper modules, a relative
import for the shared plan fixture, and replacement
of the original sibling-file launches with `python -m
helixengine.core.evidence` and `python -m helixengine.core.plan_cli`. Test
assertions and regression bodies were preserved; the per-file assertion and
`pytest.raises` counts match the downloaded source.

Excluded tests/modules: none. No platform-specific original test required a
skip, and the requested source set contained no absent research-only module.

## Verification

Run from `HelixEngine/` with the supplied virtual environment:

```text
.venv/bin/python -m py_compile tests/legacy/*.py
  PASS

.venv/bin/python -m pytest -q tests/legacy
136 passed in 2.36s
```

The green run collected and passed all 136 tests. It uses only local
deterministic subprocesses and filesystem/database fixtures; it performs no
model calls. That run covered exact bytes and numeric spelling, hash and
provenance validation, atomic publication, stale-state rejection, failure
propagation, bounded retrieval, and recovery.

Integration verification after backend changes: all 136 legacy tests pass
within the 174-test application suite on macOS/Python 3.14. Cross-platform
qualification is tracked by the release CI jobs; this local result alone
does not certify Windows or Linux behavior.
