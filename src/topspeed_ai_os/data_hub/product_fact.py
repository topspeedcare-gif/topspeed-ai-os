"""Deterministic PHASE 4 PRODUCT_FACT synthetic-v1 architecture-proof adapter."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping, Set
from datetime import datetime
from typing import Any

from topspeed_ai_os.contracts import ContractValidationError, validate_contract
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.core.ids import (
    generate_fact_id,
    require_valid_fact_id,
    require_valid_run_id,
    require_valid_task_id,
)
from topspeed_ai_os.tools.checksum import raw_sha256
from topspeed_ai_os.tools.read.tabular import TabularData
from topspeed_ai_os.tools.result import SensitiveBytes, SourceMetadata, ToolResult, ToolStatus

from .adapter import (
    AcceptedRecord,
    BatchResult,
    BatchStatus,
    ConflictRecord,
    DuplicateRecord,
    Provenance,
    ReasonCode,
    RejectedRecord,
    _make_row_trace,
    _parse_datetime,
    _record_contract_coherent,
    _record_identity,
    _row_ref,
    _safe_reference,
)

PRODUCT_FACT_SCHEMA = "topspeed.product_fact.synthetic.v1"

_CHECKSUM = re.compile(r"^sha256:[0-9a-f]{64}$")
_REQUIRED = ("sku", "fact_type", "fact_value", "data_as_of")
_OPTIONAL = ("unit",)
_FORBIDDEN = frozenset(
    {
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
    }
)
_ALL_COLUMNS = frozenset((*_REQUIRED, *_OPTIONAL))


def _invalid_result(
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
        target_contract="PRODUCT_FACT",
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
    if (
        not isinstance(metadata.checksum_sha256, str)
        or _CHECKSUM.fullmatch(metadata.checksum_sha256) is None
    ):
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


def _known_sku_set(known_skus: Iterable[str] | Set[str]) -> frozenset[str]:
    if isinstance(known_skus, (str, bytes, Mapping)):
        raise ValueError("known_skus must be an iterable of strings")
    values = frozenset(known_skus)
    if not all(isinstance(sku, str) for sku in values):
        raise ValueError("known_skus must contain strings")
    return values


def _mapping_fingerprint(known_skus: Set[str]) -> str:
    return payload_sha256(
        {
            "strategy": "direct_internal_sku",
            "schema_version": PRODUCT_FACT_SCHEMA,
            "known_skus": sorted(known_skus),
        }
    )


def _ingestion_identity(checksum: str, mapping_fingerprint: str) -> str:
    return payload_sha256(
        {
            "target_contract": "PRODUCT_FACT",
            "schema_version": PRODUCT_FACT_SCHEMA,
            "source_checksum": checksum,
            "mapping_fingerprint": mapping_fingerprint,
        }
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _fact_value(value: object) -> dict[str, Any] | list[Any]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("fact_value must be non-empty JSON text")
    try:
        parsed = json.loads(
            value,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("invalid fact_value JSON text") from exc
    if not isinstance(parsed, (dict, list)):
        raise ValueError("fact_value JSON root must be an object or array")
    return parsed


def _fact_type(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("invalid fact_type")
    return value


def _unit(raw: Mapping[str, Any], record: dict[str, Any], rules: list[str]) -> None:
    if "unit" not in raw:
        return
    value = raw["unit"]
    if value is None or (isinstance(value, str) and not value.strip()):
        record["unit"] = None
        rules.append("blank_unit_to_none")
        return
    if not isinstance(value, str):
        raise ValueError("unit must be a string")
    record["unit"] = value


def _business_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sku": record.get("sku"),
        "fact_type": record.get("fact_type"),
        "fact_value": record.get("fact_value"),
        "unit": record.get("unit"),
        "verification_status": record.get("verification_status"),
    }


def _natural_key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(record.get(key) for key in ("sku", "fact_type", "source", "data_as_of"))


def _safe_natural_key(
    raw: Mapping[str, Any], source: str, sku: str | None = None
) -> tuple[Any, ...] | None:
    if sku is None:
        return None
    try:
        fact_type = _fact_type(raw.get("fact_type"))
        _parse_datetime(raw.get("data_as_of"))
        data_as_of = str(raw["data_as_of"])
    except (KeyError, TypeError, ValueError):
        return None
    return sku, fact_type, source, data_as_of


def ingest_product_fact(
    tool_result: ToolResult,
    *,
    run_id: str,
    known_skus: Iterable[str] | Set[str],
    clock: Callable[[], datetime],
    schema_version: str = PRODUCT_FACT_SCHEMA,
    existing: Iterable[AcceptedRecord] = (),
) -> BatchResult:
    """Convert a successful PHASE 3 result into immutable UNVERIFIED PRODUCT_FACT records."""

    batch_id = (
        f"batch:{tool_result.request_id}" if hasattr(tool_result, "request_id") else "batch:invalid"
    )
    if not isinstance(tool_result, ToolResult):
        return _invalid_result(
            "batch:invalid", ReasonCode.INVALID_TOOL_RESULT, "invalid ToolResult"
        )
    if schema_version != PRODUCT_FACT_SCHEMA:
        return _invalid_result(batch_id, ReasonCode.UNSUPPORTED_SCHEMA, "unsupported schema")
    try:
        require_valid_run_id(run_id)
    except (TypeError, ValueError):
        return _invalid_result(batch_id, ReasonCode.INVALID_TOOL_RESULT, "invalid run_id")
    try:
        known_skus = _known_sku_set(known_skus)
    except Exception:
        return _invalid_result(batch_id, ReasonCode.INVALID_TOOL_RESULT, "invalid known_skus")

    if tool_result.status is not ToolStatus.SUCCESS:
        return _invalid_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, "ToolResult status is not SUCCESS"
        )
    if not isinstance(tool_result.parsed_result, TabularData):
        return _invalid_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, "parsed_result is not TabularData"
        )
    if not isinstance(tool_result.source_metadata, SourceMetadata) or not isinstance(
        tool_result.raw_result, SensitiveBytes
    ):
        return _invalid_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, "ToolResult boundary is incomplete"
        )
    if tool_result.run_id is not None and tool_result.run_id != run_id:
        return _invalid_result(
            batch_id,
            ReasonCode.INVALID_TOOL_RESULT,
            "ToolResult run_id does not match ingestion run_id",
        )
    if tool_result.task_id is not None:
        try:
            require_valid_task_id(tool_result.task_id)
        except (TypeError, ValueError):
            return _invalid_result(batch_id, ReasonCode.INVALID_TOOL_RESULT, "invalid task_id")

    metadata = tool_result.source_metadata
    try:
        _validate_metadata(metadata)
        reference = _safe_reference(metadata.source_uri)
    except (TypeError, ValueError):
        return _invalid_result(
            batch_id, ReasonCode.UNSAFE_SOURCE_REFERENCE, "invalid or unsafe source metadata"
        )
    try:
        checksum = raw_sha256(tool_result.raw_result.reveal())
    except (TypeError, ValueError):
        return _invalid_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, "invalid raw result", reference
        )
    if checksum != metadata.checksum_sha256:
        return _invalid_result(
            batch_id, ReasonCode.CHECKSUM_MISMATCH, "raw checksum mismatch", reference
        )

    data = tool_result.parsed_result
    try:
        headers = _validate_tabular_structure(data)
    except (TypeError, ValueError) as exc:
        return _invalid_result(batch_id, ReasonCode.INVALID_ROW_SHAPE, str(exc), reference)

    mapping_fingerprint = _mapping_fingerprint(known_skus)
    ingestion_identity = _ingestion_identity(metadata.checksum_sha256, mapping_fingerprint)
    try:
        previous = tuple(existing)
    except Exception:
        return _invalid_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, "invalid existing records", reference
        )
    for item in previous:
        if not _record_contract_coherent(item):
            return _invalid_result(
                batch_id,
                ReasonCode.INVALID_TOOL_RESULT,
                "existing record Contract metadata is inconsistent",
                reference,
            )
    same_contract_previous = tuple(
        item for item in previous if item.contract_name == "PRODUCT_FACT"
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
            target_contract="PRODUCT_FACT",
        )

    try:
        created_at = clock()
        if not isinstance(created_at, datetime):
            raise ValueError("clock must return datetime")
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
    except Exception as exc:
        return _invalid_result(batch_id, ReasonCode.INVALID_TOOL_RESULT, str(exc), reference)

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
        row_trace = _make_row_trace(
            target_contract="PRODUCT_FACT",
            schema_version=schema_version,
            source=metadata.source,
            source_reference=reference,
            source_checksum=metadata.checksum_sha256,
            source_row_reference=row_reference,
            raw_data_as_of=raw.get("data_as_of"),
            run_id=run_id,
            task_id=tool_result.task_id,
        )
        normalization_rules: list[str] = []
        sku: str | None = None
        try:
            if raw.get("data_as_of") in (None, ""):
                raise _ProductFactRowError(
                    ReasonCode.INVALID_DATA_AS_OF, "source data_as_of is missing"
                )
            missing = [
                field
                for field in _REQUIRED
                if field != "data_as_of"
                and (
                    raw.get(field) is None
                    or (isinstance(raw.get(field), str) and not raw.get(field).strip())
                )
            ]
            if missing:
                raise _ProductFactRowError(
                    ReasonCode.MISSING_REQUIRED_SOURCE_FIELD,
                    "missing required source field",
                )
            if not isinstance(raw["sku"], str):
                raise ValueError("sku must be a string")
            sku = raw["sku"]
            if sku not in known_skus:
                raise _ProductFactRowError(ReasonCode.UNREGISTERED_SKU, "SKU is not registered")
            fact_type = _fact_type(raw["fact_type"])
            fact_value = _fact_value(raw["fact_value"])
            try:
                data_as_of = _parse_datetime(raw["data_as_of"])
            except (TypeError, ValueError) as exc:
                raise _ProductFactRowError(
                    ReasonCode.INVALID_DATA_AS_OF, "invalid source data_as_of"
                ) from exc
            record: dict[str, Any] = {
                "sku": sku,
                "fact_type": fact_type,
                "fact_value": fact_value,
                "verification_status": "UNVERIFIED",
                "source": metadata.source,
                "run_id": run_id,
                "data_as_of": str(raw["data_as_of"]),
                "created_at": created_at.isoformat(),
            }
            if tool_result.task_id is not None:
                record["task_id"] = tool_result.task_id
            _unit(raw, record, normalization_rules)
            try:
                fact_id = generate_fact_id()
                require_valid_fact_id(fact_id)
            except Exception as exc:
                return _invalid_result(
                    batch_id, ReasonCode.INVALID_TOOL_RESULT, str(exc), reference
                )
            record["fact_id"] = fact_id
            validate_contract("PRODUCT_FACT", record, known_skus=known_skus)
        except _ProductFactRowError as exc:
            rejected.append(
                RejectedRecord(
                    row_reference,
                    exc.code,
                    exc.summary,
                    reference,
                    _safe_natural_key(raw, metadata.source, sku),
                    row_trace,
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
                    _safe_natural_key(raw, metadata.source, sku),
                    row_trace,
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
                    _safe_natural_key(raw, metadata.source, sku),
                    row_trace,
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
            target_contract="PRODUCT_FACT",
            natural_key=key,
            canonical_business_hash=business_hash,
        )
        candidate = AcceptedRecord("PRODUCT_FACT", record, key, business_hash, provenance)
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
                ConflictRecord(
                    row_reference, key, ReasonCode.NATURAL_KEY_CONFLICT, reference, row_trace
                )
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
        target_contract="PRODUCT_FACT",
    )


class _ProductFactRowError(ValueError):
    def __init__(self, code: ReasonCode, summary: str) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary
