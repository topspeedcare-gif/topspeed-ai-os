# ADR: PHASE 5 internal SKU issuance and PRODUCT_MASTER bootstrap authority v1

- Status: Accepted as a docs-only Architecture authority
- Authority: Human Architecture Owner
- Authority scope: this exact product and SKU only
- Internal SKU: `TS-WAIST-BRACE-L`
- Product: `[5중지지] 탑스피드 허리보호대 L`
- Existing ingestion schema: `topspeed.product_master.synthetic.v1`
- Target Contract: `PRODUCT_MASTER`

## Decision and authority boundary

The Human Architecture Owner authorizes `TS-WAIST-BRACE-L` as the internal SKU for the exact
product `[5중지지] 탑스피드 허리보호대 L` and for no other product, option, or SKU. External
channel identifiers cannot replace this internal SKU.

Existing `generate_sku()`, `validate_sku()`, `require_valid_sku()`, or equivalent format utilities
do not constitute SKU issuance authority. This decision creates no general or reusable SKU issuance
authority. Another product, option, or SKU requires separate Human authority.

Publication of this ADR does not create a `PRODUCT_MASTER` record and does not execute
`PRODUCT_MASTER` registration. This ADR documents Architecture approval only. Any future
registration requires a separate, exact execution authorization.

This ADR does not modify, reinterpret, supersede, or weaken `DATA_CONTRACT_V1`.

## Exact minimal bootstrap source-row input

The seven required fields of the minimal `PRODUCT_MASTER` bootstrap source-row input are exactly:

| Source-row field | Human-authorized value |
| --- | --- |
| `sku` | `TS-WAIST-BRACE-L` |
| `product_name` | `[5중지지] 탑스피드 허리보호대 L` |
| `category` | `건강관리용품` |
| `stage` | `CORE` |
| `status` | `ACTIVE` |
| `currency` | `KRW` |
| `data_as_of` | `2026-10-19T16:18:10+09:00` |

These are the seven required fields of the minimal source-row input. They are not a claim that the
complete final `PRODUCT_MASTER` Contract contains only seven required fields. The existing
ingestion boundary adds the required record and provenance fields described below.

## `data_as_of` authority

`2026-10-19T16:18:10+09:00` is the Human-supplied source-data validity timestamp for this exact
approved source record. The Human source-validity declaration is that the approved
`PRODUCT_MASTER` required source values are actually valid as of that timestamp.

It is not a chat timestamp, Human approval timestamp, ingestion clock, `fetched_at`, `created_at`,
or `updated_at`. The authoritative final-record provenance remains:

```text
data_as_of_origin = source_row:data_as_of
```

## Source row, SourceMetadata, final record, and execution clock

The existing `PRODUCT_MASTER` adapter boundary remains unchanged.

The source row supplies these business and source-validity fields:

- `sku`
- `product_name`
- `category`
- `stage`
- `status`
- `currency`
- `data_as_of`

For the exact future Human-verified registration candidate documented here, the approved source
classification is `manual_verified`. A future separately authorized execution would supply it as
`SourceMetadata.source`; it is not a source-row field.

The existing `SourceMetadata` boundary supplies `source`, `source_uri`, `fetched_at`, and
`checksum_sha256`. Although the existing `SourceMetadata` type also includes a `data_as_of` field,
`SourceMetadata.data_as_of` does not replace, override, synthesize, or become the authoritative
`PRODUCT_MASTER` source-row `data_as_of`. The final Contract record continues to receive
`source = manual_verified` from `SourceMetadata.source` and receives its authoritative
`data_as_of` from the required source-row value.

The `manual_verified` label is limited to this exact documented authority. It is not a new global
source enum, is not a general reusable authority mechanism, and authorizes neither registration nor
external writes.

The existing injected execution clock supplies `created_at` and `updated_at`. For an initial
bootstrap, `created_at == updated_at`. This ADR does not hardcode execution-specific values for
`source_uri`, `fetched_at`, `checksum_sha256`, `created_at`, `updated_at`, `run_id`, `task_id`, or
`request_id`. Those values belong to a later, separately authorized registration execution and its
exact source artifact and execution context.

## Optional source-row fields

The initial source row omits all of the following optional fields:

- `channel_ids`
- `grade`
- `supplier`
- `purchase_cost`
- `sale_price`
- `fee_rate`
- `fulfillment_cost`
- `expected_return_cost`
- `other_variable_cost`

Omission means actual omission, not blank, null, zero, a placeholder, or a synthetic value.
`contribution_margin` and `contribution_margin_rate` remain forbidden source inputs and remain
PHASE 5 calculation-owned under the existing architecture. This docs-only Architecture Slice
introduces no cost or pricing evidence requirement and no cost or pricing verification.

## Coupang identifier boundary

The following known external identifiers remain deferred:

| External identifier | Deferred value |
| --- | --- |
| `coupang_seller_product_id` | `15587136792` |
| `coupang_vendor_item_id` | `92849878174` |
| `coupang_sku_id` | `61654574` |

`channel_ids` is omitted from the exact initial source row. No Coupang identifier is activated or
registered, and no Coupang identifier may replace `TS-WAIST-BRACE-L`. Candidate identifier key
names do not become operational Contract keys through this ADR. No `channel_ids` write or
registration is authorized. This ADR creates and approves no Coupang mapping mechanism.

## Existing immutable ingestion semantics

The existing `PRODUCT_MASTER` ingestion architecture is preserved exactly:

- Schema: `topspeed.product_master.synthetic.v1`
- Natural key: `(sku,)`
- Same SKU plus the same business state: duplicate and idempotent no-op
- Same SKU plus a different business state: conflict
- Update: not defined and not authorized
- Replacement: not defined and not authorized
- Supersession: not defined and not authorized
- Version history: not defined and not authorized

This ADR introduces no new `PRODUCT_MASTER` adapter, `PRODUCT_MASTER` schema, registry, update
mechanism, replacement mechanism, supersession mechanism, or versioning mechanism. It preserves
the existing ingestion and provenance boundary without reinterpretation.

## Explicit non-authorizations

| Capability or state | Authority from this ADR |
| --- | --- |
| `PRODUCT_MASTER` registration | NOT AUTHORIZED |
| `PRODUCT_MASTER` write | NOT AUTHORIZED |
| Runtime mutation | NOT AUTHORIZED |
| Coupang external ID activation | NOT AUTHORIZED |
| `channel_ids` registration | NOT AUTHORIZED |
| Cost or pricing expansion | NOT AUTHORIZED |
| General SKU issuance authority | NOT AUTHORIZED |
| Other SKU issuance | NOT AUTHORIZED |
| Lead-Time Authority Slice resumption | NOT AUTHORIZED BY THIS ADR |
| Reorder Point runtime | NOT AUTHORIZED |
| `DATA_CONTRACT_V1` modification | NOT AUTHORIZED |
| Existing ADR modification | NOT AUTHORIZED |
| PHASE 5 completion | NOT DECLARED |
| PHASE 6 start | NOT AUTHORIZED |

No external write, registration, runtime execution, or publication action is approved by this ADR.

## Phase state

- PHASE 4: COMPLETE
- PHASE 5: NOT COMPLETE
- PHASE 6: NOT STARTED

This ADR does not reinterpret or advance those states.
