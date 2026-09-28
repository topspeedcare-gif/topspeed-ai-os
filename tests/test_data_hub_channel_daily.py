from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from topspeed_ai_os.contracts import validate_contract
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.data_hub import (
    DERIVE_NET_SALES_RULE,
    BatchStatus,
    InMemoryReferencePublisher,
    MappingEntry,
    ReasonCode,
    ingest_ad_daily,
    ingest_channel_daily,
)
from topspeed_ai_os.tools.checksum import raw_sha256
from topspeed_ai_os.tools.read.tabular import TabularData
from topspeed_ai_os.tools.result import (
    ExecutionMode,
    SensitiveBytes,
    SourceMetadata,
    ToolResult,
    ToolStatus,
)

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone(timedelta(hours=9)))
RUN = "run_00000000000000000000000000"
OTHER_RUN = "run_11111111111111111111111111"
KNOWN_SKUS = {"TS-SYNTH-001"}
MAPPING = {("tabular_file", "external_product_id", "ext-001"): "TS-SYNTH-001"}
REQUIRED_HEADERS = (
    "channel",
    "stat_date",
    "external_product_id",
    "gross_sales",
    "orders",
    "units_sold",
    "refunds",
    "refund_amount",
    "data_as_of",
)
HEADERS = (
    *REQUIRED_HEADERS,
    "channel_product_id",
    "channel_fees",
    "settlement_amount",
    "page_views",
)
BASE = {
    "channel": "synthetic_market",
    "stat_date": "2026-09-27",
    "external_product_id": "ext-001",
    "gross_sales": "1290000",
    "orders": "102",
    "units_sold": "108",
    "refunds": "5",
    "refund_amount": "64500",
    "data_as_of": "2026-09-28T06:00:00+09:00",
    "channel_product_id": "channel-987",
    "channel_fees": "132354.00",
    "settlement_amount": "1093146.00",
    "page_views": "3410",
}


def row_for(headers: tuple[object, ...] = HEADERS, **changes: object) -> tuple[object, ...]:
    values = {**BASE, **changes}
    return tuple(values.get(header) for header in headers)


def tool_result(
    *,
    headers: tuple[object, ...] = HEADERS,
    rows: tuple[tuple[object, ...], ...] | None = None,
    raw: bytes = b"channel-daily-synthetic",
    status: ToolStatus = ToolStatus.SUCCESS,
    parsed: object | None = None,
    tool_run_id: str | None = RUN,
) -> ToolResult:
    if rows is None:
        rows = (row_for(headers),)
    if parsed is None:
        parsed = TabularData(headers, rows, None)
    return ToolResult(
        tool_name="tabular_read",
        operation="tabular.read_csv",
        request_id="req_" + "c" * 32,
        status=status,
        execution_mode=ExecutionMode.MOCK,
        task_id=None,
        run_id=tool_run_id,
        source_metadata=SourceMetadata(
            source="tabular_file",
            source_uri="csv://synthetic/channel-daily.csv",
            fetched_at=NOW,
            data_as_of=None,
            checksum_sha256=raw_sha256(raw),
        ),
        raw_result=SensitiveBytes(raw),
        parsed_result=parsed,
    )


def ingest(result: object, **kwargs: object):
    return ingest_channel_daily(
        result,
        run_id=kwargs.pop("run_id", RUN),
        known_skus=kwargs.pop("known_skus", KNOWN_SKUS),
        sku_mapping=kwargs.pop("sku_mapping", MAPPING),
        clock=kwargs.pop("clock", lambda: NOW),
        **kwargs,
    )


def with_values(**changes: object) -> ToolResult:
    return tool_result(rows=(row_for(**changes),), raw=repr(sorted(changes.items())).encode())


def test_valid_required_and_optional_headers_build_full_contract_record():
    required = ingest(
        tool_result(headers=REQUIRED_HEADERS, rows=(row_for(REQUIRED_HEADERS),), raw=b"required")
    )
    optional = ingest(tool_result())
    assert required.status is BatchStatus.READY
    assert required.publish_eligible is True
    assert "channel_product_id" not in required.accepted[0].validated_record
    assert optional.status is BatchStatus.READY
    record = optional.accepted[0]
    validate_contract("CHANNEL_DAILY", record.validated_record, known_skus=KNOWN_SKUS)
    assert record.natural_key == ("synthetic_market", "2026-09-27", "TS-SYNTH-001")
    assert record.contract_name == "CHANNEL_DAILY"
    assert record.provenance.target_contract == "CHANNEL_DAILY"
    assert record.provenance.data_as_of_origin == "source_row:data_as_of"
    assert record.provenance.schema_version == "topspeed.channel_daily.synthetic.v1"


@pytest.mark.parametrize(
    ("gross_sales", "refund_amount", "expected"),
    [
        ("1290000", "64500", "1225500"),
        ("100.50", "0.50", "100"),
        ("10.25", "0.20", "10.05"),
        ("0", "0", "0"),
        ("0.0", "0.00", "0"),
        ("0", "0.00", "0"),
        ("50", "75", "-25"),
        ("-0.00", "0", "0"),
    ],
)
def test_net_sales_formula_and_local_serialization(gross_sales, refund_amount, expected):
    result = ingest(with_values(gross_sales=gross_sales, refund_amount=refund_amount))
    assert result.status is BatchStatus.READY
    actual = result.accepted[0].validated_record["net_sales"]
    assert actual == expected
    assert "e" not in actual.lower()
    assert not actual.endswith(".")
    assert actual == "0" or not actual.endswith("0") or "." not in actual
    assert DERIVE_NET_SALES_RULE in result.accepted[0].provenance.normalization_rules_applied


@pytest.mark.parametrize(
    ("gross_sales", "refund_amount", "expected"),
    [
        (
            "1234567890123456789012345678901234567890",
            "1",
            "1234567890123456789012345678901234567889",
        ),
        (
            "1.123456789012345678901234567890123456789",
            "0.000000000000000000000000000000000000001",
            "1.123456789012345678901234567890123456788",
        ),
        (
            "9999999999999999999999999999999999999999",
            "0.0000000000000000000000000000000000000001",
            "9999999999999999999999999999999999999998.9999999999999999999999999999999999999999",
        ),
        (
            "1000000000000000000000000000000000000000.00000000000000000000",
            "999999999999999999999999999999999999999.99999999999999999999",
            "0.00000000000000000001",
        ),
        (
            "100000000000000000000000000000000000000000000000000",
            "99999999999999999999999999999999999999999999999999",
            "1",
        ),
        (
            "0.0000000000000000000000000000000000000000",
            "0.0000000000000000000000000000000000000000",
            "0",
        ),
    ],
)
def test_net_sales_is_exact_beyond_default_decimal_precision(gross_sales, refund_amount, expected):
    result = ingest(with_values(gross_sales=gross_sales, refund_amount=refund_amount))
    assert result.status is BatchStatus.READY
    assert result.accepted[0].validated_record["net_sales"] == expected


@pytest.mark.parametrize(
    "invalid",
    [
        1.0,
        "NaN",
        "Infinity",
        "-Infinity",
        "1e3",
        "01",
        ".5",
        "1.",
        "12,900",
        "12,900원",
    ],
)
@pytest.mark.parametrize("field", ["gross_sales", "refund_amount"])
def test_source_decimal_rejections_follow_authoritative_contract(field, invalid):
    result = ingest(with_values(**{field: invalid}))
    assert result.status is BatchStatus.REJECTED
    assert result.publish_eligible is False
    assert result.rejected[0].reason_code is ReasonCode.INVALID_SOURCE_VALUE


@pytest.mark.parametrize("field", ["channel_fees", "settlement_amount"])
def test_optional_decimal_rejects_float_and_unsafe_coercion(field):
    assert ingest(with_values(**{field: 1.25})).status is BatchStatus.REJECTED
    assert ingest(with_values(**{field: "1e3"})).status is BatchStatus.REJECTED


@pytest.mark.parametrize(
    "headers",
    [
        tuple(header for header in REQUIRED_HEADERS if header != "orders"),
        (*REQUIRED_HEADERS, "unknown_field"),
        (*REQUIRED_HEADERS, "net_sales"),
        (*REQUIRED_HEADERS, "conversion_rate"),
        (*REQUIRED_HEADERS, "metric_version"),
    ],
)
def test_missing_unknown_and_forbidden_headers_fail_batch_closed(headers):
    result = ingest(tool_result(headers=headers, rows=(row_for(headers),)))
    assert result.status is BatchStatus.REJECTED
    assert result.batch_reason is ReasonCode.INVALID_ROW_SHAPE
    assert result.accepted == ()


def test_duplicate_and_malformed_headers_fail_batch_closed():
    duplicate = (*REQUIRED_HEADERS, "orders")
    duplicate_result = ingest(tool_result(headers=duplicate, rows=(row_for(duplicate),)))
    malformed = TabularData(REQUIRED_HEADERS, (row_for(REQUIRED_HEADERS),), None)
    object.__setattr__(malformed, "headers", [*REQUIRED_HEADERS])
    malformed_result = ingest(tool_result(parsed=malformed))
    assert duplicate_result.batch_reason is ReasonCode.INVALID_ROW_SHAPE
    assert malformed_result.batch_reason is ReasonCode.INVALID_ROW_SHAPE


def test_empty_input_and_invalid_row_width_are_batch_level_failures():
    empty = ingest(tool_result(rows=()))
    width = ingest(tool_result(rows=(row_for(), row_for()[:-1])))
    assert empty.status is BatchStatus.REJECTED
    assert width.status is BatchStatus.REJECTED
    assert width.accepted == ()
    assert width.batch_reason is ReasonCode.INVALID_ROW_SHAPE


def test_malformed_row_container_fails_batch_closed():
    data = TabularData(HEADERS, (row_for(),), None)
    object.__setattr__(data, "rows", [row_for()])
    result = ingest(tool_result(parsed=data))
    assert result.batch_reason is ReasonCode.INVALID_ROW_SHAPE


@pytest.mark.parametrize("field", ["orders", "units_sold", "refunds", "page_views"])
@pytest.mark.parametrize("invalid", [True, False, 1.5, "1.0", "01"])
def test_integer_fields_reject_bool_float_and_unsafe_coercion(field, invalid):
    result = ingest(with_values(**{field: invalid}))
    assert result.status is BatchStatus.REJECTED
    assert result.publish_eligible is False


@pytest.mark.parametrize("stat_date", ["2026-02-30", "2026/09/27", 20260927])
def test_malformed_stat_date_fails(stat_date):
    assert ingest(with_values(stat_date=stat_date)).status is BatchStatus.REJECTED


@pytest.mark.parametrize(
    "data_as_of",
    ["", None, "2026-09-28T06:00:00", "2026-09-28T25:00:00+09:00"],
)
def test_missing_naive_and_invalid_data_as_of_fail(data_as_of):
    result = ingest(with_values(data_as_of=data_as_of))
    assert result.status is BatchStatus.REJECTED
    assert result.publish_eligible is False


def test_created_at_uses_timezone_aware_injected_clock():
    valid = ingest(tool_result(), clock=lambda: NOW)
    invalid = ingest(tool_result(), clock=lambda: datetime(2026, 9, 28, 12, 0))
    assert valid.accepted[0].validated_record["created_at"] == NOW.isoformat()
    assert invalid.status is BatchStatus.REJECTED
    assert invalid.batch_reason is ReasonCode.INVALID_TOOL_RESULT


def test_non_success_and_non_tabular_tool_results_fail_closed():
    partial = ingest(tool_result(status=ToolStatus.PARTIAL))
    non_tabular = ingest(tool_result(parsed={"rows": []}))
    assert partial.rejected[0].reason_code is ReasonCode.INVALID_TOOL_RESULT
    assert non_tabular.rejected[0].reason_code is ReasonCode.INVALID_TOOL_RESULT


@pytest.mark.parametrize("field", ["source_metadata", "raw_result"])
def test_missing_tool_boundary_objects_fail_closed(field):
    result = tool_result()
    object.__setattr__(result, field, None)
    rejected = ingest(result)
    assert rejected.rejected[0].reason_code is ReasonCode.INVALID_TOOL_RESULT


def test_invalid_metadata_and_raw_result_types_fail_closed():
    invalid_metadata = tool_result()
    object.__setattr__(invalid_metadata, "source_metadata", object())
    invalid_raw = tool_result()
    object.__setattr__(invalid_raw, "raw_result", b"not-sensitive-bytes")
    assert ingest(invalid_metadata).status is BatchStatus.REJECTED
    assert ingest(invalid_raw).status is BatchStatus.REJECTED


def test_checksum_unsafe_reference_and_run_mismatch_fail_closed():
    checksum = tool_result()
    object.__setattr__(checksum.source_metadata, "checksum_sha256", raw_sha256(b"other"))
    unsafe = tool_result()
    object.__setattr__(unsafe.source_metadata, "source_uri", "https://token@host/report.csv")
    mismatch = tool_result(tool_run_id=OTHER_RUN)
    assert ingest(checksum).rejected[0].reason_code is ReasonCode.CHECKSUM_MISMATCH
    assert ingest(unsafe).rejected[0].reason_code is ReasonCode.UNSAFE_SOURCE_REFERENCE
    assert ingest(mismatch).rejected[0].reason_code is ReasonCode.INVALID_TOOL_RESULT


def test_unsupported_schema_and_invalid_run_id_fail_closed():
    schema = ingest(tool_result(), schema_version="topspeed.channel_daily.synthetic.v2")
    run_id = ingest(tool_result(), run_id="bad-run")
    assert schema.rejected[0].reason_code is ReasonCode.UNSUPPORTED_SCHEMA
    assert run_id.rejected[0].reason_code is ReasonCode.INVALID_TOOL_RESULT


def test_registered_mapping_passes_and_missing_or_unknown_keys_fail():
    assert ingest(tool_result()).status is BatchStatus.READY
    missing = ingest(with_values(external_product_id=""))
    unknown = ingest(with_values(external_product_id="ext-unknown"))
    assert missing.rejected[0].reason_code is ReasonCode.MISSING_SKU_MAPPING_KEY
    assert unknown.rejected[0].reason_code is ReasonCode.UNKNOWN_SKU


def test_ambiguous_inactive_and_unregistered_mapping_fail_closed():
    ambiguous = (
        MappingEntry("tabular_file", "external_product_id", "ext-001", "TS-SYNTH-001"),
        MappingEntry("tabular_file", "external_product_id", "ext-001", "TS-OTHER-002"),
    )
    inactive = (
        MappingEntry("tabular_file", "external_product_id", "ext-001", "TS-SYNTH-001", False),
    )
    unregistered = {"ext-001": "TS-OTHER-002"}
    assert (
        ingest(tool_result(), sku_mapping=ambiguous).rejected[0].reason_code
        is ReasonCode.AMBIGUOUS_SKU
    )
    assert (
        ingest(tool_result(), sku_mapping=inactive).rejected[0].reason_code
        is ReasonCode.UNKNOWN_SKU
    )
    assert (
        ingest(tool_result(), sku_mapping=unregistered).rejected[0].reason_code
        is ReasonCode.UNREGISTERED_SKU
    )


@pytest.mark.parametrize(
    "mapping",
    [
        {("tabular_file", "external_product_id"): "TS-SYNTH-001"},
        {"ext-001": 123},
        {1: "TS-SYNTH-001"},
        {"ext-001": {"sku": "TS-SYNTH-001", "active": 1}},
        {"ext-001": {"sku": 123}},
    ],
)
def test_malformed_and_unsafe_mapping_values_fail_batch_closed(mapping):
    result = ingest(tool_result(), sku_mapping=mapping)
    assert result.status is BatchStatus.REJECTED
    assert result.batch_reason is ReasonCode.UNSUPPORTED_MAPPING


def test_optional_blank_normalization_is_explicit_in_provenance():
    result = ingest(
        with_values(
            channel_product_id="",
            channel_fees="",
            settlement_amount=None,
            page_views="",
        )
    )
    record = result.accepted[0]
    assert record.validated_record["channel_product_id"] is None
    assert record.validated_record["channel_fees"] is None
    assert record.validated_record["settlement_amount"] is None
    assert record.validated_record["page_views"] is None
    assert record.provenance.normalization_rules_applied == (
        DERIVE_NET_SALES_RULE,
        "blank_channel_product_id_to_none",
        "blank_channel_fees_to_none",
        "blank_settlement_amount_to_none",
        "blank_page_views_to_none",
    )


def test_target_does_not_generate_phase5_or_version_fields():
    record = ingest(tool_result()).accepted[0].validated_record
    forbidden = {
        "conversion_rate",
        "metric_version",
        "ctr",
        "cvr",
        "roas",
        "average_order_value",
        "contribution_margin",
        "forecast",
    }
    assert forbidden.isdisjoint(record)


def test_business_hash_includes_net_sales_and_excludes_operational_values():
    first = ingest(tool_result(raw=b"business-one"))
    record = first.accepted[0]
    expected_payload = {
        key: record.validated_record.get(key)
        for key in (
            "channel",
            "stat_date",
            "sku",
            "channel_product_id",
            "gross_sales",
            "net_sales",
            "orders",
            "units_sold",
            "refunds",
            "refund_amount",
            "channel_fees",
            "settlement_amount",
            "page_views",
        )
    }
    assert record.canonical_business_hash == payload_sha256(expected_payload)
    changed_provenance = ingest(
        tool_result(
            rows=(row_for(data_as_of="2026-09-29T06:00:00+09:00"),),
            raw=b"business-two",
            tool_run_id=OTHER_RUN,
        ),
        run_id=OTHER_RUN,
        clock=lambda: NOW + timedelta(days=1),
        existing=first.accepted,
    )
    assert changed_provenance.status is BatchStatus.DUPLICATE
    assert changed_provenance.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE


def test_source_duplicate_is_non_publishable_and_mapping_fingerprint_reprocesses():
    first = ingest(tool_result())
    duplicate = ingest(tool_result(), existing=first.accepted)
    changed_mapping = ingest(
        tool_result(),
        sku_mapping={
            ("tabular_file", "external_product_id", "ext-001"): "TS-SYNTH-001",
            ("other_source", "external_product_id", "unused"): "TS-SYNTH-001",
        },
        existing=first.accepted,
    )
    assert duplicate.status is BatchStatus.DUPLICATE
    assert duplicate.batch_reason is ReasonCode.SOURCE_DUPLICATE
    assert duplicate.publish_eligible is False
    assert changed_mapping.status is BatchStatus.DUPLICATE
    assert changed_mapping.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE


def test_business_duplicate_and_natural_key_conflict_are_distinct():
    first = ingest(tool_result(raw=b"first"))
    duplicate = ingest(tool_result(raw=b"second"), existing=first.accepted)
    conflict = ingest(with_values(orders="103"), existing=first.accepted)
    assert duplicate.status is BatchStatus.DUPLICATE
    assert duplicate.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE
    assert conflict.status is BatchStatus.CONFLICT
    assert conflict.conflicts[0].conflict_reason is ReasonCode.NATURAL_KEY_CONFLICT
    assert conflict.publish_eligible is False


def test_batch_statuses_and_publish_gate():
    duplicate_rows = ingest(tool_result(rows=(row_for(), row_for()), raw=b"duplicate-rows"))
    partial = ingest(
        tool_result(rows=(row_for(), row_for(external_product_id="unknown")), raw=b"partial")
    )
    rejected = ingest(with_values(external_product_id="unknown"))
    assert duplicate_rows.status is BatchStatus.READY
    assert len(duplicate_rows.accepted) == 1
    assert len(duplicate_rows.duplicates) == 1
    assert duplicate_rows.publish_eligible is True
    assert partial.status is BatchStatus.PARTIAL
    assert partial.publish_eligible is False
    assert rejected.status is BatchStatus.REJECTED
    assert rejected.publish_eligible is False


def test_failed_channel_publication_preserves_current_and_last_identity():
    first = ingest(tool_result(raw=b"publish-first"))
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(first) is True
    current = publisher.current
    identity = publisher.last_ingestion_identity
    conflict = ingest(with_values(orders="999"), existing=first.accepted)
    assert publisher.publish(conflict) is False
    assert publisher.current == current
    assert publisher.last_ingestion_identity == identity


AD_HEADERS = (
    "channel",
    "stat_date",
    "external_product_id",
    "campaign_id",
    "impressions",
    "clicks",
    "ad_spend",
    "ad_orders",
    "ad_revenue",
    "data_as_of",
)
AD_ROW = (
    "synthetic_market",
    "2026-09-27",
    "ext-001",
    "campaign-1",
    "1000",
    "10",
    "20.00",
    "2",
    "100.00",
    "2026-09-28T06:00:00+09:00",
)


def ad_result(raw: bytes = b"cross-contract") -> ToolResult:
    return replace(
        tool_result(raw=raw),
        parsed_result=TabularData(AD_HEADERS, (AD_ROW,), None),
    )


def test_ad_and_channel_contracts_coexist_without_identity_or_state_collision():
    raw = b"cross-contract"
    ad = ingest_ad_daily(
        ad_result(raw),
        run_id=RUN,
        known_skus=KNOWN_SKUS,
        sku_mapping=MAPPING,
        clock=lambda: NOW,
    )
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(ad) is True
    channel = ingest(tool_result(raw=raw), existing=publisher.current or ())
    assert channel.status is BatchStatus.READY
    assert channel.batch_reason is None
    assert (
        channel.accepted[0].provenance.ingestion_identity
        != ad.accepted[0].provenance.ingestion_identity
    )
    assert publisher.publish(channel) is True

    ad_key = ("synthetic_market", "2026-09-27", "TS-SYNTH-001", "campaign-1", None)
    channel_key = ("synthetic_market", "2026-09-27", "TS-SYNTH-001")
    assert publisher.get_current("AD_DAILY", ad_key) == ad.accepted[0]
    assert publisher.get_current("CHANNEL_DAILY", channel_key) == channel.accepted[0]
    assert publisher.current == (*ad.accepted, *channel.accepted)
    assert channel.duplicates == ()
    assert channel.conflicts == ()


def test_failed_channel_batch_preserves_both_contracts_and_last_identity():
    ad = ingest_ad_daily(
        ad_result(b"ad-state"),
        run_id=RUN,
        known_skus=KNOWN_SKUS,
        sku_mapping=MAPPING,
        clock=lambda: NOW,
    )
    channel = ingest(tool_result(raw=b"channel-state"), existing=ad.accepted)
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(ad)
    assert publisher.publish(channel)
    before = publisher.current
    last_identity = publisher.last_ingestion_identity
    failed = ingest(
        with_values(orders="777"),
        existing=publisher.current or (),
    )
    assert failed.status is BatchStatus.CONFLICT
    assert publisher.publish(failed) is False
    assert publisher.current == before
    assert publisher.last_ingestion_identity == last_identity
