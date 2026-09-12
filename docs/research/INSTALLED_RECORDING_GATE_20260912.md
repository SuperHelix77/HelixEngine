# Installed recording gate: offline adjudication, 2026-09-12

**OBSERVED:** the same packaged adapter now handles explicitly authorized recording transitions before inference. It does not classify arbitrary prose as semantically resolved. The proof boundary is typed data, bound grant/state, exact capture and qualified native continuity.

## Installed-path results

| Case | Mock endpoint requests by turn | Stop notifications | Exact late recovery |
|---|---|---:|---|
| appserver-transition-installed | 1, 0, 0, 1, 1 | 2 | yes |
| appserver-transition-installed-missed | 1, 0, 1, 1 | 1 | yes |

The first case has an ordinary baseline turn, two recorded observations, a new semantic instruction and an observation after invalidation. The second deliberately disables the native hook for a semantic instruction, then restores it: the later event reaches the model because the transcript fence detects unobserved work. Disabling was limited to the isolated test home through the native configuration API. Production configuration was unchanged.

Both checks used installed Codex 0.153.4, a freshly installed wheel in a separate virtual environment, isolated Codex homes and an auth-free loopback endpoint. The package import was asserted to resolve inside that environment. The wheel is still a development build labeled 0.1.0; no v0.2 release is implied.

## Hostile adjudication

The independent review found two P1 defects despite passing earlier tests: the controller did not tie a valid historical capture to the current native request, and finalization could return suppression after OFF or deactivation during publication. Both were corrected. Current native identity, project and exact prompt digest/length must match the core-verified capture. Finalization now checks enabled state, revision, binding identity and exactly one conditional update. Regression tests include same-length prompt substitution, old-turn substitution, OFF, OFF/ON and explicit deactivation. Committed evidence survives fallback.

**OBSERVED:** 380 local tests pass after these fixes. Native continuity tests reject missing semantic turns, prefix mutation/rollback, compaction, partial records and changed context. Recording tests preserve instruction-like payload as data and retain a later-relevant Unicode marker. These are finite execution/data-integrity checks, not model intelligence parity.

## Costs and failure accounting

An initial source-environment probe failed after its first mock turn because the isolated Python home lacked certifi. That failed attempt remains retained. The installed Engine environment and then a fresh wheel environment supplied the declared dependency. No hosted inference was used by any protocol probe.

Successful transition events retain Store metric deltas and native continuity bytes read. Full snapshot/history validation repeats reads. Dependency hashing, filesystem metadata, total physical I/O and all hardware costs are not completely represented by those counters; missing costs are not zero. The experiment does not establish a token saving percentage or included-plan quota ratio.

## Admission limits

Activation requires an explicitly selected completed semantic-turn checkpoint. No cold first-turn bypass is claimed. Only the observed native stopped-turn suffix is admitted; unknown events fall back. Each grant is bounded to 256 events, and native transcript inspection is bounded to 4 MiB. The caller declares unresolved obligations and relevant dependencies; hashes do not prove that either declaration is semantically complete.

**UNKNOWN:** live desktop notification acknowledgement, hosted-model normal-answer parity, complete-workflow economics and seven-cell model medians. No live grant was enabled. These remain release gates.

## Evidence identities

- `appserver_transition_installed.py`: `e2de36b318ff257c4796326b5d2e71f7f884e39bdce73490459b47d4798c9745`
- `appserver_transition_installed_missed.py`: `24ab38268438377438c38d9ee2c84c5c074c97451e0ac60cfa0b54816b5d50da`
- `INSTALLED_GATE_AUDIT.json`: `43f0299dc57d21fd6bbd12fcda3758ab84bec86fea481012b0fd9bc2b3deab12`
- `CANDIDATE_ARTIFACTS.json`: `8b9d92ccf59f94dc67fee4e2da75867fd0ec9b2ef1acae30a5bc90a9fdd6e59d`
- `appserver-transition-installed/RESULT.json`: `db7344b3311bd07eb29dfc4fdded7b5f536c2d8aa40d8611470d4621dacc46ba`
- `appserver-transition-installed-missed/RESULT.json`: `812a3fa49531083eaad61567fc7e1797ad85caa4d317df332a24a305dc77281c`
