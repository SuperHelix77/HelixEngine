# HELIX Core v0.1 - execution protocol (frozen draft)
protocol hash: `f2e044c905160b44` (`hstep protocol`). Source of truth: `lib/hcore.py`. Provider-independent: no model SDK, adapter or memory-backend imports.

**Principle.** Frontier inference defines, adjudicates and revises the loop; HELIX executes it. A model (Laya / local / frontier) may *propose*; HELIX policy *decides*.
Never delegated to a proposer: filesystem/network mutation, claim promotion, goal completion, frontier suppression in high-cost-error states.

| Record | Purpose |
|---|---|
| GoalGraph | goal_id, objective, global_invariants, completion_predicate, steps[] (partial order, acyclic), assumptions, revision_policy |
| GoalStep | objective + contract: depends_on, required_evidence[{kind,..}], invariants, completion_predicate, uncertainty_budget, risk_class(low/medium/high), escalation_policy, output_schema, **envelope** |
| ExecutionEnvelope | may[] / may_not[] over a closed op vocabulary, budget{ops,seconds,raw_mb,frontier_tokens}, stop_when, escalate_when[] |
| EvidencePacket | typed result: observations, evidence/claim refs, contradictions, unresolved, operation_receipts, confidence, completeness, raw_backing_refs, recommended_transition |
| ClaimProposal | worker proposal (always PROPOSED, evidence required); only HELIX promotes (validate + dedup) |
| DecisionReceipt | micro-escalation outcome: question, chosen, confidence, reason<=150 words, tier |
| EscalationRequest | goal/step, reason(contradiction/missing_capability/low_confidence/envelope_exhausted/ambiguity/high_risk), evidence, decision_required |

Operations (closed vocabulary): read-only `SEARCH_SYMBOL READ_SYMBOL FIND_CALLERS FIND_CALLEES FIND_IMPORTS CHECK_TEST OUTLINE QUERY_MEMORY VERIFY`; mutating (explicit grant only) `PATCH_RANGE RUN_CMD WRITE_FILE`.
Transitions: `DONE NEXT_STEP VALIDATE_CLAIM ESCALATE:<reason> RETRY ABORT`. The reference controller (`lib/hcontrol.py`) is a deterministic FSM: it escalates on exhausted envelope, ambiguous definition, missing capability or incomplete evidence; it never guesses.

Host-adapter surface (adapters decide none of the policy): `inject_context() intercept_tool() execute_tool() observe_boundary() spawn_worker() request_model()`. Not yet implemented.
