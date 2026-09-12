# Native edit batching and the remaining source boundary

## Windows read-consistency correction

Windows Python 3.13 CI rejected stable rewritten source before reading it.
The diagnostic at commit `341af49` recorded equal device, inode, mode, link
count, size, modification time and birthtime, but unequal `st_ctime_ns`:
path lookup reported creation time `1789249628564080500`, while the open
descriptor reported change time `1789249628580347000`.
[Diagnostic CI](https://github.com/SuperHelix77/HelixEngine/actions/runs/34720860503).

This matches CPython's distinct path and descriptor implementations:
[path stat](https://github.com/python/cpython/blob/v3.13.0/Modules/posixmodule.c#L2160-L2203),
[descriptor stat](https://github.com/python/cpython/blob/v3.13.0/Python/fileutils.c#L1111-L1288).
The correction uses birthtime for Windows cross-API comparisons when available,
while comparing descriptor before/after stamps with their full change time.
Path before/after and whole-set consistency fences remain in place. A synthetic
cross-API discrepancy succeeds; a descriptor change-time-only mutation still
rejects the packet. These are capture-time consistency checks, not a filesystem
transaction or a guarantee against a malicious writer restoring metadata.

This compatibility repair does not qualify native source delivery, capability
parity, or token savings. Self-activation remains gated on those separate checks.

## Observed execution result

The local installed-client probe replaced a generated Python file-write and
subprocess wrapper with ordinary `tools.apply_patch` and `tools.exec_command`
in one `functions.exec` batch. The latter invokes the installed `helixengine`
console from its interpreter's PATH. Engine remains ON and owns test execution;
native tools own the patch. No model effort or final-answer schema was changed.

The valid repair's actual tool text fell from 3,040 to 1,582 UTF-8 bytes
(47.96%). The solution itself remained 1,088 bytes. This is observed tool
serialization, **not native output-token savings**. A preliminary 1,427-byte
estimate omitted some actual runtime arguments; use 1,582 for the tested path.

Two deterministic loopback cases passed: the valid repair executed once and
returned test exit 0; the defective repair executed once and returned test exit
1. Both retained ordinary final-message transport. The finals and repairs were
scripted by the local mock, so this establishes neither Sol reasoning nor
normal-final semantic parity. Each case had two local provider requests and
one Engine execution. No hosted inference was used.

The separate finite oracle accepted the valid source (735 graphs, 16 invalid
inputs, 751 nonmutation checks) and rejected the defective source. Protected
test/settings files stayed unchanged. Small/marginal output reductions bypassed
while Engine remained enabled.

## Stale-patch falsifier

A deliberate missing-preimage patch stopped the native batch. The next request
contained `apply_patch verification failed`; there were **zero Engine runs**
and all initial task files were unchanged. The original success-oriented
harness reports missing test markers for this case. Root adjudication treats
that retained failure as the expected stop-on-failure observation, not a passing
success-harness run. The mock final was changed to withhold completion.

This checks a stale textual patch context. It does not establish transactionality
across arbitrary multi-file patches or protect against all concurrent writers.

## Source-preparation correction

Root inspection of decoded first-request content found none of the three exact
project files in either case. The task prompt named the files; the scripted
provider already knew the repair. That distinction was not explicit enough in
the preceding report and is now corrected there.

A Luna explorer correctly located exact native prompt capture through
`UserPromptSubmit`, but concluded that this sufficed for source preparation.
Root inspection of `prompt_memory.py` rejected that conclusion: capturing prompt
bytes does not read or deliver the mentioned project files. The module itself
explicitly describes storage-only behavior. Its passing capture tests are not
file-preparation tests.

A further local wire check appended a native `mention` input for each project
file. Neither exact file contents nor the supplied absolute file paths appeared
in the observed first requests. Do not infer file expansion from the existence
of a generic mention schema. The current official documentation describes
mentions for apps and separately documents client-supplied tool output and
history injection; it does not establish an existing desktop source bridge.
[App-server documentation](https://learn.chatgpt.com/docs/app-server).

## Next implementation boundary

The bounded candidate is an explicit, project-scoped source opt-in through the
existing shared hook. Installed Engine captures a configured finite file set,
archives exact bytes, and offers a bounded quoted source packet before native
inference. It does not guess file permissions or source selection from prompt
text, execute source instructions, or replace the model's final answer. Missing,
changed-during-read, binary or oversized input returns no packet and leaves the
ordinary tool path available. Recording/recovery context retains priority.

This is intended to remove a measured discovery/read context cycle, not add a
memory agent. Configuration, reads, archives, packet size, native delivery,
retrievals and any additional model work must all be charged. It stays opt-in
pending installed delivery and a fresh paired economic/capability gate. Do not
launch a hosted comparison merely because the earlier scripted repair passed.

## Implemented preparation slice

The development branch now exposes `codex source set|status|clear --project`
through the installed CLI. The same shared hook offers configured evidence for
ordinary root submissions and child startup, with independent child attribution.
There is no additional interceptor, model call, task-text file selector or
second archive. Default behavior is unconfigured; Engine OFF prevents reading.
Source configuration lives outside the selected project. Exact CAS object
paths make recovery possible without inspecting Engine implementation code.

The full-set before/after stat fence rejects ordinary read-time changes.
It is not a lease or a concurrency-proof filesystem snapshot after return.
Read and serialized-context budgets are enforced separately. JSON source
strings remain untrusted data. Preparation failures preserve the ordinary
native task, and do not misclassify successful prompt capture as failed.

Root and independent review found and fixed path normalization, bounded CLI
errors, FIFO-open blocking, aggregate read growth, cross-file mutation,
Windows binary-read flags and oversize configuration publication. The first
installed suite passed 455 checks but preceded the last two review fixes;
the final fresh installed wheel passed **456 tests in 15.65 seconds**.
Windows-specific execution still requires the corresponding CI result.

Direct invocation of the installed hook command passed root/child exact-content,
new-source-version, old-object recovery, missing-file fallback, Engine OFF and
clear-configuration checks. Three files contained 677 source bytes; the offered
JSON packet was **1,821 bytes**. Initial preparation reported 3.24 ms and 677
object bytes written; repeated child preparation reported 9.83 ms, 677 object
bytes read and zero new object bytes written. These are local observations,
not stable latency predictions or full effective-cost accounting. In particular,
`archive_bytes` is logical archived input; `store_io` records the measured
object traffic, including deduplicated writes.

**Remaining gate:** this smoke invoked the installed hook command directly.
It did not prove native hook approval/dispatch or packet delivery into the real
desktop request. Telemetry deliberately says `hook_response_not_wire_verified`.
Native economics, semantic parity and self-activation remain unqualified.
No production source opt-in or model-setting change was made for the root agent.

## Evidence

- Native edit-batch PROBE SHA-256:
  `80d30648eb7e53439c52cba5932917153e6b10c2bf256f8ff99d73a13d4a2732`.
- Independent oracle SHA-256:
  `6c080fb574d44a54d911ca69b86d5687634bba7c78a8853ece0b8901d8d3de6e`.
- File-mention valid-case first request SHA-256:
  `4b49c25a7972deb6fe1b4124730560edce8e9f8565b368441aa7913ddc234a52`.
- Final installed source-context wheel SHA-256:
  `ff2ad6b0c5f684b20439161bcfd01e7de07525d34a63fdad198cd5999ae801c0`.
- Installed hook smoke RESULT SHA-256:
  `0664437e6d07c7c394b41fd60022be2d5e02ddeca23639ac285fb4df94d57484`.

Exact local artifacts are retained in the dated `sol-native-edit-batch`,
`sol-native-edit-stale`, and `sol-native-file-mention` research directories.
No model median is qualified and no v0.2 release is claimed.
