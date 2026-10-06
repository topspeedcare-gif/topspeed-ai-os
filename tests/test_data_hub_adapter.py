from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from tests import test_data_hub_channel_daily as channel_daily_test
from topspeed_ai_os.data_hub import (
    BatchResult,
    BatchStatus,
    InMemoryReferencePublisher,
    MappingEntry,
    ReasonCode,
    ingest_ad_daily,
)
from topspeed_ai_os.tools.checksum import raw_sha256
from topspeed_ai_os.tools.read.tabular import TabularData
from topspeed_ai_os.tools.result import (
    ErrorCategory,
    ExecutionMode,
    SensitiveBytes,
    SourceMetadata,
    ToolError,
    ToolResult,
    ToolStatus,
)

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone(timedelta(hours=9)))
RUN = "run_00000000000000000000000000"
HEADERS = (
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
    "campaign_name",
    "ad_group_id",
    "ad_units",
)
ROW = (
    "synthetic_ads",
    "2026-09-21",
    "ext-001",
    "cmp-1",
    "1000",
    "10",
    "125.50",
    "2",
    "400.00",
    "2026-09-21T23:00:00+09:00",
    "Campaign",
    "",
    "2",
)


def tool_result(
    rows=(ROW,),
    *,
    raw=b"synthetic-row",
    status=ToolStatus.SUCCESS,
    parsed=None,
    tool_run_id=RUN,
    source_metadata=None,
    raw_result=None,
):
    parsed = TabularData(HEADERS, tuple(rows), None) if parsed is None else parsed
    error = (
        ToolError(ErrorCategory.MALFORMED_SOURCE, "synthetic failure", False)
        if status is ToolStatus.FAILED
        else None
    )
    return ToolResult(
        tool_name="tabular_read",
        operation="tabular.read_csv",
        request_id="req_" + "a" * 32,
        status=status,
        execution_mode=ExecutionMode.MOCK,
        task_id=None,
        run_id=tool_run_id,
        source_metadata=source_metadata
        or SourceMetadata(
            source="tabular_file",
            source_uri="csv://synthetic/ad-daily.csv",
            fetched_at=NOW,
            data_as_of=None,
            checksum_sha256=raw_sha256(raw),
        ),
        raw_result=SensitiveBytes(raw) if raw_result is None else raw_result,
        parsed_result=parsed,
        error=error,
    )


def ingest(result, **kwargs):
    run_id = kwargs.pop("run_id", RUN)
    clock = kwargs.pop("clock", lambda: NOW)
    mapping = kwargs.pop(
        "sku_mapping",
        {("tabular_file", "external_product_id", "ext-001"): "TS-SYNTH-001"},
    )
    return ingest_ad_daily(
        result,
        run_id=run_id,
        known_skus={"TS-SYNTH-001"},
        sku_mapping=mapping,
        clock=clock,
        **kwargs,
    )


def test_success_builds_validated_ad_daily_and_provenance():
    result = ingest(tool_result())
    assert result.status is BatchStatus.READY
    assert result.publish_eligible is True
    record = result.accepted[0]
    assert record.validated_record["sku"] == "TS-SYNTH-001"
    assert record.validated_record["source_file_hash"] == raw_sha256(b"synthetic-row")
    assert "ctr" not in record.validated_record
    assert record.validated_record["ad_group_id"] is None
    assert record.provenance.data_as_of_origin == "source_row:data_as_of"
    assert record.provenance.source_row_reference == "CSV row:2"


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (lambda r: r[:-1], ReasonCode.INVALID_ROW_SHAPE),
        (lambda r: (*r[:9], "2026-09-21T23:00:00", *r[10:]), ReasonCode.INVALID_DATA_AS_OF),
        (lambda r: (*r[:9], "", *r[10:]), ReasonCode.INVALID_DATA_AS_OF),
        (lambda r: (*r[:6], 1.2, *r[7:]), ReasonCode.INVALID_SOURCE_VALUE),
    ],
)
def test_invalid_rows_fail_closed(mutator, reason):
    rows = (mutator(ROW),)
    result = ingest(tool_result(rows))
    assert result.publish_eligible is False
    assert result.rejected[0].reason_code in {reason, ReasonCode.CONTRACT_VALIDATION_FAILED}


def test_unsupported_schema_and_failed_tool_result_rejected():
    assert (
        ingest(tool_result(), schema_version="topspeed.ad_daily.synthetic.v0")
        .rejected[0]
        .reason_code
        is ReasonCode.UNSUPPORTED_SCHEMA
    )
    failed = ingest(tool_result(status=ToolStatus.FAILED))
    assert failed.rejected[0].reason_code is ReasonCode.INVALID_TOOL_RESULT


def test_checksum_mismatch_and_unknown_sku_rejected():
    bad = tool_result()
    object.__setattr__(bad.source_metadata, "checksum_sha256", raw_sha256(b"different"))
    assert ingest(bad).rejected[0].reason_code is ReasonCode.CHECKSUM_MISMATCH
    unknown = ingest(tool_result(), sku_mapping={"ext-001": "TS-OTHER-002"})
    assert unknown.rejected[0].reason_code is ReasonCode.UNREGISTERED_SKU


def test_business_duplicate_and_conflict_are_separate():
    first = ingest(tool_result())
    duplicate = ingest(tool_result(), existing=first.accepted)
    assert duplicate.status is BatchStatus.DUPLICATE
    changed = list(ROW)
    changed[7] = "3"
    conflict = ingest(
        tool_result((tuple(changed),), raw=b"synthetic-conflict"), existing=first.accepted
    )
    assert conflict.status is BatchStatus.CONFLICT
    assert conflict.publish_eligible is False


def test_different_checksum_same_business_is_duplicate_and_changed_facts_conflict():
    first = ingest(tool_result())
    duplicate = ingest(tool_result(raw=b"another-file"), existing=first.accepted)
    assert duplicate.status is BatchStatus.DUPLICATE
    assert duplicate.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE
    changed = list(ROW)
    changed[7] = "3"
    conflict = ingest(tool_result((tuple(changed),), raw=b"third-file"), existing=first.accepted)
    assert conflict.conflicts[0].conflict_reason is ReasonCode.NATURAL_KEY_CONFLICT


def test_run_and_created_at_differences_do_not_create_business_conflict():
    first = ingest(tool_result())
    same_business = ingest(
        tool_result(raw=b"new-provenance", tool_run_id="run_11111111111111111111111111"),
        existing=first.accepted,
        run_id="run_11111111111111111111111111",
        clock=lambda: datetime(2026, 9, 23, 12, 0, tzinfo=NOW.tzinfo),
    )
    assert same_business.status is BatchStatus.DUPLICATE
    assert same_business.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE


def test_conflict_batch_leaves_publisher_current_unchanged():
    first = ingest(tool_result())
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(first)
    changed = list(ROW)
    changed[7] = "9"
    conflict = ingest(tool_result((tuple(changed),), raw=b"conflict"), existing=first.accepted)
    assert conflict.status is BatchStatus.CONFLICT
    assert publisher.publish(conflict) is False
    assert publisher.current == first.accepted


def test_source_duplicate_uses_any_matching_published_ingestion_identity():
    first = ingest(tool_result())
    unrelated = ingest(tool_result(raw=b"unrelated"), sku_mapping={"ext-001": "TS-SYNTH-001"})
    result = ingest(tool_result(), existing=(*unrelated.accepted, *first.accepted))
    assert result.status is BatchStatus.DUPLICATE
    assert result.batch_reason is ReasonCode.SOURCE_DUPLICATE


def test_changed_mapping_fingerprint_reprocesses_same_checksum():
    first = ingest(tool_result())
    result = ingest(
        tool_result(),
        existing=first.accepted,
        sku_mapping={
            ("tabular_file", "external_product_id", "ext-001"): "TS-SYNTH-001",
            ("other", "external_product_id", "ext-002"): "TS-SYNTH-001",
        },
    )
    assert result.status is BatchStatus.DUPLICATE
    assert result.batch_reason is None
    assert result.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE


def test_run_mismatch_and_runtime_boundary_types_fail_closed():
    mismatch = ingest(tool_result(tool_run_id="run_11111111111111111111111111"))
    assert mismatch.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    bad_raw = ingest(tool_result(raw_result=object()))
    assert bad_raw.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    bad_metadata = ingest(tool_result(source_metadata=object()))
    assert bad_metadata.batch_reason is ReasonCode.INVALID_TOOL_RESULT


def test_mapping_boundary_and_sku_reason_codes():
    invalid = ingest(tool_result(), sku_mapping=[object()])
    assert invalid.batch_reason is ReasonCode.UNSUPPORTED_MAPPING
    ambiguous = ingest(
        tool_result(),
        sku_mapping=[
            MappingEntry("tabular_file", "external_product_id", "ext-001", "TS-SYNTH-001"),
            MappingEntry("tabular_file", "external_product_id", "ext-001", "TS-OTHER-002"),
        ],
    )
    assert ambiguous.rejected[0].reason_code is ReasonCode.AMBIGUOUS_SKU
    unknown = ingest(tool_result(), sku_mapping={"other-id": "TS-SYNTH-001"})
    assert unknown.rejected[0].reason_code is ReasonCode.UNKNOWN_SKU
    missing = ingest(tool_result(((*ROW[:2], "", *ROW[3:]),)))
    assert missing.rejected[0].reason_code is ReasonCode.MISSING_SKU_MAPPING_KEY


def test_normalization_provenance_records_only_real_transformations():
    result = ingest(tool_result())
    rules = result.accepted[0].provenance.normalization_rules_applied
    assert "blank_ad_group_id_to_none" in rules
    assert "blank_campaign_name_to_none" not in rules
    assert "blank_ad_units_to_none" not in rules


def test_publisher_merges_current_and_rejects_malformed_results():
    first = ingest(tool_result())
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(first)
    row_b = list(ROW)
    row_b[2] = "ext-002"
    row_b[3] = "cmp-2"
    second = ingest(
        tool_result((ROW, tuple(row_b)), raw=b"batch-ab"),
        sku_mapping={
            ("tabular_file", "external_product_id", "ext-001"): "TS-SYNTH-001",
            ("tabular_file", "external_product_id", "ext-002"): "TS-SYNTH-001",
        },
    )
    assert publisher.publish(second)
    assert len(publisher.current or ()) == 2
    malformed = BatchResult(
        "bad",
        BatchStatus.PARTIAL,
        accepted=second.accepted,
        rejected=second.rejected,
        publish_eligible=True,
    )
    assert publisher.publish(malformed) is False
    assert len(publisher.current or ()) == 2


def test_partial_failure_preserves_accepted_and_rejected_evidence():
    result = ingest(tool_result((ROW, ROW[:-1]), raw=b"partial"))
    assert result.status is BatchStatus.PARTIAL
    assert len(result.accepted) == 1
    assert len(result.rejected) == 1
    assert result.publish_eligible is False


def test_mapping_fingerprint_allows_reprocessing_and_publisher_is_fail_closed():
    first = ingest(tool_result())
    second = ingest(tool_result(), existing=first.accepted, sku_mapping={"ext-001": "TS-SYNTH-001"})
    assert second.status is BatchStatus.DUPLICATE
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(first) is True
    assert publisher.current == first.accepted
    assert publisher.publish(second) is False
    rejected = ingest(tool_result((ROW[:-1],)))
    assert publisher.publish(rejected) is False
    assert publisher.current == first.accepted


def test_malformed_mapping_tuple_context_fails_closed_before_fingerprint():
    result = ingest(
        tool_result(),
        sku_mapping={
            (1, 2, 3): "TS-SYNTH-001",
            ("tabular_file", "external_product_id", "ext-001"): "TS-SYNTH-001",
        },
    )
    assert result.batch_reason is ReasonCode.UNSUPPORTED_MAPPING
    assert result.accepted == ()
    assert result.publish_eligible is False


@pytest.mark.parametrize(
    "mapping",
    [
        {("tabular_file", "ext-001"): "TS-SYNTH-001"},
        {(1, "external_product_id", "ext-001"): "TS-SYNTH-001"},
        {("tabular_file", 2, "ext-001"): "TS-SYNTH-001"},
        {("tabular_file", "external_product_id", 3): "TS-SYNTH-001"},
        {("tabular_file", "external_product_id", "ext-001"): 123},
        {
            ("tabular_file", "external_product_id", "ext-001"): "TS-SYNTH-001",
            ("tabular_file", "external_product_id", "ext-002"): {"sku": 123},
        },
        {"": "TS-SYNTH-001"},
        {"   ": "TS-SYNTH-001"},
        {("", "external_product_id", "ext-001"): "TS-SYNTH-001"},
        {("tabular_file", " ", "ext-001"): "TS-SYNTH-001"},
        {("tabular_file", "external_product_id", " "): "TS-SYNTH-001"},
    ],
)
def test_invalid_mapping_semantics_are_rejected_as_a_whole(mapping):
    result = ingest(tool_result(), sku_mapping=mapping)
    assert result.batch_reason is ReasonCode.UNSUPPORTED_MAPPING
    assert result.accepted == ()
    assert result.publish_eligible is False


@pytest.mark.parametrize("active", [1, "true", None])
def test_structured_mapping_active_requires_actual_bool(active):
    result = ingest(
        tool_result(),
        sku_mapping={
            ("tabular_file", "external_product_id", "ext-001"): {
                "sku": "TS-SYNTH-001",
                "active": active,
            }
        },
    )
    assert result.batch_reason is ReasonCode.UNSUPPORTED_MAPPING


def test_supported_mapping_forms_still_resolve():
    shorthand = ingest(tool_result(), sku_mapping={"ext-001": "TS-SYNTH-001"})
    structured = ingest(
        tool_result(),
        sku_mapping={
            ("tabular_file", "external_product_id", "ext-001"): {
                "sku": "TS-SYNTH-001",
                "active": True,
            }
        },
    )
    iterable = ingest(
        tool_result(),
        sku_mapping=[
            MappingEntry("tabular_file", "external_product_id", "ext-001", "TS-SYNTH-001")
        ],
    )
    assert all(result.status is BatchStatus.READY for result in (shorthand, structured, iterable))


def test_mapping_entry_iterable_rejects_non_boolean_active():
    entry = MappingEntry("tabular_file", "external_product_id", "ext-001", "TS-SYNTH-001")
    object.__setattr__(entry, "active", "true")
    result = ingest(tool_result(), sku_mapping=[entry])
    assert result.batch_reason is ReasonCode.UNSUPPORTED_MAPPING


def test_valid_mapping_fingerprint_is_order_independent_and_effective_only():
    first = ingest(
        tool_result(),
        sku_mapping=[
            MappingEntry("tabular_file", "external_product_id", "ext-001", "TS-SYNTH-001"),
            MappingEntry("tabular_file", "external_product_id", "inactive", "TS-SYNTH-001", False),
        ],
    )
    reordered = ingest(
        tool_result(),
        sku_mapping=[
            MappingEntry("tabular_file", "external_product_id", "inactive", "TS-SYNTH-001", False),
            MappingEntry("tabular_file", "external_product_id", "ext-001", "TS-SYNTH-001"),
        ],
    )
    changed = ingest(
        tool_result(),
        sku_mapping=[
            MappingEntry("tabular_file", "external_product_id", "ext-001", "TS-SYNTH-001"),
            MappingEntry("tabular_file", "external_product_id", "ext-002", "TS-SYNTH-001"),
        ],
    )
    assert (
        first.accepted[0].provenance.mapping_fingerprint
        == reordered.accepted[0].provenance.mapping_fingerprint
    )
    assert (
        first.accepted[0].provenance.mapping_fingerprint
        != changed.accepted[0].provenance.mapping_fingerprint
    )


def test_inactive_mapping_does_not_resolve_a_sku():
    result = ingest(
        tool_result(),
        sku_mapping={
            ("tabular_file", "external_product_id", "ext-001"): {
                "sku": "TS-SYNTH-001",
                "active": False,
            }
        },
    )
    assert result.rejected[0].reason_code is ReasonCode.UNKNOWN_SKU


def _other_contract_record(_record):
    return channel_daily_test.ingest(channel_daily_test.tool_result()).accepted[0]


def test_publisher_contract_scoped_identity_and_lookup():
    ad_result = ingest(tool_result())
    ad_record = ad_result.accepted[0]
    other_record = _other_contract_record(ad_record)
    assert other_record.contract_name == "CHANNEL_DAILY"
    assert other_record.provenance.target_contract == "CHANNEL_DAILY"
    assert other_record.provenance.schema_version == "topspeed.channel_daily.synthetic.v1"
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(ad_result)
    other_result = BatchResult(
        "channel-fixture",
        BatchStatus.READY,
        accepted=(other_record,),
        publish_eligible=True,
        target_contract="CHANNEL_DAILY",
    )
    assert publisher.publish(other_result)
    assert publisher.current == (ad_record, other_record)
    assert publisher.get_current("AD_DAILY", ad_record.natural_key) is ad_record
    assert publisher.get_current("CHANNEL_DAILY", other_record.natural_key) is other_record
    assert publisher.get_current("UNKNOWN", ad_record.natural_key) is None
    with pytest.raises(TypeError):
        publisher.get_current(ad_record.natural_key)  # type: ignore[call-arg]


def test_ingestion_existing_state_is_contract_scoped():
    ad_record = ingest(tool_result()).accepted[0]
    other_record = _other_contract_record(ad_record)
    result = ingest(tool_result(), existing=(other_record,))
    assert result.status is BatchStatus.READY
    assert len(result.accepted) == 1


@pytest.mark.parametrize(
    "target_contract", [None, "", "   ", "ad_daily", "UNKNOWN", True, 1, object()]
)
def test_publisher_rejects_invalid_target_contract_without_mutation(target_contract):
    ad_record = ingest(tool_result()).accepted[0]
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(ingest(tool_result()))
    before = publisher.current
    invalid = BatchResult(
        "invalid-target",
        BatchStatus.READY,
        accepted=(ad_record,),
        publish_eligible=True,
        target_contract=target_contract,
    )
    assert publisher.publish(invalid) is False
    assert publisher.current == before


def test_publisher_rejects_contract_mismatch_and_mixed_batch_without_mutation():
    ad_record = ingest(tool_result()).accepted[0]
    other_record = _other_contract_record(ad_record)
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(ingest(tool_result()))
    before = publisher.current
    mismatch = BatchResult(
        "mismatch",
        BatchStatus.READY,
        accepted=(ad_record,),
        publish_eligible=True,
        target_contract="CHANNEL_DAILY",
    )
    mixed = BatchResult(
        "mixed",
        BatchStatus.READY,
        accepted=(ad_record, other_record),
        publish_eligible=True,
        target_contract="AD_DAILY",
    )
    assert publisher.publish(mismatch) is False
    assert publisher.current == before
    assert publisher.publish(mixed) is False
    assert publisher.current == before


def test_publisher_rejects_provenance_contract_mismatch_without_mutation():
    ad_record = ingest(tool_result()).accepted[0]
    malformed = replace(
        ad_record,
        provenance=replace(ad_record.provenance, target_contract="CHANNEL_DAILY"),
    )
    publisher = InMemoryReferencePublisher()
    before = publisher.current
    result = BatchResult(
        "bad-provenance",
        BatchStatus.READY,
        accepted=(malformed,),
        publish_eligible=True,
        target_contract="AD_DAILY",
    )
    assert publisher.publish(result) is False
    assert publisher.current == before


def test_publisher_plans_all_records_before_mutation():
    ad_record = ingest(tool_result()).accepted[0]
    row_b = list(ROW)
    row_b[2] = "ext-002"
    row_b[3] = "cmp-2"
    new_record = ingest(
        tool_result((tuple(row_b),), raw=b"new-b"),
        sku_mapping={("tabular_file", "external_product_id", "ext-002"): "TS-SYNTH-001"},
    ).accepted[0]
    conflicting = replace(ad_record, canonical_business_hash="sha256:" + "0" * 64)
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(ingest(tool_result()))
    before = publisher.current
    result = BatchResult(
        "atomic-conflict",
        BatchStatus.READY,
        accepted=(new_record, conflicting),
        publish_eligible=True,
        target_contract="AD_DAILY",
    )
    assert publisher.publish(result) is False
    assert publisher.current == before


def _assert_publisher_rejects_without_mutation(malformed):
    valid = ingest(tool_result())
    record = valid.accepted[0]
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(valid) is True
    before_current = publisher.current
    before_ingestion_identity = publisher.last_ingestion_identity
    before_lookup = publisher.get_current("AD_DAILY", record.natural_key)
    before_count = len(publisher.current or ())

    assert publisher.publish(malformed) is False

    assert publisher.current == before_current
    assert len(publisher.current or ()) == before_count
    assert publisher.get_current("AD_DAILY", record.natural_key) is before_lookup
    assert publisher.last_ingestion_identity == before_ingestion_identity


@pytest.mark.parametrize(
    "accepted_factory",
    [
        lambda record: 1,
        lambda record: "not-records",
        lambda record: {},
        lambda record: [],
        lambda record: (item for item in (record,)),
        lambda record: (object(),),
    ],
    ids=["integer", "string", "mapping", "list", "generator", "wrong-item"],
)
def test_publisher_rejects_malformed_accepted_collection_without_mutation(accepted_factory):
    valid = ingest(tool_result())
    malformed = replace(valid, accepted=accepted_factory(valid.accepted[0]))
    _assert_publisher_rejects_without_mutation(malformed)


@pytest.mark.parametrize(
    ("field", "value_factory"),
    [
        ("rejected", lambda: []),
        ("duplicates", lambda: {}),
        ("conflicts", lambda: iter(())),
        ("rejected", lambda: (object(),)),
        ("duplicates", lambda: (object(),)),
        ("conflicts", lambda: (object(),)),
    ],
    ids=[
        "rejected-shape",
        "duplicates-shape",
        "conflicts-shape",
        "rejected-item",
        "duplicates-item",
        "conflicts-item",
    ],
)
def test_publisher_rejects_other_malformed_result_collections_without_mutation(
    field, value_factory
):
    valid = ingest(tool_result())
    malformed = replace(valid, **{field: value_factory()})
    _assert_publisher_rejects_without_mutation(malformed)


@pytest.mark.parametrize(
    "natural_key_factory",
    [
        lambda: [],
        lambda: {},
        lambda: set(),
        lambda: "text",
        lambda: 1,
        lambda: None,
        lambda: (),
        lambda: ("COUPANG", ["nested"]),
    ],
    ids=["list", "mapping", "set", "string", "integer", "none", "empty", "nested-list"],
)
def test_publisher_rejects_unsafe_natural_keys_without_mutation(natural_key_factory):
    valid = ingest(tool_result())
    malformed_record = replace(valid.accepted[0], natural_key=natural_key_factory())
    malformed = replace(valid, accepted=(malformed_record,))
    _assert_publisher_rejects_without_mutation(malformed)


@pytest.mark.parametrize(
    "malformed_factory",
    [
        lambda valid: replace(
            valid,
            accepted=(replace(valid.accepted[0], contract_name="UNKNOWN"),),
        ),
        lambda valid: replace(valid, target_contract="CHANNEL_DAILY"),
        lambda valid: replace(
            valid,
            accepted=(replace(valid.accepted[0], provenance=object()),),
        ),
        lambda valid: replace(
            valid,
            accepted=(
                replace(
                    valid.accepted[0],
                    provenance=replace(
                        valid.accepted[0].provenance, target_contract="CHANNEL_DAILY"
                    ),
                ),
            ),
        ),
        lambda valid: replace(
            valid,
            accepted=(replace(valid.accepted[0], canonical_business_hash=1),),
        ),
    ],
    ids=[
        "invalid-contract",
        "batch-contract-mismatch",
        "invalid-provenance",
        "provenance-contract-mismatch",
        "invalid-business-hash",
    ],
)
def test_publisher_rejects_malformed_accepted_records_without_mutation(malformed_factory):
    valid = ingest(tool_result())
    _assert_publisher_rejects_without_mutation(malformed_factory(valid))


@pytest.mark.parametrize(
    "malformed_factory",
    [
        lambda valid: object(),
        lambda valid: replace(valid, target_contract=1),
        lambda valid: replace(valid, status="READY"),
        lambda valid: replace(valid, status=1),
        lambda valid: replace(valid, publish_eligible=1),
        lambda valid: replace(valid, publish_eligible="true"),
        lambda valid: replace(valid, ingestion_identity=1),
    ],
    ids=[
        "outer-object",
        "target-contract",
        "status-string",
        "status-integer",
        "eligible-integer",
        "eligible-string",
        "ingestion-identity",
    ],
)
def test_publisher_rejects_malformed_control_fields_without_mutation(malformed_factory):
    valid = ingest(tool_result())
    _assert_publisher_rejects_without_mutation(malformed_factory(valid))


def test_publisher_preserves_valid_ready_batch_with_duplicate_evidence():
    result = ingest(tool_result((ROW, ROW), raw=b"batch-with-duplicate"))
    assert result.status is BatchStatus.READY
    assert len(result.accepted) == 1
    assert len(result.duplicates) == 1
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(result) is True
    assert publisher.current == result.accepted
    assert publisher.last_ingestion_identity == result.ingestion_identity
