from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from datetime import datetime
from types import ModuleType
from typing import Any

import pytest

import topspeed_ai_os.data_hub.adapter as ad_runtime
import topspeed_ai_os.data_hub.channel_daily as channel_runtime
import topspeed_ai_os.data_hub.content_asset as content_runtime
import topspeed_ai_os.data_hub.inventory as inventory_runtime
import topspeed_ai_os.data_hub.product_fact as fact_runtime
import topspeed_ai_os.data_hub.product_master as master_runtime
from tests import (
    test_data_hub_adapter as ad_test,
)
from tests import (
    test_data_hub_channel_daily as channel_test,
)
from tests import (
    test_data_hub_content_asset as content_test,
)
from tests import (
    test_data_hub_inventory as inventory_test,
)
from tests import (
    test_data_hub_product_fact as fact_test,
)
from tests import (
    test_data_hub_product_master as master_test,
)
from topspeed_ai_os.data_hub import InMemoryReferencePublisher
from topspeed_ai_os.data_hub.adapter import (
    AcceptedRecord,
    ConflictRecord,
    DataAsOfState,
    DuplicateRecord,
    Provenance,
    ReasonCode,
    RejectedRecord,
    RowTrace,
    _make_row_trace,
)
from topspeed_ai_os.tools.result import SourceMetadata, ToolResult

TASK = "task_01J00000000000000000000000"
INVALID_TASK = "legacy-task"
ROW_TRACE_FIELDS = (
    "target_contract",
    "schema_version",
    "source",
    "source_reference",
    "source_checksum",
    "source_row_reference",
    "data_as_of",
    "data_as_of_state",
    "run_id",
    "task_id",
)


@dataclass(frozen=True)
class AdapterCase:
    target_contract: str
    runtime: ModuleType
    build: Callable[[dict[str, object], bytes, str | None], ToolResult]
    ingest: Callable[..., Any]
    valid_rejection: dict[str, object]
    conflict: dict[str, object]
    validates_task_id: bool


def _ad_build(changes: dict[str, object], raw: bytes, task_id: str | None) -> ToolResult:
    values = dict(zip(ad_test.HEADERS, ad_test.ROW, strict=True))
    values.update(changes)
    row = tuple(values[header] for header in ad_test.HEADERS)
    return replace(ad_test.tool_result((row,), raw=raw), task_id=task_id)


def _module_build(
    module: ModuleType, changes: dict[str, object], raw: bytes, task_id: str | None
) -> ToolResult:
    result = module.tool_result(rows=(module.row_for(**changes),), raw=raw)
    return replace(result, task_id=task_id)


CASES = (
    AdapterCase(
        "AD_DAILY",
        ad_runtime,
        _ad_build,
        ad_test.ingest,
        {"external_product_id": "unknown"},
        {"ad_orders": "3"},
        False,
    ),
    AdapterCase(
        "PRODUCT_MASTER",
        master_runtime,
        lambda changes, raw, task_id: _module_build(master_test, changes, raw, task_id),
        master_test.ingest,
        {"product_name": ""},
        {"product_name": "Changed product"},
        False,
    ),
    AdapterCase(
        "PRODUCT_FACT",
        fact_runtime,
        lambda changes, raw, task_id: _module_build(fact_test, changes, raw, task_id),
        fact_test.ingest,
        {"sku": fact_test.OTHER_SKU},
        {"fact_value": '{"value":"changed"}'},
        True,
    ),
    AdapterCase(
        "CHANNEL_DAILY",
        channel_runtime,
        lambda changes, raw, task_id: _module_build(channel_test, changes, raw, task_id),
        channel_test.ingest,
        {"external_product_id": "unknown"},
        {"orders": "103"},
        False,
    ),
    AdapterCase(
        "INVENTORY",
        inventory_runtime,
        lambda changes, raw, task_id: _module_build(inventory_test, changes, raw, task_id),
        inventory_test.ingest,
        {"external_product_id": "unknown"},
        {"on_hand_qty": "321"},
        False,
    ),
    AdapterCase(
        "CONTENT_ASSET",
        content_runtime,
        lambda changes, raw, task_id: _module_build(content_test, changes, raw, task_id),
        content_test.ingest,
        {"sku": content_test.OTHER_SKU},
        {"title": "Changed title"},
        True,
    ),
)


def _assert_authority(
    trace: RowTrace,
    case: AdapterCase,
    tool_result: ToolResult,
    state: DataAsOfState,
) -> None:
    metadata = tool_result.source_metadata
    assert isinstance(metadata, SourceMetadata)
    assert trace.target_contract == case.target_contract
    assert trace.schema_version == getattr(case.runtime, f"{case.target_contract}_SCHEMA")
    assert trace.source == metadata.source
    assert trace.source_reference == metadata.source_uri
    assert trace.source_checksum == metadata.checksum_sha256
    assert trace.source_row_reference == "CSV row:2"
    assert trace.data_as_of_state is state
    assert trace.run_id == tool_result.run_id
    assert trace.task_id == tool_result.task_id


def _assert_projection(record: AcceptedRecord | DuplicateRecord) -> None:
    trace = record.trace
    provenance = record.provenance
    assert trace.target_contract == provenance.target_contract
    assert trace.schema_version == provenance.schema_version
    assert trace.source == provenance.source
    assert trace.source_reference == provenance.source_reference
    assert trace.source_checksum == provenance.source_checksum
    assert trace.source_row_reference == provenance.source_row_reference
    assert trace.data_as_of == provenance.data_as_of
    assert trace.run_id == provenance.run_id
    assert trace.task_id == provenance.task_id
    assert trace.data_as_of_state is DataAsOfState.VALID


def test_row_trace_exact_contract_state_and_immutability() -> None:
    assert tuple(field.name for field in fields(RowTrace)) == ROW_TRACE_FIELDS
    assert {state.value for state in DataAsOfState} == {"VALID", "MISSING", "INVALID"}
    trace = _make_row_trace(
        target_contract="AD_DAILY",
        schema_version=ad_runtime.AD_DAILY_SCHEMA,
        source="tabular_file",
        source_reference="csv://synthetic/ad-daily.csv",
        source_checksum="sha256:" + "a" * 64,
        source_row_reference="CSV row:2",
        raw_data_as_of="2026-10-06T08:00:00+09:00",
        run_id=ad_test.RUN,
        task_id=None,
    )
    with pytest.raises(FrozenInstanceError):
        trace.source = "changed"  # type: ignore[misc]


def test_outcome_positional_constructors_remain_compatible() -> None:
    parsed = datetime.fromisoformat("2026-10-06T08:00:00+09:00")
    provenance = Provenance(
        "tabular_file",
        "csv://synthetic/source.csv",
        "sha256:" + "a" * 64,
        parsed,
        parsed,
        "source_row:data_as_of",
        None,
        ad_test.RUN,
        "CSV row:2",
        ad_runtime.AD_DAILY_SCHEMA,
        "sha256:" + "b" * 64,
        "sha256:" + "c" * 64,
        (),
        "AD_DAILY",
        ("key",),
        "sha256:" + "d" * 64,
    )
    accepted = AcceptedRecord(
        "AD_DAILY", {}, ("key",), provenance.canonical_business_hash, provenance
    )
    duplicate = DuplicateRecord("CSV row:2", ("key",), ReasonCode.BUSINESS_DUPLICATE, provenance)
    rejected = RejectedRecord(
        "CSV row:2", ReasonCode.INVALID_SOURCE_VALUE, "rejected", provenance.source_reference
    )
    conflict = ConflictRecord(
        "CSV row:2", ("key",), ReasonCode.NATURAL_KEY_CONFLICT, provenance.source_reference
    )
    assert accepted.trace == duplicate.trace
    assert rejected.trace is None
    assert conflict.trace is None
    assert "trace" not in accepted.validated_record


def test_row_trace_date_states_use_existing_parser_without_raw_retention() -> None:
    common = {
        "target_contract": "AD_DAILY",
        "schema_version": ad_runtime.AD_DAILY_SCHEMA,
        "source": "tabular_file",
        "source_reference": "csv://synthetic/ad-daily.csv",
        "source_checksum": "sha256:" + "a" * 64,
        "source_row_reference": "CSV row:2",
        "run_id": ad_test.RUN,
        "task_id": None,
    }
    valid = _make_row_trace(raw_data_as_of="2026-10-06T08:00:00+09:00", **common)
    missing = _make_row_trace(raw_data_as_of="", **common)
    invalid = _make_row_trace(raw_data_as_of="malformed-sensitive-date", **common)
    assert valid.data_as_of == datetime.fromisoformat("2026-10-06T08:00:00+09:00")
    assert valid.data_as_of_state is DataAsOfState.VALID
    assert missing.data_as_of is None
    assert missing.data_as_of_state is DataAsOfState.MISSING
    assert invalid.data_as_of is None
    assert invalid.data_as_of_state is DataAsOfState.INVALID
    assert "malformed-sensitive-date" not in repr(invalid)


def test_rejected_and_conflict_trace_mismatch_fails_closed() -> None:
    trace = _make_row_trace(
        target_contract="AD_DAILY",
        schema_version=ad_runtime.AD_DAILY_SCHEMA,
        source="tabular_file",
        source_reference="csv://synthetic/ad-daily.csv",
        source_checksum="sha256:" + "a" * 64,
        source_row_reference="CSV row:2",
        raw_data_as_of="2026-10-06T08:00:00+09:00",
        run_id=ad_test.RUN,
        task_id=None,
    )
    with pytest.raises(ValueError, match="batch-level"):
        RejectedRecord("batch", ReasonCode.INVALID_SOURCE_VALUE, "bad", "", trace=trace)
    with pytest.raises(ValueError, match="top-level"):
        RejectedRecord("CSV row:3", ReasonCode.INVALID_SOURCE_VALUE, "bad", "other", trace=trace)
    with pytest.raises(ValueError, match="top-level"):
        ConflictRecord("CSV row:3", ("key",), ReasonCode.NATURAL_KEY_CONFLICT, "other", trace)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.target_contract)
def test_six_adapter_row_outcome_traceability_matrix(case: AdapterCase) -> None:
    accepted_tool = case.build({}, f"{case.target_contract}:accepted".encode(), TASK)
    accepted_result = case.ingest(accepted_tool)
    accepted = accepted_result.accepted[0]
    _assert_authority(accepted.trace, case, accepted_tool, DataAsOfState.VALID)
    _assert_projection(accepted)
    assert "trace" not in accepted.validated_record

    duplicate_tool = case.build({}, f"{case.target_contract}:duplicate".encode(), TASK)
    duplicate_result = case.ingest(duplicate_tool, existing=accepted_result.accepted)
    duplicate = duplicate_result.duplicates[0]
    _assert_authority(duplicate.trace, case, duplicate_tool, DataAsOfState.VALID)
    _assert_projection(duplicate)

    valid_rejection_tool = case.build(
        case.valid_rejection, f"{case.target_contract}:valid-rejection".encode(), TASK
    )
    valid_rejection = case.ingest(valid_rejection_tool).rejected[0]
    assert valid_rejection.trace is not None
    _assert_authority(valid_rejection.trace, case, valid_rejection_tool, DataAsOfState.VALID)
    assert valid_rejection.trace.data_as_of is not None

    missing_tool = case.build(
        {"data_as_of": ""}, f"{case.target_contract}:missing-date".encode(), TASK
    )
    missing = case.ingest(missing_tool).rejected[0]
    assert missing.trace is not None
    _assert_authority(missing.trace, case, missing_tool, DataAsOfState.MISSING)
    assert missing.trace.data_as_of is None

    invalid_tool = case.build(
        {"data_as_of": "invalid-date"},
        f"{case.target_contract}:invalid-date".encode(),
        TASK,
    )
    invalid = case.ingest(invalid_tool).rejected[0]
    assert invalid.trace is not None
    _assert_authority(invalid.trace, case, invalid_tool, DataAsOfState.INVALID)
    assert invalid.trace.data_as_of is None
    assert "invalid-date" not in invalid.sanitized_summary
    assert "invalid-date" not in repr(invalid.trace)

    conflict_tool = case.build(case.conflict, f"{case.target_contract}:conflict".encode(), TASK)
    conflict = case.ingest(conflict_tool, existing=accepted_result.accepted).conflicts[0]
    assert conflict.trace is not None
    _assert_authority(conflict.trace, case, conflict_tool, DataAsOfState.VALID)
    assert conflict.trace.source_reference == conflict.source_reference
    assert conflict.trace.source_row_reference == conflict.source_row_reference


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.target_contract)
def test_task_id_acceptance_rules_are_unchanged(case: AdapterCase) -> None:
    tool_result = case.build({}, f"{case.target_contract}:task-regression".encode(), INVALID_TASK)
    result = case.ingest(tool_result)
    if case.validates_task_id:
        assert not result.accepted
        assert result.rejected[0].source_row_reference == "batch"
        assert result.rejected[0].trace is None
    else:
        assert result.accepted[0].trace.task_id == INVALID_TASK


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.target_contract)
def test_source_duplicate_remains_rowless_and_side_effect_free(
    case: AdapterCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool_result = case.build({}, f"{case.target_contract}:source-duplicate".encode(), TASK)
    first = case.ingest(tool_result)
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(first) is True
    published = publisher.current
    published_identity = publisher.last_ingestion_identity

    trace_calls = 0
    original_trace_factory = case.runtime._make_row_trace

    def counted_trace_factory(**kwargs: object) -> RowTrace:
        nonlocal trace_calls
        trace_calls += 1
        return original_trace_factory(**kwargs)

    clock_calls = 0

    def counted_clock() -> datetime:
        nonlocal clock_calls
        clock_calls += 1
        return datetime.fromisoformat("2026-10-06T12:00:00+09:00")

    id_calls = 0
    if case.runtime is fact_runtime:

        def counted_fact_id() -> str:
            nonlocal id_calls
            id_calls += 1
            return fact_test.FACT

        monkeypatch.setattr(case.runtime, "generate_fact_id", counted_fact_id)
    elif case.runtime is content_runtime:

        def counted_asset_id() -> str:
            nonlocal id_calls
            id_calls += 1
            return content_test.ASSET

        monkeypatch.setattr(case.runtime, "generate_asset_id", counted_asset_id)

    monkeypatch.setattr(case.runtime, "_make_row_trace", counted_trace_factory)
    replay = case.ingest(tool_result, existing=first.accepted, clock=counted_clock)
    assert replay.batch_reason is ReasonCode.SOURCE_DUPLICATE
    assert not replay.accepted
    assert not replay.rejected
    assert not replay.duplicates
    assert not replay.conflicts
    assert trace_calls == 0
    assert clock_calls == 0
    assert id_calls == 0
    assert publisher.publish(replay) is False
    assert publisher.current == published
    assert publisher.last_ingestion_identity == published_identity


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.target_contract)
def test_unsafe_source_reference_is_not_retained_in_trace(case: AdapterCase) -> None:
    tool_result = case.build({}, f"{case.target_contract}:unsafe".encode(), TASK)
    metadata = tool_result.source_metadata
    assert isinstance(metadata, SourceMetadata)
    unsafe = "https://user:password@example.test/data?access_token=secret-value"
    unsafe_result = replace(tool_result, source_metadata=replace(metadata, source_uri=unsafe))
    result = case.ingest(unsafe_result)
    assert not result.accepted
    assert result.rejected[0].trace is None
    assert unsafe not in repr(result)
    assert "secret-value" not in repr(result)


def test_six_contract_records_publish_without_trace_in_business_payload() -> None:
    publisher = InMemoryReferencePublisher()
    for case in CASES:
        tool_result = case.build({}, f"{case.target_contract}:publisher".encode(), TASK)
        result = case.ingest(tool_result)
        assert publisher.publish(result) is True
        assert "trace" not in result.accepted[0].validated_record
    assert publisher.current is not None
    assert {record.contract_name for record in publisher.current} == {
        case.target_contract for case in CASES
    }
