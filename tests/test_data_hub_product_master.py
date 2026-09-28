from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from topspeed_ai_os.contracts import validate_contract
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.data_hub import (
    PRODUCT_MASTER_SCHEMA,
    BatchStatus,
    InMemoryReferencePublisher,
    ReasonCode,
    ingest_ad_daily,
    ingest_channel_daily,
    ingest_product_master,
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
RUN = "run_01J00000000000000000000000"
OTHER_RUN = "run_01J00000000000000000000001"
SKU = "TS-SYNTH-001"
REQUIRED_HEADERS = (
    "sku",
    "product_name",
    "category",
    "stage",
    "status",
    "currency",
    "data_as_of",
)
OPTIONAL_HEADERS = (
    "channel_ids",
    "grade",
    "supplier",
    "purchase_cost",
    "sale_price",
    "fee_rate",
    "fulfillment_cost",
    "expected_return_cost",
    "other_variable_cost",
)
HEADERS = (*REQUIRED_HEADERS, *OPTIONAL_HEADERS)
VALUES: dict[str, object] = {
    "sku": SKU,
    "product_name": "Synthetic Product",
    "category": "Kitchen",
    "stage": "TEST",
    "status": "ACTIVE",
    "currency": "KRW",
    "data_as_of": "2026-09-28T06:00:00+09:00",
    "channel_ids": '{"coupang":"vendor-1","nested":{"id":2}}',
    "grade": "B",
    "supplier": "SUP-001",
    "purchase_cost": "5200",
    "sale_price": "12900",
    "fee_rate": "0.108",
    "fulfillment_cost": "2500",
    "expected_return_cost": "350",
    "other_variable_cost": "100",
}
DECIMAL_FIELDS = OPTIONAL_HEADERS[3:]


def row_for(headers: tuple[str, ...] = HEADERS, **changes: object) -> tuple[object, ...]:
    values = {**VALUES, **changes}
    return tuple(values[header] for header in headers)


def tool_result(
    *,
    headers: tuple[str, ...] = HEADERS,
    rows: tuple[tuple[object, ...], ...] | None = None,
    raw: bytes = b"product-master",
    parsed: object | None = None,
    status: ToolStatus = ToolStatus.SUCCESS,
    source: str = "tabular_file",
    source_uri: str = "csv://synthetic/product-master.csv",
    tool_run_id: str | None = RUN,
) -> ToolResult:
    if rows is None:
        rows = (row_for(headers),)
    if parsed is None:
        parsed = TabularData(headers, rows, None)
    return ToolResult(
        tool_name="tabular_read",
        operation="tabular.read_csv",
        request_id="req_" + ("1" * 32),
        status=status,
        execution_mode=ExecutionMode.MOCK,
        task_id=None,
        run_id=tool_run_id,
        source_metadata=SourceMetadata(
            source=source,
            source_uri=source_uri,
            fetched_at=NOW,
            data_as_of=None,
            checksum_sha256=raw_sha256(raw),
        ),
        raw_result=SensitiveBytes(raw),
        parsed_result=parsed,
    )


def ingest(result: object | None = None, **kwargs: object):
    return ingest_product_master(
        tool_result() if result is None else result,
        run_id=kwargs.pop("run_id", RUN),
        clock=kwargs.pop("clock", lambda: NOW),
        **kwargs,
    )


def with_values(**changes: object) -> ToolResult:
    return tool_result(rows=(row_for(**changes),), raw=repr(sorted(changes.items())).encode())


def test_required_only_valid_row_and_contract_validation():
    result = ingest(
        tool_result(
            headers=REQUIRED_HEADERS,
            rows=(row_for(REQUIRED_HEADERS),),
            raw=b"required-only",
        )
    )
    assert result.status is BatchStatus.READY
    record = result.accepted[0]
    validate_contract("PRODUCT_MASTER", record.validated_record)
    assert record.natural_key == (SKU,)
    assert record.contract_name == "PRODUCT_MASTER"
    assert record.provenance.target_contract == "PRODUCT_MASTER"
    assert record.provenance.schema_version == PRODUCT_MASTER_SCHEMA
    assert set(record.validated_record) == {
        *REQUIRED_HEADERS,
        "source",
        "created_at",
        "updated_at",
    }


def test_all_optional_fields_are_accepted_without_margins():
    result = ingest()
    record = result.accepted[0].validated_record
    assert result.status is BatchStatus.READY
    assert record["channel_ids"] == {"coupang": "vendor-1", "nested": {"id": 2}}
    assert set(OPTIONAL_HEADERS) <= set(record)
    assert "contribution_margin" not in record
    assert "contribution_margin_rate" not in record


@pytest.mark.parametrize("missing", REQUIRED_HEADERS)
def test_missing_required_headers_fail_closed(missing):
    headers = tuple(field for field in REQUIRED_HEADERS if field != missing)
    result = ingest(tool_result(headers=headers, rows=(row_for(headers),)))
    assert result.batch_reason is ReasonCode.INVALID_ROW_SHAPE
    assert result.accepted == ()


@pytest.mark.parametrize("field", REQUIRED_HEADERS)
@pytest.mark.parametrize("blank", ["", None])
def test_blank_required_values_are_rejected(field, blank):
    result = ingest(with_values(**{field: blank}))
    assert result.status is BatchStatus.REJECTED
    assert result.publish_eligible is False


@pytest.mark.parametrize(
    "extra",
    [
        "unknown_field",
        "source",
        "created_at",
        "updated_at",
        "contribution_margin",
        "contribution_margin_rate",
    ],
)
def test_unknown_and_forbidden_headers_fail_batch_closed(extra):
    headers = (*REQUIRED_HEADERS, extra)
    values = {**VALUES, extra: "x"}
    result = ingest(tool_result(headers=headers, rows=(tuple(values[key] for key in headers),)))
    assert result.batch_reason is ReasonCode.INVALID_ROW_SHAPE


def test_duplicate_and_malformed_headers_and_rows_fail_batch_closed():
    duplicate = (*REQUIRED_HEADERS, "sku")
    duplicate_result = ingest(tool_result(headers=duplicate, rows=(row_for(duplicate),)))
    malformed = TabularData(REQUIRED_HEADERS, (row_for(REQUIRED_HEADERS),), None)
    object.__setattr__(malformed, "headers", [*REQUIRED_HEADERS])
    malformed_result = ingest(tool_result(parsed=malformed))
    width_result = ingest(tool_result(rows=(row_for(), row_for()[:-1])))
    assert duplicate_result.batch_reason is ReasonCode.INVALID_ROW_SHAPE
    assert malformed_result.batch_reason is ReasonCode.INVALID_ROW_SHAPE
    assert width_result.batch_reason is ReasonCode.INVALID_ROW_SHAPE


@pytest.mark.parametrize("sku", ["bad-sku", "SINGLE", "TS_SYNTH_001", "TS-Ä-001"])
def test_sku_syntax_uses_product_master_contract(sku):
    result = ingest(with_values(sku=sku))
    assert result.status is BatchStatus.REJECTED
    assert result.rejected[0].reason_code is ReasonCode.CONTRACT_VALIDATION_FAILED


def test_source_sku_is_used_directly_without_generation_or_mapping():
    result = ingest(with_values(sku="INTERNAL-DIRECT-900"))
    record = result.accepted[0]
    expected = payload_sha256(
        {"strategy": "direct_internal_sku", "schema_version": PRODUCT_MASTER_SCHEMA}
    )
    assert record.validated_record["sku"] == "INTERNAL-DIRECT-900"
    assert record.natural_key == ("INTERNAL-DIRECT-900",)
    assert record.provenance.mapping_fingerprint == expected


@pytest.mark.parametrize(
    ("field", "valid", "invalid"),
    [
        ("stage", "CORE", "GROW"),
        ("grade", "S", "C"),
        ("status", "PAUSED", "APPROVED"),
    ],
)
def test_lifecycle_fields_are_contract_enum_validation_only(field, valid, invalid):
    assert ingest(with_values(**{field: valid})).status is BatchStatus.READY
    assert ingest(with_values(**{field: invalid})).status is BatchStatus.REJECTED


@pytest.mark.parametrize("field", ["product_name", "category"])
def test_text_fields_reject_non_text_and_blank(field):
    assert ingest(with_values(**{field: 123})).status is BatchStatus.REJECTED
    assert ingest(with_values(**{field: "   "})).status is BatchStatus.REJECTED


def test_optional_supplier_rejects_non_text_and_normalizes_blank_to_null():
    assert ingest(with_values(supplier=123)).status is BatchStatus.REJECTED
    blank = ingest(with_values(supplier="   "))
    assert blank.accepted[0].validated_record["supplier"] is None
    assert "blank_supplier_to_none" in blank.accepted[0].provenance.normalization_rules_applied


@pytest.mark.parametrize("currency", ["krw", "KR", "KRWW", 123])
def test_currency_uses_contract_syntax(currency):
    assert ingest(with_values(currency=currency)).status is BatchStatus.REJECTED


@pytest.mark.parametrize("field", DECIMAL_FIELDS)
@pytest.mark.parametrize("value", ["0", "0.50", "1.000"])
def test_all_six_source_decimals_use_frozen_canonical_semantics(field, value):
    result = ingest(with_values(**{field: value}))
    assert result.status is BatchStatus.READY
    assert result.accepted[0].validated_record[field] == value


@pytest.mark.parametrize("field", DECIMAL_FIELDS)
@pytest.mark.parametrize(
    "invalid",
    [1.0, "1e3", "01", ".5", "1.", "1,000", "$1", "NaN", "Infinity", "-Infinity"],
)
def test_invalid_decimal_forms_are_rejected(field, invalid):
    assert ingest(with_values(**{field: invalid})).status is BatchStatus.REJECTED


@pytest.mark.parametrize("value", ["0", "0.0", "1", "1.000"])
def test_fee_rate_inclusive_zero_to_one_bounds(value):
    assert ingest(with_values(fee_rate=value)).status is BatchStatus.READY


@pytest.mark.parametrize("value", ["-0.01", "1.01", "2"])
def test_fee_rate_out_of_bounds_is_rejected(value):
    assert ingest(with_values(fee_rate=value)).status is BatchStatus.REJECTED


@pytest.mark.parametrize("field", [field for field in DECIMAL_FIELDS if field != "fee_rate"])
def test_no_nonnegative_constraint_is_invented_for_cost_or_price_fields(field):
    result = ingest(with_values(**{field: "-1.25"}))
    assert result.status is BatchStatus.READY
    assert result.accepted[0].validated_record[field] == "-1.25"


@pytest.mark.parametrize("field", DECIMAL_FIELDS)
@pytest.mark.parametrize("blank", ["", None, "   "])
def test_optional_decimal_blanks_normalize_to_null(field, blank):
    result = ingest(with_values(**{field: blank}))
    record = result.accepted[0]
    assert record.validated_record[field] is None
    assert f"blank_{field}_to_none" in record.provenance.normalization_rules_applied


def test_channel_ids_omitted_and_blank_behaviors_are_distinct():
    omitted_headers = tuple(field for field in HEADERS if field != "channel_ids")
    omitted = ingest(
        tool_result(
            headers=omitted_headers,
            rows=(row_for(omitted_headers),),
            raw=b"omitted-channel-ids",
        )
    )
    blank = ingest(with_values(channel_ids=""))
    none = ingest(with_values(channel_ids=None))
    assert "channel_ids" not in omitted.accepted[0].validated_record
    assert blank.accepted[0].validated_record["channel_ids"] is None
    assert none.accepted[0].validated_record["channel_ids"] is None
    assert "blank_channel_ids_to_none" in blank.accepted[0].provenance.normalization_rules_applied


def test_channel_ids_valid_json_object_text_is_parsed():
    result = ingest(with_values(channel_ids=' { "z": 1, "a": [true, null] } '))
    assert result.accepted[0].validated_record["channel_ids"] == {
        "z": 1,
        "a": [True, None],
    }


@pytest.mark.parametrize("value", ["{", '{"a":}', "not-json", '{"a":NaN}'])
def test_channel_ids_malformed_json_is_rejected(value):
    assert ingest(with_values(channel_ids=value)).status is BatchStatus.REJECTED


@pytest.mark.parametrize("value", ["[]", '"text"', "1", "true", "null"])
def test_channel_ids_non_object_json_roots_are_rejected(value):
    assert ingest(with_values(channel_ids=value)).status is BatchStatus.REJECTED


@pytest.mark.parametrize("value", [{"native": "mapping"}, ["native-list"], 1, True])
def test_channel_ids_native_non_text_values_are_rejected(value):
    assert ingest(with_values(channel_ids=value)).status is BatchStatus.REJECTED


@pytest.mark.parametrize("value", ['{"a":1,"a":2}', '{"outer":{"x":1,"x":2}}'])
def test_channel_ids_duplicate_keys_are_rejected_at_any_depth(value):
    assert ingest(with_values(channel_ids=value)).status is BatchStatus.REJECTED


@pytest.mark.parametrize(
    "data_as_of",
    ["", None, "2026-09-28T06:00:00", "2026-09-28T25:00:00+09:00", 20260928],
)
def test_data_as_of_must_be_valid_timezone_aware_source_datetime(data_as_of):
    result = ingest(with_values(data_as_of=data_as_of))
    assert result.status is BatchStatus.REJECTED


def test_timezone_aware_clock_sets_equal_created_and_updated_at():
    result = ingest(clock=lambda: NOW)
    record = result.accepted[0].validated_record
    assert record["created_at"] == NOW.isoformat()
    assert record["updated_at"] == record["created_at"]
    assert ingest(clock=lambda: datetime(2026, 9, 28, 12)).status is BatchStatus.REJECTED


def test_source_comes_only_from_verified_metadata():
    result = ingest(tool_result(source="verified_internal_source"))
    record = result.accepted[0]
    assert record.validated_record["source"] == "verified_internal_source"
    assert record.provenance.source == "verified_internal_source"
    assert "source" not in HEADERS


def test_checksum_source_run_boundary_and_schema_fail_closed():
    checksum = tool_result()
    object.__setattr__(checksum.source_metadata, "checksum_sha256", raw_sha256(b"other"))
    unsafe = tool_result(source_uri="https://secret@host/report.csv")
    mismatch = tool_result(tool_run_id=OTHER_RUN)
    non_tabular = tool_result(parsed={"rows": []})
    partial = tool_result(status=ToolStatus.PARTIAL)
    missing_raw = tool_result()
    object.__setattr__(missing_raw, "raw_result", None)
    missing_metadata = tool_result()
    object.__setattr__(missing_metadata, "source_metadata", None)
    schema = ingest(schema_version="topspeed.product_master.synthetic.v2")
    assert ingest(checksum).batch_reason is ReasonCode.CHECKSUM_MISMATCH
    assert ingest(unsafe).batch_reason is ReasonCode.UNSAFE_SOURCE_REFERENCE
    assert ingest(mismatch).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert ingest(non_tabular).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert ingest(partial).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert ingest(missing_raw).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert ingest(missing_metadata).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert schema.batch_reason is ReasonCode.UNSUPPORTED_SCHEMA


def test_ingestion_identity_contains_required_inputs():
    result = ingest()
    record = result.accepted[0]
    expected = payload_sha256(
        {
            "target_contract": "PRODUCT_MASTER",
            "schema_version": PRODUCT_MASTER_SCHEMA,
            "source_checksum": record.provenance.source_checksum,
            "mapping_fingerprint": record.provenance.mapping_fingerprint,
        }
    )
    assert record.provenance.ingestion_identity == expected == result.ingestion_identity


def test_final_validation_is_exact_product_master_contract_call(monkeypatch):
    calls: list[tuple[object, ...]] = []

    def spy(*args, **kwargs):
        calls.append((*args, kwargs))

    monkeypatch.setattr("topspeed_ai_os.data_hub.product_master.validate_contract", spy)
    result = ingest()
    assert result.status is BatchStatus.READY
    assert calls == [("PRODUCT_MASTER", result.accepted[0].validated_record, {})]


def test_no_known_skus_requirement_or_parameter():
    assert ingest().status is BatchStatus.READY
    with pytest.raises(TypeError):
        ingest_product_master(tool_result(), run_id=RUN, clock=lambda: NOW, known_skus={SKU})


def test_business_hash_covers_every_owned_business_field():
    result = ingest()
    record = result.accepted[0]
    expected = {
        key: record.validated_record.get(key)
        for key in (
            "sku",
            "product_name",
            "category",
            "channel_ids",
            "stage",
            "grade",
            "status",
            "supplier",
            "currency",
            *DECIMAL_FIELDS,
        )
    }
    assert record.canonical_business_hash == payload_sha256(expected)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("product_name", "Changed Name"),
        ("category", "Changed Category"),
        ("channel_ids", '{"other":"id"}'),
        ("stage", "CORE"),
        ("grade", "A"),
        ("status", "PAUSED"),
        ("supplier", "SUP-002"),
        ("currency", "USD"),
        ("purchase_cost", "5201"),
        ("sale_price", "12901"),
        ("fee_rate", "0.109"),
        ("fulfillment_cost", "2501"),
        ("expected_return_cost", "351"),
        ("other_variable_cost", "101"),
    ],
)
def test_each_business_field_change_conflicts_for_same_sku(field, value):
    first = ingest(tool_result(raw=b"business-first"))
    changed = ingest(with_values(**{field: value}), existing=first.accepted)
    assert changed.status is BatchStatus.CONFLICT
    assert changed.conflicts[0].conflict_reason is ReasonCode.NATURAL_KEY_CONFLICT


def test_business_hash_excludes_provenance_data_as_of_and_generated_timestamps():
    first = ingest(tool_result(raw=b"provenance-first"))
    second_input = tool_result(
        rows=(row_for(data_as_of="2026-09-29T06:00:00+09:00"),),
        raw=b"provenance-second",
        source="different_verified_source",
        source_uri="csv://synthetic/second.csv",
        tool_run_id=OTHER_RUN,
    )
    second = ingest(
        second_input,
        run_id=OTHER_RUN,
        clock=lambda: NOW + timedelta(days=1),
        existing=first.accepted,
    )
    assert second.status is BatchStatus.DUPLICATE
    assert second.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE


def test_source_duplicate_is_idempotent_non_publishable_noop():
    first = ingest()
    duplicate = ingest(existing=first.accepted)
    assert duplicate.status is BatchStatus.DUPLICATE
    assert duplicate.batch_reason is ReasonCode.SOURCE_DUPLICATE
    assert duplicate.publish_eligible is False
    assert duplicate.accepted == ()


def test_same_normalized_business_state_is_business_duplicate():
    first = ingest(tool_result(raw=b"normalized-first"))
    second = ingest(
        tool_result(
            rows=(row_for(channel_ids='{"nested":{"id":2},"coupang":"vendor-1"}'),),
            raw=b"normalized-second",
        ),
        existing=first.accepted,
    )
    assert second.status is BatchStatus.DUPLICATE
    assert second.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE


def test_duplicate_sku_rows_inside_batch_are_duplicate_or_conflict():
    duplicate = ingest(tool_result(rows=(row_for(), row_for()), raw=b"duplicate-rows"))
    conflict = ingest(
        tool_result(
            rows=(row_for(), row_for(product_name="Changed")),
            raw=b"conflicting-rows",
        )
    )
    assert duplicate.status is BatchStatus.READY
    assert len(duplicate.accepted) == 1
    assert len(duplicate.duplicates) == 1
    assert conflict.status is BatchStatus.CONFLICT
    assert conflict.publish_eligible is False


def test_failed_partial_and_conflicting_batches_cannot_promote_state():
    partial = ingest(
        tool_result(
            rows=(row_for(), row_for(sku="invalid")),
            raw=b"partial-batch",
        )
    )
    rejected = ingest(with_values(sku="invalid"))
    first = ingest(tool_result(raw=b"current-state"))
    conflict = ingest(with_values(product_name="Changed"), existing=first.accepted)
    assert partial.status is BatchStatus.PARTIAL and not partial.publish_eligible
    assert rejected.status is BatchStatus.REJECTED and not rejected.publish_eligible
    assert conflict.status is BatchStatus.CONFLICT and not conflict.publish_eligible


def test_failed_publication_preserves_prior_state_and_last_identity():
    first = ingest(tool_result(raw=b"publish-first"))
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(first)
    before = publisher.current
    identity = publisher.last_ingestion_identity
    failed = ingest(with_values(product_name="Changed"), existing=before or ())
    assert publisher.publish(failed) is False
    assert publisher.current == before
    assert publisher.last_ingestion_identity == identity


def _fact_result(headers, row, raw):
    return replace(tool_result(raw=raw), parsed_result=TabularData(headers, (row,), None))


def test_product_ad_and_channel_contracts_coexist_without_collisions():
    product = ingest(tool_result(raw=b"product-state"))
    ad_headers = (
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
    ad_row = (
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
    mapping = {"ext-001": SKU}
    ad = ingest_ad_daily(
        _fact_result(ad_headers, ad_row, b"ad-state"),
        run_id=RUN,
        known_skus={SKU},
        sku_mapping=mapping,
        clock=lambda: NOW,
        existing=product.accepted,
    )
    channel_headers = (
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
    channel_row = (
        "synthetic_market",
        "2026-09-27",
        "ext-001",
        "100.00",
        "2",
        "2",
        "0",
        "0",
        "2026-09-28T06:00:00+09:00",
    )
    channel = ingest_channel_daily(
        _fact_result(channel_headers, channel_row, b"channel-state"),
        run_id=RUN,
        known_skus={SKU},
        sku_mapping=mapping,
        clock=lambda: NOW,
        existing=(*product.accepted, *ad.accepted),
    )
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(product)
    assert publisher.publish(ad)
    assert publisher.publish(channel)
    assert {record.contract_name for record in publisher.current or ()} == {
        "PRODUCT_MASTER",
        "AD_DAILY",
        "CHANNEL_DAILY",
    }
    assert len({record.provenance.ingestion_identity for record in publisher.current or ()}) == 3


def test_margin_source_headers_forbidden_and_margins_never_generated():
    for field in ("contribution_margin", "contribution_margin_rate"):
        headers = (*REQUIRED_HEADERS, field)
        values = {**VALUES, field: "1"}
        result = ingest(tool_result(headers=headers, rows=(tuple(values[key] for key in headers),)))
        assert result.batch_reason is ReasonCode.INVALID_ROW_SHAPE
    record = ingest().accepted[0].validated_record
    assert "contribution_margin" not in record
    assert "contribution_margin_rate" not in record
