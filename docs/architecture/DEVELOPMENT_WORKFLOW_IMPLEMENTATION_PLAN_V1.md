# Development Workflow Automation V1 — Implementation Plan

## Status and Boundary

This plan sequences possible future implementation of **LOCAL-FIRST DETERMINISTIC COORDINATOR
V1**. It does not implement a Coordinator, Runner, CLI, GitHub Action, validator, or any other
runtime component.

Every Step requires its own FINAL APPROVED WORK ORDER and both Audit1 `PASS` and Audit2 `PASS`.
Listing a Step does not approve it, select it as next work, advance a Phase, or authorize a push.
The Developer Workflow control plane remains separate from the production Core, Business Runtime,
Business Data Contract, `APPROVAL_QUEUE`, `AI_RUN_LOG`, and `TOPSPEED_DATA_HUB`.

## STEP 0 — Architecture Contract Publication

| Item | Contract |
| --- | --- |
| Purpose | Establish the reviewed ADR, state contract, Draft 2020-12 Schema, and this implementation plan as the sole V1 architecture package. |
| Inputs | Frozen Architecture, Data Contract, Implementation Plan, Migration Matrix, approved ADRs, current handoff, Git/CI evidence, approved workflow inputs, and the FINAL APPROVED WORK ORDER. |
| Outputs | Exactly the four Development Workflow Architecture Contract files and their audited local result commit; remote publication only after the existing Publication Gate. |
| Dependency | Correct Git baseline and clean tree; no unresolved authority conflict. |
| Allowed authority | `DOC_WRITE`, `READ_ONLY_VALIDATION`, and the one approved `LOCAL_COMMIT` within exact paths. A separately approved Publication Runner may later publish. |
| Forbidden authority | Runtime code, source/tests/CI/config changes, business writes, automatic push, `main` merge, Phase advance, new Slice selection. |
| Test | Exact file scope; strict UTF-8 and JSON parse; Draft 2020-12 meta-schema check; terminology and workflow consistency; whitespace, diff, and sensitive-value checks. |
| Completion condition | Audit1 and Audit2 independently pass the same result SHA and the human-approved Publication Gate completes without a remote race. |
| STOP condition | Authority conflict, scope drift, invalid Schema, changed baseline/ref, dirty tree, audit mismatch, missing approval, or remote race. |

## STEP 1 — Deterministic State Machine and Schema Validator

| Item | Contract |
| --- | --- |
| Purpose | Implement deterministic structural validation and fixed-stage transition logic without invoking a real Actor. |
| Inputs | Published V1 ADR, State Contract, JSON Schema, and a separately approved Work Order. |
| Outputs | State validator, deterministic transition function, and test fixtures using only a fake Runner. |
| Dependency | STEP 0 published and independently audited. |
| Allowed authority | Work-Order-scoped `SOURCE_WRITE`, `TEST_WRITE`, `CONFIG_WRITE` only if explicitly listed; local validation. |
| Forbidden authority | Real Actor execution, workspace mutation by Builder, credentials, remote calls, push, business runtime coupling. |
| Test | Stage/status/verdict matrices, fail-closed unknown values, idempotency canonicalization, scope-hash fixtures, replay rejection, and property/negative cases. |
| Completion condition | Same validated input yields the same state and hashes; invalid or ambiguous input always stops; fake Runner is the only Runner. |
| STOP condition | Nondeterminism, Schema/document mismatch, skipped stage, unapproved field/enum, or any external side effect. |

## STEP 2 — Audit1/Audit2 Read-Only Actor Runner

| Item | Contract |
| --- | --- |
| Purpose | Execute Audit1 and Audit2 as independent, read-only Actors and validate their structured results. |
| Inputs | STEP 1 state machine, approved Actor result contract, repository/evidence snapshot, and separate execution-context configuration. |
| Outputs | Schema-valid Audit1/Audit2 results with evidence references, verdicts, findings, and audited result SHAs. |
| Dependency | STEP 1 passed independent audits; Actor isolation defined by a new approved Work Order. |
| Allowed authority | Repository/Git/evidence read-only and Developer Workflow state writes by Coordinator. |
| Forbidden authority | Repository mutation, shared Audit1/Audit2 execution context, credential leakage, verdict reclassification, push, business writes. |
| Test | Context separation, read-only enforcement, malformed/unknown verdict rejection, result-SHA preservation, evidence validation, and audit mismatch STOP. |
| Completion condition | Both Actors run separately, cannot mutate the repository, and only schema-valid results enter state. |
| STOP condition | Shared context, write attempt, malformed result, missing evidence, unexpected verdict, SHA mismatch, or credential boundary violation. |

## STEP 3 — Builder Workspace-Write Runner

| Item | Contract |
| --- | --- |
| Purpose | Permit bounded local implementation only under a FINAL APPROVED WORK ORDER. |
| Inputs | Valid approved transition, Work Order canonical hash and scope, clean verified baseline, and STEP 2 audit result. |
| Outputs | Local result artifact/commit plus actual paths, operations, SHAs, and evidence for Audit1. |
| Dependency | STEP 2 passed; Work Order deterministically resolves ID, paths, operation classes, phase, and slice. |
| Allowed authority | Only local workspace-write and optional local commit explicitly granted by the Work Order. |
| Forbidden authority | Push, publication credential, business write, `main` mutation, scope expansion, corrective Work Order generation, blind retry. |
| Test | Exact path and operation enforcement, clean-tree and ancestry checks, actual-vs-approved scope comparison, push denial, and secret isolation. |
| Completion condition | Result is locally verified, scope-exact, committed only if authorized, and ready for Audit1 without remote mutation. |
| STOP condition | Missing/invalid Work Order, dirty tree, baseline mismatch, unauthorized path/operation, unexpected commit, scope drift, or ambiguous side effect. |

## STEP 4 — Crash Recovery and Reconciliation

| Item | Contract |
| --- | --- |
| Purpose | Recover deterministic state after interruption without duplicating or hiding side effects. |
| Inputs | Persisted Transition state, actual Git/worktree state, result artifacts, and remote-ref evidence where applicable. |
| Outputs | Verified `COMPLETED`, permitted read-only rerun, or fail-closed `STOPPED`/`RECONCILIATION_REQUIRED`. |
| Dependency | STEP 3 passed; durable state storage behavior approved separately. |
| Allowed authority | Read-only reconciliation and Developer Workflow state updates; read-only Actor rerun only in the contract-defined no-mutation case. |
| Forbidden authority | Builder automatic retry, automatic revert/reset, guessed side-effect status, new corrective scope, push. |
| Test | Dirty tree, unexpected SHA/commit, duplicate Transition, pre/post-mutation crash, missing artifact, and ambiguous side effect. |
| Completion condition | Every restart outcome is uniquely classified from persisted and actual evidence, with no duplicate Builder execution. |
| STOP condition | Any mismatch or ambiguity that cannot be proven safe; remote ref change; failed persistence. |

## STEP 5 — Docs-Only Dry Run

| Item | Contract |
| --- | --- |
| Purpose | Exercise the complete local workflow through `PUBLICATION_READY` using docs-only work and no business-function change. |
| Inputs | Steps 1–4, a docs-only FINAL APPROVED WORK ORDER, isolated Audit contexts, and a clean local repository. |
| Outputs | State/evidence chain for every fixed stage ending at `PUBLICATION_READY`; no automatic publication. |
| Dependency | Steps 1–4 individually approved, implemented, and passed by Audit1 and Audit2. |
| Allowed authority | Exact docs-only write scope, read-only audits, local state, and local commit if the dry-run Work Order allows it. |
| Forbidden authority | Business feature change, production data access/write, automatic push, stage skip, Phase/Slice decision. |
| Test | Normal PASS route plus all required failure, replay, crash, scope, approval, and boundary scenarios below. |
| Completion condition | Fixed workflow reaches `PUBLICATION_READY` deterministically, while push remains forbidden without human approval. |
| STOP condition | Any inconsistent handoff, stage/status/verdict mismatch, scope drift, audit SHA mismatch, or attempted automatic publication. |

## STEP 6 — Human-Approved Publication Runner

| Item | Contract |
| --- | --- |
| Purpose | Provide a Builder-separated, least-privilege publication path after all local gates pass. |
| Inputs | Audit1 `PASS`, Audit2 `PASS`, identical audited `result_sha`, authenticated Human Owner approval, and successful remote race check. |
| Outputs | Candidate fast-forward push to the approved audit branch plus remote/CI evidence; never a `main` change. |
| Dependency | STEP 5 passed; separate Work Order and publication-security review; Publication Runner credential boundary approved. |
| Allowed authority | Narrow push capability for the explicitly approved audit branch and result SHA only. |
| Forbidden authority | Source mutation, Builder identity/credential reuse, non-fast-forward push, force operation, tag, PR orchestration, `main` push/merge, Phase advance. |
| Test | Missing/expired approval, Audit1/Audit2 SHA mismatch, remote race, wrong branch/ref, non-fast-forward update, credential absence/leakage, and `main` denial. |
| Completion condition | Exact approved result is fast-forward published to the audit branch and remote evidence is recorded without exposing credentials. |
| STOP condition | Any publication precondition fails or remote state differs; no retry until the approved ownership flow resolves it. |

## Required Future Test Contract

The following are implementation requirements for the relevant future Steps. They are not test code
in STEP 0.

1. **Normal PASS path:** every fixed stage completes in order and ends at `PUBLICATION_READY` with no push.
2. **Audit1 FAIL:** preserve `FAIL`, set `STOPPED`, and clear `expected_next_stage`.
3. **Audit2 FAIL:** preserve `FAIL`, set `STOPPED`, and do not invoke Builder or Publication Runner.
4. **BLOCKED:** preserve `BLOCKED`, stop, and require Human/corrective ownership.
5. **Unexpected verdict:** reject the result as schema/state failure; do not reclassify it.
6. **Schema validation failure:** stop before dependent action and record an explanatory `error_code`.
7. **Dirty working tree:** use `RECONCILIATION_REQUIRED` during reconciliation and stop.
8. **Baseline SHA mismatch:** stop before Actor execution; do not repair Git state.
9. **Audit1/Audit2 result SHA mismatch:** prohibit `PUBLICATION_READY`/publication routing.
10. **Duplicate trigger:** resolve to the existing Transition identity without duplicate Actor side effects.
11. **Completed Transition replay:** never re-execute the Actor for the same completed `idempotency_key`.
12. **Builder crash before mutation:** do not auto-retry Builder; reconcile evidence and require approved routing.
13. **Builder crash after commit:** validate actual commit/result artifact; never create a second commit blindly.
14. **Ambiguous side effect:** set `AMBIGUOUS_SIDE_EFFECT`, `BLOCKED`, and STOP with Audit1 as next owner.
15. **Scope drift:** set `SCOPE_DRIFT`, stop, and do not revert or expand scope.
16. **Unexpected changed path:** classify as scope drift and stop.
17. **Unauthorized operation class:** classify as scope drift and stop before publication.
18. **Remote ref race:** set `BLOCKED`/STOP and prohibit push.
19. **Missing credential:** Publication Runner stops without exposing or requesting token values through Coordinator.
20. **No publication approval:** `PUBLICATION_READY` remains local and push is forbidden.
21. **Attempted `main` push:** deny and stop.
22. **Attempted Phase advance:** deny; no state or repository Phase mutation.
23. **Attempted automatic new Slice selection:** deny and return ownership to Audit1.
24. **Attempted business credential access:** deny, record credential-boundary violation, and stop without secret value.
25. **Attempted external business write:** deny and stop; no Business Runtime coupling.
26. **Missing idempotency canonicalization input:** do not generate a key; set `BLOCKED`/STOP.
27. **Failed scope-hash Work Order resolution:** do not generate the hash; set `BLOCKED`/STOP.
28. **STOPPED before valid verdict:** allow `verdict = null` only with non-null `error_code`.
29. **COMPLETED with null verdict:** reject as an invalid state.
30. **Automatic push from `PUBLICATION_READY`:** deny; require all publication preconditions and Publication Runner.

## Cross-Step Completion Rule

No later Step may be treated as authorized because an earlier Step passed. Each Step is a separate
work item with its own scope hash, FINAL APPROVED WORK ORDER, Audit1 implementation audit, Audit2
independent re-audit, and Publication Gate. Failure, blocking, ambiguity, or invariant violation
sets `expected_next_stage = null` and provides no automatic corrective authority.
