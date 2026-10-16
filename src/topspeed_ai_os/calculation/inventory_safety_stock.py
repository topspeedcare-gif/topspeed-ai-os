"""Canonical policy authority carrier for inventory safety stock."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.core.ids import require_valid_run_id

from .contribution_margin import UnsupportedFormulaVersionError
from .inventory_demand_velocity import (
    INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION,
    InventoryDemandVelocityInputRef,
    InventoryDemandVelocityOutput,
    InventoryDemandVelocityResult,
)

_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_POLICY_VERSION = "TOPSPEED_SAFETY_STOCK_POLICY_V1"
_APPROVAL_AUTHORITY = "TOPSPEED Human Architecture Owner"
_SOURCE = "topspeed.repository.policy_authority.inventory_safety_stock.v1"
_DATA_AS_OF = "2026-10-15T16:05:35+09:00"
_POLICY_HASH = "sha256:c1960068c6bb5a527c826bd1bbea6a2c021d29b3b9f439b2f77033bd1b20ba2a"
INVENTORY_SAFETY_STOCK_FORMULA_VERSION = "topspeed.calculation.inventory_safety_stock.v1"

_METRIC_FAMILY = "INVENTORY_SAFETY_STOCK"
_DEMAND_METRIC_FAMILY = "INVENTORY_DEMAND_VELOCITY"
_DEMAND_OUTPUT_NAME = "avg_daily_units"
_OUTPUT_NAME = "safety_stock_qty"
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_FIXED_POINT_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,4})?")


def _policy_payload(
    policy_version: str,
    approval_authority: str,
    authority_reference: str,
    authority_status: str,
    source: str,
    data_as_of: str,
    safety_stock_days: int,
) -> dict[str, object]:
    return {
        "policy_version": policy_version,
        "approval_authority": approval_authority,
        "authority_reference": authority_reference,
        "authority_status": authority_status,
        "source": source,
        "data_as_of": data_as_of,
        "safety_stock_days": safety_stock_days,
    }


def _validate_data_as_of(value: str) -> None:
    if value != _DATA_AS_OF:
        raise ValueError("data_as_of must equal the approved V1 value")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("data_as_of must be a real Gregorian datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("data_as_of must include a timezone")
    if parsed.isoformat() != value:
        raise ValueError("data_as_of must round-trip canonically")


@dataclass(frozen=True, slots=True)
class InventorySafetyStockPolicyAuthority:
    """Immutable, validated V1 policy authority projection."""

    policy_version: str
    approval_authority: str
    authority_reference: str
    authority_status: Literal["APPROVED"]
    source: str
    data_as_of: str
    safety_stock_days: int
    input_hash: str

    def __post_init__(self) -> None:
        for field, value in (
            ("policy_version", self.policy_version),
            ("approval_authority", self.approval_authority),
            ("authority_reference", self.authority_reference),
            ("authority_status", self.authority_status),
            ("source", self.source),
            ("data_as_of", self.data_as_of),
            ("input_hash", self.input_hash),
        ):
            if type(value) is not str:
                raise TypeError(f"{field} must be an exact str")
        if type(self.safety_stock_days) is not int:
            raise TypeError("safety_stock_days must be an exact int")
        if self.policy_version != _POLICY_VERSION:
            raise ValueError("unsupported policy_version")
        if self.approval_authority != _APPROVAL_AUTHORITY:
            raise ValueError("unsupported approval_authority")
        if self.authority_reference != _POLICY_VERSION:
            raise ValueError("unsupported authority_reference")
        if self.authority_status != "APPROVED":
            raise ValueError("authority_status must be APPROVED")
        if not self.source:
            raise ValueError("source must be non-empty")
        _validate_data_as_of(self.data_as_of)
        if self.safety_stock_days != 7:
            raise ValueError("safety_stock_days must equal 7")
        if _HASH_PATTERN.fullmatch(self.input_hash) is None:
            raise ValueError("input_hash must be canonical lowercase sha256")
        expected_hash = payload_sha256(
            _policy_payload(
                self.policy_version,
                self.approval_authority,
                self.authority_reference,
                self.authority_status,
                self.source,
                self.data_as_of,
                self.safety_stock_days,
            )
        )
        if self.input_hash != expected_hash or self.input_hash != _POLICY_HASH:
            raise ValueError("input_hash does not match the approved policy payload")


def _require_exact_str(value: object, field: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field} must be an exact str")


def _require_optional_exact_str(value: object, field: str) -> None:
    if value is not None:
        _require_exact_str(value, field)


def _require_canonical_hash(value: str, field: str) -> None:
    if _HASH_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a canonical lowercase sha256 hash")


def _parse_canonical_date(value: str, field: str) -> date:
    if _DATE_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a canonical YYYY-MM-DD date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a real Gregorian date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must round-trip canonically")
    return parsed


def _validate_canonical_fixed_point(value: str, field: str) -> None:
    if _FIXED_POINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a canonical nonnegative fixed-point string")
    if "." in value and value.endswith("0"):
        raise ValueError(f"{field} must not contain trailing fractional zeros")


def _parse_fixed_point(value: str) -> tuple[int, int]:
    _validate_canonical_fixed_point(value, "avg_daily_units")
    whole, separator, fraction = value.partition(".")
    if not separator:
        return int(whole), 1
    return int(whole + fraction), 10 ** len(fraction)


def _safety_stock_quantity(avg_daily_units: str, safety_stock_days: int) -> int:
    numerator, scale = _parse_fixed_point(avg_daily_units)
    quotient, remainder = divmod(numerator * safety_stock_days, scale)
    return quotient + int(remainder != 0)


def _project_demand_input_ref(ref: InventoryDemandVelocityInputRef) -> dict[str, object]:
    return {
        "contract_name": ref.contract_name,
        "natural_key": list(ref.natural_key),
        "source": ref.source,
        "data_as_of": ref.data_as_of,
        "input_hash": ref.input_hash,
    }


def _demand_payload(
    metric_family: str,
    formula_version: str,
    channel: str,
    sku: str,
    window_start_date: str,
    window_end_date: str,
    avg_daily_units: str,
    upstream_input_refs: tuple[InventoryDemandVelocityInputRef, ...],
) -> dict[str, object]:
    return {
        "metric_family": metric_family,
        "formula_version": formula_version,
        "channel": channel,
        "sku": sku,
        "window_start_date": window_start_date,
        "window_end_date": window_end_date,
        "avg_daily_units": avg_daily_units,
        "input_refs": [_project_demand_input_ref(ref) for ref in upstream_input_refs],
    }


def _policy_payload_from_fields(
    policy_version: str,
    approval_authority: str,
    authority_reference: str,
    authority_status: str,
    source: str,
    data_as_of: str,
    safety_stock_days: int,
) -> dict[str, object]:
    return {
        "policy_version": policy_version,
        "approval_authority": approval_authority,
        "authority_reference": authority_reference,
        "authority_status": authority_status,
        "source": source,
        "data_as_of": data_as_of,
        "safety_stock_days": safety_stock_days,
    }


def _final_payload(
    formula_version: str, demand_input_hash: str, policy_authority_hash: str
) -> dict[str, object]:
    return {
        "formula_version": formula_version,
        "demand_input_hash": demand_input_hash,
        "policy_authority_hash": policy_authority_hash,
    }


def _canonical_data_as_of(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("data_as_of must be a real ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("data_as_of must include a timezone")
    if parsed.isoformat() != value:
        raise ValueError("data_as_of must round-trip canonically")


@dataclass(frozen=True, slots=True)
class InventorySafetyStockInputRef:
    kind: Literal["DEMAND_VELOCITY", "SAFETY_STOCK_POLICY"]
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

    def __post_init__(self) -> None:
        _require_exact_str(self.kind, "kind")
        for field, value in (
            ("metric_family", self.metric_family),
            ("formula_version", self.formula_version),
            ("policy_version", self.policy_version),
            ("approval_authority", self.approval_authority),
            ("authority_reference", self.authority_reference),
            ("authority_status", self.authority_status),
            ("source", self.source),
            ("data_as_of", self.data_as_of),
            ("channel", self.channel),
            ("sku", self.sku),
            ("window_start_date", self.window_start_date),
            ("window_end_date", self.window_end_date),
            ("avg_daily_units", self.avg_daily_units),
        ):
            _require_optional_exact_str(value, field)
        if self.safety_stock_days is not None and type(self.safety_stock_days) is not int:
            raise TypeError("safety_stock_days must be an exact int or None")
        _require_exact_str(self.input_hash, "input_hash")
        _require_canonical_hash(self.input_hash, "input_hash")
        if type(self.upstream_input_refs) is not tuple:
            raise TypeError("upstream_input_refs must be an exact tuple")
        if any(
            type(ref) is not InventoryDemandVelocityInputRef for ref in self.upstream_input_refs
        ):
            raise TypeError("upstream_input_refs must contain exact demand input refs")
        if self.kind == "DEMAND_VELOCITY":
            self._validate_demand_kind()
        elif self.kind == "SAFETY_STOCK_POLICY":
            self._validate_policy_kind()
        else:
            raise ValueError(f"unsupported input-reference kind: {self.kind!r}")

    def _validate_demand_kind(self) -> None:
        if any(
            value is not None
            for value in (
                self.policy_version,
                self.approval_authority,
                self.authority_reference,
                self.authority_status,
                self.source,
                self.data_as_of,
                self.safety_stock_days,
            )
        ):
            raise ValueError("DEMAND_VELOCITY reference contains policy-only fields")
        if self.metric_family != _DEMAND_METRIC_FAMILY:
            raise ValueError("invalid demand metric_family")
        if self.formula_version != INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION:
            raise ValueError("invalid demand formula_version")
        if any(
            value is None
            for value in (
                self.channel,
                self.sku,
                self.window_start_date,
                self.window_end_date,
                self.avg_daily_units,
            )
        ):
            raise ValueError("DEMAND_VELOCITY reference requires all demand fields")
        window_start = _parse_canonical_date(self.window_start_date, "window_start_date")
        window_end = _parse_canonical_date(self.window_end_date, "window_end_date")
        try:
            expected_start = window_end - timedelta(days=29)
        except OverflowError as exc:
            raise ValueError("window_end_date cannot form an inclusive 30-day window") from exc
        if window_start != expected_start:
            raise ValueError("window_start_date must be window_end_date minus 29 days")
        _validate_canonical_fixed_point(self.avg_daily_units, "avg_daily_units")
        if len(self.upstream_input_refs) != 30:
            raise ValueError("DEMAND_VELOCITY reference requires exactly 30 upstream refs")
        for ref in self.upstream_input_refs:
            ref.__post_init__()
        ordered = tuple(
            sorted(
                self.upstream_input_refs,
                key=lambda ref: (ref.natural_key[1], ref.input_hash),
            )
        )
        if self.upstream_input_refs != ordered:
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
            raise ValueError("upstream refs must cover the complete inclusive 30-day window")
        expected_hash = payload_sha256(
            _demand_payload(
                self.metric_family,
                self.formula_version,
                self.channel,
                self.sku,
                self.window_start_date,
                self.window_end_date,
                self.avg_daily_units,
                self.upstream_input_refs,
            )
        )
        if self.input_hash != expected_hash:
            raise ValueError("demand input_hash does not match its projected payload")

    def _validate_policy_kind(self) -> None:
        if any(
            value is not None
            for value in (
                self.metric_family,
                self.formula_version,
                self.channel,
                self.sku,
                self.window_start_date,
                self.window_end_date,
                self.avg_daily_units,
            )
        ):
            raise ValueError("SAFETY_STOCK_POLICY reference contains demand-only fields")
        if self.policy_version != _POLICY_VERSION:
            raise ValueError("invalid policy_version")
        if self.approval_authority != _APPROVAL_AUTHORITY:
            raise ValueError("invalid approval_authority")
        if self.authority_reference != _POLICY_VERSION:
            raise ValueError("invalid authority_reference")
        if self.authority_status != "APPROVED":
            raise ValueError("authority_status must be APPROVED")
        if self.source != _SOURCE:
            raise ValueError("source must equal the approved policy source")
        _canonical_data_as_of(self.data_as_of)
        if self.safety_stock_days != 7:
            raise ValueError("safety_stock_days must equal 7")
        if self.upstream_input_refs != ():
            raise ValueError("policy reference requires empty upstream_input_refs")
        expected_hash = payload_sha256(
            _policy_payload_from_fields(
                self.policy_version,
                self.approval_authority,
                self.authority_reference,
                self.authority_status,
                self.source,
                self.data_as_of,
                self.safety_stock_days,
            )
        )
        if self.input_hash != expected_hash:
            raise ValueError("policy input_hash does not match its projected payload")


@dataclass(frozen=True, slots=True)
class InventorySafetyStockOutput:
    name: Literal["safety_stock_qty"]
    value: int

    def __post_init__(self) -> None:
        _require_exact_str(self.name, "name")
        if self.name != _OUTPUT_NAME:
            raise ValueError(f"name must be {_OUTPUT_NAME!r}")
        if type(self.value) is not int:
            raise TypeError("value must be an exact int")
        if self.value < 0:
            raise ValueError("value must be nonnegative")


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

    def __post_init__(self) -> None:
        for field, value in (
            ("metric_family", self.metric_family),
            ("formula_version", self.formula_version),
            ("policy_version", self.policy_version),
            ("run_id", self.run_id),
            ("channel", self.channel),
            ("sku", self.sku),
            ("window_start_date", self.window_start_date),
            ("window_end_date", self.window_end_date),
            ("status", self.status),
            ("input_hash", self.input_hash),
        ):
            _require_exact_str(value, field)
        if type(self.outputs) is not tuple:
            raise TypeError("outputs must be an exact tuple")
        if any(type(output) is not InventorySafetyStockOutput for output in self.outputs):
            raise TypeError("outputs must contain exact InventorySafetyStockOutput instances")
        if type(self.input_refs) is not tuple:
            raise TypeError("input_refs must be an exact tuple")
        if any(type(ref) is not InventorySafetyStockInputRef for ref in self.input_refs):
            raise TypeError("input_refs must contain exact InventorySafetyStockInputRef instances")
        if type(self.errors) is not tuple:
            raise TypeError("errors must be an exact tuple")
        if self.errors:
            raise ValueError("V1 SUCCESS result requires empty errors")
        _require_canonical_hash(self.input_hash, "input_hash")
        if self.metric_family != _METRIC_FAMILY:
            raise ValueError("invalid metric_family")
        if self.formula_version != INVENTORY_SAFETY_STOCK_FORMULA_VERSION:
            raise ValueError("invalid formula_version")
        if self.policy_version != _POLICY_VERSION:
            raise ValueError("invalid policy_version")
        if self.status != "SUCCESS":
            raise ValueError("status must be SUCCESS")
        require_valid_run_id(self.run_id)
        _parse_canonical_date(self.window_start_date, "window_start_date")
        _parse_canonical_date(self.window_end_date, "window_end_date")
        if len(self.outputs) != 1:
            raise ValueError("SUCCESS result requires exactly one output")
        self.outputs[0].__post_init__()
        if len(self.input_refs) != 2:
            raise ValueError("input_refs must contain exactly two references")
        demand_ref, policy_ref = self.input_refs
        demand_ref.__post_init__()
        policy_ref.__post_init__()
        if demand_ref.kind != "DEMAND_VELOCITY" or policy_ref.kind != "SAFETY_STOCK_POLICY":
            raise ValueError("input_refs must be ordered DEMAND_VELOCITY then SAFETY_STOCK_POLICY")
        if (
            self.channel != demand_ref.channel
            or self.sku != demand_ref.sku
            or self.window_start_date != demand_ref.window_start_date
            or self.window_end_date != demand_ref.window_end_date
        ):
            raise ValueError("result identity and window must equal the demand reference")
        if self.policy_version != policy_ref.policy_version:
            raise ValueError("result policy_version must equal the policy reference")
        expected_quantity = _safety_stock_quantity(
            demand_ref.avg_daily_units, policy_ref.safety_stock_days
        )
        if self.outputs[0].value != expected_quantity:
            raise ValueError("safety_stock_qty does not match the authoritative demand and policy")
        expected_hash = payload_sha256(
            _final_payload(
                self.formula_version,
                demand_ref.input_hash,
                policy_ref.input_hash,
            )
        )
        if self.input_hash != expected_hash:
            raise ValueError("input_hash does not match the exact final payload")


def _validate_demand_source(
    demand_velocity: InventoryDemandVelocityResult,
) -> InventoryDemandVelocityOutput:
    if (
        type(demand_velocity.metric_family) is not str
        or demand_velocity.metric_family != _DEMAND_METRIC_FAMILY
        or type(demand_velocity.formula_version) is not str
        or demand_velocity.formula_version != INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION
        or type(demand_velocity.outputs) is not tuple
        or len(demand_velocity.outputs) != 1
        or type(demand_velocity.outputs[0]) is not InventoryDemandVelocityOutput
        or type(demand_velocity.outputs[0].name) is not str
        or demand_velocity.outputs[0].name != _DEMAND_OUTPUT_NAME
        or type(demand_velocity.outputs[0].value) is not str
    ):
        raise ValueError("demand result identity or output shape is invalid")
    _validate_canonical_fixed_point(demand_velocity.outputs[0].value, "avg_daily_units")
    return demand_velocity.outputs[0]


def _validate_demand_coherence(demand_velocity: InventoryDemandVelocityResult) -> str:
    if (
        type(demand_velocity.channel) is not str
        or type(demand_velocity.sku) is not str
        or type(demand_velocity.window_start_date) is not str
        or type(demand_velocity.window_end_date) is not str
        or type(demand_velocity.input_refs) is not tuple
    ):
        raise ValueError("demand result coherence fields are invalid")
    window_start = _parse_canonical_date(demand_velocity.window_start_date, "window_start_date")
    window_end = _parse_canonical_date(demand_velocity.window_end_date, "window_end_date")
    try:
        expected_start = window_end - timedelta(days=29)
    except OverflowError as exc:
        raise ValueError("window_end_date cannot form an inclusive 30-day window") from exc
    if window_start != expected_start:
        raise ValueError("demand window must be exactly 30 inclusive days")
    if len(demand_velocity.input_refs) != 30:
        raise ValueError("demand result requires exactly 30 upstream references")
    if any(type(ref) is not InventoryDemandVelocityInputRef for ref in demand_velocity.input_refs):
        raise ValueError("demand input_refs must contain exact upstream reference instances")
    for ref in demand_velocity.input_refs:
        if (
            type(ref.contract_name) is not str
            or ref.contract_name != "CHANNEL_DAILY"
            or type(ref.natural_key) is not tuple
            or len(ref.natural_key) != 3
            or any(type(item) is not str for item in ref.natural_key)
            or type(ref.source) is not str
            or type(ref.data_as_of) is not str
            or type(ref.input_hash) is not str
            or _HASH_PATTERN.fullmatch(ref.input_hash) is None
        ):
            raise ValueError("demand input reference is malformed")
        _parse_canonical_date(ref.natural_key[1], "natural_key stat_date")
    ordered = tuple(
        sorted(
            demand_velocity.input_refs,
            key=lambda ref: (ref.natural_key[1], ref.input_hash),
        )
    )
    if demand_velocity.input_refs != ordered:
        raise ValueError("demand input_refs are not canonically ordered")
    if any(
        ref.natural_key[0] != demand_velocity.channel or ref.natural_key[2] != demand_velocity.sku
        for ref in demand_velocity.input_refs
    ):
        raise ValueError("demand input_refs are incoherent with channel or SKU")
    expected_dates = tuple(
        (window_start + timedelta(days=offset)).isoformat() for offset in range(30)
    )
    actual_dates = tuple(ref.natural_key[1] for ref in demand_velocity.input_refs)
    if actual_dates != expected_dates or expected_dates[-1] != window_end.isoformat():
        raise ValueError("demand input_refs do not cover every window date exactly once")
    output = demand_velocity.outputs[0]
    expected_hash = payload_sha256(
        _demand_payload(
            demand_velocity.metric_family,
            demand_velocity.formula_version,
            demand_velocity.channel,
            demand_velocity.sku,
            demand_velocity.window_start_date,
            demand_velocity.window_end_date,
            output.value,
            demand_velocity.input_refs,
        )
    )
    return expected_hash


def _validate_policy_authority(policy_authority: InventorySafetyStockPolicyAuthority) -> None:
    # Re-run canonical carrier checks to reject mutation through object.__setattr__.
    policy_authority.__post_init__()


def _policy_input_ref(
    policy_authority: InventorySafetyStockPolicyAuthority,
) -> InventorySafetyStockInputRef:
    policy_hash = payload_sha256(
        _policy_payload(
            policy_authority.policy_version,
            policy_authority.approval_authority,
            policy_authority.authority_reference,
            policy_authority.authority_status,
            policy_authority.source,
            policy_authority.data_as_of,
            policy_authority.safety_stock_days,
        )
    )
    return InventorySafetyStockInputRef(
        kind="SAFETY_STOCK_POLICY",
        metric_family=None,
        formula_version=None,
        policy_version=policy_authority.policy_version,
        approval_authority=policy_authority.approval_authority,
        authority_reference=policy_authority.authority_reference,
        authority_status=policy_authority.authority_status,
        source=policy_authority.source,
        data_as_of=policy_authority.data_as_of,
        channel=None,
        sku=None,
        window_start_date=None,
        window_end_date=None,
        avg_daily_units=None,
        safety_stock_days=policy_authority.safety_stock_days,
        input_hash=policy_hash,
        upstream_input_refs=(),
    )


def calculate_inventory_safety_stock(
    demand_velocity: InventoryDemandVelocityResult,
    policy_authority: InventorySafetyStockPolicyAuthority,
    *,
    run_id: str,
    formula_version: str = INVENTORY_SAFETY_STOCK_FORMULA_VERSION,
) -> InventorySafetyStockResult:
    if type(demand_velocity) is not InventoryDemandVelocityResult:
        raise TypeError("demand_velocity must be an exact InventoryDemandVelocityResult")
    if type(demand_velocity.status) is not str or demand_velocity.status != "SUCCESS":
        raise ValueError("demand_velocity status must be SUCCESS")
    output = _validate_demand_source(demand_velocity)
    demand_hash = _validate_demand_coherence(demand_velocity)
    if type(policy_authority) is not InventorySafetyStockPolicyAuthority:
        raise TypeError("policy_authority must be an exact InventorySafetyStockPolicyAuthority")
    _validate_policy_authority(policy_authority)
    _require_exact_str(formula_version, "formula_version")
    if formula_version != INVENTORY_SAFETY_STOCK_FORMULA_VERSION:
        raise UnsupportedFormulaVersionError(f"unsupported formula version: {formula_version!r}")
    _require_exact_str(run_id, "run_id")
    validated_run_id = require_valid_run_id(run_id)

    demand_ref = InventorySafetyStockInputRef(
        kind="DEMAND_VELOCITY",
        metric_family=demand_velocity.metric_family,
        formula_version=demand_velocity.formula_version,
        policy_version=None,
        approval_authority=None,
        authority_reference=None,
        authority_status=None,
        source=None,
        data_as_of=None,
        channel=demand_velocity.channel,
        sku=demand_velocity.sku,
        window_start_date=demand_velocity.window_start_date,
        window_end_date=demand_velocity.window_end_date,
        avg_daily_units=output.value,
        safety_stock_days=None,
        input_hash=demand_hash,
        upstream_input_refs=demand_velocity.input_refs,
    )
    policy_ref = _policy_input_ref(policy_authority)
    input_refs = (demand_ref, policy_ref)
    final_hash = payload_sha256(
        _final_payload(
            formula_version,
            demand_ref.input_hash,
            policy_ref.input_hash,
        )
    )
    quantity = _safety_stock_quantity(output.value, policy_authority.safety_stock_days)
    return InventorySafetyStockResult(
        metric_family=_METRIC_FAMILY,
        formula_version=formula_version,
        policy_version=policy_authority.policy_version,
        run_id=validated_run_id,
        channel=demand_velocity.channel,
        sku=demand_velocity.sku,
        window_start_date=demand_velocity.window_start_date,
        window_end_date=demand_velocity.window_end_date,
        status="SUCCESS",
        outputs=(InventorySafetyStockOutput(_OUTPUT_NAME, quantity),),
        input_refs=input_refs,
        errors=(),
        input_hash=final_hash,
    )
