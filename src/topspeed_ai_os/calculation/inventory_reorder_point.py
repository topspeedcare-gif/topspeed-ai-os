"""Private Safety Stock projection foundation for a future Reorder Point slice."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Literal

from topspeed_ai_os.calculation.inventory_demand_velocity import InventoryDemandVelocityInputRef
from topspeed_ai_os.calculation.inventory_safety_stock import (
    INVENTORY_SAFETY_STOCK_FORMULA_VERSION,
    InventorySafetyStockInputRef,
    InventorySafetyStockOutput,
    InventorySafetyStockResult,
    _demand_payload,
)
from topspeed_ai_os.contracts import validate_schema_only
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.core.ids import require_valid_run_id

_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_AUTHORITY_REFERENCE_PATTERN = re.compile(r"TOPSPEED_SAFETY_STOCK_POLICY_V1@sha256:[0-9a-f]{64}")
_DATETIME_TIMEZONE_SUFFIX_PATTERN = re.compile(r"(?:Z|[+-][0-9]{2}:[0-9]{2})$")
_AUTHORITY_HASH_FIELDS = (
    "kind",
    "sku",
    "value",
    "authority_reference",
    "authority_status",
    "formula_version",
    "source",
    "data_as_of",
)


def _authority_payload(
    kind: str,
    sku: str,
    value: int | None,
    authority_reference: str,
    authority_status: str,
    formula_version: str | None,
    source: str,
    data_as_of: str,
) -> dict[str, object]:
    return {
        "kind": kind,
        "sku": sku,
        "value": value,
        "authority_reference": authority_reference,
        "authority_status": authority_status,
        "formula_version": formula_version,
        "source": source,
        "data_as_of": data_as_of,
    }


def _require_exact_str(value: object, field: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field} must be an exact str")


def _require_canonical_datetime(value: str, field: str) -> None:
    _require_exact_str(value, field)
    if _DATETIME_TIMEZONE_SUFFIX_PATTERN.search(value) is None:
        raise ValueError(f"{field} must end in Z or a canonical ±HH:MM offset")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a real ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    canonical = parsed.isoformat()
    if value.endswith("Z"):
        canonical = canonical.removesuffix("+00:00") + "Z"
    elif value.endswith("-00:00"):
        canonical = canonical.removesuffix("+00:00") + "-00:00"
    if canonical != value:
        raise ValueError(f"{field} must be canonical")


@dataclass(frozen=True, slots=True)
class InventoryReorderPointAuthorityRef:
    """Canonical immutable authority projection for future Reorder Point inputs."""

    kind: Literal["LEAD_TIME_SUPPLIER_CONTRACT", "SAFETY_STOCK_POLICY"]
    sku: str
    value: int | None
    authority_reference: str
    authority_status: Literal["VERIFIED", "APPROVED"]
    formula_version: str | None
    source: str
    data_as_of: str
    input_hash: str

    def __post_init__(self) -> None:
        for field, value in (
            ("kind", self.kind),
            ("sku", self.sku),
            ("authority_reference", self.authority_reference),
            ("authority_status", self.authority_status),
            ("source", self.source),
            ("data_as_of", self.data_as_of),
            ("input_hash", self.input_hash),
        ):
            _require_exact_str(value, field)
        if self.value is not None and type(self.value) is not int:
            raise TypeError("value must be an exact int or None")
        if self.value is not None and self.value < 0:
            raise ValueError("value must be nonnegative or None")
        if self.formula_version is not None:
            _require_exact_str(self.formula_version, "formula_version")
        if self.kind not in {"LEAD_TIME_SUPPLIER_CONTRACT", "SAFETY_STOCK_POLICY"}:
            raise ValueError("unsupported authority kind")
        if not self.sku:
            raise ValueError("sku must be non-empty")
        if not self.authority_reference:
            raise ValueError("authority_reference must be non-empty")
        if not self.source:
            raise ValueError("source must be non-empty")
        if _HASH_PATTERN.fullmatch(self.input_hash) is None:
            raise ValueError("input_hash must use canonical sha256 grammar")
        _require_canonical_datetime(self.data_as_of, "data_as_of")

        if self.kind == "LEAD_TIME_SUPPLIER_CONTRACT":
            if self.authority_status != "VERIFIED":
                raise ValueError("lead-time authority_status must be VERIFIED")
            if self.formula_version is not None:
                raise ValueError("lead-time formula_version must be None")
        else:
            if self.authority_status != "APPROVED":
                raise ValueError("safety-stock authority_status must be APPROVED")
            if type(self.formula_version) is not str or not self.formula_version:
                raise ValueError("safety-stock formula_version must be a non-empty exact str")

        expected_hash = payload_sha256(
            _authority_payload(
                self.kind,
                self.sku,
                self.value,
                self.authority_reference,
                self.authority_status,
                self.formula_version,
                self.source,
                self.data_as_of,
            )
        )
        if self.input_hash != expected_hash:
            raise ValueError("input_hash does not match the exact authority payload")


@dataclass(frozen=True, slots=True)
class _InventorySafetyStockProjection:
    """Private, read-only pairing of projected INVENTORY and its authority."""

    inventory: Mapping[str, object]
    authority: InventoryReorderPointAuthorityRef

    def __post_init__(self) -> None:
        if type(self.inventory) is not MappingProxyType:
            raise TypeError("inventory must be an exact MappingProxyType")
        if type(self.authority) is not InventoryReorderPointAuthorityRef:
            raise TypeError("authority must be the exact canonical authority class")
        self.authority.__post_init__()
        if "sku" not in self.inventory or "safety_stock_qty" not in self.inventory:
            raise ValueError("projection must contain sku and safety_stock_qty")
        if self.inventory["sku"] != self.authority.sku:
            raise ValueError("projected INVENTORY SKU must equal authority SKU")
        if self.inventory["safety_stock_qty"] != self.authority.value:
            raise ValueError("projected safety_stock_qty must equal authority value")


def _require_exact_result_field_types(safety_stock: InventorySafetyStockResult) -> None:
    for field, value in (
        ("metric_family", safety_stock.metric_family),
        ("formula_version", safety_stock.formula_version),
        ("policy_version", safety_stock.policy_version),
        ("run_id", safety_stock.run_id),
        ("channel", safety_stock.channel),
        ("sku", safety_stock.sku),
        ("window_start_date", safety_stock.window_start_date),
        ("window_end_date", safety_stock.window_end_date),
        ("status", safety_stock.status),
        ("input_hash", safety_stock.input_hash),
    ):
        _require_exact_str(value, field)
    for field, value in (
        ("outputs", safety_stock.outputs),
        ("input_refs", safety_stock.input_refs),
        ("errors", safety_stock.errors),
    ):
        if type(value) is not tuple:
            raise TypeError(f"{field} must be an exact tuple")
    if any(type(item) is not InventorySafetyStockOutput for item in safety_stock.outputs):
        raise TypeError("outputs must contain exact InventorySafetyStockOutput instances")
    if any(type(item) is not InventorySafetyStockInputRef for item in safety_stock.input_refs):
        raise TypeError("input_refs must contain exact InventorySafetyStockInputRef instances")
    for output in safety_stock.outputs:
        _require_exact_str(output.name, "output.name")
        if type(output.value) is not int:
            raise TypeError("output.value must be an exact int")
    for ref in safety_stock.input_refs:
        for field in (
            "kind",
            "metric_family",
            "formula_version",
            "policy_version",
            "approval_authority",
            "authority_reference",
            "authority_status",
            "source",
            "data_as_of",
            "channel",
            "sku",
            "window_start_date",
            "window_end_date",
            "avg_daily_units",
            "input_hash",
        ):
            value = getattr(ref, field)
            if value is not None:
                _require_exact_str(value, f"input_refs.{field}")
        if ref.safety_stock_days is not None and type(ref.safety_stock_days) is not int:
            raise TypeError("input_refs.safety_stock_days must be an exact int or None")
        if type(ref.upstream_input_refs) is not tuple:
            raise TypeError("upstream_input_refs must be an exact tuple")
        if any(
            type(item) is not InventoryDemandVelocityInputRef for item in ref.upstream_input_refs
        ):
            raise TypeError("upstream_input_refs must contain exact demand input refs")
        for upstream_ref in ref.upstream_input_refs:
            for field in ("contract_name", "source", "data_as_of", "input_hash"):
                _require_exact_str(getattr(upstream_ref, field), f"upstream_input_refs.{field}")
            if (
                type(upstream_ref.natural_key) is not tuple
                or len(upstream_ref.natural_key) != 3
                or any(type(item) is not str for item in upstream_ref.natural_key)
            ):
                raise TypeError("upstream_input_refs.natural_key must be an exact str tuple")


def _validate_demand_reference(ref: InventorySafetyStockInputRef) -> None:
    ref.__post_init__()
    if ref.kind != "DEMAND_VELOCITY":
        raise ValueError("first input reference must be DEMAND_VELOCITY")
    expected_hash = payload_sha256(
        _demand_payload(
            ref.metric_family,
            ref.formula_version,
            ref.channel,
            ref.sku,
            ref.window_start_date,
            ref.window_end_date,
            ref.avg_daily_units,
            ref.upstream_input_refs,
        )
    )
    if ref.input_hash != expected_hash:
        raise ValueError("demand reference hash does not match its projected payload")


def _project_inventory_safety_stock_for_reorder_point(
    inventory: Mapping[str, object],
    safety_stock: InventorySafetyStockResult,
) -> _InventorySafetyStockProjection:
    """Create a validated, non-persisted INVENTORY projection with paired authority."""

    # 1. Mapping boundary.
    if not isinstance(inventory, Mapping):
        raise TypeError("inventory must satisfy collections.abc.Mapping")

    # 2. Source Contract schema authority; exceptions intentionally propagate unchanged.
    validate_schema_only("INVENTORY", inventory)

    # 3. Existing safety stock is never overwritten or replaced, including None.
    if "safety_stock_qty" in inventory:
        raise ValueError("source INVENTORY must not contain safety_stock_qty")

    # 4. Exact result identity.
    if type(safety_stock) is not InventorySafetyStockResult:
        raise TypeError("safety_stock must be the exact InventorySafetyStockResult class")

    # 5. Exact built-in scalar, tuple and nested carrier types.
    _require_exact_result_field_types(safety_stock)

    # 6. Literals and Core run-id authority.
    if safety_stock.metric_family != "INVENTORY_SAFETY_STOCK":
        raise ValueError("invalid Safety Stock metric_family")
    if safety_stock.formula_version != INVENTORY_SAFETY_STOCK_FORMULA_VERSION:
        raise ValueError("invalid Safety Stock formula_version")
    if safety_stock.policy_version != "TOPSPEED_SAFETY_STOCK_POLICY_V1":
        raise ValueError("invalid Safety Stock policy_version")
    if safety_stock.status != "SUCCESS":
        raise ValueError("Safety Stock status must be SUCCESS")
    require_valid_run_id(safety_stock.run_id)

    # 7. Exact output shape and value.
    if len(safety_stock.outputs) != 1:
        raise ValueError("Safety Stock result must contain exactly one output")
    output = safety_stock.outputs[0]
    if type(output.name) is not str or output.name != "safety_stock_qty":
        raise ValueError("Safety Stock output name must be safety_stock_qty")
    if type(output.value) is not int:
        raise TypeError("Safety Stock output value must be an exact int")
    if output.value < 0:
        raise ValueError("Safety Stock output value must be nonnegative")

    # 8. Exact reference tuple and order.
    if len(safety_stock.input_refs) != 2:
        raise ValueError("Safety Stock result must contain exactly two input references")
    demand_ref, policy_ref = safety_stock.input_refs
    if demand_ref.kind != "DEMAND_VELOCITY" or policy_ref.kind != "SAFETY_STOCK_POLICY":
        raise ValueError(
            "input references must be ordered DEMAND_VELOCITY then SAFETY_STOCK_POLICY"
        )

    # 9. Demand window, upstream order/coverage/coherence and projected-reference hash.
    _validate_demand_reference(demand_ref)

    # 10. Policy literals, provenance, days and hash.
    policy_ref.__post_init__()
    if policy_ref.kind != "SAFETY_STOCK_POLICY":
        raise ValueError("second input reference must be SAFETY_STOCK_POLICY")

    # 11. Revalidate all result coherence, CEILING calculation and final hash.
    safety_stock.__post_init__()

    # 12. SKU coherence; inventory location is intentionally independent of demand channel.
    if inventory["sku"] != safety_stock.sku:
        raise ValueError("INVENTORY SKU must equal Safety Stock result SKU")

    # 13. Fresh immutable projection; mapping access/iteration exceptions propagate unchanged.
    projected_values = dict(inventory)
    projected_values["safety_stock_qty"] = output.value
    projected_inventory = MappingProxyType(projected_values)

    # 14. Validate the projected record through the existing schema-only authority.
    validate_schema_only("INVENTORY", projected_inventory)

    # 15. Exact result-bound authority reference.
    authority_reference = f"{policy_ref.authority_reference}@{safety_stock.input_hash}"
    if _AUTHORITY_REFERENCE_PATTERN.fullmatch(authority_reference) is None:
        raise ValueError("authority_reference is not canonical for the Safety Stock result")

    # 16. Hash only the eight published authority fields, in their declared order.
    authority_values = _authority_payload(
        "SAFETY_STOCK_POLICY",
        safety_stock.sku,
        output.value,
        authority_reference,
        "APPROVED",
        safety_stock.formula_version,
        policy_ref.source,
        policy_ref.data_as_of,
    )
    if tuple(authority_values) != _AUTHORITY_HASH_FIELDS:
        raise ValueError("authority payload field order is not canonical")
    authority = InventoryReorderPointAuthorityRef(
        kind="SAFETY_STOCK_POLICY",
        sku=safety_stock.sku,
        value=output.value,
        authority_reference=authority_reference,
        authority_status="APPROVED",
        formula_version=safety_stock.formula_version,
        source=policy_ref.source,
        data_as_of=policy_ref.data_as_of,
        input_hash=payload_sha256(authority_values),
    )

    # 17. Construct and explicitly revalidate the exact paired projection.
    projection = _InventorySafetyStockProjection(
        inventory=projected_inventory,
        authority=authority,
    )
    projection.__post_init__()

    # 18. Return exactly the private carrier.
    return projection
