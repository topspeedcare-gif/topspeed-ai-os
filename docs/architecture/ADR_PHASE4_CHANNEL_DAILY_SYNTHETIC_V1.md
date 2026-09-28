# ADR: PHASE 4 CHANNEL_DAILY synthetic v1

- Status: Accepted for PHASE 4 synthetic Architecture-proof scope
- Schema: `topspeed.channel_daily.synthetic.v1`
- Target: `CHANNEL_DAILY`
- Formula version: `synthetic.v1`

## Decision

For this synthetic Architecture-proof slice only:

`net_sales = gross_sales - refund_amount`

Both inputs first pass the authoritative canonical DECIMAL validation. The derivation uses exact
Python `Decimal` subtraction with no rounding. Its result uses a synthetic-v1-local deterministic
serialization: fixed-point notation, no insignificant trailing zero or dangling decimal point, and
negative zero normalized to `0`. Negative `net_sales` is allowed.

The stable provenance formula rule is:

`derive_net_sales:gross_sales-refund_amount@synthetic.v1`

## Scope and change policy

Production claims: **NONE**. This decision does not define marketplace settlement, tax, discount,
cancellation, refund-attribution, or PHASE 5 Calculation Engine semantics.

Global DECIMAL semantics changed: **NO**. The serialization rule is local to
`topspeed.channel_daily.synthetic.v1`; repository-wide canonicalization and existing AD_DAILY
DECIMAL behavior are unchanged.

`metric_version` is not generated because it is absent from the committed CHANNEL_DAILY schema.
A formula or aggregation-semantics change requires either
`topspeed.channel_daily.synthetic.v2` or a separate Architecture/Data Contract Gate. The meaning of
synthetic v1 must not change silently.

This ADR neither modifies nor reinterprets Frozen documents. Frozen modifications: 0. HANDOFF
modifications: 0. Workflow modifications: 0.
