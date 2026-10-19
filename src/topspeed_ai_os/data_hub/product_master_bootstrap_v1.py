"""Private PRODUCT_MASTER bootstrap producer for one Human-approved record."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, fields
from datetime import datetime

from topspeed_ai_os.core.ids import require_valid_run_id
from topspeed_ai_os.tools.checksum import raw_sha256
from topspeed_ai_os.tools.read.tabular import TabularData
from topspeed_ai_os.tools.result import (
    ExecutionMode,
    SensitiveBytes,
    SourceMetadata,
    ToolResult,
    ToolStatus,
)

from .adapter import AcceptedRecord, BatchResult
from .product_master import PRODUCT_MASTER_SCHEMA, ingest_product_master

__all__: tuple[str, ...] = ()

_RECORD_FIELDS = (
    "sku",
    "product_name",
    "category",
    "stage",
    "status",
    "currency",
    "data_as_of",
)
_APPROVED_SKU = "TS-WAIST-BRACE-L"
_APPROVED_PRODUCT_NAME = "[5중지지] 탑스피드 허리보호대 L"
_APPROVED_CATEGORY = "건강관리용품"
_APPROVED_STAGE = "CORE"
_APPROVED_STATUS = "ACTIVE"
_APPROVED_CURRENCY = "KRW"
_APPROVED_DATA_AS_OF = "2026-10-19T16:18:10+09:00"
_APPROVED_CHECKSUM = "sha256:32cc3b490277426594ebf9b26c55ecc29e69f978c32974f88d86b9b3c367e5ae"
_SOURCE = "manual_verified"
_SOURCE_URI = "repo://topspeed-ai-os/product-master/bootstrap/TS-WAIST-BRACE-L/v1"
_REQUEST_ID_PATTERN = re.compile(r"^req_[0-9a-f]{32}$")


def _require_exact_literal(value: object, field_name: str, expected: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be an exact str")
    if value != expected:
        raise ValueError(f"{field_name} must equal the approved literal")


def _require_canonical_aware_datetime(value: str, field_name: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a real ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    canonical = parsed.isoformat()
    if value.endswith("Z"):
        canonical = canonical.removesuffix("+00:00") + "Z"
    if canonical != value:
        raise ValueError(f"{field_name} must be canonical")


@dataclass(frozen=True, slots=True)
class _ProductMasterBootstrapRecord:
    sku: str
    product_name: str
    category: str
    stage: str
    status: str
    currency: str
    data_as_of: str

    def __post_init__(self) -> None:
        _validate_record_values(self)


def _validate_record_values(record: _ProductMasterBootstrapRecord) -> None:
    _require_exact_literal(record.sku, "sku", _APPROVED_SKU)
    _require_exact_literal(record.product_name, "product_name", _APPROVED_PRODUCT_NAME)
    _require_exact_literal(record.category, "category", _APPROVED_CATEGORY)
    _require_exact_literal(record.stage, "stage", _APPROVED_STAGE)
    _require_exact_literal(record.status, "status", _APPROVED_STATUS)
    _require_exact_literal(record.currency, "currency", _APPROVED_CURRENCY)
    _require_exact_literal(record.data_as_of, "data_as_of", _APPROVED_DATA_AS_OF)
    _require_canonical_aware_datetime(record.data_as_of, "data_as_of")


_BOOTSTRAP_RECORD = _ProductMasterBootstrapRecord(
    sku=_APPROVED_SKU,
    product_name=_APPROVED_PRODUCT_NAME,
    category=_APPROVED_CATEGORY,
    stage=_APPROVED_STAGE,
    status=_APPROVED_STATUS,
    currency=_APPROVED_CURRENCY,
    data_as_of=_APPROVED_DATA_AS_OF,
)


def _serialize_record(record: _ProductMasterBootstrapRecord) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(_RECORD_FIELDS)
    writer.writerow(tuple(getattr(record, field_name) for field_name in _RECORD_FIELDS))
    return stream.getvalue().encode("utf-8")


def _produce_product_master_bootstrap_batch(
    *,
    request_id: str,
    run_id: str,
    fetched_at: datetime,
    clock: Callable[[], datetime],
    existing: Iterable[AcceptedRecord] = (),
) -> BatchResult:
    """Produce one repository-owned bootstrap batch without publishing it."""

    record = _BOOTSTRAP_RECORD

    # 1. Exact private record identity.
    if type(record) is not _ProductMasterBootstrapRecord:
        raise TypeError("bootstrap record must have the exact private record identity")

    # 2. Exact private record shape and order.
    if tuple(field.name for field in fields(_ProductMasterBootstrapRecord)) != _RECORD_FIELDS:
        raise TypeError("bootstrap record fields or field order are invalid")

    # 3-10. Exact types, approved literals, and canonical source-validity datetime.
    _validate_record_values(record)

    # 11-12. Exact request identifier type and syntax.
    if type(request_id) is not str:
        raise TypeError("request_id must be an exact str")
    if _REQUEST_ID_PATTERN.fullmatch(request_id) is None:
        raise ValueError("request_id must match ^req_[0-9a-f]{32}$")

    # 13-14. Exact run identifier type and existing identifier authority.
    if type(run_id) is not str:
        raise TypeError("run_id must be an exact str")
    require_valid_run_id(run_id)

    # 15-16. Exact fetched_at identity and timezone awareness.
    if type(fetched_at) is not datetime:
        raise TypeError("fetched_at must be an exact datetime")
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise ValueError("fetched_at must be timezone-aware")

    # 17. The Adapter remains the sole clock caller.
    if not callable(clock):
        raise TypeError("clock must be callable")

    # 18-19. Canonical in-memory CSV and exact approved checksum.
    raw_bytes = _serialize_record(record)
    checksum = raw_sha256(raw_bytes)
    if checksum != _APPROVED_CHECKSUM:
        raise ValueError("canonical bootstrap checksum does not match the approved checksum")

    # 20-22. Existing typed read-tool boundary, with no filesystem or network access.
    tabular_data = TabularData(
        headers=_RECORD_FIELDS,
        rows=(tuple(getattr(record, field_name) for field_name in _RECORD_FIELDS),),
        sheet_name=None,
    )
    source_metadata = SourceMetadata(
        source=_SOURCE,
        source_uri=_SOURCE_URI,
        fetched_at=fetched_at,
        data_as_of=None,
        checksum_sha256=checksum,
    )
    sensitive_bytes = SensitiveBytes(raw_bytes)
    tool_result = ToolResult(
        tool_name="product_master_bootstrap",
        operation="product_master.bootstrap_v1",
        request_id=request_id,
        status=ToolStatus.SUCCESS,
        execution_mode=ExecutionMode.MOCK,
        task_id=None,
        run_id=run_id,
        source_metadata=source_metadata,
        raw_result=sensitive_bytes,
        parsed_result=tabular_data,
    )

    # 23. Forward the exact clock and existing iterable once, without pre-consumption.
    result = ingest_product_master(
        tool_result,
        run_id=run_id,
        clock=clock,
        schema_version=PRODUCT_MASTER_SCHEMA,
        existing=existing,
    )

    # 24-25. Preserve the exact authoritative BatchResult object and semantics.
    if type(result) is not BatchResult:
        raise TypeError("ingest_product_master must return the exact BatchResult type")
    return result
