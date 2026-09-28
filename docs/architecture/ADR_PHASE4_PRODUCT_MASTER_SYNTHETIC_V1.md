# ADR: PHASE 4 PRODUCT_MASTER synthetic v1

- Status: Accepted for PHASE 4 synthetic/internal architecture-proof scope
- Schema: `topspeed.product_master.synthetic.v1`
- Target: `PRODUCT_MASTER`

## Decision

For this synthetic/internal architecture-proof slice, `PRODUCT_MASTER` is the internal SKU master.
The source SKU is the direct internal SKU; there is no external mapping and no `known_skus`
validation because `PRODUCT_MASTER` defines the master. The natural key is `(sku,)`.

Bootstrap ingestion is immutable:

- Same SKU and the same business state is a duplicate/no-op.
- Same SKU and a different business state is a conflict.
- No update, replacement, supersession, or version history is defined in this slice.

`channel_ids` has the following input semantics:

- Omitted means absent.
- Blank or `None` means null.
- A nonblank value must be JSON object text.
- Duplicate JSON keys are rejected.
- Malformed JSON, non-object JSON, and native mapping inputs are rejected.

The source-owned decimal fields are exactly these six:

- `purchase_cost`
- `sale_price`
- `fee_rate`
- `fulfillment_cost`
- `expected_return_cost`
- `other_variable_cost`

`contribution_margin` and `contribution_margin_rate` are PHASE 5-owned. They are forbidden as
source input and are not generated here.

`mapping_fingerprint` is deterministic from both of the following values:

- `strategy=direct_internal_sku`
- `schema_version=topspeed.product_master.synthetic.v1`

For initial bootstrap only, `created_at == updated_at`; both values come from one injected,
timezone-aware clock.

## Scope and authority boundaries

Successful ingestion does not prove SKU issuance authority and does not imply human approval for
launch or lifecycle decisions. No production update semantics are defined.

This ADR defines no LIVE API behavior, external writes, approval execution, or PHASE 5 calculation
behavior.

This ADR neither modifies nor reinterprets Frozen documents. Frozen documents modified: 0.
