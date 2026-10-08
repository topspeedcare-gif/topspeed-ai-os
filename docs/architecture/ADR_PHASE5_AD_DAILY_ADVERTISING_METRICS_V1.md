# ADR: PHASE 5 AD_DAILY advertising metrics v1

- Status: Accepted architecture; runtime implementation not authorized
- Classification: NORMATIVE INTERNAL PHASE 5 ARCHITECTURE DECISION
- Architecture: PHASE 5 AD_DAILY ADVERTISING METRICS V1
- Metric family: AD_DAILY_ADVERTISING_METRICS
- Formula version: topspeed.calculation.ad_metrics.v1
- Human Architecture decision: H1 / A / BUSINESS-STRICT

## 1. Decision and authority

This ADR records the already-approved PHASE 5 Architecture for deterministic CTR, CVR, and ROAS
calculation from one existing AD_DAILY record. It is documentation only. It does not authorize
runtime code, tests, persistence, publication, an external write, another Calculation slice, or a
PHASE 5 completion declaration.

The existing Data Contract, machine-readable Schema, Contract registry, Core run-ID authority,
canonical hashing authority, and canonical DECIMAL parser remain authoritative. This ADR changes
none of them and introduces no new Human Architecture choice.

## 2. Pure runtime boundary and public entry point

The future calculation receives exactly:

1. one existing Contract-valid AD_DAILY record; and
2. one caller-supplied calculation run_id.

The AD_DAILY record's existing run_id is ingestion provenance. The caller-supplied run_id is
calculation provenance. They are separate values. The calculation preserves the validated caller
value and must reuse topspeed_ai_os.core.ids.require_valid_run_id; it must not generate,
normalize, repair, or replace an identifier.

The future public entry point is:

~~~python
def calculate_ad_daily_metrics(
    ad_daily: Mapping[str, object],
    *,
    run_id: str,
    formula_version: str = AD_METRICS_FORMULA_VERSION,
) -> AdvertisingMetricsResult: ...
~~~

The only supported formula version is topspeed.calculation.ad_metrics.v1. There is no dynamic
formula selection, caller-provided expression, Calculation ID, clock, callback, publisher, or
persistence dependency.

## 3. Exact boundary precedence

The runtime order is fixed:

1. verify that ad_daily is a Mapping;
2. validate it through the existing AD_DAILY Contract boundary;
3. validate the caller-supplied calculation run_id;
4. verify exact formula_version equality;
5. construct the input reference and Calculation input_hash;
6. perform primitive BUSINESS-STRICT validation;
7. perform cross-field validation;
8. detect zero denominators; and
9. perform arithmetic only for defined metrics.

Failures at steps 1 through 4 create no AdvertisingMetricsResult. Existing Contract and run-ID
exceptions propagate and are not translated into Calculation-level errors. An unsupported formula
version also fails closed before a result exists.

After the validated boundary, every Calculation-semantic outcome contains exactly one input
reference. Primitive errors stop cross-field checks, zero-denominator checks, and arithmetic.
Cross-field errors stop zero-denominator checks and arithmetic. This precedence is normative.

## 4. Formula identity and derived-field exclusion

The formulas are:

~~~text
ctr = clicks / impressions
cvr = ad_orders / clicks
roas = ad_revenue / ad_spend
~~~

CTR and CVR are ratios, not percentages.

Existing AD_DAILY ctr, cvr, and roas fields are derived values. They are not calculation inputs,
reconciliation authorities, input_hash inputs, or write-back targets. A future implementation
must calculate only from the approved primitive inputs and must ignore changes to those existing
derived fields.

## 5. H1 primitive BUSINESS-STRICT policy

After Contract validation, the Calculation-level policy is:

~~~text
impressions >= 0
clicks >= 0
ad_spend >= 0
ad_orders >= 0
ad_revenue >= 0
~~~

The existing canonical DECIMAL parser is used for Contract-valid ad_spend and ad_revenue strings
during semantic validation. Parsing must not replace, normalize, or reserialize the source strings
used by input_hash.

Primitive validation order is exactly:

1. impressions;
2. clicks;
3. ad_spend;
4. ad_orders; and
5. ad_revenue.

Every primitive violation is collected in that order and produces:

~~~text
code = INVALID_INPUT
metric = None
field = exact offending primitive field
~~~

Any primitive violation produces status ERROR, outputs (), and an ordered nonempty error tuple.
Cross-field rules, zero denominators, and arithmetic are not evaluated after a primitive error
exists. This semantic policy does not alter the Data Contract or Schema.

## 6. Cross-field policy

Only after all primitive validation passes, evaluate exactly:

1. clicks <= impressions; and
2. ad_orders <= clicks.

If clicks > impressions, return:

~~~text
code = INVALID_INPUT
metric = ctr
field = clicks/impressions
~~~

If ad_orders > clicks, return:

~~~text
code = INVALID_INPUT
metric = cvr
field = ad_orders/clicks
~~~

If both violations exist, collect both in the order shown. Any cross-field violation produces
status ERROR and outputs (). Zero-denominator evaluation and arithmetic are not performed.

## 7. Status and zero-denominator contract

The only statuses are SUCCESS, PARTIAL, and ERROR:

- SUCCESS means all three metrics are defined and calculated.
- PARTIAL means primitive and cross-field validation passed, but at least one metric is undefined
  solely because its denominator is numeric zero.
- ERROR means at least one primitive or cross-field INVALID_INPUT violation exists.

Zero denominators are Calculation-level undefined-metric outcomes, not Contract failures and not
INVALID_INPUT:

| Condition | Error code | Metric | Field |
| --- | --- | --- | --- |
| impressions == 0 | ZERO_DENOMINATOR | ctr | impressions |
| clicks == 0 | ZERO_DENOMINATOR | cvr | clicks |
| ad_spend == numeric zero | ZERO_DENOMINATOR | roas | ad_spend |

Zero-denominator errors are ordered ctr, cvr, roas. PARTIAL returns only defined outputs, in the
canonical relative order ctr, cvr, roas. If all three denominator conditions are reached, the
result is PARTIAL with outputs () and three ordered ZERO_DENOMINATOR errors.

Earlier precedence is absolute. For example, impressions == 0 and clicks > 0 violates
clicks <= impressions. It is ERROR for the cross-field rule; zero-denominator evaluation is never
reached and the result must not be reclassified as PARTIAL.

## 8. Exact rational rounding for CTR and CVR

Every calculated metric uses quantum 0.0001 and ROUND_HALF_UP. Ordinary finite-precision Decimal
division is not the algorithm.

For an exact nonnegative ratio A / B with B > 0:

~~~text
scaled_numerator = A * 10000
q, r = divmod(scaled_numerator, B)

if 2 * r >= B:
    q += 1
~~~

The rounded result is represented exactly with coefficient q and exponent -4.

For CTR:

~~~text
A = clicks
B = impressions
~~~

For CVR:

~~~text
A = ad_orders
B = clicks
~~~

The integer arithmetic is arbitrary precision. There is no intermediate rounding, double
rounding, ambient Decimal precision dependency, or ambient rounding-mode dependency.

## 9. Exact ROAS rational construction

For exact parsed canonical DECIMAL values:

~~~text
ad_revenue = Cr * 10^Er
ad_spend = Cs * 10^Es
delta = Er - Es
~~~

After primitive and denominator validation, Cr >= 0 and Cs > 0. Construct the exact rational:

~~~text
if delta >= 0:
    A = Cr * 10^delta
    B = Cs
else:
    A = Cr
    B = Cs * 10^(-delta)
~~~

Apply the exact quotient/remainder rounding rule from the preceding section. Coefficients are
arbitrary-precision integers and must not be truncated. The calculation must not use
finite-precision Decimal division, mutate the global Decimal context, accept ambient context
state, or retry after an inexact intermediate result.

Contract-valid negative zero is numeric zero. It is a zero denominator when supplied as ad_spend.
Numeric-zero ad_revenue with positive ad_spend produces canonical output "0".

## 10. Canonical output serialization

Calculated metric values use canonical fixed-point strings:

- no exponent notation;
- at most four fractional digits;
- no unnecessary fractional trailing zeros;
- no trailing decimal point;
- numeric zero is exactly "0"; and
- calculated negative zero is exactly "0".

Thus internal values corresponding to 0.5000, 1.0000, and 0.0000 serialize as "0.5", "1", and
"0". This output policy does not normalize source AD_DAILY DECIMAL strings before input hashing.

## 11. Immutable public carriers

This slice defines separate advertising metric carriers:

- AdvertisingMetricOutput;
- AdvertisingMetricsInputRef;
- AdvertisingMetricsError; and
- AdvertisingMetricsResult.

It does not alter or generalize Contribution Margin carriers. Every carrier is a
dataclass(frozen=True, slots=True). Future constructor validation must enforce the exact runtime
types and whole-result invariants below. It must not coerce mutable containers, normalize invalid
constructor values, retain arbitrary mutable state, or accept subclasses when exact class identity
is required.

## 12. AdvertisingMetricOutput contract

Fields are exactly, in order:

~~~text
metric
value
~~~

Both fields are exact built-in str values. metric is exactly one of ctr, cvr, or roas. value is the
canonical nonnegative calculated representation defined by this ADR. Lists, dictionaries, sets,
bytearrays, mutable-state str subclasses, and other non-exact strings are rejected rather than
converted.

## 13. AdvertisingMetricsInputRef contract

Fields are exactly, in order:

~~~text
contract_name
natural_key
source
data_as_of
input_hash
~~~

contract_name is the exact built-in string AD_DAILY. source, data_as_of, and input_hash are exact
built-in strings.

natural_key is an exact built-in tuple of exactly five elements:

~~~text
(
    channel,
    stat_date,
    sku,
    campaign_id,
    ad_group_id,
)
~~~

The first four elements are exact built-in strings. The fifth is either an exact built-in string
or None. A missing ad_group_id remains None; it is not replaced with an empty string.

Lists, dictionaries, sets, generators, bytearrays, tuple subclasses, invalid element types, and
invalid tuple lengths are rejected without conversion.

## 14. AdvertisingMetricsError contract

Fields are exactly, in order:

~~~text
code
metric
field
~~~

code is an exact built-in string and is exactly INVALID_INPUT or ZERO_DENOMINATOR. metric is None
or an exact built-in string. field is an exact built-in string.

Reachability constrains error values:

- primitive INVALID_INPUT has metric None and its exact primitive field;
- cross-field INVALID_INPUT has metric ctr or cvr and field clicks/impressions or
  ad_orders/clicks, respectively; and
- ZERO_DENOMINATOR has metric ctr, cvr, or roas with field impressions, clicks, or ad_spend,
  respectively.

Mutable or non-exact scalar values are rejected. Constructor validation must not create new error
semantics beyond these reachable states.

## 15. AdvertisingMetricsResult contract and whole-result invariants

Fields are exactly, in order:

~~~text
metric_family
formula_version
run_id
sku
status
outputs
input_refs
errors
~~~

The five scalar fields are exact built-in strings. metric_family is fixed to
AD_DAILY_ADVERTISING_METRICS, formula_version is fixed to topspeed.calculation.ad_metrics.v1, and
status is exactly SUCCESS, PARTIAL, or ERROR.

The container types are exact:

- outputs is an exact built-in tuple of exact AdvertisingMetricOutput instances;
- input_refs is an exact built-in tuple of exact AdvertisingMetricsInputRef instances; and
- errors is an exact built-in tuple of exact AdvertisingMetricsError instances.

No list, dictionary, set, generator, bytearray, tuple subclass, or wrong nested carrier type is
accepted or converted. Every result has exactly one input reference whose contract_name is
AD_DAILY.

Every runtime-produced SUCCESS, PARTIAL, and ERROR result sets run_id to the exact validated
caller-supplied calculation run_id and sku to the exact validated AD_DAILY sku. The AD_DAILY
record run_id remains ingestion provenance only and is never copied into result.run_id.

For every AdvertisingMetricsResult, result.sku equals
result.input_refs[0].natural_key[2]. The sole input reference natural key is ordered channel,
stat_date, sku, campaign_id, ad_group_id, so natural_key[2] is the validated AD_DAILY sku. A
directly constructed result whose sku does not equal input_refs[0].natural_key[2] is an invalid
whole-result state and fails closed; it is rejected without SKU normalization, rewriting,
automatic correction, or constructor coercion. No direct-constructor cross-object run-ID invariant
is required because a standalone result constructor has no independent caller-run object against
which runtime provenance can be proven.

SUCCESS has exactly three outputs, ordered ctr, cvr, roas, and errors (). PARTIAL has one or more
ordered ZERO_DENOMINATOR errors and contains only defined outputs in canonical relative order. Its
output metric set and error metric set are disjoint, and their union is exactly
{ctr, cvr, roas}. ERROR has outputs () and an ordered, nonempty tuple containing only
INVALID_INPUT errors.

INVALID_INPUT and ZERO_DENOMINATOR never coexist in one result. Invalid direct-constructor states
fail closed. Valid result graphs remain deeply immutable: carrier fields cannot be reassigned,
new attributes cannot be added, tuple items cannot be replaced, and nested carriers expose no
mutable approved field state.

## 16. Natural key

The exact AD_DAILY natural key is:

~~~text
(
    channel,
    stat_date,
    sku,
    campaign_id,
    ad_group_id,
)
~~~

It excludes campaign_name, source_file_hash, both run IDs, created_at, and every calculated
metric. A missing ad_group_id is represented by None and is never substituted with an empty
string.

## 17. Calculation input hash

The exact Calculation input_hash key set is:

~~~text
channel
stat_date
sku
campaign_id
ad_group_id
impressions
clicks
ad_spend
ad_orders
ad_revenue
source_file_hash
source
data_as_of
~~~

The future implementation reuses the existing canonical JSON and
topspeed_ai_os.core.canonical.payload_sha256 authorities. The exact validated lexical source
strings are preserved for ad_spend and ad_revenue. Missing ad_group_id and source_file_hash values
project to explicit JSON null.

No parsed Decimal is serialized back into the hash payload. Contract-valid values such as "10",
"10.0", and "10.00" may produce equal metrics but must produce distinct input hashes.

The input hash excludes exactly:

- the AD_DAILY ingestion run_id;
- the caller calculation run_id;
- created_at;
- campaign_name;
- ad_units;
- existing ctr;
- existing cvr;
- existing roas; and
- formula_version.

Changing only an excluded field has no effect on input_hash, status, outputs, or errors, except
that changing the caller calculation run_id changes only AdvertisingMetricsResult.run_id.

## 18. Input reference

Every Calculation-semantic result contains exactly one AdvertisingMetricsInputRef:

~~~text
contract_name = AD_DAILY
natural_key = exact five-element AD_DAILY natural key
source = exact validated AD_DAILY source
data_as_of = exact validated AD_DAILY data_as_of
input_hash = exact Calculation input hash
~~~

The implementation must not substitute current time, calculation time, fetch time, wall-clock
state, a generic source label, or a generated timestamp.

## 19. Determinism and side-effect boundary

For identical validated AD_DAILY values, caller calculation run_id, and formula_version, repeated
calls produce structurally and value-equal results for:

- status;
- outputs and output ordering;
- input references;
- errors and error ordering;
- input_hash; and
- canonical output strings.

No complete byte serialization, result-wide hash, or persisted wire protocol is defined.

The calculation is pure deterministic code. It performs no filesystem access or mutation,
database access, environment-variable access, credential access, network or external API access,
wall-clock access, randomness, ID generation, LLM numeric calculation, AD_DAILY mutation or
write-back, persistence, publisher mutation, or external business write.

## 20. Existing Architecture non-interference

This decision neither redefines nor generalizes the existing Contribution Margin slice. It does
not alter its formula version, constants, public API, carrier classes, Decimal algorithm, output
contract, or tests.

The AD_DAILY Data Contract and Schema remain unchanged. In particular, existing derived ctr, cvr,
and roas fields remain part of AD_DAILY but have no authority inside this calculation. No
PRODUCT_MASTER linkage or join is introduced.

## 21. Future runtime test obligations

Runtime implementation is not authorized by this ADR. A separately authorized implementation must
test all of the following:

### 21.1 Boundary and precedence

- non-Mapping input;
- existing AD_DAILY Contract failures, including wrong shape and invalid primitive types;
- invalid caller calculation run_id;
- unsupported formula_version;
- exact boundary precedence and absence of AdvertisingMetricsResult for boundary failures;
- exactly one input reference for every Calculation-semantic result;
- primitive single violations for all five fields;
- multiple primitive violations with complete exact ordering;
- proof that primitive errors stop later validation and arithmetic;
- each cross-field violation independently;
- both cross-field violations with exact ordering;
- proof that cross-field errors stop denominator checks and arithmetic; and
- impressions == 0 with clicks > 0 producing cross-field ERROR rather than PARTIAL.

### 21.2 Statuses, denominators, and arithmetic

- exact SUCCESS, PARTIAL, and ERROR shapes;
- every reachable zero-denominator combination;
- defined-output filtering and canonical relative ordering;
- ordered ctr, cvr, roas ZERO_DENOMINATOR errors;
- all three denominators zero with PARTIAL, outputs (), and three errors;
- hand-calculated CTR, CVR, and ROAS fixtures;
- ROUND_HALF_UP exact ties;
- values immediately below and above each rounding tie;
- no finite-precision or double rounding;
- very large integer coefficients;
- large positive and negative DECIMAL exponent deltas;
- arbitrary-precision exact ROAS rational construction;
- ambient Decimal precision mutation;
- ambient Decimal rounding mutation;
- proof of no global Decimal context mutation;
- source and calculated negative zero behavior; and
- canonical fixed-point output serialization.

For all eight boolean combinations of impressions denominator zero/nonzero, clicks denominator
zero/nonzero, and ad_spend denominator zero/nonzero, tests must construct inputs that respect
earlier semantic precedence or explicitly assert the earlier ERROR. A denominator pattern never
overrides primitive or cross-field invalidity.

### 21.3 Carrier construction and deep immutability

- exact public carrier field names and order;
- valid direct construction for every carrier;
- exact built-in string enforcement;
- mutable str subclass rejection where exact str is required;
- list, dictionary, set, and bytearray injection rejection;
- generator injection rejection;
- tuple subclass rejection;
- exact tuple length and element validation;
- wrong nested carrier type rejection;
- direct construction with result.sku unequal to input_refs[0].natural_key[2] failing closed through
  the public carrier constructor;
- every whole-result invariant for SUCCESS, PARTIAL, and ERROR;
- rejection of mixed INVALID_INPUT and ZERO_DENOMINATOR errors;
- field reassignment rejection;
- new attribute assignment rejection;
- tuple item replacement rejection; and
- nested carrier immutability.

### 21.4 Hashing, determinism, and side effects

- sensitivity to each of the 13 exact input-hash fields;
- non-interference from every excluded field;
- "10", "10.0", and "10.00" producing distinct hashes;
- explicit JSON null for missing ad_group_id and source_file_hash;
- exact five-element natural key, including None ad_group_id;
- existing derived ctr, cvr, and roas non-interference;
- ingestion run_id and calculation run_id separation;
- caller run_id exclusion from input_hash;
- SUCCESS preserving the exact validated caller-supplied calculation run_id through the public
  runtime calculation entry point;
- PARTIAL preserving the exact validated caller-supplied calculation run_id through the public
  runtime calculation entry point;
- ERROR preserving the exact validated caller-supplied calculation run_id through the public
  runtime calculation entry point;
- SUCCESS preserving the exact validated AD_DAILY sku through the public runtime calculation entry
  point;
- PARTIAL preserving the exact validated AD_DAILY sku through the public runtime calculation entry
  point;
- ERROR preserving the exact validated AD_DAILY sku through the public runtime calculation entry
  point;
- every runtime-produced result satisfying result.sku ==
  result.input_refs[0].natural_key[2];
- deterministic replay and structural equality;
- input AD_DAILY mapping non-mutation;
- absence of AD_DAILY write-back, persistence, publisher mutation, external access, and other side
  effects; and
- complete existing Contribution Margin regression preservation.

## 22. Explicit exclusions

This Architecture does not include:

- CHANNEL_DAILY conversion_rate;
- inventory days, reorder point, recommended order quantity, or inventory policy;
- advertising-after contribution profit;
- PRODUCT_MASTER linkage or join;
- AD_DAILY write-back;
- Contract, Schema, or registry modification;
- Coupang API or any other external ingestion;
- dashboard, Slack, or Discord integration;
- Approval or Execution behavior;
- Contribution Margin API or carrier modification;
- PHASE 6;
- another Calculation slice; or
- a PHASE 5 completion declaration.

## 23. Phase and authorization state

- Human Architecture decision H1 / A / BUSINESS-STRICT: PRESERVED
- PHASE 4: COMPLETE
- PHASE 5: NOT COMPLETE
- Runtime implementation: NOT AUTHORIZED
- Test implementation: NOT AUTHORIZED
- Publication: NOT AUTHORIZED
- Residual Builder choice within this ADR: NONE

This accepted Architecture is a prerequisite for a separate future runtime implementation work
order. This ADR does not itself start that implementation and does not select the next slice.
