# ADR: PHASE 5 INVENTORY SAFETY STOCK POLICY AUTHORITY PRODUCER V1

- Status: APPROVED ARCHITECTURE; IMPLEMENTATION NOT AUTHORIZED
- Classification: NORMATIVE INTERNAL PHASE 5 ARCHITECTURE DECISION
- Source literal: `topspeed.repository.policy_authority.inventory_safety_stock.v1`
- Policy version: `TOPSPEED_SAFETY_STOCK_POLICY_V1`
- Approval authority: `TOPSPEED Human Architecture Owner`
- Effective datetime: `2026-10-15T16:05:35+09:00`
- Public API expansion: NONE

## 1. Decision and authority

This ADR defines the repository-recognized V1 Architecture for producing the immutable policy
authority consumed by the published Inventory Safety Stock Architecture. It closes residual
producer design choices without implementing the producer, Safety Stock calculation, INVENTORY
materialization, Reorder Point, or any external execution path.

The Human-approved policy remains unchanged:

```text
policy_version = TOPSPEED_SAFETY_STOCK_POLICY_V1
approval_authority = TOPSPEED Human Architecture Owner
authority_status = APPROVED
data_as_of = 2026-10-15T16:05:35+09:00
safety_stock_days = 7
```

The Human Architecture Owner supplied and approved the exact initial policy effective datetime as
`2026-10-15T16:05:35+09:00`. This value is preserved verbatim as `_POLICY_RECORD.data_as_of`.
It is not normalized, converted, truncated, inferred, or replaced by a runtime-derived value.

## 2. Exact Architecture identifiers

The exact source literal is:

```text
topspeed.repository.policy_authority.inventory_safety_stock.v1
```

The exact future record file is:

```text
src/topspeed_ai_os/policy_authority/inventory_safety_stock_v1.py
```

The exact future producer module is:

```text
topspeed_ai_os.policy_authority.inventory_safety_stock_v1
```

The exact internal identifiers are:

```text
private record class = _InventorySafetyStockPolicyRecord
immutable record symbol = _POLICY_RECORD
producer symbol = _produce_inventory_safety_stock_policy_authority
```

The exact producer signature is:

```text
def _produce_inventory_safety_stock_policy_authority(
) -> InventorySafetyStockPolicyAuthority: ...
```

The producer and record symbols are internal. They must not be added to
`topspeed_ai_os.calculation.__all__`, `topspeed_ai_os.policy_authority.__all__`, or package-root
exports. The published Safety Stock six-symbol public API remains unchanged.

## 3. Exact static loading mechanism

The private record and producer reside in the same statically imported Python module. The module
declares exactly one frozen and slotted private record instance named `_POLICY_RECORD`. The
zero-argument producer directly references that module-level record and constructs a new exact
frozen `InventorySafetyStockPolicyAuthority` on every invocation.

Normal Python interpreter loading of the statically named module is not a producer filesystem
lookup or an alternate source authority.

The producer must not return a mutable singleton or use object identity as authority evidence.

The following are forbidden:

- JSON, YAML, TOML, CSV, or database records;
- Drive document, network, or API lookup;
- environment variables;
- `pathlib`, `open`, or `os` filesystem access;
- `importlib`, dynamic module selection, or package-resource loading;
- caller-supplied paths or records;
- callbacks or registry selection;
- fallback records;
- current time or generated IDs; and
- mutable caches.

## 4. Exact immutable record

The future private record is exactly:

```python
@dataclass(frozen=True, slots=True)
class _InventorySafetyStockPolicyRecord:
    policy_version: str
    approval_authority: str
    authority_reference: str
    authority_status: str
    source: str
    data_as_of: str
    safety_stock_days: int
    input_hash: str
```

Fields are exact and in the displayed order. No field is nullable. No additional field,
`InitVar`, hidden field, alternate record class, Mapping representation, or subtype is permitted.

The exact fixed values are:

```text
policy_version = TOPSPEED_SAFETY_STOCK_POLICY_V1
approval_authority = TOPSPEED Human Architecture Owner
authority_reference = TOPSPEED_SAFETY_STOCK_POLICY_V1
authority_status = APPROVED
source = topspeed.repository.policy_authority.inventory_safety_stock.v1
safety_stock_days = exact built-in int 7
```

`data_as_of` is the exact Human-approved policy effective datetime represented as the canonical,
timezone-bearing ISO-8601 built-in string `2026-10-15T16:05:35+09:00`. The future record must use
this value verbatim. The Builder must not change, normalize, convert to UTC, truncate, derive, or
substitute it. No `effective_datetime` field is introduced.

`input_hash` is the exact existing canonical lowercase value matching
`^sha256:[0-9a-f]{64}$`, calculated from the seven non-hash fields under Section 5.

## 5. Exact hash contract

Hashing reuses exactly `topspeed_ai_os.core.canonical.payload_sha256` and existing
`canonical_json` behavior. The primitive payload is exactly:

```text
{
    "policy_version": record.policy_version,
    "approval_authority": record.approval_authority,
    "authority_reference": record.authority_reference,
    "authority_status": record.authority_status,
    "source": record.source,
    "data_as_of": record.data_as_of,
    "safety_stock_days": record.safety_stock_days,
}
```

The exact key order is:

1. `policy_version`
2. `approval_authority`
3. `authority_reference`
4. `authority_status`
5. `source`
6. `data_as_of`
7. `safety_stock_days`

The stored record hash must equal `payload_sha256(payload)`.

Forbidden hash content is:

- `input_hash` itself;
- calculation `run_id`;
- `safety_stock_qty` or `avg_daily_units`;
- `lead_time_days` or the standard reference value `14`;
- wall-clock or Git commit time;
- filesystem metadata; and
- output or result fields.

No second digest or alternate canonicalizer is permitted.

## 6. Exact producer contract

The future producer takes zero arguments. It reads no mutable or external state. On every
invocation it validates the exact module-level `_POLICY_RECORD`, constructs a new exact
`InventorySafetyStockPolicyAuthority`, verifies the returned projection, and returns that frozen
carrier.

The producer does not calculate Safety Stock, supply `avg_daily_units`, create a run ID, consult
INVENTORY, choose an effective datetime, or establish approval on behalf of the Human owner.

## 7. Exact producer validation precedence

The producer validates in exactly this order:

1. Require `_POLICY_RECORD` exact class identity.
2. Require the private record dataclass exact fields and order.
3. Require `policy_version` exact built-in `str`.
4. Require `policy_version` exact approved literal.
5. Require `approval_authority` exact built-in `str`.
6. Require `approval_authority` exact approved literal.
7. Require `authority_reference` exact built-in `str`.
8. Require `authority_reference` exact approved literal.
9. Require `authority_status` exact built-in `str`.
10. Require `authority_status` exact `APPROVED`.
11. Require `source` exact built-in `str`.
12. Require `source` non-empty and exact approved source literal.
13. Require `data_as_of` exact built-in `str`.
14. Require `data_as_of` real, timezone-aware, and lexically canonical.
15. Require `safety_stock_days` exact built-in `int`.
16. Require `safety_stock_days` exact integer `7`.
17. Require `input_hash` exact built-in `str`.
18. Require `input_hash` canonical sha256 lexical form.
19. Recompute the policy hash from the exact primitive payload.
20. Require stored and recomputed hash equality.
21. Construct the exact `InventorySafetyStockPolicyAuthority`.
22. Require returned carrier identity and every projected field to equal the validated record.
23. Return the newly constructed frozen carrier.

A failure stops all lower-precedence validation.

## 8. Exact exception contract

The exact exception mapping is:

- Steps 1, 2, 3, 5, 7, 9, 11, 13, 15, and 17: `TypeError`.
- Steps 4, 6, 8, and 10: `ValueError`.
- Step 12: `ValueError`.
- Step 14: `ValueError`.
- Step 16: `ValueError`.
- Step 18: `ValueError`.
- Step 19: existing `canonical_json` or `payload_sha256` `TypeError` or `ValueError`
  propagates unchanged.
- Step 20: `ValueError`.
- Step 21: existing `InventorySafetyStockPolicyAuthority` constructor `TypeError` or
  `ValueError` propagates unchanged.
- Step 22 wrong carrier identity: `TypeError`.
- Step 22 projected-field or coherence mismatch: `ValueError`.

No exception may be wrapped, translated, suppressed, replaced, converted into a result, repaired,
normalized, coerced, or replaced by a fallback policy.

## 9. Effective datetime evidence and dependency gate

The exact initial policy effective datetime prerequisite is satisfied by Human evidence. The
approved value is exactly:

```text
_POLICY_RECORD.data_as_of = "2026-10-15T16:05:35+09:00"
```

Human evidence satisfies only the effective-datetime prerequisite. `P5-ISS-DEP-A1-F-001` remains
open until Policy Authority Producer implementation, audit, publication, and exact-SHA CI closure.
The evidence does not authorize implementation and does not close that dependency.

Codex, the future Builder, and the future producer must not replace or derive the value from:

- current time;
- the Human approval-message time;
- ADR creation or commit time;
- publication or CI time;
- file modification time; or
- any other inferred timestamp.

The approved `data_as_of` is fixed V1 record evidence, not a caller input, environment value,
fallback timestamp, or unfinished Builder Architecture choice.

## 10. Authority meaning

Direct construction of a structurally valid `InventorySafetyStockPolicyAuthority` does not
establish production authority. The approved producer defined by this ADR is the sole
repository-recognized production construction path.

Production provenance is demonstrated by:

- the exact record module path;
- exact immutable record identity;
- exact canonical record content;
- stored and recomputed hash equality;
- exact producer implementation path;
- deterministic producer tests; and
- future production-wiring allowlist evidence.

Do not add an origin token, secret or hidden carrier field, process-local identity check, mutable
registry, runtime filesystem proof, callback, unsupported cryptographic claim, or additional
public carrier field.

## 11. Immutable version lifecycle and Human ownership

`TOPSPEED_SAFETY_STOCK_POLICY_V1` and its `_POLICY_RECORD` are immutable. The future implementation
must not mutate or replace the record after module loading. Runtime input, environment state, a
caller, or the producer cannot revise any record field.

A change to the policy version, approved literals, effective datetime, source identity, or record
content requires separate Human approval and a separate Architecture, implementation, audit, and
publication path. No change is applied in place under the existing V1 identity.

`TOPSPEED Human Architecture Owner` is the exact approval owner for the policy record and exact
effective datetime. The producer validates and projects approved evidence; it does not create or
delegate approval authority.

## 12. Canonical carrier foundation sequencing

The canonical future implementation home is exactly:

```text
src/topspeed_ai_os/calculation/inventory_safety_stock.py
```

The canonical carrier class is exactly:

```text
topspeed_ai_os.calculation.inventory_safety_stock.InventorySafetyStockPolicyAuthority
```

The future separately authorized Producer implementation Slice may establish this exact carrier
foundation at that module path because the producer return annotation and returned object must
resolve to that exact canonical class identity. The carrier semantics are not reopened. The
foundation must preserve the already approved exact class name, fields, field order, scalar types,
nullability, frozen and slotted semantics, constructor invariants, and canonical lexical
requirements. No alternate or duplicate carrier is permitted.

During that future Producer implementation Slice, `topspeed_ai_os.calculation.__all__` must remain
unchanged. `InventorySafetyStockPolicyAuthority` may exist in
`topspeed_ai_os.calculation.inventory_safety_stock` as the single canonical implementation
identity, but it must not yet be exposed through package-level public exports. The producer must
import and return that exact class, and `type(produced_authority) is
InventorySafetyStockPolicyAuthority` must hold.

Before the separately authorized Safety Stock runtime Slice, none of the following six symbols may
be exposed through `topspeed_ai_os.calculation.__all__`:

1. `INVENTORY_SAFETY_STOCK_FORMULA_VERSION`
2. `InventorySafetyStockPolicyAuthority`
3. `InventorySafetyStockInputRef`
4. `InventorySafetyStockOutput`
5. `InventorySafetyStockResult`
6. `calculate_inventory_safety_stock`

The future Safety Stock runtime Slice must reuse the already-created canonical
`InventorySafetyStockPolicyAuthority` without redefining, moving, wrapping, subclassing, or
replacing it. That Slice must implement the remaining approved Safety Stock runtime symbols and
expose all six symbols atomically, preserve all existing Calculation exports in their existing
order, and add no seventh Safety Stock public symbol.

The following are forbidden during the Producer foundation Slice:

- a second carrier definition or duplicate dataclass;
- a protocol, Mapping, compatibility-wrapper, or subclass substitute;
- dynamic carrier construction;
- re-export from `topspeed_ai_os.policy_authority`;
- modification of `topspeed_ai_os.calculation.__all__`; and
- partial Safety Stock package API activation.

## 13. Public API and Contract boundary

This producer and its record remain internal. No symbol is added to public `__all__` exports or the
package root. The published Inventory Safety Stock public API remains exactly six symbols and is
not reopened.

This Architecture requires no Data Contract definition, JSON Schema, registry, Frozen
Architecture, Implementation Plan, Migration Matrix, handoff document, configuration, dependency,
or workflow change.

The producer's output is the already approved exact
`InventorySafetyStockPolicyAuthority`; no additional public field, carrier, result, token, or
authority proof is introduced.

## 14. Pure side-effect boundary

The future producer performs no:

- filesystem, database, Drive, network, or API lookup;
- environment or credential access;
- clock access or timestamp inference;
- ID or random-value generation;
- mutable caching or registry mutation;
- Contract, Schema, or record mutation;
- INVENTORY or PRODUCT_MASTER write-back;
- APPROVAL_QUEUE or AI_RUN_LOG persistence;
- Safety Stock calculation;
- supplier lead-time lookup or calculation;
- Inventory Stock Days, Reorder Point, or Recommended Order Quantity calculation; or
- external business write.

## 15. Future producer implementation test obligations

A separately authorized producer implementation work order must test:

- the exact file and module path;
- exact internal symbol names and zero-argument signature;
- no public export expansion;
- exact frozen and slotted record fields, order, and types;
- absence of nullable, hidden, alternate, Mapping, and `InitVar` state;
- all exact fixed literals;
- exact built-in scalar enforcement and subclass rejection;
- bool rejection for `safety_stock_days`;
- exact approved `2026-10-15T16:05:35+09:00` `data_as_of` acceptance;
- naive, malformed, noncanonical, and substituted datetime rejection;
- the exact payload key set and order;
- stored and recomputed hash equality;
- tampered record and hash rejection;
- exact 23-step fail-closed precedence;
- exact exception mapping and unchanged exception propagation;
- a newly constructed exact frozen carrier on every invocation;
- exact record-to-carrier field projection;
- deterministic structural equality across repeated calls;
- no singleton identity claim;
- no dynamic loading or external lookup;
- no environment, clock, filesystem, network, ID, or mutable-cache access;
- no Contract, Schema, registry, config, or workflow change;
- no Safety Stock, supplier lead-time, Reorder Point, or Recommended Order Quantity behavior;
- full existing repository and Calculation regression suites;
- Ruff check and format check;
- strict UTF-8, no BOM, final newline, and no trailing whitespace;
- no skip, skipif, xfail, deleted test, or weakened assertion;
- exact changed-path scope; and
- sensitive-material scan.

The effective-datetime prerequisite is satisfied by Human evidence. Tests and implementation
remain not authorized until a separate implementation work order is approved.

## 16. Runtime and downstream prohibitions

This ADR does not authorize:

- producer implementation or producer tests;
- Safety Stock runtime, tests, or publication;
- INVENTORY `safety_stock_qty` materialization;
- Reorder Point runtime;
- supplier-contract or `lead_time_days` work;
- Recommended Order Quantity;
- purchase approval or execution;
- Phase completion; or
- PHASE 6 work.

Publication of this docs-only ADR does not satisfy the producer implementation prerequisite. Even
future producer publication does not by itself authorize Safety Stock runtime or establish the
Reorder Point materialization path.

## 17. Explicit non-decisions

This ADR does not decide:

- future policy versions or their record identities;
- production wiring or allowlist implementation;
- producer implementation details beyond this exact Architecture;
- supplier-contract source format or verification;
- `lead_time_days`;
- INVENTORY `safety_stock_qty` materialization;
- Safety Stock calculation implementation;
- Reorder Point or Recommended Order Quantity runtime;
- dashboards, notifications, UI, or LIVE connectors; or
- PHASE 6 work.

Each requires its own evidence or Architecture Gate.

## 18. Finding reconciliation

```text
P5-ISSPA-WO-A2-F-001 = CLOSED
P5-ISSPA-WO-A2-F-002 = CLOSED
P5-ISS-DEP-A1-F-001 = OPEN
  effective-datetime prerequisite = SATISFIED BY HUMAN EVIDENCE
  exact approved data_as_of = 2026-10-15T16:05:35+09:00
  closure condition = POLICY AUTHORITY PRODUCER IMPLEMENTATION, AUDIT, PUBLICATION,
    AND EXACT-SHA CI CLOSURE
P5-ISSPA-DEP-A1-F-002 = CLOSED BY CORRECTED CARRIER-SEQUENCING ARCHITECTURE
P5-ISSPA-SEQ-A2-F-001 = CLOSED
  final Human data_as_of = 2026-10-15T16:05:35+09:00
P5-ISSPA-SEQ-A2-F-002 = CLOSED
  exact field = data_as_of
P5-ISSPA-SEQ-A2-F-003 = CLOSED
  complete Producer dependency remains OPEN
Residual Builder Architecture choice = NONE
Additional Human effective-datetime evidence required = NO
New Human policy decision required = NO
```

## 19. Phase and authorization state

```text
PHASE 4 = COMPLETE
PHASE 5 = NOT COMPLETE
PHASE 6 = NOT STARTED

Policy Authority Producer Architecture = APPROVED
Policy Authority Producer docs-only ADR = AUTHORIZED
Effective-datetime prerequisite = SATISFIED BY HUMAN EVIDENCE
Policy Authority Producer implementation Work Order = NOT AUTHORIZED
Policy Authority Producer implementation = NOT AUTHORIZED
Safety Stock runtime = NOT AUTHORIZED
INVENTORY materialization = NOT AUTHORIZED
Reorder Point runtime = NOT AUTHORIZED
Recommended Order Quantity = NOT AUTHORIZED
```
