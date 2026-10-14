# ADR: PHASE 5 INVENTORY REORDER POINT V1

- Status: APPROVED ARCHITECTURE; RUNTIME NOT AUTHORIZED
- Classification: NORMATIVE INTERNAL PHASE 5 ARCHITECTURE DECISION
- Metric family: `INVENTORY_REORDER_POINT`
- Formula version: `topspeed.calculation.inventory_reorder_point.v1`
- Human decision: H4 / A1 + B1 + C1 + D2 + E1 + F1
- Future write-back target: NONE

## 1. Decision and authority

This ADR defines the V1 deterministic Inventory Reorder Point Calculation slice. It transcribes
the Human H4 decision without reopening, weakening, extending, or replacing it. Frozen
Architecture, the Data Contract, the Implementation Plan, and already published Phase 5 ADRs
remain authoritative in that order.

This ADR authorizes no runtime, runtime test, Adapter, Contract, Schema, registry, publication,
write-back, or external execution implementation.

## 2. Exact scope

This slice calculates only:

```text
reorder_point_qty
```

It does not calculate `safety_stock_qty`, `avg_daily_units`, `stock_days`,
`recommended_order_qty`, purchase quantity, a purchase order, or an inventory-risk grade.

The output is not written back to INVENTORY or any external system.

## 3. Preserved H4 decision

### H4-A / A1 — authoritative safety stock

Consume the existing authoritative `INVENTORY.safety_stock_qty`. Do not calculate, normalize,
replace, infer, or reconstruct safety stock. Safety-stock policy/formula provenance is mandatory.

### H4-B / B1 — formula

```text
unrounded_reorder_point =
avg_daily_units * lead_time_days + safety_stock_qty
```

### H4-C / C1 — numeric policy

Use exact rational arithmetic. Convert the final result to INTEGER with exactly one final
mathematical CEILING. Binary floating point, intermediate rounding, double rounding, ambient or
global Decimal-context dependency, and global Decimal-context mutation are forbidden.

### H4-D / D2 — missing values

```text
null lead_time_days
-> ERROR / MISSING_INPUT / lead_time_days

null safety_stock_qty
-> ERROR / MISSING_INPUT / safety_stock_qty
```

### H4-E / E1 — accepted domain

`lead_time_days` and `safety_stock_qty` must be nonnegative exact built-in integers when non-null.
Zero is valid. A negative value produces `ERROR / INVALID_INPUT` for its field. The runtime must
not clamp, apply `abs()`, default, repair, coerce, or substitute a value.

### H4-F / F1 — zero demand

```text
avg_daily_units == 0
-> SUCCESS
-> reorder_point_qty = safety_stock_qty
```

This slice has no `PARTIAL` or `ZERO_DEMAND` outcome.

## 4. Authoritative future inputs

The future calculation consumes exactly:

1. one `collections.abc.Mapping` representing a Contract-valid `INVENTORY` record;
2. one exact successful `InventoryDemandVelocityResult`;
3. one exact `InventoryReorderPointAuthorityRef` of kind
   `LEAD_TIME_SUPPLIER_CONTRACT`;
4. one exact `InventoryReorderPointAuthorityRef` of kind `SAFETY_STOCK_POLICY`;
5. a caller-supplied `run_id`; and
6. `formula_version`, defaulting to `INVENTORY_REORDER_POINT_FORMULA_VERSION`.

`avg_daily_units` comes only from the successful demand result. `lead_time_days` and
`safety_stock_qty` come from the validated INVENTORY record and must exactly equal the
corresponding authority-reference values.

The calculation does not consume `InventoryStockDaysResult`, `INVENTORY.avg_daily_units`,
`INVENTORY.stock_days`, `INVENTORY.reorder_point_qty`,
`INVENTORY.recommended_order_qty`, PRODUCT_MASTER, APPROVAL_QUEUE, AI_RUN_LOG, wall-clock values,
or generated IDs.

Inventory location and demand channel remain distinct dimensions. No location/channel equality is
inferred.

## 5. Authority-reference carrier

The future public carrier is exactly:

```python
@dataclass(frozen=True, slots=True)
class InventoryReorderPointAuthorityRef:
    kind: Literal[
        "LEAD_TIME_SUPPLIER_CONTRACT",
        "SAFETY_STOCK_POLICY",
    ]
    sku: str
    value: int | None
    authority_reference: str
    authority_status: Literal["VERIFIED", "APPROVED"]
    formula_version: str | None
    source: str
    data_as_of: str
    input_hash: str
```

All scalar values require exact built-in types. `bool` and integer subclasses are not valid
integers. String subclasses are not valid strings. No coercion or normalization occurs.
`authority_reference` and `source` are non-empty exact strings. `data_as_of` uses the existing
canonical timezone-bearing DATETIME authority. `input_hash` is a canonical existing
`sha256:<64 lowercase hexadecimal digits>` hash.

For `LEAD_TIME_SUPPLIER_CONTRACT`:

```text
authority_status = VERIFIED
formula_version = None
value = authoritative lead_time_days, including None or zero
```

For `SAFETY_STOCK_POLICY`:

```text
authority_status = APPROVED
formula_version = exact non-empty approved policy/formula ID
value = authoritative safety_stock_qty, including None or zero
```

The safety-stock policy identity is preserved but its formula is not executed. No registry,
callback, network lookup, filesystem lookup, or new Data Contract authority is introduced.

## 6. Authority-reference hashes

For both authority kinds, use existing canonical JSON plus `payload_sha256` over exactly:

```text
kind
sku
value
authority_reference
authority_status
formula_version
source
data_as_of
```

Null remains JSON null. No dataclass is hashed directly. Changing any included field changes the
hash. Exclude calculation `run_id`, wall clock, output, result, and the Reorder Point formula
version from each authority-reference hash.

## 7. Future public API

```python
def calculate_inventory_reorder_point(
    inventory: Mapping[str, object],
    demand_velocity: InventoryDemandVelocityResult,
    lead_time_authority: InventoryReorderPointAuthorityRef,
    safety_stock_policy: InventoryReorderPointAuthorityRef,
    *,
    run_id: str,
    formula_version: str = INVENTORY_REORDER_POINT_FORMULA_VERSION,
) -> InventoryReorderPointResult: ...
```

Future public symbols are exactly, in this order:

1. `INVENTORY_REORDER_POINT_FORMULA_VERSION`
2. `InventoryReorderPointAuthorityRef`
3. `InventoryReorderPointError`
4. `InventoryReorderPointInputRef`
5. `InventoryReorderPointOutput`
6. `InventoryReorderPointResult`
7. `calculate_inventory_reorder_point`

No additional alias or Reorder Point public symbol is permitted.

## 8. Exact no-result boundary precedence

The future runtime applies this exact fail-closed order:

1. require `inventory` to satisfy `collections.abc.Mapping`;
2. call exactly `validate_schema_only("INVENTORY", inventory)`;
3. require `demand_velocity` to be an exact `InventoryDemandVelocityResult`;
4. require `demand_velocity.status == "SUCCESS"`;
5. require `lead_time_authority` to be an exact
   `InventoryReorderPointAuthorityRef`;
6. require its kind to be `LEAD_TIME_SUPPLIER_CONTRACT`;
7. require `safety_stock_policy` to be an exact
   `InventoryReorderPointAuthorityRef`;
8. require its kind to be `SAFETY_STOCK_POLICY`;
9. require `formula_version` to be an exact built-in `str`;
10. require the exact supported formula version;
11. require `run_id` to be an exact built-in `str`;
12. validate `run_id` through existing `require_valid_run_id`;
13. require exact SKU equality across INVENTORY, demand result, and both authorities;
14. require authority values to exactly equal the corresponding INVENTORY values; and
15. require exactly one canonical `avg_daily_units` output in the demand result.

Any failure creates no `InventoryReorderPointResult`. The runtime must not use
`validate_contract`, `validate_record`, fabricated or derived `known_skus`, a PRODUCT_MASTER
lookup, or a new Contract registry or mapping authority.

## 9. Boundary exception authority

An INVENTORY Contract failure propagates the existing `ContractValidationError` unchanged. An
unsupported exact-string formula version raises the existing `UnsupportedFormulaVersionError`.
An invalid exact-string run ID propagates the existing `InvalidIdentifierError` unchanged. Exact
type, carrier, or coherence failures raise the deterministic ADR-specified `TypeError` or
`ValueError`.

No boundary exception is wrapped, translated, replaced, or converted into a Calculation `ERROR`.

## 10. Semantic error policy

Only after every no-result boundary succeeds, inspect exactly `lead_time_days` and
`safety_stock_qty`. Reachable semantic errors are exactly:

```text
MISSING_INPUT / lead_time_days
MISSING_INPUT / safety_stock_qty
INVALID_INPUT / lead_time_days
INVALID_INPUT / safety_stock_qty
```

Null produces `MISSING_INPUT`; a negative exact integer produces `INVALID_INPUT`; zero and a
positive integer are valid. Collect every reachable error. Each field produces at most one error.

Canonical ordering is first by code (`MISSING_INPUT`, then `INVALID_INPUT`) and then by field
(`lead_time_days`, then `safety_stock_qty`). An `ERROR` result contains no numeric output.

## 11. Exact numeric strategy

Interpret canonical nonnegative `avg_daily_units` as an exact integer numerator plus decimal
scale. Compute exactly:

```text
numerator =
avg_daily_units_numerator * lead_time_days
+ safety_stock_qty * avg_daily_units_scale

reorder_point_qty = ceil(numerator / avg_daily_units_scale)
```

Use deterministic integer `divmod` or an exact equivalent. Perform no binary floating-point
arithmetic and no intermediate rounding. Apply CEILING exactly once to the final exact rational.
Ambient Decimal and `DefaultContext` state must neither affect the result nor be mutated.

Required identities are:

```text
avg_daily_units == 0 -> reorder_point_qty == safety_stock_qty
lead_time_days == 0 -> reorder_point_qty == safety_stock_qty
safety_stock_qty == 0 -> reorder_point_qty == ceil(avg_daily_units * lead_time_days)
```

## 12. Output carrier

```python
@dataclass(frozen=True, slots=True)
class InventoryReorderPointOutput:
    name: Literal["reorder_point_qty"]
    value: int
```

`value` is an exact nonnegative built-in `int`. Reject `bool`, integer subclasses, `str`,
`Decimal`, and `float`. No coercion occurs.

## 13. Error carrier

```python
@dataclass(frozen=True, slots=True)
class InventoryReorderPointError:
    code: Literal["MISSING_INPUT", "INVALID_INPUT"]
    field: Literal["lead_time_days", "safety_stock_qty"]
    input_hashes: tuple[str, ...]
```

Every `input_hashes` value is an exact built-in two-item tuple of canonical hashes. For either
error code, the exact mapping is:

```text
lead_time_days:
(inventory_ref.input_hash, lead_time_authority_ref.input_hash)

safety_stock_qty:
(inventory_ref.input_hash, safety_stock_policy_ref.input_hash)
```

The inventory hash is always first and the matching authority hash second. A demand hash or final
hash never appears in semantic-field errors. Reject reversed order, missing or extra hashes, the
wrong authority hash, demand/final hash substitution, tuple subclasses, and noncanonical hashes.

## 14. Input-reference carrier

```python
@dataclass(frozen=True, slots=True)
class InventoryReorderPointInputRef:
    kind: Literal[
        "INVENTORY",
        "DEMAND_VELOCITY",
        "LEAD_TIME_SUPPLIER_CONTRACT",
        "SAFETY_STOCK_POLICY",
    ]
    contract_name: str | None
    natural_key: tuple[str, str, str] | None
    source: str | None
    data_as_of: str | None
    input_hash: str
    metric_family: str | None
    formula_version: str | None
    channel: str | None
    sku: str
    location: str | None
    window_start_date: str | None
    window_end_date: str | None
    avg_daily_units: str | None
    lead_time_days: int | None
    safety_stock_qty: int | None
    authority_reference: str | None
    authority_status: str | None
    upstream_input_refs: tuple[InventoryDemandVelocityInputRef, ...]
```

There is no additional field, subtype, hidden provenance object, private source-state field,
`InitVar`, registry field, or alternate carrier. All non-null strings are exact built-in strings,
all tuples are exact built-in tuples, and all non-null integer values are exact built-in integers.
Reject string, tuple, integer, and nested carrier subclasses. No coercion or normalization occurs.

Every result contains exactly four references in this order:

```text
0 INVENTORY
1 DEMAND_VELOCITY
2 LEAD_TIME_SUPPLIER_CONTRACT
3 SAFETY_STOCK_POLICY
```

## 15. INVENTORY reference kind

The INVENTORY reference requires exactly:

```text
kind = INVENTORY
contract_name = INVENTORY
natural_key = (snapshot_at, sku, location)
source = exact INVENTORY.source
data_as_of = exact INVENTORY.data_as_of
input_hash = exact approved INVENTORY projection hash
metric_family = None
formula_version = None
channel = None
sku = exact INVENTORY.sku
location = exact INVENTORY.location
window_start_date = None
window_end_date = None
avg_daily_units = None
lead_time_days = exact INVENTORY.lead_time_days, including None or zero
safety_stock_qty = exact INVENTORY.safety_stock_qty, including None or zero
authority_reference = None
authority_status = None
upstream_input_refs = ()
```

The natural key has exactly three exact strings; index 0 is the exact snapshot, index 1 equals
`sku`, and index 2 equals `location`. The constructor recomputes the INVENTORY projection hash and
forbids demand- or authority-only fields.

## 16. DEMAND_VELOCITY reference kind

The demand reference requires exactly:

```text
kind = DEMAND_VELOCITY
contract_name = None
natural_key = None
source = None
data_as_of = None
input_hash = approved demand projection hash
metric_family = INVENTORY_DEMAND_VELOCITY
formula_version = topspeed.calculation.inventory_demand_velocity.v1
channel = exact demand channel
sku = exact demand SKU
location = None
window_start_date = exact upstream window start
window_end_date = exact upstream window end
avg_daily_units = exact canonical upstream value
lead_time_days = None
safety_stock_qty = None
authority_reference = None
authority_status = None
upstream_input_refs = exact ordered tuple of 30 InventoryDemandVelocityInputRef objects
```

Enforce exact successful Demand Velocity V1 identity, the exact inclusive 30-day window, exactly
30 upstream refs, canonical order, complete date coverage, channel/SKU coherence, duplicate
cardinality, repeated hashes, and recomputation of the demand projection hash.

## 17. LEAD_TIME_SUPPLIER_CONTRACT reference kind

Require exactly:

```text
kind = LEAD_TIME_SUPPLIER_CONTRACT
contract_name = None
natural_key = None
source = exact authority source
data_as_of = exact canonical timezone-bearing authority data_as_of
input_hash = exact lead-time authority hash
metric_family = None
formula_version = None
channel = None
sku = exact authority SKU
location = None
window_start_date = None
window_end_date = None
avg_daily_units = None
lead_time_days = exact authoritative value, including None or zero
safety_stock_qty = None
authority_reference = exact non-empty supplier-contract reference
authority_status = VERIFIED
upstream_input_refs = ()
```

## 18. SAFETY_STOCK_POLICY reference kind

Require exactly:

```text
kind = SAFETY_STOCK_POLICY
contract_name = None
natural_key = None
source = exact policy authority source
data_as_of = exact canonical timezone-bearing policy data_as_of
input_hash = exact safety-stock authority hash
metric_family = None
formula_version = exact non-empty approved policy/formula version
channel = None
sku = exact policy SKU
location = None
window_start_date = None
window_end_date = None
avg_daily_units = None
lead_time_days = None
safety_stock_qty = exact authoritative value, including None or zero
authority_reference = exact non-empty policy reference
authority_status = APPROVED
upstream_input_refs = ()
```

Entry-point coherence requires the INVENTORY value, corresponding authority carrier value, and
corresponding input-reference value to be exactly equal. All four input references use the exact
same SKU.

## 19. Result carrier

```python
@dataclass(frozen=True, slots=True)
class InventoryReorderPointResult:
    metric_family: str
    formula_version: str
    run_id: str
    sku: str
    location: str
    demand_channel: str
    snapshot_at: str
    window_start_date: str
    window_end_date: str
    status: Literal["SUCCESS", "ERROR"]
    outputs: tuple[InventoryReorderPointOutput, ...]
    input_refs: tuple[InventoryReorderPointInputRef, ...]
    errors: tuple[InventoryReorderPointError, ...]
    input_hash: str
```

There is no additional public result field, including no `reason`, `stock_days`,
`recommended_order_qty`, `available_qty`, `inbound_qty`, generated timestamp, or hidden source
state.

The result requires:

```text
metric_family = INVENTORY_REORDER_POINT
formula_version = topspeed.calculation.inventory_reorder_point.v1
result.sku = every input-reference SKU
result.location = inventory_ref.location = inventory_ref.natural_key[2]
result.snapshot_at = inventory_ref.natural_key[0]
result.demand_channel = demand_ref.channel
result.window_start_date = demand_ref.window_start_date
result.window_end_date = demand_ref.window_end_date
```

The constructor recomputes the final input hash from the formula version and the four ordered
nested hashes.

SUCCESS requires exactly one `InventoryReorderPointOutput("reorder_point_qty", value)`, empty
errors, both required numeric inputs present and nonnegative, and `value` equal to the approved
CEILING formula. Zero demand requires the output to equal `safety_stock_qty`.

ERROR requires empty outputs and the exact complete canonical tuple of all reachable semantic
errors. ERROR is invalid when both required numeric inputs are present and nonnegative.

Every constructor enforces every invariant decidable solely from its declared fields.

## 20. Provenance and hash authority

The INVENTORY projection hash uses existing canonical JSON plus `payload_sha256` over exactly:

```text
snapshot_at
sku
location
lead_time_days
safety_stock_qty
source
data_as_of
```

It excludes `on_hand_qty`, `available_qty`, `reserved_qty`, `inbound_qty`, INVENTORY
`avg_daily_units`, `stock_days`, `reorder_point_qty`, `recommended_order_qty`, ingestion `run_id`,
`created_at`, and calculation `run_id`.

The demand projection reuses the exact primitive projection approved for Inventory Stock Days V1:

```text
metric_family
formula_version
channel
sku
window_start_date
window_end_date
avg_daily_units
input_refs
```

Each projected upstream demand reference contains exactly `contract_name`, `natural_key` as a JSON
array, `source`, `data_as_of`, and `input_hash`. No dataclass object is hashed directly.

The final input hash contains exactly:

```text
formula_version
inventory_input_hash
demand_input_hash
lead_time_authority_hash
safety_stock_policy_hash
```

Changing only calculation `run_id` changes none of the hashes, numeric result, status, or errors.
The full ordered upstream provenance is retained; no opaque digest replaces it.

## 21. Constructor and entry-point responsibility

Direct carrier construction enforces every approved invariant decidable from declared fields,
including exact types and literals, exact tuple shapes, nested carrier identity, ordering,
coherence, complete demand-window coverage, authority hash recomputation, INVENTORY hash
recomputation, final hash recomputation, semantic error completeness, and exact SUCCESS/ERROR
shapes.

The public calculation entry point validates and projects the original INVENTORY mapping, embeds
the passed demand refs, compares authority values with the validated source fields, and applies the
actual missing, negative, zero, and positive source values. No extra public input, `InitVar`, hidden
state, callback, registry, source lookup, or mutable cache is permitted.

## 22. Runtime provenance prerequisite

This docs-only ADR may be accepted and published. Runtime implementation remains NOT AUTHORIZED
until both authoritative input paths below exist and have been independently audited.

The supplier-contract path must supply:

```text
sku
lead_time_days
authority_reference
authority_status = VERIFIED
source
data_as_of
canonical input hash
```

The safety-stock policy/formula path must supply:

```text
sku
safety_stock_qty
authority_reference
authority_status = APPROVED
formula_version
source
data_as_of
canonical input hash
```

The current PHASE 4 synthetic INVENTORY Adapter does not establish either production authority
path. An INVENTORY field value alone, manually invented strings, arbitrary caller declarations,
and test fixtures do not satisfy this prerequisite.

Until separately audited evidence exists:

```text
runtime Work Order = NOT ELIGIBLE
runtime implementation = NOT AUTHORIZED
runtime tests = NOT AUTHORIZED
runtime publication = NOT AUTHORIZED
```

Any future source or Adapter work requires its own Architecture Gate and approved Work Order.

## 23. Pure side-effect boundary

The future calculation is pure and deterministic. It performs no INVENTORY or Contract
write-back, source mutation, demand-result mutation, authority-reference mutation, publisher
mutation, filesystem/database/network access, environment or credential access, clock or
randomness use, ID generation, APPROVAL_QUEUE mutation, AI_RUN_LOG persistence, purchase-order
creation, or other external business write.

## 24. Future runtime test obligations

A separately authorized future runtime Work Order must test all obligations below.

### 24.1 Boundary

- non-Mapping INVENTORY;
- exact `validate_schema_only("INVENTORY", inventory)` authority and Contract exception
  propagation;
- exact demand-result type and SUCCESS status;
- exact authority carrier types and kind ordering;
- exact formula and run-ID types and their approved exception authorities;
- exact validation precedence; and
- proof that a boundary failure creates no result.

### 24.2 H4 semantic behavior

- null lead time, null safety stock, and both null;
- negative lead time, negative safety stock, and both negative;
- zero lead time, zero safety stock, zero demand, and positive demand;
- complete canonical collect-all errors; and
- absence of clamp, default, repair, or substitution.

### 24.3 Numeric behavior

- exact built-in integer results;
- just-above-integer CEILING and exact-integer no increment;
- fractional demand and very large valid integers without overflow;
- no float and no intermediate rounding;
- ambient Decimal and DefaultContext independence;
- unchanged global Decimal contexts; and
- exactly one final rounding.

### 24.4 Provenance and hashes

- exact INVENTORY, demand, lead-authority, safety-policy, and final hashes;
- all demand upstream refs, order, duplicate cardinality, and repeated hashes;
- sensitivity of every included field and non-interference of every excluded field;
- run-ID hash non-interference;
- authority/INVENTORY value mismatch and SKU mismatch rejection;
- tampered-hash rejection; and
- reordered, missing, extra, or substituted reference rejection.

### 24.5 Carriers

- frozen and slots-based dataclasses with exact field order;
- absence of instance dictionaries and extra constructor authority;
- exact scalar, tuple, and nullability matrices;
- rejection of tuple, string, integer, and nested carrier subclasses;
- exact SUCCESS and ERROR shapes; and
- direct-constructor fail-closed behavior.

### 24.6 Non-regression and integrity

- complete Contribution Margin, AD_DAILY, Inventory Demand Velocity, and Inventory Stock Days
  suites;
- full repository suite and exact public export order;
- no skip, skipif, xfail, weakened assertion, or deleted test;
- Ruff check and format check;
- strict UTF-8, no BOM, final newline, and no trailing whitespace;
- exact path scope; and
- sensitive-material scan.

## 25. Explicit non-decisions

This ADR does not decide or implement a safety-stock calculation formula, safety-stock policy
generation, supplier-contract verification system, `recommended_order_qty`, target coverage days,
EOQ, MOQ, order multiple, inbound or available/on-hand inventory deduction, risk grade, reorder
alert, purchase approval or execution, INVENTORY write-back, dashboard/UI/notification, LIVE
connector, PHASE 6 work, or PHASE 5 completion.

## 26. Existing Architecture non-interference

No existing Calculation API, carrier, formula, output, error, hash, or export is changed. Frozen
Architecture, DATA_CONTRACT, IMPLEMENTATION_PLAN, Contract definitions, schemas, registry,
Adapters, existing ADRs, and handoff state remain unchanged.

Inventory Stock Days is not an arithmetic or provenance input to this slice. Contribution Margin,
AD_DAILY Advertising Metrics, Inventory Demand Velocity, and Inventory Stock Days behavior remains
unchanged.

## 27. Phase and authorization state

- Human H4 / A1 + B1 + C1 + D2 + E1 + F1 decision: PRESERVED
- Docs-only ADR: AUTHORIZED
- Runtime Work Order: NOT ELIGIBLE pending independently audited authority paths
- Runtime implementation: NOT AUTHORIZED
- Runtime tests: NOT AUTHORIZED
- Runtime publication: NOT AUTHORIZED
- External write-back: NONE
- PHASE 4: COMPLETE
- PHASE 5: NOT COMPLETE
- PHASE 6: NOT STARTED
