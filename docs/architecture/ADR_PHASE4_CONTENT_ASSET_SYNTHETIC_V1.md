# ADR: PHASE 4 CONTENT_ASSET synthetic/internal v1

## 1. Status

- Status: Proposed for synthetic v1 implementation
- Runtime authorization: not granted by this ADR commit
- Phase 4: not complete
- Phase 5: not started

This ADR defines Architecture for a future synthetic/internal implementation. A separate audited
implementation Work Order is required before any `CONTENT_ASSET` runtime or Core asset-ID change
may begin.

## 2. Context

The five published Phase 4 slices do not include `CONTENT_ASSET`. The Frozen Architecture and
Data Contract already define the Contract, but a future Builder also needs fixed decisions for
source fields, IDs, claim references, immutable identity, provenance, and publication safety.

This decision closes only that Architecture gap. A Contract-valid DRAFT candidate is not an
approved or published asset, does not prove the truth of a claim, and does not prove that the
referenced asset bytes exist or match the source-declared asset checksum.

## 3. Authority

The authority order is:

1. Frozen Architecture
2. `DATA_CONTRACT_V1.md`
3. `IMPLEMENTATION_PLAN_V1.md`
4. current Contract Schema and registry
5. approved and published ADRs
6. actual implementation
7. the approved Work Order for this ADR

This ADR does not modify or reinterpret a higher authority. The Frozen `CONTENT_ASSET` Schema and
the existing shared Phase 4 result and publisher model remain authoritative.

## 4. Scope

The scope is synthetic/internal architecture-proof candidate ingestion into `CONTENT_ASSET`.
Candidates are DRAFT only.

The following are not approved: production asset synchronization, actual Drive asset download,
asset-byte verification, approval execution, publication execution, external storage writes, and
runtime implementation of this ADR.

## 5. Schema identifier

- Schema identifier: `topspeed.content_asset.synthetic.v1`
- Target Contract: `CONTENT_ASSET`
- Candidate status: `DRAFT`

This identifier selects this synthetic mapping and identity policy. It does not replace or modify
the Frozen JSON Schema identifier.

## 6. Source/input contract

The Phase 3 typed boundary remains authoritative. A future ingestion call requires this envelope:

- one `ToolResult`
- its `SourceMetadata`
- a `SensitiveBytes` `raw_result`
- a `TabularData` `parsed_result` produced in the same `ToolResult`
- caller-provided `known_skus`
- actual existing `PRODUCT_FACT` referential context
- actual existing `CONTENT_ASSET` records
- a caller-provided `run_id`
- a required valid `ToolResult.task_id`
- an injected timezone-aware clock

The raw checksum must be verified before the Adapter trusts or consumes the parsed result. Phase 4
does not introduce another generic parser or force all Phase 3 formats through a new UTF-8 decoder.

Source row required fields are exactly:

- `sku`
- `asset_type`
- `title`
- `mime_type`
- `storage_uri`
- `checksum_sha256`
- `version`
- `generated_by`
- `claim_fact_ids`
- `data_as_of`

There are no optional source-row fields. Unknown fields fail closed.

Field rules are:

- `title`, `mime_type`, and `generated_by` are required nonblank strings. Accepted values are
  preserved exactly; trim-and-accept, inference, normalization, and automatic correction are
  forbidden.
- `mime_type` uses current Contract validation. It is not inferred from an extension or URI,
  sniffed from bytes, or alias-normalized.
- `asset_type` uses the current Contract enum without Adapter-local expansion.
- `checksum_sha256` is the source-declared asset-content checksum. It must already satisfy the
  lowercase canonical Contract shape; the Adapter neither lowercases it nor recomputes it from
  asset bytes.
- `claim_fact_ids` is strict JSON array text. Malformed JSON, a scalar root, non-string members,
  blank or malformed IDs, duplicate IDs, and parser ambiguity fail closed. An empty array is
  allowed. The validated record may preserve input order; only business hashing sorts the IDs.
- `data_as_of` is required, timezone-aware under Contract rules, and preserved from the validated
  source value.

## 7. Forbidden source fields

Forbidden source fields include exactly these reserved/provenance fields:

- `asset_id`
- `status`
- `approved_by`
- `source`
- `created_at`
- `updated_at`
- `run_id`
- `task_id`
- `approval_id`
- `audit_status`
- `idempotency_key`
- `source_checksum`
- `verification_status`

They are rejected rather than ignored. Any other field outside the exact source contract is also
an unknown field and fails closed.

## 8. Asset-ID authority

`asset_id` is not source-provided. Its authority is the TOPSPEED Core ID layer. A future runtime
prerequisite is the following API in `topspeed_ai_os.core.ids`, following the current prefixed-ULID
and error conventions:

- `generate_asset_id()`
- `validate_asset_id()`
- `require_valid_asset_id()`

The required format is `asset_<canonical ULID>`. The current repository does not implement these
APIs. This ADR does not authorize their implementation or a package-root export.

`asset_id` is record identity. It is excluded from the natural key, business hash, and source-
ingestion identity. Random asset IDs must never bypass duplicate detection, and rejected or
duplicate paths must not consume one unnecessarily.

## 9. SKU strategy

The strategy is direct internal SKU:

- the source value is a TOPSPEED internal SKU
- caller-supplied `known_skus` is required
- exact membership is required
- unknown or unregistered SKU is rejected
- mapping, generation, trimming, case conversion, and `vendorItemId` substitution are forbidden
- asset/fact references may not cross SKUs

Malformed `known_skus` context fails closed. An ordinary `Exception` from an approved bounded
dependency may be translated to a fail-closed result at that boundary; `BaseException` propagates.

## 10. Claim-fact referential strategy

The Frozen relationship is:

```text
CONTENT_ASSET.claim_fact_ids
-> PRODUCT_FACT.fact_id
-> same SKU
```

Every referenced fact must have a structurally valid Fact ID, actually exist, be a structurally
and coherently valid `PRODUCT_FACT`, have the same SKU as the asset, and have
`verification_status == VERIFIED`.

Unknown, malformed, duplicate, cross-SKU, UNVERIFIED, or synthetic imaginary Fact IDs fail closed.
A malformed existing fact also fails closed. `CONTENT_ASSET` ingestion cannot create facts,
create VERIFIED facts, or reference a fact generated inside the same asset batch.
`claim_fact_ids = []` is allowed.

The Adapter owns Fact-ID validation, duplicate rejection, existence lookup, same-SKU and VERIFIED
checks, and referential-context construction. The existing Contract validator remains responsible
for `CONTENT_ASSET` shape, `known_skus`, and existing same-SKU reference validation. Audit and
Approval retain truth assessment, expression acceptability, human approval, and publication
approval.

## 11. Status/approved_by boundary

Every synthetic-v1 candidate has:

```text
status = DRAFT
approved_by = null
```

Neither value is source-controlled. This slice forbids APPROVED or PUBLISHED creation, inferred
approval, generated approver identity or approval time, status transitions, `APPROVAL_QUEUE`
creation, publication, Drive writes, channel publication, and mutation of an existing asset's
status. The Frozen Schema remains unchanged.

## 12. Storage URI/checksum ownership

`storage_uri` is a required source string. Blank input and surrounding-whitespace input are
rejected rather than trimmed. Accepted values are preserved exactly and validated by the Frozen
Contract and current Schema/validator.

In addition to Frozen URI validation, `storage_uri` reuses the existing repository source-reference
safety boundary in `topspeed_ai_os.tools.redaction.sanitized_source_uri`, with the same exact-
equality enforcement as `topspeed_ai_os.data_hub.adapter._safe_reference`:

```text
sanitized = sanitized_source_uri(storage_uri)
accept only if sanitization succeeds and sanitized == storage_uri
```

That existing boundary rejects URI userinfo when either a username or password is present. For each
query pair, it percent-decodes the parameter name through the existing implementation, lowercases
it, and rejects an exact match in this current set:

- `access_token`
- `token`
- `authorization`
- `signature`
- `secret`
- `refresh_token`

The sanitizer removes URI fragments, so a fragment makes the sanitized value differ from the
original and exact-equality enforcement rejects it. Sanitizer failure also fails closed. An accepted
`storage_uri` is preserved exactly and is never rewritten.

Unsafe input is not placed in a validated `CONTENT_ASSET` record, human-readable error detail, log,
or persistent provenance. Failure reporting uses only a sanitized, non-sensitive summary consistent
with the existing source-reference boundary; this ADR introduces no new logging or redaction
subsystem.

This reuse does not claim detection of every provider-specific signed URL, credential-bearing URI
pattern, possible secret parameter, or ambiguous URI. In particular, vendor-specific names such as
`X-Amz-Signature` and `X-Goog-Signature` are not claimed as covered by the current exact-name set.
Synthetic v1 adds no URI scheme allowlist, secret taxonomy, canonicalizer, or production storage
policy. It does not modify the existing sanitizer, add a CONTENT_ASSET-specific validator,
dereference, download, check existence, convert schemes, or rewrite URLs.

Two checksum concepts remain separate:

1. `SourceMetadata.checksum_sha256` proves raw source payload provenance. It is verified by hashing
   the exact original `SensitiveBytes` and comparing exactly. Decoded or re-encoded text,
   normalized newlines, parsed rows, serialized rows, and sorted rows are not checksum inputs.
2. `CONTENT_ASSET.checksum_sha256` is the source-declared checksum of referenced asset content. In
   this slice it receives format validation only. There is no asset download, recomputation, or
   independent byte-verification claim.

Neither checksum may substitute for the other.

## 13. Raw/parsed result provenance

The same `ToolResult` must supply `SourceMetadata`, `SensitiveBytes raw_result`, and
`TabularData parsed_result`:

```text
raw source bytes
-> Phase 3 format-specific parsing
-> ToolResult(SourceMetadata, SensitiveBytes, TabularData)
-> Phase 4 exact raw-checksum verification
-> CONTENT_ASSET normalization and validation
```

Missing `SensitiveBytes`, missing or invalid `TabularData`, an invalid relationship between the
two, or checksum mismatch is a rejection. Parsed rows alone are insufficient evidence. Phase 3,
not this Adapter, owns format-specific parsing.

## 14. Task/run authority

`task_id` is required and non-null for every accepted candidate. Its authority is
`ToolResult.task_id`; it must pass the existing Core task-ID boundary and be preserved exactly in
the record. It is never supplied by a row, generated by the Adapter, replaced with `run_id`, or
reused from prior state. Null, blank, missing, or malformed values fail closed. If a future
interface separately supplies a caller task ID, exact equality with `ToolResult.task_id` is
required or the batch is rejected.

`run_id` is required from the caller, validated through the existing Core run-ID boundary, and
stored in every accepted record. A row cannot provide it and the Adapter cannot generate it. If
`ToolResult.run_id` is present, it must exactly equal caller `run_id`; mismatch is rejected.

Both IDs are required correlation metadata but are excluded from the natural key, business hash,
and source-ingestion identity.

## 15. Version policy

`version` authority is the source row. It must be an integer but not a Boolean, and must be
positive for synthetic v1. String and float coercion, Adapter auto-increment, and existing-record
mutation are forbidden. One logical key/version state is immutable.

## 16. Natural key

The synthetic-v1 natural key is exactly:

```text
(sku, asset_type, storage_uri, version)
```

It is local to `topspeed.content_asset.synthetic.v1`, not a production-wide identity claim. It
uses accepted values without whitespace, case, or URI normalization. `generated_by` and random
`asset_id` are excluded.

## 17. Business hash

The canonical business-state fields are exactly:

- `sku`
- `asset_type`
- `title`
- `mime_type`
- `storage_uri`
- `checksum_sha256`
- `version`
- `generated_by`
- `sorted(claim_fact_ids)`
- `status`

`generated_by` appears exactly once. It is preserved exactly and is neither normalized, inferred,
nor corrected. A change to it under the same natural key changes the business hash.

The hash excludes exactly these provenance/non-business inputs:

- `asset_id`
- `source`
- `data_as_of`
- `created_at`
- `updated_at`
- `run_id`
- `task_id`
- `approved_by`
- `SourceMetadata` checksum

No other clock or ingestion-provenance value is added. Canonical encoding is UTF-8 JSON with
sorted object keys and compact separators; lists are sorted only where explicitly stated. The
digest is lowercase SHA-256 hex.

Thus the same natural key and complete hash is a business duplicate. The same key with changed
`generated_by`, title, MIME type, asset checksum, or claim IDs is a conflict. A different random
`asset_id`, or a difference only in excluded provenance, leaves the business hash unchanged.

## 18. Fact-context fingerprint

For each referenced `PRODUCT_FACT`, the canonical field set is exactly:

- `fact_id`
- `sku`
- `fact_type`
- `fact_value`
- `unit`
- `verification_status`

No other fact field is an input. In particular, source, `data_as_of`, `created_at`, `run_id`,
`task_id`, `verified_at`, `valid_from`, `valid_to`, `source_uri`, `source_checksum`, and other
provenance are excluded.

Actual referenced records are sorted by `fact_id`. Each becomes an object containing those exact
six keys. `fact_value` uses the stored validated JSON value. Missing and null `unit` canonicalize
consistently with the existing PRODUCT_FACT synthetic-v1 no-unit semantics. The list is encoded as
UTF-8 canonical JSON with sorted object keys and compact separators, then hashed to lowercase
SHA-256 hex. The canonical input for no referenced facts is `[]`.

The fingerprint is computed from actual existing records. A stored business hash or caller-
supplied fingerprint is never substituted.

## 19. Source-ingestion identity

The source-ingestion identity is the canonical hash of exactly these four top-level fields:

```text
target_contract = CONTENT_ASSET
schema_version = topspeed.content_asset.synthetic.v1
source_checksum = verified checksum of the original SensitiveBytes from the same ToolResult
mapping_fingerprint = deterministic hash of the approved effective referential context
```

Its shape is equivalent to:

```python
payload_sha256(
    {
        "target_contract": "CONTENT_ASSET",
        "schema_version": CONTENT_ASSET_SCHEMA,
        "source_checksum": verified_source_checksum,
        "mapping_fingerprint": mapping_fingerprint,
    }
)
```

There is no fifth top-level field. `SourceMetadata` source identity, canonical source-row payload,
raw context objects, `known_skus`, the fact-context fingerprint, `run_id`, `task_id`, clock, and
random `asset_id` are not separate top-level ingestion-identity inputs.

The deterministic `mapping_fingerprint` encapsulates the direct-internal-SKU strategy identity,
the approved schema/strategy version, sorted and deduplicated `known_skus`, and the exact
`PRODUCT_FACT` referential-context fingerprint defined in section 18. Those values are not exposed
again at the ingestion-identity top level. The fact context remains actual existing records reduced
to exactly `fact_id`, `sku`, `fact_type`, `fact_value`, `unit`, and `verification_status`; no seventh
field is added, and neither a stored business hash nor a caller-supplied fact fingerprint may
substitute for it.

The ingestion identity excludes `run_id`, `task_id`, clock, `created_at`, `updated_at`, random
`asset_id`, and retry count. Those values cannot turn an exact replay into a new ingestion identity.

The Adapter must first perform enough deterministic structural parsing and actual fact-context
resolution to canonicalize validated `claim_fact_ids` and construct the approved
`mapping_fingerprint`; it must not fingerprint unparsed or unvalidated claims. It then determines
the source-ingestion identity and checks actual existing state for an exact source duplicate before
invoking the asset-ID factory or calling the injected clock. If a matching ingestion identity
exists, it immediately returns a source-duplicate idempotent no-op with zero asset-ID factory calls,
zero clock calls, and zero publisher mutation. This ordering does not authorize another
Architecture decision or optimization.

## 20. Duplicate semantics

- Same source-ingestion identity is a source duplicate and idempotent no-op. It invokes neither the
  asset-ID factory nor the clock, mutates no publisher state, creates no accepted candidate state,
  and has `publish_eligible == false`.
- Within one batch, the same natural key and same complete business hash produces one business
  candidate plus duplicate classification.
- Against existing state, the same natural key and same complete business hash preserves existing
  state and returns a duplicate result; no new asset ID is required for that duplicate state.

## 21. Conflict semantics

The same natural key with a different complete business hash is `NATURAL_KEY_CONFLICT`. It is not
publishable and leaves existing state unchanged. In particular:

```text
same natural key + changed generated_by
-> different business hash
-> NATURAL_KEY_CONFLICT
```

A changed referential context must not silently reuse stale identity. Invalid reference context
fails closed. Failed, partial, and conflicting candidate sets are never promoted.

## 22. Idempotency

Retry count, random asset-ID differences, clock values, and excluded provenance cannot change
source-ingestion or business identity. Exact replay has no persistent side effect. Source-duplicate
classification precedes both asset-ID factory invocation and `clock()` invocation, not merely
persistent timestamp mutation, and it precedes publisher mutation.

## 23. Time/source provenance

- `data_as_of` is the required source-semantic effective time. It is timezone-aware under Contract
  rules, preserved from the validated row, and never replaced by `fetched_at` or current time.
- `source` comes from verified `SourceMetadata.source`, not a row, and is not rewritten.
- `created_at` and `updated_at` come from one injected timezone-aware clock value per accepted
  batch. A new DRAFT candidate has `created_at == updated_at`, and all accepted rows in that batch
  share that value.
- Replay or duplicate handling creates no persistent timestamp state. Failure cannot mutate
  publisher timestamps.

## 24. Failure boundary

The batch is non-publishable for malformed envelope objects; missing or invalid source metadata,
raw bytes, or parsed data; checksum mismatch; missing or invalid task correlation; run mismatch;
unknown or missing fields; invalid SKU, asset type, title, MIME type, generator, storage URI,
asset checksum, version, claim JSON, or timestamps; invalid, cross-SKU, UNVERIFIED, or malformed
fact references; natural-key conflict; invalid future asset-ID generation; Contract validation
failure; publisher coherence failure; target mismatch; or ambiguous publisher state.

An ordinary `Exception` from an approved bounded dependency may be translated to a fail-closed
result only at that boundary. `BaseException` propagates. Whole-function and row-loop broad catches
that disguise programming or runtime defects as source errors are forbidden.

## 25. Batch atomicity

A partial result may carry candidate information internally, but publisher mutation is zero. Any
rejected or conflicting row makes the batch non-publishable. Existing records, current/latest
state, and timestamps remain unchanged on failed, rejected, partial, or conflicting batches.

## 26. Shared publisher

The future implementation reuses the existing shared Data Hub publisher without redesign. Its
target is `CONTENT_ASSET`, and publication requires all of:

- batch `status == READY`
- `publish_eligible == true`
- a non-empty accepted-record set
- no rejected or conflicting records

Synthetic v1 is immutable: no overwrite, partial update, implicit status transition, or existing-
record mutation is allowed.

## 27. Cross-contract isolation

The shared publisher must support isolated coexistence of:

- `PRODUCT_MASTER`
- `PRODUCT_FACT`
- `AD_DAILY`
- `CHANNEL_DAILY`
- `INVENTORY`
- `CONTENT_ASSET`

Publisher identity remains contract-scoped as `(target_contract, natural_key)`. An asset row cannot
publish a fact, create a fact, or contaminate another SKU or Contract's duplicate/conflict state.
Target mismatch, malformed cross-Contract records, and ambiguous state fail closed rather than
being silently ignored. Existing records are not automatically modified.

## 28. Explicit exclusions

This ADR does not authorize:

- Phase 5 contribution-margin, CTR, CVR, ROAS, inventory, reorder, score, or grade calculations
- `APPROVAL_QUEUE`, approval processing, approval notification, approver population, or status
  transition behavior
- Drive writes, file upload, asset or marketplace publication, asset deletion/replacement, or any
  pricing, inventory, advertising, purchase, or channel write
- `AI_RUN_LOG` writer, audit lifecycle runtime, `human_edit_ratio`, or post-execution audit
- database selection, production persistence, production Data Hub sync, real asset download,
  asset-byte verification, LIVE API calls, credential access, or remote object existence checks
- Development Workflow Automation changes
- external writes of any kind

Phase 4 remains not complete and Phase 5 remains not started.

## 29. Implementation prerequisites

Before implementation, a separate audited Work Order must explicitly authorize its file scope and
tests. That Work Order may include Core `generate_asset_id`, `validate_asset_id`, and
`require_valid_asset_id` APIs. This ADR does not authorize Core changes, package-root export,
source or test changes, dependency changes, or runtime implementation.

The future implementation must use the current Contract/Schema/registry, Core run/task ID
validators, Phase 3 typed result boundary, actual PRODUCT_FACT records, Phase 4 shared result types,
and shared publisher without weakening their fail-closed behavior.

## 30. Future implementation test obligations

A separately authorized implementation must test at least:

- input: valid DRAFT candidate; missing or unknown fields; blank/whitespace fields; invalid version,
  asset checksum, storage URI, title, MIME type, generator, or claim JSON; duplicate Fact IDs
- SKU/references: unknown SKU; missing, malformed, cross-SKU, or UNVERIFIED fact; VERIFIED same-SKU
  fact; empty claims; malformed fact records and referential context
- task/run: exact task preservation; missing, null, blank, or malformed task rejection; run mismatch;
  separate caller task mismatch if that interface exists
- raw boundary: valid exact-byte checksum; mismatch; missing `SensitiveBytes`; invalid raw/parsed
  relationship; separation of source checksum from asset checksum
- storage URI safety: Frozen-valid plus existing-sanitizer-valid acceptance; username and password
  userinfo rejection; exact rejection of `access_token`, `token`, `authorization`, `signature`,
  `secret`, and `refresh_token` query names; percent-decoded and case-insensitive name matching;
  fragment rejection through exact equality; unchanged preservation of accepted values; no unsafe
  original URI in a record, error, log, or persistent provenance; no vendor-specific signed-URL
  guarantee and no new scheme allowlist
- ID: asset format, wrong prefix, invalid ULID, generator ordinary `Exception` and `BaseException`,
  and no unnecessary ID on duplicate or rejected paths
- identity: an exact four-field top-level object containing only `target_contract`, `schema_version`,
  `source_checksum`, and `mapping_fingerprint`; no fifth top-level field; changed `known_skus` or
  approved six-field fact context changes the mapping fingerprint; source-checksum changes alter
  ingestion identity; `run_id`, `task_id`, clock, and random asset ID do not; exact replay;
  within-batch and existing duplicates; same-key/different-hash conflict; random ID unable to bypass
  duplicates
- business hash: exact field set; `generated_by` exactly once; same generator plus same business
  fields is `BUSINESS_DUPLICATE`; changed generator under the same key is conflict; random ID and
  provenance-only changes leave the hash unchanged
- fact fingerprint: exact six fields; deterministic Fact-ID order; empty `[]`; provenance excluded;
  malformed referenced facts fail closed
- provenance: required run/task IDs, `data_as_of` preservation, and one injected clock for a new
  accepted batch
- source replay ordering: direct instrumentation proves asset-ID factory calls equal zero, clock
  calls equal zero, and publisher mutations equal zero; result classification is `SOURCE_DUPLICATE`,
  `publish_eligible == false`, and no new accepted candidate state exists
- publisher: READY atomic publication; no publication for PARTIAL, CONFLICT, or REJECTED; target
  mismatch; real six-Contract coexistence; malformed cross-Contract state; existing-state
  immutability
- boundaries: no Phase 5 calculation, Approval Queue, AI run-log writer, LIVE/API/credential
  access, or external write

## 31. Corrective finding closure

- `CA-A1-F-001`: CLOSED by exact reuse of the current repository URI safety boundary with exact-
  equality enforcement and without broader security claims or a new taxonomy.
- `CA-A1-F-002`: CLOSED by fixing the source-ingestion identity to exactly four top-level fields and
  encapsulating approved SKU and fact context in `mapping_fingerprint`.
- `CA-A1-F-003`: CLOSED by requiring exact source-duplicate detection before both asset-ID factory
  invocation and `clock()` invocation, with direct zero-call and zero-mutation test obligations.

## 32. Non-decisions

The following remain explicitly undecided:

- production storage-scheme allowlist
- production database engine
- production `CONTENT_ASSET` persistence
- production Drive synchronization
- remote asset existence verification
- actual asset-byte verification
- content Approval lifecycle
- Publication lifecycle
- asset replacement or supersession
- broader version-history semantics
- Phase 5 calculations
- `AI_RUN_LOG` implementation
- external marketplace publication

None may be inferred from this ADR. Any such decision requires its own authority and gate.
