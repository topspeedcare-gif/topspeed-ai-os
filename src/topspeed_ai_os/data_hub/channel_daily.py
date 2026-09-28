"""Deterministic PHASE 4 CHANNEL_DAILY synthetic-v1 architecture-proof adapter."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Set
from datetime import datetime
from decimal import MAX_EMAX, MIN_EMIN, Decimal, localcontext
from typing import Any

from topspeed_ai_os.contracts import ContractValidationError, validate_contract
from topspeed_ai_os.contracts.logical_types import (
    InvalidDecimalError,
    parse_canonical_decimal,
)
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.core.ids import require_valid_run_id
from topspeed_ai_os.tools.checksum import raw_sha256
from topspeed_ai_os.tools.read.tabular import TabularData
from topspeed_ai_os.tools.result import SensitiveBytes, SourceMetadata, ToolResult, ToolStatus

from .adapter import (
    AcceptedRecord,
    BatchResult,
    BatchStatus,
    ConflictRecord,
    DuplicateRecord,
    MappingEntry,
    Provenance,
    ReasonCode,
    RejectedRecord,
    _fingerprint,
    _mapping_entries,
    _parse_date,
    _parse_datetime,
    _parse_integer,
    _record_contract_coherent,
    _record_identity,
    _resolve_sku,
    _row_ref,
    _safe_reference,
    _text,
)

CHANNEL_DAILY_SCHEMA = "topspeed.channel_daily.synthetic.v1"
DERIVE_NET_SALES_RULE = "derive_net_sales:gross_sales-refund_amount@synthetic.v1"

_CHECKSUM = re.compile(r"^sha256:[0-9a-f]{64}$")
_REQUIRED = (
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
_OPTIONAL = (
    "channel_product_id",
    "channel_fees",
    "settlement_amount",
    "page_views",
)
_FORBIDDEN = frozenset({"net_sales", "conversion_rate", "metric_version"})
_ALL_COLUMNS = frozenset((*_REQUIRED, *_OPTIONAL))


def _invalid_channel_result(
    batch_id: str,
    code: ReasonCode,
    summary: str,
    reference: str = "",
) -> BatchResult:
    return BatchResult(
        batch_id=batch_id,
        status=BatchStatus.REJECTED,
        rejected=(RejectedRecord("batch", code, summary, reference),),
        publish_eligible=False,
        summary=summary,
        batch_reason=code,
        target_contract="CHANNEL_DAILY",
    )


def _validate_metadata(metadata: SourceMetadata) -> None:
    if not isinstance(metadata.source, str) or not metadata.source.strip():
        raise ValueError("invalid source metadata")
    if not isinstance(metadata.source_uri, str) or not metadata.source_uri:
        raise ValueError("invalid source metadata")
    if not isinstance(metadata.fetched_at, datetime):
        raise ValueError("invalid source metadata")
    if metadata.fetched_at.tzinfo is None or metadata.fetched_at.utcoffset() is None:
        raise ValueError("invalid source metadata")
    if not isinstance(metadata.checksum_sha256, str):
        raise ValueError("invalid source metadata")


def _validate_tabular_structure(data: TabularData) -> tuple[str, ...]:
    if not isinstance(data.headers, tuple) or not isinstance(data.rows, tuple):
        raise ValueError("malformed tabular structure")
    headers = data.headers
    if not headers or any(not isinstance(header, str) or not header for header in headers):
        raise ValueError("malformed header")
    if len(headers) != len(set(headers)):
        raise ValueError("duplicate header")
    header_set = set(headers)
    if header_set & _FORBIDDEN:
        raise ValueError("forbidden source header")
    if not header_set >= set(_REQUIRED):
        raise ValueError("missing required header")
    if not header_set <= _ALL_COLUMNS:
        raise ValueError("unknown source header")
    if not data.rows:
        raise ValueError("empty input")
    if any(not isinstance(row, tuple) or len(row) != len(headers) for row in data.rows):
        raise ValueError("malformed row structure")
    if data.sheet_name is not None and not isinstance(data.sheet_name, str):
        raise ValueError("malformed tabular structure")
    return headers


def _canonical_decimal(value: object) -> tuple[str, Decimal]:
    try:
        parsed = parse_canonical_decimal(value)
    except InvalidDecimalError as exc:
        raise ValueError("invalid canonical decimal") from exc
    return value, parsed


def _exact_subtract(left: Decimal, right: Decimal) -> Decimal:
    """Subtract without the default Decimal context's 28-digit rounding."""

    left_tuple = left.as_tuple()
    right_tuple = right.as_tuple()
    common_exponent = min(left_tuple.exponent, right_tuple.exponent)
    left_width = len(left_tuple.digits) + left_tuple.exponent - common_exponent
    right_width = len(right_tuple.digits) + right_tuple.exponent - common_exponent
    precision = max(1, left_width, right_width) + 1
    with localcontext() as context:
        context.prec = precision
        context.Emax = MAX_EMAX
        context.Emin = MIN_EMIN
        context.clamp = 0
        return left - right


def _serialize_net_sales(value: Decimal) -> str:
    """Apply the synthetic-v1-only fixed-point serialization rule."""

    if value.is_zero():
        return "0"
    fixed = format(value, "f")
    if "." in fixed:
        fixed = fixed.rstrip("0").rstrip(".")
    return fixed


def _derive_net_sales(gross_sales: Decimal, refund_amount: Decimal) -> str:
    return _serialize_net_sales(_exact_subtract(gross_sales, refund_amount))


def _ingestion_identity(checksum: str, mapping_fingerprint: str) -> str:
    return payload_sha256(
        {
            "target_contract": "CHANNEL_DAILY",
            "schema_version": CHANNEL_DAILY_SCHEMA,
            "source_checksum": checksum,
            "mapping_fingerprint": mapping_fingerprint,
        }
    )


def _business_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: record.get(key)
        for key in (
            "channel",
            "stat_date",
            "sku",
            "channel_product_id",
            "gross_sales",
            "net_sales",
            "orders",
            "units_sold",
            "refunds",
            "refund_amount",
            "channel_fees",
            "settlement_amount",
            "page_views",
        )
    }


def _natural_key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(record.get(key) for key in ("channel", "stat_date", "sku"))


def _safe_natural_key(raw: Mapping[str, Any], sku: str | None = None) -> tuple[Any, ...] | None:
    if sku is None:
        return None
    try:
        return _text(raw.get("channel")), _parse_date(raw.get("stat_date")), sku
    except (TypeError, ValueError):
        return None


def _optional_value(
    raw: Mapping[str, Any],
    record: dict[str, Any],
    field_name: str,
    parser: Callable[[object], Any],
    normalization_rules: list[str],
) -> None:
    if field_name not in raw:
        return
    value = raw[field_name]
    if value in (None, ""):
        normalization_rules.append(f"blank_{field_name}_to_none")
        record[field_name] = None
    else:
        record[field_name] = parser(value)


def _decimal_string(value: object) -> str:
    canonical, _ = _canonical_decimal(value)
    return canonical


def ingest_channel_daily(
    tool_result: ToolResult,
    *,
    run_id: str,
    known_skus: Set[str],
    sku_mapping: Mapping[Any, Any] | Iterable[MappingEntry],
    clock: Callable[[], datetime],
    schema_version: str = CHANNEL_DAILY_SCHEMA,
    existing: Iterable[AcceptedRecord] = (),
) -> BatchResult:
    """Convert one successful PHASE 3 result into validated CHANNEL_DAILY records."""

    batch_id = (
        f"batch:{tool_result.request_id}" if hasattr(tool_result, "request_id") else "batch:invalid"
    )
    if not isinstance(tool_result, ToolResult):
        return _invalid_channel_result(
            "batch:invalid", ReasonCode.INVALID_TOOL_RESULT, "invalid ToolResult"
        )
    if schema_version != CHANNEL_DAILY_SCHEMA:
        return _invalid_channel_result(
            batch_id, ReasonCode.UNSUPPORTED_SCHEMA, "unsupported schema"
        )
    try:
        require_valid_run_id(run_id)
    except (TypeError, ValueError):
        return _invalid_channel_result(batch_id, ReasonCode.INVALID_TOOL_RESULT, "invalid run_id")
    try:
        if not isinstance(known_skus, Set):
            known_skus = set(known_skus)
        if not all(isinstance(sku, str) for sku in known_skus):
            raise ValueError("known_skus must contain strings")
    except (TypeError, ValueError):
        return _invalid_channel_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, "invalid known_skus"
        )

    if tool_result.status is not ToolStatus.SUCCESS:
        return _invalid_channel_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, "ToolResult status is not SUCCESS"
        )
    if not isinstance(tool_result.parsed_result, TabularData):
        return _invalid_channel_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, "parsed_result is not TabularData"
        )
    if not isinstance(tool_result.source_metadata, SourceMetadata) or not isinstance(
        tool_result.raw_result, SensitiveBytes
    ):
        return _invalid_channel_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, "ToolResult boundary is incomplete"
        )
    if tool_result.run_id is not None and tool_result.run_id != run_id:
        return _invalid_channel_result(
            batch_id,
            ReasonCode.INVALID_TOOL_RESULT,
            "ToolResult run_id does not match ingestion run_id",
        )

    metadata = tool_result.source_metadata
    try:
        _validate_metadata(metadata)
        reference = _safe_reference(metadata.source_uri)
    except (TypeError, ValueError):
        return _invalid_channel_result(
            batch_id, ReasonCode.UNSAFE_SOURCE_REFERENCE, "invalid or unsafe source metadata"
        )
    try:
        checksum = raw_sha256(tool_result.raw_result.reveal())
    except (TypeError, ValueError):
        return _invalid_channel_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, "invalid raw result", reference
        )
    if (
        checksum != metadata.checksum_sha256
        or _CHECKSUM.fullmatch(metadata.checksum_sha256) is None
    ):
        return _invalid_channel_result(
            batch_id, ReasonCode.CHECKSUM_MISMATCH, "raw checksum mismatch", reference
        )

    data = tool_result.parsed_result
    try:
        headers = _validate_tabular_structure(data)
    except (TypeError, ValueError) as exc:
        return _invalid_channel_result(batch_id, ReasonCode.INVALID_ROW_SHAPE, str(exc), reference)
    try:
        entries = _mapping_entries(sku_mapping)
        mapping_fingerprint = _fingerprint(entries, known_skus)
    except (TypeError, ValueError):
        return _invalid_channel_result(
            batch_id, ReasonCode.UNSUPPORTED_MAPPING, "unsupported SKU mapping", reference
        )

    ingestion_identity = _ingestion_identity(metadata.checksum_sha256, mapping_fingerprint)
    try:
        previous = tuple(existing)
    except TypeError:
        return _invalid_channel_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, "invalid existing records", reference
        )
    for item in previous:
        if not _record_contract_coherent(item):
            return _invalid_channel_result(
                batch_id,
                ReasonCode.INVALID_TOOL_RESULT,
                "existing record Contract metadata is inconsistent",
                reference,
            )
    same_contract_previous = tuple(
        item for item in previous if item.contract_name == "CHANNEL_DAILY"
    )
    if any(
        item.provenance.ingestion_identity == ingestion_identity for item in same_contract_previous
    ):
        return BatchResult(
            batch_id=batch_id,
            status=BatchStatus.DUPLICATE,
            publish_eligible=False,
            ingestion_identity=ingestion_identity,
            summary="source duplicate / idempotent no-op",
            batch_reason=ReasonCode.SOURCE_DUPLICATE,
            target_contract="CHANNEL_DAILY",
        )

    try:
        created_at = clock()
        if not isinstance(created_at, datetime):
            raise ValueError("clock must return datetime")
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
    except Exception as exc:
        return _invalid_channel_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, str(exc), reference
        )

    accepted: list[AcceptedRecord] = []
    rejected: list[RejectedRecord] = []
    duplicates: list[DuplicateRecord] = []
    conflicts: list[ConflictRecord] = []
    seen: dict[tuple[str, tuple[Any, ...]], AcceptedRecord] = {
        _record_identity(item): item for item in same_contract_previous
    }

    for index, values in enumerate(data.rows, start=2):
        row_reference = _row_ref(data, index)
        raw = dict(zip(headers, values, strict=True))
        normalization_rules = [DERIVE_NET_SALES_RULE]
        sku: str | None = None
        try:
            if raw.get("data_as_of") in (None, ""):
                raise _ChannelRowError(
                    ReasonCode.INVALID_DATA_AS_OF, "source data_as_of is missing"
                )
            if raw.get("external_product_id") in (None, ""):
                raise _ChannelRowError(
                    ReasonCode.MISSING_SKU_MAPPING_KEY,
                    "external SKU mapping key is missing",
                )
            missing = [
                field
                for field in _REQUIRED
                if field not in {"data_as_of", "external_product_id"}
                and raw.get(field) in (None, "")
            ]
            if missing:
                raise _ChannelRowError(
                    ReasonCode.MISSING_REQUIRED_SOURCE_FIELD,
                    "missing required source field",
                )
            sku, mapping_error = _resolve_sku(
                entries, metadata.source, raw.get("external_product_id"), known_skus
            )
            if mapping_error:
                raise _ChannelRowError(mapping_error, "SKU mapping failed")

            gross_sales, gross_decimal = _canonical_decimal(raw["gross_sales"])
            refund_amount, refund_decimal = _canonical_decimal(raw["refund_amount"])
            data_as_of = _parse_datetime(raw["data_as_of"])
            record: dict[str, Any] = {
                "channel": _text(raw["channel"]),
                "stat_date": _parse_date(raw["stat_date"]),
                "sku": sku,
                "gross_sales": gross_sales,
                "net_sales": _derive_net_sales(gross_decimal, refund_decimal),
                "orders": _parse_integer(raw["orders"]),
                "units_sold": _parse_integer(raw["units_sold"]),
                "refunds": _parse_integer(raw["refunds"]),
                "refund_amount": refund_amount,
                "run_id": run_id,
                "source": metadata.source,
                "data_as_of": str(raw["data_as_of"]),
                "created_at": created_at.isoformat(),
            }
            _optional_value(raw, record, "channel_product_id", _text, normalization_rules)
            _optional_value(raw, record, "channel_fees", _decimal_string, normalization_rules)
            _optional_value(raw, record, "settlement_amount", _decimal_string, normalization_rules)
            _optional_value(raw, record, "page_views", _parse_integer, normalization_rules)
            validate_contract("CHANNEL_DAILY", record, known_skus=known_skus)
        except _ChannelRowError as exc:
            rejected.append(
                RejectedRecord(
                    row_reference,
                    exc.code,
                    exc.summary,
                    reference,
                    _safe_natural_key(raw),
                )
            )
            continue
        except ContractValidationError:
            rejected.append(
                RejectedRecord(
                    row_reference,
                    ReasonCode.CONTRACT_VALIDATION_FAILED,
                    "row rejected by validation",
                    reference,
                    _safe_natural_key(raw, sku),
                )
            )
            continue
        except (TypeError, ValueError):
            rejected.append(
                RejectedRecord(
                    row_reference,
                    ReasonCode.INVALID_SOURCE_VALUE,
                    "row rejected by validation",
                    reference,
                    _safe_natural_key(raw, sku),
                )
            )
            continue

        key = _natural_key(record)
        business_hash = payload_sha256(_business_payload(record))
        provenance = Provenance(
            source=metadata.source,
            source_reference=reference,
            source_checksum=metadata.checksum_sha256,
            fetched_at=metadata.fetched_at,
            data_as_of=data_as_of,
            data_as_of_origin="source_row:data_as_of",
            task_id=tool_result.task_id,
            run_id=run_id,
            source_row_reference=row_reference,
            schema_version=schema_version,
            mapping_fingerprint=mapping_fingerprint,
            ingestion_identity=ingestion_identity,
            normalization_rules_applied=tuple(normalization_rules),
            target_contract="CHANNEL_DAILY",
            natural_key=key,
            canonical_business_hash=business_hash,
        )
        candidate = AcceptedRecord("CHANNEL_DAILY", record, key, business_hash, provenance)
        identity = _record_identity(candidate)
        prior = seen.get(identity)
        if prior is None:
            seen[identity] = candidate
            accepted.append(candidate)
        elif prior.canonical_business_hash == business_hash:
            duplicates.append(
                DuplicateRecord(row_reference, key, ReasonCode.BUSINESS_DUPLICATE, provenance)
            )
        else:
            conflicts.append(
                ConflictRecord(row_reference, key, ReasonCode.NATURAL_KEY_CONFLICT, reference)
            )

    status = (
        BatchStatus.CONFLICT
        if conflicts
        else BatchStatus.PARTIAL
        if accepted and rejected
        else BatchStatus.DUPLICATE
        if duplicates and not accepted and not rejected
        else BatchStatus.REJECTED
        if rejected and not accepted
        else BatchStatus.READY
        if accepted
        else BatchStatus.REJECTED
    )
    publish_eligible = bool(accepted) and not rejected and not conflicts
    return BatchResult(
        batch_id=batch_id,
        status=status,
        accepted=tuple(accepted),
        rejected=tuple(rejected),
        duplicates=tuple(duplicates),
        conflicts=tuple(conflicts),
        publish_eligible=publish_eligible,
        ingestion_identity=ingestion_identity,
        summary=status.value,
        target_contract="CHANNEL_DAILY",
    )


class _ChannelRowError(ValueError):
    def __init__(self, code: ReasonCode, summary: str) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary
