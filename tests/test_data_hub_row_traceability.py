from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from datetime import datetime
from inspect import signature
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
    PHASE4_SCHEMA_BY_CONTRACT,
    AcceptedRecord,
    BatchResult,
    ConflictRecord,
    DataAsOfState,
    DuplicateRecord,
    Provenance,
    ReasonCode,
    RejectedRecord,
    RowTrace,
    _make_row_trace,
    _record_identity,
    _record_publication_safe,
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


def _valid_result(case: AdapterCase, suffix: str) -> BatchResult:
    tool_result = case.build({}, f"{case.target_contract}:{suffix}".encode(), TASK)
    return case.ingest(tool_result)


def _seeded_publisher(
    excluded_contract: str,
) -> tuple[
    InMemoryReferencePublisher,
    tuple[AcceptedRecord, ...],
    str | None,
]:
    seed_case = next(case for case in CASES if case.target_contract != excluded_contract)
    seed_result = _valid_result(seed_case, f"seed-for-{excluded_contract}")
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(seed_result) is True
    assert publisher.current is not None
    return publisher, publisher.current, publisher.last_ingestion_identity


def _assert_atomic_publication_rejection(result: BatchResult, *, excluded_contract: str) -> None:
    publisher, current_before, identity_before = _seeded_publisher(excluded_contract)
    assert publisher.publish(result) is False
    assert publisher.current == current_before
    assert publisher.last_ingestion_identity == identity_before


def _canonical_snapshot(result: BatchResult, record: AcceptedRecord) -> tuple[object, ...]:
    return (
        result.ingestion_identity,
        record.provenance.ingestion_identity,
        record.provenance.mapping_fingerprint,
        record.natural_key,
        record.canonical_business_hash,
        _record_identity(record),
        record.provenance.source_checksum,
        result.status,
        result.batch_reason,
        result.publish_eligible,
        len(result.accepted),
        len(result.rejected),
        len(result.duplicates),
        len(result.conflicts),
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.target_contract)
def test_trace_only_copy_cannot_change_identity_or_classification(case: AdapterCase) -> None:
    accepted_result = _valid_result(case, "identity-baseline")
    accepted = accepted_result.accepted[0]
    accepted_before = _canonical_snapshot(accepted_result, accepted)

    foreign_schema = next(
        schema
        for contract, schema in PHASE4_SCHEMA_BY_CONTRACT.items()
        if contract != case.target_contract
    )
    detached_trace = replace(accepted.trace, schema_version=foreign_schema)
    assert detached_trace.schema_version != accepted.trace.schema_version
    assert _canonical_snapshot(accepted_result, accepted) == accepted_before

    duplicate_tool = case.build({}, f"{case.target_contract}:identity-duplicate".encode(), TASK)
    duplicate_result = case.ingest(duplicate_tool, existing=accepted_result.accepted)
    duplicate = duplicate_result.duplicates[0]
    duplicate_before = (
        duplicate_result.ingestion_identity,
        duplicate.provenance.ingestion_identity,
        duplicate.provenance.mapping_fingerprint,
        duplicate.natural_key,
        duplicate.provenance.canonical_business_hash,
        (duplicate.provenance.target_contract, duplicate.natural_key),
        duplicate.provenance.source_checksum,
        duplicate.duplicate_reason,
        duplicate_result.status,
        duplicate_result.batch_reason,
        duplicate_result.publish_eligible,
    )
    detached_duplicate_trace = replace(duplicate.trace, schema_version=foreign_schema)
    assert detached_duplicate_trace.schema_version != duplicate.trace.schema_version
    assert (
        duplicate_result.ingestion_identity,
        duplicate.provenance.ingestion_identity,
        duplicate.provenance.mapping_fingerprint,
        duplicate.natural_key,
        duplicate.provenance.canonical_business_hash,
        (duplicate.provenance.target_contract, duplicate.natural_key),
        duplicate.provenance.source_checksum,
        duplicate.duplicate_reason,
        duplicate_result.status,
        duplicate_result.batch_reason,
        duplicate_result.publish_eligible,
    ) == duplicate_before
    assert duplicate.duplicate_reason is ReasonCode.BUSINESS_DUPLICATE


def test_accepted_rejects_independent_conflicting_trace_input() -> None:
    accepted = _valid_result(CASES[0], "accepted-projection-negative").accepted[0]
    foreign_trace = _valid_result(CASES[1], "accepted-foreign-trace").accepted[0].trace
    assert "trace" not in signature(AcceptedRecord).parameters
    with pytest.raises(TypeError, match="trace"):
        replace(accepted, trace=foreign_trace)
    assert accepted.trace.target_contract == accepted.provenance.target_contract
    assert accepted.trace.schema_version == accepted.provenance.schema_version


def test_business_duplicate_rejects_independent_conflicting_trace_input() -> None:
    case = CASES[0]
    accepted_result = _valid_result(case, "duplicate-projection-baseline")
    duplicate_tool = case.build({}, b"duplicate-projection-candidate", TASK)
    duplicate = case.ingest(duplicate_tool, existing=accepted_result.accepted).duplicates[0]
    foreign_trace = _valid_result(CASES[1], "duplicate-foreign-trace").accepted[0].trace
    assert "trace" not in signature(DuplicateRecord).parameters
    with pytest.raises(TypeError, match="trace"):
        replace(duplicate, trace=foreign_trace)
    assert duplicate.trace.target_contract == duplicate.provenance.target_contract
    assert duplicate.trace.schema_version == duplicate.provenance.schema_version


def test_observed_content_asset_product_master_schema_contamination_is_rejected() -> None:
    content_result = _valid_result(CASES[5], "observed-schema-defect")
    content_record = content_result.accepted[0]
    product_master_schema = PHASE4_SCHEMA_BY_CONTRACT["PRODUCT_MASTER"]
    contaminated = replace(
        content_record,
        provenance=replace(content_record.provenance, schema_version=product_master_schema),
    )
    assert contaminated.trace.schema_version == product_master_schema
    assert _record_publication_safe(contaminated, "CONTENT_ASSET") is False
    _assert_atomic_publication_rejection(
        replace(content_result, accepted=(contaminated,)),
        excluded_contract="CONTENT_ASSET",
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.target_contract)
def test_six_contract_schema_matrix_and_unknown_schema_rejection(case: AdapterCase) -> None:
    result = _valid_result(case, "schema-matrix")
    record = result.accepted[0]
    expected_schema = PHASE4_SCHEMA_BY_CONTRACT[case.target_contract]
    assert record.provenance.schema_version == expected_schema
    assert record.trace.schema_version == expected_schema
    assert _record_publication_safe(record, case.target_contract) is True

    publisher = InMemoryReferencePublisher()
    assert publisher.publish(result) is True
    assert publisher.current == (record,)
    assert publisher.last_ingestion_identity == result.ingestion_identity

    foreign_schemas = {
        schema
        for contract, schema in PHASE4_SCHEMA_BY_CONTRACT.items()
        if contract != case.target_contract
    }
    foreign_schemas.add("topspeed.unknown.synthetic.v1")
    for foreign_schema in foreign_schemas:
        contaminated = replace(
            record,
            provenance=replace(record.provenance, schema_version=foreign_schema),
        )
        assert contaminated.trace.schema_version == foreign_schema
        assert _record_publication_safe(contaminated, case.target_contract) is False
        _assert_atomic_publication_rejection(
            replace(result, accepted=(contaminated,)),
            excluded_contract=case.target_contract,
        )


def test_cross_contract_target_contamination_is_rejected_atomically() -> None:
    content_result = _valid_result(CASES[5], "target-contamination")
    content_record = content_result.accepted[0]
    foreign_target = "PRODUCT_MASTER"

    mutations = (
        replace(content_record, contract_name=foreign_target),
        replace(
            content_record,
            provenance=replace(content_record.provenance, target_contract=foreign_target),
        ),
    )
    for contaminated in mutations:
        assert _record_publication_safe(contaminated, "CONTENT_ASSET") is False
        _assert_atomic_publication_rejection(
            replace(content_result, accepted=(contaminated,)),
            excluded_contract="CONTENT_ASSET",
        )

    mismatched_batch = replace(content_result, target_contract=foreign_target)
    assert _record_publication_safe(content_record, foreign_target) is False
    _assert_atomic_publication_rejection(
        mismatched_batch,
        excluded_contract="CONTENT_ASSET",
    )


@pytest.mark.parametrize("non_phase4_target", ("APPROVAL_QUEUE", "AI_RUN_LOG"))
def test_non_phase4_repository_contract_target_fails_closed(non_phase4_target: str) -> None:
    result = _valid_result(CASES[5], f"non-phase4-{non_phase4_target}")
    record = result.accepted[0]
    contaminated = replace(
        record,
        contract_name=non_phase4_target,
        provenance=replace(
            record.provenance,
            target_contract=non_phase4_target,
            schema_version=f"topspeed.{non_phase4_target.lower()}.synthetic.v1",
        ),
    )
    contaminated_result = replace(
        result,
        accepted=(contaminated,),
        target_contract=non_phase4_target,
    )
    assert non_phase4_target not in PHASE4_SCHEMA_BY_CONTRACT
    assert _record_publication_safe(contaminated, non_phase4_target) is False
    _assert_atomic_publication_rejection(
        contaminated_result,
        excluded_contract="CONTENT_ASSET",
    )


def test_unknown_batch_target_fails_closed_without_publisher_mutation() -> None:
    result = _valid_result(CASES[5], "unknown-target")
    unknown_target_result = replace(result, target_contract="UNKNOWN")
    _assert_atomic_publication_rejection(
        unknown_target_result,
        excluded_contract="CONTENT_ASSET",
    )
