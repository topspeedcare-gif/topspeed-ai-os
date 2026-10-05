from __future__ import annotations

import inspect
import re
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

import topspeed_ai_os.data_hub.content_asset as content_asset_module
from topspeed_ai_os.contracts import ContractValidationError, validate_contract
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.data_hub import (
    AcceptedRecord,
    BatchStatus,
    InMemoryReferencePublisher,
    Provenance,
    ReasonCode,
    ingest_ad_daily,
    ingest_channel_daily,
    ingest_content_asset,
    ingest_inventory,
    ingest_product_fact,
    ingest_product_master,
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

NOW = datetime(2026, 10, 5, 13, 0, tzinfo=timezone(timedelta(hours=9)))
RUN = "run_01J00000000000000000000000"
OTHER_RUN = "run_01J00000000000000000000001"
TASK = "task_01J00000000000000000000000"
OTHER_TASK = "task_01J00000000000000000000001"
SKU = "TS-SYNTH-001"
OTHER_SKU = "TS-SYNTH-002"
FACT = "fact_01J00000000000000000000000"
OTHER_FACT = "fact_01J00000000000000000000001"
ASSET = "asset_01J00000000000000000000000"
OTHER_ASSET = "asset_01J00000000000000000000001"
HEADERS = (
    "sku",
    "asset_type",
    "title",
    "mime_type",
    "storage_uri",
    "checksum_sha256",
    "version",
    "generated_by",
    "claim_fact_ids",
    "data_as_of",
)
VALUES: dict[str, object] = {
    "sku": SKU,
    "asset_type": "DETAIL_PAGE",
    "title": "Synthetic detail page",
    "mime_type": "text/markdown",
    "storage_uri": "drive://file/content-asset-001",
    "checksum_sha256": "sha256:" + ("a" * 64),
    "version": 1,
    "generated_by": "content_skill",
    "claim_fact_ids": "[]",
    "data_as_of": "2026-10-05T08:00:00+09:00",
}


def row_for(headers: tuple[object, ...] = HEADERS, **changes: object) -> tuple[object, ...]:
    values = {**VALUES, **changes}
    return tuple(values[str(header)] for header in headers)


def tool_result(
    *,
    headers: tuple[object, ...] = HEADERS,
    rows: tuple[tuple[object, ...], ...] | None = None,
    raw: bytes = b"content-asset-synthetic",
    parsed: object | None = None,
    status: ToolStatus = ToolStatus.SUCCESS,
    source: str = "tabular_file",
    source_uri: str = "csv://synthetic/content-asset.csv",
    fetched_at: datetime = NOW,
    tool_run_id: str | None = RUN,
    task_id: str | None = TASK,
) -> ToolResult:
    if rows is None:
        rows = (row_for(headers),)
    if parsed is None:
        parsed = TabularData(headers, rows, None)
    error = (
        ToolError(ErrorCategory.UNKNOWN, "synthetic failure", False)
        if status is ToolStatus.FAILED
        else None
    )
    return ToolResult(
        tool_name="tabular_read",
        operation="tabular.read_csv",
        request_id="req_" + ("9" * 32),
        status=status,
        execution_mode=ExecutionMode.MOCK,
        task_id=task_id,
        run_id=tool_run_id,
        source_metadata=(
            None
            if status is ToolStatus.FAILED
            else SourceMetadata(
                source=source,
                source_uri=source_uri,
                fetched_at=fetched_at,
                data_as_of=None,
                checksum_sha256=raw_sha256(raw),
            )
        ),
        raw_result=None if status is ToolStatus.FAILED else SensitiveBytes(raw),
        parsed_result=None if status is ToolStatus.FAILED else parsed,
        error=error,
    )


def malformed_tool(base: ToolResult, **changes: object) -> ToolResult:
    result = object.__new__(ToolResult)
    for field in fields(ToolResult):
        object.__setattr__(result, field.name, changes.get(field.name, getattr(base, field.name)))
    return result


def ingest(result: object | None = None, **kwargs: object):
    return ingest_content_asset(
        tool_result() if result is None else result,
        run_id=kwargs.pop("run_id", RUN),
        known_skus=kwargs.pop("known_skus", {SKU}),
        clock=kwargs.pop("clock", lambda: NOW),
        **kwargs,
    )


def with_values(**changes: object) -> ToolResult:
    raw = repr(sorted(changes.items())).encode()
    return tool_result(rows=(row_for(**changes),), raw=raw)


def fact_record(
    *,
    fact_id: str = FACT,
    sku: str = SKU,
    status: str = "VERIFIED",
    fact_type: str = "material",
    fact_value: object = None,
    unit: object = "grade",
    include_unit: bool = True,
) -> AcceptedRecord:
    if fact_value is None:
        fact_value = {"value": "STS304"}
    record: dict[str, Any] = {
        "fact_id": fact_id,
        "sku": sku,
        "fact_type": fact_type,
        "fact_value": fact_value,
        "verification_status": status,
        "source": "verified_fixture",
        "run_id": RUN,
        "task_id": TASK,
        "data_as_of": "2026-10-04T08:00:00+09:00",
        "created_at": NOW.isoformat(),
    }
    if include_unit:
        record["unit"] = unit
    validate_contract("PRODUCT_FACT", record, known_skus={sku})
    key = (sku, fact_type, "verified_fixture", record["data_as_of"])
    business_hash = payload_sha256(
        {
            "sku": sku,
            "fact_type": fact_type,
            "fact_value": fact_value,
            "unit": record.get("unit"),
            "verification_status": status,
        }
    )
    provenance = Provenance(
        source="verified_fixture",
        source_reference="memory://product-fact",
        source_checksum="sha256:" + ("b" * 64),
        fetched_at=NOW,
        data_as_of=datetime.fromisoformat(record["data_as_of"]),
        data_as_of_origin="source_row:data_as_of",
        task_id=TASK,
        run_id=RUN,
        source_row_reference="fixture:1",
        schema_version="topspeed.product_fact.synthetic.v1",
        mapping_fingerprint="sha256:" + ("c" * 64),
        ingestion_identity="sha256:" + ("d" * 64),
        normalization_rules_applied=(),
        target_contract="PRODUCT_FACT",
        natural_key=key,
        canonical_business_hash=business_hash,
    )
    return AcceptedRecord("PRODUCT_FACT", record, key, business_hash, provenance)


class IterableRuntimeError:
    def __iter__(self):
        raise RuntimeError("iteration failed")


class BoundaryStop(BaseException):
    pass


class IterableBaseException:
    def __iter__(self):
        raise BoundaryStop("stop")


def test_valid_content_asset_builds_exact_draft_record_and_provenance(monkeypatch):
    monkeypatch.setattr(content_asset_module, "generate_asset_id", lambda: ASSET)
    result = ingest()
    assert result.status is BatchStatus.READY
    assert result.publish_eligible is True
    assert result.target_contract == "CONTENT_ASSET"
    accepted = result.accepted[0]
    assert accepted.validated_record == {
        "asset_id": ASSET,
        "sku": SKU,
        "asset_type": "DETAIL_PAGE",
        "title": "Synthetic detail page",
        "mime_type": "text/markdown",
        "storage_uri": "drive://file/content-asset-001",
        "checksum_sha256": "sha256:" + ("a" * 64),
        "version": 1,
        "generated_by": "content_skill",
        "claim_fact_ids": [],
        "status": "DRAFT",
        "approved_by": None,
        "source": "tabular_file",
        "run_id": RUN,
        "task_id": TASK,
        "data_as_of": VALUES["data_as_of"],
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    validate_contract("CONTENT_ASSET", accepted.validated_record, known_skus={SKU})
    assert accepted.natural_key == (SKU, "DETAIL_PAGE", VALUES["storage_uri"], 1)
    assert accepted.canonical_business_hash == payload_sha256(
        {
            "sku": SKU,
            "asset_type": "DETAIL_PAGE",
            "title": VALUES["title"],
            "mime_type": VALUES["mime_type"],
            "storage_uri": VALUES["storage_uri"],
            "checksum_sha256": VALUES["checksum_sha256"],
            "version": 1,
            "generated_by": VALUES["generated_by"],
            "claim_fact_ids": [],
            "status": "DRAFT",
        }
    )
    assert accepted.provenance.source == "tabular_file"
    assert accepted.provenance.source_reference == "csv://synthetic/content-asset.csv"
    assert accepted.provenance.data_as_of == datetime.fromisoformat(VALUES["data_as_of"])
    assert accepted.provenance.data_as_of_origin == "source_row:data_as_of"
    assert accepted.provenance.task_id == TASK
    assert accepted.provenance.run_id == RUN
    assert accepted.provenance.normalization_rules_applied == ()


def test_multirow_batch_calls_clock_once_and_uses_one_timestamp(monkeypatch):
    ids = iter((ASSET, OTHER_ASSET))
    monkeypatch.setattr(content_asset_module, "generate_asset_id", lambda: next(ids))
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        return NOW

    rows = (row_for(), row_for(storage_uri="drive://file/content-asset-002", version=2))
    result = ingest(tool_result(rows=rows, raw=b"two-assets"), clock=clock)
    assert result.status is BatchStatus.READY
    assert len(result.accepted) == 2
    assert calls == 1
    assert {item.validated_record["created_at"] for item in result.accepted} == {NOW.isoformat()}


@pytest.mark.parametrize("missing", HEADERS)
def test_every_missing_required_header_fails_batch_closed(missing):
    headers = tuple(field for field in HEADERS if field != missing)
    result = ingest(tool_result(headers=headers, rows=(row_for(headers),)))
    assert result.batch_reason is ReasonCode.INVALID_ROW_SHAPE
    assert result.accepted == ()


@pytest.mark.parametrize(
    "headers,rows",
    [
        ((*HEADERS, "unknown"), ((*row_for(), "x"),)),
        ((*HEADERS, "asset_id"), ((*row_for(), ASSET),)),
        ((*HEADERS[:-1], "sku"), ((*row_for(HEADERS[:-1]), SKU),)),
        (HEADERS, ()),
        (HEADERS, (row_for()[:-1],)),
    ],
)
def test_unknown_forbidden_duplicate_empty_and_wrong_width_sources_fail_closed(headers, rows):
    result = ingest(tool_result(headers=headers, rows=rows, raw=repr(headers).encode()))
    assert result.batch_reason is ReasonCode.INVALID_ROW_SHAPE
    assert result.accepted == ()


def test_tool_result_source_raw_parsed_checksum_and_schema_boundaries_fail_closed():
    base = tool_result()
    assert ingest(object()).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert (
        ingest(tool_result(status=ToolStatus.FAILED)).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    )
    assert (
        ingest(malformed_tool(base, source_metadata=None)).batch_reason
        is ReasonCode.INVALID_TOOL_RESULT
    )
    assert (
        ingest(malformed_tool(base, raw_result=None)).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    )
    assert (
        ingest(malformed_tool(base, parsed_result=None)).batch_reason
        is ReasonCode.INVALID_TOOL_RESULT
    )
    mismatch_metadata = replace(base.source_metadata, checksum_sha256="sha256:" + ("f" * 64))
    assert (
        ingest(malformed_tool(base, source_metadata=mismatch_metadata)).batch_reason
        is ReasonCode.CHECKSUM_MISMATCH
    )
    assert ingest(schema_version="unsupported").batch_reason is ReasonCode.UNSUPPORTED_SCHEMA


@pytest.mark.parametrize("known_skus", [SKU, b"sku", {"sku": SKU}, [SKU, 1], ["bad-sku"]])
def test_invalid_known_skus_containers_and_members_fail_closed(known_skus):
    result = ingest(known_skus=known_skus)
    assert result.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert result.accepted == ()


def test_known_skus_materialization_runtime_error_fails_closed_and_base_exception_propagates():
    assert ingest(known_skus=IterableRuntimeError()).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    with pytest.raises(BoundaryStop):
        ingest(known_skus=IterableBaseException())


@pytest.mark.parametrize("sku", ["ts-synth-001", "TS", " TS-SYNTH-001", 1])
def test_source_sku_uses_exact_core_boundary_without_normalization(sku):
    result = ingest(with_values(sku=sku))
    assert result.status is BatchStatus.REJECTED
    assert result.accepted == ()


def test_unknown_well_formed_source_sku_is_unregistered():
    result = ingest(with_values(sku=OTHER_SKU))
    assert result.rejected[0].reason_code is ReasonCode.UNREGISTERED_SKU


@pytest.mark.parametrize("field", HEADERS)
@pytest.mark.parametrize("blank", [None, ""])
def test_each_missing_or_blank_required_source_value_is_rejected(field, blank):
    result = ingest(with_values(**{field: blank}))
    assert result.status is BatchStatus.REJECTED
    assert result.accepted == ()


@pytest.mark.parametrize(
    "field,value",
    [
        ("asset_type", "VIDEO"),
        ("title", 1),
        ("mime_type", []),
        ("generated_by", True),
        ("checksum_sha256", "a" * 64),
        ("checksum_sha256", "sha256:" + ("A" * 64)),
        ("version", 0),
        ("version", -1),
        ("version", True),
        ("version", "1"),
        ("version", 1.0),
        ("data_as_of", "2026-10-05T08:00:00"),
        ("data_as_of", "not-a-datetime"),
    ],
)
def test_invalid_field_values_are_rejected_without_coercion(field, value):
    result = ingest(with_values(**{field: value}))
    assert result.status is BatchStatus.REJECTED
    assert result.accepted == ()


def test_accepted_text_and_data_as_of_values_are_preserved_exactly(monkeypatch):
    monkeypatch.setattr(content_asset_module, "generate_asset_id", lambda: ASSET)
    result = ingest(
        with_values(
            title="  Preserved title  ",
            mime_type=" text/custom ",
            generated_by=" Generator V1 ",
            data_as_of="2026-10-05T08:00:00Z",
        )
    )
    record = result.accepted[0].validated_record
    assert record["title"] == "  Preserved title  "
    assert record["mime_type"] == " text/custom "
    assert record["generated_by"] == " Generator V1 "
    assert record["data_as_of"] == "2026-10-05T08:00:00Z"


@pytest.mark.parametrize(
    "claim_text",
    [
        "{",
        '"scalar"',
        "1",
        "null",
        "[1]",
        '[""]',
        '["fact_bad"]',
        f'["{FACT}","{FACT}"]',
        "[NaN]",
    ],
)
def test_claim_fact_ids_requires_strict_unique_valid_json_array_text(claim_text):
    result = ingest(with_values(claim_fact_ids=claim_text))
    assert result.status is BatchStatus.REJECTED
    assert result.accepted == ()


@pytest.mark.parametrize(
    "storage_uri",
    [
        " https://example.invalid/asset",
        "https://user@example.invalid/asset",
        "https://:password@example.invalid/asset",
        "https://example.invalid/asset#fragment",
        "https://example.invalid/asset?token=value",
        "https://example.invalid/asset?ToKeN=value",
        "https://example.invalid/asset?%74oken=value",
        "https://example.invalid/asset?access_token=value",
        "https://example.invalid/asset?authorization=value",
        "https://example.invalid/asset?signature=value",
        "https://example.invalid/asset?secret=value",
        "https://example.invalid/asset?refresh_token=value",
    ],
)
def test_storage_uri_reuses_exact_safety_boundary_without_leaking_input(storage_uri):
    result = ingest(with_values(storage_uri=storage_uri))
    assert result.status is BatchStatus.REJECTED
    assert result.accepted == ()
    assert storage_uri not in result.rejected[0].sanitized_summary
    assert storage_uri not in result.rejected[0].source_reference


def test_contract_invalid_storage_uri_is_rejected_before_asset_id(monkeypatch):
    calls = 0

    def asset_id():
        nonlocal calls
        calls += 1
        return ASSET

    monkeypatch.setattr(content_asset_module, "generate_asset_id", asset_id)
    result = ingest(with_values(storage_uri="not a valid URI"))
    assert result.status is BatchStatus.REJECTED
    assert result.rejected[0].reason_code is ReasonCode.CONTRACT_VALIDATION_FAILED
    assert calls == 0


def test_safe_storage_uri_is_preserved_and_vendor_specific_guarantee_is_not_invented():
    uri = "https://example.invalid/asset?X-Amz-Signature=synthetic"
    result = ingest(with_values(storage_uri=uri))
    assert result.status is BatchStatus.READY
    assert result.accepted[0].validated_record["storage_uri"] == uri


def test_source_and_asset_checksums_remain_separate():
    raw = b"raw-tabular-source"
    asset_checksum = "sha256:" + ("1" * 64)
    result = ingest(tool_result(rows=(row_for(checksum_sha256=asset_checksum),), raw=raw))
    record = result.accepted[0]
    assert record.validated_record["checksum_sha256"] == asset_checksum
    assert record.provenance.source_checksum == raw_sha256(raw)
    assert record.validated_record["checksum_sha256"] != record.provenance.source_checksum


@pytest.mark.parametrize("task_id", [None, "", "task_bad"])
def test_task_id_is_required_and_must_be_valid(task_id):
    result = ingest(tool_result(task_id=task_id))
    assert result.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert result.accepted == ()


def test_run_and_task_authorities_are_exact_and_never_generated():
    valid = ingest()
    invalid_run = ingest(run_id="run_bad")
    mismatch = ingest(tool_result(tool_run_id=OTHER_RUN))
    assert valid.accepted[0].validated_record["task_id"] == TASK
    assert valid.accepted[0].validated_record["run_id"] == RUN
    assert invalid_run.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert mismatch.batch_reason is ReasonCode.INVALID_TOOL_RESULT


def test_empty_claims_and_valid_verified_same_sku_fact_are_accepted():
    empty = ingest()
    claimed = ingest(
        with_values(claim_fact_ids=f'["{FACT}"]'),
        existing=(fact_record(),),
    )
    assert empty.status is BatchStatus.READY
    assert claimed.status is BatchStatus.READY
    assert claimed.accepted[0].validated_record["claim_fact_ids"] == [FACT]


def test_repeated_valid_fact_across_rows_is_allowed(monkeypatch):
    monkeypatch.setattr(
        content_asset_module, "generate_asset_id", lambda: next(iter((ASSET, OTHER_ASSET)))
    )
    claims = f'["{FACT}"]'
    rows = (
        row_for(claim_fact_ids=claims),
        row_for(storage_uri="drive://file/content-asset-002", version=2, claim_fact_ids=claims),
    )
    ids = iter((ASSET, OTHER_ASSET))
    monkeypatch.setattr(content_asset_module, "generate_asset_id", lambda: next(ids))
    result = ingest(tool_result(rows=rows, raw=b"repeated-fact"), existing=(fact_record(),))
    assert result.status is BatchStatus.READY
    assert len(result.accepted) == 2


@pytest.mark.parametrize("case", ["unknown", "cross-sku", "unverified", "malformed", "duplicate"])
def test_invalid_product_fact_reference_context_fails_closed(case):
    claims = f'["{FACT}"]'
    existing: tuple[AcceptedRecord, ...]
    known_skus = {SKU}
    if case == "unknown":
        existing = ()
    elif case == "cross-sku":
        existing = (fact_record(sku=OTHER_SKU),)
        known_skus = {SKU, OTHER_SKU}
    elif case == "unverified":
        existing = (fact_record(status="UNVERIFIED"),)
    elif case == "malformed":
        valid = fact_record()
        existing = (
            replace(valid, validated_record={**valid.validated_record, "fact_value": "bad"}),
        )
    else:
        existing = (fact_record(), fact_record(fact_value={"value": "different"}))
    result = ingest(with_values(claim_fact_ids=claims), existing=existing, known_skus=known_skus)
    assert result.status is BatchStatus.REJECTED
    assert result.accepted == ()


def test_product_fact_context_has_exact_six_fields_sorted_and_excludes_provenance():
    facts = (
        fact_record(fact_id=OTHER_FACT, fact_type="dimensions", fact_value=[1, 2], unit=None),
        fact_record(),
    )
    requested = {OTHER_FACT: {SKU}, FACT: {SKU}}
    context, lookup = content_asset_module._product_fact_context(requested, facts, frozenset({SKU}))
    assert [item["fact_id"] for item in context] == [FACT, OTHER_FACT]
    assert all(set(item) == content_asset_module._FACT_CONTEXT_KEYS for item in context)
    assert context[0] == {
        "fact_id": FACT,
        "sku": SKU,
        "fact_type": "material",
        "fact_value": {"value": "STS304"},
        "unit": "grade",
        "verification_status": "VERIFIED",
    }
    assert lookup == {FACT: SKU, OTHER_FACT: SKU}


def test_fact_lookup_claim_order_and_absent_null_unit_are_mapping_equivalent():
    absent = fact_record(include_unit=False)
    explicit_null = fact_record(unit=None)
    absent_context, _ = content_asset_module._product_fact_context(
        {FACT: {SKU}}, (absent,), frozenset({SKU})
    )
    null_context, _ = content_asset_module._product_fact_context(
        {FACT: {SKU}}, (explicit_null,), frozenset({SKU})
    )
    absent_fp = content_asset_module._mapping_fingerprint(
        content_asset_module._mapping_payload([SKU], absent_context)
    )
    null_fp = content_asset_module._mapping_fingerprint(
        content_asset_module._mapping_payload([SKU], null_context)
    )
    assert absent_context == null_context
    assert absent_fp == null_fp


def test_mapping_payload_is_exact_and_rejects_renamed_or_additional_keys():
    payload = content_asset_module._mapping_payload([SKU], [])
    assert set(payload) == {
        "known_skus",
        "mapping_strategy_version",
        "product_fact_context",
        "sku_strategy",
    }
    for invalid in (
        {**payload, "extra": "x"},
        {"skus": payload["known_skus"], **{k: v for k, v in payload.items() if k != "known_skus"}},
    ):
        with pytest.raises(ValueError):
            content_asset_module._mapping_fingerprint(invalid)


def test_known_skus_mapping_fingerprint_is_order_independent_deduplicated_and_sensitive():
    first = ingest(known_skus=[OTHER_SKU, SKU, SKU])
    second = ingest(known_skus=[SKU, OTHER_SKU])
    changed = ingest(known_skus=[SKU])
    assert (
        first.accepted[0].provenance.mapping_fingerprint
        == second.accepted[0].provenance.mapping_fingerprint
    )
    assert (
        first.accepted[0].provenance.mapping_fingerprint
        != changed.accepted[0].provenance.mapping_fingerprint
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("fact_id", OTHER_FACT),
        ("sku", OTHER_SKU),
        ("fact_type", "dimensions"),
        ("fact_value", {"value": "STS316"}),
        ("unit", "mm"),
        ("verification_status", "UNVERIFIED"),
    ],
)
def test_each_fact_context_field_is_mapping_fingerprint_sensitive(field, value):
    baseline = {
        "fact_id": FACT,
        "sku": SKU,
        "fact_type": "material",
        "fact_value": {"value": "STS304"},
        "unit": "grade",
        "verification_status": "VERIFIED",
    }
    changed = {**baseline, field: value}
    baseline_fp = content_asset_module._mapping_fingerprint(
        content_asset_module._mapping_payload(sorted({SKU, OTHER_SKU}), [baseline])
    )
    changed_fp = content_asset_module._mapping_fingerprint(
        content_asset_module._mapping_payload(sorted({SKU, OTHER_SKU}), [changed])
    )
    assert changed_fp != baseline_fp


def test_mapping_strategy_fields_are_sensitive_deterministic_and_prefixed():
    baseline = content_asset_module._mapping_payload([SKU], [])
    fingerprint = content_asset_module._mapping_fingerprint(baseline)
    changed_version = content_asset_module._mapping_payload(
        [SKU], [], mapping_strategy_version="topspeed.content_asset.mapping.synthetic.v2"
    )
    changed_strategy = content_asset_module._mapping_payload(
        [SKU], [], sku_strategy="validated_direct_internal_sku"
    )
    assert content_asset_module._mapping_fingerprint(baseline) == fingerprint
    assert content_asset_module._mapping_fingerprint(changed_version) != fingerprint
    assert content_asset_module._mapping_fingerprint(changed_strategy) != fingerprint
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", fingerprint)
    with pytest.raises(ValueError):
        content_asset_module._mapping_fingerprint({**baseline, "known_skus": [SKU, SKU]})


def test_ingestion_identity_has_exact_four_fields_and_each_is_sensitive():
    baseline = content_asset_module._identity_payload(
        "sha256:" + ("1" * 64), "sha256:" + ("2" * 64)
    )
    baseline_identity = content_asset_module._ingestion_identity(baseline)
    assert set(baseline) == {
        "target_contract",
        "schema_version",
        "source_checksum",
        "mapping_fingerprint",
    }
    alternatives = {
        "target_contract": "PRODUCT_FACT",
        "schema_version": "topspeed.content_asset.synthetic.v2",
        "source_checksum": "sha256:" + ("3" * 64),
        "mapping_fingerprint": "sha256:" + ("4" * 64),
    }
    for field, value in alternatives.items():
        changed = {**baseline, field: value}
        assert sum(changed[key] != baseline[key] for key in baseline) == 1
        assert content_asset_module._ingestion_identity(changed) != baseline_identity
        for checksum_field in ("source_checksum", "mapping_fingerprint"):
            assert re.fullmatch(r"sha256:[0-9a-f]{64}", changed[checksum_field])


def test_ingestion_identity_rejects_fifth_key_and_malformed_hashes():
    payload = content_asset_module._identity_payload("sha256:" + ("1" * 64), "sha256:" + ("2" * 64))
    with pytest.raises(ValueError):
        content_asset_module._ingestion_identity({**payload, "run_id": RUN})
    for field in ("source_checksum", "mapping_fingerprint"):
        with pytest.raises(ValueError):
            content_asset_module._ingestion_identity({**payload, field: "1" * 64})


def test_run_task_clock_and_random_asset_id_do_not_change_ingestion_identity(monkeypatch):
    ids = iter((ASSET, OTHER_ASSET))
    monkeypatch.setattr(content_asset_module, "generate_asset_id", lambda: next(ids))
    first = ingest(tool_result(raw=b"stable-identity"))
    second = ingest(
        tool_result(raw=b"stable-identity", tool_run_id=OTHER_RUN, task_id=OTHER_TASK),
        run_id=OTHER_RUN,
        clock=lambda: NOW + timedelta(days=1),
    )
    assert first.ingestion_identity == second.ingestion_identity
    assert (
        first.accepted[0].validated_record["asset_id"]
        != second.accepted[0].validated_record["asset_id"]
    )
    assert "target_contract" not in inspect.signature(ingest_content_asset).parameters


def test_source_duplicate_returns_before_clock_id_and_publisher_mutation(monkeypatch):
    first = ingest()
    publisher = InMemoryReferencePublisher()
    assert publisher.publish(first)
    before = publisher.current
    last_identity = publisher.last_ingestion_identity
    calls = {"clock": 0, "asset": 0}

    def clock():
        calls["clock"] += 1
        return NOW

    def asset_id():
        calls["asset"] += 1
        return ASSET

    monkeypatch.setattr(content_asset_module, "generate_asset_id", asset_id)
    duplicate = ingest(existing=publisher.current or (), clock=clock)
    assert duplicate.status is BatchStatus.DUPLICATE
    assert duplicate.batch_reason is ReasonCode.SOURCE_DUPLICATE
    assert duplicate.accepted == ()
    assert duplicate.publish_eligible is False
    assert calls == {"clock": 0, "asset": 0}
    assert publisher.publish(duplicate) is False
    assert publisher.current == before
    assert publisher.last_ingestion_identity == last_identity


def test_within_batch_and_existing_business_duplicates_issue_no_extra_asset_id(monkeypatch):
    calls = 0

    def asset_id():
        nonlocal calls
        calls += 1
        return ASSET

    monkeypatch.setattr(content_asset_module, "generate_asset_id", asset_id)
    within = ingest(tool_result(rows=(row_for(), row_for()), raw=b"within-duplicate"))
    assert within.status is BatchStatus.READY
    assert len(within.accepted) == 1
    assert len(within.duplicates) == 1
    assert calls == 1
    calls = 0
    existing = ingest(tool_result(raw=b"first-existing"))
    calls = 0
    duplicate = ingest(tool_result(raw=b"different-source"), existing=existing.accepted)
    assert duplicate.status is BatchStatus.DUPLICATE
    assert duplicate.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE
    assert calls == 0


def test_generated_by_change_conflicts_and_random_id_cannot_bypass_duplicate(monkeypatch):
    ids = iter((ASSET, OTHER_ASSET))
    monkeypatch.setattr(content_asset_module, "generate_asset_id", lambda: next(ids))
    first = ingest(tool_result(raw=b"base-business"))
    duplicate = ingest(tool_result(raw=b"new-provenance"), existing=first.accepted)
    conflict = ingest(
        tool_result(rows=(row_for(generated_by="human"),), raw=b"changed-generator"),
        existing=first.accepted,
    )
    assert duplicate.status is BatchStatus.DUPLICATE
    assert conflict.status is BatchStatus.CONFLICT
    assert conflict.conflicts[0].conflict_reason is ReasonCode.NATURAL_KEY_CONFLICT


def test_claim_order_does_not_change_business_hash():
    facts = (fact_record(), fact_record(fact_id=OTHER_FACT, fact_type="dimensions"))
    first = ingest(with_values(claim_fact_ids=f'["{FACT}","{OTHER_FACT}"]'), existing=facts)
    second = ingest(
        tool_result(
            rows=(row_for(claim_fact_ids=f'["{OTHER_FACT}","{FACT}"]'),),
            raw=b"claim-order-two",
        ),
        existing=(*facts, *first.accepted),
    )
    assert second.status is BatchStatus.DUPLICATE
    assert second.duplicates[0].duplicate_reason is ReasonCode.BUSINESS_DUPLICATE


def test_asset_id_failure_is_atomic_after_an_earlier_candidate(monkeypatch):
    calls = 0

    def factory():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("asset ID failure")
        return ASSET

    monkeypatch.setattr(content_asset_module, "generate_asset_id", factory)
    rows = (row_for(), row_for(storage_uri="drive://file/content-asset-002", version=2))
    result = ingest(tool_result(rows=rows, raw=b"id-failure"))
    assert result.status is BatchStatus.REJECTED
    assert result.accepted == ()
    assert result.publish_eligible is False


def test_asset_id_ordinary_exception_fails_closed_and_base_exception_propagates(monkeypatch):
    def runtime_failure():
        raise RuntimeError("failure")

    monkeypatch.setattr(content_asset_module, "generate_asset_id", runtime_failure)
    assert ingest().batch_reason is ReasonCode.INVALID_TOOL_RESULT

    def stop():
        raise BoundaryStop("stop")

    monkeypatch.setattr(content_asset_module, "generate_asset_id", stop)
    with pytest.raises(BoundaryStop):
        ingest()


def test_malformed_asset_id_from_factory_fails_closed(monkeypatch):
    monkeypatch.setattr(content_asset_module, "generate_asset_id", lambda: "asset_bad")
    result = ingest()
    assert result.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert result.accepted == ()


@pytest.mark.parametrize("clock", [lambda: "not-datetime", lambda: datetime(2026, 10, 5)])
def test_invalid_clock_fails_closed(clock):
    assert ingest(clock=clock).batch_reason is ReasonCode.INVALID_TOOL_RESULT


def test_clock_ordinary_exception_fails_closed_and_base_exception_propagates():
    def runtime_clock():
        raise RuntimeError("clock failure")

    def stop_clock():
        raise BoundaryStop("stop")

    assert ingest(clock=runtime_clock).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    with pytest.raises(BoundaryStop):
        ingest(clock=stop_clock)


def test_final_contract_validation_call_uses_actual_fact_lookup(monkeypatch):
    calls: list[tuple[object, ...]] = []
    original = content_asset_module.validate_contract

    def spy(*args, **kwargs):
        calls.append((*args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(content_asset_module, "validate_contract", spy)
    result = ingest(with_values(claim_fact_ids=f'["{FACT}"]'), existing=(fact_record(),))
    assert result.status is BatchStatus.READY
    assert calls[-1] == (
        "CONTENT_ASSET",
        result.accepted[0].validated_record,
        {"known_skus": frozenset({SKU}), "fact_sku_by_id": {FACT: SKU}},
    )


def test_contract_validation_error_is_classified_but_unexpected_failures_propagate(monkeypatch):
    def contract_error(*args, **kwargs):
        del args, kwargs
        raise ContractValidationError("CONTENT_ASSET", ["synthetic"])

    monkeypatch.setattr(content_asset_module, "validate_contract", contract_error)
    rejected = ingest()
    assert rejected.rejected[0].reason_code is ReasonCode.CONTRACT_VALIDATION_FAILED

    def runtime_error(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("unexpected")

    monkeypatch.setattr(content_asset_module, "validate_contract", runtime_error)
    with pytest.raises(RuntimeError, match="unexpected"):
        ingest()

    def base_error(*args, **kwargs):
        del args, kwargs
        raise BoundaryStop("stop")

    monkeypatch.setattr(content_asset_module, "validate_contract", base_error)
    with pytest.raises(BoundaryStop):
        ingest()


def test_existing_materialization_and_cross_contract_coherence_fail_closed():
    assert ingest(existing=IterableRuntimeError()).batch_reason is ReasonCode.INVALID_TOOL_RESULT
    with pytest.raises(BoundaryStop):
        ingest(existing=IterableBaseException())
    valid = fact_record()
    malformed = replace(
        valid,
        contract_name="PRODUCT_MASTER",
        provenance=replace(valid.provenance, target_contract="AD_DAILY"),
    )
    result = ingest(existing=(malformed,))
    assert result.batch_reason is ReasonCode.INVALID_TOOL_RESULT
    assert result.accepted == ()


def test_valid_other_contract_is_ignored_for_asset_business_comparison():
    fact = fact_record()
    result = ingest(existing=(fact,))
    assert result.status is BatchStatus.READY
    assert result.duplicates == ()
    assert result.conflicts == ()


def test_ready_publishes_atomically_and_nonpublishable_statuses_preserve_state():
    publisher = InMemoryReferencePublisher()
    ready = ingest(tool_result(raw=b"publisher-ready"))
    assert publisher.publish(ready)
    before = publisher.current
    last_identity = publisher.last_ingestion_identity
    partial_rows = (row_for(), row_for(storage_uri="bad uri", version=2))
    partial = ingest(tool_result(rows=partial_rows, raw=b"partial"))
    conflict = ingest(
        tool_result(rows=(row_for(generated_by="human"),), raw=b"conflict"),
        existing=ready.accepted,
    )
    rejected = ingest(with_values(version=0))
    source_duplicate = ingest(existing=ready.accepted)
    target_mismatch = replace(ready, target_contract="PRODUCT_FACT")
    for result in (partial, conflict, rejected, source_duplicate, target_mismatch):
        assert publisher.publish(result) is False
        assert publisher.current == before
        assert publisher.last_ingestion_identity == last_identity


def _other_contract_tool_result(headers, row, raw):
    return replace(
        tool_result(raw=raw),
        parsed_result=TabularData(headers, (row,), None),
    )


def test_actual_six_contract_ingestion_boundaries_coexist_in_shared_publisher():
    product_headers = (
        "sku",
        "product_name",
        "category",
        "stage",
        "status",
        "currency",
        "data_as_of",
    )
    product_row = (SKU, "Synthetic", "Kitchen", "TEST", "ACTIVE", "KRW", VALUES["data_as_of"])
    product = ingest_product_master(
        _other_contract_tool_result(product_headers, product_row, b"six-product"),
        run_id=RUN,
        clock=lambda: NOW,
    )

    fact_headers = ("sku", "fact_type", "fact_value", "data_as_of")
    fact_row = (SKU, "material", '{"value":"synthetic"}', VALUES["data_as_of"])
    fact = ingest_product_fact(
        _other_contract_tool_result(fact_headers, fact_row, b"six-fact"),
        run_id=RUN,
        known_skus={SKU},
        clock=lambda: NOW,
        existing=product.accepted,
    )
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
        "synthetic",
        "2026-10-05",
        "ext-001",
        "campaign-1",
        "100",
        "10",
        "20.00",
        "2",
        "100.00",
        VALUES["data_as_of"],
    )
    prior = (*product.accepted, *fact.accepted)
    ad = ingest_ad_daily(
        _other_contract_tool_result(ad_headers, ad_row, b"six-ad"),
        run_id=RUN,
        known_skus={SKU},
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
        "synthetic",
        "2026-10-05",
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
        _other_contract_tool_result(channel_headers, channel_row, b"six-channel"),
        run_id=RUN,
        known_skus={SKU},
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
        _other_contract_tool_result(inventory_headers, inventory_row, b"six-inventory"),
        run_id=RUN,
        known_skus={SKU},
        sku_mapping=mapping,
        clock=lambda: NOW,
        existing=prior,
    )

    prior = (*prior, *inventory.accepted)
    asset = ingest(tool_result(raw=b"six-asset"), existing=prior)
    results = (product, fact, ad, channel, inventory, asset)
    assert all(result.status is BatchStatus.READY for result in results)
    publisher = InMemoryReferencePublisher()
    assert all(publisher.publish(result) for result in results)
    assert {record.contract_name for record in publisher.current or ()} == {
        "PRODUCT_MASTER",
        "PRODUCT_FACT",
        "AD_DAILY",
        "CHANNEL_DAILY",
        "INVENTORY",
        "CONTENT_ASSET",
    }
    assert len(publisher.current or ()) == 6


def test_explicit_exclusions_are_absent_from_record_and_ingestion_has_no_side_effects():
    publisher = InMemoryReferencePublisher()
    result = ingest()
    record = result.accepted[0].validated_record
    assert publisher.current is None
    assert publisher.last_ingestion_identity is None
    assert set(record).isdisjoint(
        {
            "approval_id",
            "audit_status",
            "idempotency_key",
            "human_edit_ratio",
            "contribution_margin",
            "ctr",
            "cvr",
            "roas",
            "source_uri",
            "source_checksum",
            "mapping_fingerprint",
            "ingestion_identity",
        }
    )
