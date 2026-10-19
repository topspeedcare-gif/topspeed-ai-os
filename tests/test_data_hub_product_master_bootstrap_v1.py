from __future__ import annotations

import ast
import inspect
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

import topspeed_ai_os.data_hub as data_hub
import topspeed_ai_os.data_hub.product_master_bootstrap_v1 as bootstrap
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.core.ids import InvalidIdentifierError
from topspeed_ai_os.data_hub.adapter import (
    AcceptedRecord,
    BatchResult,
    BatchStatus,
    ReasonCode,
)
from topspeed_ai_os.data_hub.product_master import PRODUCT_MASTER_SCHEMA
from topspeed_ai_os.tools.read.tabular import TabularData
from topspeed_ai_os.tools.result import (
    ExecutionMode,
    SensitiveBytes,
    SourceMetadata,
    ToolResult,
    ToolStatus,
)

REQUEST_ID = "req_" + "1" * 32
RUN_ID = "run_01J" + "0" * 23
FETCHED_AT = datetime(2026, 10, 19, 16, 20, tzinfo=timezone(timedelta(hours=9)))
CREATED_AT = datetime(2026, 10, 19, 16, 21, tzinfo=timezone(timedelta(hours=9)))
FIELDS = (
    "sku",
    "product_name",
    "category",
    "stage",
    "status",
    "currency",
    "data_as_of",
)
VALUES = {
    "sku": "TS-WAIST-BRACE-L",
    "product_name": "[5중지지] 탑스피드 허리보호대 L",
    "category": "건강관리용품",
    "stage": "CORE",
    "status": "ACTIVE",
    "currency": "KRW",
    "data_as_of": "2026-10-19T16:18:10+09:00",
}
CSV_BYTES = (
    "sku,product_name,category,stage,status,currency,data_as_of\n"
    "TS-WAIST-BRACE-L,[5중지지] 탑스피드 허리보호대 L,건강관리용품,CORE,ACTIVE,KRW,"
    "2026-10-19T16:18:10+09:00\n"
).encode()
CHECKSUM = "sha256:32cc3b490277426594ebf9b26c55ecc29e69f978c32974f88d86b9b3c367e5ae"
SOURCE_URI = "repo://topspeed-ai-os/product-master/bootstrap/TS-WAIST-BRACE-L/v1"


class StrChild(str):
    pass


class DateTimeChild(datetime):
    pass


def _record(**changes: object) -> bootstrap._ProductMasterBootstrapRecord:
    return bootstrap._ProductMasterBootstrapRecord(**{**VALUES, **changes})


def _produce(**changes: object) -> BatchResult:
    arguments = {
        "request_id": REQUEST_ID,
        "run_id": RUN_ID,
        "fetched_at": FETCHED_AT,
        "clock": lambda: CREATED_AT,
    }
    arguments.update(changes)
    return bootstrap._produce_product_master_bootstrap_batch(**arguments)


def _capture_boundary(monkeypatch, *, existing=()):
    captured = {}
    returned = BatchResult("batch:captured", BatchStatus.READY)

    def fake_ingest(tool_result, *, run_id, clock, schema_version, existing):
        captured.update(
            tool_result=tool_result,
            run_id=run_id,
            clock=clock,
            schema_version=schema_version,
            existing=existing,
        )
        return returned

    monkeypatch.setattr(bootstrap, "ingest_product_master", fake_ingest)

    def clock():
        return CREATED_AT

    actual = bootstrap._produce_product_master_bootstrap_batch(
        request_id=REQUEST_ID,
        run_id=RUN_ID,
        fetched_at=FETCHED_AT,
        clock=clock,
        existing=existing,
    )
    assert actual is returned
    return captured, clock


def test_private_record_identity_shape_frozen_slots_and_exact_values():
    record = bootstrap._BOOTSTRAP_RECORD
    assert type(record) is bootstrap._ProductMasterBootstrapRecord
    assert tuple(field.name for field in fields(type(record))) == FIELDS
    assert tuple(type(record).__slots__) == FIELDS
    assert not hasattr(record, "__dict__")
    assert {field: getattr(record, field) for field in FIELDS} == VALUES
    assert all(type(getattr(record, field)) is str for field in FIELDS)
    with pytest.raises(FrozenInstanceError):
        record.sku = "CHANGED"  # type: ignore[misc]


@pytest.mark.parametrize("field", FIELDS)
def test_private_record_rejects_str_subclasses(field):
    with pytest.raises(TypeError, match=field):
        _record(**{field: StrChild(VALUES[field])})


@pytest.mark.parametrize("field", FIELDS)
def test_private_record_rejects_wrong_approved_literals(field):
    with pytest.raises(ValueError, match=field):
        _record(**{field: "wrong"})


@pytest.mark.parametrize(
    "value",
    [
        "not-a-date",
        "2026-02-30T00:00:00+09:00",
        "2026-10-19T16:18:10",
        "2026-10-19T16:18:10.000000+09:00",
    ],
)
def test_data_as_of_real_aware_canonical_validation_after_literal(monkeypatch, value):
    record = _record()
    object.__setattr__(record, "data_as_of", value)
    monkeypatch.setattr(bootstrap, "_APPROVED_DATA_AS_OF", value)
    monkeypatch.setattr(bootstrap, "_BOOTSTRAP_RECORD", record)
    with pytest.raises(ValueError, match="data_as_of"):
        _produce()


def test_producer_signature_keyword_only_and_exact_default():
    signature = inspect.signature(bootstrap._produce_product_master_bootstrap_batch)
    assert tuple(signature.parameters) == (
        "request_id",
        "run_id",
        "fetched_at",
        "clock",
        "existing",
    )
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )
    assert signature.parameters["existing"].default == ()
    assert all(
        signature.parameters[name].default is inspect.Parameter.empty
        for name in ("request_id", "run_id", "fetched_at", "clock")
    )
    with pytest.raises(TypeError):
        bootstrap._produce_product_master_bootstrap_batch(  # type: ignore[misc]
            REQUEST_ID, RUN_ID, FETCHED_AT, lambda: CREATED_AT
        )


def test_record_identity_has_highest_combined_fault_precedence(monkeypatch):
    monkeypatch.setattr(bootstrap, "_BOOTSTRAP_RECORD", object())
    monkeypatch.setattr(
        bootstrap,
        "require_valid_run_id",
        lambda _value: pytest.fail("lower-precedence run validation executed"),
    )
    with pytest.raises(TypeError, match="record identity"):
        bootstrap._produce_product_master_bootstrap_batch(
            request_id=object(),  # type: ignore[arg-type]
            run_id=object(),  # type: ignore[arg-type]
            fetched_at=object(),  # type: ignore[arg-type]
            clock=object(),  # type: ignore[arg-type]
        )


def test_record_field_order_precedes_value_and_input_validation(monkeypatch):
    @dataclass(frozen=True, slots=True)
    class WrongOrder:
        product_name: str
        sku: str
        category: str
        stage: str
        status: str
        currency: str
        data_as_of: str

    wrong = WrongOrder(
        VALUES["product_name"],
        VALUES["sku"],
        VALUES["category"],
        VALUES["stage"],
        VALUES["status"],
        VALUES["currency"],
        VALUES["data_as_of"],
    )
    monkeypatch.setattr(bootstrap, "_ProductMasterBootstrapRecord", WrongOrder)
    monkeypatch.setattr(bootstrap, "_BOOTSTRAP_RECORD", wrong)
    with pytest.raises(TypeError, match="fields or field order"):
        _produce(request_id="bad", run_id="bad", fetched_at=object(), clock=object())


@pytest.mark.parametrize("field", FIELDS)
def test_record_field_validation_precedes_request_validation(monkeypatch, field):
    record = _record()
    object.__setattr__(record, field, StrChild(VALUES[field]))
    monkeypatch.setattr(bootstrap, "_BOOTSTRAP_RECORD", record)
    with pytest.raises(TypeError, match=field):
        _produce(request_id="bad")


@pytest.mark.parametrize("value", [None, "req_" + "A" * 32, "req_" + "0" * 31, "bad"])
def test_request_id_exact_syntax_and_lower_precedence_short_circuit(monkeypatch, value):
    monkeypatch.setattr(
        bootstrap,
        "require_valid_run_id",
        lambda _value: pytest.fail("run validation executed"),
    )
    expected = TypeError if value is None else ValueError
    with pytest.raises(expected):
        _produce(request_id=value, run_id="bad", fetched_at=object(), clock=object())


def test_request_and_run_str_subclasses_are_rejected():
    with pytest.raises(TypeError, match="request_id"):
        _produce(request_id=StrChild(REQUEST_ID))
    with pytest.raises(TypeError, match="run_id"):
        _produce(run_id=StrChild(RUN_ID))


def test_existing_run_id_authority_and_exception_identity(monkeypatch):
    with pytest.raises(InvalidIdentifierError):
        _produce(run_id="invalid")
    sentinel = RuntimeError("run authority sentinel")

    def fail(_value):
        raise sentinel

    monkeypatch.setattr(bootstrap, "require_valid_run_id", fail)
    with pytest.raises(RuntimeError) as raised:
        _produce()
    assert raised.value is sentinel


def test_fetched_at_exact_datetime_and_timezone_precede_clock():
    child = DateTimeChild(2026, 10, 19, 16, 20, tzinfo=UTC)
    with pytest.raises(TypeError, match="fetched_at"):
        _produce(fetched_at=child, clock=object())
    with pytest.raises(ValueError, match="timezone-aware"):
        _produce(fetched_at=datetime(2026, 10, 19, 16, 20), clock=object())
    with pytest.raises(TypeError, match="clock"):
        _produce(clock=object())


def test_canonical_artifact_metadata_and_tool_result_are_exact(monkeypatch):
    captured, _clock = _capture_boundary(monkeypatch)
    tool_result = captured["tool_result"]
    assert type(tool_result) is ToolResult
    assert tool_result.tool_name == "product_master_bootstrap"
    assert tool_result.operation == "product_master.bootstrap_v1"
    assert tool_result.request_id == REQUEST_ID
    assert tool_result.status is ToolStatus.SUCCESS
    assert tool_result.execution_mode is ExecutionMode.MOCK
    assert tool_result.task_id is None
    assert tool_result.run_id == RUN_ID
    assert type(tool_result.raw_result) is SensitiveBytes
    raw = tool_result.raw_result.reveal()
    assert raw == CSV_BYTES
    assert raw[:3] != b"\xef\xbb\xbf"
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    assert bootstrap.raw_sha256(raw) == CHECKSUM

    metadata = tool_result.source_metadata
    assert type(metadata) is SourceMetadata
    assert metadata.source == "manual_verified"
    assert metadata.source_uri == SOURCE_URI
    assert metadata.fetched_at is FETCHED_AT
    assert metadata.data_as_of is None
    assert metadata.checksum_sha256 == CHECKSUM

    parsed = tool_result.parsed_result
    assert type(parsed) is TabularData
    assert parsed.headers == FIELDS
    assert parsed.rows == (tuple(VALUES[field] for field in FIELDS),)
    assert parsed.sheet_name is None
    assert set(parsed.headers) == set(FIELDS)
    assert not {
        "channel_ids",
        "grade",
        "supplier",
        "purchase_cost",
        "sale_price",
        "fee_rate",
        "fulfillment_cost",
        "expected_return_cost",
        "other_variable_cost",
    } & set(parsed.headers)


def test_clock_and_existing_are_forwarded_by_identity_without_preconsumption(monkeypatch):
    class UnconsumableExisting:
        def __iter__(self):
            raise AssertionError("producer consumed existing")

    existing = UnconsumableExisting()
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        return CREATED_AT

    captured = {}
    returned = BatchResult("batch:captured", BatchStatus.READY)

    def fake_ingest(tool_result, *, run_id, clock: object, schema_version, existing: object):
        captured.update(
            tool_result=tool_result,
            run_id=run_id,
            clock=clock,
            schema_version=schema_version,
            existing=existing,
        )
        assert calls == 0
        return returned

    monkeypatch.setattr(bootstrap, "ingest_product_master", fake_ingest)
    actual = _produce(clock=clock, existing=existing)
    assert actual is returned
    assert captured["clock"] is clock
    assert captured["existing"] is existing
    assert captured["schema_version"] == PRODUCT_MASTER_SCHEMA
    assert captured["run_id"] == RUN_ID
    assert calls == 0


def test_real_adapter_ready_record_provenance_and_hash_continuity():
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        return CREATED_AT

    result = _produce(clock=clock)
    assert type(result) is BatchResult
    assert result.status is BatchStatus.READY
    assert result.publish_eligible is True
    assert len(result.accepted) == 1
    assert calls == 1
    accepted = result.accepted[0]
    assert type(accepted) is AcceptedRecord
    assert accepted.natural_key == (VALUES["sku"],)
    expected_record = {
        **VALUES,
        "source": "manual_verified",
        "created_at": CREATED_AT.isoformat(),
        "updated_at": CREATED_AT.isoformat(),
    }
    assert dict(accepted.validated_record) == expected_record
    assert "channel_ids" not in accepted.validated_record
    assert accepted.provenance.source == "manual_verified"
    assert accepted.provenance.source_reference == SOURCE_URI
    assert accepted.provenance.source_checksum == CHECKSUM
    assert accepted.provenance.fetched_at is FETCHED_AT
    assert accepted.provenance.data_as_of.isoformat() == VALUES["data_as_of"]
    assert accepted.provenance.data_as_of_origin == "source_row:data_as_of"
    assert accepted.provenance.schema_version == PRODUCT_MASTER_SCHEMA
    expected_mapping = payload_sha256(
        {"strategy": "direct_internal_sku", "schema_version": PRODUCT_MASTER_SCHEMA}
    )
    assert accepted.provenance.mapping_fingerprint == expected_mapping
    business_fields = (
        "sku",
        "product_name",
        "category",
        "channel_ids",
        "stage",
        "grade",
        "status",
        "supplier",
        "currency",
        "purchase_cost",
        "sale_price",
        "fee_rate",
        "fulfillment_cost",
        "expected_return_cost",
        "other_variable_cost",
    )
    expected_business_hash = payload_sha256(
        {field: accepted.validated_record.get(field) for field in business_fields}
    )
    assert accepted.canonical_business_hash == expected_business_hash
    assert accepted.provenance.canonical_business_hash == expected_business_hash


def test_source_duplicate_is_idempotent_noop_and_does_not_call_clock():
    first = _produce()

    def forbidden_clock():
        raise AssertionError("source duplicate called clock")

    duplicate = _produce(existing=first.accepted, clock=forbidden_clock)
    assert duplicate.status is BatchStatus.DUPLICATE
    assert duplicate.batch_reason is ReasonCode.SOURCE_DUPLICATE
    assert duplicate.publish_eligible is False
    assert duplicate.accepted == ()


def test_same_sku_different_business_state_remains_conflict():
    first = _produce()
    accepted = first.accepted[0]
    changed_record = {**accepted.validated_record, "product_name": "Different product"}
    business_fields = (
        "sku",
        "product_name",
        "category",
        "channel_ids",
        "stage",
        "grade",
        "status",
        "supplier",
        "currency",
        "purchase_cost",
        "sale_price",
        "fee_rate",
        "fulfillment_cost",
        "expected_return_cost",
        "other_variable_cost",
    )
    changed_hash = payload_sha256({field: changed_record.get(field) for field in business_fields})
    changed_provenance = replace(
        accepted.provenance,
        ingestion_identity="sha256:" + "0" * 64,
        canonical_business_hash=changed_hash,
    )
    changed_existing = replace(
        accepted,
        validated_record=changed_record,
        canonical_business_hash=changed_hash,
        provenance=changed_provenance,
    )
    result = _produce(existing=(changed_existing,))
    assert result.status is BatchStatus.CONFLICT
    assert result.publish_eligible is False
    assert result.conflicts[0].conflict_reason is ReasonCode.NATURAL_KEY_CONFLICT


def test_adapter_rejection_remains_batch_result_not_exception():
    result = _produce(clock=lambda: datetime(2026, 10, 19, 16, 21))
    assert type(result) is BatchResult
    assert result.status is BatchStatus.REJECTED
    assert result.batch_reason is ReasonCode.INVALID_TOOL_RESULT


@pytest.mark.parametrize(
    "boundary",
    [
        "raw_sha256",
        "TabularData",
        "SourceMetadata",
        "SensitiveBytes",
        "ToolResult",
        "ingest_product_master",
    ],
)
def test_existing_boundary_exceptions_propagate_unchanged(monkeypatch, boundary):
    sentinel = RuntimeError(f"{boundary} sentinel")

    def fail(*_args, **_kwargs):
        raise sentinel

    monkeypatch.setattr(bootstrap, boundary, fail)
    with pytest.raises(RuntimeError) as raised:
        _produce()
    assert raised.value is sentinel


def test_checksum_mismatch_fails_closed_before_boundary_construction(monkeypatch):
    monkeypatch.setattr(bootstrap, "raw_sha256", lambda _raw: "sha256:" + "0" * 64)
    monkeypatch.setattr(
        bootstrap,
        "TabularData",
        lambda *_args, **_kwargs: pytest.fail("lower-precedence boundary executed"),
    )
    with pytest.raises(ValueError, match="checksum"):
        _produce()


def test_non_exact_batch_result_is_rejected(monkeypatch):
    class BatchResultChild(BatchResult):
        pass

    child = BatchResultChild("batch:child", BatchStatus.READY)
    monkeypatch.setattr(bootstrap, "ingest_product_master", lambda *_args, **_kwargs: child)
    with pytest.raises(TypeError, match="exact BatchResult"):
        _produce()


def test_private_module_has_zero_exports_and_package_exports_are_unchanged():
    assert bootstrap.__all__ == ()
    assert "_produce_product_master_bootstrap_batch" not in data_hub.__all__
    assert "_ProductMasterBootstrapRecord" not in data_hub.__all__
    assert not hasattr(data_hub, "_produce_product_master_bootstrap_batch")
    assert data_hub.__all__ == [
        "AD_DAILY_SCHEMA",
        "CHANNEL_DAILY_SCHEMA",
        "CONTENT_ASSET_SCHEMA",
        "DERIVE_NET_SALES_RULE",
        "INVENTORY_SCHEMA",
        "PRODUCT_FACT_SCHEMA",
        "PRODUCT_MASTER_SCHEMA",
        "AcceptedRecord",
        "BatchResult",
        "BatchStatus",
        "ConflictRecord",
        "DuplicateRecord",
        "InMemoryReferencePublisher",
        "MappingEntry",
        "Provenance",
        "ReasonCode",
        "RejectedRecord",
        "SourceBatch",
        "ingest_ad_daily",
        "ingest_channel_daily",
        "ingest_content_asset",
        "ingest_inventory",
        "ingest_product_fact",
        "ingest_product_master",
    ]


def test_source_has_no_external_side_effect_or_id_generation_paths():
    source = inspect.getsource(bootstrap)
    tree = ast.parse(source)
    forbidden_import_roots = {
        "os",
        "pathlib",
        "random",
        "secrets",
        "socket",
        "requests",
        "urllib",
        "httpx",
    }
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.partition(".")[0])
    assert imported_roots.isdisjoint(forbidden_import_roots)
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert called_names.isdisjoint(
        {
            "open",
            "getenv",
            "generate_sku",
            "generate_run_id",
            "generate_task_id",
            "generate_idempotency_key",
            "InMemoryReferencePublisher",
        }
    )
    assert "repo://topspeed-ai-os/product-master/bootstrap/TS-WAIST-BRACE-L/v1" in source
    assert source.count("ingest_product_master(") == 1
