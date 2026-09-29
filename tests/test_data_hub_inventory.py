from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

import topspeed_ai_os.data_hub.inventory as inventory_module
from topspeed_ai_os.contracts import validate_contract
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.data_hub import (
    INVENTORY_SCHEMA,
    BatchStatus,
    InMemoryReferencePublisher,
    MappingEntry,
    ReasonCode,
    ingest_ad_daily,
    ingest_channel_daily,
    ingest_inventory,
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

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone(timedelta(hours=9)))
RUN = "run_01J00000000000000000000000"
OTHER_RUN = "run_01J00000000000000000000001"
SKU = "TS-SYNTH-001"
KNOWN_SKUS = {SKU}
MAPPING = {("tabular_file", "external_product_id", "ext-001"): SKU}
HEADERS = (
    "snapshot_at",
    "external_product_id",
    "location",
    "on_hand_qty",
    "available_qty",
    "reserved_qty",
    "inbound_qty",
    "data_as_of",
)
VALUES: dict[str, object] = {
    "snapshot_at": "2026-09-29T08:00:00+09:00",
    "external_product_id": "ext-001",
    "location": "synthetic_fulfillment",
    "on_hand_qty": "320",
    "available_qty": "285",
    "reserved_qty": "20",
    "inbound_qty": "100",
    "data_as_of": "2026-09-29T08:05:00+09:00",
}
QUANTITY_FIELDS = ("on_hand_qty", "available_qty", "reserved_qty", "inbound_qty")
FORBIDDEN_FIELDS = (
    "sku",
    "run_id",
    "source",
    "created_at",
    "avg_daily_units",
    "stock_days",
    "lead_time_days",
    "safety_stock_qty",
    "reorder_point_qty",
    "recommended_order_qty",
)


def row_for(headers: tuple[str, ...] = HEADERS, **changes: object) -> tuple[object, ...]:
    values = {**VALUES, **changes}
    return tuple(values[header] for header in headers)


def tool_result(
    *,
    headers: tuple[object, ...] = HEADERS,
    rows: tuple[tuple[object, ...], ...] | None = None,
    raw: bytes = b"inventory-synthetic",
    parsed: object | None = None,
    status: ToolStatus = ToolStatus.SUCCESS,
    source: str = "tabular_file",
    source_uri: str = "csv://synthetic/inventory.csv",
    tool_run_id: str | None = RUN,
) -> ToolResult:
    if rows is None:
        rows = (row_for(headers),)
    if parsed is None:
        parsed = TabularData(headers, rows, None)
    return ToolResult(
        tool_name="tabular_read",
        operation="tabular.read_csv",
        request_id="req_" + ("7" * 32),
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
    return ingest_inventory(
        tool_result() if result is None else result,
        run_id=kwargs.pop("run_id", RUN),
        known_skus=kwargs.pop("known_skus", KNOWN_SKUS),
        sku_mapping=kwargs.pop("sku_mapping", MAPPING),
        clock=kwargs.pop("clock", lambda: NOW),
        **kwargs,
    )


def with_values(**changes: object) -> ToolResult:
    return tool_result(rows=(row_for(**changes),), raw=repr(sorted(changes.items())).encode())


def test_valid_synthetic_row_builds_exact_inventory_contract_record():
    result = ingest()
    assert result.status is BatchStatus.READY
    assert result.publish_eligible is True
    record = result.accepted[0]
    validate_contract("INVENTORY", record.validated_record, known_skus=KNOWN_SKUS)
    assert record.validated_record == {
        "snapshot_at": VALUES["snapshot_at"],
        "sku": SKU,
        "location": VALUES["location"],
        "on_hand_qty": 320,
        "available_qty": 285,
        "reserved_qty": 20,
        "inbound_qty": 100,
        "run_id": RUN,
        "source": "tabular_file",
        "data_as_of": VALUES["data_as_of"],
        "created_at": NOW.isoformat(),
    }
    assert record.natural_key == (VALUES["snapshot_at"], SKU, VALUES["location"])
    assert record.contract_name == "INVENTORY"
    assert record.provenance.target_contract == "INVENTORY"
    assert record.provenance.schema_version == INVENTORY_SCHEMA
    assert record.provenance.data_as_of_origin == "source_row:data_as_of"
    assert record.provenance.normalization_rules_applied == ()


def test_final_validation_call_is_exact_full_inventory_validation(monkeypatch):
    calls: list[tuple[object, ...]] = []
    original_validate_contract = inventory_module.validate_contract

    def spy(*args, **kwargs):
        calls.append((*args, kwargs))
        return original_validate_contract(*args, **kwargs)

    monkeypatch.setattr(inventory_module, "validate_contract", spy)
    result = ingest()
    assert result.status is BatchStatus.READY
    assert calls == [
        ("INVENTORY", result.accepted[0].validated_record, {"known_skus": frozenset({SKU})})
    ]


def test_mapping_fingerprint_and_ingestion_identity_reuse_shared_semantics():
    result = ingest()
    record = result.accepted[0]
    expected_fingerprint = payload_sha256(
        {
            "entries": [
                ("tabular_file", "external_product_id", "ext-001", SKU, True),
            ],
            "known_skus": [SKU],
        }
    )
    expected_identity = payload_sha256(
        {
            "target_contract": "INVENTORY",
            "schema_version": INVENTORY_SCHEMA,
            "source_checksum": record.provenance.source_checksum,
            "mapping_fingerprint": expected_fingerprint,
        }
    )
    assert record.provenance.mapping_fingerprint == expected_fingerprint
    assert record.provenance.ingestion_identity == expected_identity
    assert result.ingestion_identity == expected_identity


@pytest.mark.parametrize("missing", HEADERS)
def test_missing_required_header_rejects_batch(missing):
    headers = tuple(field for field in HEADERS if field != missing)
    result = ingest(tool_result(headers=headers, rows=(row_for(headers),)))
    assert result.status is BatchStatus.REJECTED
    assert result.batch_reason is ReasonCode.INVALID_ROW_SHAPE
    assert result.accepted == ()


@pytest.mark.parametrize("field", HEADERS)
@pytest.mark.parametrize("blank", ["", None])
def test_blank_required_values_are_rejected(field, blank):
    result = ingest(with_values(**{field: blank}))
    assert result.status is BatchStatus.REJECTED
    assert result.publish_eligible is False


@pytest.mark.parametrize("field", (*FORBIDDEN_FIELDS, "unknown_field"))
def test_forbidden_and_unknown_source_headers_fail_batch_closed(field):
    headers = (*HEADERS, field)
    values = {**VALUES, field: "1"}
    result = ingest(tool_result(headers=headers, rows=(tuple(values[key] for key in headers),)))
    assert result.status is BatchStatus.REJECTED
    assert result.batch_reason is ReasonCode.INVALID_ROW_SHAPE


def test_duplicate_malformed_empty_and_wrong_width_tabular_shapes_fail_closed():
    duplicate_headers = (*HEADERS, "location")
    duplicate = ingest(tool_result(headers=duplicate_headers, rows=(row_for(duplicate_headers),)))
    malformed_headers = TabularData(HEADERS, (row_for(),), None)
    object.__setattr__(malformed_headers, "headers", [*HEADERS])
    malformed_rows = TabularData(HEADERS, (row_for(),), None)
    object.__setattr__(malformed_rows, "rows", [row_for()])
    empty = ingest(tool_result(rows=()))
    width = ingest(tool_result(rows=(row_for(), row_for()[:-1])))
    assert duplicate.batch_reason is ReasonCode.INVALID_ROW_SHAPE
    assert (
        ingest(tool_result(parsed=malformed_headers)).batch_reason is ReasonCode.INVALID_ROW_SHAPE
    )
    assert ingest(tool_result(parsed=malformed_rows)).batch_reason is ReasonCode.INVALID_ROW_SHAPE
    assert empty.batch_reason is ReasonCode.INVALID_ROW_SHAPE
    assert width.batch_reason is ReasonCode.INVALID_ROW_SHAPE


def test_exact_mapping_generates_sku_and_source_sku_is_not_accepted():
    result = ingest()
    assert result.accepted[0].validated_record["sku"] == SKU
    assert "external_product_id" not in result.accepted[0].validated_record
    headers = (*HEADERS, "sku")
    values = {**VALUES, "sku": SKU}
    forbidden = ingest(tool_result(headers=headers, rows=(tuple(values[key] for key in headers),)))
    assert forbidden.batch_reason is ReasonCode.INVALID_ROW_SHAPE


@pytest.mark.parametrize("known_skus", [None, SKU, {1}, {"sku": SKU}, object()])
def test_malformed_known_skus_fail_closed_before_mapping(known_skus):
    result = ingest(known_skus=known_skus)
    assert result.status is BatchStatus.REJECTED
    assert result.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert result.accepted == ()


def test_known_skus_accepts_valid_string_iterables_without_changing_mapping_semantics():
    assert ingest(known_skus=[SKU]).status is BatchStatus.READY
    assert ingest(known_skus=(sku for sku in [SKU])).status is BatchStatus.READY


def test_missing_mapping_context_fails_closed():
    result = ingest(sku_mapping=None)
    assert result.status is BatchStatus.REJECTED
    assert result.batch_reason is ReasonCode.UNSUPPORTED_MAPPING


def test_blank_unknown_inactive_ambiguous_and_unregistered_mapping_failures():
    blank = ingest(with_values(external_product_id=""))
    unknown = ingest(with_values(external_product_id="ext-unknown"))
    inactive = ingest(
        sku_mapping=(MappingEntry("tabular_file", "external_product_id", "ext-001", SKU, False),)
    )
    ambiguous = ingest(
        sku_mapping=(
            MappingEntry("tabular_file", "external_product_id", "ext-001", SKU),
            MappingEntry("tabular_file", "external_product_id", "ext-001", "TS-OTHER-002"),
        )
    )
    unregistered = ingest(sku_mapping={"ext-001": "TS-OTHER-002"})
    assert blank.rejected[0].reason_code is ReasonCode.MISSING_SKU_MAPPING_KEY
    assert unknown.rejected[0].reason_code is ReasonCode.UNKNOWN_SKU
    assert inactive.rejected[0].reason_code is ReasonCode.UNKNOWN_SKU
    assert ambiguous.rejected[0].reason_code is ReasonCode.AMBIGUOUS_SKU
    assert unregistered.rejected[0].reason_code is ReasonCode.UNREGISTERED_SKU


@pytest.mark.parametrize(
    "mapping",
    [
        {("tabular_file", "external_product_id"): SKU},
        {1: SKU},
        {"ext-001": 123},
        {"ext-001": {"sku": 123}},
        {"ext-001": {"sku": SKU, "active": 1}},
        [object()],
    ],
)
def test_malformed_mapping_reuses_shared_fail_closed_normalization(mapping):
    result = ingest(sku_mapping=mapping)
    assert result.status is BatchStatus.REJECTED
    assert result.batch_reason is ReasonCode.UNSUPPORTED_MAPPING


class _RuntimeErrorIterable:
    def __iter__(self):
        raise RuntimeError("synthetic iteration failure")


class _SyntheticBaseException(BaseException):
    pass


class _BaseExceptionIterable:
    def __iter__(self):
        raise _SyntheticBaseException("synthetic base exception")


@pytest.mark.parametrize(
    ("boundary", "reason"),
    [
        ("known_skus", ReasonCode.INVALID_TOOL_RESULT),
        ("sku_mapping", ReasonCode.UNSUPPORTED_MAPPING),
        ("existing", ReasonCode.INVALID_TOOL_RESULT),
    ],
)
def test_iterable_runtime_errors_fail_closed_and_preserve_publisher_state(boundary, reason):
    prior = ingest(tool_result(raw=b"iterable-prior"))
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(prior) is True
    current = publisher.current
    last_ingestion_identity = publisher.last_ingestion_identity

    rejected = ingest(
        tool_result(raw=f"iterable-{boundary}".encode()),
        **{boundary: _RuntimeErrorIterable()},
    )

    assert rejected.status is BatchStatus.REJECTED
    assert rejected.batch_reason is reason
    assert rejected.publish_eligible is False
    assert rejected.accepted == ()
    assert publisher.publish(rejected) is False
    assert publisher.current == current
    assert publisher.last_ingestion_identity == last_ingestion_identity


@pytest.mark.parametrize("boundary", ["known_skus", "sku_mapping", "existing"])
def test_iterable_base_exceptions_are_not_caught(boundary):
    with pytest.raises(_SyntheticBaseException, match="synthetic base exception"):
        ingest(**{boundary: _BaseExceptionIterable()})


@pytest.mark.parametrize(
    "field",
    ["snapshot_at", "data_as_of"],
)
@pytest.mark.parametrize(
    "invalid",
    ["2026-09-29T08:00:00", "2026-09-29T25:00:00+09:00", "not-a-date", 20260929],
)
def test_source_datetimes_must_be_valid_and_timezone_aware(field, invalid):
    result = ingest(with_values(**{field: invalid}))
    assert result.status is BatchStatus.REJECTED
    assert result.publish_eligible is False


def test_source_datetimes_are_preserved_without_substitution_or_global_normalization():
    result = ingest(
        with_values(
            snapshot_at="2026-09-28T23:00:00Z",
            data_as_of="2026-09-29T08:30:00+09:00",
        ),
        clock=lambda: datetime(2030, 1, 1, tzinfo=UTC),
    )
    record = result.accepted[0]
    assert record.validated_record["snapshot_at"] == "2026-09-28T23:00:00Z"
    assert record.validated_record["data_as_of"] == "2026-09-29T08:30:00+09:00"
    assert record.validated_record["snapshot_at"] != record.validated_record["created_at"]
    assert record.provenance.data_as_of_origin == "source_row:data_as_of"


def test_snapshot_and_data_as_of_have_no_invented_equality_or_order_rule():
    earlier_data_as_of = ingest(with_values(data_as_of="2026-09-29T07:00:00+09:00"))
    later_data_as_of = ingest(with_values(data_as_of="2026-09-29T09:00:00+09:00"))
    assert earlier_data_as_of.status is BatchStatus.READY
    assert later_data_as_of.status is BatchStatus.READY


@pytest.mark.parametrize("field", QUANTITY_FIELDS)
@pytest.mark.parametrize(
    "invalid",
    [True, False, 1.5, "1e3", "01", "1,000", "1개", object(), [], {}],
)
def test_quantity_fields_use_strict_integer_parsing(field, invalid):
    result = ingest(with_values(**{field: invalid}))
    assert result.status is BatchStatus.REJECTED
    assert result.publish_eligible is False


@pytest.mark.parametrize("field", QUANTITY_FIELDS)
def test_negative_quantities_are_not_rejected_by_an_invented_policy(field):
    result = ingest(with_values(**{field: "-7"}))
    assert result.status is BatchStatus.READY
    assert result.accepted[0].validated_record[field] == -7


@pytest.mark.parametrize(
    "changes",
    [
        {"on_hand_qty": "1", "available_qty": "99", "reserved_qty": "50"},
        {"on_hand_qty": "0", "available_qty": "5", "inbound_qty": "-3"},
    ],
)
def test_no_inventory_quantity_arithmetic_relationship_is_invented(changes):
    assert ingest(with_values(**changes)).status is BatchStatus.READY


def test_generated_fields_come_only_from_verified_boundaries():
    result = ingest(
        tool_result(source="verified_inventory_source"),
        sku_mapping={
            ("verified_inventory_source", "external_product_id", "ext-001"): SKU,
        },
    )
    record = result.accepted[0].validated_record
    assert record["run_id"] == RUN
    assert record["source"] == "verified_inventory_source"
    assert record["created_at"] == NOW.isoformat()
    assert ingest(clock=lambda: datetime(2026, 9, 29, 12)).status is BatchStatus.REJECTED


def test_phase5_and_deferred_fields_are_neither_accepted_nor_generated():
    forbidden = {
        "avg_daily_units",
        "stock_days",
        "lead_time_days",
        "safety_stock_qty",
        "reorder_point_qty",
        "recommended_order_qty",
    }
    record = ingest().accepted[0].validated_record
    assert forbidden.isdisjoint(record)
    for field in forbidden:
        headers = (*HEADERS, field)
        values = {**VALUES, field: "1"}
        result = ingest(tool_result(headers=headers, rows=(tuple(values[key] for key in headers),)))
        assert result.batch_reason is ReasonCode.INVALID_ROW_SHAPE


def test_tool_metadata_checksum_run_and_schema_boundaries_fail_closed():
    checksum = tool_result()
    object.__setattr__(checksum.source_metadata, "checksum_sha256", raw_sha256(b"other"))
    unsafe = tool_result(source_uri="https://secret@host/inventory.csv")
    mismatch = tool_result(tool_run_id=OTHER_RUN)
    non_tabular = tool_result(parsed={"rows": []})
    partial = tool_result(status=ToolStatus.PARTIAL)
    missing_raw = tool_result()
    object.__setattr__(missing_raw, "raw_result", None)
    missing_metadata = tool_result()
    object.__setattr__(missing_metadata, "source_metadata", None)
    assert ingest(checksum).batch_reason is ReasonCode.CHECKSUM_MISMATCH
    assert ingest(unsafe).batch_reason is ReasonCode.UNSAFE_SOURCE_REFERENCE
    assert ingest(mismatch).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert ingest(non_tabular).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert ingest(partial).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert ingest(missing_raw).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert ingest(missing_metadata).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert (
        ingest(schema_version="topspeed.inventory.synthetic.v2").batch_reason
        is ReasonCode.UNSUPPORTED_SCHEMA
    )


def test_business_hash_has_exact_inventory_snapshot_state():
    result = ingest()
    record = result.accepted[0]
    expected = {
        "snapshot_at": VALUES["snapshot_at"],
        "sku": SKU,
        "location": VALUES["location"],
        "on_hand_qty": 320,
        "available_qty": 285,
        "reserved_qty": 20,
        "inbound_qty": 100,
    }
    assert record.canonical_business_hash == payload_sha256(expected)


def test_same_source_identity_is_idempotent_non_publishable_noop():
    first = ingest()
    duplicate = ingest(existing=first.accepted)
    assert duplicate.status is BatchStatus.DUPLICATE
    assert duplicate.batch_reason is ReasonCode.SOURCE_DUPLICATE
    assert duplicate.publish_eligible is False
    assert duplicate.accepted == ()


def test_same_natural_key_same_business_state_is_business_duplicate():
    first = ingest(tool_result(raw=b"business-one"))
    duplicate = ingest(tool_result(raw=b"business-two"), existing=first.accepted)
    assert duplicate.status is BatchStatus.DUPLICATE
    assert duplicate.batch_reason is None
    assert duplicate.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE


@pytest.mark.parametrize("field", QUANTITY_FIELDS)
def test_same_natural_key_changed_quantity_is_conflict(field):
    first = ingest(tool_result(raw=b"conflict-first"))
    changed = ingest(with_values(**{field: "999"}), existing=first.accepted)
    assert changed.status is BatchStatus.CONFLICT
    assert changed.conflicts[0].conflict_reason is ReasonCode.NATURAL_KEY_CONFLICT
    assert changed.publish_eligible is False


def test_changed_provenance_and_data_as_of_only_is_not_natural_key_conflict():
    first = ingest(tool_result(raw=b"provenance-first"))
    changed_input = tool_result(
        rows=(row_for(data_as_of="2026-09-30T10:00:00+09:00"),),
        raw=b"provenance-second",
        source="other_verified_source",
        source_uri="csv://synthetic/other-inventory.csv",
        tool_run_id=OTHER_RUN,
    )
    changed = ingest(
        changed_input,
        run_id=OTHER_RUN,
        clock=lambda: NOW + timedelta(days=1),
        sku_mapping={
            ("other_verified_source", "external_product_id", "ext-001"): SKU,
        },
        existing=first.accepted,
    )
    assert changed.status is BatchStatus.DUPLICATE
    assert changed.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE
    assert changed.conflicts == ()


def test_duplicate_and_conflicting_rows_inside_batch_are_distinguished():
    duplicate = ingest(tool_result(rows=(row_for(), row_for()), raw=b"duplicate-rows"))
    conflict = ingest(
        tool_result(
            rows=(row_for(), row_for(available_qty="999")),
            raw=b"conflicting-rows",
        )
    )
    assert duplicate.status is BatchStatus.READY
    assert len(duplicate.accepted) == 1
    assert len(duplicate.duplicates) == 1
    assert duplicate.publish_eligible is True
    assert conflict.status is BatchStatus.CONFLICT
    assert conflict.publish_eligible is False


def test_partial_rejected_and_conflicting_batches_do_not_publish():
    partial = ingest(
        tool_result(
            rows=(row_for(), row_for(external_product_id="unknown")),
            raw=b"partial",
        )
    )
    rejected = ingest(with_values(external_product_id="unknown"))
    first = ingest(tool_result(raw=b"existing"))
    conflict = ingest(with_values(inbound_qty="999"), existing=first.accepted)
    publisher = InMemoryReferencePublisher()
    assert partial.status is BatchStatus.PARTIAL
    assert rejected.status is BatchStatus.REJECTED
    assert conflict.status is BatchStatus.CONFLICT
    assert publisher.publish(partial) is False
    assert publisher.publish(rejected) is False
    assert publisher.publish(conflict) is False
    assert publisher.current is None


def test_failed_publication_preserves_current_and_last_ingestion_identity():
    first = ingest(tool_result(raw=b"publish-first"))
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(first)
    before = publisher.current
    identity = publisher.last_ingestion_identity
    conflict = ingest(with_values(on_hand_qty="999"), existing=before or ())
    assert publisher.publish(conflict) is False
    assert publisher.current == before
    assert publisher.last_ingestion_identity == identity


def test_multirow_conflict_is_atomic_and_promotes_no_partial_state():
    first = ingest(tool_result(raw=b"atomic-first"))
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(first)
    before = publisher.current
    last_identity = publisher.last_ingestion_identity
    batch = ingest(
        tool_result(
            rows=(
                row_for(
                    snapshot_at="2026-09-29T09:00:00+09:00",
                    location="second_location",
                ),
                row_for(on_hand_qty="999"),
            ),
            raw=b"atomic-conflict",
        ),
        existing=before or (),
    )
    assert batch.status is BatchStatus.CONFLICT
    assert len(batch.accepted) == 1
    assert publisher.publish(batch) is False
    assert publisher.current == before
    assert publisher.last_ingestion_identity == last_identity


def test_malformed_existing_collection_and_records_fail_closed():
    assert ingest(existing=object()).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    valid = ingest().accepted[0]
    malformed = replace(
        valid,
        provenance=replace(valid.provenance, target_contract="AD_DAILY"),
    )
    result = ingest(existing=(malformed,))
    assert result.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert result.accepted == ()


def test_other_contract_existing_record_cannot_trigger_inventory_source_or_key_collision():
    inventory = ingest(tool_result(raw=b"isolation"))
    record = inventory.accepted[0]
    other = replace(
        record,
        contract_name="PRODUCT_MASTER",
        provenance=replace(record.provenance, target_contract="PRODUCT_MASTER"),
    )
    result = ingest(tool_result(raw=b"isolation"), existing=(other,))
    assert result.status is BatchStatus.READY
    assert result.batch_reason is None
    assert result.duplicates == ()
    assert result.conflicts == ()


def _other_contract_tool_result(headers, row, raw):
    return replace(
        tool_result(raw=raw),
        parsed_result=TabularData(headers, (row,), None),
    )


def test_four_real_contract_ingestion_boundaries_coexist_in_publisher():
    product_headers = (
        "sku",
        "product_name",
        "category",
        "stage",
        "status",
        "currency",
        "data_as_of",
    )
    product_row = (
        SKU,
        "Synthetic Product",
        "Kitchen",
        "TEST",
        "ACTIVE",
        "KRW",
        "2026-09-29T06:00:00+09:00",
    )
    product = ingest_product_master(
        _other_contract_tool_result(product_headers, product_row, b"product-four"),
        run_id=RUN,
        clock=lambda: NOW,
    )

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
        "2026-09-28",
        "ext-001",
        "campaign-1",
        "1000",
        "10",
        "20.00",
        "2",
        "100.00",
        "2026-09-29T06:00:00+09:00",
    )
    ad = ingest_ad_daily(
        _other_contract_tool_result(ad_headers, ad_row, b"ad-four"),
        run_id=RUN,
        known_skus=KNOWN_SKUS,
        sku_mapping=MAPPING,
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
        "2026-09-28",
        "ext-001",
        "100.00",
        "2",
        "2",
        "0",
        "0",
        "2026-09-29T06:00:00+09:00",
    )
    channel = ingest_channel_daily(
        _other_contract_tool_result(channel_headers, channel_row, b"channel-four"),
        run_id=RUN,
        known_skus=KNOWN_SKUS,
        sku_mapping=MAPPING,
        clock=lambda: NOW,
        existing=(*product.accepted, *ad.accepted),
    )
    inventory = ingest(
        tool_result(raw=b"inventory-four"),
        existing=(*product.accepted, *ad.accepted, *channel.accepted),
    )

    assert all(result.status is BatchStatus.READY for result in (product, ad, channel, inventory))
    assert all(len(result.accepted) == 1 for result in (product, ad, channel, inventory))
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(product)
    assert publisher.publish(ad)
    assert publisher.publish(channel)
    assert publisher.publish(inventory)
    assert {record.contract_name for record in publisher.current or ()} == {
        "PRODUCT_MASTER",
        "AD_DAILY",
        "CHANNEL_DAILY",
        "INVENTORY",
    }
    assert len(publisher.current or ()) == 4
    assert len({record.provenance.ingestion_identity for record in publisher.current or ()}) == 4
