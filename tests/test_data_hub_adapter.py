from __future__ import annotations

from datetime import datetime

import pytest

from topspeed_ai_os.core.ids import generate_run_id
from topspeed_ai_os.data_hub import (
    BatchStatus,
    InMemoryReferencePublisher,
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

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=datetime.now().astimezone().tzinfo)
RUN = generate_run_id()
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


def tool_result(rows=(ROW,), *, raw=b"synthetic-row", status=ToolStatus.SUCCESS, parsed=None):
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
        run_id=RUN,
        source_metadata=SourceMetadata(
            source="tabular_file",
            source_uri="csv://synthetic/ad-daily.csv",
            fetched_at=NOW,
            data_as_of=None,
            checksum_sha256=raw_sha256(raw),
        ),
        raw_result=SensitiveBytes(raw),
        parsed_result=parsed,
        error=error,
    )


def ingest(result, **kwargs):
    mapping = kwargs.pop(
        "sku_mapping",
        {("tabular_file", "external_product_id", "ext-001"): "TS-SYNTH-001"},
    )
    return ingest_ad_daily(
        result,
        run_id=RUN,
        known_skus={"TS-SYNTH-001"},
        sku_mapping=mapping,
        clock=lambda: NOW,
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
