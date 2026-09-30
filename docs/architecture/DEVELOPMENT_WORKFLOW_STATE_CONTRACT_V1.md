# Development Workflow State Contract V1

## Classification

This is the **Developer Workflow State Contract** for the Developer Workflow / Development Control
Plane. It is not the Business Data Contract frozen in `DATA_CONTRACT_V1.md`.

This state is not stored in, joined to, or treated as an extension of:

- `APPROVAL_QUEUE`
- `AI_RUN_LOG`
- `TOPSPEED_DATA_HUB`
- the Business Audit Layer

Development state cannot authorize a business write or alter production Core runtime state.

## State Object Rules

Every listed field is present in a V1 state object. A field marked nullable is present with an
explicit JSON `null` until its value is validly established. Unknown values cannot be replaced with
empty strings, zero, a guessed SHA, or a synthesized identifier. All timestamps are timezone-aware
RFC 3339 date-times. All Git SHA-1 and SHA-256 values are lowercase hexadecimal.

“Immutable” means immutable after the field's first valid persistence for that Transition.
“Write-once” permits the initial null value to be replaced once by a verified value. State changes
are made only by the listed owner and must be durably persisted before dependent work proceeds.

## State Fields

| Field | Meaning | Type | Required / nullable | Creation owner | Mutability |
| --- | --- | --- | --- | --- | --- |
| `schema_version` | Contract identifier; V1 value is `development_workflow_state.v1` | string constant | required, non-null | Coordinator | immutable |
| `workflow_run_id` | Identity of one end-to-end workflow run | non-empty string | required, non-null | Coordinator | immutable |
| `work_item_id` | Identity of the approved unit of work | non-empty string | required, non-null | Audit1, persisted by Coordinator | immutable |
| `phase` | Phase named by the approved Work Order | non-empty string | required, non-null | Work Order, resolved by Coordinator | immutable for the workflow run |
| `slice` | Slice named by the approved Work Order; null when no Slice applies | non-empty string or null | required, nullable | Work Order, resolved by Coordinator | immutable for the workflow run |
| `stage` | Current fixed V1 stage | stage enum | required, non-null | Coordinator | immutable for the Transition |
| `actor` | Actor assigned to the Transition | non-empty string | required, non-null | Coordinator from the fixed workflow | immutable for the Transition |
| `transition_id` | Unique identity of this Transition record | non-empty string | required, non-null | Coordinator | immutable |
| `idempotency_key` | Canonical Transition replay key | SHA-256 string | required, non-null | Coordinator | immutable |
| `transition_status` | Persisted execution status | status enum | required, non-null | Coordinator | mutable only by valid lifecycle transition |
| `baseline_sha` | Approved repository baseline for the work item | Git SHA-1 string | required, non-null | Work Order, verified by Coordinator | immutable |
| `pre_stage_sha` | Actual HEAD verified immediately before the stage | Git SHA-1 string | required, non-null | Actor Runner, persisted before execution | immutable |
| `post_stage_sha` | Actual HEAD verified after Actor completion or recovery | Git SHA-1 string or null | required, nullable | Actor Runner | write-once after verification |
| `result_sha` | Commit/result identity produced or audited by the Actor | Git SHA-1 string or null | required, nullable | Actor, verified by Actor Runner | write-once; auditors preserve the audited value |
| `scope_hash` | Canonical hash of the approved scope | SHA-256 string | required, non-null | Coordinator from Work Order inputs | immutable |
| `parent_scope_hash` | Prior approved scope linked by a corrective Work Order | SHA-256 string or null | required, nullable | Coordinator from corrective Work Order | immutable |
| `attempt` | Persisted invocation count; not an idempotency input | integer, minimum 1 | required, non-null | Coordinator | increment only for a separately permitted invocation |
| `verdict` | Actor result without Coordinator reclassification | `PASS`, `FAIL`, `BLOCKED`, or null | required, nullable | Actor | write-once; preserved on STOP |
| `findings` | Machine-readable Actor finding summaries | array of non-empty strings | required, non-null | Actor | write-once with Actor result |
| `work_order_ref` | Repository-relative POSIX path to the FINAL APPROVED WORK ORDER | safe path string | required, non-null | Coordinator | immutable |
| `approved_work_order_sha256` | Approved canonical-content hash of the referenced Work Order | SHA-256 string | required, non-null | Audit2 approval evidence, verified by Coordinator | immutable |
| `evidence_refs` | Stable repository, Git, CI, or result-artifact references | array of non-empty strings | required, non-null | Actor and Actor Runner | append-only before completion; immutable after completion |
| `actual_changed_paths` | Actual changed repository paths, sorted and deduplicated | array of safe path strings | required, non-null | Actor Runner from Git evidence | write-once after execution; empty for read-only work |
| `actual_operation_classes` | Actual operation classes observed for the Transition | array of operation-class enum values | required, non-null | Actor Runner | write-once after execution; empty before observation |
| `expected_next_stage` | Only the next fixed stage, or null when no automatic route is allowed | stage enum or null | required, nullable | Coordinator after validated result | write-once for the completed/stopped Transition |
| `human_approval_required` | Whether the next publication action requires Human Owner approval | boolean | required, non-null | Coordinator from policy | immutable for the Transition |
| `error_code` | Machine-readable STOP or reconciliation cause | non-empty string or null | required, nullable | Coordinator or Actor Runner | write-once when an error is established |
| `created_at` | Time the PENDING Transition was durably created | timezone-aware date-time | required, non-null | Coordinator state store | immutable |
| `completed_at` | Time terminal status was durably recorded | timezone-aware date-time or null | required, nullable | Coordinator state store | write-once at `COMPLETED`, `STOPPED`, or `RECONCILIATION_REQUIRED` |

The V1 JSON Schema defines the structural types, patterns, enums, and nullability. Cross-field and
Git/evidence invariants in this document are normative even when the Schema cannot express them
safely.

## Deterministic Stage Model

The `stage` enum is closed:

1. `AUDIT1_DRAFT`
2. `AUDIT2_WORK_ORDER_REVIEW`
3. `BUILDER_IMPLEMENTATION`
4. `AUDIT1_IMPLEMENTATION_AUDIT`
5. `AUDIT2_IMPLEMENTATION_REAUDIT`
6. `PUBLICATION_READY`

The only normal order is:

```text
AUDIT1_DRAFT
→ AUDIT2_WORK_ORDER_REVIEW
→ BUILDER_IMPLEMENTATION
→ AUDIT1_IMPLEMENTATION_AUDIT
→ AUDIT2_IMPLEMENTATION_REAUDIT
→ PUBLICATION_READY
```

For a valid `COMPLETED`/`PASS`, `expected_next_stage` is exactly the next value in this sequence.
For `PUBLICATION_READY`, it is null. `PUBLICATION_READY` is not a push instruction. Before Human
Owner publication approval, push is forbidden.

On `FAIL`, `BLOCKED`, ambiguity, or invariant violation, `expected_next_stage` is null and the
derived routing outcome is `automatic_next_transition = NONE`. The latter is a normative outcome,
not an additional V1 state field. The Coordinator cannot infer a skipped stage or create a new one.

## Transition Status and Verdict

The `transition_status` enum is closed:

- `PENDING`
- `RUNNING`
- `COMPLETED`
- `STOPPED`
- `RECONCILIATION_REQUIRED`

The `verdict` enum is `PASS`, `FAIL`, or `BLOCKED`, and the field is nullable. The following
cross-field rules are normative:

- `PENDING`: `verdict = null`, `completed_at = null`.
- `RUNNING`: `verdict = null`, `completed_at = null`.
- `COMPLETED`: a valid Actor result exists, so `verdict` is non-null. Normal forward routing also
  requires `verdict = PASS`.
- `STOPPED`: when an Actor returned a valid `FAIL` or `BLOCKED`, that verdict is preserved.
- `STOPPED`: when schema failure, state mismatch, or ambiguous side effect stops processing before
  a valid Actor verdict exists, `verdict = null` is allowed and `error_code` is required.
- `RECONCILIATION_REQUIRED`: `verdict = null` is allowed and `error_code` is required to explain
  the mismatch.

The Coordinator records but never reclassifies an Actor verdict. Unexpected verdict text is schema
failure, not a value that may be mapped to a valid enum.

## STOP Rules

Automatic progress stops for any of the following:

- `FAIL`
- `BLOCKED`
- schema validation failure
- unexpected verdict
- state mismatch
- dirty tree
- unexpected commit
- SHA mismatch
- scope drift
- ambiguous side effect
- remote ref race
- credential boundary violation

For a normal STOP, `transition_status = STOPPED`, `expected_next_stage = null`, and
`automatic_next_transition = NONE`. A dirty tree or unexpected commit discovered during restart
reconciliation uses `RECONCILIATION_REQUIRED` and also stops.

The Coordinator cannot generate remediation or a corrective Work Order, edit findings, expand the
Work Order, blind-retry Builder, or reclassify `FAIL` as `PASS`. It does not automatically revert
changes.

## Corrective Ownership

The only corrective flow is:

```text
Audit1 corrective draft
→ Audit2 independent review / hardening
→ FINAL APPROVED corrective work order
→ Schema validation
→ new approved transition
→ Builder
```

The existence of an Audit1 corrective draft never authorizes Builder before Audit2 approval. The
same `scope_hash` is not sufficient to reopen work. `BLOCKED` or ambiguity routes to **Human
Required → STOP**. Audit1 is the next owner for an ambiguous side effect or scope drift; this is a
normative ownership rule, not an additional V1 state field.

## Idempotency Contract

The canonical input object contains exactly:

```text
schema_version
workflow_run_id
work_item_id
stage
actor
approved_work_order_sha256
pre_stage_sha
```

`attempt` is excluded. Keys are sorted in ascending order, JSON contains no unnecessary whitespace,
the JSON byte sequence is UTF-8, and SHA-256 is applied to those bytes. The stored key is 64
lowercase hexadecimal characters.

If any required input is absent or canonicalization cannot produce one deterministic byte sequence,
the Coordinator cannot invent a key. The Transition is `BLOCKED` and `STOPPED`. A Transition with
the same `idempotency_key` already in `COMPLETED` state is never re-executed.

## Crash Recovery and Reconciliation

The persistence order is mandatory:

1. Persist the Transition as `PENDING` before Actor execution.
2. Persist `pre_stage_sha` and the verified working-tree state.
3. Only after persistence succeeds, set `RUNNING`.
4. Invoke the Actor.
5. After Actor exit, inspect actual Git state and the result artifact.
6. Record verified `post_stage_sha`.
7. Set `COMPLETED` only after all result, scope, and state validation passes.

On restart, persisted state is reconciled against actual Git state before any Actor call:

- Actual SHA equals recorded `post_stage_sha`: validate the result artifact, then recovery to
  `COMPLETED` is permitted.
- Actual SHA equals `pre_stage_sha` and no mutation exists: only a read-only Actor may be rerun.
- Builder was `RUNNING` at crash: automatic retry is forbidden.
- Dirty tree: `RECONCILIATION_REQUIRED` → STOP.
- Unexpected commit: `RECONCILIATION_REQUIRED` → STOP.
- Side-effect status is unclear: `BLOCKED` → `STOPPED`, with
  `error_code = AMBIGUOUS_SIDE_EFFECT` and next owner Audit1.
- Remote ref changed: `BLOCKED` → `STOPPED`.

Increasing `attempt` alone never authorizes a Builder rerun.

## Scope Hash Contract

Every FINAL APPROVED WORK ORDER has an independent `scope_hash`. Its canonical input object
contains exactly:

```text
schema_version
work_item_id
approved_work_order_id
approved_work_order_sha256
baseline_sha
phase
slice
allowed_paths
allowed_operation_classes
```

`approved_work_order_id`, `allowed_paths`, and `allowed_operation_classes` are not independently
mutable state fields. The Coordinator resolves them from the FINAL APPROVED WORK ORDER referenced
by `work_order_ref`. That Work Order must state all three values. Failure to resolve any value
deterministically forbids hash generation and produces `BLOCKED` → STOP.

Before hashing, object keys are sorted ascending; `allowed_paths` and
`allowed_operation_classes` are each sorted and deduplicated; nullable `slice` is encoded as an
explicit null; JSON has no unnecessary whitespace and is UTF-8. Paths are repository-relative
POSIX paths with no absolute form, backslash, or `..` segment. SHA-256 output is lowercase
hexadecimal. `approved_work_order_sha256` must equal the referenced Work Order's approved canonical
content hash.

A corrective Work Order always gets a new `scope_hash` and links the prior approved scope through
`parent_scope_hash`; it cannot reuse the prior hash as authority.

## Operation Classes and Scope Drift

A FINAL APPROVED WORK ORDER may grant Builder only these operation classes:

- `DOC_WRITE`
- `SOURCE_WRITE`
- `TEST_WRITE`
- `CONFIG_WRITE`
- `LOCAL_COMMIT`
- `READ_ONLY_VALIDATION`

It cannot grant Builder `GIT_PUSH`, `MAIN_MERGE`, `BUSINESS_WRITE`, or `PHASE_ADVANCE`.

After Builder returns, Actor Runner compares approved `allowed_paths` to
`actual_changed_paths`, approved operation classes to `actual_operation_classes`, `baseline_sha` to
actual commit ancestry, and `result_sha` to the reported result. Any mismatch produces:

```text
error_code = SCOPE_DRIFT
transition_status = STOPPED
expected_next_stage = null
next owner = Audit1
```

The Coordinator neither reverts the changes, broadens the approved scope, nor generates a new Work
Order.

## Credential and Authority Contract

- Coordinator: Git and repository-content read-only; Developer Workflow runtime state read/write;
  no commit, push, branch mutation, `main` mutation, business credential, or publication credential.
- Audit1: repository and evidence read-only.
- Audit2: separate execution context; repository and evidence read-only.
- Builder: local workspace-write only inside the FINAL APPROVED WORK ORDER; no push or business
  write.
- Actor Runner: supplies the Actor execution environment and only approved credential injection.
- Publication Runner: separate from Builder, cannot mutate source, and may act only during an
  approved publication.

Coordinator never reads token values and never stores them in state or logs. A credential boundary
violation is a STOP condition.

## Publication Contract

Publication capability remains outside automatic stage execution. It is available only after:

- Audit1 `PASS`
- Audit2 `PASS`
- identical audited `result_sha`
- authenticated Human Owner publication approval is present
- remote ref race check `PASS`

`human_approval_required` records that approval is required; it does not prove approval presence.
Approval presence must be independently verified from authenticated publication evidence referenced
by `evidence_refs`. Failure of any precondition forbids push.
