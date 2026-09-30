# ADR: PHASE 4 PRODUCT_FACT synthetic v1

- Status: Proposed for synthetic v1 implementation
- Schema: `topspeed.product_fact.synthetic.v1`
- Target: `PRODUCT_FACT`
- Scope: synthetic/internal architecture-proof

## Decision

This ADR defines a PHASE 4 synthetic ingestion slice for `UNVERIFIED` PRODUCT_FACT candidate
records. It does not authorize the implementation itself. Successful ingestion means only that a
synthetic source row satisfies this slice's approved structure and the full PRODUCT_FACT Contract.

The following invariant is mandatory:

`Contract-valid != fact-verified`

This slice does not establish production fact ingestion, VERIFIED fact issuance, human approval,
a Research Provider, an Evidence Validator, source-authority scoring, content-publication
approval, PHASE 5 calculation, or AI/LLM fact synthesis.

## Source contract

The required source fields are exactly:

- `sku`
- `fact_type`
- `fact_value`
- `data_as_of`

The only optional source field is:

- `unit`

The following source fields are forbidden:

- `fact_id`
- `verification_status`
- `source`
- `source_uri`
- `source_checksum`
- `verified_at`
- `valid_from`
- `valid_to`
- `created_at`
- `run_id`
- `task_id`

Forbidden and unknown source headers fail closed and are not silently ignored.

## SKU model and fingerprint

The source `sku` is a direct TOPSPEED internal SKU. This slice does not accept
`external_product_id`, perform `MappingEntry` resolution, create a PRODUCT_MASTER record, or issue
an SKU. Caller-supplied `known_skus` is mandatory, malformed context fails closed, and unknown or
unregistered SKUs are rejected.

Full validation is:

```python
validate_contract(
    "PRODUCT_FACT",
    record,
    known_skus=known_skus,
)
```

The deterministic mapping fingerprint binds the complete effective referential context:

```python
payload_sha256(
    {
        "strategy": "direct_internal_sku",
        "schema_version": PRODUCT_FACT_SCHEMA,
        "known_skus": sorted(known_skus),
    }
)
```

It excludes `fact_id`, `run_id`, `task_id`, `created_at`, clock values, and row order. Reuse of a
shared helper is permitted only when it deterministically represents the same effective context.

## Fact ID authority

`fact_id` is issued by the TOPSPEED Core ID layer and has the Frozen Contract shape
`fact_<canonical ULID>`. It is not source-provided. Adapter-local generation and deterministic
content hashes disguised as ULIDs are forbidden.

The future Core API follows the existing naming convention:

- `generate_fact_id() -> str`
- `validate_fact_id(value: object) -> bool`
- `require_valid_fact_id(value: str) -> str`

Implementing that API is deferred to a separately audited PRODUCT_FACT implementation task. This
ADR does not modify Core IDs.

`fact_id` is system record identity. It is not the natural key, source-ingestion identity, or an
input to the business hash. A later ingestion may generate a different random `fact_id` without
changing business identity. Exact source-duplicate detection should occur before unnecessary
clock and fact-ID generation where feasible.

## Natural key and business state

The synthetic-v1 natural key is:

```text
(sku, fact_type, source, data_as_of)
```

Every member is taken from validated Contract-record values. For one exact tuple, synthetic v1
permits one business fact state. Multiple independent facts with the same tuple are outside this
slice. `fact_id` and `fact_value` are not natural-key members. A changed `fact_value` under the same
key is a conflict, not a new fact.

This natural key is local to `topspeed.product_fact.synthetic.v1` and is not a production-wide
PRODUCT_FACT natural-key claim.

The business hash contains exactly these normalized business-state fields:

- `sku`
- `fact_type`
- `fact_value`
- `unit`
- `verification_status`

Absent and null `unit` represent the same no-unit state for business hashing. The hash excludes
`fact_id`, `source`, `data_as_of`, `created_at`, `run_id`, `task_id`, the mapping fingerprint, the
source-ingestion checksum, and all shared provenance metadata. `source` and `data_as_of` are
identity context through the natural key rather than business-hash state.

## Verification authority

The source cannot provide `verification_status` or `verified_at`. The Adapter creates every
candidate with:

```text
verification_status = UNVERIFIED
```

`verified_at` remains absent. Synthetic ingestion never produces `VERIFIED`, `REJECTED`, or
`EXPIRED`, and successful ingestion never transitions an existing fact to VERIFIED. Source name,
trust, or checksum cannot grant verification.

VERIFIED status and `verified_at` belong to a future dedicated Evidence Validation/Audit Gate. The
transition mechanism is intentionally not defined here.

## Fact type policy

The Frozen Contract defines `fact_type` as a non-empty string and provides no taxonomy, enum, or
allowlist. This slice does not invent one. A source value is treated as an already internally
classified input, not as authority for an external provider to create TOPSPEED taxonomy.

The value must be a non-empty string without leading or trailing whitespace. Case is preserved.
The Adapter performs no trimming, alias conversion, case normalization, or semantic inference.
Whitespace-bearing values are rejected. A future taxonomy requires a separate Architecture
decision.

## Fact value policy

The official tabular representation of `fact_value` is JSON text. Input must be a string whose
decoded root is an object or array. The Contract record stores the parsed object or array, and its
business hash uses the existing canonical payload semantics.

The following values fail closed:

- blank input
- JSON null
- string, number, or boolean scalar roots
- malformed JSON
- duplicate object keys at any depth
- `NaN`, `Infinity`, or `-Infinity`
- native mapping or list inputs
- any other non-string input

The Adapter does not use `str(value)` coercion or parse implicit Python representations.

## Optional unit policy

If the `unit` header is omitted, the record field may remain absent. If it is present with a blank
or `None` value, the Adapter normalizes it to null. A nonblank value must be a string and is
preserved exactly.

The Adapter performs no trimming, case normalization, conversion, or alias mapping. If
normalization provenance is recorded, blank-unit-to-null may be listed explicitly.

## Source and temporal fields

`record.source` is generated only from verified `SourceMetadata.source`; a source row cannot
provide it.

`record.data_as_of` is a required, timezone-aware source-row DATETIME. Its validated source
representation is preserved. Missing values are not inferred, and the value is not replaced by
`SourceMetadata.fetched_at`, an injected clock, `created_at`, or another row field.

`created_at` is generated from one injected timezone-aware clock value per successfully processed
batch. Every accepted record in that batch uses the same value. The Adapter does not use a
source-created timestamp, `fetched_at`, a direct wall-clock call, or a different value per row.

## Correlation fields

Record optionality does not make an ingestion attempt anonymous. Future `ingest_product_fact()`
requires a caller `run_id`, validates it through the existing Core ID boundary, and stores it as
`record.run_id` and shared `Provenance.run_id`.

When `tool_result.run_id` is present, it must equal the caller `run_id`; mismatch fails closed. The
source never provides `run_id`, and the Adapter does not generate a missing run ID.

The Adapter does not generate a task ID. If `tool_result.task_id` is present, it is preserved
exactly as `record.task_id` and `Provenance.task_id`. If absent, the record field may remain absent
and provenance remains `None`.

Invalid correlation IDs are not trimmed, repaired, removed, or regenerated. Final Contract
validation remains authoritative for record-level ID shape.

## Record-level evidence provenance

Although the PRODUCT_FACT Contract permits `source_uri` and `source_checksum`, synthetic v1 does
not populate either field. Batch raw-source provenance is not automatically row-specific fact
evidence provenance.

The Adapter does not copy `SourceMetadata.source_uri` into `record.source_uri`, or the raw batch
checksum into `record.source_checksum`, merely because they exist. Shared ingestion `Provenance`
may retain the sanitized source reference, verified raw checksum, `fetched_at`, `data_as_of`,
run/task correlation, schema, and ingestion identity. Those values remain distinct from
record-level evidence provenance.

Record-level URI/checksum support requires a later dedicated evidence-provenance decision.

## Validity fields

Synthetic v1 excludes `valid_from`, `valid_to`, and `verified_at`. It defines no date-order rule,
automatic EXPIRED transition, validity/status coupling, or verification lifecycle. Those decisions
belong to a later verification/lifecycle Gate.

## Source-ingestion identity

The source-ingestion identity is the canonical hash of exactly:

```text
target_contract = PRODUCT_FACT
schema_version = topspeed.product_fact.synthetic.v1
source_checksum = verified raw-source checksum
mapping_fingerprint = direct-internal-SKU fingerprint bound to known_skus
```

It excludes `fact_id`, clock values, `created_at`, row order, `run_id`, and `task_id`. The same
source checksum, effective referential context, target Contract, and schema is a SOURCE_DUPLICATE
idempotent no-op.

## Duplicate, conflict, and publication semantics

- Same natural key plus the same canonical business hash is a BUSINESS_DUPLICATE no-op.
- Same natural key plus a different canonical business hash is a NATURAL_KEY_CONFLICT and cannot
  be published.
- Exact source-ingestion identity is a SOURCE_DUPLICATE idempotent no-op.

Synthetic v1 supports no update, replacement, supersession, version history, automatic
expiration, or record mutation. Failed, partial, rejected, and conflicting batches cannot replace
current/latest publisher state.

Future implementation uses the existing shared `AcceptedRecord`, `Provenance`, `BatchResult`,
`ReasonCode`, `InMemoryReferencePublisher`, and contract-scoped identity semantics. Existing
records must pass Contract-coherence validation before contract-specific duplicate/conflict
evaluation. No shared publisher redesign is approved.

Different Contracts remain isolated by `(target_contract, natural_key)`. Malformed cross-contract
records are not silently ignored. Semantic tests must demonstrate coexistence of PRODUCT_MASTER,
PRODUCT_FACT, AD_DAILY, CHANNEL_DAILY, and INVENTORY using actual public ingestion results and the
actual reference publisher.

## Phase and authority boundaries

This ADR does not approve contribution-margin, advertising, inventory, fact-confidence, or
source-authority calculations; automatic verification; fact synthesis; LLM calls; LINER/Research
Provider; Evidence Validator implementation; CONTENT_ASSET claim linking; approval execution; or
production writes.

Production semantics are not approved. Verification authority is not granted to the Adapter.
PHASE 5 behavior is not included, and PHASE 5 remains not started.

Frozen document modification: none. This ADR neither modifies nor reinterprets the Frozen
Contract. Core fact-ID API implementation is deferred to the separately audited PRODUCT_FACT
implementation work. This ADR commit itself does not authorize PRODUCT_FACT implementation.

## Architecture Gate finding closure

- `PF-ADG-001`: closed by assigning fact-ID issuance to the Core ID layer and approving the future
  API naming convention without implementing it here.
- `PF-ADG-002`: closed by defining the synthetic-v1 natural key, business-state hash, and their
  separation from record identity.
- `PF-ADG-003`: closed by limiting ingestion to Adapter-generated UNVERIFIED candidates and
  deferring verification transitions to a future Gate.
- `PF-ADG-004`: closed by selecting direct internal SKU input, mandatory `known_skus` validation,
  and a referential-context-bound fingerprint.
- `PF-ADG-005`: closed by defining strict JSON-text input, object/array roots, and fail-closed
  parsing rules.
- `PF-ADG-006`: closed by separating shared batch ingestion provenance from omitted record-level
  evidence URI/checksum fields.
- `PF-ADG-007`: closed by preserving already internally classified non-whitespace `fact_type`
  strings without inventing a taxonomy.
- `PF-ADG-008`: closed by defining immutable duplicate, conflict, idempotency, and publication
  behavior.
- `PF-ADG-009`: closed by defining run/task correlation and explicitly excluding validity and
  verification lifecycle fields.
- `PF-ADG-010`: closed by fixing the slice schema identifier to
  `topspeed.product_fact.synthetic.v1` without changing the global Contract schema.

Closure means that coherent synthetic-v1 decisions are documented. It does not mean that any
PRODUCT_FACT implementation exists or is authorized.
