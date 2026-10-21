"""Synthetic in-memory Source-to-assessment tests; no actual business workbook is read."""

from __future__ import annotations

import builtins
import hashlib
import io
import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, localcontext
from xml.etree.ElementTree import Element, fromstring, tostring
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

import topspeed_ai_os.calculation as calculation
import topspeed_ai_os.calculation.coupang_period_aggregate_inventory_assessment as module
from topspeed_ai_os.calculation.coupang_period_aggregate_inventory_assessment import (
    COUPANG_PERIOD_AGGREGATE_INVENTORY_ASSESSMENT_FORMULA_VERSION as VERSION,
)
from topspeed_ai_os.calculation.coupang_period_aggregate_inventory_assessment import (
    _assess_coupang_period_aggregate_inventory as assess,
)
from topspeed_ai_os.calculation.coupang_period_aggregate_inventory_assessment import (
    _produce_coupang_inventory_availability_observation as produce_inventory,
)
from topspeed_ai_os.calculation.coupang_period_aggregate_inventory_assessment import (
    _produce_coupang_vendor_item_period_aggregate as produce_aggregate,
)
from topspeed_ai_os.core.ids import InvalidIdentifierError
from topspeed_ai_os.tools import ErrorCategory, ExecutionMode, SensitiveBytes, ToolStatus
from topspeed_ai_os.tools.errors import ToolFailure
from topspeed_ai_os.tools.read.coupang_wing_export import CoupangWingExportReadTool

SALES = "SALES_PERIOD_AGGREGATE"
INVENTORY = "INVENTORY_HEALTH_OBSERVATION"
CLOSE = datetime.fromisoformat("2026-10-20T00:00:00+09:00")
RUN = "run_01ARZ3NDEKTSV4RRFFQ69G5FAV"
OTHER_RUN = "run_01ARZ3NDEKTSV4RRFFQ69G5FAW"
SALES_HEADERS = ("등록상품ID", "옵션 ID", "판매방식", "총 판매수", "총 취소된 상품수", "판매량")
INVENTORY_HEADERS = (
    "등록상품 ID",
    "옵션 ID",
    "SKU ID",
    "상품등급",
    "판매가능재고 (실시간 기준)",
    "입고예정재고(실시간 기준)",
    "고객반품 지난 30일(전일자 기준)",
)
# Only approved Architecture identifiers are real. Every quantity below is synthetic.
SALES_ROW = ("15587136792", "92849878174", "로켓그로스", "19", "-2", "17")
INVENTORY_ROW = ("15587136792", "92849878174", "61654574", "NEW", "12", "4", "3")


def independent_hash(payload):
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def book(kind=SALES, *, rows=None, headers=None, created="2026-10-20T00:00:00+09:00"):
    workbook = Workbook()
    workbook.properties.creator = "SYNTHETIC-TEST"
    workbook.properties.created = datetime(2000, 1, 1)
    workbook.properties.modified = datetime(2000, 1, 1)
    sheet = workbook.active
    sheet.title = "vendor item metrics" if kind == SALES else "Excel Data"
    sheet.append(
        headers if headers is not None else SALES_HEADERS if kind == SALES else INVENTORY_HEADERS
    )
    if kind == INVENTORY:
        sheet.append(["SYNTHETIC-EXPLANATION"] * len(INVENTORY_HEADERS))
    for row in rows if rows is not None else [SALES_ROW if kind == SALES else INVENTORY_ROW]:
        sheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    output = io.BytesIO()
    with (
        ZipFile(io.BytesIO(stream.getvalue())) as source,
        ZipFile(output, "w", ZIP_DEFLATED) as target,
    ):
        root = fromstring(source.read("docProps/core.xml"))
        tag = "{http://purl.org/dc/terms/}created"
        for node in list(root):
            if node.tag == tag:
                root.remove(node)
        node = Element(tag)
        node.text = created
        root.append(node)
        for info in source.infolist():
            target.writestr(
                info,
                tostring(root)
                if info.filename == "docProps/core.xml"
                else source.read(info.filename),
            )
    return output.getvalue()


def source_result(kind=SALES, *, raw=None, **book_arguments):
    raw = book(kind, **book_arguments) if raw is None else raw
    tool = CoupangWingExportReadTool(
        clock=lambda: CLOSE + timedelta(days=2), request_id_factory=lambda: "req_" + "c" * 32
    )
    selection = (
        {"period_start": "2026-09-20", "period_end": "2026-10-19", "period_timezone": "Asia/Seoul"}
        if kind == SALES
        else {}
    )
    return tool.read(raw_bytes=raw, export_kind=kind, **selection)


def pair(*, net=17, available=12, inbound=4, returns=3):
    aggregate = produce_aggregate(
        source_result(rows=[(*SALES_ROW[:3], str(net + 2), "-2", str(net))])
    )
    inventory = produce_inventory(
        source_result(
            INVENTORY, rows=[(*INVENTORY_ROW[:4], str(available), str(inbound), str(returns))]
        )
    )
    return aggregate, inventory


def carrier_payload(carrier, kind):
    return {
        "kind": kind,
        **{
            field.name: getattr(carrier, field.name)
            for field in fields(carrier)
            if field.name != "input_hash"
        },
    }


def metadata_change(result, **updates):
    return replace(result, source_metadata=replace(result.source_metadata, **updates))


def specific_change(result, **updates):
    return metadata_change(
        result,
        source_specific_metadata={**result.source_metadata.source_specific_metadata, **updates},
    )


def resign_source(result, *, raw=None, **updates):
    """Synthetic adversary can recalculate hashes; raw-byte authority must still be checked."""
    raw = result.raw_result.reveal() if raw is None else raw
    checksum = "sha256:" + hashlib.sha256(raw).hexdigest()
    metadata = result.source_metadata
    specific = {
        **metadata.source_specific_metadata,
        "raw_artifact_checksum_sha256": checksum,
        **updates,
    }
    envelope = {
        "schema_version": specific["schema_version"],
        "source": metadata.source,
        "source_uri": metadata.source_uri,
        "export_kind": specific["export_kind"],
        "worksheet_name": specific["worksheet_name"],
        "raw_checksum_sha256": checksum,
        "workbook_created_at": specific["workbook_created_at"],
        "period_start": specific["period_start"],
        "period_end": specific["period_end"],
        "period_timezone": specific["period_timezone"],
        "period_close": specific["period_close"],
        "data_as_of": metadata.data_as_of.isoformat(),
        "selection_authority_reference": specific["selection_authority_reference"],
    }
    specific["envelope_sha256"] = independent_hash(envelope)
    return replace(
        result,
        raw_result=SensitiveBytes(raw),
        source_metadata=replace(
            metadata, checksum_sha256=checksum, source_specific_metadata=specific
        ),
    )


def forged(carrier, **updates):
    # Model bypass of shallow/frozen boundaries; consuming callables must revalidate.
    duplicate = object.__new__(type(carrier))
    for field in fields(carrier):
        object.__setattr__(
            duplicate, field.name, updates.get(field.name, getattr(carrier, field.name))
        )
    return duplicate


@pytest.mark.parametrize(
    "kind,producer", [(SALES, produce_aggregate), (INVENTORY, produce_inventory)]
)
def test_successful_source_projection_has_independent_hash_and_preserves_input(kind, producer):
    source = source_result(kind)
    original_metadata = dict(source.source_metadata.source_specific_metadata)
    result = producer(source)
    assert result.channel == "COUPANG"
    assert result.internal_sku == "TS-WAIST-BRACE-L"
    assert result.seller_product_id == "15587136792"
    assert result.vendor_item_id == "92849878174"
    assert result.source == "coupang_wing_export"
    assert (
        result.source_checksum == "sha256:" + hashlib.sha256(source.raw_result.reveal()).hexdigest()
    )
    kind_literal = (
        "COUPANG_VENDOR_ITEM_PERIOD_AGGREGATE"
        if kind == SALES
        else "COUPANG_INVENTORY_AVAILABILITY_OBSERVATION"
    )
    assert result.input_hash == independent_hash(carrier_payload(result, kind_literal))
    assert source.source_metadata.source_specific_metadata == original_metadata
    assert source.status is ToolStatus.SUCCESS
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.input_hash = "sha256:" + "0" * 64
    if kind == SALES:
        assert (result.gross_sold_units, result.cancelled_units, result.net_sold_units) == (
            19,
            2,
            17,
        )
        assert result.exported_at == CLOSE.isoformat()
        assert result.period_timezone == "Asia/Seoul"
        assert not hasattr(result, "coupang_sku_id")
    else:
        assert (result.available_qty, result.inbound_qty, result.customer_return_units) == (
            12,
            4,
            3,
        )
        assert result.observed_at == CLOSE.isoformat()
        assert result.coupang_sku_id == "61654574"


@pytest.mark.parametrize(
    "net", [0, 1, 2, 3, 29, 30, 31, 59, 60, 61, 1000000000000000000000000000001]
)
def test_average_round_half_up_and_ceiling_against_independent_decimal(net):
    aggregate, inventory = pair(net=net, available=100)
    result = assess(aggregate, inventory, run_id=RUN)
    with localcontext() as context:
        context.prec = len(str(net)) + 20
        average = (Decimal(net) / Decimal(30)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        expected_qty = int((average * 7).to_integral_value(rounding=ROUND_CEILING))
        expected_average = format(average, "f").rstrip("0").rstrip(".")
    assert result.avg_daily_units == expected_average
    assert result.indicative_safety_stock_qty == expected_qty
    assert type(result.indicative_safety_stock_qty) is int
    assert result.period_days == 30
    assert result.indicative_safety_stock_days == 7


@pytest.mark.parametrize(
    "available,status",
    [
        (6, "BELOW_INDICATIVE_SAFETY_STOCK"),
        (7, "ABOVE_OR_EQUAL_INDICATIVE_SAFETY_STOCK"),
        (8, "ABOVE_OR_EQUAL_INDICATIVE_SAFETY_STOCK"),
    ],
)
def test_exact_status_boundary(available, status):
    aggregate, inventory = pair(net=30, available=available)
    result = assess(aggregate, inventory, run_id=RUN)
    assert result.avg_daily_units == "1"
    assert result.indicative_safety_stock_qty == 7
    assert result.status == status


@pytest.mark.parametrize("inbound,returns", [(0, 0), (200, 0), (0, 200), (200, 300)])
def test_observational_inbound_and_returns_do_not_change_demand_or_status(inbound, returns):
    aggregate, inventory = pair(net=30, available=6, inbound=inbound, returns=returns)
    result = assess(aggregate, inventory, run_id=RUN)
    assert result.status == "BELOW_INDICATIVE_SAFETY_STOCK"
    assert result.net_sold_units == 30
    assert result.avg_daily_units == "1"
    assert result.indicative_safety_stock_qty == 7
    assert result.available_qty == 6
    assert result.inbound_qty == inbound
    assert result.customer_return_units == returns


def test_final_hash_is_exact_and_excludes_run_and_calculated_output_fields():
    aggregate, inventory = pair()
    first = assess(aggregate, inventory, run_id=RUN)
    second = assess(aggregate, inventory, run_id=OTHER_RUN)
    expected = {
        "formula_version": VERSION,
        "channel": "COUPANG",
        "internal_sku": "TS-WAIST-BRACE-L",
        "period_start_date": "2026-09-20",
        "period_end_date": "2026-10-19",
        "period_days": 30,
        "indicative_safety_stock_days": 7,
        "aggregate_ref.input_hash": aggregate.input_hash,
        "inventory_ref.input_hash": inventory.input_hash,
    }
    assert first.input_hash == second.input_hash == independent_hash(expected)
    assert first.run_id != second.run_id
    assert first.aggregate_ref is aggregate
    assert first.inventory_ref is inventory
    assert not hasattr(first, "__dict__")
    with pytest.raises(FrozenInstanceError):
        first.status = "SYNTHETIC-TAMPER"


@pytest.mark.parametrize(
    "kind,producer,row",
    [(SALES, produce_aggregate, SALES_ROW), (INVENTORY, produce_inventory, INVENTORY_ROW)],
)
@pytest.mark.parametrize("fault", ["missing", "duplicate", "seller_conflict", "option_conflict"])
def test_exact_target_row_and_mapping_are_required(kind, producer, row, fault):
    if fault == "missing":
        rows = [("99999999999", "88888888888", *row[2:])]
    elif fault == "duplicate":
        rows = [row, row]
    elif fault == "seller_conflict":
        rows = [("99999999999", *row[1:])]
    else:
        rows = [(row[0], "88888888888", *row[2:])]
    with pytest.raises(ValueError):
        producer(source_result(kind, rows=rows))


def test_other_options_are_ignored_without_product_name_or_row_order_join():
    other = (SALES_ROW[0], "88888888888", "SYNTHETIC-OTHER-MODE", "999", "0", "999")
    source = source_result(rows=[other, SALES_ROW])
    assert produce_aggregate(source).net_sold_units == 17


@pytest.mark.parametrize(
    "kind,producer,index,value",
    [
        (SALES, produce_aggregate, 2, "SYNTHETIC-OTHER-MODE"),
        (INVENTORY, produce_inventory, 2, "99999999"),
        (INVENTORY, produce_inventory, 3, "USED"),
    ],
)
def test_sales_mode_inventory_grade_and_coupang_sku_are_exact(kind, producer, index, value):
    row = list(SALES_ROW if kind == SALES else INVENTORY_ROW)
    row[index] = value
    with pytest.raises(ValueError):
        producer(source_result(kind, rows=[row]))


def test_duplicate_inventory_target_is_rejected_even_when_only_one_grade_is_new():
    used = (*INVENTORY_ROW[:3], "USED", *INVENTORY_ROW[4:])
    with pytest.raises(ValueError):
        produce_inventory(source_result(INVENTORY, rows=[INVENTORY_ROW, used]))


@pytest.mark.parametrize(
    "kind,producer,indices",
    [(SALES, produce_aggregate, (3, 4, 5)), (INVENTORY, produce_inventory, (4, 5, 6))],
)
@pytest.mark.parametrize(
    "value", ["", "-", " 1", "1 ", "+1", "01", "-0", "1.0", "1e2", "\uff11", True, 1, 1.5]
)
def test_invalid_quantity_lexical_and_builtin_forms_fail_closed(kind, producer, indices, value):
    for index in indices:
        row = list(SALES_ROW if kind == SALES else INVENTORY_ROW)
        row[index] = value
        with pytest.raises((TypeError, ValueError)):
            producer(source_result(kind, rows=[row]))


@pytest.mark.parametrize(
    "quantities",
    [
        ("19", "2", "17"),
        ("19", "-20", "0"),
        ("19", "-2", "16"),
        ("-1", "0", "0"),
        ("19", "0", "-1"),
    ],
)
def test_cancellation_sign_and_reconciliation_failures(quantities):
    with pytest.raises(ValueError):
        produce_aggregate(source_result(rows=[(*SALES_ROW[:3], *quantities)]))


def test_zero_cancellation_and_zero_demand_are_valid_not_fallbacks():
    aggregate = produce_aggregate(source_result(rows=[(*SALES_ROW[:3], "0", "0", "0")]))
    result = assess(aggregate, pair(available=0)[1], run_id=RUN)
    assert result.avg_daily_units == "0"
    assert result.indicative_safety_stock_qty == 0
    assert result.status == "ABOVE_OR_EQUAL_INDICATIVE_SAFETY_STOCK"


@pytest.mark.parametrize("producer", [produce_aggregate, produce_inventory])
@pytest.mark.parametrize("bad", [None, {}, object(), "SYNTHETIC-NOT-TOOLRESULT"])
def test_exact_toolresult_boundary(producer, bad):
    with pytest.raises(TypeError):
        producer(bad)


@pytest.mark.parametrize(
    "kind,producer", [(SALES, produce_aggregate), (INVENTORY, produce_inventory)]
)
@pytest.mark.parametrize("field", ["raw_result", "source_metadata"])
def test_missing_source_boundaries(kind, producer, field):
    source = source_result(kind)
    with pytest.raises(ValueError):
        producer(forged(source, **{field: None}))


def test_failed_and_partial_results_cannot_be_consumed():
    source = source_result()
    for status in (ToolStatus.PARTIAL, ToolStatus.FAILED):
        altered = forged(source, status=status)
        with pytest.raises(ValueError):
            produce_aggregate(altered)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tool_name", "tabular_read"),
        ("operation", "tabular.read_xlsx"),
        ("execution_mode", ExecutionMode.LIVE),
        ("attempt_count", 2),
        ("request_id", "SYNTHETIC-INVALID-ID"),
    ],
)
def test_wrong_source_invocation_authority_is_rejected(field, value):
    with pytest.raises(ValueError):
        produce_aggregate(forged(source_result(), **{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("raw_result", b"SYNTHETIC"),
        ("source_metadata", {}),
        ("parsed_result", {}),
        ("attempt_count", True),
        ("warnings", []),
        ("status", "SUCCESS"),
    ],
)
def test_wrong_exact_source_boundary_types(field, value):
    with pytest.raises(TypeError):
        produce_aggregate(forged(source_result(), **{field: value}))


@pytest.mark.parametrize(
    "kind,producer", [(SALES, produce_aggregate), (INVENTORY, produce_inventory)]
)
def test_raw_bytes_and_both_checksum_locations_are_recomputed(kind, producer):
    source = source_result(kind)
    for changed in (
        replace(
            source, raw_result=SensitiveBytes(source.raw_result.reveal() + b"SYNTHETIC-TAMPER")
        ),
        metadata_change(source, checksum_sha256="sha256:" + "0" * 64),
        specific_change(source, raw_artifact_checksum_sha256="sha256:" + "0" * 64),
    ):
        with pytest.raises(ValueError):
            producer(changed)


@pytest.mark.parametrize(
    "kind,producer", [(SALES, produce_aggregate), (INVENTORY, produce_inventory)]
)
def test_every_source_specific_key_is_required_exact_and_extra_keys_are_rejected(kind, producer):
    source = source_result(kind)
    original = source.source_metadata.source_specific_metadata
    for name in original:
        missing = dict(original)
        missing.pop(name)
        with pytest.raises(ValueError):
            producer(metadata_change(source, source_specific_metadata=missing))
        with pytest.raises((TypeError, ValueError)):
            producer(specific_change(source, **{name: "SYNTHETIC-TAMPER"}))
    with pytest.raises(ValueError):
        producer(specific_change(source, SYNTHETIC_EXTRA="SYNTHETIC-VALUE"))


@pytest.mark.parametrize(
    "kind,producer", [(SALES, produce_aggregate), (INVENTORY, produce_inventory)]
)
def test_recomputed_envelope_hash_cannot_replace_actual_workbook_creation_time(kind, producer):
    source = source_result(kind)
    with pytest.raises(ValueError):
        producer(resign_source(source, workbook_created_at="2026-10-20T00:00:01+09:00"))


@pytest.mark.parametrize("fault", ["header", "formula", "different_rows"])
def test_recomputed_checksums_cannot_bypass_raw_worksheet_revalidation(fault):
    source = source_result()
    if fault == "header":
        raw = book(headers=("SYNTHETIC-WRONG", *SALES_HEADERS[1:]))
    elif fault == "formula":
        raw = book(rows=[(*SALES_ROW[:3], "=1+1", *SALES_ROW[4:])])
    else:
        raw = book(rows=[(*SALES_ROW[:3], "20", "-2", "18")])
    with pytest.raises((ToolFailure, ValueError)):
        produce_aggregate(resign_source(source, raw=raw))


def test_carrier_does_not_retain_mutable_source_metadata_or_parsed_state():
    source = source_result()
    aggregate = produce_aggregate(source)
    snapshot = carrier_payload(aggregate, "COUPANG_VENDOR_ITEM_PERIOD_AGGREGATE")
    source.source_metadata.source_specific_metadata.clear()
    assert carrier_payload(aggregate, "COUPANG_VENDOR_ITEM_PERIOD_AGGREGATE") == snapshot
    assert assess(aggregate, pair()[1], run_id=RUN).net_sold_units == 17


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", "tabular_file"),
        ("source_uri", "SYNTHETIC-WRONG-URI"),
        ("content_type", "text/csv"),
        ("http_status", 200),
        ("modified_time", "SYNTHETIC-TIME"),
        ("data_as_of", CLOSE + timedelta(seconds=1)),
        ("data_as_of", CLOSE.astimezone(UTC)),
        ("fetched_at", CLOSE - timedelta(seconds=1)),
    ],
)
def test_typed_source_metadata_cannot_be_relabelled(field, value):
    with pytest.raises(ValueError):
        produce_aggregate(metadata_change(source_result(), **{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("sheet_name", "SYNTHETIC-WRONG-SHEET"),
        ("headers", ("SYNTHETIC-HEADER",)),
        ("rows", (("SYNTHETIC-ROW",),)),
    ],
)
def test_parsed_values_are_independently_reparsed_from_raw_bytes(field, value):
    source = source_result()
    altered = replace(source, parsed_result=replace(source.parsed_result, **{field: value}))
    with pytest.raises(ValueError):
        produce_aggregate(altered)


def test_equal_but_differently_typed_parsed_cells_are_not_equivalent():
    source = source_result(headers=(*SALES_HEADERS, "SYNTHETIC-EXTRA"), rows=[(*SALES_ROW, 1)])
    parsed = replace(source.parsed_result, rows=((*SALES_ROW, True),))
    assert parsed == source.parsed_result  # Python equality alone would accept bool == int.
    with pytest.raises(ValueError):
        produce_aggregate(replace(source, parsed_result=parsed))


@pytest.mark.parametrize(
    "kind,producer", [(SALES, produce_aggregate), (INVENTORY, produce_inventory)]
)
def test_preclose_workbooks_never_produce_a_carrier(kind, producer):
    source = source_result(kind, created="2026-10-19T23:59:59+09:00")
    assert source.status is ToolStatus.FAILED
    with pytest.raises(ValueError):
        producer(source)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-10-20T00:00:00",
        "2026-10-19T15:00:00Z",
        "2026-10-20T00:00:00.000+09:00",
        "2026-10-20T00:00:00+08:00",
        "2026-10-19T23:59:59+09:00",
    ],
)
def test_carrier_time_representation_and_postclose_eligibility_are_exact(timestamp):
    aggregate, inventory = pair()
    with pytest.raises(ValueError):
        assess(forged(aggregate, exported_at=timestamp), inventory, run_id=RUN)
    with pytest.raises(ValueError):
        assess(aggregate, forged(inventory, observed_at=timestamp), run_id=RUN)


@pytest.mark.parametrize(
    "field,value",
    [
        ("channel", "SYNTHETIC-CHANNEL"),
        ("internal_sku", "SYNTHETIC-SKU"),
        ("seller_product_id", "99999999999"),
        ("vendor_item_id", "88888888888"),
        ("period_start_date", "2026-09-21"),
        ("period_end_date", "2026-10-20"),
        ("period_timezone", "+09:00"),
        ("sales_mode", "SYNTHETIC-MODE"),
        ("gross_sold_units", -1),
        ("cancelled_units", 100),
        ("net_sold_units", 2),
        ("source", "coupang"),
        ("source_uri", "SYNTHETIC-URI"),
        ("source_checksum", "SYNTHETIC-HASH"),
        ("input_hash", "sha256:" + "0" * 64),
    ],
)
def test_assessment_revalidates_aggregate_identity_quantities_period_and_hash(field, value):
    aggregate, inventory = pair()
    with pytest.raises(ValueError):
        assess(forged(aggregate, **{field: value}), inventory, run_id=RUN)


@pytest.mark.parametrize(
    "field,value",
    [
        ("channel", "SYNTHETIC-CHANNEL"),
        ("internal_sku", "SYNTHETIC-SKU"),
        ("seller_product_id", "99999999999"),
        ("vendor_item_id", "88888888888"),
        ("coupang_sku_id", "99999999"),
        ("available_qty", -1),
        ("inbound_qty", -1),
        ("customer_return_units", -1),
        ("source", "coupang"),
        ("source_uri", "SYNTHETIC-URI"),
        ("input_hash", "sha256:" + "0" * 64),
    ],
)
def test_assessment_revalidates_inventory_cross_source_binding_and_hash(field, value):
    aggregate, inventory = pair()
    with pytest.raises(ValueError):
        assess(aggregate, forged(inventory, **{field: value}), run_id=RUN)


@pytest.mark.parametrize("field", ["gross_sold_units", "cancelled_units", "net_sold_units"])
@pytest.mark.parametrize("value", [True, 1.5, "1", None])
def test_exact_builtin_aggregate_quantity_types(field, value):
    aggregate, inventory = pair()
    with pytest.raises(TypeError):
        assess(forged(aggregate, **{field: value}), inventory, run_id=RUN)


@pytest.mark.parametrize("field", ["available_qty", "inbound_qty", "customer_return_units"])
def test_exact_builtin_inventory_quantity_types(field):
    aggregate, inventory = pair()
    with pytest.raises(TypeError):
        assess(aggregate, forged(inventory, **{field: True}), run_id=RUN)


@pytest.mark.parametrize("argument", ["aggregate", "inventory"])
def test_wrong_nested_carrier_identity_is_rejected(argument):
    aggregate, inventory = pair()
    with pytest.raises(TypeError):
        assess(
            None if argument == "aggregate" else aggregate,
            {} if argument == "inventory" else inventory,
            run_id=RUN,
        )


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("run_id", "SYNTHETIC-INVALID-RUN", InvalidIdentifierError),
        ("run_id", True, TypeError),
        ("formula_version", "SYNTHETIC-VERSION", ValueError),
        ("formula_version", None, TypeError),
    ],
)
def test_run_and_formula_version_validation_is_preserved(field, value, error):
    aggregate, inventory = pair()
    arguments = {"run_id": RUN, "formula_version": VERSION, field: value}
    with pytest.raises(error):
        assess(aggregate, inventory, **arguments)


@pytest.mark.parametrize(
    "field,value",
    [
        ("avg_daily_units", "999"),
        ("indicative_safety_stock_qty", 999),
        ("status", "SYNTHETIC-STATUS"),
        ("net_sold_units", 999),
        ("available_qty", 999),
        ("inbound_qty", 999),
        ("customer_return_units", 999),
        ("period_days", 29),
        ("indicative_safety_stock_days", 8),
        ("inventory_observed_at", "SYNTHETIC-TIME"),
        ("input_hash", "sha256:" + "0" * 64),
    ],
)
def test_final_carrier_constructor_rejects_hash_and_output_coherence_tampering(field, value):
    result = assess(*pair(), run_id=RUN)
    with pytest.raises(ValueError):
        replace(result, **{field: value})


def test_source_reader_exceptions_propagate_without_becoming_a_partial_carrier(monkeypatch):
    source = source_result()
    failure = ToolFailure(ErrorCategory.MALFORMED_SOURCE, "SYNTHETIC-PARSER-FAILURE")

    def broken(*args, **kwargs):
        raise failure

    monkeypatch.setattr(module, "_parse_worksheet", broken)
    with pytest.raises(ToolFailure) as caught:
        produce_aggregate(source)
    assert caught.value is failure


def test_calculation_requires_no_raw_bytes_and_claims_no_source_authentication(monkeypatch):
    aggregate, inventory = pair()

    def forbidden(*args, **kwargs):
        raise AssertionError("SYNTHETIC-UNEXPECTED-RAW-READER")

    monkeypatch.setattr(module, "_validated_source", forbidden)
    assert assess(aggregate, inventory, run_id=RUN).aggregate_ref is aggregate


def test_public_exports_are_unchanged_and_all_new_carriers_are_private():
    names = {
        "_CoupangVendorItemPeriodAggregate",
        "_CoupangInventoryAvailabilityObservation",
        "_CoupangPeriodAggregateInventoryAssessment",
        "_assess_coupang_period_aggregate_inventory",
        "_produce_coupang_vendor_item_period_aggregate",
        "_produce_coupang_inventory_availability_observation",
        "COUPANG_PERIOD_AGGREGATE_INVENTORY_ASSESSMENT_FORMULA_VERSION",
    }
    assert names.isdisjoint(calculation.__all__)
    assert all(not hasattr(calculation, name) for name in names)
    assert calculation.calculate_inventory_demand_velocity.__module__.endswith(
        "inventory_demand_velocity"
    )


def test_no_filesystem_network_environment_credential_or_external_write_behavior(monkeypatch):
    import os
    import socket

    sources = source_result(), source_result(INVENTORY)

    def forbidden(*args, **kwargs):
        raise AssertionError("SYNTHETIC-FORBIDDEN-SIDE-EFFECT")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(io, "open", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    aggregate, inventory = produce_aggregate(sources[0]), produce_inventory(sources[1])
    assert (
        assess(aggregate, inventory, run_id=RUN).status == "ABOVE_OR_EQUAL_INDICATIVE_SAFETY_STOCK"
    )
