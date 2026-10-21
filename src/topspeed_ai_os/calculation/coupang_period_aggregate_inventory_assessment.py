"""Private, read-only assessment of the approved Coupang aggregate and observation."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from datetime import datetime

from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.core.ids import require_valid_run_id, require_valid_task_id
from topspeed_ai_os.tools.checksum import raw_sha256
from topspeed_ai_os.tools.read.coupang_wing_export import (
    _INVENTORY,
    _SALES,
    _parse_worksheet,
    _workbook_created_at,
)
from topspeed_ai_os.tools.read.tabular import TabularData
from topspeed_ai_os.tools.result import (
    ExecutionMode,
    SensitiveBytes,
    SourceMetadata,
    ToolResult,
    ToolStatus,
)

COUPANG_PERIOD_AGGREGATE_INVENTORY_ASSESSMENT_FORMULA_VERSION = (
    "topspeed.calculation.coupang_period_aggregate_inventory_assessment.v1"
)
_IDENTITY = {
    "channel": "COUPANG",
    "internal_sku": "TS-WAIST-BRACE-L",
    "seller_product_id": "15587136792",
    "vendor_item_id": "92849878174",
}
_COUPANG_SKU = "61654574"
_START = "2026-09-20"
_END = "2026-10-19"
_TIMEZONE = "Asia/Seoul"
_CLOSE_TEXT = "2026-10-20T00:00:00+09:00"
_CLOSE = datetime.fromisoformat(_CLOSE_TEXT)
_SOURCE = "coupang_wing_export"
_SCHEMA = "topspeed.coupang_wing_export.source_envelope.v1"
_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_AUTHORITY = (
    "docs/architecture/"
    "ADR_PHASE5_COUPANG_PERIOD_AGGREGATE_READ_ONLY_INVENTORY_ASSESSMENT_V1.md"
    "@f5952d3dcb808c4cb65e6f18bc64b52afcbeab6d"
)
_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_UNSIGNED = re.compile(r"0|[1-9][0-9]*")
_SIGNED_CANCELLATION = re.compile(r"0|-[1-9][0-9]*")
_IDENTIFIER = re.compile(r"[0-9]+")
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+09:00")
_ABOVE = "ABOVE_OR_EQUAL_INDICATIVE_SAFETY_STOCK"
_BELOW = "BELOW_INDICATIVE_SAFETY_STOCK"


def _exact(value: object, expected: type, label: str) -> None:
    if type(value) is not expected:
        raise TypeError(f"{label} has the wrong exact type")


def _equal(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise ValueError(f"{label} does not match the approved contract")


def _canonical_hash(value: str) -> None:
    if _HASH.fullmatch(value) is None:
        raise ValueError("Hash is not canonical lowercase SHA-256")


def _source_time(value: str) -> datetime:
    if _TIMESTAMP.fullmatch(value) is None:
        raise ValueError("Source time must be canonical whole-second +09:00")
    parsed = datetime.fromisoformat(value)
    if parsed.isoformat() != value or parsed < _CLOSE:
        raise ValueError("Source time is noncanonical or pre-close")
    return parsed


def _carrier_types(carrier: object, integer_fields: set[str]) -> None:
    for field in fields(carrier):
        _exact(
            getattr(carrier, field.name), int if field.name in integer_fields else str, field.name
        )


def _identity(carrier: object) -> None:
    for name, expected in _IDENTITY.items():
        _equal(getattr(carrier, name), expected, name)


def _carrier_payload(carrier: object, kind: str) -> dict[str, object]:
    return {
        "kind": kind,
        **{
            field.name: getattr(carrier, field.name)
            for field in fields(carrier)
            if field.name != "input_hash"
        },
    }


@dataclass(frozen=True, slots=True)
class _CoupangVendorItemPeriodAggregate:
    channel: str
    internal_sku: str
    seller_product_id: str
    vendor_item_id: str
    sales_mode: str
    period_start_date: str
    period_end_date: str
    period_timezone: str
    exported_at: str
    gross_sold_units: int
    cancelled_units: int
    net_sold_units: int
    source: str
    source_uri: str
    source_checksum: str
    input_hash: str

    def __post_init__(self) -> None:
        _validate_aggregate(self)


@dataclass(frozen=True, slots=True)
class _CoupangInventoryAvailabilityObservation:
    channel: str
    internal_sku: str
    seller_product_id: str
    vendor_item_id: str
    coupang_sku_id: str
    observed_at: str
    available_qty: int
    inbound_qty: int
    customer_return_units: int
    source: str
    source_uri: str
    source_checksum: str
    input_hash: str

    def __post_init__(self) -> None:
        _validate_inventory(self)


@dataclass(frozen=True, slots=True)
class _CoupangPeriodAggregateInventoryAssessment:
    formula_version: str
    run_id: str
    channel: str
    internal_sku: str
    period_start_date: str
    period_end_date: str
    period_days: int
    net_sold_units: int
    avg_daily_units: str
    indicative_safety_stock_days: int
    indicative_safety_stock_qty: int
    available_qty: int
    inbound_qty: int
    customer_return_units: int
    inventory_observed_at: str
    status: str
    aggregate_ref: _CoupangVendorItemPeriodAggregate
    inventory_ref: _CoupangInventoryAvailabilityObservation
    input_hash: str

    def __post_init__(self) -> None:
        _validate_assessment(self)


def _validate_aggregate(aggregate: _CoupangVendorItemPeriodAggregate) -> None:
    _exact(aggregate, _CoupangVendorItemPeriodAggregate, "aggregate")
    _carrier_types(aggregate, {"gross_sold_units", "cancelled_units", "net_sold_units"})
    _identity(aggregate)
    _equal(aggregate.sales_mode, "로켓그로스", "sales_mode")
    _equal(aggregate.period_start_date, _START, "period_start_date")
    _equal(aggregate.period_end_date, _END, "period_end_date")
    _equal(aggregate.period_timezone, _TIMEZONE, "period_timezone")
    _source_time(aggregate.exported_at)
    if min(aggregate.gross_sold_units, aggregate.cancelled_units, aggregate.net_sold_units) < 0:
        raise ValueError("Aggregate quantities must be nonnegative")
    if aggregate.net_sold_units != aggregate.gross_sold_units - aggregate.cancelled_units:
        raise ValueError("Aggregate cancellation reconciliation failed")
    _equal(aggregate.source, _SOURCE, "source")
    _equal(aggregate.source_uri, _SALES.source_uri, "source_uri")
    _canonical_hash(aggregate.source_checksum)
    _canonical_hash(aggregate.input_hash)
    _equal(
        aggregate.input_hash,
        payload_sha256(_carrier_payload(aggregate, "COUPANG_VENDOR_ITEM_PERIOD_AGGREGATE")),
        "aggregate input_hash",
    )


def _validate_inventory(inventory: _CoupangInventoryAvailabilityObservation) -> None:
    _exact(inventory, _CoupangInventoryAvailabilityObservation, "inventory")
    _carrier_types(inventory, {"available_qty", "inbound_qty", "customer_return_units"})
    _identity(inventory)
    _equal(inventory.coupang_sku_id, _COUPANG_SKU, "coupang_sku_id")
    _source_time(inventory.observed_at)
    if min(inventory.available_qty, inventory.inbound_qty, inventory.customer_return_units) < 0:
        raise ValueError("Inventory observations must be nonnegative")
    _equal(inventory.source, _SOURCE, "source")
    _equal(inventory.source_uri, _INVENTORY.source_uri, "source_uri")
    _canonical_hash(inventory.source_checksum)
    _canonical_hash(inventory.input_hash)
    _equal(
        inventory.input_hash,
        payload_sha256(_carrier_payload(inventory, "COUPANG_INVENTORY_AVAILABILITY_OBSERVATION")),
        "inventory input_hash",
    )


def _formula_and_run(formula_version: str, run_id: str) -> None:
    _exact(formula_version, str, "formula_version")
    _exact(run_id, str, "run_id")
    _equal(
        formula_version,
        COUPANG_PERIOD_AGGREGATE_INVENTORY_ASSESSMENT_FORMULA_VERSION,
        "formula_version",
    )
    require_valid_run_id(run_id)


def _calculated_values(net_sold_units: int, available_qty: int) -> tuple[str, int, str]:
    quotient, remainder = divmod(net_sold_units * 10000, 30)
    scaled_average = quotient + int(remainder * 2 >= 30)
    whole, fraction = divmod(scaled_average, 10000)
    average = f"{whole}.{fraction:04d}".rstrip("0").rstrip(".") if fraction else str(whole)
    indicative = (scaled_average * 7 + 9999) // 10000
    return average, indicative, _ABOVE if available_qty >= indicative else _BELOW


def _assessment_payload(aggregate, inventory, formula_version) -> dict[str, object]:
    # The two dotted keys are the exact reference-hash entries listed in ADR section 11.
    return {
        "formula_version": formula_version,
        "channel": aggregate.channel,
        "internal_sku": aggregate.internal_sku,
        "period_start_date": aggregate.period_start_date,
        "period_end_date": aggregate.period_end_date,
        "period_days": 30,
        "indicative_safety_stock_days": 7,
        "aggregate_ref.input_hash": aggregate.input_hash,
        "inventory_ref.input_hash": inventory.input_hash,
    }


def _validate_assessment(result: _CoupangPeriodAggregateInventoryAssessment) -> None:
    _exact(result, _CoupangPeriodAggregateInventoryAssessment, "assessment")
    integer_fields = {
        "period_days",
        "net_sold_units",
        "indicative_safety_stock_days",
        "indicative_safety_stock_qty",
        "available_qty",
        "inbound_qty",
        "customer_return_units",
    }
    for field in fields(result):
        if field.name not in {"aggregate_ref", "inventory_ref"}:
            _exact(
                getattr(result, field.name),
                int if field.name in integer_fields else str,
                field.name,
            )
    _validate_aggregate(result.aggregate_ref)
    _validate_inventory(result.inventory_ref)
    _formula_and_run(result.formula_version, result.run_id)
    aggregate, inventory = result.aggregate_ref, result.inventory_ref
    average, indicative, status = _calculated_values(
        aggregate.net_sold_units, inventory.available_qty
    )
    expected = {
        "channel": aggregate.channel,
        "internal_sku": aggregate.internal_sku,
        "period_start_date": aggregate.period_start_date,
        "period_end_date": aggregate.period_end_date,
        "period_days": 30,
        "net_sold_units": aggregate.net_sold_units,
        "avg_daily_units": average,
        "indicative_safety_stock_days": 7,
        "indicative_safety_stock_qty": indicative,
        "available_qty": inventory.available_qty,
        "inbound_qty": inventory.inbound_qty,
        "customer_return_units": inventory.customer_return_units,
        "inventory_observed_at": inventory.observed_at,
        "status": status,
    }
    for name, value in expected.items():
        _equal(getattr(result, name), value, name)
    _canonical_hash(result.input_hash)
    _equal(
        result.input_hash,
        payload_sha256(_assessment_payload(aggregate, inventory, result.formula_version)),
        "assessment input_hash",
    )


def _validated_source(tool_result: ToolResult, spec) -> tuple[TabularData, str, str]:
    """Validate one invocation-owned snapshot; neither hashes nor class identity authenticate it."""
    _exact(tool_result, ToolResult, "tool_result")
    _exact(tool_result.status, ToolStatus, "status")
    _exact(tool_result.execution_mode, ExecutionMode, "execution_mode")
    if tool_result.status is not ToolStatus.SUCCESS:
        raise ValueError("Source result must be SUCCESS")
    if tool_result.source_metadata is None or tool_result.raw_result is None:
        raise ValueError("Source metadata and original bytes are required")
    _exact(tool_result.source_metadata, SourceMetadata, "source_metadata")
    _exact(tool_result.raw_result, SensitiveBytes, "raw_result")
    metadata = tool_result.source_metadata
    raw = tool_result.raw_result.reveal()
    _exact(raw, bytes, "original bytes")
    checksum = raw_sha256(raw)
    _exact(metadata.checksum_sha256, str, "checksum_sha256")
    _equal(metadata.checksum_sha256, checksum, "raw checksum")
    _exact(metadata.source_specific_metadata, dict, "source_specific_metadata")
    specific = metadata.source_specific_metadata.copy()
    for key in specific:
        _exact(key, str, "source-specific metadata key")
    for name in ("tool_name", "operation", "request_id"):
        _exact(getattr(tool_result, name), str, name)
    _equal(tool_result.tool_name, "coupang_wing_export_read", "tool_name")
    _equal(tool_result.operation, spec.operation, "operation")
    _equal(tool_result.execution_mode, ExecutionMode.MOCK, "execution_mode")
    if re.fullmatch(r"req_[0-9a-f]{32}", tool_result.request_id) is None:
        raise ValueError("Invalid source request ID")
    _exact(tool_result.attempt_count, int, "attempt_count")
    _equal(tool_result.attempt_count, 1, "attempt_count")
    _equal(tool_result.error, None, "error")
    _exact(tool_result.warnings, tuple, "warnings")
    for warning in tool_result.warnings:
        _exact(warning, str, "warning")
    for name, validator in (("task_id", require_valid_task_id), ("run_id", require_valid_run_id)):
        value = getattr(tool_result, name)
        if value is not None:
            _exact(value, str, name)
            validator(value)
    for name in ("source", "source_uri", "content_type"):
        _exact(getattr(metadata, name), str, name)
    _equal(metadata.source, _SOURCE, "source")
    _equal(metadata.source_uri, spec.source_uri, "source_uri")
    _equal(metadata.content_type, _CONTENT_TYPE, "content_type")
    _equal(metadata.http_status, None, "http_status")
    _equal(metadata.modified_time, None, "modified_time")
    created = _workbook_created_at(raw)
    created_text = created.isoformat()
    _source_time(created_text)
    _exact(metadata.fetched_at, datetime, "fetched_at")
    if metadata.fetched_at.utcoffset() is None or metadata.fetched_at < created:
        raise ValueError("Source acquisition must be aware and not precede workbook creation")
    data_as_of = _CLOSE if spec is _SALES else created
    _exact(metadata.data_as_of, datetime, "data_as_of")
    _equal(metadata.data_as_of.isoformat(), data_as_of.isoformat(), "data_as_of")
    sales = spec is _SALES
    expected = {
        "schema_version": _SCHEMA,
        "export_kind": "SALES_PERIOD_AGGREGATE" if sales else "INVENTORY_HEALTH_OBSERVATION",
        "worksheet_name": spec.worksheet,
        "workbook_created_at": created_text,
        "raw_artifact_checksum_sha256": checksum,
        "original_source_uri": spec.source_uri,
        "period_start": _START if sales else None,
        "period_end": _END if sales else None,
        "period_timezone": _TIMEZONE if sales else None,
        "period_close": _CLOSE_TEXT if sales else None,
        "selection_authority_reference": _AUTHORITY,
    }
    _equal(set(specific), set(expected) | {"envelope_sha256"}, "metadata key set")
    for name, value in expected.items():
        _exact(specific[name], type(value), name)
        _equal(specific[name], value, name)
    _exact(specific["envelope_sha256"], str, "envelope_sha256")
    envelope = {
        "schema_version": _SCHEMA,
        "source": _SOURCE,
        "source_uri": spec.source_uri,
        "export_kind": expected["export_kind"],
        "worksheet_name": spec.worksheet,
        "raw_checksum_sha256": checksum,
        "workbook_created_at": created_text,
        "period_start": expected["period_start"],
        "period_end": expected["period_end"],
        "period_timezone": expected["period_timezone"],
        "period_close": expected["period_close"],
        "data_as_of": data_as_of.isoformat(),
        "selection_authority_reference": _AUTHORITY,
    }
    _equal(specific["envelope_sha256"], payload_sha256(envelope), "envelope hash")
    table = tool_result.parsed_result
    _exact(table, TabularData, "parsed_result")
    _exact(table.headers, tuple, "headers")
    _exact(table.rows, tuple, "rows")
    _exact(table.sheet_name, str, "sheet_name")
    for header in table.headers:
        _exact(header, str, "header")
    for row in table.rows:
        _exact(row, tuple, "row")
    snapshot = TabularData(
        tuple(table.headers), tuple(tuple(row) for row in table.rows), table.sheet_name
    )
    reparsed = _parse_worksheet(raw, spec)
    if snapshot != reparsed or any(
        type(value) is not type(original)
        for row, original_row in zip(snapshot.rows, reparsed.rows, strict=True)
        for value, original in zip(row, original_row, strict=True)
    ):
        raise ValueError("Parsed worksheet is not bound to the original bytes")
    return snapshot, created_text, checksum


def _target_row(table: TabularData, seller_header: str) -> dict[str, object]:
    seller_index, option_index = table.headers.index(seller_header), table.headers.index("옵션 ID")
    matches = [
        row
        for row in table.rows
        if row[seller_index] == _IDENTITY["seller_product_id"]
        and row[option_index] == _IDENTITY["vendor_item_id"]
    ]
    if len(matches) != 1:
        raise ValueError("Exactly one target product/option row is required")
    row = dict(zip(table.headers, matches[0], strict=True))
    for header in (seller_header, "옵션 ID"):
        _exact(row[header], str, "identifier")
        if _IDENTIFIER.fullmatch(row[header]) is None:
            raise ValueError("Identifiers must be exact ASCII digit strings")
    return row


def _quantity(value: object, *, signed: bool = False) -> int:
    _exact(value, str, "source quantity")
    if (_SIGNED_CANCELLATION if signed else _UNSIGNED).fullmatch(value) is None:
        raise ValueError("Source quantity is not a canonical integer string")
    return int(value)


def _produce_coupang_vendor_item_period_aggregate(
    tool_result: ToolResult,
) -> _CoupangVendorItemPeriodAggregate:
    table, created, checksum = _validated_source(tool_result, _SALES)
    row = _target_row(table, "등록상품ID")
    _exact(row["판매방식"], str, "sales_mode")
    _equal(row["판매방식"], "로켓그로스", "sales_mode")
    gross = _quantity(row["총 판매수"])
    cancelled = -_quantity(row["총 취소된 상품수"], signed=True)
    net = _quantity(row["판매량"])
    values = {
        **_IDENTITY,
        "sales_mode": "로켓그로스",
        "period_start_date": _START,
        "period_end_date": _END,
        "period_timezone": _TIMEZONE,
        "exported_at": created,
        "gross_sold_units": gross,
        "cancelled_units": cancelled,
        "net_sold_units": net,
        "source": _SOURCE,
        "source_uri": _SALES.source_uri,
        "source_checksum": checksum,
    }
    return _CoupangVendorItemPeriodAggregate(
        **values,
        input_hash=payload_sha256({"kind": "COUPANG_VENDOR_ITEM_PERIOD_AGGREGATE", **values}),
    )


def _produce_coupang_inventory_availability_observation(
    tool_result: ToolResult,
) -> _CoupangInventoryAvailabilityObservation:
    table, created, checksum = _validated_source(tool_result, _INVENTORY)
    row = _target_row(table, "등록상품 ID")
    _exact(row["SKU ID"], str, "coupang_sku_id")
    _equal(row["SKU ID"], _COUPANG_SKU, "coupang_sku_id")
    _exact(row["상품등급"], str, "inventory grade")
    _equal(row["상품등급"], "NEW", "inventory grade")
    values = {
        **_IDENTITY,
        "coupang_sku_id": _COUPANG_SKU,
        "observed_at": created,
        "available_qty": _quantity(row["판매가능재고 (실시간 기준)"]),
        "inbound_qty": _quantity(row["입고예정재고(실시간 기준)"]),
        "customer_return_units": _quantity(row["고객반품 지난 30일(전일자 기준)"]),
        "source": _SOURCE,
        "source_uri": _INVENTORY.source_uri,
        "source_checksum": checksum,
    }
    return _CoupangInventoryAvailabilityObservation(
        **values,
        input_hash=payload_sha256({"kind": "COUPANG_INVENTORY_AVAILABILITY_OBSERVATION", **values}),
    )


def _assess_coupang_period_aggregate_inventory(
    aggregate: _CoupangVendorItemPeriodAggregate,
    inventory: _CoupangInventoryAvailabilityObservation,
    *,
    run_id: str,
    formula_version: str = COUPANG_PERIOD_AGGREGATE_INVENTORY_ASSESSMENT_FORMULA_VERSION,
) -> _CoupangPeriodAggregateInventoryAssessment:
    """Revalidate carriers, not raw workbook authenticity; no Source or operational authority."""
    _validate_aggregate(aggregate)
    _validate_inventory(inventory)
    for name in _IDENTITY:
        _equal(getattr(aggregate, name), getattr(inventory, name), "cross-source " + name)
    _formula_and_run(formula_version, run_id)
    average, indicative, status = _calculated_values(
        aggregate.net_sold_units, inventory.available_qty
    )
    return _CoupangPeriodAggregateInventoryAssessment(
        formula_version,
        run_id,
        aggregate.channel,
        aggregate.internal_sku,
        aggregate.period_start_date,
        aggregate.period_end_date,
        30,
        aggregate.net_sold_units,
        average,
        7,
        indicative,
        inventory.available_qty,
        inventory.inbound_qty,
        inventory.customer_return_units,
        inventory.observed_at,
        status,
        aggregate,
        inventory,
        payload_sha256(_assessment_payload(aggregate, inventory, formula_version)),
    )
