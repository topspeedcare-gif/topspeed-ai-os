# ADR: PHASE 5 Inventory Safety Stock Read-Only Projection V1

## Status

Accepted by the Human Architecture Gate. This ADR records the approved read-only authoritative inventory projection architecture. It does not authorize runtime implementation, publication, Reorder Point implementation, or Phase advancement.

## Decision

The selected architecture is a read-only authoritative INVENTORY projection. Actual INVENTORY persistence and write-back are deferred.

The approved future flow is:

`InventorySafetyStockResult` → validated read-only Contract-valid INVENTORY projection → paired `InventoryReorderPointAuthorityRef` → future Reorder Point consumer.

The projection MUST NOT mutate or persist the source INVENTORY. Direct `InventorySafetyStockResult` consumption by the future Reorder Point entry point is NOT selected: the published Reorder Point function contract consumes a Contract-valid INVENTORY `Mapping` and an exact `SAFETY_STOCK_POLICY` authority.

## Architecture basis

1. `DATA_CONTRACT_V1` already permits optional `INVENTORY.safety_stock_qty`.
2. PHASE 4 INVENTORY synthetic v1 intentionally rejects `safety_stock_qty` only as a source-provided ingestion field. That synthetic Adapter does not establish the authoritative Safety Stock consumption path.
3. `ADR_PHASE5_INVENTORY_SAFETY_STOCK_V1` requires a separate Architecture Gate for a path that materializes or supplies exact `safety_stock_qty` through a Contract-valid INVENTORY record while preserving authoritative Safety Stock provenance.
4. `ADR_PHASE5_INVENTORY_REORDER_POINT_V1` requires both a Contract-valid INVENTORY record containing `safety_stock_qty` and an exact `InventoryReorderPointAuthorityRef` of kind `SAFETY_STOCK_POLICY` whose value equals that INVENTORY value.
5. The existing Reorder Point exact public entry-point contract is preserved and is NOT modified by this Slice.

## Exact private return carrier

The future private return carrier is exactly:

```python
@dataclass(frozen=True, slots=True)
class _InventorySafetyStockProjection:
    inventory: Mapping[str, object]
    authority: InventoryReorderPointAuthorityRef
```

Its fields are exactly, in order, `inventory`, then `authority`. No additional field, `InitVar`, hidden provenance field, callback, registry, alternate authority state, or alternate return carrier is permitted.

The `inventory` field MUST hold an exact `MappingProxyType` wrapping a newly created `dict`; the dict MUST NOT alias the source inventory, and no mutable source object is returned directly. The return carrier remains private and non-exported.

## Exact private producer contract

The future private producer is exactly:

```python
def _project_inventory_safety_stock_for_reorder_point(
    inventory: Mapping[str, object],
    safety_stock: InventorySafetyStockResult,
) -> _InventorySafetyStockProjection: ...
```

It has exactly two positional parameters, with no additional positional parameter, keyword-only parameter, default parameter, or `run_id` parameter. It uses no clock, callback, registry, environment lookup, filesystem lookup, network lookup, or source lookup. It returns exactly the private carrier; it does not return a tuple or raw dict. The producer remains private and non-exported.

## Canonical future foundation and activation boundary

The canonical future module is `src/topspeed_ai_os/calculation/inventory_reorder_point.py`. The canonical authority carrier is `InventoryReorderPointAuthorityRef`; no duplicate or alternate authority carrier is permitted.

During this Slice, `InventoryReorderPointAuthorityRef` public activation is NOT AUTHORIZED; projection producer public activation is NOT AUTHORIZED; `_InventorySafetyStockProjection` public activation is NOT AUTHORIZED; `calculation.__all__` remains UNCHANGED; and Reorder Point seven-symbol public activation is NOT AUTHORIZED.

## Exact input and output boundary

The projection consumes exactly (1) one `collections.abc.Mapping` representing a Contract-valid INVENTORY record and (2) one exact successful `InventorySafetyStockResult`.

The source INVENTORY MUST NOT contain `safety_stock_qty`. The key must be entirely absent. Both `safety_stock_qty = None` and `safety_stock_qty = any existing integer` are rejected. No overwrite path exists.

The projection returns exactly one `_InventorySafetyStockProjection`. Its `inventory` contains every original source INVENTORY key and value, exactly one newly added key, `safety_stock_qty`, and no other new key or changed source value. The projected value equals the exact `InventorySafetyStockResult` `safety_stock_qty` output value. The projected INVENTORY MUST pass:

```python
validate_schema_only("INVENTORY", projected_inventory)
```

The projection performs no persistence.

## Exact paired authority

The returned authority is the canonical `InventoryReorderPointAuthorityRef`, with exactly:

| Field | Required value |
| --- | --- |
| `kind` | `SAFETY_STOCK_POLICY` |
| `sku` | exact `InventorySafetyStockResult.sku` |
| `value` | exact `safety_stock_qty` output value |
| `authority_status` | `APPROVED` |
| `formula_version` | exact `InventorySafetyStockResult.formula_version` |
| `source` | exact Safety Stock policy input-reference `source` |
| `data_as_of` | exact Safety Stock policy input-reference `data_as_of` |

`authority_reference` MUST be exactly `<exact policy authority_reference>@<exact Safety Stock result input_hash>`. For V1 the exact resulting grammar is `TOPSPEED_SAFETY_STOCK_POLICY_V1@sha256:<64 lowercase hex>`. No wall-clock value or generated ID is used.

## Exact authority hash

The authority reuses the published Reorder Point authority hash contract: the existing canonical JSON / `payload_sha256` authority over exactly and in this order: `kind`, `sku`, `value`, `authority_reference`, `authority_status`, `formula_version`, `source`, `data_as_of`.

No additional hash field or alternate canonicalizer is permitted. No fourth/new provenance digest is introduced solely by this projection. The result-bound `authority_reference` preserves continuity to the exact `InventorySafetyStockResult.input_hash` without changing the published `InventoryReorderPointAuthorityRef` field set.

## Exact coherence and preserved values

The following equalities are required:

```text
projected_inventory["safety_stock_qty"] == authority.value == Safety Stock output value
projected_inventory["sku"] == authority.sku == InventorySafetyStockResult.sku
```

Inventory location and Safety Stock demand channel remain distinct dimensions. DO NOT infer `inventory.location == demand channel`.

All existing source INVENTORY fields remain unchanged, including `run_id`, `source`, `data_as_of`, `created_at`, `snapshot_at`, `location`, `on_hand_qty`, `available_qty`, `reserved_qty`, `inbound_qty`, and every other existing Contract-valid field. No freshness threshold is added. Existing source and `data_as_of` values are preserved. Phase 7 freshness authority remains unchanged.

## Exact ordered fail-closed precedence

The future projection applies exactly this order; a failure stops every lower-precedence step, and no projection result is created on failure.

1. Require `inventory` to satisfy `collections.abc.Mapping`.
2. Call exactly `validate_schema_only("INVENTORY", inventory)`.
3. Require the `safety_stock_qty` key to be entirely absent from `inventory`; presence with `None` also fails.
4. Require `safety_stock` to be an exact `InventorySafetyStockResult`; subclasses are rejected.
5. Require all applicable scalar, tuple, and nested carrier values in the Safety Stock result to use the exact approved built-in types and exact approved carrier identities.
6. Require exact Safety Stock result metric, formula version, policy version, `SUCCESS` status, and `run_id` validity. Revalidate `run_id` through existing Core validation.
7. Require exactly one output: `name = safety_stock_qty`; `value = nonnegative exact built-in int`.
8. Require an exact two-item `input_refs` tuple in this order: (1) `DEMAND_VELOCITY`, (2) `SAFETY_STOCK_POLICY`.
9. Revalidate the Demand reference: canonical demand window, exact upstream ordering, complete demand coverage, channel coherence, SKU coherence, and demand hash.
10. Revalidate the Safety Stock policy reference: exact policy literals, exact source, exact `data_as_of`, `safety_stock_days`, and policy hash.
11. Recompute and require result channel coherence, result SKU coherence, result window coherence, result policy coherence, exact approved CEILING output, and exact final Safety Stock input hash.
12. Require `inventory["sku"] == safety_stock.sku`. Do not infer location/channel equality.
13. Create a new dict from the source INVENTORY; add exactly `safety_stock_qty =` the exact Safety Stock output value; wrap the new dict in exact `MappingProxyType`. Do not mutate the source Mapping.
14. Call exactly `validate_schema_only("INVENTORY", projected_inventory)`.
15. Create the exact authority reference `TOPSPEED_SAFETY_STOCK_POLICY_V1@<exact Safety Stock result input_hash>`.
16. Compute the published Reorder Point authority hash over exactly `kind`, `sku`, `value`, `authority_reference`, `authority_status`, `formula_version`, `source`, `data_as_of`; then construct the exact canonical `InventoryReorderPointAuthorityRef`.
17. Construct exact `_InventorySafetyStockProjection`. Require projected inventory SKU = authority SKU = Safety Stock result SKU, and projected `safety_stock_qty` = authority value = Safety Stock output value.
18. Return exactly one `_InventorySafetyStockProjection`.

## Exact exception contract

No exception may be wrapped, translated, suppressed, repaired, normalized, coerced, converted into a projection result, converted into another status, or replaced with fallback data.

| Step | Failure | Required result |
| --- | --- | --- |
| 1 | non-Mapping inventory | `TypeError` |
| 2 | INVENTORY schema failure | existing `ContractValidationError` propagated unchanged |
| 3 | existing `safety_stock_qty` key | `ValueError` |
| 4 | wrong Safety Stock result class identity or subclass | `TypeError` |
| 5 | wrong exact scalar / tuple / nested carrier type | `TypeError` |
| 6 | wrong metric/formula/policy/status literal | `ValueError` |
| 6 | invalid exact-str `run_id` | existing `InvalidIdentifierError` propagated unchanged |
| 7 | wrong exact type | `TypeError` |
| 7 | wrong output count/name/value | `ValueError` |
| 8 | wrong tuple type or nested carrier class type | `TypeError` |
| 8 | wrong count/order/kind | `ValueError` |
| 9–11 | wrong exact type | `TypeError` |
| 9–11 | coherence / calculation / hash failure | `ValueError` |
| 12 | INVENTORY / Safety Stock SKU mismatch | `ValueError` |
| 13 | existing Mapping access or iteration exception | propagated unchanged |
| 14 | projected INVENTORY schema failure | existing `ContractValidationError` propagated unchanged |
| 15–16 | wrong exact type | `TypeError` |
| 15–16 | authority-reference / literal / hash failure | `ValueError` |
| 17 | wrong private return-carrier field type | `TypeError` |
| 17 | paired projection coherence failure | `ValueError` |

## Pure / read-only boundary

The future projection MUST NOT perform source INVENTORY mutation, Safety Stock result mutation, policy authority mutation, persistence, database write, Google Sheet write, external business write, filesystem access, network access, environment access, credential access, clock use, random generation, ID generation, callback execution, mutable cache, mutable registry, Contract mutation, or Schema mutation. No persistence or write-back authority is established by this Slice.

## Explicitly forbidden architecture

This ADR does not introduce actual INVENTORY write-back; overwrite of existing `safety_stock_qty`; replacement of null `safety_stock_qty`; direct Reorder Point consumption of `InventorySafetyStockResult`; an alternate authority or projection carrier; a public projection API; `calculation.__all__` changes; public Reorder Point activation; a Safety Stock formula or policy change; a Policy Authority Producer change; Contract, Schema, registry, config, or workflow changes; production `lead_time_days`; lead-time fallback; supplier-contract lookup; Reorder Point calculation; Recommended Order Quantity; purchase behavior; a freshness threshold; or Phase advancement.

## Reorder Point eligibility boundary

This Architecture establishes only the future authoritative Safety Stock side of the Reorder Point prerequisite. It does NOT establish the authoritative supplier-contract `lead_time_days` path. Therefore Safety Stock projection Architecture is ESTABLISHED; Safety Stock projection runtime is NOT YET AUTHORIZED BY THIS DOCS-ONLY WORK ORDER; the authoritative lead-time path is STILL REQUIRED; Reorder Point Runtime Work Order is NOT AUTOMATICALLY ELIGIBLE; Reorder Point implementation is NOT AUTHORIZED; and Reorder Point publication is NOT AUTHORIZED. A later Audit1 Architecture Gate must independently determine remaining prerequisite state.

## Phase boundary

PHASE 4 is COMPLETE. PHASE 5 is NOT COMPLETE. PHASE 6 is NOT STARTED. This ADR does not complete PHASE 5, authorize the next Slice, or authorize PHASE 6.

## Consequences

The projection supplies a Contract-valid read-only INVENTORY view paired with explicit Safety Stock authority, while preserving source values and Safety Stock provenance. Persistence, write-back, runtime authorization, and Reorder Point eligibility remain outside this decision.
