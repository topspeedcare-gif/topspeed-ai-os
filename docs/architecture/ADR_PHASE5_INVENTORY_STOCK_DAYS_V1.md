# ADR: PHASE 5 INVENTORY STOCK DAYS V1

- Status: Accepted architecture; runtime implementation not authorized
- Classification: NORMATIVE INTERNAL PHASE 5 ARCHITECTURE DECISION
- Architecture: PHASE 5 INVENTORY STOCK DAYS V1
- Metric family: `INVENTORY_STOCK_DAYS`
- Metric: `stock_days`
- Formula version: `topspeed.calculation.inventory_stock_days.v1`
- Human Architecture decision: H3 / A2 + B1 + C1 + D1 + E2
- Future write-back target: NONE

## 1. Decision and authority

This ADR records the already-approved PHASE 5 Architecture for deterministic inventory stock
days. It transcribes H3 / A2 + B1 + C1 + D1 + E2 and creates no new Architecture choice.

This ADR is documentation only. It authorizes no runtime source, runtime tests, persistence,
publication, external write, PHASE 6 behavior, next Calculation slice, or PHASE 5 completion
declaration. It modifies no Frozen Architecture, Data Contract, Schema, registry, or existing
ADR.

## 2. A2 authoritative inputs

The future calculation consumes exactly:

1. one existing Contract-valid `INVENTORY` record; and
2. one exact `InventoryDemandVelocityResult` with status `SUCCESS`.

The optional `INVENTORY.avg_daily_units` field is not denominator authority for this slice. The
denominator authority is exactly `demand_velocity.outputs[0].value` from the accepted successful
demand result. The calculation does not recalculate `avg_daily_units`, reconcile it against the
optional INVENTORY field, or write either derived value back to INVENTORY.

## 3. B1 SKU, location, and channel identity

The validated source objects must satisfy exact SKU equality:

~~~text
inventory["sku"] == demand_velocity.sku
~~~

The result preserves `INVENTORY.location` and `demand_velocity.channel` as separate dimensions.
They are not required to be equal. The calculation does not infer semantic equivalence, normalize
one value into the other, create a location/channel mapping, create a mapping registry, or create
a new Contract.

## 4. Future public API

The future public entry point is exactly:

~~~python
def calculate_inventory_stock_days(
    inventory: Mapping[str, object],
    demand_velocity: InventoryDemandVelocityResult,
    *,
    run_id: str,
    formula_version: str = INVENTORY_STOCK_DAYS_FORMULA_VERSION,
) -> InventoryStockDaysResult: ...
~~~

The future public symbols are exactly, in order of this decision:

1. `INVENTORY_STOCK_DAYS_FORMULA_VERSION`;
2. `InventoryStockDaysError`;
3. `InventoryStockDaysInputRef`;
4. `InventoryStockDaysOutput`;
5. `InventoryStockDaysResult`; and
6. `calculate_inventory_stock_days`.

This ADR does not authorize implementation or export of any symbol.

## 5. Pure deterministic runtime boundary

The future calculation performs no network or external API access, filesystem access or mutation,
database access, environment-variable access, credential access, wall-clock access, random
generation, ID generation, LLM inference, Contract mutation, INVENTORY write-back, publisher
mutation, `APPROVAL_QUEUE` mutation, `AI_RUN_LOG` persistence, or external business write.

`run_id` is caller supplied and must be validated through the existing
`topspeed_ai_os.core.ids.require_valid_run_id` authority. The runtime creates no new run-ID
grammar and does not repair, normalize, replace, or generate an ID. The exact validated value is
preserved in the result and excluded from hashes and numeric calculation.

## 6. Exact no-result boundary precedence

The future runtime applies this exact fail-closed order:

1. require `inventory` to satisfy `collections.abc.Mapping`;
2. call exactly `topspeed_ai_os.contracts.validate_schema_only("INVENTORY", inventory)`;
3. require `demand_velocity` to be an exact `InventoryDemandVelocityResult` instance;
4. require `demand_velocity.status` to equal `SUCCESS`;
5. require `formula_version` to be an exact built-in `str`;
6. require `formula_version` to equal
   `topspeed.calculation.inventory_stock_days.v1`;
7. require `run_id` to be an exact built-in `str`;
8. validate `run_id` through the existing Core `require_valid_run_id` authority;
9. require `inventory["sku"]` to equal `demand_velocity.sku` exactly;
10. require `demand_velocity` to contain exactly one output named `avg_daily_units`; and
11. require that output value to be an exact built-in `str` in the approved canonical
    nonnegative fixed-point representation.

A failure stops every lower-precedence check. Steps 1 through 11 create no
`InventoryStockDaysResult`.

The INVENTORY validation path must not use `validate_contract`, `validate_record`, fabricated or
derived `known_skus`, a `PRODUCT_MASTER` lookup, a new SKU registry, or a new mapping authority.

## 7. Exact boundary exception authority

An INVENTORY Contract failure propagates the existing `ContractValidationError` unchanged. An
unsupported exact-built-in-string formula version raises the existing approved Calculation
`UnsupportedFormulaVersionError`. An invalid exact-built-in-string run ID propagates the existing
Core `InvalidIdentifierError` unchanged.

These failures are not translated, wrapped, replaced with fallback `ValueError`, or converted to
a Calculation `ERROR` or `PARTIAL` result. No partial result, side effect, or write-back occurs,
and these failures never enter Calculation business-semantic handling.

## 8. Formula and C1 available-quantity policy

The authoritative formula is:

~~~text
stock_days = available_qty / avg_daily_units
~~~

`available_qty` is the validated `INVENTORY.available_qty`. `avg_daily_units` is the canonical
value from the exact successful demand result.

The approved C1 rule is `available_qty >= 0`. A negative `available_qty` produces:

~~~text
status = ERROR
outputs = ()
reason = None
errors = exactly one InventoryStockDaysError
error.code = INVALID_INPUT
error.field = available_qty
error.input_hashes = (inventory_input_hash,)
~~~

The runtime does not clamp, apply `abs()`, normalize, produce negative stock days, or divide after
detecting this error. No arithmetic occurs.

## 9. E2 zero-demand outcome

When `available_qty >= 0` and numeric `avg_daily_units == 0`, the result is:

~~~text
status = PARTIAL
outputs = exactly one InventoryStockDaysOutput("stock_days", None)
reason = ZERO_DEMAND
errors = ()
~~~

`ZERO_DEMAND` is a valid mathematically undefined calculation outcome. It is not malformed input,
a Calculation error, or an exception. The runtime does not substitute infinity, a large-number
sentinel, zero stock days, an exception, or `ERROR`.

## 10. Positive-demand success

When `available_qty >= 0` and numeric `avg_daily_units > 0`, the result is:

~~~text
status = SUCCESS
outputs = exactly one stock_days output with a non-null canonical value
reason = None
errors = ()
~~~

## 11. D1 exact numeric strategy

The output quantum is exactly `0.0001` and the rounding mode is `ROUND_HALF_UP`.
`avg_daily_units` is interpreted as an exact base-10 rational. The runtime constructs the exact
rational numerator and denominator, uses arbitrary-precision integer arithmetic when needed,
performs no binary floating-point arithmetic and no intermediate rounding, and rounds exactly
once at the end.

Ambient Decimal precision and rounding do not affect the result. The global Decimal context is not
mutated, and `DefaultContext` does not affect the result. Ordinary finite-precision Decimal
division is not an implicit rounding authority. A deterministic integer quotient/remainder
implementation is permitted.

## 12. Canonical non-null output

A numeric `stock_days` output is an exact built-in `str` with all of these properties:

- ASCII digits only;
- fixed-point notation only;
- no exponent notation;
- no leading plus sign;
- no unnecessary leading zeros;
- no negative zero;
- no unnecessary trailing fractional zeros;
- no trailing decimal point;
- zero exactly `"0"`; and
- at most four fractional digits.

Examples are `"0"`, `"1"`, `"1.5"`, and `"1.25"`. The exact value `11.62996` rounds to
`"11.63"` at quantum `0.0001` with `ROUND_HALF_UP`. The example does not replace the general
algorithm.

## 13. Immutable carrier boundary

`InventoryStockDaysOutput`, `InventoryStockDaysError`, `InventoryStockDaysInputRef`, and
`InventoryStockDaysResult` are frozen, slots-based immutable carriers. Their public constructors
enforce every invariant determinable solely from their declared fields. No coercion occurs.
Exact built-in scalar and tuple requirements reject subclasses where specified. Nested approved
carriers require exact class identity.

## 14. InventoryStockDaysOutput

Fields are exactly, in order:

~~~text
name
value
~~~

`name` is an exact built-in `str` equal to `stock_days`. `value` is either an exact built-in `str`
in the canonical form defined above or `None`. `None` is valid only in the complete
`PARTIAL` / `ZERO_DEMAND` result shape.

## 15. InventoryStockDaysError

Fields are exactly, in order:

~~~text
code
field
input_hashes
~~~

`code` and `field` are exact built-in strings. `input_hashes` is an exact built-in
`tuple[str, ...]`, and every hash matches `^sha256:[0-9a-f]{64}$`.

The only valid V1 error has `code == "INVALID_INPUT"`, `field == "available_qty"`, and an exact
one-element `input_hashes` tuple containing the INVENTORY input-reference hash. No other code,
field, or cardinality is valid.

## 16. InventoryStockDaysInputRef tagged carrier

This decision defines exactly one public tagged input-reference carrier. A hidden subtype
hierarchy, private alternative carrier, another public reference carrier, or caller-selected
layout is forbidden.

Fields are exactly, in order:

~~~text
kind
contract_name
natural_key
source
data_as_of
input_hash
metric_family
formula_version
channel
sku
window_start_date
window_end_date
avg_daily_units
upstream_input_refs
~~~

Exact runtime types are:

- `kind`: exact built-in `str`;
- `contract_name`: exact built-in `str` or `None`;
- `natural_key`: exact built-in tuple of exactly three exact built-in `str` elements or `None`;
- `source`: exact built-in `str` or `None`;
- `data_as_of`: exact built-in `str` or `None`;
- `input_hash`: exact built-in `str` matching `^sha256:[0-9a-f]{64}$`;
- `metric_family`: exact built-in `str` or `None`;
- `formula_version`: exact built-in `str` or `None`;
- `channel`: exact built-in `str` or `None`;
- `sku`: exact built-in `str`;
- `window_start_date`: exact built-in `str` or `None`;
- `window_end_date`: exact built-in `str` or `None`;
- `avg_daily_units`: exact built-in `str` or `None`; and
- `upstream_input_refs`: exact built-in tuple containing exact
  `InventoryDemandVelocityInputRef` objects.

Tuple subclasses, string subclasses, nested carrier subclasses, and wrong combinations are
rejected.

## 17. INVENTORY input-reference kind

For `kind == "INVENTORY"`, required values are:

~~~text
contract_name = INVENTORY
natural_key = (inventory.snapshot_at, inventory.sku, inventory.location)
source = inventory.source
data_as_of = inventory.data_as_of
input_hash = approved INVENTORY input hash
sku = inventory.sku
upstream_input_refs = ()
~~~

`metric_family`, `formula_version`, `channel`, `window_start_date`, `window_end_date`, and
`avg_daily_units` are all `None`. Any other combination is invalid. The carrier enforces
`natural_key[1] == sku` and preserves direct-projection values without normalization or
reconstruction.

## 18. DEMAND_VELOCITY input-reference kind

For `kind == "DEMAND_VELOCITY"`, required values are:

~~~text
contract_name = None
natural_key = None
source = None
data_as_of = None
input_hash = approved demand-side projected input hash
metric_family = INVENTORY_DEMAND_VELOCITY
formula_version = demand_velocity.formula_version
channel = demand_velocity.channel
sku = demand_velocity.sku
window_start_date = demand_velocity.window_start_date
window_end_date = demand_velocity.window_end_date
avg_daily_units = demand_velocity.outputs[0].value
upstream_input_refs = exact ordered demand_velocity.input_refs tuple
~~~

`upstream_input_refs` contains exactly 30 exact `InventoryDemandVelocityInputRef` objects. Their
original ordering, duplicate cardinality, and identical repeated hashes are preserved. No
reference is regenerated, summarized, sorted, or replaced by a digest. Any other field
combination is invalid.

## 19. Result input references

`InventoryStockDaysResult.input_refs` is an exact built-in tuple of length two in this exact order:

1. the `INVENTORY` `InventoryStockDaysInputRef`; and
2. the `DEMAND_VELOCITY` `InventoryStockDaysInputRef`.

Reversed order, extra or missing references, lists, tuple subclasses, and alternate carrier
classes are invalid.

## 20. Exact INVENTORY input hash

The implementation reuses `topspeed_ai_os.core.canonical.payload_sha256`. The INVENTORY input hash
payload contains exactly:

~~~text
snapshot_at
sku
location
available_qty
source
data_as_of
~~~

It excludes `on_hand_qty`, `reserved_qty`, `inbound_qty`, `INVENTORY.avg_daily_units`,
`INVENTORY.stock_days`, `lead_time_days`, `safety_stock_qty`, `reorder_point_qty`,
`recommended_order_qty`, ingestion `run_id`, and `created_at`. No dataclass object is hashed.

## 21. Exact demand provenance projection and hash

The exact ordered `demand_velocity.input_refs` tuple remains embedded as immutable downstream
provenance. The demand-side hash is supplementary integrity evidence only and does not replace
the upstream references. It is not called a demand result hash.

The DEMAND_VELOCITY input-reference hash uses `payload_sha256` over a primitive JSON-compatible
payload with exactly these top-level keys:

~~~text
metric_family
formula_version
channel
sku
window_start_date
window_end_date
avg_daily_units
input_refs
~~~

`input_refs` is an ordered JSON array. Every projected upstream reference object contains exactly
`contract_name`, `natural_key`, `source`, `data_as_of`, and `input_hash`. `natural_key` is an
ordered JSON array preserving exact lexical element values.

The projection never hashes dataclass objects directly. It preserves upstream order, duplicate
cardinality, identical repeated hashes, source strings, `data_as_of` strings, and natural-key
lexical values. It does not sort or deduplicate upstream references and does not introduce
complete-result serialization.

## 22. Final Inventory Stock Days input hash

`InventoryStockDaysResult.input_hash` uses `payload_sha256` over exactly:

~~~text
formula_version
inventory_input_hash
demand_input_hash
~~~

`inventory_input_hash` is the INVENTORY input-reference hash. `demand_input_hash` is the
DEMAND_VELOCITY input-reference hash.

The final hash excludes caller calculation `run_id`, output `stock_days`, status, reason, errors,
`created_at`, INVENTORY ingestion `run_id`, and every field already excluded from the approved
projections. Changing an included value changes the appropriate hash; changing only excluded
values does not.

## 23. InventoryStockDaysResult

Fields are exactly, in order:

~~~text
metric_family
formula_version
run_id
sku
location
demand_channel
snapshot_at
window_start_date
window_end_date
status
outputs
input_refs
reason
errors
input_hash
~~~

All non-null scalar fields are exact built-in strings. Fixed values are
`metric_family == "INVENTORY_STOCK_DAYS"` and
`formula_version == "topspeed.calculation.inventory_stock_days.v1"`. Status is exactly
`SUCCESS`, `PARTIAL`, or `ERROR`; reason is exactly `None` or `ZERO_DEMAND`.
`input_hash` is an exact built-in string matching `^sha256:[0-9a-f]{64}$`.

`outputs`, `input_refs`, and `errors` are exact built-in tuples containing only exact approved
carrier classes. Provenance values are exact: `sku` is the coherent source SKU; `location` is
`inventory.location`; `demand_channel` is `demand_velocity.channel`; `snapshot_at` is
`inventory.snapshot_at`; and the window dates are the demand result window dates.

## 24. Whole-result shapes

### SUCCESS

- `status` is `SUCCESS`;
- `outputs` contains exactly one non-null `stock_days` output;
- `input_refs` contains exactly the approved two references;
- `reason` is `None`; and
- `errors` is `()`.

### PARTIAL

- `status` is `PARTIAL`;
- `outputs` contains exactly one `stock_days` output whose value is `None`;
- `input_refs` contains exactly the approved two references;
- `reason` is `ZERO_DEMAND`; and
- `errors` is `()`.

### ERROR

- `status` is `ERROR`;
- `outputs` is `()`;
- `input_refs` contains exactly the approved two references;
- `reason` is `None`; and
- `errors` contains exactly one `INVALID_INPUT` / `available_qty` error.

No other combination is valid.

## 25. Direct-constructor coherence

The public result constructor enforces all invariants decidable solely from its fields, including:

- result SKU equality with both input references;
- result location equality with the INVENTORY natural-key location;
- result snapshot equality with the INVENTORY natural-key snapshot;
- result demand channel equality with the demand reference channel;
- result window-date equality with demand reference dates;
- exact input-reference length, order, and kinds;
- inventory error hash equality with the INVENTORY input hash;
- final input-hash equality with the formula version and two nested hashes; and
- exact `SUCCESS`, `PARTIAL`, and `ERROR` shapes.

The constructor does not revalidate external Contract state, access filesystem, network, or
database state, perform `PRODUCT_MASTER` lookup, fabricate `known_skus`, infer location/channel
equality, mutate nested carriers, or maintain hidden registries or state.

## 26. Determinism

Determinism means structural and value equality. The same validated source inputs and formula
version reproduce equal status, outputs, input references, reason, errors, and input hash.
Changing only a valid caller calculation `run_id` changes only `result.run_id`.

No complete-result byte serialization or result-wide wire protocol is introduced.

## 27. Existing Architecture non-interference

This decision makes no existing Calculation API, carrier, or export-order modification. It makes
no Contract, Schema, registry, Data Contract, Frozen Architecture, or existing ADR modification.
It performs no INVENTORY write-back, demand-result mutation, or `avg_daily_units` recalculation.

The published Contribution Margin, AD_DAILY Advertising Metrics, and Inventory Demand Velocity
architectures and runtimes remain unchanged.

## 28. Future runtime test obligations

Runtime and test implementation are not authorized by this ADR. A separately authorized future
implementation must cover all obligations below.

### 28.1 Boundary and F-001

- non-Mapping INVENTORY;
- exact `validate_schema_only` authority and exact `"INVENTORY"` argument;
- Contract validation before demand-carrier validation;
- unchanged `ContractValidationError` propagation;
- absence of `validate_contract`, `validate_record`, `known_skus` creation, and PRODUCT_MASTER
  lookup;
- exact public API and exact boundary precedence;
- exact demand carrier identity and required `SUCCESS` status;
- exact-string formula and run-ID rules;
- `UnsupportedFormulaVersionError` and unchanged `InvalidIdentifierError` propagation;
- proof that boundary failures create no result and receive no exception translation;
- exact SKU mismatch failure; and
- acceptance of unequal location and channel with separate preservation.

### 28.2 Tagged carrier and F-002

- exact field sets and order for every carrier;
- frozen and slots-based construction;
- exact scalar and tuple types;
- valid and invalid INVENTORY kind combinations;
- valid and invalid DEMAND_VELOCITY kind combinations;
- no subtype or alternate reference carrier;
- exact result input-reference length and order;
- nested carrier subclass rejection;
- output and result direct-constructor invariants; and
- exact `SUCCESS`, `PARTIAL`, and `ERROR` shapes.

### 28.3 Provenance, hashes, and F-003

- exactly 30 embedded upstream references;
- preserved upstream order, duplicate cardinality, and identical repeated hashes;
- proof that a digest cannot replace upstream references;
- exact primitive projection keys and natural-key ordered JSON arrays;
- no direct dataclass hashing;
- lexical `source`, `data_as_of`, and natural-key preservation;
- sensitivity of every included field and non-interference from every excluded field;
- exact INVENTORY hash, demand hash, and final input hash;
- calculation and ingestion run-ID hash non-interference; and
- optional INVENTORY derived-field non-interference.

### 28.4 Exceptions and F-004

- unsupported exact-string formula version raises `UnsupportedFormulaVersionError`;
- invalid exact-string run ID propagates `InvalidIdentifierError` unchanged;
- neither creates `InventoryStockDaysResult`; and
- neither is wrapped, translated, or replaced.

### 28.5 Business and numeric behavior

- negative `available_qty` produces the exact `ERROR` without clamp or arithmetic;
- zero demand produces `PARTIAL`, `stock_days` value `None`, reason `ZERO_DEMAND`, and no errors;
- positive demand produces exact `SUCCESS`;
- exact rational arithmetic and `0.0001` `ROUND_HALF_UP` boundaries;
- exactly one final rounding and no double rounding;
- very large valid integers;
- ambient Decimal precision, ambient rounding, and `DefaultContext` independence;
- no global Decimal context mutation;
- canonical ASCII output; and
- deterministic structural equality.

### 28.6 Side effects and non-regression

- input objects remain unchanged;
- no filesystem, database, network, environment, credential, clock, randomness, ID generation,
  persistence, publisher, approval, log, or external-write side effect;
- complete Contribution Margin regression;
- complete AD_DAILY Advertising Metrics regression;
- complete Inventory Demand Velocity regression;
- full repository regression; and
- no skip, skipif, or xfail.

## 29. Explicit exclusions

This Architecture excludes:

- runtime implementation and runtime tests;
- persistence and write-back;
- `safety_stock_qty`, `reorder_point_qty`, and `recommended_order_qty` calculation;
- lead-time and target-coverage policy;
- forecasting and seasonality;
- 1-day and 7-day demand metrics;
- dashboard and UI;
- `APPROVAL_QUEUE` and `AI_RUN_LOG` writer behavior;
- external API or network access and credential access;
- PHASE 6 Skill, HQ, or Router work; and
- a PHASE 5 completion declaration.

## 30. Phase, authorization, and finding state

- Human H3 / A2 + B1 + C1 + D1 + E2 decision: PRESERVED
- P5-ISD-WO-A2-F-001: CLOSED
- P5-ISD-WO-A2-F-002: CLOSED
- P5-ISD-WO-A2-F-003: CLOSED
- P5-ISD-WO-A2-F-004: CLOSED
- Residual Builder choice: NONE
- PHASE 4: COMPLETE
- PHASE 5: NOT COMPLETE
- Runtime implementation: NOT AUTHORIZED
- Runtime tests: NOT AUTHORIZED
- Publication: NOT AUTHORIZED
- PHASE 6: NOT AUTHORIZED

This accepted Architecture is a prerequisite for a separate future runtime implementation work
order. It does not start implementation, select the next slice, or authorize publication.
