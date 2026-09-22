"""The deterministic PHASE 4 AD_DAILY architecture-proof slice.

This module consumes only the typed PHASE 3 ``ToolResult`` boundary.  It does
not call a Source, persist to a database, or calculate derived ad metrics.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence, Set
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Protocol

from topspeed_ai_os.contracts import ContractValidationError, validate_contract
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.core.ids import require_valid_run_id
from topspeed_ai_os.tools.checksum import raw_sha256
from topspeed_ai_os.tools.read.tabular import TabularData
from topspeed_ai_os.tools.redaction import sanitized_source_uri
from topspeed_ai_os.tools.result import SensitiveBytes, SourceMetadata, ToolResult, ToolStatus

AD_DAILY_SCHEMA = "topspeed.ad_daily.synthetic.v1"
_CHECKSUM = re.compile(r"^sha256:[0-9a-f]{64}$")
_INTEGER = re.compile(r"^-?(?:0|[1-9][0-9]*)$")
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_REQUIRED = (
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
_OPTIONAL = ("campaign_name", "ad_group_id", "ad_units")
_ALL_COLUMNS = frozenset((*_REQUIRED, *_OPTIONAL))


class ReasonCode(StrEnum):
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    UNSUPPORTED_MAPPING = "UNSUPPORTED_MAPPING"
    INVALID_TOOL_RESULT = "INVALID_TOOL_RESULT"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    UNSAFE_SOURCE_REFERENCE = "UNSAFE_SOURCE_REFERENCE"
    INVALID_ROW_SHAPE = "INVALID_ROW_SHAPE"
    MISSING_REQUIRED_SOURCE_FIELD = "MISSING_REQUIRED_SOURCE_FIELD"
    INVALID_SOURCE_VALUE = "INVALID_SOURCE_VALUE"
    INVALID_DATA_AS_OF = "INVALID_DATA_AS_OF"
    MISSING_SKU_MAPPING_KEY = "MISSING_SKU_MAPPING_KEY"
    UNKNOWN_SKU = "UNKNOWN_SKU"
    AMBIGUOUS_SKU = "AMBIGUOUS_SKU"
    UNREGISTERED_SKU = "UNREGISTERED_SKU"
    CONTRACT_VALIDATION_FAILED = "CONTRACT_VALIDATION_FAILED"
    BUSINESS_DUPLICATE = "BUSINESS_DUPLICATE"
    NATURAL_KEY_CONFLICT = "NATURAL_KEY_CONFLICT"
    SOURCE_DUPLICATE = "SOURCE_DUPLICATE"


class BatchStatus(StrEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class MappingEntry:
    source: str
    identifier_type: str
    external_product_id: str
    sku: str
    active: bool = True


@dataclass(frozen=True, slots=True)
class Provenance:
    source: str
    source_reference: str
    source_checksum: str
    fetched_at: datetime
    data_as_of: datetime
    data_as_of_origin: str
    task_id: str | None
    run_id: str
    source_row_reference: str
    schema_version: str
    mapping_fingerprint: str
    ingestion_identity: str
    normalization_rules_applied: tuple[str, ...]
    target_contract: str
    natural_key: tuple[Any, ...]
    canonical_business_hash: str


@dataclass(frozen=True, slots=True)
class AcceptedRecord:
    contract_name: str
    validated_record: Mapping[str, Any]
    natural_key: tuple[Any, ...]
    canonical_business_hash: str
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class RejectedRecord:
    source_row_reference: str
    reason_code: ReasonCode
    sanitized_summary: str
    source_reference: str
    natural_key: tuple[Any, ...] | None = None


@dataclass(frozen=True, slots=True)
class DuplicateRecord:
    source_row_reference: str
    natural_key: tuple[Any, ...]
    duplicate_reason: ReasonCode
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class ConflictRecord:
    source_row_reference: str
    natural_key: tuple[Any, ...]
    conflict_reason: ReasonCode
    source_reference: str


@dataclass(frozen=True, slots=True)
class SourceBatch:
    batch_id: str
    schema_version: str
    source_metadata: Any
    mapping_fingerprint: str
    tabular_data: TabularData
    run_id: str
    known_skus: frozenset[str]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BatchResult:
    batch_id: str
    status: BatchStatus
    accepted: tuple[AcceptedRecord, ...] = ()
    rejected: tuple[RejectedRecord, ...] = ()
    duplicates: tuple[DuplicateRecord, ...] = ()
    conflicts: tuple[ConflictRecord, ...] = ()
    publish_eligible: bool = False
    ingestion_identity: str | None = None
    summary: str = ""
    batch_reason: ReasonCode | None = None


class ReferencePublisher(Protocol):
    def publish(self, result: BatchResult) -> bool: ...


class InMemoryReferencePublisher:
    """Small architecture-test publisher; it is not a production store."""

    def __init__(self) -> None:
        self.current: tuple[AcceptedRecord, ...] | None = None
        self.last_ingestion_identity: str | None = None

    def publish(self, result: BatchResult) -> bool:
        if (
            not result.publish_eligible
            or result.status is not BatchStatus.READY
            or not result.accepted
            or result.rejected
            or result.conflicts
        ):
            return False
        current = list(self.current or ())
        by_key = {record.natural_key: record for record in current}
        for record in result.accepted:
            previous = by_key.get(record.natural_key)
            if (
                previous is not None
                and previous.canonical_business_hash != record.canonical_business_hash
            ):
                return False
            if previous is None:
                current.append(record)
                by_key[record.natural_key] = record
        self.current = tuple(current)
        self.last_ingestion_identity = result.ingestion_identity
        return True


def _safe_reference(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("source reference is missing")
    sanitized = sanitized_source_uri(value)
    if sanitized != value:
        raise ValueError("source reference is not sanitized")
    return sanitized


def _mapping_entries(
    mapping: Mapping[Any, Any] | Iterable[MappingEntry],
) -> tuple[MappingEntry, ...]:
    if isinstance(mapping, Mapping):
        entries: list[MappingEntry] = []
        for key, value in mapping.items():
            if isinstance(key, tuple) and len(key) == 3:
                source, identifier_type, external_id = key
            else:
                source, identifier_type, external_id = "tabular_file", "external_product_id", key
            if isinstance(value, str):
                entries.append(MappingEntry(source, identifier_type, str(external_id), value))
            elif isinstance(value, Mapping):
                active = value.get("active", True)
                if not isinstance(active, bool):
                    raise ValueError("mapping active must be bool")
                entries.append(
                    MappingEntry(
                        str(value.get("source", source)),
                        str(value.get("identifier_type", identifier_type)),
                        str(value.get("external_product_id", external_id)),
                        str(value.get("sku", "")),
                        active,
                    )
                )
            else:
                raise ValueError("unsupported mapping entry")
        return tuple(entries)
    entries = tuple(mapping)
    if any(
        not isinstance(entry, MappingEntry)
        or not isinstance(entry.source, str)
        or not isinstance(entry.identifier_type, str)
        or not isinstance(entry.external_product_id, str)
        or not isinstance(entry.sku, str)
        or not isinstance(entry.active, bool)
        for entry in entries
    ):
        raise ValueError("mapping entries must be valid MappingEntry values")
    return entries


def _fingerprint(entries: Sequence[MappingEntry], known_skus: Set[str]) -> str:
    effective = sorted(
        (e.source, e.identifier_type, e.external_product_id, e.sku, e.active)
        for e in entries
        if e.active
    )
    return payload_sha256({"entries": effective, "known_skus": sorted(known_skus)})


def _ingestion_identity(checksum: str, mapping_fp: str) -> str:
    return payload_sha256(
        {
            "target_contract": "AD_DAILY",
            "schema_version": AD_DAILY_SCHEMA,
            "source_checksum": checksum,
            "mapping_fingerprint": mapping_fp,
        }
    )


def _parse_date(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    date.fromisoformat(value)
    return value


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("datetime must be an ISO string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("datetime must include timezone")
    return parsed


def _parse_integer(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean is not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and _INTEGER.fullmatch(value):
        return int(value)
    raise ValueError("invalid integer")


def _parse_decimal(value: object) -> str:
    if not isinstance(value, str) or _DECIMAL.fullmatch(value) is None:
        raise ValueError("invalid canonical decimal")
    try:
        Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid canonical decimal") from exc
    return value


def _row_ref(data: TabularData, number: int) -> str:
    return f"{data.sheet_name}:{number}" if data.sheet_name else f"CSV row:{number}"


def _resolve_sku(
    entries: Sequence[MappingEntry], source: str, external_id: object, known_skus: Set[str]
) -> tuple[str | None, ReasonCode | None]:
    if not isinstance(external_id, str) or not external_id.strip():
        return None, ReasonCode.MISSING_SKU_MAPPING_KEY
    candidates = [
        e.sku
        for e in entries
        if e.active
        and e.source == source
        and e.identifier_type == "external_product_id"
        and e.external_product_id == external_id
    ]
    if not candidates:
        return None, ReasonCode.UNKNOWN_SKU
    if len(set(candidates)) != 1:
        return None, ReasonCode.AMBIGUOUS_SKU
    if candidates[0] not in known_skus:
        return None, ReasonCode.UNREGISTERED_SKU
    return candidates[0], None


def _business_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: record.get(key)
        for key in (
            "channel",
            "stat_date",
            "sku",
            "campaign_id",
            "campaign_name",
            "ad_group_id",
            "impressions",
            "clicks",
            "ad_spend",
            "ad_orders",
            "ad_units",
            "ad_revenue",
        )
    }


def _natural_key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(
        record.get(key) for key in ("channel", "stat_date", "sku", "campaign_id", "ad_group_id")
    )


def _invalid_result(
    batch_id: str, code: ReasonCode, summary: str, reference: str = ""
) -> BatchResult:
    return BatchResult(
        batch_id=batch_id,
        status=BatchStatus.REJECTED,
        rejected=(RejectedRecord("batch", code, summary, reference),),
        publish_eligible=False,
        summary=summary,
        batch_reason=code,
    )


def _safe_natural_key(raw: Mapping[str, Any], sku: str | None = None) -> tuple[Any, ...] | None:
    if sku is None:
        return None
    try:
        channel = _text(raw.get("channel"))
        stat_date = _parse_date(raw.get("stat_date"))
        campaign_id = _text(raw.get("campaign_id"))
    except (TypeError, ValueError):
        return None
    ad_group = raw.get("ad_group_id")
    if ad_group in (None, ""):
        ad_group = None
    elif not isinstance(ad_group, str):
        return None
    return channel, stat_date, sku, campaign_id, ad_group


def ingest_ad_daily(
    tool_result: ToolResult,
    *,
    run_id: str,
    known_skus: Set[str],
    sku_mapping: Mapping[Any, Any] | Iterable[MappingEntry],
    clock: Callable[[], datetime],
    schema_version: str = AD_DAILY_SCHEMA,
    existing: Iterable[AcceptedRecord] = (),
) -> BatchResult:
    """Convert one successful PHASE 3 tabular result into validated AD_DAILY records."""

    batch_id = (
        f"batch:{tool_result.request_id}" if hasattr(tool_result, "request_id") else "batch:invalid"
    )
    if not isinstance(tool_result, ToolResult):
        return _invalid_result(
            "batch:invalid", ReasonCode.INVALID_TOOL_RESULT, "invalid ToolResult"
        )
    if schema_version != AD_DAILY_SCHEMA:
        return _invalid_result(batch_id, ReasonCode.UNSUPPORTED_SCHEMA, "unsupported schema")
    try:
        require_valid_run_id(run_id)
    except (TypeError, ValueError):
        return _invalid_result(batch_id, ReasonCode.INVALID_TOOL_RESULT, "invalid run_id")
    if not isinstance(known_skus, Set):
        known_skus = set(known_skus)
    try:
        if tool_result.status is not ToolStatus.SUCCESS:
            return _invalid_result(
                batch_id, ReasonCode.INVALID_TOOL_RESULT, "ToolResult status is not SUCCESS"
            )
        if not isinstance(tool_result.parsed_result, TabularData):
            return _invalid_result(
                batch_id, ReasonCode.INVALID_TOOL_RESULT, "parsed_result is not TabularData"
            )
        if tool_result.source_metadata is None or tool_result.raw_result is None:
            return _invalid_result(
                batch_id, ReasonCode.INVALID_TOOL_RESULT, "ToolResult boundary is incomplete"
            )
        metadata = tool_result.source_metadata
        if not isinstance(metadata, SourceMetadata) or not isinstance(
            tool_result.raw_result, SensitiveBytes
        ):
            return _invalid_result(
                batch_id, ReasonCode.INVALID_TOOL_RESULT, "ToolResult boundary types are invalid"
            )
        if tool_result.run_id is not None and tool_result.run_id != run_id:
            return _invalid_result(
                batch_id,
                ReasonCode.INVALID_TOOL_RESULT,
                "ToolResult run_id does not match ingestion run_id",
            )
        try:
            reference = _safe_reference(metadata.source_uri)
        except ValueError:
            return _invalid_result(
                batch_id, ReasonCode.UNSAFE_SOURCE_REFERENCE, "unsafe source reference"
            )
        checksum = raw_sha256(tool_result.raw_result.reveal())
        if (
            checksum != metadata.checksum_sha256
            or _CHECKSUM.fullmatch(metadata.checksum_sha256) is None
        ):
            return _invalid_result(
                batch_id, ReasonCode.CHECKSUM_MISMATCH, "raw checksum mismatch", reference
            )
    except ValueError as exc:
        code = (
            ReasonCode.UNSAFE_SOURCE_REFERENCE
            if "reference" in str(exc)
            else ReasonCode.INVALID_TOOL_RESULT
        )
        return _invalid_result(batch_id, code, str(exc))

    data = tool_result.parsed_result
    headers = tuple(data.headers)
    if (
        len(headers) != len(set(headers))
        or not set(headers) >= set(_REQUIRED)
        or not set(headers) <= _ALL_COLUMNS
    ):
        return _invalid_result(
            batch_id,
            ReasonCode.INVALID_ROW_SHAPE,
            "unsupported source columns or missing headers",
            reference,
        )
    try:
        entries = _mapping_entries(sku_mapping)
    except (TypeError, ValueError):
        return _invalid_result(
            batch_id, ReasonCode.UNSUPPORTED_MAPPING, "unsupported SKU mapping", reference
        )
    mapping_fp = _fingerprint(entries, known_skus)
    ingestion_id = _ingestion_identity(metadata.checksum_sha256, mapping_fp)
    previous = tuple(existing)
    if any(item.provenance.ingestion_identity == ingestion_id for item in previous):
        return BatchResult(
            batch_id,
            BatchStatus.DUPLICATE,
            duplicates=(),
            publish_eligible=False,
            ingestion_identity=ingestion_id,
            summary="source duplicate / idempotent no-op",
            batch_reason=ReasonCode.SOURCE_DUPLICATE,
        )
    try:
        created_at = clock()
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
    except Exception as exc:
        return _invalid_result(batch_id, ReasonCode.INVALID_TOOL_RESULT, str(exc), reference)

    accepted: list[AcceptedRecord] = []
    rejected: list[RejectedRecord] = []
    duplicates: list[DuplicateRecord] = []
    conflicts: list[ConflictRecord] = []
    seen: dict[tuple[Any, ...], AcceptedRecord] = {item.natural_key: item for item in previous}
    for index, values in enumerate(data.rows, start=2):
        row_ref = _row_ref(data, index)
        if len(values) != len(headers):
            rejected.append(
                RejectedRecord(
                    row_ref, ReasonCode.INVALID_ROW_SHAPE, "row width mismatch", reference
                )
            )
            continue
        raw = dict(zip(headers, values, strict=True))
        normalized_rules: list[str] = []
        sku: str | None = None
        try:
            if raw.get("data_as_of") in (None, ""):
                raise _RowError(ReasonCode.INVALID_DATA_AS_OF, "source data_as_of is missing")
            if raw.get("external_product_id") in (None, ""):
                raise _RowError(
                    ReasonCode.MISSING_SKU_MAPPING_KEY, "external SKU mapping key is missing"
                )
            missing = [
                field
                for field in _REQUIRED
                if field not in {"data_as_of", "external_product_id"}
                and raw.get(field) in (None, "")
            ]
            if missing:
                raise _RowError(
                    ReasonCode.MISSING_REQUIRED_SOURCE_FIELD, "missing required source field"
                )
            sku, mapping_error = _resolve_sku(
                entries, metadata.source, raw.get("external_product_id"), known_skus
            )
            if mapping_error:
                raise _RowError(mapping_error, "SKU mapping failed")
            record: dict[str, Any] = {
                "channel": _text(raw["channel"]),
                "stat_date": _parse_date(raw["stat_date"]),
                "sku": sku,
                "campaign_id": _text(raw["campaign_id"]),
                "impressions": _parse_integer(raw["impressions"]),
                "clicks": _parse_integer(raw["clicks"]),
                "ad_spend": _parse_decimal(raw["ad_spend"]),
                "ad_orders": _parse_integer(raw["ad_orders"]),
                "ad_revenue": _parse_decimal(raw["ad_revenue"]),
                "source_file_hash": metadata.checksum_sha256,
                "run_id": run_id,
                "source": metadata.source,
                "data_as_of": raw["data_as_of"],
                "created_at": created_at.isoformat(),
            }
            for field_name in ("campaign_name", "ad_group_id", "ad_units"):
                if field_name in raw:
                    value = raw[field_name]
                    if field_name == "ad_units":
                        if value in (None, ""):
                            normalized_rules.append("blank_ad_units_to_none")
                            record[field_name] = None
                        else:
                            record[field_name] = _parse_integer(value)
                    else:
                        if value in (None, ""):
                            normalized_rules.append(f"blank_{field_name}_to_none")
                            record[field_name] = None
                        else:
                            record[field_name] = _text(value)
            try:
                _parse_datetime(raw["data_as_of"])
            except ValueError as exc:
                raise _RowError(ReasonCode.INVALID_DATA_AS_OF, "invalid source data_as_of") from exc
            record["data_as_of"] = str(raw["data_as_of"])
            validate_contract("AD_DAILY", record, known_skus=known_skus)
        except _RowError as exc:
            rejected.append(
                RejectedRecord(
                    row_ref,
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
                    row_ref,
                    ReasonCode.CONTRACT_VALIDATION_FAILED,
                    "row rejected by validation",
                    reference,
                    _safe_natural_key(raw, sku),
                )
            )
            continue
        except (ValueError, TypeError) as exc:
            code = (
                ReasonCode.INVALID_DATA_AS_OF
                if "data" in str(exc).lower() or "timezone" in str(exc).lower()
                else ReasonCode.INVALID_SOURCE_VALUE
            )
            rejected.append(
                RejectedRecord(
                    row_ref,
                    code,
                    "row rejected by validation",
                    reference,
                    _safe_natural_key(raw, sku),
                )
            )
            continue
        key = _natural_key(record)
        business_hash = payload_sha256(_business_payload(record))
        provenance = Provenance(
            metadata.source,
            reference,
            metadata.checksum_sha256,
            metadata.fetched_at,
            _parse_datetime(record["data_as_of"]),
            "source_row:data_as_of",
            tool_result.task_id,
            run_id,
            row_ref,
            schema_version,
            mapping_fp,
            ingestion_id,
            tuple(normalized_rules),
            "AD_DAILY",
            key,
            business_hash,
        )
        candidate = AcceptedRecord("AD_DAILY", record, key, business_hash, provenance)
        prior = seen.get(key)
        if prior is None:
            seen[key] = candidate
            accepted.append(candidate)
        elif prior.canonical_business_hash == business_hash:
            duplicates.append(
                DuplicateRecord(row_ref, key, ReasonCode.BUSINESS_DUPLICATE, provenance)
            )
        else:
            conflicts.append(
                ConflictRecord(row_ref, key, ReasonCode.NATURAL_KEY_CONFLICT, reference)
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
    eligible = bool(accepted) and not rejected and not conflicts
    return BatchResult(
        batch_id,
        status,
        tuple(accepted),
        tuple(rejected),
        tuple(duplicates),
        tuple(conflicts),
        eligible,
        ingestion_id,
        status.value,
    )


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("text field is empty")
    return value


@dataclass(frozen=True, slots=True)
class _RowError(ValueError):
    code: ReasonCode
    summary: str
