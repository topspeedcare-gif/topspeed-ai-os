# ADR: PHASE 5 Coupang L Repeatable Completed 30D Read-Only Authority V1

## Status and approval basis

Docs-only Architecture candidate recorded under the exact Audit2 FINAL APPROVED
Work Order below. This candidate is not effective, published, implementation
authority, or an activated repeat-execution grant. Work Order approval does not
substitute for Audit1 and independent Audit2 artifact approval.

```text
work_item_id = P5-CPAIR-L-REPEATABLE-COMPLETED-30D-V1
approved_work_order_id = A2-P5-CPAIR-L-REPEATABLE-30D-ADR-WO-V1
approved_work_order_sha256 =
089f612a647838d6aabb87a228cb72a7fa109ee8be636d13ae0ea616ef47e785
schema_version = development_workflow_state.v1
baseline_sha = 68712bcb5862015aba3af78091fe2fe5119c84d9
phase = PHASE_5
slice = coupang_l_repeatable_completed_30d_authority
parent_scope_hash = null

Repository = topspeedcare-gif/topspeed-ai-os
Branch = audit/phase4-data-hub-adapter
Required origin/audit = 68712bcb5862015aba3af78091fe2fe5119c84d9
Required origin/main = f51dde902e1d460f9e55ff41841aa80970ea723f

allowed_paths =
[
  docs/architecture/ADR_PHASE5_COUPANG_L_REPEATABLE_COMPLETED_30D_READ_ONLY_AUTHORITY_V1.md
]

allowed_operation_classes =
[
  DOC_WRITE,
  LOCAL_COMMIT,
  READ_ONLY_VALIDATION
]
```

The source artifact is
`FINAL_APPROVED_WORK_ORDER_P5_CPAIR_L_REPEATABLE_30D_ADR_V1.md`
(17,716 bytes, UTF-8 without BOM, LF, final newline present). Its digest is
fixed by external Audit2 approval evidence, not self-embedded in that Work
Order. The approved canonical scope has exactly the V1 nine fields and hash
`f729b8adcc2fbcc3fcbbe2ff68cea796fb4174cbf6a38d43e8cf23cef638a896`.
`parent_scope_hash = null` is separate lineage metadata, not a tenth canonical
scope field. These workflow identifiers do not advance the business Phase.

The only currently usable operations are docs-only candidate writing and
read-only validation. `LOCAL_COMMIT` is unavailable during candidate creation
and artifact audit; its later conditions are stated in section 9.

## 1. Governing published authority

The two governing V1 documents are immutable historical authority:

```text
docs/architecture/ADR_PHASE5_COUPANG_WING_EXPORT_SOURCE_ENVELOPE_AUTHORITY_V1.md
Git blob = 42425dd47f9cfd33f8cf82d288a6bca4c696c75b

docs/architecture/ADR_PHASE5_COUPANG_PERIOD_AGGREGATE_READ_ONLY_INVENTORY_ASSESSMENT_V1.md
Git blob = f5952d3dcb808c4cb65e6f18bc64b52afcbeab6d

Published runtime result SHA =
68712bcb5862015aba3af78091fe2fe5119c84d9
```

The completed one-time Stage B execution establishes evidence for the exact V1
pipeline only. It grants no authority for a different period or repeated use.
This candidate adds no actual workbook rows, workbook bytes, business sample
quantities, private mapping table, or credentials.

## 2. Decision and bounded outcome

The reserved future path accepts explicit sales and inventory files and one
explicit completed 30-day period, and returns one informational L-SKU
assessment without source-code modification or a normal-case per-run audit
relay after the separately approved repeat grant is activated.

This is not unattended automation. A command-line wrapper alone cannot
generalize V1: both the published Source reader and assessment reject periods
outside their fixed V1 selection. Later implementation must follow the
published delta authority, without silently weakening or reinterpreting V1.

Only the fixed-period and one-time-execution limits necessary for this work
item are addressed. The exact supersession map in section 5.2.1 is exhaustive;
silence is not permission. Existing files remain unchanged.

## 3. Preserved identity, boundaries, and behavior

The published Source identities, exact Source URIs, export kinds, worksheets,
required headers and row interpretation remain unchanged. The existing exact
`ToolResult`, `SensitiveBytes`, `SourceMetadata`, private carrier types and
field ordering, frozen/slotted status, calculation hash payloads, exception
contracts, and public exports remain unchanged except for the expressly
superseded temporal values and sales-envelope authority below.

Source-to-carrier producers continue to own raw-byte checksum verification,
exact Source and metadata validation, raw-byte reparsing equivalence, row
selection, quantity validation and carrier construction. The private
carrier-only assessment revalidates carriers, both carrier input hashes,
cross-source coherence, the supplied period's temporal rules, formula/run
identity, calculation and final result coherence. It does not authenticate
raw workbooks it does not possess.

The period aggregate remains separate from `CHANNEL_DAILY` and
`calculate_inventory_demand_velocity`. No artificial daily rows, existing
demand-velocity result, Safety Stock policy result, or `INVENTORY` Contract
record is created. No new calculation hash layer is introduced.

## 4. Authority state of this candidate

Writing this ADR does not change the current runtime, its fixed V1 period,
existing one-time approvals, source files, or active business permissions.
Generalized implementation requires a later exact implementation Work Order
after this ADR is published. Repeated business-data execution additionally
requires the limited Human grant described in section 5.5.

## 5. Completed-period and repeat-execution decision

### 5.1 Exact period input

The future caller explicitly supplies:

```text
period_start: exact built-in str in YYYY-MM-DD form
period_end: exact built-in str in YYYY-MM-DD form
period_timezone: exact built-in str equal to Asia/Seoul
```

All of the following are mandatory:

1. Both date strings parse as real Gregorian calendar dates and serialize back
   to exactly the supplied strings.
2. `period_end - period_start` is exactly `29` calendar days.
3. The inclusive period is exactly `30` completed calendar days.
4. `period_close` is derived as midnight at the start of the calendar day
   immediately after `period_end`, with exact `+09:00` offset.
5. The sales workbook-created/exported instant is at or after that close.
6. The inventory workbook-created/observed instant is at or after the same
   derived close.
7. The injected fetched-at clock remains timezone-aware and does not precede
   its workbook-created instant.
8. Only one aggregate period is accepted per invocation.

The period is a caller assertion bound to the raw sales checksum and envelope.
The XLSX does not cryptographically prove the Coupang export selection.

The period must never be inferred or repaired from filename, filesystem
created/modified time, workbook-created time, download time, current date,
worksheet rows, another report, or chat/operator text not supplied through
the approved invocation boundary. Unknown, missing, or unbound selection
does not become valid through a default or fallback.

### 5.2 Source envelope version and provenance

Generalized sales selection uses exactly:

```text
export_kind = SALES_PERIOD_AGGREGATE
schema_version = topspeed.coupang_wing_export.source_envelope.v2
selection_authority_path =
docs/architecture/ADR_PHASE5_COUPANG_L_REPEATABLE_COMPLETED_30D_READ_ONLY_AUTHORITY_V1.md
selection_authority_reference =
<selection_authority_path>@<that ADR's exact published Git blob>
```

The later runtime Work Order must bind the final reference component to this
delta ADR's exact published Git blob. No alternate document, branch name,
commit name, mutable ref, or unpinned path may replace it. The candidate
Builder does not choose that identity, and this ADR does not self-embed its
own not-yet-created Git blob. `selection_authority_path` identifies the
document used to construct the existing reference field; it adds no envelope
payload or source-specific metadata key.

Source-envelope V2 applies only to `SALES_PERIOD_AGGREGATE`. It must not
silently change the meaning of Source-envelope V1.

`INVENTORY_HEALTH_OBSERVATION` remains on
`topspeed.coupang_wing_export.source_envelope.v1`. Its period arguments remain
`None`; its Source envelope authenticates `observed_at`. The generalized
assessment and carrier validation own the dynamic cross-source requirement
`observed_at >= derived period_close`. There is no hidden inventory-period
input and no new inventory metadata key. Inventory's remaining V1 Source
requirements and selection-authority reference are not superseded.

The established envelope field set is unchanged:

```text
schema_version
source
source_uri
export_kind
worksheet_name
raw_checksum_sha256
workbook_created_at
period_start
period_end
period_timezone
period_close
data_as_of
selection_authority_reference
```

The established source-specific metadata key set is unchanged:

```text
schema_version
export_kind
worksheet_name
workbook_created_at
raw_artifact_checksum_sha256
original_source_uri
period_start
period_end
period_timezone
period_close
selection_authority_reference
envelope_sha256
```

For generalized sales V2, `data_as_of` is the derived `period_close`. For
inventory V1, it remains the exact workbook-created/observed instant; all
period metadata is semantically absent and represented as `None`.

Raw checksums use the exact original bytes and retain the existing lowercase
`sha256:<64 hex>` representation. The raw checksum and source URI agree with
both their typed SourceMetadata fields and preserved metadata counterparts.
`payload_sha256()` and the hash field sets remain unchanged. Acquisition
time and request/task/run IDs do not acquire period authority or enter the
envelope hash.

Same-byte parsing, worksheet/header validation, exact metadata key-set
validation, fresh invocation-owned dictionary construction, consistent
consumer snapshots, independent checksum/envelope-hash recomputation,
raw-byte worksheet reparsing equivalence, and fail-closed behavior remain
mandatory. Matching hashes or class identities alone do not authenticate
production provenance.

### 5.2.1 Exact supersession map

This ADR supersedes only these exact clauses:

1. Source-envelope ADR V1 section 5, only the sales fixed values
   `2026-09-20`, `2026-10-19`, the fixed derived close, and the sales
   `selection_authority_reference`. Inventory's `None` period-argument rule
   remains unchanged.
2. Source-envelope ADR V1 section 7, only the sales fixed-close comparison.
   The inventory Source-envelope V1 observation meaning remains unchanged;
   the assessment applies its dynamic cross-source close comparison.
3. Source-envelope ADR V1 section 9, only for `SALES_PERIOD_AGGREGATE`, the
   schema-version literal and selection-authority-reference value. The exact
   envelope payload field set, metadata key set, checksum rules, hash
   algorithm, and consumer verification remain unchanged.
4. Assessment ADR V1 section 5, only the sentence tying the customer-return
   warning to the literal `2026-09-20` through `2026-10-19`; it instead refers
   to the caller-supplied completed sales period. Customer-return calculation
   semantics remain unchanged.
5. Assessment ADR V1 section 6 in full only as to the four fixed temporal
   values and rejection of every alternate start/end date. Its inclusive
   30-day identity, `Asia/Seoul`, derived close, post-close sales and inventory
   requirements, authoritative timestamp sources, single-period rule, and
   fail-closed behavior remain mandatory for the supplied period.
6. Assessment ADR V1 sections 10, 10.2, 10.4, and 12 only where they
   transitively invoke section 6's fixed date literals. Their Source identity,
   checksum, producer, carrier, validation-order, and exception contracts are
   otherwise unchanged.

No other clause of either governing ADR is superseded. In particular, product
identity, worksheet/header semantics, formula, carrier layout, input hashes,
private visibility, no-write boundaries, and public exports remain unchanged.

### 5.3 L-SKU identity remains fixed

```text
channel = COUPANG
internal_sku = TS-WAIST-BRACE-L
seller_product_id = 15587136792
vendor_item_id = 92849878174
coupang_sku_id = 61654574
sales_mode = 로켓그로스
inventory grade = NEW
```

There is no general mapping authority, mapping file, registry, wildcard,
product-name matching, row-order fallback, or alternate SKU. Required exact
identifiers, one-target-row selection, duplicate/conflict rejection, source
sales mode and inventory grade remain as published. External IDs do not
replace the internal SKU or activate PRODUCT_MASTER channel identifiers.

### 5.4 Calculation contract remains unchanged

```text
period_days = 30
cancelled_units = 0 - signed_cancelled_units
net_sold_units = gross_sold_units - cancelled_units
avg_daily_units = ROUND_HALF_UP(net_sold_units / 30, 4 decimal places)
indicative_safety_stock_days = 7
indicative_safety_stock_qty = CEILING(avg_daily_units * 7)
```

The published sign, gross/net reconciliation, canonical quantity, integer and
fixed-point rules remain unchanged. Binary float is forbidden. The average
retains its canonical nonnegative fixed-point ASCII representation without
exponents or unnecessary fractional trailing zeros.

`inbound_qty` and `customer_return_units` remain separate observations and do
not affect status. Inbound is not added to available quantity. Customer returns
are not deducted a second time and must not be presented as an exact count for
the caller-supplied completed sales period without separate Source authority
proving that equivalence. Their rolling-window meaning remains distinct.

The exact statuses remain:

```text
ABOVE_OR_EQUAL_INDICATIVE_SAFETY_STOCK
BELOW_INDICATIVE_SAFETY_STOCK
```

Available quantity at or above the indicative safety-stock quantity produces
the first status; below produces the second. This is informational only,
not Safety Stock policy-result production, Reorder Point, Recommended Order
Quantity, purchase approval, or order action.

### 5.5 Limited repeat-execution authority design

This ADR reserves, but does not activate, a later Tier-3 limited repeat grant:

1. The exact allowed external input root is
   `C:\TOPSPEED_AI_OS_INPUT\COUPANG`.
2. Both sales and inventory paths are explicitly supplied for every run.
3. No directory scan, glob, newest-file choice, recursive discovery, or
   filename-based report classification is permitted.
4. Both canonical absolute paths must resolve beneath the allowed root.
5. The two inputs must be distinct regular `.xlsx` files and must not resolve
   into `C:\Dev\topspeed-ai-os`.
6. Each file is read exactly once into bytes for its Source invocation.
7. The Source layer recomputes and reports each raw SHA-256 every run.
8. Normal eligible runs do not require advance approval of each new file hash.
9. Any path, type, period, time, Source, schema, identity, quantity, checksum,
   or cross-source mismatch stops the complete run before assessment output.
10. The run is read-only and returns one L-SKU assessment only.

These future external path reads belong to the operator boundary, not a new
filesystem capability in the caller-supplied-byte Source reader. The exact
same loaded bytes bind checksum verification and Source invocation. Actual
XLSX/raw business data must not be copied into any repository location,
including tracked, untracked, ignored, temporary, generated, or LFS paths.

The existing one-time Human approval does not grant repeat authority.
Activation requires a later exact implementation Work Order, Audit1 and
independent Audit2 review of the same result SHA, publication, and
action-specific Human approval for this bounded repeat grant. Neither
candidate creation nor future ADR publication alone activates that grant.

## 6. Required failure boundaries

The future contract fails closed for at least:

- Missing or wrong exact period scalar type.
- Invalid or noncanonical date.
- Period shorter or longer than 30 inclusive days.
- Timezone other than exact `Asia/Seoul`.
- Pre-close sales workbook.
- Pre-close inventory observation.
- Fetched-at earlier than workbook creation.
- Absent, duplicate, or mismatched target row.
- Wrong L-SKU identity, sales mode, or inventory grade.
- Checksum, envelope, worksheet, header, row-shape, formula, or quantity error.
- Path outside the approved root.
- Path inside the repository.
- Automatic file discovery or ambiguous input selection.
- Any attempt to produce a partial or fallback assessment.

No partial carrier or assessment, guessed period, coercion, healthy-zero
fallback, or inferred replacement data is permitted. Failure output must not
expose raw workbook values, secrets, credentials, unapproved identifiers, or
local paths beyond safe approved constants. Existing exception and Source
failure contracts remain unchanged outside the exact supersession map.

## 7. Explicit exclusions

This ADR explicitly excludes:

```text
automatic latest-file discovery
directory scanning or watching
scheduler or background service
network or Coupang API/browser automation
environment or credential access
multi-SKU support
SKU mapping input or registry
product-name matching
database, Google Sheet, AI_RUN_LOG or file output
inventory materialization or write-back
public package export activation
Safety Stock policy-result production
Reorder Point or Recommended Order Quantity
purchase order or external business action
actual business XLSX in Git
runtime implementation under this docs-only Work Order
actual business-data execution under this docs-only Work Order
commit before section-9 prerequisites, push, publication, main modification
or Phase advancement
```

## 8. Candidate acceptance and evidence

Exactly one new path is permitted: this ADR. No tracked file or other
untracked path may change. The candidate must identify both governing V1
blobs, preserve the exact section-5.2.1 supersession map, explicit completed
30-day period authority, exact L identity, unchanged calculation, sales V2
and inventory V1 distinction, and explicit-path/no-discovery repeat boundary.
Architecture eligibility, implementation and Human activation remain separate.

The candidate contains no actual business rows, workbook bytes, credentials,
secrets, private mapping tables, or new product identifiers. Encoding must be
UTF-8 without BOM, LF-only, with a final newline. `git diff --check`,
business-data exclusion and the scoped secret scan must pass.

Builder returns baseline/HEAD/origin refs, exact candidate path and changed
count, candidate SHA-256/Git blob, governing blob matches, encoding and diff
checks, business-data exclusion, secret-scan tool/version/configuration/exit,
working-tree status, staged count, and active Git operation state.

## 9. Conditional local sealing; not currently eligible

During candidate creation and both artifact audits this ADR remains
untracked and unstaged. `LOCAL_COMMIT` becomes usable only after all three
conditions are recorded against the unchanged candidate bytes:

1. Audit1 artifact PASS.
2. Independent Audit2 artifact PASS of the same candidate SHA-256 and Git blob.
3. Human exact-artifact local-sealing approval.

Only then may Codex create exactly one single-parent local commit containing
exactly this approved ADR path and unchanged approved blob. No additional
path or content change is permitted. Push and publication remain unauthorized.

## 10. Audit and workflow

```text
Audit1 draft
-> Audit2 independent Work Order review
-> FINAL approved docs-only Work Order
-> Codex creates exact one-file ADR candidate
-> Audit1 artifact audit
-> Audit2 independent same-artifact audit
-> Human exact-artifact local-sealing decision
-> conditional LOCAL_COMMIT becomes available
-> exactly one single-parent local commit of the unchanged approved blob
-> Audit1 and Audit2 same-result-SHA audits
-> Human publication decision
-> normal non-force push and exact-SHA CI
```

No implementation Work Order is eligible until this ADR is published.

## 11. Current authority state

```text
Docs-only candidate creation = AUTHORIZED UNDER THE FINAL WORK ORDER
Runtime implementation = NOT AUTHORIZED
Repeated actual-XLSX execution = NOT AUTHORIZED
Actual business-data processing = NOT AUTHORIZED
Local commit now = NOT ELIGIBLE; conditional only under section 9
Push / publication = NOT AUTHORIZED
Main modification = NOT AUTHORIZED
Phase advancement = NO
PHASE 4 = COMPLETE
PHASE 5 = NOT COMPLETE
PHASE 6 = NOT STARTED
NEXT OWNER = Audit1
NEXT ACTION = independent artifact audit of this unchanged candidate,
followed by independent Audit2 same-artifact audit before Human sealing.
```
