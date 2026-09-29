# ADR: PHASE 4 INVENTORY synthetic v1

- Status: Accepted for PHASE 4 synthetic/internal architecture-proof scope
- Schema: `topspeed.inventory.synthetic.v1`
- Target: `INVENTORY`

## Decision

This slice converts a verified PHASE 3 tabular result into raw `INVENTORY` snapshots. It is an
internal Architecture proof only; it does not define a production Coupang inventory schema,
production update semantics, or a persistence engine.

The required source fields are exactly:

- `snapshot_at`
- `external_product_id`
- `location`
- `on_hand_qty`
- `available_qty`
- `reserved_qty`
- `inbound_qty`
- `data_as_of`

There are no optional source fields. Source-provided `sku`, `run_id`, `source`, and `created_at`
are forbidden. The following calculation or deferred fields are also forbidden:

- `avg_daily_units`
- `stock_days`
- `lead_time_days`
- `safety_stock_qty`
- `reorder_point_qty`
- `recommended_order_qty`

`external_product_id` is resolved through the existing normalized `MappingEntry` flow using
`SourceMetadata.source`, identifier type `external_product_id`, and the source value. Mapping
normalization, the mapping fingerprint, and SKU resolution reuse the existing PHASE 4 helpers.
The mapped SKU must exist in caller-supplied `known_skus`.

The synthetic-v1 natural key is:

`(snapshot_at, sku, location)`

This is limited to this Architecture-proof schema and is not a production-wide natural-key claim.
The business hash contains exactly:

- `snapshot_at`
- `sku`
- `location`
- `on_hand_qty`
- `available_qty`
- `reserved_qty`
- `inbound_qty`

It excludes `run_id`, `source`, `data_as_of`, `created_at`, and all provenance metadata. Therefore,
the same key and raw quantities with changed provenance only is a business duplicate, not a
conflict.

The adapter recalculates the raw SHA-256 checksum from `SensitiveBytes`. Ingestion identity contains
the target Contract, schema version, verified source checksum, and the existing normalized mapping
fingerprint. The same checksum and mapping context is an idempotent source duplicate. For one
natural key, the same business hash is a business duplicate and a different hash is a conflict.
Snapshots are immutable in this slice.

`snapshot_at` and `data_as_of` must both be timezone-aware source datetimes. Their verified source
representations are preserved, and provenance records `source_row:data_as_of`. The adapter does not
replace either value with `fetched_at`, the injected clock, or another source field, and it creates
no global datetime-normalization policy.

## Explicit non-decisions

The four raw quantity fields use the existing strict integer parser and the frozen Contract. This
slice invents no nonnegative rule and no arithmetic relationship among quantities. It does not
derive availability or perform unit conversion.

PHASE 5 owns average sales, stock days, safety stock, reorder point, and order recommendation, so
none is accepted or generated. `lead_time_days` is deferred until a supplier-contract Source is
defined and verified; the field remains present in the Frozen Contract.

This slice performs no LIVE/API call, credential access, database operation, filesystem ledger
write, approval execution, or external write. Frozen documents modified: 0. It does not mean that
PHASE 4 overall is complete, and PHASE 5 is not started.
