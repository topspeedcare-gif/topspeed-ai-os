from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

import topspeed_ai_os.data_hub.product_fact as product_fact_module
from topspeed_ai_os.contracts import validate_contract
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.data_hub import (
    PRODUCT_FACT_SCHEMA,
    BatchStatus,
    InMemoryReferencePublisher,
    ReasonCode,
    ingest_ad_daily,
    ingest_channel_daily,
    ingest_inventory,
    ingest_product_fact,
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

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone(timedelta(hours=9)))
RUN = "run_01J00000000000000000000000"
OTHER_RUN = "run_01J00000000000000000000001"
TASK = "task_01J00000000000000000000000"
OTHER_TASK = "task_01J00000000000000000000001"
SKU = "TS-SYNTH-001"
OTHER_SKU = "TS-SYNTH-002"
KNOWN_SKUS = {SKU}
HEADERS = ("sku", "fact_type", "fact_value", "data_as_of")
VALUES: dict[str, object] = {
    "sku": SKU,
    "fact_type": "material",
    "fact_value": '{"value":"STS304","details":{"grade":"food"}}',
    "data_as_of": "2026-09-30T08:00:00+09:00",
}


def row_for(headers: tuple[object, ...] = HEADERS, **changes: object) -> tuple[object, ...]:
    values = {**VALUES, **changes}
    return tuple(values[str(header)] for header in headers)


def tool_result(
    *,
    headers: tuple[object, ...] = HEADERS,
    rows: tuple[tuple[object, ...], ...] | None = None,
    raw: bytes = b"product-fact-synthetic",
    parsed: object | None = None,
    status: ToolStatus = ToolStatus.SUCCESS,
    source: str = "tabular_file",
    source_uri: str = "csv://synthetic/product-fact.csv",
    metadata_data_as_of: datetime | None = None,
    fetched_at: datetime = NOW,
    tool_run_id: str | None = RUN,
    task_id: str | None = None,
) -> ToolResult:
    if rows is None:
        rows = (row_for(headers),)
    if parsed is None:
        parsed = TabularData(headers, rows, None)
    return ToolResult(
        tool_name="tabular_read",
        operation="tabular.read_csv",
        request_id="req_" + ("8" * 32),
        status=status,
        execution_mode=ExecutionMode.MOCK,
        task_id=task_id,
        run_id=tool_run_id,
        source_metadata=SourceMetadata(
            source=source,
            source_uri=source_uri,
            fetched_at=fetched_at,
            data_as_of=metadata_data_as_of,
            checksum_sha256=raw_sha256(raw),
        ),
        raw_result=SensitiveBytes(raw),
        parsed_result=parsed,
    )


def ingest(result: object | None = None, **kwargs: object):
    return ingest_product_fact(
        tool_result() if result is None else result,
        run_id=kwargs.pop("run_id", RUN),
        known_skus=kwargs.pop("known_skus", KNOWN_SKUS),
        clock=kwargs.pop("clock", lambda: NOW),
        **kwargs,
    )


def with_values(**changes: object) -> ToolResult:
    raw = repr(sorted(changes.items())).encode()
    return tool_result(rows=(row_for(**changes),), raw=raw)


class IterableRuntimeError:
    def __iter__(self):
        raise RuntimeError("iteration failed")


class BoundaryStop(BaseException):
    pass


class IterableBaseException:
    def __iter__(self):
        raise BoundaryStop("stop")


def test_valid_row_builds_exact_unverified_contract_record():
    result = ingest()
    assert result.status is BatchStatus.READY
    assert result.publish_eligible is True
    record = result.accepted[0]
    validate_contract("PRODUCT_FACT", record.validated_record, known_skus=KNOWN_SKUS)
    assert record.validated_record == {
        "fact_id": record.validated_record["fact_id"],
        "sku": SKU,
        "fact_type": "material",
        "fact_value": {"value": "STS304", "details": {"grade": "food"}},
        "verification_status": "UNVERIFIED",
        "source": "tabular_file",
        "run_id": RUN,
        "data_as_of": VALUES["data_as_of"],
        "created_at": NOW.isoformat(),
    }
    assert record.validated_record["fact_id"].startswith("fact_")
    assert "verified_at" not in record.validated_record
    assert "valid_from" not in record.validated_record
    assert "valid_to" not in record.validated_record
    assert "source_uri" not in record.validated_record
    assert "source_checksum" not in record.validated_record
    assert record.natural_key == (SKU, "material", "tabular_file", VALUES["data_as_of"])
    assert record.provenance.target_contract == "PRODUCT_FACT"
    assert record.provenance.schema_version == PRODUCT_FACT_SCHEMA
    assert record.provenance.data_as_of_origin == "source_row:data_as_of"


def test_valid_multirow_batch_uses_one_clock_value():
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        return NOW

    rows = (
        row_for(),
        row_for(fact_type="dimensions", data_as_of="2026-09-30T08:01:00+09:00"),
    )
    result = ingest(tool_result(rows=rows, raw=b"multi"), clock=clock)
    assert result.status is BatchStatus.READY
    assert len(result.accepted) == 2
    assert calls == 1
    assert {item.validated_record["created_at"] for item in result.accepted} == {NOW.isoformat()}


def test_final_validation_calls_original_with_normalized_known_skus(monkeypatch):
    calls: list[tuple[object, ...]] = []
    original = product_fact_module.validate_contract

    def spy(*args, **kwargs):
        calls.append((*args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(product_fact_module, "validate_contract", spy)
    result = ingest(known_skus=[SKU])
    assert result.status is BatchStatus.READY
    assert calls == [
        ("PRODUCT_FACT", result.accepted[0].validated_record, {"known_skus": frozenset({SKU})})
    ]


@pytest.mark.parametrize("missing", HEADERS)
def test_missing_required_header_fails_batch_closed(missing):
    headers = tuple(field for field in HEADERS if field != missing)
    result = ingest(tool_result(headers=headers))
    assert result.status is BatchStatus.REJECTED
    assert result.batch_reason is ReasonCode.INVALID_ROW_SHAPE
    assert result.accepted == ()


@pytest.mark.parametrize(
    "extra",
    [
        "unknown",
        "fact_id",
        "verification_status",
        "source",
        "source_uri",
        "source_checksum",
        "verified_at",
        "valid_from",
        "valid_to",
        "created_at",
        "run_id",
        "task_id",
    ],
)
def test_unknown_and_forbidden_headers_fail_batch_closed(extra):
    headers = (*HEADERS, extra)
    result = ingest(tool_result(headers=headers, rows=(row_for(headers, **{extra: "x"}),)))
    assert result.batch_reason is ReasonCode.INVALID_ROW_SHAPE
    assert result.accepted == ()


def test_duplicate_empty_and_wrong_width_tabular_shapes_fail_closed():
    duplicate = ingest(
        tool_result(
            headers=(*HEADERS, "sku"),
            rows=(row_for((*HEADERS, "sku")),),
            raw=b"duplicate-header",
        )
    )
    empty = ingest(tool_result(rows=(), raw=b"empty"))
    width = ingest(tool_result(rows=(row_for()[:-1],), raw=b"width"))
    assert all(
        result.batch_reason is ReasonCode.INVALID_ROW_SHAPE for result in (duplicate, empty, width)
    )


def test_malformed_tool_and_tabular_boundaries_fail_closed():
    invalid_tool = ingest(object())
    invalid_parsed = ingest(tool_result(parsed=object()))
    assert invalid_tool.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert invalid_parsed.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert invalid_tool.accepted == invalid_parsed.accepted == ()


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("sku", None, ReasonCode.MISSING_REQUIRED_SOURCE_FIELD),
        ("fact_type", "", ReasonCode.MISSING_REQUIRED_SOURCE_FIELD),
        ("fact_value", " ", ReasonCode.MISSING_REQUIRED_SOURCE_FIELD),
        ("data_as_of", "", ReasonCode.INVALID_DATA_AS_OF),
        ("data_as_of", "2026-09-30T08:00:00", ReasonCode.INVALID_DATA_AS_OF),
    ],
)
def test_invalid_required_row_values_are_rejected(field, value, reason):
    result = ingest(with_values(**{field: value}))
    assert result.status is BatchStatus.REJECTED
    assert result.rejected[0].reason_code is reason


def test_unregistered_and_empty_known_skus_reject_rows():
    unknown = ingest(known_skus={OTHER_SKU})
    empty = ingest(known_skus=set())
    assert unknown.rejected[0].reason_code is ReasonCode.UNREGISTERED_SKU
    assert empty.rejected[0].reason_code is ReasonCode.UNREGISTERED_SKU


@pytest.mark.parametrize("known_skus", ["TS-SYNTH-001", b"sku", {"sku": SKU}, [SKU, 1]])
def test_malformed_known_skus_fail_batch_closed(known_skus):
    result = ingest(known_skus=known_skus)
    assert result.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert result.accepted == ()


def test_known_skus_runtime_error_fails_closed_and_base_exception_propagates():
    assert ingest(known_skus=IterableRuntimeError()).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    with pytest.raises(BoundaryStop):
        ingest(known_skus=IterableBaseException())


def test_known_skus_fingerprint_is_order_independent_and_membership_sensitive():
    ordered = ingest(tool_result(raw=b"fingerprint"), known_skus=[SKU, OTHER_SKU])
    reversed_order = ingest(tool_result(raw=b"fingerprint"), known_skus=[OTHER_SKU, SKU])
    changed = ingest(tool_result(raw=b"fingerprint"), known_skus=[SKU])
    assert (
        ordered.accepted[0].provenance.mapping_fingerprint
        == reversed_order.accepted[0].provenance.mapping_fingerprint
    )
    assert (
        ordered.accepted[0].provenance.mapping_fingerprint
        != changed.accepted[0].provenance.mapping_fingerprint
    )
    assert ordered.ingestion_identity == reversed_order.ingestion_identity
    assert ordered.ingestion_identity != changed.ingestion_identity


@pytest.mark.parametrize("value", ["", " ", " material", "material "])
def test_fact_type_whitespace_and_blank_values_are_rejected(value):
    result = ingest(with_values(fact_type=value))
    assert result.status is BatchStatus.REJECTED


def test_fact_type_preserves_exact_case():
    result = ingest(with_values(fact_type="MaTeRiAl"))
    assert result.accepted[0].validated_record["fact_type"] == "MaTeRiAl"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('{"value":"STS304"}', {"value": "STS304"}),
        ('["STS304",{"grade":"food"}]', ["STS304", {"grade": "food"}]),
    ],
)
def test_fact_value_accepts_only_object_or_array_json_text(value, expected):
    result = ingest(with_values(fact_value=value))
    assert result.status is BatchStatus.READY
    assert result.accepted[0].validated_record["fact_value"] == expected


@pytest.mark.parametrize(
    "value",
    [
        "null",
        '"text"',
        "1",
        "true",
        "{",
        '{"a":1,"a":2}',
        '{"outer":{"a":1,"a":2}}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":-Infinity}',
        '[{"value":NaN}]',
        {"value": "STS304"},
        ["STS304"],
        1,
        True,
    ],
)
def test_fact_value_rejects_invalid_json_boundaries(value):
    result = ingest(with_values(fact_value=value))
    assert result.status is BatchStatus.REJECTED
    assert result.rejected[0].reason_code in {
        ReasonCode.MISSING_REQUIRED_SOURCE_FIELD,
        ReasonCode.INVALID_SOURCE_VALUE,
    }


def test_canonical_fact_value_key_order_has_stable_business_hash():
    first = ingest(with_values(fact_value='{"a":1,"b":{"x":2,"y":3}}'))
    second = ingest(
        tool_result(
            rows=(row_for(fact_value='{"b":{"y":3,"x":2},"a":1}'),),
            raw=b"reordered-json",
        ),
        existing=first.accepted,
    )
    assert second.status is BatchStatus.DUPLICATE
    assert second.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE
    assert (
        second.duplicates[0].provenance.canonical_business_hash
        == first.accepted[0].canonical_business_hash
    )


def test_unit_absent_null_blank_and_preserved_semantics():
    absent = ingest(tool_result(raw=b"unit-absent"))
    headers = (*HEADERS, "unit")
    none = ingest(
        tool_result(headers=headers, rows=(row_for(headers, unit=None),), raw=b"unit-none")
    )
    blank = ingest(
        tool_result(headers=headers, rows=(row_for(headers, unit=""),), raw=b"unit-blank")
    )
    spaces = ingest(
        tool_result(headers=headers, rows=(row_for(headers, unit="   "),), raw=b"unit-spaces")
    )
    exact = ingest(
        tool_result(headers=headers, rows=(row_for(headers, unit=" Mm "),), raw=b"unit-exact")
    )
    assert "unit" not in absent.accepted[0].validated_record
    assert none.accepted[0].validated_record["unit"] is None
    assert blank.accepted[0].validated_record["unit"] is None
    assert spaces.accepted[0].validated_record["unit"] is None
    assert exact.accepted[0].validated_record["unit"] == " Mm "
    hashes = {
        result.accepted[0].canonical_business_hash for result in (absent, none, blank, spaces)
    }
    assert len(hashes) == 1


def test_unit_absent_and_null_are_business_duplicates():
    first = ingest(tool_result(raw=b"unit-business-absent"))
    headers = (*HEADERS, "unit")
    second = ingest(
        tool_result(
            headers=headers,
            rows=(row_for(headers, unit=None),),
            raw=b"unit-business-null",
        ),
        existing=first.accepted,
    )
    assert second.status is BatchStatus.DUPLICATE
    assert second.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE


def test_verification_and_record_evidence_fields_are_not_generated():
    record = ingest().accepted[0].validated_record
    assert record["verification_status"] == "UNVERIFIED"
    for field in ("verified_at", "valid_from", "valid_to", "source_uri", "source_checksum"):
        assert field not in record


def test_source_and_row_data_as_of_come_from_approved_boundaries():
    metadata_time = NOW - timedelta(days=10)
    result = ingest(
        tool_result(
            source="internal_fact_source",
            metadata_data_as_of=metadata_time,
            fetched_at=NOW - timedelta(days=1),
        )
    )
    record = result.accepted[0]
    assert record.validated_record["source"] == "internal_fact_source"
    assert record.validated_record["data_as_of"] == VALUES["data_as_of"]
    assert record.provenance.data_as_of.isoformat() == "2026-09-30T08:00:00+09:00"
    assert record.provenance.fetched_at == NOW - timedelta(days=1)


def test_source_reference_and_raw_checksum_are_shared_provenance_only():
    raw = b"verified-fact-source"
    result = ingest(tool_result(raw=raw, source_uri="csv://safe/product-fact.csv"))
    record = result.accepted[0]
    assert record.provenance.source_reference == "csv://safe/product-fact.csv"
    assert record.provenance.source_checksum == raw_sha256(raw)
    assert "source_uri" not in record.validated_record
    assert "source_checksum" not in record.validated_record


def test_unsafe_reference_and_checksum_mismatch_fail_closed():
    unsafe = ingest(tool_result(source_uri="https://example.invalid/facts?token=secret"))
    mismatch_input = tool_result(raw=b"actual")
    assert mismatch_input.source_metadata is not None
    mismatch = ingest(
        replace(
            mismatch_input,
            source_metadata=replace(
                mismatch_input.source_metadata,
                checksum_sha256=raw_sha256(b"different"),
            ),
        )
    )
    assert unsafe.batch_reason is ReasonCode.UNSAFE_SOURCE_REFERENCE
    assert mismatch.batch_reason is ReasonCode.CHECKSUM_MISMATCH


def test_run_and_task_correlation_are_exact_and_task_is_not_generated():
    absent = ingest()
    present = ingest(tool_result(raw=b"task", task_id=TASK))
    assert absent.accepted[0].validated_record["run_id"] == RUN
    assert absent.accepted[0].provenance.run_id == RUN
    assert "task_id" not in absent.accepted[0].validated_record
    assert absent.accepted[0].provenance.task_id is None
    assert present.accepted[0].validated_record["task_id"] == TASK
    assert present.accepted[0].provenance.task_id == TASK


def test_invalid_run_task_and_tool_run_mismatch_fail_batch_closed():
    invalid_run = ingest(run_id="run_invalid")
    mismatch = ingest(tool_result(tool_run_id=OTHER_RUN))
    invalid_task = ingest(tool_result(task_id="task_invalid"))
    assert all(
        result.batch_reason is ReasonCode.INVALID_TOOL_RESULT
        for result in (invalid_run, mismatch, invalid_task)
    )
    assert all(result.accepted == () for result in (invalid_run, mismatch, invalid_task))


@pytest.mark.parametrize("clock", [lambda: "not-datetime", lambda: datetime(2026, 9, 30)])
def test_invalid_clock_values_fail_closed(clock):
    result = ingest(clock=clock)
    assert result.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert result.accepted == ()


def test_clock_exception_fails_closed_and_base_exception_propagates():
    def runtime_clock():
        raise RuntimeError("clock failed")

    def base_clock():
        raise BoundaryStop("stop")

    assert ingest(clock=runtime_clock).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    with pytest.raises(BoundaryStop):
        ingest(clock=base_clock)


def test_source_duplicate_returns_before_clock_and_fact_id(monkeypatch):
    first = ingest()
    calls = {"clock": 0, "fact": 0}

    def clock():
        calls["clock"] += 1
        return NOW

    def fact_id():
        calls["fact"] += 1
        return "fact_01J00000000000000000000000"

    monkeypatch.setattr(product_fact_module, "generate_fact_id", fact_id)
    duplicate = ingest(existing=first.accepted, clock=clock)
    assert duplicate.batch_reason is ReasonCode.SOURCE_DUPLICATE
    assert duplicate.publish_eligible is False
    assert duplicate.accepted == ()
    assert calls == {"clock": 0, "fact": 0}


def test_fact_id_exception_fails_entire_batch_and_base_exception_propagates(monkeypatch):
    rows = (
        row_for(),
        row_for(fact_type="dimensions", data_as_of="2026-09-30T08:01:00+09:00"),
    )
    calls = 0

    def fail_second():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("ID failure")
        return "fact_01J00000000000000000000000"

    monkeypatch.setattr(product_fact_module, "generate_fact_id", fail_second)
    result = ingest(tool_result(rows=rows, raw=b"id-failure"))
    assert result.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert result.accepted == ()

    def stop():
        raise BoundaryStop("stop")

    monkeypatch.setattr(product_fact_module, "generate_fact_id", stop)
    with pytest.raises(BoundaryStop):
        ingest(tool_result(raw=b"id-base"))


def test_fact_id_failure_does_not_mutate_publisher(monkeypatch):
    publisher = InMemoryReferencePublisher()
    first = ingest(tool_result(raw=b"published"))
    assert publisher.publish(first)
    before = publisher.current
    last_identity = publisher.last_ingestion_identity

    def fail():
        raise RuntimeError("ID failure")

    monkeypatch.setattr(product_fact_module, "generate_fact_id", fail)
    failed = ingest(tool_result(raw=b"failed-id"))
    assert publisher.publish(failed) is False
    assert publisher.current == before
    assert publisher.last_ingestion_identity == last_identity


def test_natural_key_and_business_hash_are_exact():
    record = ingest().accepted[0]
    assert record.natural_key == (SKU, "material", "tabular_file", VALUES["data_as_of"])
    assert record.canonical_business_hash == payload_sha256(
        {
            "sku": SKU,
            "fact_type": "material",
            "fact_value": {"value": "STS304", "details": {"grade": "food"}},
            "unit": None,
            "verification_status": "UNVERIFIED",
        }
    )


def test_ingestion_identity_contains_exact_approved_inputs():
    result = ingest()
    record = result.accepted[0]
    expected_fingerprint = payload_sha256(
        {
            "strategy": "direct_internal_sku",
            "schema_version": PRODUCT_FACT_SCHEMA,
            "known_skus": [SKU],
        }
    )
    expected_identity = payload_sha256(
        {
            "target_contract": "PRODUCT_FACT",
            "schema_version": PRODUCT_FACT_SCHEMA,
            "source_checksum": record.provenance.source_checksum,
            "mapping_fingerprint": expected_fingerprint,
        }
    )
    assert record.provenance.mapping_fingerprint == expected_fingerprint
    assert result.ingestion_identity == expected_identity


def test_same_key_same_business_is_duplicate_and_changed_value_conflicts():
    first = ingest(tool_result(raw=b"first-state"))
    duplicate = ingest(tool_result(raw=b"same-state"), existing=first.accepted)
    conflict = ingest(
        tool_result(
            rows=(row_for(fact_value='{"value":"STS316"}'),),
            raw=b"changed-state",
        ),
        existing=first.accepted,
    )
    assert duplicate.status is BatchStatus.DUPLICATE
    assert duplicate.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE
    assert conflict.status is BatchStatus.CONFLICT
    assert conflict.conflicts[0].conflict_reason is ReasonCode.NATURAL_KEY_CONFLICT


def test_provenance_and_random_fact_id_differences_remain_business_duplicate(monkeypatch):
    ids = iter(
        [
            "fact_01J00000000000000000000000",
            "fact_01J00000000000000000000001",
        ]
    )
    monkeypatch.setattr(product_fact_module, "generate_fact_id", lambda: next(ids))
    first = ingest(tool_result(raw=b"provenance-one", task_id=TASK))
    second = ingest(
        tool_result(
            raw=b"provenance-two",
            tool_run_id=OTHER_RUN,
            task_id=OTHER_TASK,
            fetched_at=NOW + timedelta(hours=1),
        ),
        run_id=OTHER_RUN,
        clock=lambda: NOW + timedelta(days=1),
        existing=first.accepted,
    )
    assert second.batch_reason is None
    assert second.status is BatchStatus.DUPLICATE
    assert second.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE
    assert (
        second.duplicates[0].provenance.canonical_business_hash
        == first.accepted[0].canonical_business_hash
    )


def test_existing_runtime_error_fails_closed_and_base_exception_propagates():
    assert ingest(existing=IterableRuntimeError()).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    with pytest.raises(BoundaryStop):
        ingest(existing=IterableBaseException())


def test_malformed_other_contract_existing_record_fails_before_filtering():
    first = ingest()
    malformed = replace(
        first.accepted[0],
        contract_name="PRODUCT_MASTER",
        provenance=replace(first.accepted[0].provenance, target_contract="AD_DAILY"),
    )
    result = ingest(tool_result(raw=b"malformed-existing"), existing=(malformed,))
    assert result.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert result.accepted == ()


def _other_contract_tool_result(headers, row, raw):
    return replace(
        tool_result(raw=raw),
        parsed_result=TabularData(headers, (row,), None),
    )


def _real_product_master(raw: bytes = b"product-master"):
    headers = ("sku", "product_name", "category", "stage", "status", "currency", "data_as_of")
    row = (SKU, "Synthetic Product", "Kitchen", "TEST", "ACTIVE", "KRW", VALUES["data_as_of"])
    return ingest_product_master(
        _other_contract_tool_result(headers, row, raw), run_id=RUN, clock=lambda: NOW
    )


def test_valid_other_contract_existing_record_is_ignored_after_coherence_check():
    product = _real_product_master()
    result = ingest(tool_result(raw=b"fact-with-product"), existing=product.accepted)
    assert product.status is BatchStatus.READY
    assert result.status is BatchStatus.READY
    assert result.duplicates == ()
    assert result.conflicts == ()


def test_partial_conflict_rejected_and_duplicate_results_preserve_publisher_state():
    product = _real_product_master(b"publisher-product")
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(product)
    before = publisher.current
    last_identity = publisher.last_ingestion_identity

    partial_rows = (row_for(), row_for(sku=OTHER_SKU, fact_type="other"))
    partial = ingest(tool_result(rows=partial_rows, raw=b"partial"))
    rejected = ingest(with_values(sku=OTHER_SKU))
    first_fact = ingest(tool_result(raw=b"conflict-base"))
    conflict = ingest(
        tool_result(
            rows=(row_for(fact_value='{"value":"changed"}'),),
            raw=b"conflict",
        ),
        existing=first_fact.accepted,
    )
    source_duplicate = ingest(existing=first_fact.accepted)
    for result in (partial, rejected, conflict, source_duplicate):
        assert result.publish_eligible is False
        assert publisher.publish(result) is False
        assert publisher.current == before
        assert publisher.last_ingestion_identity == last_identity

    ready = ingest(tool_result(raw=b"ready-fact"))
    assert publisher.publish(ready)
    assert {record.contract_name for record in publisher.current or ()} == {
        "PRODUCT_MASTER",
        "PRODUCT_FACT",
    }


def test_five_real_contract_ingestion_boundaries_coexist_in_publisher():
    product = _real_product_master(b"product-five")
    fact = ingest(tool_result(raw=b"fact-five"), existing=product.accepted)
    mapping = {("tabular_file", "external_product_id", "ext-001"): SKU}

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
        "2026-09-29",
        "ext-001",
        "campaign-1",
        "1000",
        "10",
        "20.00",
        "2",
        "100.00",
        VALUES["data_as_of"],
    )
    prior = (*product.accepted, *fact.accepted)
    ad = ingest_ad_daily(
        _other_contract_tool_result(ad_headers, ad_row, b"ad-five"),
        run_id=RUN,
        known_skus=KNOWN_SKUS,
        sku_mapping=mapping,
        clock=lambda: NOW,
        existing=prior,
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
        "2026-09-29",
        "ext-001",
        "100.00",
        "2",
        "2",
        "0",
        "0",
        VALUES["data_as_of"],
    )
    prior = (*prior, *ad.accepted)
    channel = ingest_channel_daily(
        _other_contract_tool_result(channel_headers, channel_row, b"channel-five"),
        run_id=RUN,
        known_skus=KNOWN_SKUS,
        sku_mapping=mapping,
        clock=lambda: NOW,
        existing=prior,
    )

    inventory_headers = (
        "snapshot_at",
        "external_product_id",
        "location",
        "on_hand_qty",
        "available_qty",
        "reserved_qty",
        "inbound_qty",
        "data_as_of",
    )
    inventory_row = (
        VALUES["data_as_of"],
        "ext-001",
        "synthetic_fulfillment",
        "100",
        "90",
        "10",
        "20",
        VALUES["data_as_of"],
    )
    prior = (*prior, *channel.accepted)
    inventory = ingest_inventory(
        _other_contract_tool_result(inventory_headers, inventory_row, b"inventory-five"),
        run_id=RUN,
        known_skus=KNOWN_SKUS,
        sku_mapping=mapping,
        clock=lambda: NOW,
        existing=prior,
    )

    results = (product, fact, ad, channel, inventory)
    assert all(result.status is BatchStatus.READY for result in results)
    assert all(result.publish_eligible is True for result in results)
    publisher = InMemoryReferencePublisher()
    assert all(publisher.publish(result) for result in results)
    assert {record.contract_name for record in publisher.current or ()} == {
        "PRODUCT_MASTER",
        "PRODUCT_FACT",
        "AD_DAILY",
        "CHANNEL_DAILY",
        "INVENTORY",
    }
    assert len(publisher.current or ()) == 5


def test_ingestion_does_not_mutate_publisher_without_explicit_publish():
    publisher = InMemoryReferencePublisher()
    result = ingest()
    assert result.status is BatchStatus.READY
    assert publisher.current is None
    assert publisher.last_ingestion_identity is None


def test_no_phase5_or_content_fields_are_generated():
    record = ingest().accepted[0].validated_record
    assert set(record) == {
        "fact_id",
        "sku",
        "fact_type",
        "fact_value",
        "verification_status",
        "source",
        "run_id",
        "data_as_of",
        "created_at",
    }
