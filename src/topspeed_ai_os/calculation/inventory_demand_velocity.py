"""Pure CHANNEL_DAILY inventory-demand-velocity calculation."""

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from topspeed_ai_os.contracts import validate_schema_only
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.core.ids import require_valid_run_id

from .contribution_margin import UnsupportedFormulaVersionError

INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION = "topspeed.calculation.inventory_demand_velocity.v1"

_METRIC_FAMILY = "INVENTORY_DEMAND_VELOCITY"
_OUTPUT_NAME = "avg_daily_units"
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_OUTPUT_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,4})?")
_ERROR_FIELDS = {
    "OUT_OF_WINDOW": "stat_date",
    "DUPLICATE_DATE": "stat_date",
    "MISSING_DATE": "stat_date",
    "NEGATIVE_UNITS_SOLD": "units_sold",
}
_ERROR_PRECEDENCE = {
    "OUT_OF_WINDOW": 0,
    "DUPLICATE_DATE": 1,
    "MISSING_DATE": 2,
    "NEGATIVE_UNITS_SOLD": 3,
}


def _require_exact_str(value: object, field: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field} must be an exact str")


def _require_exact_tuple(value: object, field: str, item_type: type[object]) -> None:
    if type(value) is not tuple:
        raise TypeError(f"{field} must be an exact tuple")
    if any(type(item) is not item_type for item in value):
        raise TypeError(f"{field} items must be exact {item_type.__name__} instances")


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


def _require_canonical_hash(value: str, field: str) -> None:
    if _HASH_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a canonical input hash")


def _validate_canonical_output(value: str) -> None:
    if _OUTPUT_PATTERN.fullmatch(value) is None:
        raise ValueError("value must be a canonical nonnegative fixed-point string")
    if "." in value and value.endswith("0"):
        raise ValueError("value must not contain trailing fractional zeros")


def _error_sort_key(error: "InventoryDemandVelocityError") -> tuple[object, ...]:
    return (_ERROR_PRECEDENCE[error.code], error.stat_date, error.input_hashes)


@dataclass(frozen=True, slots=True)
class InventoryDemandVelocityOutput:
    name: Literal["avg_daily_units"]
    value: str

    def __post_init__(self) -> None:
        _require_exact_str(self.name, "name")
        _require_exact_str(self.value, "value")
        if self.name != _OUTPUT_NAME:
            raise ValueError(f"name must be {_OUTPUT_NAME!r}")
        _validate_canonical_output(self.value)


@dataclass(frozen=True, slots=True)
class InventoryDemandVelocityInputRef:
    contract_name: str
    natural_key: tuple[str, str, str]
    source: str
    data_as_of: str
    input_hash: str

    def __post_init__(self) -> None:
        _require_exact_str(self.contract_name, "contract_name")
        if self.contract_name != "CHANNEL_DAILY":
            raise ValueError("contract_name must be 'CHANNEL_DAILY'")
        if type(self.natural_key) is not tuple or len(self.natural_key) != 3:
            raise TypeError("natural_key must be an exact three-item tuple")
        if any(type(item) is not str for item in self.natural_key):
            raise TypeError("natural_key items must be exact str values")
        _parse_canonical_date(self.natural_key[1], "natural_key stat_date")
        _require_exact_str(self.source, "source")
        _require_exact_str(self.data_as_of, "data_as_of")
        _require_exact_str(self.input_hash, "input_hash")
        _require_canonical_hash(self.input_hash, "input_hash")


@dataclass(frozen=True, slots=True)
class InventoryDemandVelocityError:
    code: Literal[
        "OUT_OF_WINDOW",
        "DUPLICATE_DATE",
        "MISSING_DATE",
        "NEGATIVE_UNITS_SOLD",
    ]
    field: str
    stat_date: str
    input_hashes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_exact_str(self.code, "code")
        _require_exact_str(self.field, "field")
        _require_exact_str(self.stat_date, "stat_date")
        _parse_canonical_date(self.stat_date, "stat_date")
        if self.code not in _ERROR_FIELDS:
            raise ValueError(f"unsupported error code: {self.code!r}")
        if self.field != _ERROR_FIELDS[self.code]:
            raise ValueError(f"field is invalid for {self.code}")
        if type(self.input_hashes) is not tuple:
            raise TypeError("input_hashes must be an exact tuple")
        if any(type(input_hash) is not str for input_hash in self.input_hashes):
            raise TypeError("input_hashes items must be exact str values")
        for input_hash in self.input_hashes:
            _require_canonical_hash(input_hash, "input_hashes item")

        if self.code == "MISSING_DATE":
            if self.input_hashes:
                raise ValueError("MISSING_DATE requires empty input_hashes")
        elif self.code == "DUPLICATE_DATE":
            if len(self.input_hashes) < 2 or self.input_hashes != tuple(sorted(self.input_hashes)):
                raise ValueError(
                    "DUPLICATE_DATE requires two or more canonically ordered input_hashes"
                )
        elif len(self.input_hashes) != 1:
            raise ValueError(f"{self.code} requires exactly one input hash")


@dataclass(frozen=True, slots=True)
class InventoryDemandVelocityResult:
    metric_family: str
    formula_version: str
    run_id: str
    channel: str
    sku: str
    window_start_date: str
    window_end_date: str
    status: Literal["SUCCESS", "ERROR"]
    outputs: tuple[InventoryDemandVelocityOutput, ...]
    input_refs: tuple[InventoryDemandVelocityInputRef, ...]
    errors: tuple[InventoryDemandVelocityError, ...]

    def __post_init__(self) -> None:
        for field, value in (
            ("metric_family", self.metric_family),
            ("formula_version", self.formula_version),
            ("run_id", self.run_id),
            ("channel", self.channel),
            ("sku", self.sku),
            ("window_start_date", self.window_start_date),
            ("window_end_date", self.window_end_date),
            ("status", self.status),
        ):
            _require_exact_str(value, field)
        _require_exact_tuple(self.outputs, "outputs", InventoryDemandVelocityOutput)
        _require_exact_tuple(self.input_refs, "input_refs", InventoryDemandVelocityInputRef)
        _require_exact_tuple(self.errors, "errors", InventoryDemandVelocityError)

        if self.metric_family != _METRIC_FAMILY:
            raise ValueError(f"metric_family must be {_METRIC_FAMILY!r}")
        if self.formula_version != INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION:
            raise ValueError(
                f"formula_version must be {INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION!r}"
            )
        if self.status not in {"SUCCESS", "ERROR"}:
            raise ValueError(f"unsupported status: {self.status!r}")

        window_start = _parse_canonical_date(self.window_start_date, "window_start_date")
        window_end = _parse_canonical_date(self.window_end_date, "window_end_date")
        if window_start != window_end - timedelta(days=29):
            raise ValueError("window_start_date must be window_end_date minus 29 days")
        if not self.input_refs:
            raise ValueError("input_refs must contain at least one supplied row reference")
        if self.input_refs != tuple(
            sorted(self.input_refs, key=lambda ref: (ref.natural_key[1], ref.input_hash))
        ):
            raise ValueError("input_refs must be canonically ordered")
        if any(
            ref.natural_key[0] != self.channel or ref.natural_key[2] != self.sku
            for ref in self.input_refs
        ):
            raise ValueError("channel and sku must be coherent with every input reference")
        if self.errors != tuple(sorted(self.errors, key=_error_sort_key)):
            raise ValueError("errors must be canonically ordered")

        if self.status == "SUCCESS":
            self._validate_success(window_start, window_end)
        else:
            self._validate_error(window_start, window_end)

    def _validate_success(self, window_start: date, window_end: date) -> None:
        if (
            len(self.outputs) != 1
            or self.outputs[0].name != _OUTPUT_NAME
            or self.errors
            or len(self.input_refs) != 30
        ):
            raise ValueError("invalid SUCCESS result shape")
        expected_dates = tuple(
            (window_start + timedelta(days=offset)).isoformat() for offset in range(30)
        )
        reference_dates = tuple(ref.natural_key[1] for ref in self.input_refs)
        if reference_dates != expected_dates or expected_dates[-1] != window_end.isoformat():
            raise ValueError("SUCCESS requires exactly one reference for every window date")

    def _validate_error(self, window_start: date, window_end: date) -> None:
        if self.outputs or not self.errors:
            raise ValueError("ERROR requires no outputs and one or more errors")

        required_dates = {
            (window_start + timedelta(days=offset)).isoformat() for offset in range(30)
        }
        hashes_by_date: dict[str, list[str]] = {}
        for ref in self.input_refs:
            hashes_by_date.setdefault(ref.natural_key[1], []).append(ref.input_hash)
        for hashes in hashes_by_date.values():
            hashes.sort()

        expected_out = tuple(
            sorted(
                (
                    InventoryDemandVelocityError(
                        "OUT_OF_WINDOW", "stat_date", ref.natural_key[1], (ref.input_hash,)
                    )
                    for ref in self.input_refs
                    if ref.natural_key[1] not in required_dates
                ),
                key=_error_sort_key,
            )
        )
        expected_duplicate = tuple(
            InventoryDemandVelocityError("DUPLICATE_DATE", "stat_date", stat_date, tuple(hashes))
            for stat_date, hashes in sorted(hashes_by_date.items())
            if len(hashes) > 1
        )
        expected_missing = tuple(
            InventoryDemandVelocityError("MISSING_DATE", "stat_date", stat_date, ())
            for stat_date in sorted(required_dates - hashes_by_date.keys())
        )

        for code, expected in (
            ("OUT_OF_WINDOW", expected_out),
            ("DUPLICATE_DATE", expected_duplicate),
            ("MISSING_DATE", expected_missing),
        ):
            actual = tuple(error for error in self.errors if error.code == code)
            if actual != expected:
                raise ValueError(f"{code} errors are not coherent with input_refs and window")

        available = Counter((ref.natural_key[1], ref.input_hash) for ref in self.input_refs)
        negative = Counter(
            (error.stat_date, error.input_hashes[0])
            for error in self.errors
            if error.code == "NEGATIVE_UNITS_SOLD"
        )
        if any(count > available[key] for key, count in negative.items()):
            raise ValueError("NEGATIVE_UNITS_SOLD errors must reference supplied rows")


def _input_ref(row: Mapping[str, object]) -> InventoryDemandVelocityInputRef:
    payload = {
        "channel": row["channel"],
        "stat_date": row["stat_date"],
        "sku": row["sku"],
        "units_sold": row["units_sold"],
        "source": row["source"],
        "data_as_of": row["data_as_of"],
    }
    return InventoryDemandVelocityInputRef(
        contract_name="CHANNEL_DAILY",
        natural_key=(row["channel"], row["stat_date"], row["sku"]),
        source=row["source"],
        data_as_of=row["data_as_of"],
        input_hash=payload_sha256(payload),
    )


def _round_scaled_units(scaled_units: int) -> int:
    quotient, remainder = divmod(scaled_units, 30)
    if 2 * remainder >= 30:
        quotient += 1
    return quotient


def _rounded_average(total_units: int) -> str:
    quotient = _round_scaled_units(total_units * 10_000)
    if quotient == 0:
        return "0"
    whole, fractional = divmod(quotient, 10_000)
    if fractional == 0:
        return str(whole)
    return f"{whole}.{fractional:04d}".rstrip("0")


def calculate_inventory_demand_velocity(
    channel_daily: tuple[Mapping[str, object], ...],
    *,
    run_id: str,
    window_end_date: str,
    formula_version: str = INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION,
) -> InventoryDemandVelocityResult:
    if type(channel_daily) is not tuple:
        raise TypeError("channel_daily must be an exact tuple")
    for row in channel_daily:
        if not isinstance(row, Mapping):
            raise TypeError("every channel_daily item must satisfy Mapping")
    if not channel_daily:
        raise ValueError("channel_daily must be non-empty")

    _require_exact_str(formula_version, "formula_version")
    if formula_version != INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION:
        raise UnsupportedFormulaVersionError(f"unsupported formula version: {formula_version!r}")

    _require_exact_str(run_id, "run_id")
    validated_run_id = require_valid_run_id(run_id)

    _require_exact_str(window_end_date, "window_end_date")
    parsed_window_end = _parse_canonical_date(window_end_date, "window_end_date")
    try:
        parsed_window_start = parsed_window_end - timedelta(days=29)
    except OverflowError as exc:
        raise ValueError("window_end_date cannot form a complete 30-day window") from exc

    for row in channel_daily:
        validate_schema_only("CHANNEL_DAILY", row)

    channel = channel_daily[0]["channel"]
    if any(row["channel"] != channel for row in channel_daily[1:]):
        raise ValueError("channel_daily must contain exactly one channel")
    sku = channel_daily[0]["sku"]
    if any(row["sku"] != sku for row in channel_daily[1:]):
        raise ValueError("channel_daily must contain exactly one SKU")

    row_refs = tuple((row, _input_ref(row)) for row in channel_daily)
    input_refs = tuple(
        sorted(
            (ref for _row, ref in row_refs),
            key=lambda ref: (ref.natural_key[1], ref.input_hash),
        )
    )
    required_dates = {
        (parsed_window_start + timedelta(days=offset)).isoformat() for offset in range(30)
    }

    errors: list[InventoryDemandVelocityError] = []
    for row, ref in row_refs:
        if row["stat_date"] not in required_dates:
            errors.append(
                InventoryDemandVelocityError(
                    "OUT_OF_WINDOW", "stat_date", row["stat_date"], (ref.input_hash,)
                )
            )

    hashes_by_date: dict[str, list[str]] = {}
    for _row, ref in row_refs:
        hashes_by_date.setdefault(ref.natural_key[1], []).append(ref.input_hash)
    for stat_date, hashes in hashes_by_date.items():
        if len(hashes) > 1:
            errors.append(
                InventoryDemandVelocityError(
                    "DUPLICATE_DATE", "stat_date", stat_date, tuple(sorted(hashes))
                )
            )

    for stat_date in required_dates - hashes_by_date.keys():
        errors.append(InventoryDemandVelocityError("MISSING_DATE", "stat_date", stat_date, ()))

    for row, ref in row_refs:
        if row["units_sold"] < 0:
            errors.append(
                InventoryDemandVelocityError(
                    "NEGATIVE_UNITS_SOLD",
                    "units_sold",
                    row["stat_date"],
                    (ref.input_hash,),
                )
            )

    canonical_errors = tuple(sorted(errors, key=_error_sort_key))
    common = {
        "metric_family": _METRIC_FAMILY,
        "formula_version": INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION,
        "run_id": validated_run_id,
        "channel": channel,
        "sku": sku,
        "window_start_date": parsed_window_start.isoformat(),
        "window_end_date": parsed_window_end.isoformat(),
        "input_refs": input_refs,
    }
    if canonical_errors:
        return InventoryDemandVelocityResult(
            **common,
            status="ERROR",
            outputs=(),
            errors=canonical_errors,
        )

    total_units = sum(row["units_sold"] for row in channel_daily)
    return InventoryDemandVelocityResult(
        **common,
        status="SUCCESS",
        outputs=(InventoryDemandVelocityOutput(_OUTPUT_NAME, _rounded_average(total_units)),),
        errors=(),
    )
