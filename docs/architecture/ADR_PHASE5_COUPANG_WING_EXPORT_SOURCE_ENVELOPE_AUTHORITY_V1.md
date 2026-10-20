# ADR: PHASE 5 Coupang Wing Export Source Envelope Authority V1

## Status and approval basis

Docs-only architecture candidate transcribed under the exact-hash FINAL APPROVED
CODEX DOCS-ONLY WORK ORDER supplied by Human. The source Work Order retains its
draft-state text unchanged; execution authority is the separate final approval
of those exact Work Order bytes, not its draft self-check.

- Work item: `P5-COUPANG-WING-SOURCE-ENVELOPE-AUTHORITY-V1`.
- Approved Work Order ID: `A2-P5-CWSE-ADR-WO-V1-250fd9d95530922c`.
- Approved Work Order: `WORK_ORDER_PHASE5_COUPANG_WING_EXPORT_SOURCE_ENVELOPE_V1.md`.
- Approved Work Order SHA-256: `250fd9d95530922c5f3e8f35b3e74fe3dc1333e080f2649501e936f813ab3cee`.
- Repository: `topspeedcare-gif/topspeed-ai-os`.
- Branch: `audit/phase4-data-hub-adapter`.
- Baseline: `975f9c66a2ffecee11a289677068a038ada1fce7`.
- Required `origin/main`: `f51dde902e1d460f9e55ff41841aa80970ea723f`.
- Process: `PROCESS_AMENDMENT_V2`, effective `2026-10-20T14:37:50+09:00`.
- Tier: `2`, new Source authority and provenance boundary.
- Authorized change: this new ADR only; no existing file modification.

This candidate requires Audit1 and independent Audit2 artifact audits before any
local sealing decision. Work Order approval does not approve this artifact,
runtime, real-data execution, registration, persistence, external write,
Reorder Point/ROQ behavior, Phase transition, commit, push, or publication.

## 1. Decision and exact scope

This ADR records the missing production Source-envelope Architecture required
by section 10.3 of the published
`ADR_PHASE5_COUPANG_PERIOD_AGGREGATE_READ_ONLY_INVENTORY_ASSESSMENT_V1.md`.
Its scope is limited to:

1. The exact `coupang_wing_export` Source identity.
2. One-call binding of exact original XLSX bytes to parsed worksheet data.
3. Raw-byte checksum and checksum-bound export selection/provenance.
4. The exact `ToolResult` success/failure boundary for a future read-only
   Source-envelope producer.
5. Eligibility for a later, separate runtime Work Order.

Writing this candidate does not itself close the independent Architecture Gate
or establish an implemented production Source-envelope producer.

## 2. Existing contracts remain unchanged

The following contracts are preserved without reinterpretation:

- `SourceMetadata`, `SensitiveBytes`, `ToolResult`, `ToolStatus`,
  `ExecutionMode`, and `ErrorCategory` in
  `src/topspeed_ai_os/tools/result.py`.
- `raw_sha256()` in `src/topspeed_ai_os/tools/checksum.py`.
- Canonical `payload_sha256()` behavior.
- Caller-supplied-byte and pure parsing boundary of `TabularReadTool`.
- API-only authority of `CoupangReadTool` with `source = "coupang"`.
- All package exports and `__all__` values.
- The published period-aggregate assessment ADR, including its exact
  worksheet/header, SKU mapping, time, calculation, and no-write constraints.

Neither `TabularReadTool` nor `CoupangReadTool` may be relabeled as
`coupang_wing_export`. An existing `ToolResult` from either tool may not be
forwarded with rewritten metadata.

## 3. Reserved future module and non-exported producer

The only reserved future implementation path is:

`src/topspeed_ai_os/tools/read/coupang_wing_export.py`

The future module defines a package-non-exported read tool named
`CoupangWingExportReadTool`. Tests may import it from its defining module.
The future foundation implementation must not add it to
`topspeed_ai_os.tools`, `topspeed_ai_os.tools.read`, or any package `__all__`.

Its exact callable contract is:

```python
class CoupangWingExportReadTool(ReadTool):
    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        request_id_factory: Callable[[], str] | None = None,
    ) -> None: ...

    def read(
        self,
        *,
        raw_bytes: bytes,
        export_kind: str,
        period_start: str | None = None,
        period_end: str | None = None,
        period_timezone: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> ToolResult: ...
```

The caller cannot supply `source`, `source_uri`, `worksheet_name`,
`data_as_of`, raw checksum, workbook-created time, period close, or envelope
hash. The tool derives them under this contract.

`clock` is mandatory. Omission, explicit `None`, or a non-callable value raises
`TypeError` during construction before `ReadTool` initialization. The future
implementation must not permit the base class's `clock=None` wall-clock
fallback. Existing `ReadTool` and existing readers remain unchanged.

This is a pure caller-supplied-byte read boundary. It performs no filesystem,
network, environment, credential, clock fallback, persistence, registry, cache,
or external write action. Its execution mode is exactly `ExecutionMode.MOCK`,
matching the existing meaning for caller-supplied raw bytes; this does not
claim the bytes are synthetic. Actual-source authority comes from the exact
Source identity, raw checksum, workbook metadata, Human-approved selection,
and envelope hash.

## 4. Exact export kinds and derived constants

Only these two exact built-in-string `export_kind` values are allowed:

| `export_kind` | Derived `source_uri` | Derived worksheet | Derived operation |
| --- | --- | --- | --- |
| `SALES_PERIOD_AGGREGATE` | `coupang-wing://seller-insights/vendor-item-metrics` | `vendor item metrics` | `coupang_wing_export.read_sales_period_aggregate` |
| `INVENTORY_HEALTH_OBSERVATION` | `coupang-wing://inventory-health/sku-info` | `Excel Data` | `coupang_wing_export.read_inventory_health_observation` |

For both kinds:

- `tool_name = "coupang_wing_export_read"`.
- `source = "coupang_wing_export"`.
- Content type is
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- `http_status = None`, `modified_time = None`, and `attempt_count = 1`.
- SUCCESS has `error = None`; FAILED has no source metadata, raw result,
  or parsed result.
- `PARTIAL` is not permitted.

Before a valid exact `export_kind` is established, any FAILED result uses the
safe constant operation `coupang_wing_export.read_invalid_request`. It never
derives an operation from, or echoes, invalid caller input. After a valid
kind is established, later failures use that kind's derived operation above.

## 5. Human-approved export-selection authority

For `SALES_PERIOD_AGGREGATE`, the only V1 selection is:

- `period_start = "2026-09-20"`.
- `period_end = "2026-10-19"`.
- `period_timezone = "Asia/Seoul"`.
- Inclusive completed-day count is exactly `30`.
- Derived close is `2026-10-20T00:00:00+09:00`.

These are Human-approved Source-selection values. They are not inferred from
the XLSX, filename, chat timestamp, filesystem timestamps, download clock, or
workbook rows. The inspected Coupang workbook contains no embedded
period-selection metadata; any other selection is outside V1 and fails closed.

The exact selection authority reference is:

`docs/architecture/ADR_PHASE5_COUPANG_PERIOD_AGGREGATE_READ_ONLY_INVENTORY_ASSESSMENT_V1.md@f5952d3dcb808c4cb65e6f18bc64b52afcbeab6d`

The caller's exact approved export-request assertion is the trust boundary
for the period fields. Binding that assertion and the raw checksum in one
hash detects later disagreement; it does not cryptographically prove that
Coupang generated the workbook using that selection.

For `INVENTORY_HEALTH_OBSERVATION`, all three period arguments must be `None`.
Supplying period arguments for inventory or omitting/changing them for sales
is malformed input.

## 6. Raw-byte, workbook-time, and parsed-data binding

One `read()` invocation must use the same exact `raw_bytes` object value to:

1. Compute `raw_sha256(raw_bytes)`.
2. Open the XLSX ZIP package.
3. Read `docProps/core.xml`.
4. Extract exactly one `dcterms:created` W3CDTF value.
5. Parse the exact derived worksheet.
6. Build `SensitiveBytes(raw_bytes)` and `TabularData` for the final SUCCESS
   `ToolResult`.

Externally supplied parsed rows, externally supplied workbook timestamps, or
a checksum over re-serialized cells are forbidden. The producer must not
accept a second byte payload for metadata or parsing. No workbook content
may be mutated or normalized before the raw checksum is computed.

The workbook-created value must be timezone-aware ISO-8601 with whole-second
precision and a `Z` or `±HH:MM` offset. Naive values, missing/multiple created
nodes, fractional seconds, and second- or fractional-second timezone offsets
fail closed. The instant is normalized to the canonical `Asia/Seoul` fixed
offset representation `YYYY-MM-DDTHH:MM:SS+09:00` for metadata and hashing.

The injected tool clock supplies `fetched_at` exactly once. It must be
timezone-aware and must not precede workbook creation. It does not supply or
replace `data_as_of`, the selection period, period close, or observation time.

## 7. Exact temporal authority

For sales:

- Workbook-created instant must be at or after the exact period close.
- `SourceMetadata.data_as_of` equals the derived period-close instant.
- Workbook-created instant is the export instant, not the sales validity
  instant.

For inventory:

- Workbook-created instant is `observed_at`.
- `SourceMetadata.data_as_of` equals that exact instant.
- Workbook-created/observed instant must be at or after the same exact
  period close `2026-10-20T00:00:00+09:00` before this narrowly scoped tool
  may return SUCCESS.
- Period fields and period close are absent semantically and represented
  as `None` in the envelope hash payload.

No wall-clock fallback is permitted. A missing, malformed, naive, or
pre-close required source time prevents SUCCESS.

## 8. Source worksheet and schema validation

Before SUCCESS, the producer must validate the source-specific worksheet
against the published assessment ADR.

Sales:

- Worksheet: `vendor item metrics`.
- Header row: `1`; data begins at row `2`.
- Exact required headers: `등록상품ID`, `옵션 ID`, `판매방식`, `총 판매수`,
  `총 취소된 상품수`, `판매량`.

Inventory:

- Worksheet: `Excel Data`.
- Header row: `1`.
- Row `2` is the known explanatory subheader and is not data.
- Data begins at row `3`.
- Exact required headers: `등록상품 ID`, `옵션 ID`, `SKU ID`, `상품등급`,
  `판매가능재고 (실시간 기준)`, `입고예정재고(실시간 기준)`,
  `고객반품 지난 30일(전일자 기준)`.

Required headers must each occur exactly once. Missing/duplicate required
headers, missing sheet, formula cells in any required header or consumed
data cell, malformed row widths, or an empty data body fail closed.
Additional non-required columns may be preserved but cannot become authority
for this V1 assessment.

## 9. Exact checksum and envelope hash

`SourceMetadata.checksum_sha256` must equal `raw_sha256(raw_bytes)` in the
existing lowercase `sha256:<64 hex>` format.

The exact envelope hash is `payload_sha256()` over this mapping and no
other fields:

```text
schema_version = topspeed.coupang_wing_export.source_envelope.v1
source = coupang_wing_export
source_uri = <derived exact URI>
export_kind = <exact export kind>
worksheet_name = <derived exact worksheet>
raw_checksum_sha256 = <raw checksum>
workbook_created_at = <canonical +09:00 string>
period_start = <exact sales date or null>
period_end = <exact sales date or null>
period_timezone = <Asia/Seoul or null>
period_close = <canonical sales close or null>
data_as_of = <canonical SourceMetadata data_as_of string>
selection_authority_reference = <exact published ADR path@blob reference>
```

`SourceMetadata.source_specific_metadata` must contain exactly these keys:

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

The authoritative raw checksum and source URI each enter the envelope-hash
payload once under `raw_checksum_sha256` and `source_uri`. The published
assessment ADR also requires their preservation inside source-specific
metadata. Thus `raw_artifact_checksum_sha256` must exactly equal
`SourceMetadata.checksum_sha256`, and `original_source_uri` must exactly
equal `SourceMetadata.source_uri`; disagreement fails closed. `data_as_of`
remains in its typed field and participates in the envelope hash.
`fetched_at`, request/task/run IDs, and parsed rows do not enter that hash.

This source-envelope integrity digest is separate from the published policy,
demand-side, and final Safety Stock calculation hashes. It does not create
a fourth calculation hash or change any published calculation carrier or
payload.

### Mutable metadata and consumer verification

The future producer must construct a fresh invocation-owned plain dictionary
containing only the exact scalar keys above and retain no mutable reference
used to build it. The existing `SourceMetadata` contract is shallowly frozen
and its dictionary is mutable; neither object/class identity nor the stored
`envelope_sha256` is self-authenticating or deeply immutable.

Before consuming a SUCCESS result, a future source-to-carrier producer must
take one consistent snapshot and independently, from `raw_result.reveal()`
and typed metadata:

1. Recompute the raw checksum and require equality with both checksum
   locations.
2. Require the exact source, URI, data-as-of, export kind, worksheet,
   authority reference, and exact metadata key set; reject absent, extra,
   altered, or conflicting authority fields.
3. Re-extract and normalize workbook creation time from the same raw bytes.
4. Rebuild the exact envelope payload and require its hash to equal the
   stored envelope hash.
5. Reparse the exact approved worksheet from those raw bytes and require
   exact `TabularData` type, headers, sheet name, rows, formula handling,
   and structural equality with `parsed_result`.
6. Perform all carrier construction and assessment consumption only from
   that validated snapshot.

This verification introduces no registry, token, mutable cache, persistence,
or new authority. Its runtime implementation requires a separate Work Order.

## 10. ToolResult success boundary

A SUCCESS result must contain:

- Exact `tool_name`, operation, `ExecutionMode.MOCK`, and
  `ToolStatus.SUCCESS`.
- Invocation-owned request ID and unchanged optional task/run IDs.
- The exact `SourceMetadata` defined above.
- `SensitiveBytes` revealing byte-for-byte equal original input.
- Exact `TabularData` parsed from those same bytes and exact derived
  worksheet.
- Warnings only for non-authoritative informational conditions; formulas
  are failures, not warnings.

The implementation may refactor or reuse a pure XLSX parsing helper, but may
not forward or relabel an existing `TabularReadTool`/`CoupangReadTool`
`ToolResult`. Any refactor must preserve all existing public behavior and
requires explicit paths in the later runtime Work Order.

## 11. Fail-closed and exception boundary

All authority-bearing checks must precede SUCCESS. No private call order is
prescribed beyond these safety dependencies: raw checksum precedes content
normalization; workbook metadata and parsed data come from the same bytes;
selection/time/schema validation all complete before envelope hash and
SUCCESS construction.

| Failure | Required result |
| --- | --- |
| Invalid exact input type/value or invalid export-kind/period combination | FAILED / `MALFORMED_INPUT` |
| Empty/malformed XLSX, malformed ZIP/XML, missing/multiple/invalid created time, pre-close sales export, pre-close inventory observation, required formula cell | FAILED / `MALFORMED_SOURCE` |
| Exact derived worksheet absent | FAILED / `SOURCE_NOT_FOUND` |
| Required header missing/duplicated, row shape changed, or source layout incompatible | FAILED / `SOURCE_SCHEMA_CHANGED` |
| Unsupported content/format | FAILED / `UNSUPPORTED_FORMAT` |

Existing task/run ID validation and injected clock/request-ID infrastructure
exceptions preserve their existing unchanged behavior. Unexpected internal
exceptions must not expose raw content, identifiers beyond approved
constants, secrets, local paths, workbook author names, or payload values.
They map to redacted FAILED / `UNKNOWN` unless an existing infrastructure
exception is contractually required to propagate.

No FAILED result may contain `SourceMetadata`, `raw_result`, or
`parsed_result`. No assessment or downstream carrier may be constructed
from a FAILED/PARTIAL Source result.

## 12. Evidence-only current files and future eligibility

The currently inspected files were created on `2026-10-19`, before the sales
period closed, and remain evidence-only. Their known checksums may be cited
as inspection evidence but must not be hardcoded as future runtime allowlist
values and do not become eligible production inputs. No actual artifact was
processed to write this ADR.

A later production runtime Work Order remains blocked until this ADR is
published and a post-close sales export plus contemporaneous inventory
export satisfy this Source-envelope contract. That future Work Order must
separately authorize exact code/test paths and actual local input handling.

## 13. Security and forbidden capabilities

Actual XLSX/CSV/TSV/XLS/Parquet/JSONL files, raw payloads, and non-public
mapping tables remain outside the Git repository. Actual row values must
not appear in source, tests, logs, ADR examples, Git history, or error
messages. Public tests must use synthetic fixtures only.

This ADR grants no authority for:

- Actual file reading from a filesystem path.
- Network access or Coupang API/browser automation.
- Environment or credential access.
- Registration, persistence, cache, registry, or mutable state.
- Public export activation.
- Existing Contract/Schema modification.
- Inventory materialization or write-back.
- Reorder Point, ROQ, ordering, approval, or external execution.
- Actual business-data processing.
- Commit, push, publication, main modification, or Phase advancement.

## Artifact review and state lock

This file records future Source-envelope contracts only. It creates no
runtime module, test, reader, parsed business-data result, carrier,
assessment, or active production integration. Existing code, tests,
contracts, package exports, and the published assessment ADR are unchanged.

Artifact approval, local sealing, publication, and production runtime
eligibility remain distinct gates; none is granted by candidate creation.

Runtime = NOT AUTHORIZED.
Actual business-data processing = NOT AUTHORIZED.
Commit / push / publication = NOT AUTHORIZED.
PHASE 4 = COMPLETE. PHASE 5 = NOT COMPLETE. PHASE 6 = NOT STARTED.

NEXT OWNER = Audit1.
NEXT ACTION = independent docs-only ADR implementation audit, followed by
independent Audit2 audit of the unchanged candidate before local sealing.
