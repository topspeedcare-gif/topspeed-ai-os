"""Deterministic PHASE 5 inventory stock-days calculation."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from topspeed_ai_os.contracts import validate_schema_only
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.core.ids import require_valid_run_id

from .contribution_margin import UnsupportedFormulaVersionError
from .inventory_demand_velocity import (
    INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION,
    InventoryDemandVelocityInputRef,
    InventoryDemandVelocityOutput,
    InventoryDemandVelocityResult,
)

INVENTORY_STOCK_DAYS_FORMULA_VERSION = "topspeed.calculation.inventory_stock_days.v1"

_METRIC_FAMILY = "INVENTORY_STOCK_DAYS"
_DEMAND_METRIC_FAMILY = "INVENTORY_DEMAND_VELOCITY"
_OUTPUT_NAME = "stock_days"
_DEMAND_OUTPUT_NAME = "avg_daily_units"
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_FIXED_POINT_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,4})?")


def _require_exact_str(value: object, field: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field} must be an exact str")


def _require_optional_exact_str(value: object, field: str) -> None:
    if value is not None:
        _require_exact_str(value, field)


def _require_exact_tuple(value: object, field: str, item_type: type[object]) -> None:
    if type(value) is not tuple:
        raise TypeError(f"{field} must be an exact tuple")
    if any(type(item) is not item_type for item in value):
        raise TypeError(f"{field} items must be exact {item_type.__name__} instances")


def _require_canonical_hash(value: str, field: str) -> None:
    if _HASH_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a canonical input hash")


def _parse_canonical_date(value: str, field: str) -> date:
    if _DATE_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a canonical YYYY-MM-DD date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a real Gregorian calendar date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must round-trip canonically")
    return parsed


def _validate_canonical_fixed_point(value: str, field: str) -> None:
    if _FIXED_POINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a canonical nonnegative fixed-point string")
    if "." in value and value.endswith("0"):
        raise ValueError(f"{field} must not contain trailing fractional zeros")


def _project_demand_input_ref(ref: InventoryDemandVelocityInputRef) -> dict[str, object]:
    return {
        "contract_name": ref.contract_name,
        "natural_key": list(ref.natural_key),
        "source": ref.source,
        "data_as_of": ref.data_as_of,
        "input_hash": ref.input_hash,
    }


def _demand_hash_payload(
    *,
    metric_family: str,
    formula_version: str,
    channel: str,
    sku: str,
    window_start_date: str,
    window_end_date: str,
    avg_daily_units: str,
    input_refs: tuple[InventoryDemandVelocityInputRef, ...],
) -> dict[str, object]:
    return {
        "metric_family": metric_family,
        "formula_version": formula_version,
        "channel": channel,
        "sku": sku,
        "window_start_date": window_start_date,
        "window_end_date": window_end_date,
        "avg_daily_units": avg_daily_units,
        "input_refs": [_project_demand_input_ref(ref) for ref in input_refs],
    }


def _demand_input_hash(
    *,
    metric_family: str,
    formula_version: str,
    channel: str,
    sku: str,
    window_start_date: str,
    window_end_date: str,
    avg_daily_units: str,
    input_refs: tuple[InventoryDemandVelocityInputRef, ...],
) -> str:
    return payload_sha256(
        _demand_hash_payload(
            metric_family=metric_family,
            formula_version=formula_version,
            channel=channel,
            sku=sku,
            window_start_date=window_start_date,
            window_end_date=window_end_date,
            avg_daily_units=avg_daily_units,
            input_refs=input_refs,
        )
    )


def _final_input_hash(formula_version: str, inventory_hash: str, demand_hash: str) -> str:
    return payload_sha256(
        {
            "formula_version": formula_version,
            "inventory_input_hash": inventory_hash,
            "demand_input_hash": demand_hash,
        }
    )


@dataclass(frozen=True, slots=True)
class InventoryStockDaysOutput:
    name: Literal["stock_days"]
    value: str | None

    def __post_init__(self) -> None:
        _require_exact_str(self.name, "name")
        if self.name != _OUTPUT_NAME:
            raise ValueError(f"name must be {_OUTPUT_NAME!r}")
        if self.value is not None:
            _require_exact_str(self.value, "value")
            _validate_canonical_fixed_point(self.value, "value")


@dataclass(frozen=True, slots=True)
class InventoryStockDaysError:
    code: Literal["INVALID_INPUT"]
    field: Literal["available_qty"]
    input_hashes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_exact_str(self.code, "code")
        _require_exact_str(self.field, "field")
        if self.code != "INVALID_INPUT" or self.field != "available_qty":
            raise ValueError("unsupported error code or field")
        if type(self.input_hashes) is not tuple:
            raise TypeError("input_hashes must be an exact tuple")
        if len(self.input_hashes) != 1:
            raise ValueError("INVALID_INPUT requires exactly one input hash")
        if type(self.input_hashes[0]) is not str:
            raise TypeError("input_hashes items must be exact str values")
        _require_canonical_hash(self.input_hashes[0], "input_hashes item")


@dataclass(frozen=True, slots=True)
class InventoryStockDaysInputRef:
    kind: Literal["INVENTORY", "DEMAND_VELOCITY"]
    contract_name: str | None
    natural_key: tuple[str, str, str] | None
    source: str | None
    data_as_of: str | None
    input_hash: str
    metric_family: str | None
    formula_version: str | None
    channel: str | None
    sku: str
    window_start_date: str | None
    window_end_date: str | None
    avg_daily_units: str | None
    upstream_input_refs: tuple[InventoryDemandVelocityInputRef, ...]

    def __post_init__(self) -> None:
        _require_exact_str(self.kind, "kind")
        for field, value in (
            ("contract_name", self.contract_name),
            ("source", self.source),
            ("data_as_of", self.data_as_of),
            ("metric_family", self.metric_family),
            ("formula_version", self.formula_version),
            ("channel", self.channel),
            ("window_start_date", self.window_start_date),
            ("window_end_date", self.window_end_date),
            ("avg_daily_units", self.avg_daily_units),
        ):
            _require_optional_exact_str(value, field)
        _require_exact_str(self.input_hash, "input_hash")
        _require_canonical_hash(self.input_hash, "input_hash")
        _require_exact_str(self.sku, "sku")
        _require_exact_tuple(
            self.upstream_input_refs,
            "upstream_input_refs",
            InventoryDemandVelocityInputRef,
        )

        if self.natural_key is not None:
            if type(self.natural_key) is not tuple or len(self.natural_key) != 3:
                raise TypeError("natural_key must be an exact three-item tuple or None")
            if any(type(item) is not str for item in self.natural_key):
                raise TypeError("natural_key items must be exact str values")

        if self.kind == "INVENTORY":
            self._validate_inventory_kind()
        elif self.kind == "DEMAND_VELOCITY":
            self._validate_demand_kind()
        else:
            raise ValueError(f"unsupported input-reference kind: {self.kind!r}")

    def _validate_inventory_kind(self) -> None:
        if self.contract_name != "INVENTORY":
            raise ValueError("INVENTORY reference requires contract_name 'INVENTORY'")
        if self.natural_key is None or self.source is None or self.data_as_of is None:
            raise ValueError("INVENTORY reference requires direct Contract projections")
        if any(
            value is not None
            for value in (
                self.metric_family,
                self.formula_version,
                self.channel,
                self.window_start_date,
                self.window_end_date,
                self.avg_daily_units,
            )
        ):
            raise ValueError("INVENTORY reference forbids demand fields")
        if self.upstream_input_refs:
            raise ValueError("INVENTORY reference requires empty upstream_input_refs")
        if self.natural_key[1] != self.sku:
            raise ValueError("INVENTORY natural-key SKU must equal sku")

    def _validate_demand_kind(self) -> None:
        if any(
            value is not None
            for value in (self.contract_name, self.natural_key, self.source, self.data_as_of)
        ):
            raise ValueError("DEMAND_VELOCITY reference forbids Contract fields")
        if self.metric_family != _DEMAND_METRIC_FAMILY:
            raise ValueError(f"metric_family must be {_DEMAND_METRIC_FAMILY!r}")
        if self.formula_version != INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION:
            raise ValueError("invalid demand formula_version")
        if any(
            value is None
            for value in (
                self.channel,
                self.window_start_date,
                self.window_end_date,
                self.avg_daily_units,
            )
        ):
            raise ValueError("DEMAND_VELOCITY reference requires all demand fields")

        window_start = _parse_canonical_date(self.window_start_date, "window_start_date")
        window_end = _parse_canonical_date(self.window_end_date, "window_end_date")
        if window_start != window_end - timedelta(days=29):
            raise ValueError("window_start_date must be window_end_date minus 29 days")
        _validate_canonical_fixed_point(self.avg_daily_units, "avg_daily_units")
        if len(self.upstream_input_refs) != 30:
            raise ValueError("DEMAND_VELOCITY reference requires exactly 30 upstream references")
        canonical = tuple(
            sorted(
                self.upstream_input_refs,
                key=lambda ref: (ref.natural_key[1], ref.input_hash),
            )
        )
        if self.upstream_input_refs != canonical:
            raise ValueError("upstream_input_refs must be canonically ordered")
        if any(
            ref.natural_key[0] != self.channel or ref.natural_key[2] != self.sku
            for ref in self.upstream_input_refs
        ):
            raise ValueError("upstream channel and SKU must be coherent")
        expected_dates = tuple(
            (window_start + timedelta(days=offset)).isoformat() for offset in range(30)
        )
        actual_dates = tuple(ref.natural_key[1] for ref in self.upstream_input_refs)
        if actual_dates != expected_dates or expected_dates[-1] != window_end.isoformat():
            raise ValueError("upstream references must cover the complete demand window")

        expected_hash = _demand_input_hash(
            metric_family=self.metric_family,
            formula_version=self.formula_version,
            channel=self.channel,
            sku=self.sku,
            window_start_date=self.window_start_date,
            window_end_date=self.window_end_date,
            avg_daily_units=self.avg_daily_units,
            input_refs=self.upstream_input_refs,
        )
        if self.input_hash != expected_hash:
            raise ValueError("demand input_hash does not match the projected payload")


@dataclass(frozen=True, slots=True)
class InventoryStockDaysResult:
    metric_family: str
    formula_version: str
    run_id: str
    sku: str
    location: str
    demand_channel: str
    snapshot_at: str
    window_start_date: str
    window_end_date: str
    status: Literal["SUCCESS", "PARTIAL", "ERROR"]
    outputs: tuple[InventoryStockDaysOutput, ...]
    input_refs: tuple[InventoryStockDaysInputRef, ...]
    reason: Literal["ZERO_DEMAND"] | None
    errors: tuple[InventoryStockDaysError, ...]
    input_hash: str

    def __post_init__(self) -> None:
        for field, value in (
            ("metric_family", self.metric_family),
            ("formula_version", self.formula_version),
            ("run_id", self.run_id),
            ("sku", self.sku),
            ("location", self.location),
            ("demand_channel", self.demand_channel),
            ("snapshot_at", self.snapshot_at),
            ("window_start_date", self.window_start_date),
            ("window_end_date", self.window_end_date),
            ("status", self.status),
            ("input_hash", self.input_hash),
        ):
            _require_exact_str(value, field)
        _require_optional_exact_str(self.reason, "reason")
        _require_canonical_hash(self.input_hash, "input_hash")
        _require_exact_tuple(self.outputs, "outputs", InventoryStockDaysOutput)
        _require_exact_tuple(self.input_refs, "input_refs", InventoryStockDaysInputRef)
        _require_exact_tuple(self.errors, "errors", InventoryStockDaysError)

        if self.metric_family != _METRIC_FAMILY:
            raise ValueError(f"metric_family must be {_METRIC_FAMILY!r}")
        if self.formula_version != INVENTORY_STOCK_DAYS_FORMULA_VERSION:
            raise ValueError("invalid inventory stock-days formula_version")
        if self.status not in {"SUCCESS", "PARTIAL", "ERROR"}:
            raise ValueError(f"unsupported status: {self.status!r}")
        if self.reason not in {None, "ZERO_DEMAND"}:
            raise ValueError(f"unsupported reason: {self.reason!r}")
        _parse_canonical_date(self.window_start_date, "window_start_date")
        _parse_canonical_date(self.window_end_date, "window_end_date")

        if len(self.input_refs) != 2:
            raise ValueError("input_refs must contain exactly two references")
        inventory_ref, demand_ref = self.input_refs
        if inventory_ref.kind != "INVENTORY" or demand_ref.kind != "DEMAND_VELOCITY":
            raise ValueError("input_refs must be ordered INVENTORY then DEMAND_VELOCITY")
        if self.sku != inventory_ref.sku or self.sku != demand_ref.sku:
            raise ValueError("result SKU must equal both input-reference SKUs")
        if self.snapshot_at != inventory_ref.natural_key[0]:
            raise ValueError("result snapshot_at must equal inventory natural key")
        if self.location != inventory_ref.natural_key[2]:
            raise ValueError("result location must equal inventory natural key")
        if self.demand_channel != demand_ref.channel:
            raise ValueError("result demand_channel must equal demand reference channel")
        if self.window_start_date != demand_ref.window_start_date:
            raise ValueError("result window_start_date must equal demand reference")
        if self.window_end_date != demand_ref.window_end_date:
            raise ValueError("result window_end_date must equal demand reference")
        expected_hash = _final_input_hash(
            self.formula_version,
            inventory_ref.input_hash,
            demand_ref.input_hash,
        )
        if self.input_hash != expected_hash:
            raise ValueError("input_hash does not match the approved nested hashes")

        if self.status == "SUCCESS":
            if (
                len(self.outputs) != 1
                or self.outputs[0].value is None
                or self.reason is not None
                or self.errors
            ):
                raise ValueError("invalid SUCCESS result shape")
        elif self.status == "PARTIAL":
            if (
                len(self.outputs) != 1
                or self.outputs[0].value is not None
                or self.reason != "ZERO_DEMAND"
                or self.errors
            ):
                raise ValueError("invalid PARTIAL result shape")
        elif (
            self.outputs
            or self.reason is not None
            or len(self.errors) != 1
            or self.errors[0].input_hashes != (inventory_ref.input_hash,)
        ):
            raise ValueError("invalid ERROR result shape")


def _inventory_input_ref(inventory: Mapping[str, object]) -> InventoryStockDaysInputRef:
    payload = {
        "snapshot_at": inventory["snapshot_at"],
        "sku": inventory["sku"],
        "location": inventory["location"],
        "available_qty": inventory["available_qty"],
        "source": inventory["source"],
        "data_as_of": inventory["data_as_of"],
    }
    return InventoryStockDaysInputRef(
        kind="INVENTORY",
        contract_name="INVENTORY",
        natural_key=(inventory["snapshot_at"], inventory["sku"], inventory["location"]),
        source=inventory["source"],
        data_as_of=inventory["data_as_of"],
        input_hash=payload_sha256(payload),
        metric_family=None,
        formula_version=None,
        channel=None,
        sku=inventory["sku"],
        window_start_date=None,
        window_end_date=None,
        avg_daily_units=None,
        upstream_input_refs=(),
    )


def _demand_input_ref(
    demand_velocity: InventoryDemandVelocityResult,
    output: InventoryDemandVelocityOutput,
) -> InventoryStockDaysInputRef:
    input_hash = _demand_input_hash(
        metric_family=demand_velocity.metric_family,
        formula_version=demand_velocity.formula_version,
        channel=demand_velocity.channel,
        sku=demand_velocity.sku,
        window_start_date=demand_velocity.window_start_date,
        window_end_date=demand_velocity.window_end_date,
        avg_daily_units=output.value,
        input_refs=demand_velocity.input_refs,
    )
    return InventoryStockDaysInputRef(
        kind="DEMAND_VELOCITY",
        contract_name=None,
        natural_key=None,
        source=None,
        data_as_of=None,
        input_hash=input_hash,
        metric_family=demand_velocity.metric_family,
        formula_version=demand_velocity.formula_version,
        channel=demand_velocity.channel,
        sku=demand_velocity.sku,
        window_start_date=demand_velocity.window_start_date,
        window_end_date=demand_velocity.window_end_date,
        avg_daily_units=output.value,
        upstream_input_refs=demand_velocity.input_refs,
    )


def _parse_fixed_point(value: str) -> tuple[int, int]:
    if "." not in value:
        return int(value), 1
    whole, fractional = value.split(".")
    scale = 10 ** len(fractional)
    return int(whole) * scale + int(fractional), scale


def _rounded_stock_days(available_qty: int, demand_units: int, demand_scale: int) -> str:
    quotient, remainder = divmod(available_qty * demand_scale * 10_000, demand_units)
    if 2 * remainder >= demand_units:
        quotient += 1
    whole, fractional = divmod(quotient, 10_000)
    if fractional == 0:
        return str(whole)
    return f"{whole}.{fractional:04d}".rstrip("0")


def calculate_inventory_stock_days(
    inventory: Mapping[str, object],
    demand_velocity: InventoryDemandVelocityResult,
    *,
    run_id: str,
    formula_version: str = INVENTORY_STOCK_DAYS_FORMULA_VERSION,
) -> InventoryStockDaysResult:
    if not isinstance(inventory, Mapping):
        raise TypeError("inventory must satisfy Mapping")
    validate_schema_only("INVENTORY", inventory)

    if type(demand_velocity) is not InventoryDemandVelocityResult:
        raise TypeError("demand_velocity must be an exact InventoryDemandVelocityResult")
    if demand_velocity.status != "SUCCESS":
        raise ValueError("demand_velocity must have SUCCESS status")

    _require_exact_str(formula_version, "formula_version")
    if formula_version != INVENTORY_STOCK_DAYS_FORMULA_VERSION:
        raise UnsupportedFormulaVersionError(f"unsupported formula version: {formula_version!r}")

    _require_exact_str(run_id, "run_id")
    validated_run_id = require_valid_run_id(run_id)

    if inventory["sku"] != demand_velocity.sku:
        raise ValueError("inventory and demand_velocity must have exactly equal SKUs")
    if (
        type(demand_velocity.outputs) is not tuple
        or len(demand_velocity.outputs) != 1
        or type(demand_velocity.outputs[0]) is not InventoryDemandVelocityOutput
        or demand_velocity.outputs[0].name != _DEMAND_OUTPUT_NAME
    ):
        raise ValueError("demand_velocity must contain exactly one avg_daily_units output")
    demand_output = demand_velocity.outputs[0]
    _require_exact_str(demand_output.value, "avg_daily_units")
    _validate_canonical_fixed_point(demand_output.value, "avg_daily_units")

    inventory_ref = _inventory_input_ref(inventory)
    demand_ref = _demand_input_ref(demand_velocity, demand_output)
    input_refs = (inventory_ref, demand_ref)
    final_hash = _final_input_hash(formula_version, inventory_ref.input_hash, demand_ref.input_hash)
    common = {
        "metric_family": _METRIC_FAMILY,
        "formula_version": formula_version,
        "run_id": validated_run_id,
        "sku": inventory["sku"],
        "location": inventory["location"],
        "demand_channel": demand_velocity.channel,
        "snapshot_at": inventory["snapshot_at"],
        "window_start_date": demand_velocity.window_start_date,
        "window_end_date": demand_velocity.window_end_date,
        "input_refs": input_refs,
        "input_hash": final_hash,
    }

    available_qty = inventory["available_qty"]
    if available_qty < 0:
        return InventoryStockDaysResult(
            **common,
            status="ERROR",
            outputs=(),
            reason=None,
            errors=(
                InventoryStockDaysError(
                    "INVALID_INPUT",
                    "available_qty",
                    (inventory_ref.input_hash,),
                ),
            ),
        )

    demand_units, demand_scale = _parse_fixed_point(demand_output.value)
    if demand_units == 0:
        return InventoryStockDaysResult(
            **common,
            status="PARTIAL",
            outputs=(InventoryStockDaysOutput(_OUTPUT_NAME, None),),
            reason="ZERO_DEMAND",
            errors=(),
        )

    return InventoryStockDaysResult(
        **common,
        status="SUCCESS",
        outputs=(
            InventoryStockDaysOutput(
                _OUTPUT_NAME,
                _rounded_stock_days(available_qty, demand_units, demand_scale),
            ),
        ),
        reason=None,
        errors=(),
    )
