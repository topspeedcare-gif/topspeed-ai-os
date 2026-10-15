# ADR: PHASE 5 INVENTORY SAFETY STOCK V1

- Status: APPROVED ARCHITECTURE; RUNTIME NOT AUTHORIZED
- Classification: NORMATIVE INTERNAL PHASE 5 ARCHITECTURE DECISION
- Metric family: `INVENTORY_SAFETY_STOCK`
- Formula version: `topspeed.calculation.inventory_safety_stock.v1`
- Policy version: `TOPSPEED_SAFETY_STOCK_POLICY_V1`
- Approval authority: `TOPSPEED Human Architecture Owner`
- Future write-back target: NONE

## 1. Decision and authority

This ADR defines the V1 deterministic Inventory Safety Stock Calculation slice. It transcribes the
Human-approved Safety Stock policy and the final Audit2 hardening without reopening, weakening,
extending, or replacing them. Frozen Architecture, the Data Contract, the Implementation Plan, and
already published Phase 5 ADRs remain authoritative in that order.

This ADR authorizes no runtime, runtime test, Adapter, Contract, Schema, registry, publication,
write-back, or external execution implementation.

Human approval establishes the business policy only. It does not establish the production
policy-authority provenance producer required by Section 16.

## 2. Exact scope

This slice calculates only:

```text
safety_stock_qty
```

It consumes the authoritative successful Inventory Demand Velocity result and an approved Safety
Stock policy authority. It does not consume Inventory Stock Days, calculate or infer supplier lead
time, calculate Reorder Point or Recommended Order Quantity, or mutate INVENTORY.

No Contract, Schema, registry, dependency, configuration, workflow, source, test, or existing ADR
change is part of this decision.

## 3. Preserved Human policy

The exact policy identity is:

```text
metric_family = INVENTORY_SAFETY_STOCK
formula_version = topspeed.calculation.inventory_safety_stock.v1
policy_version = TOPSPEED_SAFETY_STOCK_POLICY_V1
approval_authority = TOPSPEED Human Architecture Owner
authority_status = APPROVED
safety_stock_days = 7
```

The exact formula is:

```text
safety_stock_qty =
CEILING(authoritative avg_daily_units * 7)
```

`standard lead_time_days = 14` is a reference or benchmark only. The value `14` must not appear as
a calculation input, default, fallback, substitute, runtime lead-time value, output, input-hash
field, policy-authority-hash field, or replacement for verified supplier-contract
`lead_time_days`.

## 4. Exact future public API

The future public symbols are exactly, in this order:

1. `INVENTORY_SAFETY_STOCK_FORMULA_VERSION`
2. `InventorySafetyStockPolicyAuthority`
3. `InventorySafetyStockInputRef`
4. `InventorySafetyStockOutput`
5. `InventorySafetyStockResult`
6. `calculate_inventory_safety_stock`

No additional public Safety Stock symbol, error carrier, subtype, alternate result carrier, or
alternate input-reference carrier is permitted.

The future function signature is exactly:

```python
def calculate_inventory_safety_stock(
    demand_velocity: InventoryDemandVelocityResult,
    policy_authority: InventorySafetyStockPolicyAuthority,
    *,
    run_id: str,
    formula_version: str = INVENTORY_SAFETY_STOCK_FORMULA_VERSION,
) -> InventorySafetyStockResult: ...
```

No raw `avg_daily_units`, `safety_stock_days`, SKU, channel, window, policy string, or
caller-supplied hash is accepted separately.

## 5. Exact policy-authority carrier

The future carrier is exactly:

```python
@dataclass(frozen=True, slots=True)
class InventorySafetyStockPolicyAuthority:
    policy_version: str
    approval_authority: str
    authority_reference: str
    authority_status: Literal["APPROVED"]
    source: str
    data_as_of: str
    safety_stock_days: int
    input_hash: str
```

Fields are exactly in the displayed order. No field is nullable.

Exact invariants are:

```text
policy_version = TOPSPEED_SAFETY_STOCK_POLICY_V1
approval_authority = TOPSPEED Human Architecture Owner
authority_reference = TOPSPEED_SAFETY_STOCK_POLICY_V1
authority_status = APPROVED
safety_stock_days = exact built-in int 7
```

`source` is an exact non-empty built-in `str` identifying the established authoritative policy
record source. `data_as_of` is an exact built-in `str` containing a canonical timezone-bearing
ISO-8601 datetime from that authoritative policy record. The datetime must parse as a real
timezone-aware datetime and round-trip to the identical lexical value.

`input_hash` is an exact canonical lowercase hash matching `^sha256:[0-9a-f]{64}$` and must equal
the recomputed Section 12.1 policy hash.

Reject bool as `safety_stock_days`, int subclasses, str subclasses, empty source, naive or
noncanonical datetime strings, wrong literals, carrier subclasses, coercion, normalization, and
hash mismatch.

Direct construction of a structurally valid carrier does not prove production authority. Runtime
eligibility remains gated by Section 16.

## 6. Exact input-reference carrier

The future carrier is exactly:

```python
@dataclass(frozen=True, slots=True)
class InventorySafetyStockInputRef:
    kind: Literal[
        "DEMAND_VELOCITY",
        "SAFETY_STOCK_POLICY",
    ]
    metric_family: str | None
    formula_version: str | None
    policy_version: str | None
    approval_authority: str | None
    authority_reference: str | None
    authority_status: str | None
    source: str | None
    data_as_of: str | None
    channel: str | None
    sku: str | None
    window_start_date: str | None
    window_end_date: str | None
    avg_daily_units: str | None
    safety_stock_days: int | None
    input_hash: str
    upstream_input_refs: tuple[InventoryDemandVelocityInputRef, ...]
```

Fields and order are exact. No subtype hierarchy, alternate reference carrier, hidden field,
`InitVar`, registry field, or private source-state field is permitted.

All non-null strings are exact built-in `str` values. All tuples are exact built-in tuples. All
non-null integers are exact built-in `int` values and reject bool. All nested demand references
require exact carrier identity.

## 7. `DEMAND_VELOCITY` input-reference kind

The `DEMAND_VELOCITY` kind requires exactly:

```text
kind = DEMAND_VELOCITY
metric_family = INVENTORY_DEMAND_VELOCITY
formula_version = topspeed.calculation.inventory_demand_velocity.v1
policy_version = None
approval_authority = None
authority_reference = None
authority_status = None
source = None
data_as_of = None
channel = exact upstream demand channel
sku = exact upstream demand SKU
window_start_date = exact upstream window start
window_end_date = exact upstream window end
avg_daily_units = exact canonical upstream output value
safety_stock_days = None
input_hash = exact demand-side hash from Section 12.2
upstream_input_refs = exact ordered upstream InventoryDemandVelocityInputRef tuple
```

Projected-reference constructor invariants are limited to invariants decidable solely from the
carrier's declared fields:

- canonical nonnegative `avg_daily_units`;
- exact inclusive 30-day window;
- exactly 30 upstream refs;
- canonical upstream ordering;
- complete date coverage;
- exact channel/SKU coherence;
- duplicate cardinality preservation;
- repeated hash preservation; and
- demand-side hash recomputation equality.

The exact `InventoryDemandVelocityResult` class identity, `status == "SUCCESS"`, and exactly one
upstream output named `avg_daily_units` are entry-point-only validations performed before
projection by Section 13 steps 1 through 4.

`InventorySafetyStockInputRef` must not claim to verify source-result identity, source-result
status, or source-result output cardinality that are not represented in its declared fields.

## 8. `SAFETY_STOCK_POLICY` input-reference kind

The `SAFETY_STOCK_POLICY` kind requires exactly:

```text
kind = SAFETY_STOCK_POLICY
metric_family = None
formula_version = None
policy_version = TOPSPEED_SAFETY_STOCK_POLICY_V1
approval_authority = TOPSPEED Human Architecture Owner
authority_reference = TOPSPEED_SAFETY_STOCK_POLICY_V1
authority_status = APPROVED
source = exact policy_authority.source
data_as_of = exact policy_authority.data_as_of
channel = None
sku = None
window_start_date = None
window_end_date = None
avg_daily_units = None
safety_stock_days = exact built-in int 7
input_hash = exact policy authority hash from Section 12.1
upstream_input_refs = ()
```

The policy reference is an exact projection of the passed
`InventorySafetyStockPolicyAuthority`. Its constructor recomputes the policy hash and rejects any
mismatch.

A manually typed policy string, arbitrary Mapping, test fixture, or general caller assertion is
not authoritative production provenance.

## 9. Exact output carrier

The future carrier is exactly:

```python
@dataclass(frozen=True, slots=True)
class InventorySafetyStockOutput:
    name: Literal["safety_stock_qty"]
    value: int
```

Fields are exactly, in order:

1. `name`
2. `value`

`name` is the exact built-in `str` `safety_stock_qty`. `value` is an exact nonnegative built-in
`int`.

Reject bool, int subclasses, `str`, `Decimal`, `float`, negative values, coercion, and every other
output name.

## 10. Exact result carrier

The future carrier is exactly:

```python
@dataclass(frozen=True, slots=True)
class InventorySafetyStockResult:
    metric_family: str
    formula_version: str
    policy_version: str
    run_id: str
    channel: str
    sku: str
    window_start_date: str
    window_end_date: str
    status: Literal["SUCCESS"]
    outputs: tuple[InventorySafetyStockOutput, ...]
    input_refs: tuple[InventorySafetyStockInputRef, ...]
    errors: tuple[()]
    input_hash: str
```

Fields and order are exact. No additional field is permitted.

Required literals are:

```text
metric_family = INVENTORY_SAFETY_STOCK
formula_version = topspeed.calculation.inventory_safety_stock.v1
policy_version = TOPSPEED_SAFETY_STOCK_POLICY_V1
status = SUCCESS
```

Required shapes are:

- `outputs` is an exact one-item tuple containing
  `InventorySafetyStockOutput("safety_stock_qty", expected_value)`;
- `input_refs` is an exact two-item tuple ordered as `DEMAND_VELOCITY`, then
  `SAFETY_STOCK_POLICY`; and
- `errors` is the exact empty built-in tuple `()`.

Result coherence requires:

- result channel, SKU, and window equal the demand reference;
- result policy version equals the policy reference;
- output value equals the exact Section 11 calculation;
- result input hash equals the recomputed final hash;
- `run_id` passes existing Core validation; and
- every nested carrier is an exact approved class, not a subclass.

There is no ERROR or PARTIAL Safety Stock result in V1. Every invalid input covered by the
boundary contract creates no `InventorySafetyStockResult`.

## 11. Exact numeric policy

The sole numeric authority is:

```text
demand_velocity.outputs[0].value
```

Interpret the canonical decimal as the exact base-10 rational:

```text
avg_daily_units = numerator / scale
```

Then calculate exactly:

```text
safety_stock_qty = ceil(numerator * 7 / scale)
```

Required implementation meaning is arbitrary-precision integer arithmetic, quotient/remainder
CEILING, and exactly one final rounding. There is no intermediate rounding, binary float,
ordinary finite-precision Decimal division, ambient Decimal-context dependence, DefaultContext
dependence, mutation of global Decimal state, clamp, sentinel, or infinity.

Numeric zero produces exact integer `0`. Negative, exponent, noncanonical, trailing-zero, or
otherwise invalid `avg_daily_units` values are rejected at the no-result boundary.

## 12. Exact canonical hash architecture

All three hashes use exactly `topspeed_ai_os.core.canonical.payload_sha256`, which uses the
existing `canonical_json` authority. Dataclass objects are never hashed directly. No fourth hash
layer is introduced.

### 12.1 Policy authority hash

The policy payload is exactly this primitive mapping:

```text
{
    "policy_version": policy_authority.policy_version,
    "approval_authority": policy_authority.approval_authority,
    "authority_reference": policy_authority.authority_reference,
    "authority_status": policy_authority.authority_status,
    "source": policy_authority.source,
    "data_as_of": policy_authority.data_as_of,
    "safety_stock_days": policy_authority.safety_stock_days,
}
```

The exact key set is, in order:

1. `policy_version`
2. `approval_authority`
3. `authority_reference`
4. `authority_status`
5. `source`
6. `data_as_of`
7. `safety_stock_days`

The stored hash is `payload_sha256(policy_payload)`.

The payload excludes `input_hash` itself, calculation formula version, `run_id`, SKU, channel,
window, demand values, calculated `safety_stock_qty`, `lead_time_days`, and the reference value
`14`.

### 12.2 Demand-side hash

The demand payload is exactly:

```text
{
    "metric_family": demand_velocity.metric_family,
    "formula_version": demand_velocity.formula_version,
    "channel": demand_velocity.channel,
    "sku": demand_velocity.sku,
    "window_start_date": demand_velocity.window_start_date,
    "window_end_date": demand_velocity.window_end_date,
    "avg_daily_units": demand_velocity.outputs[0].value,
    "input_refs": [
        {
            "contract_name": ref.contract_name,
            "natural_key": [
                ref.natural_key[0],
                ref.natural_key[1],
                ref.natural_key[2],
            ],
            "source": ref.source,
            "data_as_of": ref.data_as_of,
            "input_hash": ref.input_hash,
        }
        for ref in demand_velocity.input_refs
    ],
}
```

The exact top-level key set is, in order:

1. `metric_family`
2. `formula_version`
3. `channel`
4. `sku`
5. `window_start_date`
6. `window_end_date`
7. `avg_daily_units`
8. `input_refs`

Each projected upstream reference has exactly `contract_name`, `natural_key`, `source`,
`data_as_of`, and `input_hash`. `natural_key` is projected as a three-element JSON array.

Preserve exact upstream order, repeated references, duplicate cardinality, lexical source values,
and lexical `data_as_of` values. The stored demand hash is `payload_sha256(demand_payload)`.

### 12.3 Final Safety Stock input hash

The final payload is exactly:

```text
{
    "formula_version": "topspeed.calculation.inventory_safety_stock.v1",
    "demand_input_hash": demand_ref.input_hash,
    "policy_authority_hash": policy_ref.input_hash,
}
```

The exact key set is, in order:

1. `formula_version`
2. `demand_input_hash`
3. `policy_authority_hash`

The result hash is `payload_sha256(final_payload)`.

The final input hash excludes `run_id`, output `safety_stock_qty`, created-at or clock values, the
reference lead time `14`, supplier-contract data, Inventory Stock Days, Reorder Point, Recommended
Order Quantity, and unrelated Contract values. Changing only `run_id` changes no hash, output, or
status.

## 13. Exact fail-closed validation precedence

The future entry point applies exactly this order:

1. Require `demand_velocity` to be an exact `InventoryDemandVelocityResult`.
2. Require `demand_velocity.status == "SUCCESS"`.
3. Require exact Inventory Demand Velocity metric identity, formula version, and one
   `avg_daily_units` output.
4. Require canonical 30-day window, exact ordered upstream references, channel/SKU coherence, and
   recomputed demand hash equality.
5. Require `policy_authority` to be an exact `InventorySafetyStockPolicyAuthority`.
6. Require every policy literal, scalar type, canonical `data_as_of` value, and recomputed policy
   hash to be valid.
7. Require `formula_version` to be an exact built-in `str`.
8. Require `formula_version` to equal
   `topspeed.calculation.inventory_safety_stock.v1`.
9. Require `run_id` to be an exact built-in `str`.
10. Validate `run_id` with existing `require_valid_run_id`.
11. Project the exact two input references and recompute the final hash.
12. Perform the deterministic calculation and construct SUCCESS.

A failure stops every lower-precedence check. No failure in steps 1 through 11 creates a result.

## 14. Exact exception mapping

- Step 1, wrong carrier type or carrier subclass: `TypeError`.
- Steps 2 through 4, non-SUCCESS status, wrong demand identity, malformed output, noncanonical
  value, window/reference/coherence failure, or demand-hash mismatch: `ValueError`.
- Step 5, wrong policy carrier type or carrier subclass: `TypeError`.
- Step 6, wrong exact scalar or tuple type: `TypeError`.
- Step 6, wrong literal, empty source, malformed canonical `data_as_of`, invalid policy value, or
  policy-hash mismatch: `ValueError`.
- Step 7, non-exact-str `formula_version`: `TypeError`.
- Step 8, unsupported exact-str `formula_version`: existing
  `UnsupportedFormulaVersionError`.
- Step 9, non-exact-str `run_id`: `TypeError`.
- Step 10, invalid exact-str `run_id`: existing `InvalidIdentifierError`, propagated unchanged.
- Step 11, input-reference projection or final-hash coherence failure: `ValueError`.

No exception is wrapped, translated, suppressed, converted to SUCCESS/ERROR/PARTIAL, replaced
with a default, or repaired through coercion.

## 15. Constructor responsibility

Every public carrier constructor enforces all invariants decidable solely from its declared
fields. This includes exact fields and types, exact literals, exact tuple shapes, nested exact
carrier identity, canonical date and window formats, exact 30-day demand coverage, upstream
ordering and coherence, policy-hash recomputation, demand-hash recomputation, final-hash
recomputation, exact output calculation, exact input-reference order, exact SUCCESS shape, and
run-ID validity.

Source-result identity, source-result status, and source-result output cardinality are not
constructor invariants of the projected demand reference because those facts are absent from its
declared fields. They are entry-point validations under Section 13.

No constructor may accept additional authority through `InitVar`, hidden fields, private source
state, mutable caches, registries, callbacks or state hooks, filesystem or environment access, or
alternate constructor parameters.

## 16. Policy-authority provenance prerequisite

Human approval establishes the business policy only. It does not, by itself, establish a
production policy-authority source path. This docs-only ADR may be accepted and published.

Safety Stock runtime work orders, tests, implementation, and publication remain NOT ELIGIBLE until
a separate Architecture Gate establishes and an independent audit approves a
repository-recognized policy-authority provenance producer.

That producer must create the exact `InventorySafetyStockPolicyAuthority` from an authoritative,
versioned, immutable policy record and establish:

- source ownership;
- canonical `data_as_of` mechanics;
- `authority_reference` mechanics;
- APPROVED status ownership;
- policy-record lifecycle;
- canonical policy hashing;
- exact producer/consumer boundary; and
- evidence that the carrier came from that path.

Arbitrary direct or caller-created carriers, manual strings, hand-created dictionaries, tests or
fixtures, comments or documentation alone, environment variables, fallback constants, runtime
reconstruction of missing authority, the lead-time reference value `14`, and Human approval text
without the audited producer path do not satisfy the prerequisite.

Until that path exists and is independently audited:

```text
Safety Stock runtime Work Order = NOT ELIGIBLE
Safety Stock runtime tests = NOT AUTHORIZED
Safety Stock runtime implementation = NOT AUTHORIZED
Safety Stock runtime publication = NOT AUTHORIZED
```

## 17. Reorder Point materialization boundary

Even a future successful publication of the Safety Stock calculation does not establish the
complete Reorder Point safety-stock input path.

Reorder Point requires both:

1. authoritative Safety Stock calculation provenance; and
2. a separately established path that materializes or supplies the exact `safety_stock_qty`
   through a Contract-valid INVENTORY record coherently paired with the approved Safety Stock
   authority.

The current PHASE 4 synthetic INVENTORY Adapter intentionally rejects `safety_stock_qty` as a
source input and does not establish this path.

A separate future Architecture Gate is required for INVENTORY `safety_stock_qty` materialization
or authoritative consumption, source/result coherence, provenance retention, hash continuity, no
unauthorized write-back, and Reorder Point consumer eligibility.

This ADR does not select or implement that path and does not reopen or weaken the accepted Reorder
Point ADR.

## 18. Pure side-effect boundary

The future calculation performs no:

- INVENTORY or PRODUCT_MASTER write-back;
- Contract, Schema, or registry mutation;
- filesystem, database, network, environment, or credential access;
- clock use, random generation, or ID generation;
- publisher or APPROVAL_QUEUE mutation;
- AI_RUN_LOG persistence;
- supplier-contract lookup or lead-time calculation;
- Inventory Stock Days calculation;
- Reorder Point or Recommended Order Quantity calculation; or
- external business write.

## 19. Future runtime test obligations

A separately authorized future runtime work order must test all of the following.

### Public API

- exact six exports and order;
- exact function signature; and
- no additional public Safety Stock symbol.

### Carriers

- exact fields, order, types, and nullability;
- frozen, slotted, and no instance dictionary;
- tuple, str, int, and nested-carrier subclass rejection;
- bool rejection and no coercion; and
- direct-constructor fail-closed behavior limited to invariants decidable from declared fields.

### Policy authority

- every exact literal;
- canonical timezone-bearing `data_as_of`;
- empty or noncanonical source rejection;
- wrong `safety_stock_days` rejection; and
- tampered policy-hash rejection.

### Demand authority

- exact SUCCESS source carrier at the entry point;
- ERROR demand rejection;
- source output count, name, and value at the entry point;
- exact 30-day window;
- upstream count, order, channel, SKU, and date coverage;
- repeated references and hashes; and
- tampered demand-hash rejection.

### Numeric behavior

- zero demand produces integer `0`;
- fractional CEILING and exact-integer boundaries;
- just-above-integer CEILING;
- very large integer arithmetic;
- no float and exactly one final rounding;
- ambient and DefaultContext independence; and
- unchanged Decimal contexts.

### Final result

- exact two-reference order and SUCCESS-only shape;
- exact calculated output and final-hash recomputation;
- tampered, reordered, missing, or extra reference rejection;
- run-ID validation; and
- run-ID hash non-interference.

### Policy isolation and integrity

- standard `lead_time_days` reference `14` has no runtime or hash effect;
- no supplier-contract, Stock Days, Reorder Point, or Recommended Order Quantity input or behavior;
- all existing Calculation suites and the full repository suite;
- exact export-order regression;
- Ruff check and format check;
- strict UTF-8, no BOM, final newline, and no trailing whitespace;
- no skip, skipif, xfail, deleted test, or weakened assertion;
- exact changed-path scope; and
- sensitive-material scan.

## 20. Explicit non-decisions

This ADR does not decide:

- policy-authority storage location;
- the not-yet-established authority producer implementation;
- supplier-contract format or verification;
- `lead_time_days`;
- INVENTORY `safety_stock_qty` materialization;
- Reorder Point runtime;
- Recommended Order Quantity;
- purchase approval or execution;
- dashboards, notifications, UI, or LIVE connectors;
- PHASE 6 work; or
- PHASE 5 completion.

Each requires its own Architecture Gate.

## 21. Existing Architecture non-interference

This ADR does not modify `ARCHITECTURE_FREEZE_V1.md`, `DATA_CONTRACT_V1.md`,
`IMPLEMENTATION_PLAN_V1.md`, `MIGRATION_MATRIX_V1.md`, `CURRENT_PHASE_HANDOFF`, any existing ADR,
Contract definitions, Contract JSON Schema, Contract registry, dependency or configuration files,
or GitHub workflows.

The Human Safety Stock policy is preserved. Published Inventory Demand Velocity and Inventory
Reorder Point authorities remain closed and unchanged. Inventory Stock Days is not an input to this
slice.

## 22. Phase and authorization state

```text
PHASE 4 = COMPLETE
PHASE 5 = NOT COMPLETE
PHASE 6 = NOT STARTED

Safety Stock Architecture = APPROVED
Safety Stock docs-only ADR = AUTHORIZED
Safety Stock runtime Work Order = NOT ELIGIBLE
Safety Stock runtime tests = NOT AUTHORIZED
Safety Stock runtime implementation = NOT AUTHORIZED
Safety Stock runtime publication = NOT AUTHORIZED
Reorder Point runtime = NOT AUTHORIZED BY THIS ADR
```
