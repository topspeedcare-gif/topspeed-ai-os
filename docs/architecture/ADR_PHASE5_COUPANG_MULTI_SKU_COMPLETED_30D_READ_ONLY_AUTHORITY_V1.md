# ADR: PHASE 5 Coupang Multi-SKU Completed 30D Read-Only Authority V1

## 1. Status, approval basis, and deterministic scope

Status: docs-only Architecture candidate; not yet artifact-audited, sealed,
published, or implementation authority. Approval of the Work Order authorizes
this candidate only, not SKU issuance, mapping approval, or business execution.

```text
schema_version = development_workflow_state.v1
work_item_id = P5-CPAIR-MULTI-SKU-READ-ONLY-AUTHORITY-V1
approved_work_order_id = A2-P5-CPAIR-MULTI-SKU-READ-ONLY-AUTHORITY-WO-V1
approved_work_order_sha256 =
67d12864bc72602083de6928bcb3714afe7ea6f688ead2cac49eb44416e27bfc
baseline_sha = 9cea4595a834b17ac1bfd904c83d8b997c317956
phase = PHASE_5
slice = coupang_multi_sku_completed_30d_authority
parent_scope_hash = null

Repository = C:\Dev\topspeed-ai-os
Repository identity = topspeedcare-gif/topspeed-ai-os
Branch = audit/phase4-data-hub-adapter
Required origin/audit = 9cea4595a834b17ac1bfd904c83d8b997c317956
Required origin/main = f51dde902e1d460f9e55ff41841aa80970ea723f

allowed_paths =
[
  docs/architecture/ADR_PHASE5_COUPANG_MULTI_SKU_COMPLETED_30D_READ_ONLY_AUTHORITY_V1.md
]

allowed_operation_classes =
[
  DOC_WRITE,
  LOCAL_COMMIT,
  READ_ONLY_VALIDATION
]
```

Authority artifact:
`FINAL_APPROVED_WORK_ORDER_P5_CPAIR_MULTI_SKU_READ_ONLY_AUTHORITY_V1.md`,
14,652 bytes, 440 lines, UTF-8 without BOM, LF, final newline present.
The exact Work Order digest is fixed by external Audit2 approval evidence.
The canonical nine-field V1 scope hash is
`98cf58ef1b9e81e9f95b71f1264d4c18d4967135ee43fb6bb755cf377c07dd16`.
`parent_scope_hash = null` is separate lineage metadata. These workflow
identifiers do not advance the business Phase.

Maximum changed path count is one. No existing tracked file may be modified.
Only candidate writing and read-only validation are currently usable.
`LOCAL_COMMIT` remains unavailable until the conditions in section 13 hold.

## 2. Preserved baseline authority

Preserve the published completed-30D Source and calculation behavior and the
existing single-L runner, `tools/run_coupang_l_repeatable_completed_30d.py`.
The existing repeatable-period authority remains:

```text
docs/architecture/ADR_PHASE5_COUPANG_L_REPEATABLE_COMPLETED_30D_READ_ONLY_AUTHORITY_V1.md
Published Git blob = b02fb74a766f4f85e7c7d878a3a5faa4a16bc7ba
Published runtime SHA = 9cea4595a834b17ac1bfd904c83d8b997c317956
```

This ADR adds only approved external SKU-mapping authority and atomic multi-SKU
read-only assessment authority. Any existing contract not expressly changed by
this ADR remains unchanged. Candidate creation changes neither existing code
nor the active L-only execution permission.

## 3. Bounded architecture decision

The future invocation is:

```text
explicit sales XLSX
+ explicit inventory XLSX
+ explicit completed 30-day period
+ explicit approved SKU mapping JSON
+ Human-approved exact mapping SHA-256
-> one atomic multi-SKU read-only assessment
```

Initial target labels are:

```text
TS-WAIST-BRACE-M
TS-WAIST-BRACE-L
TS-WAIST-BRACE-XL
TS-WAIST-BRACE-XXL
```

Actual Coupang identifiers for M/XL/XXL must not appear in this ADR, source,
tests, or examples. They remain in the separately Human-approved mapping
artifact outside the repository.

## 4. Internal-SKU issuance is separate from mapping approval

Mapping approval does not issue, create, reserve, infer, rename, or activate an
internal SKU. Every `internal_sku` in an approved mapping must already have
separate exact Human internal-SKU issuance authority. Mapping only connects an
already-issued internal SKU to approved Coupang identifiers.

```text
TS-WAIST-BRACE-L = ISSUED under existing authority
TS-WAIST-BRACE-M = TARGET LABEL ONLY / NOT ISSUED BY THIS WORK ORDER
TS-WAIST-BRACE-XL = TARGET LABEL ONLY / NOT ISSUED BY THIS WORK ORDER
TS-WAIST-BRACE-XXL = TARGET LABEL ONLY / NOT ISSUED BY THIS WORK ORDER
```

The first four-SKU mapping is ineligible until M/XL/XXL each have separate
exact Human issuance authority, every mapping `internal_sku` exactly matches
that authority, and the Human separately approves the exact mapping bytes and
raw SHA-256.

Already-issued SKU plus schema-compatible mapping update does not require a
code or ADR amendment, but always requires exact mapping-artifact Human
approval. An unissued SKU cannot be activated by mapping and requires separate
Human issuance authority first. This ADR issues no SKU.

## 5. Mapping V1 exact contract

### 5.1 Encoding, types, keys, and lexical rules

The mapping artifact is UTF-8 without BOM JSON. SHA-256 is computed over the
original raw bytes before normalization or reserialization.

Top-level runtime type: `type(mapping) is dict`.
The exact top-level key set is:

```text
schema_version
mapping_set_id
mapping_revision
channel
product_family
entries
```

| Field | Exact type and value |
| --- | --- |
| `schema_version` | exact built-in `str`, `topspeed.coupang.sku_mapping.v1` |
| `mapping_set_id` | exact built-in `str`, `topspeed.waist_brace.coupang` |
| `mapping_revision` | exact built-in `str` matching `^[1-9][0-9]*$` |
| `channel` | exact built-in `str`, `COUPANG` |
| `product_family` | exact built-in `str`, `TS-WAIST-BRACE` |
| `entries` | non-empty exact built-in `list` |

`mapping_revision` forbids zero, signs, fractions, exponents, whitespace,
and leading zero.

Every entry has runtime type `type(entry) is dict` and this exact key set:

```text
internal_sku
seller_product_id
vendor_item_id
coupang_sku_id
```

All four entry values are exact built-in `str`. `seller_product_id`,
`vendor_item_id`, and `coupang_sku_id` each match `^[1-9][0-9]*$`.
`internal_sku` is byte-for-byte identical to separately issued Human authority.

Reject JSON null, boolean, or number in scalar positions; scalar coercion;
bool-as-int acceptance; Python subclass-equivalent values; unknown or missing
keys; and duplicate JSON object keys at any nesting level.

Reject duplicate `internal_sku`, duplicate `(seller_product_id, vendor_item_id)`,
duplicate `coupang_sku_id`, missing/additional/conflicting mapping identity,
product-name/row-order/substring/option-name inference, and L fallback.

The first eligible waist-brace mapping contains exactly four entries for the
separately issued M/L/XL/XXL internal SKUs.

### 5.2 Approval checksum

```text
approved_mapping_sha256: exact built-in str
exact form: ^sha256:[0-9a-f]{64}$

approved_mapping_sha256
== raw_sha256(mapping_original_bytes)
== mapping_checksum_sha256
```

All three checksum values use the canonical prefixed SHA-256 representation.
No uppercase repair, prefix repair, bare hex, normalization, or reserialized
hash is permitted. Mapping approval binds the original raw artifact bytes.

### 5.3 External mapping input boundary

```text
Allowed root = C:\TOPSPEED_AI_OS_INPUT\COUPANG
File type = .json
Selection = explicit absolute path only
Read count = exactly once
```

No discovery, scanning, globbing, watching, recursive search, latest/newest
selection, filename identity, repository-contained mapping path, or path
outside the approved root is permitted. No actual mapping JSON or private
mapping values may be added anywhere inside the repository.

## 6. Existing Source and calculation contracts remain unchanged

Reuse without semantic change:

- `CoupangWingExportReadTool`.
- Sales Source-envelope V2.
- Inventory Source-envelope V1.
- Explicit completed 30-day validation and `Asia/Seoul`.
- Dynamic post-close validation.
- Raw XLSX checksum and envelope verification.
- Cancellation reconciliation.
- `ROUND_HALF_UP(net_sold_units / 30, 4)`.
- `CEILING(avg_daily_units * 7)`.
- Inbound and customer-return non-interference.
- Existing no-write boundary.

Sales and inventory XLSX are each read exactly once. Source validation and
worksheet parsing are reused; mapping controls only target identity selection.
No synthetic daily rows or reinterpretation of the completed-30D Source is
introduced. No Safety Stock policy-result, Reorder Point, or ROQ is produced.

## 7. Exact row linking and atomicity

Sales matching requires all three:

```text
등록상품ID == seller_product_id
옵션 ID == vendor_item_id
판매방식 == 로켓그로스
```

Inventory matching requires all four:

```text
등록상품 ID == seller_product_id
옵션 ID == vendor_item_id
SKU ID == coupang_sku_id
상품등급 == NEW
```

Each approved internal SKU must have exactly one matching sales row and
exactly one matching inventory row.

Fail the whole invocation for missing or duplicate target rows, cross-source
or mapping identity mismatch, borrowing another SKU quantity, replacing
missing quantity with zero, partial-SKU success, row-order join, or
product-name join. No partial assessment is authorized.

## 8. Exact SUCCESS output contract

```text
schema_version = topspeed.coupang.multi_sku_completed_30d_assessment.v1
exit code = 0
stdout = exactly one UTF-8 JSON line plus one newline
stderr = empty
```

The SUCCESS top-level exact key set is:

```text
schema_version
status
run_id
channel
period_start
period_end
period_timezone
period_days
mapping_set_id
mapping_revision
mapping_checksum_sha256
sales_source_checksum
inventory_source_checksum
sales_workbook_created_at
inventory_observed_at
results
```

| Field | Type and value |
| --- | --- |
| `schema_version` | exact schema literal `str` stated above |
| `status` | exact `str`, `SUCCESS` |
| `run_id` | `str` under the existing canonical run-ID contract |
| `channel` | exact `str`, `COUPANG` |
| `period_start`, `period_end` | canonical `YYYY-MM-DD` `str` |
| `period_timezone` | exact `str`, `Asia/Seoul` |
| `period_days` | exact `int`, `30`; bool forbidden |
| `mapping_set_id` | exact `str`, `topspeed.waist_brace.coupang` |
| `mapping_revision` | Mapping V1 revision `str` |
| `mapping_checksum_sha256` | canonical prefixed SHA-256 `str` |
| `sales_source_checksum` | canonical prefixed SHA-256 `str` |
| `inventory_source_checksum` | canonical prefixed SHA-256 `str` |
| `sales_workbook_created_at` | canonical whole-second `+09:00` `str` |
| `inventory_observed_at` | canonical whole-second `+09:00` `str` |
| `results` | non-empty exact built-in `list` |

No JSON null is allowed in SUCCESS. `results` length equals the approved
mapping entry count and is sorted ascending by `internal_sku`.

Each result is an exact built-in `dict` with this exact key set:

```text
internal_sku
net_sold_units
avg_daily_units
indicative_safety_stock_days
indicative_safety_stock_qty
available_qty
inbound_qty
customer_return_units
assessment_status
aggregate_input_hash
inventory_input_hash
assessment_input_hash
```

| Result field | Type and value |
| --- | --- |
| `internal_sku` | `str` |
| `net_sold_units` | `int`; bool forbidden |
| `avg_daily_units` | `str` under the existing canonical fixed-point contract |
| `indicative_safety_stock_days` | exact `int`, `7`; bool forbidden |
| `indicative_safety_stock_qty` | `int`; bool forbidden |
| `available_qty` | `int`; bool forbidden |
| `inbound_qty` | `int`; bool forbidden |
| `customer_return_units` | `int`; bool forbidden |
| `assessment_status` | existing two-value `str` enum |
| `aggregate_input_hash` | canonical prefixed SHA-256 `str` |
| `inventory_input_hash` | canonical prefixed SHA-256 `str` |
| `assessment_input_hash` | canonical prefixed SHA-256 `str` |

The existing assessment status values remain:

```text
ABOVE_OR_EQUAL_INDICATIVE_SAFETY_STOCK
BELOW_INDICATIVE_SAFETY_STOCK
```

SUCCESS must not expose Coupang external IDs, local absolute paths, raw rows,
raw mapping content, credentials, or unapproved identifiers.

## 9. Exact FAILED output contract

```text
exit code = 1
stdout = empty
stderr = exactly one UTF-8 JSON line plus one newline
```

The FAILED exact key set is:

```text
schema_version
status
error_code
internal_sku
```

`schema_version` is the exact output schema `str` from section 8.
`status` is exact `str` `FAILED`. `error_code` is an exact built-in `str`
from this closed enum:

```text
INVALID_INVOCATION
INPUT_BOUNDARY_INVALID
PERIOD_INVALID
MAPPING_SCHEMA_INVALID
MAPPING_CHECKSUM_MISMATCH
MAPPING_ENTRY_DUPLICATE
SOURCE_VALIDATION_FAILED
SALES_ROW_MISSING
SALES_ROW_DUPLICATE
INVENTORY_ROW_MISSING
INVENTORY_ROW_DUPLICATE
CROSS_SOURCE_IDENTITY_MISMATCH
ASSESSMENT_VALIDATION_FAILED
INTERNAL_FAILURE
```

`internal_sku` is an exact built-in `str` only when one already validated
mapping entry unambiguously owns the error; otherwise it is JSON null.

FAILED forbids results, partial result, quantity or checksum output,
additional keys, traceback, raw exception, local path, raw row, and external
IDs. Any single-SKU failure prevents SUCCESS and terminates the full
invocation under this FAILED contract.

## 10. Existing L compatibility

The current L-only runner and its normal input, failure, redaction, completed
period, Source, formula, and hash behavior must remain valid.

A later runtime Work Order may authorize common internal refactoring only
while preserving those behaviors. This docs-only Work Order authorizes no
runtime code. The multi-SKU output contract is not a replacement for the
existing L-only runner's output contract.

## 11. Explicit exclusions

Not authorized:

```text
internal-SKU issuance
actual mapping approval
actual mapping values in Git
actual XLSX/business rows in Git
automatic discovery/latest selection/directory scan/watch
scheduler/background service
Coupang API/browser/network
environment/credential access
database/Google Sheet/AI_RUN_LOG write
inventory materialization
automatic mapping approval
product-name matching
partial per-SKU success
multi-channel support
public package export activation
Safety Stock policy-result production
Reorder Point
Recommended Order Quantity
purchase/order action
runtime implementation under this Work Order
actual business-data execution
main modification
Phase advancement
push/publication
```

## 12. Candidate acceptance and evidence

The candidate passes only if all these conditions hold:

1. Exactly one new authorized ADR exists; no other path changes.
2. Existing completed-30D Source/calculation architecture is preserved.
3. Internal-SKU issuance and mapping approval are separated as in section 4.
4. Mapping V1 exact types, keys, duplicate-key rejection, and raw checksum
   are fixed.
5. Only already-issued internal SKUs can become active mappings.
6. Exact row matching and atomic all-or-nothing behavior are defined.
7. Exact SUCCESS/FAILED transport, key sets, types, and enum are defined.
8. Existing single-L behavior remains protected.
9. All exclusions in section 11 are present.
10. No actual external IDs for M/XL/XXL, mapping JSON, workbook bytes,
    business rows, credentials, secrets, or private mapping table appear.
11. UTF-8 without BOM, LF, final newline, `git diff --check`, business-data
    exclusion, and secret scan pass.
12. The candidate remains untracked and unstaged through both artifact audits.

Builder returns baseline/HEAD/origin refs; exact candidate path and changed
count; Work Order and canonical scope integrity; candidate SHA-256 and raw
Git blob; encoding, whitespace, diff, business-data and scoped secret-scan
evidence; and final working-tree, staged, and active-operation state.
This is Builder evidence, not an Audit1 or Audit2 artifact verdict.

## 13. Conditional local sealing and workflow

During candidate creation and artifact audits, `LOCAL_COMMIT` is unavailable.
It becomes usable only after:

1. Audit1 exact-candidate PASS.
2. Audit2 independent same-artifact PASS on the same SHA-256/blob.
3. Human exact-artifact local-sealing approval.

Then Codex may create exactly one single-parent local commit containing only
the unchanged approved ADR blob. Push/publication remain unauthorized.

```text
Audit1 draft
-> Audit2 FINAL Work Order
-> Codex one-file ADR candidate
-> Audit1 exact-candidate audit
-> Audit2 same-artifact audit
-> Human exact-artifact sealing
-> one local single-parent commit
-> Audit1 exact-result-SHA audit
-> Audit2 same-result-SHA audit
-> Human publication approval
-> Publication Executor exact-range gate
-> normal non-force audit-branch push once
-> remote exact-SHA/blob verification
-> exact-SHA CI/publication closure
-> separate runtime implementation Work Order
-> runtime publication
-> separate Human exact mapping-artifact approval
-> bounded actual multi-SKU execution
```

No runtime implementation Work Order is eligible until this ADR is published.
The first mapping also remains subject to the separate issuance prerequisites
in section 4; mapping approval and runtime publication do not issue SKUs.

## 14. Current authority state and routing

```text
Docs-only ADR candidate creation = AUTHORIZED
Runtime implementation = NOT AUTHORIZED
Internal-SKU issuance = NOT AUTHORIZED
Mapping approval = NOT GRANTED
Actual mapping/XLSX execution = NOT AUTHORIZED
Local commit now = NOT ELIGIBLE
Push/publication = NOT AUTHORIZED
Main modification = NOT AUTHORIZED
Phase advancement = NO
PHASE 5 = NOT COMPLETE

NEXT OWNER = Audit1
ROLE = exact-candidate artifact auditor
NEXT ACTION = audit this unchanged candidate and its exact SHA-256/Git blob;
route to independent Audit2 same-artifact audit only after Audit1 PASS.
```
