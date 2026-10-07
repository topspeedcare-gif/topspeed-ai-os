# ADR: PHASE 5 deterministic calculation foundation and PRODUCT_MASTER contribution margin v1

- Status: Accepted architecture; runtime implementation not authorized
- Classification: NORMATIVE INTERNAL PHASE 5 ARCHITECTURE DECISION
- Architecture: PHASE 5 DETERMINISTIC CALCULATION FOUNDATION AND PRODUCT_MASTER CONTRIBUTION MARGIN V1
- Metric: `CONTRIBUTION_MARGIN`
- Formula version: `topspeed.calculation.contribution_margin.v1`

## 1. Decision and selected slice

This ADR records the approved Human Architecture Decision B / BUSINESS-STRICT for the PHASE 5
deterministic Calculation foundation. The selected slice contains only:

- deterministic Calculation foundation;
- PRODUCT_MASTER contribution margin; and
- PRODUCT_MASTER contribution margin rate.

No CTR, CVR, ROAS, or inventory metric enters this slice. This ADR is architecture only. It does
not authorize runtime code, tests, persistence, publication, or an external write.

## 2. Pure runtime boundary

The future Calculation Engine is pure deterministic code. It receives exactly:

1. one record that already passed the existing PRODUCT_MASTER Contract validation boundary; and
2. one caller-supplied `run_id` validated by the existing Core run-ID authority.

The engine must not perform network access, external API access, filesystem mutation, database
access, environment-variable access, credential access, LLM inference, wall-clock access, random
generation, ID generation, Contract mutation, publisher mutation, or external business writes.

## 3. Formula identity and evaluation

The only supported formula version in this slice is
`topspeed.calculation.contribution_margin.v1`.

```text
contribution_margin =
    sale_price
    - purchase_cost
    - (sale_price * fee_rate)
    - fulfillment_cost
    - expected_return_cost
    - other_variable_cost

contribution_margin_rate = contribution_margin / sale_price
```

There is no dynamic expression evaluation and no caller-selected formula text. An unknown formula
version fails closed before calculation and creates no `CalculationResult`.

## 4. Run-ID authority

`run_id` is mandatory and caller supplied. The future public Calculation entry point must reuse
`topspeed_ai_os.core.ids.require_valid_run_id`.

It must not create a new run-ID grammar, duplicate the run-ID regular expression, repair or
normalize a run ID, or generate a run ID. An invalid `run_id` is a boundary failure and creates no
`CalculationResult`.

A valid `run_id` is preserved exactly in `CalculationResult.run_id`. It is excluded from
`input_hash` and has no effect on numeric outputs, calculation status, or errors.

## 5. Existing PRODUCT_MASTER DECIMAL authority

The existing PRODUCT_MASTER Contract and repository DECIMAL semantics are authoritative. The
future engine must reuse the existing Contract validation boundary and
`topspeed_ai_os.contracts.logical_types.parse_canonical_decimal`; it must not invent a stricter
lexical grammar.

Existing Contract-valid forms such as `"0"`, `"0.50"`, `"1.000"`, and `"5000.00"` remain valid
calculation input representations. A Contract-valid DECIMAL must not become `INVALID_INPUT`
because it contains insignificant fractional zeros.

Input processing order is exact:

1. existing PRODUCT_MASTER Contract validation;
2. existing repository DECIMAL parsing;
3. BUSINESS-STRICT semantic validation; and
4. formula evaluation only when semantic validation has no errors.

Validated PRODUCT_MASTER decimal source strings are preserved. Numerically equivalent values such
as `"5000.00"`, `"5000.0"`, and `"5000"` remain distinct lexical source values. Trailing zeros are
not removed from the source record or before `input_hash`, do not cause `INVALID_INPUT`, and do not
alter numeric BUSINESS-STRICT comparison.

## 6. BUSINESS-STRICT semantic policy

After Contract validation and repository DECIMAL parsing, the following rules apply:

```text
sale_price > 0

purchase_cost >= 0
fulfillment_cost >= 0
expected_return_cost >= 0
other_variable_cost >= 0

0 <= fee_rate <= 1
```

A negative calculated `contribution_margin` is valid `SUCCESS`. A negative calculated
`contribution_margin_rate` is valid internal `SUCCESS`. Calculated results must not be clamped to
zero.

## 7. Boundary failures and calculation errors

Contract/input boundary failures create no `CalculationResult`. They propagate through the
existing validation boundary and must not be translated into `MISSING_INPUT`, `INVALID_INPUT`, or
`ZERO_SALE_PRICE`. Boundary failures include:

- an invalid PRODUCT_MASTER Contract record or the wrong Contract;
- Contract-invalid required-field absence;
- Contract-invalid DECIMAL syntax, type, or nonfinite value;
- an invalid `run_id`; and
- an unknown formula version.

`CalculationResult` with status `ERROR` is reserved for an already Contract-valid PRODUCT_MASTER
record that fails Calculation-level BUSINESS-STRICT semantics. The exact calculation error codes
are:

- `MISSING_INPUT`: a Contract-valid omitted or null formula input;
- `ZERO_SALE_PRICE`: a Contract-valid `sale_price` whose parsed numeric value equals zero; and
- `INVALID_INPUT`: a Contract-valid parsed value that violates the Human B range.

Reachable negative `sale_price`, `purchase_cost`, `fulfillment_cost`, `expected_return_cost`, or
`other_variable_cost` is `INVALID_INPUT`. The current PRODUCT_MASTER Contract already enforces
`0 <= fee_rate <= 1`. A normal public call must not manufacture a `CalculationResult` for a
Contract-invalid `fee_rate`; the local BUSINESS-STRICT range check remains required but does not
authorize bypassing the Contract boundary.

Multiple Calculation-level semantic errors may be returned, with at most one error per formula
field. Errors are ordered exactly by:

1. `sale_price`;
2. `purchase_cost`;
3. `fee_rate`;
4. `fulfillment_cost`;
5. `expected_return_cost`; and
6. `other_variable_cost`.

Per-field precedence is exact: Contract-valid omitted or null becomes `MISSING_INPUT`;
`sale_price` numeric zero becomes `ZERO_SALE_PRICE`; and a Contract-valid numeric Human-B
violation becomes `INVALID_INPUT`. No formula arithmetic occurs when one or more Calculation
errors exist.

## 8. Calculation input hash

The exact `input_hash` payload fields are:

```text
sku
currency
sale_price
purchase_cost
fee_rate
fulfillment_cost
expected_return_cost
other_variable_cost
source
data_as_of
```

The hash excludes `run_id`, `formula_version`, `contribution_margin`,
`contribution_margin_rate`, clock values, and generated identifiers.

For PRODUCT_MASTER DECIMAL fields, the payload contains the exact validated lexical field strings.
The engine must not strip trailing zeros, normalize equivalent Decimal strings, normalize negative
zero before hashing, or serialize a parsed Decimal back into a replacement string. A Contract-valid
omitted or null nullable formula value projects to explicit JSON `null` in the hash payload.

The only hash authority is `topspeed_ai_os.core.canonical.canonical_json` together with
`topspeed_ai_os.core.canonical.payload_sha256`.

## 9. CalculationInputRef

`CalculationInputRef` has exactly these fields:

```text
contract_name
natural_key
source
data_as_of
input_hash
```

Their exact meanings are:

- `contract_name`: `PRODUCT_MASTER`;
- `natural_key`: an immutable one-element tuple containing the validated input `sku`;
- `source`: the exact validated PRODUCT_MASTER `source` value;
- `data_as_of`: the exact validated PRODUCT_MASTER `data_as_of` value; and
- `input_hash`: the exact Calculation input hash defined by this ADR.

Every `CalculationResult` contains exactly one input reference. A generic `"PRODUCT_MASTER"`
source, current time, fetch time, calculation time, or generated timestamp must not be substituted
for the source-owned values.

## 10. Decimal context isolation

Every future calculation uses an isolated local Decimal context and does not depend on ambient or
global Decimal context. It must not call `decimal.setcontext(...)` or mutate
`decimal.getcontext().prec`, `decimal.getcontext().rounding`, or any other process-global Decimal
context state.

Changes to ambient precision, rounding, traps, or exponent settings must not change numeric
results, status, errors, `input_hash`, or output serialization. The global Decimal context must
remain unchanged by the calculation.

## 11. Exact margin precision strategy

For each finite Decimal operand, derive its exact coefficient digits and base-10 exponent from its
Decimal tuple. `coefficient_digits(value)` is the number of digits in that tuple's coefficient; the
Decimal tuple supplies the exponent without lexical normalization.

For:

```text
fee_amount = sale_price * fee_rate
```

define:

```text
product_coefficient_digits =
    coefficient_digits(sale_price) + coefficient_digits(fee_rate)
```

The six monetary terms are `sale_price`, `purchase_cost`, `fee_amount`, `fulfillment_cost`,
`expected_return_cost`, and `other_variable_cost`.

Define:

```text
common_exponent = minimum base-10 exponent of the six monetary terms

aligned_digits(term) =
    coefficient_digits(term)
    + max(0, exponent(term) - common_exponent)

margin_precision = max(
    product_coefficient_digits,
    max(aligned_digits(term) for the six terms) + 1,
    1,
)
```

The `+1` is the carry bound for combining at most six aligned terms. The per-call local calculation
context is:

```text
precision = margin_precision
rounding = ROUND_HALF_UP
```

The multiplication/subtraction sequence must be exact. It must not silently accept `Inexact` or
`Rounded`. `InvalidOperation`, `DivisionByZero`, and `Overflow` fail closed.

## 12. Exact contribution-margin-rate rounding

The precision target is `Decimal("0.0001")` with `ROUND_HALF_UP`. Intermediate Decimal division
must not create double rounding.

The implementation must use an exact quotient/remainder rule equivalent to:

```text
round-half-up(contribution_margin / sale_price * 10000) / 10000
```

For absolute exact rational numerator `N` and positive denominator `D`:

```text
quotient, remainder = divmod(N, D)

rounded_quotient = quotient + 1  if 2 * remainder >= D
rounded_quotient = quotient      otherwise
```

The original sign is then applied. The quantized internal rate has exponent `-4`. Calculated
negative zero is normalized to positive zero.

## 13. Calculated output serialization

Calculated output numbers use canonical decimal strings with all of these properties:

- finite only;
- fixed-point notation only;
- no exponent notation;
- no leading `+`;
- no unnecessary leading zeros;
- no trailing fractional zeros;
- no trailing decimal point;
- zero is exactly `"0"`; and
- calculated negative zero becomes `"0"`.

This output policy does not redefine PRODUCT_MASTER input validity or lexical preservation.

## 14. Immutable result value objects

All result carriers are immutable, frozen, slot-based value objects.

`CalculationOutput` has exactly:

```text
name
value
```

Allowed `name` values are `contribution_margin` and `contribution_margin_rate`.

`CalculationInputRef` has exactly:

```text
contract_name
natural_key
source
data_as_of
input_hash
```

`CalculationError` has exactly:

```text
code
field
```

`CalculationResult` has exactly:

```text
metric
formula_version
run_id
sku
status
outputs
input_refs
errors
```

Container semantics are exact: `outputs` is an immutable
`tuple[CalculationOutput, ...]`; `input_refs` is an immutable
`tuple[CalculationInputRef, ...]`; and `errors` is an immutable
`tuple[CalculationError, ...]`. The only statuses are `SUCCESS` and `ERROR`.

## 15. Result shapes

### SUCCESS

- `metric` is `CONTRIBUTION_MARGIN`.
- `formula_version` is `topspeed.calculation.contribution_margin.v1`.
- `run_id` is the validated caller-supplied value.
- `sku` is the validated PRODUCT_MASTER value.
- `status` is `SUCCESS`.
- `outputs` contains exactly, in order, `contribution_margin` and
  `contribution_margin_rate`.
- `input_refs` contains exactly one item.
- `errors` is the empty tuple.

### ERROR

A Calculation-level semantic error result has:

- `metric` equal to `CONTRIBUTION_MARGIN`;
- `formula_version` equal to `topspeed.calculation.contribution_margin.v1`;
- `run_id` equal to the validated caller-supplied value;
- `sku` equal to the validated PRODUCT_MASTER value;
- `status` equal to `ERROR`;
- `outputs` equal to the empty tuple;
- `input_refs` containing exactly one item; and
- `errors` as an ordered, nonempty, immutable tuple.

## 16. Result determinism

Determinism means DETERMINISTIC STRUCTURAL AND VALUE EQUALITY. It does not mean a byte-identical
`CalculationResult`.

This ADR defines no new Business Contract, `CalculationResult` wire protocol, result hash, or
result-wide persisted serialization. For identical validated PRODUCT_MASTER field values,
including exact validated lexical DECIMAL strings, plus an identical formula version and validated
`run_id`, the complete immutable `CalculationResult` must be structurally equal.

Changing only `run_id` leaves numeric outputs, status, errors, and `input_hash` unchanged; only
`CalculationResult.run_id` changes. Lexically distinct but numerically equal DECIMAL strings may
produce identical numeric outputs but must produce different `input_hash` values, so their full
results need not be structurally equal.

## 17. Write-back boundary

`CalculationResult` is internal. The future calculation must not modify or write PRODUCT_MASTER,
DATA_CONTRACT_V1, Contract JSON Schema, the Contract registry, the Data Hub publisher, or existing
PRODUCT_MASTER records.

A negative internal `contribution_margin_rate` is valid. Persisting a negative rate into
PRODUCT_MASTER is not authorized and requires a separate future Architecture decision.

## 18. Explicit exclusions

The following are excluded from this decision:

- CTR, CVR, ROAS, and advertising-after contribution profit;
- time-window aggregation;
- inventory calculations, reorder point, recommended order quantity, and safety stock policy;
- PRODUCT_MASTER write-back;
- Contract or Schema changes;
- database persistence and publisher mutation;
- AI_RUN_LOG writer;
- Audit Layer, Approval Layer, and Execution Layer implementation;
- PHASE 6;
- LIVE/API access and credential access; and
- external business writes.

## 19. Future runtime test obligations

Future runtime implementation is not authorized by this ADR. When separately authorized, tests
must cover at least the following obligations.

The DATA_CONTRACT fixture:

```text
sale_price = 12900
purchase_cost = 5200
fee_rate = 0.108
fulfillment_cost = 2500
expected_return_cost = 350
other_variable_cost = 100

expected contribution_margin = 3356.8
expected contribution_margin_rate = 0.2602
```

Required boundary, semantic, arithmetic, and determinism coverage:

- Contract-valid trailing-zero DECIMAL inputs;
- lexically equivalent values with distinct `input_hash` values;
- exact source lexical preservation;
- Contract-invalid lexical input, wrong type, nonfinite input, and invalid run ID create no result;
- null or omitted formula input produces `MISSING_INPUT`;
- zero `sale_price` produces `ZERO_SALE_PRICE`;
- negative `sale_price` produces `INVALID_INPUT`;
- each negative cost independently produces `INVALID_INPUT`;
- `fee_rate` values 0 and 1 succeed;
- current-Contract out-of-range `fee_rate` is rejected before `CalculationResult`;
- multiple semantic errors aggregate in the fixed field order;
- negative calculated margin and rate succeed;
- exact margin arithmetic and exact 0.0001 rate rounding;
- positive and negative half-way `ROUND_HALF_UP`, below-half-way, and above-half-way cases;
- no double rounding;
- large- and small-coefficient cases;
- ambient Decimal context changes do not alter behavior;
- the global Decimal context remains unchanged;
- immutable carriers and exact SUCCESS output order;
- identical exact input, formula version, and `run_id` give structural equality;
- changing `run_id` changes only `run_id`, and `run_id` is excluded from `input_hash`;
- changing each hash field changes the hash;
- derived PRODUCT_MASTER contribution fields are ignored;
- `source` and `data_as_of` are preserved in `CalculationInputRef`;
- the input record is not mutated;
- no PRODUCT_MASTER write-back, publisher mutation, or external side effect;
- deterministic behavior across Windows and Linux; and
- deterministic behavior across supported Python 3.12 patch versions.

## 20. Phase and finding state

- `P5-A2-F-001`: CLOSED
- `P5-A2-F-002`: CLOSED
- `P5-A2-F-003`: CLOSED
- Human B decision: PRESERVED
- PHASE 4: COMPLETE
- PHASE 5: NOT STARTED
- Runtime implementation: NOT AUTHORIZED

This accepted architecture is the prerequisite for a separate future implementation work order. It
does not itself start PHASE 5 runtime implementation.
