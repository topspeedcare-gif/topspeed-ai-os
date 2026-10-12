# ADR: PHASE 5 INVENTORY DEMAND VELOCITY V1

- Status: Accepted architecture; runtime implementation not authorized
- Classification: NORMATIVE INTERNAL PHASE 5 ARCHITECTURE DECISION
- Architecture: PHASE 5 DETERMINISTIC CALCULATION FOUNDATION + INVENTORY DEMAND VELOCITY V1
- Metric family: `INVENTORY_DEMAND_VELOCITY`
- Metric: `avg_daily_units`
- Formula version: `topspeed.calculation.inventory_demand_velocity.v1`
- Human Architecture decision: H2 / 30D-COMPLETE-CHANNEL-STRICT
- Authoritative input Contract: `CHANNEL_DAILY`
- Future write-back target: NONE

## 1. Decision and authority

This ADR records the already-approved PHASE 5 Architecture for deterministic inventory demand
velocity. It transcribes the fixed H2 / 30D-COMPLETE-CHANNEL-STRICT decision and creates no new
Architecture choice.

This ADR authorizes no runtime source, tests, persistence, publication, external write, PHASE 6
behavior, or PHASE 5 completion declaration. It modifies no Frozen Architecture, Data Contract,
Schema, registry, or existing ADR.

The selected slice contains only the deterministic Calculation foundation needed to calculate
`avg_daily_units` from existing `CHANNEL_DAILY` records for one exact channel and one exact SKU.

## 2. Exact 30-day policy

The official demand baseline is exactly 30 calendar days. The window is inclusive of
`window_end_date`:

~~~text
window_start_date = window_end_date - 29 calendar days
~~~

Exactly one valid `CHANNEL_DAILY` row is required for every calendar date in the window.
`units_sold` is the sole demand quantity primitive.

- refunds are not subtracted;
- missing dates are not zero and are not imputed;
- duplicate dates are not merged or summed;
- partial-window SUCCESS is forbidden;
- 1-day and 7-day metrics are excluded; and
- dashboard or UI representation is excluded.

## 3. Future public API

The future public entry point is:

~~~python
def calculate_inventory_demand_velocity(
    channel_daily: tuple[Mapping[str, object], ...],
    *,
    run_id: str,
    window_end_date: str,
    formula_version: str = INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION,
) -> InventoryDemandVelocityResult: ...
~~~

`channel_daily` must be an exact built-in tuple. Tuple subclasses, lists, sets, dictionaries,
generators, and other iterables are rejected without materialization or coercion. Every tuple
element must satisfy the existing `collections.abc.Mapping` boundary and then pass the existing
`CHANNEL_DAILY` Contract validator. Contract values and caller mappings are not normalized,
repaired, coerced, or mutated.

## 4. Exact no-result boundary precedence

The future runtime must apply this exact fail-closed order:

1. require `channel_daily` to be an exact built-in tuple;
2. require every tuple element to satisfy the `collections.abc.Mapping` boundary;
3. require the tuple to be non-empty;
4. require `formula_version` to be an exact built-in `str`, then require the exact supported
   value `topspeed.calculation.inventory_demand_velocity.v1`;
5. require `run_id` to be an exact built-in `str`, then validate it through the existing Core
   `require_valid_run_id` authority;
6. require `window_end_date` to be an exact built-in `str`, then validate its exact canonical
   lexical and calendar form;
7. validate every tuple element through the existing `CHANNEL_DAILY` Contract validator in
   original tuple index order;
8. require one exact channel across all validated rows; and
9. require one exact SKU across all validated rows.

A failure stops every lower-precedence boundary check. No failure in steps 1 through 9 creates an
`InventoryDemandVelocityResult`, and no calculation-semantic error collection begins before all
nine steps succeed.

Contract-invalid rows propagate the existing `ContractValidationError`. An invalid Core run ID
propagates the existing `InvalidIdentifierError`. A supported-type formula string whose value is
not the exact supported formula version raises the existing
`UnsupportedFormulaVersionError`. Contract and Core exceptions are not translated into
Calculation-semantic errors.

## 5. Exact scalar boundaries and run provenance

`formula_version`, `run_id`, and `window_end_date` must each be an exact built-in `str` at
their respective precedence step. String subclasses are rejected. No scalar is normalized or
coerced.

`run_id` is caller supplied. Its exact type is required before calling
`require_valid_run_id`. The Calculation Engine does not generate, repair, replace, or normalize
an identifier. The validated value is preserved exactly in the result.

Ingestion run IDs in `CHANNEL_DAILY` rows remain source provenance. Calculation and ingestion run
IDs are separate. The calculation `run_id` is excluded from every row `input_hash` and has no
effect on numeric results. Clock access, randomness, and ID factories are forbidden.

## 6. Window-end-date boundary

`window_end_date` must be an exact built-in string in canonical `YYYY-MM-DD` form, represent a
real Gregorian calendar date, and round-trip identically through the approved date parser.

Reject without normalization:

- string subclasses;
- `datetime` and `date` objects;
- whitespace-padded strings;
- non-ASCII or otherwise noncanonical digit representations;
- timezone text;
- impossible calendar dates;
- alternate separators; and
- every normalization-dependent form.

No current-date, clock, or timezone lookup is permitted.

## 7. Row input hash

Each validated supplied row receives one deterministic Calculation-layer `input_hash`. Its
canonical payload contains exactly:

~~~text
channel
stat_date
sku
units_sold
source
data_as_of
~~~

The implementation must reuse the existing repository canonical JSON and SHA-256 authority. The
result uses the existing `sha256:<64 lowercase hexadecimal characters>` form.

The row hash excludes:

- ingestion `run_id`;
- calculation `run_id`;
- `created_at`;
- `updated_at`;
- `orders`;
- `gross_sales`;
- `refunds`;
- `net_sales`;
- `formula_version`;
- calculated outputs; and
- every other unrelated Contract field.

No source string normalization or numeric coercion is introduced solely for this metric.

## 8. Input reference contract

`InventoryDemandVelocityInputRef` is an immutable frozen, slotted dataclass with fields exactly,
in order:

~~~text
contract_name
natural_key
source
data_as_of
input_hash
~~~

`contract_name` is the exact built-in string `CHANNEL_DAILY`. `natural_key` is the exact
built-in tuple:

~~~text
(channel, stat_date, sku)
~~~

Each natural-key item, `source`, `data_as_of`, and `input_hash` is an exact built-in string
preserving the validated row value. Wrong carrier types, mutable containers, tuple subclasses,
wrong tuple lengths, wrong nested element types, and mutable-state string subclasses are rejected
without coercion.

Canonical `input_refs` ordering is `(stat_date, input_hash)`.

SUCCESS contains exactly 30 input references. ERROR contains every actually supplied
Contract-valid row remaining after the same-channel and same-SKU no-result boundaries succeed,
including out-of-window, duplicate-date, and negative-units rows. Missing dates create no
synthetic references. Duplicate rows remain separate references, including rows with identical
hashes.

## 9. Output contract

`InventoryDemandVelocityOutput` is an immutable frozen, slotted dataclass with fields exactly,
in order:

~~~text
name
value
~~~

`name` is the exact built-in string `avg_daily_units`. The field name is `name`, not
`metric`.

`value` is the approved canonical nonnegative fixed-point string:

- no exponent notation;
- no plus sign;
- ASCII digits only;
- no leading zeros except the value zero;
- no trailing fractional zeros;
- no terminal decimal point;
- numeric zero is exactly `"0"`; and
- one to four fractional digits appear only when required.

Wrong or mutable scalar types are rejected rather than converted.

## 10. Result contract

`InventoryDemandVelocityResult` is an immutable frozen, slotted dataclass with fields exactly,
in order:

~~~text
metric_family
formula_version
run_id
channel
sku
window_start_date
window_end_date
status
outputs
input_refs
errors
~~~

Fixed values are:

~~~text
metric_family = INVENTORY_DEMAND_VELOCITY
formula_version = topspeed.calculation.inventory_demand_velocity.v1
status = SUCCESS or ERROR
~~~

`outputs`, `input_refs`, and `errors` are exact built-in tuples containing only their exact
approved carrier classes. Tuple subclasses, lists, sets, generators, wrong nested classes, and
mutable nested state are rejected. No coercion occurs.

SUCCESS requires exactly one `avg_daily_units` output, exactly 30 input references, no errors,
exactly 30 distinct required dates, exactly one row per required date, and nonnegative
`units_sold` for every row. Result channel and SKU equal the channel and SKU in every input
reference.

ERROR requires no outputs, all qualifying supplied references in canonical order, one or more
canonical errors, result channel and SKU coherence with every included reference, and no partial
numeric output.

## 11. Exact calculation and numeric determinism

SUCCESS uses:

~~~text
total_units = exact integer sum of the 30 units_sold values
avg_daily_units = total_units / 30
~~~

The denominator is exactly 30. The output quantum is exactly `0.0001` and the rounding mode is
`ROUND_HALF_UP`. Arithmetic is exact before the single final rounding step. Integer
quotient/remainder arithmetic or an equivalently exact isolated strategy is required.

Ambient Decimal precision and rounding do not affect the result. The global Decimal context is
not mutated. Source tuple order does not affect the result, and structurally equivalent inputs
produce structurally equal results.

## 12. Error element contract

`InventoryDemandVelocityError` is an immutable frozen, slotted dataclass with fields exactly,
in order:

~~~text
code
field
stat_date
input_hashes
~~~

`code` is exactly one of:

- `OUT_OF_WINDOW`;
- `DUPLICATE_DATE`;
- `MISSING_DATE`; or
- `NEGATIVE_UNITS_SOLD`.

`field` is an exact built-in string. `stat_date` is an exact canonical `YYYY-MM-DD` string.
`input_hashes` is an exact built-in tuple of canonical input-hash strings. Lists, generators,
sets, tuple subclasses, and non-exact nested values are rejected without coercion.

## 13. Collect-all semantic error policy

After every no-result boundary succeeds, the runtime collects every reachable
Calculation-semantic error. A higher-precedence semantic error does not suppress a reachable
lower-precedence semantic error. ERROR never contains a partial `avg_daily_units` output.

### 13.1 OUT_OF_WINDOW

Produce one error for each supplied row outside the inclusive 30-day window:

~~~text
code = OUT_OF_WINDOW
field = stat_date
stat_date = offending row stat_date
input_hashes = one-element tuple containing that row input_hash
~~~

Multiple out-of-window rows produce multiple errors.

### 13.2 DUPLICATE_DATE

Produce exactly one error for each `stat_date` represented by more than one supplied row:

~~~text
code = DUPLICATE_DATE
field = stat_date
stat_date = duplicated validated date
input_hashes = every supplied row hash for that date, sorted lexicographically
~~~

`input_hashes` preserves actual supplied row cardinality. Equal hashes are not deduplicated.
Two identical duplicate rows with hash `H` therefore produce `(H, H)`, not `(H)`.

A duplicated date produces exactly one `DUPLICATE_DATE` error regardless of row count. Its
individual rows remain separate `input_refs`, including multiple equal references for identical
rows.

### 13.3 MISSING_DATE

Produce exactly one error for every required window date with no supplied row:

~~~text
code = MISSING_DATE
field = stat_date
stat_date = missing required date
input_hashes = ()
~~~

No synthetic row, hash, or input reference is created.

### 13.4 NEGATIVE_UNITS_SOLD

Produce one error for each supplied row whose `units_sold` is less than zero:

~~~text
code = NEGATIVE_UNITS_SOLD
field = units_sold
stat_date = offending row stat_date
input_hashes = one-element tuple containing that row input_hash
~~~

Two negative rows on one date produce two `NEGATIVE_UNITS_SOLD` errors. If the date is also
duplicated, the result additionally contains the single `DUPLICATE_DATE` error.

## 14. Canonical error order

Code precedence is:

1. `OUT_OF_WINDOW`;
2. `DUPLICATE_DATE`;
3. `MISSING_DATE`; and
4. `NEGATIVE_UNITS_SOLD`.

Sort the complete error collection by:

1. code precedence;
2. `stat_date` lexicographic ascending; and
3. `input_hashes` tuple lexicographic ascending.

Equivalent input tuple permutations produce the same errors tuple. Error collection is
deterministic and independent of caller row order.

## 15. Source and identity non-interference

This slice does not modify:

- `CHANNEL_DAILY` Contract identity or natural key;
- Data Hub ingestion identity;
- mapping fingerprint;
- source checksum;
- publisher state;
- row traceability;
- existing classification; or
- existing records.

Calculation input hashes are Calculation-layer references only and do not replace Data Hub
ingestion identities.

## 16. Determinism and side-effect boundary

The future runtime is pure deterministic calculation. It performs no:

- INVENTORY, CHANNEL_DAILY, or PRODUCT_MASTER write-back;
- publisher mutation;
- database persistence;
- filesystem business write;
- network or external API call;
- environment or credential access;
- clock access;
- randomness or ID generation;
- callback execution;
- Approval state transition;
- AI_RUN_LOG writing; or
- external publication.

Caller mappings remain unchanged. The result is an internal Calculation result, not a new Data
Contract.

## 17. Existing Architecture non-interference

This decision does not alter H2 / 30D-COMPLETE-CHANNEL-STRICT, the 30-day formula, numeric policy,
six-field row hash, input-reference carrier, output/result/error carrier identities,
Calculation-semantic collect-all behavior, canonical error ordering, scope exclusions, or
side-effect boundary.

It does not redefine or generalize the published Contribution Margin or AD_DAILY Advertising
Metrics slices. No public API, Contract, Schema, registry, Data Hub Adapter, publisher,
configuration, workflow, or dependency is changed by this ADR.

## 18. Explicit exclusions

Excluded from this slice:

- 1-day and 7-day demand velocity;
- weighted demand and seasonality;
- refund-adjusted demand;
- forecast generation;
- reorder point, safety stock, and lead-time calculation;
- inventory-risk grade and reorder recommendation;
- purchase-order generation;
- dashboard, UI, alerting, Slack, and Discord notification;
- Coupang LIVE/API calls;
- INVENTORY mutation;
- Contract, Schema, or registry changes;
- PHASE 6 behavior; and
- a PHASE 5 completion declaration.

## 19. Future runtime test obligations

Runtime and test implementation are not authorized by this ADR. A separately approved runtime
work order must test at minimum:

### 19.1 Public boundary

- exact tuple acceptance and tuple-subclass rejection;
- list, set, dictionary, and generator rejection;
- element `Mapping` validation before non-empty validation;
- empty tuple rejection;
- non-Mapping element rejection;
- exact built-in `formula_version` and string-subclass rejection;
- unsupported supported-type formula string through
  `UnsupportedFormulaVersionError`;
- exact built-in `run_id` and string-subclass rejection before Core validation;
- invalid run ID through `InvalidIdentifierError`;
- exact built-in, canonical `window_end_date` and string-subclass rejection;
- Contract-invalid row rejection in original tuple index order;
- mixed channel and mixed SKU rejection;
- exact approved no-result precedence; and
- proof that boundary failures create no result.

### 19.2 Success

- exactly 30 consecutive dates with one row per date;
- all-zero demand and mixed zero/positive demand;
- large integer `units_sold`;
- exact window start/end inclusivity;
- exactly 30 input references;
- one canonical `avg_daily_units` output; and
- deterministic equality under input permutation.

### 19.3 Numeric determinism

- exact total divided by 30;
- half-up and no-rounding cases;
- canonical zero, integer, and fractional outputs;
- ambient Decimal precision and rounding mutation;
- global Decimal context unchanged;
- no exponent notation; and
- ASCII-only output.

### 19.4 Error contract

- single and multiple out-of-window rows;
- duplicate date with two and more than two rows;
- duplicate date with two distinct hashes;
- duplicate date with two identical rows and equal hashes;
- repeated equal hashes preserved in `DUPLICATE_DATE.input_hashes`;
- duplicate input references preserved, including equal references;
- single and multiple missing dates;
- single negative `units_sold`;
- multiple negative rows on one date;
- combined duplicate and negative errors;
- a combination containing all four error codes;
- collect-all behavior and no partial output;
- exact code, date, and `input_hashes` ordering; and
- missing-date empty `input_hashes`.

### 19.5 Input references and hashes

- exact six-field row hash payload;
- independent sensitivity to every included field;
- non-interference from every excluded field;
- exact natural key;
- duplicate rows and equal hashes retained as separate references;
- no fake reference for a missing date;
- ERROR retaining every qualifying supplied reference;
- canonical `(stat_date, input_hash)` ordering; and
- calculation and ingestion run IDs excluded from the row hash.

### 19.6 Carriers

- frozen and slotted carriers;
- exact fields and order for every carrier;
- `InventoryDemandVelocityOutput` fields exactly `("name", "value")`;
- exact built-in scalar types and mutable string-subclass rejection;
- exact tuple enforcement and tuple-subclass rejection;
- wrong nested carrier rejection;
- SUCCESS and ERROR whole-result invariants;
- channel, SKU, and input-reference coherence;
- nested immutability;
- field reassignment rejection; and
- new attribute rejection.

### 19.7 Side effects

- input mappings remain unchanged;
- no filesystem, database, network, environment, or credential access;
- no clock, randomness, or ID generation;
- no publisher or Contract mutation;
- no INVENTORY write-back; and
- an AST or equivalent forbidden-capability regression guard.

### 19.8 Non-regression

- complete Contribution Margin targeted suite;
- complete AD_DAILY Advertising Metrics targeted suite;
- current full repository suite;
- no deleted or weakened existing tests; and
- no new skip, skipif, or xfail.

## 20. Phase and authorization state

- Human H2 / 30D-COMPLETE-CHANNEL-STRICT decision: PRESERVED
- Audit1 Architecture: APPROVED
- Audit2 final Architecture: APPROVED
- P5-IDV-A2-F-001 through P5-IDV-A2-F-004: CLOSED
- Residual Builder Architecture choice: NONE
- PHASE 4: COMPLETE
- PHASE 5: NOT COMPLETE
- Runtime implementation: NOT AUTHORIZED
- Test implementation: NOT AUTHORIZED
- Publication: NOT AUTHORIZED
- PHASE 6: NOT AUTHORIZED

This ADR is a prerequisite for a separate future runtime implementation work order. It does not
start implementation or authorize another PHASE 5 slice.
