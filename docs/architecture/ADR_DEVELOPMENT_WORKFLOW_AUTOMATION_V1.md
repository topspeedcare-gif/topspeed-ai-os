# ADR: Development Workflow Automation V1

## Status

**ACCEPTED FOR IMPLEMENTATION PLANNING**

This status accepts the architecture contract and its implementation plan. It does not claim that
the Coordinator, any Runner, CLI, GitHub Action, or other automation runtime has been implemented.

## Scope Classification

This is an Architecture Decision for the **Developer Workflow / Development Control Plane**. It is
not a change to the production Core Architecture or Business Data Contract, a new PHASE 4 Data Hub
Slice, entry into PHASE 5, or a change to Business Runtime behavior.

The Developer Workflow control plane is separate from the TOPSPEED AI OS production Core runtime.
Its local-first execution model therefore does not alter the Frozen Architecture invariant that the
production Core is not dependent on a single local PC. This ADR does not change the production
Core, Business Runtime, Data Hub, `APPROVAL_QUEUE`, or `AI_RUN_LOG` runtime architecture.

## Context

The approved development and audit process currently depends on manual copy/paste relay among
Audit1, Audit2, and Codex. Manual relay makes stage identity, evidence, scope, and corrective
ownership difficult to verify deterministically after retries or interruption.

Before publication, the authoritative working model is local-only: local Git state and local
evidence establish what an Actor reviewed or changed. Audit1 and Audit2 must remain independent;
Audit2 cannot be collapsed into Audit1 or run as an implicit continuation of the same review
context. A GitHub remote-event orchestrator would conflict with this pre-publication authority
model by making remote events drive work before the approved local gates are complete.

Development workflow state must also remain distinct from business runtime state. Reusing the
Business Data Contract, business approval queue, business run log, or Data Hub would couple
repository-development control to production commerce behavior and credentials. A dedicated,
machine-readable development state contract is therefore required.

## Decision

The selected architecture is **LOCAL-FIRST DETERMINISTIC COORDINATOR V1**.

- Pre-publication authority: **Local Git + Local Evidence**.
- Remote authority: **Publication + CI + Remote Evidence**.
- Automation boundary: through **Publication-ready** only.
- Git push: **Human approval required**.

The Coordinator validates state and routes only the next authorized transition. It does not infer
missing approval, generate architecture, repair findings, mutate source, or publish.

## Fixed Workflow

The workflow is fixed exactly as follows:

```text
Audit1 Draft
→ Audit2 Review / FINAL APPROVED WORK ORDER
→ Codex Implementation
→ Audit1 Implementation Audit
→ Audit2 Independent Re-audit
→ Publication Gate
→ Next Work returns to Audit1
```

The Coordinator cannot reorder, omit, combine, or synthesize any stage in this workflow.

## Explicit Exclusions

- GitHub Action orchestration
- PR orchestration
- Remote-first execution
- Automatic push
- Automatic main merge
- Automatic Phase advance
- Automatic Slice selection
- Automatic Architecture decision
- External business write
- Business `APPROVAL_QUEUE` use
- Business `AI_RUN_LOG` use
- `TOPSPEED_DATA_HUB` use

## Role Boundaries

### Coordinator

- May read repository and Git state.
- May read and write only Developer Workflow runtime state.
- Cannot mutate source, documentation, tests, branches, or `main`.
- Cannot commit or push.
- Has no business credential and no publication credential.

### Audit1

- Has read-only access to repository content and evidence.
- Owns initial and corrective drafts and receives stopped work requiring correction.

### Audit2

- Runs in an execution context separate from Audit1.
- Has read-only access to repository content and evidence.
- Independently reviews and hardens Audit1 work orders and implementation audit results.

### Builder

- Has local workspace-write authority only within the current FINAL APPROVED WORK ORDER.
- Has no push authority and no business-write authority.
- Cannot expand allowed paths or operation classes.

### Actor Runner

- Provides the approved execution environment for an Actor.
- Owns the credential-injection boundary.
- Never exposes credential or token values to Coordinator state or logs.

### Publication Runner

- Is separate from Builder.
- Cannot mutate source.
- May receive narrowly limited push capability only for a human-approved publication that passes
  every publication precondition.

### Human Owner

- May release a STOP through the approved corrective flow.
- Provides publication approval.
- Owns high-risk approvals, including Architecture and Phase decisions.

## Publication Preconditions

Publication capability may be used only when all of the following are true:

1. Audit1 verdict is `PASS`.
2. Audit2 verdict is `PASS`.
3. Audit1 and Audit2 audited the same `result_sha`.
4. Human publication approval is `PRESENT`.
5. The remote ref race check is `PASS`.

If any precondition is absent or fails, push is forbidden. `PUBLICATION_READY` is a local workflow
state and never means automatic push.

## Consequences

### Benefits

- Machine-readable handoffs replace manual relay while preserving independent review.
- Fixed stage order, idempotency, scope hashing, and fail-closed routing make retries auditable.
- Builder, Coordinator, audit, and publication authorities remain separated by least privilege.
- Crash recovery reconciles persisted intent with actual Git state before further action.

### Limitations

- V1 remains local-first and does not orchestrate GitHub Actions, pull requests, or other remote
  events.
- STOP conditions require the approved corrective ownership flow; the Coordinator cannot repair or
  reinterpret them.
- Publication still requires a human decision and a separate Publication Runner.
- Local-machine dependency applies only to Developer Workflow tooling. The production Core remains
  independent of a single local PC.

Any future remote orchestration requires a separate ADR. This ADR provides no authority for that
future work and does not authorize any implementation-plan step automatically.
