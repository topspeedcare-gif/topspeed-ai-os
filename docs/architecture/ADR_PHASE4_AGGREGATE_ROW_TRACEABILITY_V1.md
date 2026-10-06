# ADR: PHASE 4 aggregate row traceability v1

## 1. Status and classification

```text
Architecture =
PHASE 4 AGGREGATE ROW TRACEABILITY V1

Classification =
Normative Internal PHASE 4 Architecture Decision

Scope =
Synthetic/Internal Aggregate Outcome Traceability

Business Data Contract =
NO

Frozen Architecture Change =
NO

Data Contract Change =
NO

Contract JSON Schema Change =
NO

Implementation Authorization =
NO

Phase 4 Completion Authorization =
NO

Phase 5 Entry Authorization =
NO
```

This ADR does not create or change the PHASE 4 completion condition. It defines only the internal
aggregate hardening needed to satisfy the published condition:

```text
모든 row의 Source와 기준일 추적 가능
```

## 2. Context and decision

The six published PHASE 4 source-ingestion Adapters already produce shared aggregate outcomes, but
the four actual row-level outcomes do not share one explicit immutable carrier for Source and
effective-date evidence. This ADR defines:

```text
RowTrace =
PHASE 4 내부 immutable aggregate outcome carrier
```

`RowTrace` is not a Business Data Contract. It applies to actual row-level outcomes represented by:

1. `AcceptedRecord`
2. `DuplicateRecord`
3. `RejectedRecord`
4. `ConflictRecord`

A batch-level failure, or a failure before row materialization, must not be represented as an actual
row-level outcome.

## 3. Exact RowTrace field set

`RowTrace` contains exactly these fields:

```text
target_contract
schema_version
source
source_reference
source_checksum
source_row_reference
data_as_of
data_as_of_state
run_id
task_id
```

No additional field is part of Aggregate Row Traceability V1, whether required or optional.

## 4. Field authority

| Field | Authority |
| --- | --- |
| `target_contract` | The fixed target Contract of the Adapter |
| `schema_version` | The approved synthetic schema identifier of the Adapter |
| `source` | Validated `SourceMetadata.source` |
| `source_reference` | The sanitized source reference that passed the existing approved sanitizer and safe-reference boundary |
| `source_checksum` | The existing source checksum calculated from and verified against the exact original `SensitiveBytes` |
| `source_row_reference` | The existing Adapter row-reference authority |
| `data_as_of` | A timezone-aware datetime produced by the existing PHASE 4 datetime parser, or null |
| `data_as_of_state` | Exactly `VALID`, `MISSING`, or `INVALID` |
| `run_id` | The validated caller-supplied `run_id` |
| `task_id` | The existing approved task-ID semantics of the individual Adapter, as hardened below |

If an existing Adapter requires task-ID validation at its already approved boundary, `task_id` is
the `ToolResult.task_id` that passed that validation. If an existing Adapter does not require
separate task-ID validation, `task_id` is the `ToolResult.task_id` or null already carried by the
existing `Provenance` semantics.

Aggregate Row Traceability V1 adds no global task-ID validation, rejection gate, or task-ID
generation. A source row cannot override the target Contract, schema version, source identity,
source checksum, run ID, or task ID.

## 5. Data-as-of states and relationship

`data_as_of_state` allows exactly three values:

```text
VALID =
Preserve in data_as_of the timezone-aware datetime returned by the existing PHASE 4 datetime parser

MISSING =
data_as_of = null

INVALID =
data_as_of = null
```

`MISSING` and `INVALID` remain distinct. A missing or invalid source value must not be replaced with
`clock()`, `fetched_at`, `created_at`, current time, or an arbitrary default date. A malformed raw
`data_as_of` value must not be copied into `RowTrace`, `Provenance`, an error, or a log. Failure
explanation remains within the existing reason-code and sanitized-summary boundaries.

For every Accepted or `BUSINESS_DUPLICATE` outcome:

```text
trace.data_as_of == provenance.data_as_of
```

Applying the existing PHASE 4 datetime parser to the accepted candidate's source `data_as_of`
value must also produce exactly `trace.data_as_of`. This ADR adds no datetime normalization rule.

## 6. Outcome binding and constructor compatibility

### 6.1 AcceptedRecord

`AcceptedRecord.trace` is a deterministic projection of its existing `Provenance` and has
`data_as_of_state = VALID`. It is not an independent caller input. Existing `Provenance` is neither
removed nor reduced.

### 6.2 DuplicateRecord

Only an existing row-level `BUSINESS_DUPLICATE` is the `DuplicateRecord` outcome covered here.
`DuplicateRecord.trace` is a deterministic projection of its existing `Provenance`, is not an
independent caller input, and has `data_as_of_state = VALID`. Existing duplicate meaning and
classification do not change.

### 6.3 RejectedRecord

`RejectedRecord.trace` has type `RowTrace | null`. An actual row-level rejection requires a trace.
A batch-level rejection requires a null trace. Existing batch-failure semantics use
`source_row_reference == "batch"` for this boundary.

The existing top-level `source_row_reference`, `reason_code`, `sanitized_summary`,
`source_reference`, and optional `natural_key` fields remain. When a value with the same meaning is
present both at top level and in `RowTrace`, exact equality is required and mismatch fails closed.
The date state reflects the actual date-validation result independently of the rejection reason:
a valid date plus an unregistered SKU is `VALID`, a missing date is `MISSING`, and an invalid date
is `INVALID`.

### 6.4 ConflictRecord

`ConflictRecord.trace` has type `RowTrace | null`. An actual row-level conflict requires a trace and
has `data_as_of_state = VALID`. The existing top-level `source_row_reference`, `natural_key`,
`conflict_reason`, and `source_reference` fields remain. Same-meaning top-level and trace values
must be exactly equal; mismatch fails closed.

### 6.5 Constructor compatibility

Adding `RowTrace` alone must not change existing positional construction semantics.
`AcceptedRecord.trace` and `DuplicateRecord.trace` must not become newly required caller-supplied
constructor arguments. Optional trace support for `RejectedRecord` and `ConflictRecord` must be
additive and must not unnecessarily break existing construction.

## 7. Provenance projection

For Accepted and `BUSINESS_DUPLICATE` outcomes, these values must be exact projections:

```text
trace.target_contract == provenance.target_contract
trace.schema_version == provenance.schema_version
trace.source == provenance.source
trace.source_reference == provenance.source_reference
trace.source_checksum == provenance.source_checksum
trace.source_row_reference == provenance.source_row_reference
trace.data_as_of == provenance.data_as_of
trace.run_id == provenance.run_id
trace.task_id == provenance.task_id
```

The same semantic value must not be accepted as two independent caller inputs that can diverge.
The authority or meaning of existing `Provenance` is not reduced.

## 8. SOURCE_DUPLICATE boundary

`SOURCE_DUPLICATE` is a batch-level idempotent replay outcome. It is not a row-level
`DuplicateRecord` or `BUSINESS_DUPLICATE`.

An exact source replay preserves all existing behavior:

- no fabricated row record
- no fabricated `RowTrace`
- unchanged ingestion identity
- unchanged zero-clock semantics
- unchanged zero-ID semantics
- unchanged idempotent no-op meaning
- no publisher mutation

RowTrace coverage applies only to materialized Accepted, Rejected, `BUSINESS_DUPLICATE`, and
Conflict row outcomes.

## 9. Source safety

`RowTrace` is not a raw-payload carrier. It must not retain:

- raw `SensitiveBytes`
- credentials, access tokens, or authorization headers
- unsafe source or storage URIs
- malformed raw `data_as_of`
- an entire source row
- raw exception text

`source_reference` reuses the existing sanitizer and safe-reference boundary. This ADR creates no
URI scheme allowlist, credential taxonomy, or ambiguous-URI security classification.

## 10. Identity, time, and factory non-interference

`RowTrace` changes none of these canonical inputs or identities:

- natural key
- business hash
- mapping fingerprint
- ingestion identity
- source checksum
- Contract record identity

Adding `RowTrace` alone must not change accepted/rejected classification, duplicate/conflict
classification, `BatchStatus`, publish eligibility, or publisher current/latest state. `RowTrace`
has no separate ID, hash, or ingestion identity.

`RowTrace` adds no timestamp, including `created_at`, `updated_at`, `recorded_at`, `rejected_at`, or
`conflicted_at`. It causes no new `clock()` call and issues no run ID, task ID, Contract record ID,
or aggregate outcome ID. Existing duplicate and idempotency paths retain their clock and ID-factory
call behavior.

## 11. Publisher and atomicity

The shared publisher API and responsibility do not change. The publisher continues to process only
Contract-valid accepted records under its existing rules. `RejectedRecord`, `ConflictRecord`, and
`RowTrace` are diagnostic or audit aggregate state and are not published as Business Contract
records.

The existing invariant remains normative:

```text
오류 batch가 current/latest로 승격되지 않음
```

## 12. Six-Contract boundary

This Architecture applies to exactly the six published PHASE 4 Adapters:

1. `PRODUCT_MASTER`
2. `PRODUCT_FACT`
3. `CHANNEL_DAILY`
4. `AD_DAILY`
5. `INVENTORY`
6. `CONTENT_ASSET`

Each Adapter uses only its own fixed `target_contract` and `schema_version`. Cross-contract
contamination fails closed. No source-ingestion Contract is added.

## 13. Backward compatibility

The existing meaning of `AcceptedRecord`, `DuplicateRecord`, `RejectedRecord`, and
`ConflictRecord` remains. Existing top-level fields are not deleted or renamed. `RowTrace` is
additive aggregate hardening, adds no field to a Business Contract JSON Schema, and is not required
for batch-level failures.

## 14. Future implementation test obligations

A future implementation Work Order must require at least the following tests. This docs-only ADR
does not implement them.

### 14.1 Common

- actual row-level four-outcome coverage
- exact `RowTrace` field set
- immutability
- required and nullability behavior

### 14.2 Authority

- Adapter-fixed target Contract
- Adapter-fixed schema version
- validated metadata source
- exact source-checksum relationship
- caller run ID
- existing per-Adapter task-ID semantics
- rejection of source-row authority override
- adding `RowTrace` alone does not change any Adapter's existing task-ID acceptance, rejection, or
  classification result

### 14.3 Data as of

- valid produces `VALID` plus a timezone-aware datetime
- missing produces `MISSING` plus null
- invalid produces `INVALID` plus null
- no clock substitution
- no fetched, created, or current-time substitution
- no retention of a malformed raw value
- for Accepted and `BUSINESS_DUPLICATE`, applying the existing PHASE 4 datetime parser to source
  `data_as_of` produces exactly `trace.data_as_of`

### 14.4 Outcomes

- Accepted trace
- `BUSINESS_DUPLICATE` trace
- Rejected valid-date trace
- Rejected missing-date trace
- Rejected invalid-date trace
- Conflict trace
- Provenance projection equality
- top-level compatibility equality
- batch-level rejection trace null

### 14.5 SOURCE_DUPLICATE

- batch-level replay remains rowless
- no fabricated `RowTrace`
- unchanged ingestion identity
- preserved zero-clock behavior
- preserved zero-ID behavior
- no publisher mutation

### 14.6 Security

- unsafe source-reference rejection
- `SensitiveBytes` non-retention
- zero credential leakage
- zero raw-exception retention
- zero malformed-raw-date retention

### 14.7 Regression

- unchanged natural key
- unchanged business hash
- unchanged mapping fingerprint
- unchanged ingestion identity
- unchanged classification
- unchanged `BatchStatus`
- unchanged publish eligibility
- unchanged publisher atomicity
- unchanged current/latest state

### 14.8 Isolation

- correct target for all six Adapters
- valid cross-contract coexistence
- malformed cross-contract state fails closed
- zero `APPROVAL_QUEUE` coupling
- zero `AI_RUN_LOG` coupling

## 15. Explicit non-decisions

This ADR does not decide, change, or authorize:

- Frozen Architecture, `DATA_CONTRACT_V1.md`, Contract JSON Schema, or `IMPLEMENTATION_PLAN_V1.md`
- production database or external persistence
- `AI_RUN_LOG` writer
- `APPROVAL_QUEUE`, approval lifecycle, or execution lifecycle
- PHASE 5 calculation
- LIVE API, credential access, or external business write
- PHASE 4 completion, PHASE 5 entry, or next-Phase selection
- an additional source-ingestion Contract
- shared publisher redesign
- runtime or test implementation
