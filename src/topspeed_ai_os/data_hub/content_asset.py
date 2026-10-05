"""Deterministic PHASE 4 CONTENT_ASSET synthetic-v1 architecture-proof adapter."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from typing import Any

from topspeed_ai_os.contracts import (
    ContractValidationError,
    validate_contract,
    validate_schema_only,
)
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.core.enums import AssetType, VerificationStatus
from topspeed_ai_os.core.ids import (
    generate_asset_id,
    require_valid_asset_id,
    require_valid_fact_id,
    require_valid_run_id,
    require_valid_sku,
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
    _parse_datetime,
    _record_contract_coherent,
    _row_ref,
    _safe_reference,
)

CONTENT_ASSET_SCHEMA = "topspeed.content_asset.synthetic.v1"

_MAPPING_STRATEGY_VERSION = "topspeed.content_asset.mapping.direct_sku_fact_context.v1"
_SKU_STRATEGY = "direct_internal_sku"
_CHECKSUM = re.compile(r"^sha256:[0-9a-f]{64}$")
_REQUIRED = (
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
_ALL_COLUMNS = frozenset(_REQUIRED)
_MAPPING_KEYS = frozenset(
    {"known_skus", "mapping_strategy_version", "product_fact_context", "sku_strategy"}
)
_FACT_CONTEXT_KEYS = frozenset(
    {"fact_id", "sku", "fact_type", "fact_value", "unit", "verification_status"}
)
_IDENTITY_KEYS = frozenset(
    {"target_contract", "schema_version", "source_checksum", "mapping_fingerprint"}
)


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
        target_contract="CONTENT_ASSET",
    )


def _row_invalid_result(
    batch_id: str,
    row_reference: str,
    code: ReasonCode,
    summary: str,
    reference: str,
) -> BatchResult:
    return BatchResult(
        batch_id=batch_id,
        status=BatchStatus.REJECTED,
        rejected=(RejectedRecord(row_reference, code, summary, reference),),
        publish_eligible=False,
        summary=summary,
        batch_reason=code,
        target_contract="CONTENT_ASSET",
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
    if len(headers) != len(_REQUIRED) or set(headers) != _ALL_COLUMNS:
        raise ValueError("unsupported source columns or missing headers")
    if not data.rows:
        raise ValueError("empty input")
    if any(not isinstance(row, tuple) or len(row) != len(headers) for row in data.rows):
        raise ValueError("malformed row structure")
    if data.sheet_name is not None and not isinstance(data.sheet_name, str):
        raise ValueError("malformed tabular structure")
    return headers


def _known_sku_values(known_skus: Iterable[str]) -> tuple[frozenset[str], list[str]]:
    if isinstance(known_skus, (str, bytes, Mapping)):
        raise ValueError("known_skus must be an iterable of strings")
    values = tuple(known_skus)
    for sku in values:
        if not isinstance(sku, str):
            raise ValueError("known_skus must contain strings")
        require_valid_sku(sku)
    canonical = sorted(set(values))
    return frozenset(canonical), canonical


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _claims(value: object) -> list[str]:
    if not isinstance(value, str):
        raise ValueError("claim_fact_ids must be JSON array text")
    try:
        parsed = json.loads(value, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("invalid claim_fact_ids JSON") from exc
    if not isinstance(parsed, list):
        raise ValueError("claim_fact_ids JSON root must be an array")
    seen: set[str] = set()
    for fact_id in parsed:
        if not isinstance(fact_id, str) or not fact_id.strip():
            raise ValueError("claim_fact_ids must contain nonblank strings")
        require_valid_fact_id(fact_id)
        if fact_id in seen:
            raise ValueError("claim_fact_ids contains a duplicate")
        seen.add(fact_id)
    return parsed


def _mapping_payload(
    known_skus: list[str],
    product_fact_context: list[dict[str, Any]],
    *,
    mapping_strategy_version: str = _MAPPING_STRATEGY_VERSION,
    sku_strategy: str = _SKU_STRATEGY,
) -> dict[str, Any]:
    return {
        "known_skus": known_skus,
        "mapping_strategy_version": mapping_strategy_version,
        "product_fact_context": product_fact_context,
        "sku_strategy": sku_strategy,
    }


def _mapping_fingerprint(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping) or set(payload) != _MAPPING_KEYS:
        raise ValueError("invalid mapping payload keys")
    known_skus = payload["known_skus"]
    context = payload["product_fact_context"]
    if not isinstance(known_skus, list) or not all(isinstance(sku, str) for sku in known_skus):
        raise ValueError("invalid canonical known_skus")
    if known_skus != sorted(set(known_skus)):
        raise ValueError("known_skus must be sorted and deduplicated")
    for sku in known_skus:
        require_valid_sku(sku)
    if not isinstance(context, list):
        raise ValueError("invalid PRODUCT_FACT context")
    fact_ids: list[str] = []
    for fact in context:
        if not isinstance(fact, Mapping) or set(fact) != _FACT_CONTEXT_KEYS:
            raise ValueError("invalid PRODUCT_FACT context keys")
        require_valid_fact_id(fact["fact_id"])
        require_valid_sku(fact["sku"])
        if not isinstance(fact["fact_type"], str) or not fact["fact_type"]:
            raise ValueError("invalid PRODUCT_FACT fact_type")
        if not isinstance(fact["fact_value"], (dict, list)):
            raise ValueError("invalid PRODUCT_FACT fact_value")
        if fact["unit"] is not None and (not isinstance(fact["unit"], str) or not fact["unit"]):
            raise ValueError("invalid PRODUCT_FACT unit")
        if fact["verification_status"] not in {item.value for item in VerificationStatus}:
            raise ValueError("invalid PRODUCT_FACT verification_status")
        fact_ids.append(fact["fact_id"])
    if fact_ids != sorted(set(fact_ids)):
        raise ValueError("PRODUCT_FACT context must be sorted and unique")
    for key in ("mapping_strategy_version", "sku_strategy"):
        if not isinstance(payload[key], str) or not payload[key]:
            raise ValueError(f"invalid {key}")
    return payload_sha256(payload)


def _identity_payload(source_checksum: str, mapping_fingerprint: str) -> dict[str, str]:
    return {
        "target_contract": "CONTENT_ASSET",
        "schema_version": CONTENT_ASSET_SCHEMA,
        "source_checksum": source_checksum,
        "mapping_fingerprint": mapping_fingerprint,
    }


def _ingestion_identity(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping) or set(payload) != _IDENTITY_KEYS:
        raise ValueError("invalid ingestion identity payload keys")
    if not isinstance(payload["target_contract"], str) or not payload["target_contract"]:
        raise ValueError("invalid target_contract")
    if not isinstance(payload["schema_version"], str) or not payload["schema_version"]:
        raise ValueError("invalid schema_version")
    for key in ("source_checksum", "mapping_fingerprint"):
        value = payload[key]
        if not isinstance(value, str) or _CHECKSUM.fullmatch(value) is None:
            raise ValueError(f"invalid {key}")
    return payload_sha256(payload)


class _ReferenceError(ValueError):
    pass


def _product_fact_context(
    requested_by_sku: Mapping[str, set[str]],
    existing_facts: tuple[AcceptedRecord, ...],
    known_skus: frozenset[str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    context: list[dict[str, Any]] = []
    fact_sku_by_id: dict[str, str] = {}
    for fact_id in sorted(requested_by_sku):
        matches = [
            item
            for item in existing_facts
            if isinstance(item.validated_record, Mapping)
            and item.validated_record.get("fact_id") == fact_id
        ]
        if len(matches) != 1:
            raise _ReferenceError("referenced PRODUCT_FACT is missing or ambiguous")
        record = matches[0].validated_record
        try:
            require_valid_fact_id(record.get("fact_id"))
        except (TypeError, ValueError) as exc:
            raise _ReferenceError("referenced PRODUCT_FACT has invalid fact_id") from exc
        validate_contract("PRODUCT_FACT", record, known_skus=known_skus)
        sku = record.get("sku")
        if record.get("verification_status") != "VERIFIED":
            raise _ReferenceError("referenced PRODUCT_FACT is not VERIFIED")
        if not isinstance(sku, str) or requested_by_sku[fact_id] != {sku}:
            raise _ReferenceError("referenced PRODUCT_FACT belongs to another SKU")
        fact_sku_by_id[fact_id] = sku
        context.append(
            {
                "fact_id": record["fact_id"],
                "sku": record["sku"],
                "fact_type": record["fact_type"],
                "fact_value": record["fact_value"],
                "unit": record.get("unit"),
                "verification_status": record["verification_status"],
            }
        )
    return context, fact_sku_by_id


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid {field}")
    return value


def _asset_type(value: object) -> str:
    if not isinstance(value, str) or value not in {item.value for item in AssetType}:
        raise ValueError("invalid asset_type")
    return value


def _asset_checksum(value: object) -> str:
    if not isinstance(value, str) or _CHECKSUM.fullmatch(value) is None:
        raise ValueError("invalid checksum_sha256")
    return value


def _version(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("invalid version")
    return value


def _storage_uri(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("invalid storage_uri")
    return _safe_reference(value)


def _natural_key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(record[key] for key in ("sku", "asset_type", "storage_uri", "version"))


def _business_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sku": record["sku"],
        "asset_type": record["asset_type"],
        "title": record["title"],
        "mime_type": record["mime_type"],
        "storage_uri": record["storage_uri"],
        "checksum_sha256": record["checksum_sha256"],
        "version": record["version"],
        "generated_by": record["generated_by"],
        "claim_fact_ids": sorted(record["claim_fact_ids"]),
        "status": record["status"],
    }


def _safe_natural_key(raw: Mapping[str, Any], known_skus: frozenset[str]) -> tuple[Any, ...] | None:
    try:
        sku = raw.get("sku")
        if not isinstance(sku, str):
            return None
        require_valid_sku(sku)
        if sku not in known_skus:
            return None
        return (
            sku,
            _asset_type(raw.get("asset_type")),
            _storage_uri(raw.get("storage_uri")),
            _version(raw.get("version")),
        )
    except (TypeError, ValueError):
        return None


def ingest_content_asset(
    tool_result: ToolResult,
    *,
    run_id: str,
    known_skus: Iterable[str],
    clock: Callable[[], datetime],
    schema_version: str = CONTENT_ASSET_SCHEMA,
    existing: Iterable[AcceptedRecord] = (),
) -> BatchResult:
    """Convert a successful PHASE 3 result into immutable DRAFT CONTENT_ASSET records."""

    batch_id = (
        f"batch:{tool_result.request_id}" if hasattr(tool_result, "request_id") else "batch:invalid"
    )
    if not isinstance(tool_result, ToolResult):
        return _invalid_result(
            "batch:invalid", ReasonCode.INVALID_TOOL_RESULT, "invalid ToolResult"
        )
    if tool_result.status is not ToolStatus.SUCCESS:
        return _invalid_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, "ToolResult status is not SUCCESS"
        )
    if schema_version != CONTENT_ASSET_SCHEMA:
        return _invalid_result(batch_id, ReasonCode.UNSUPPORTED_SCHEMA, "unsupported schema")
    try:
        require_valid_run_id(run_id)
    except (TypeError, ValueError):
        return _invalid_result(batch_id, ReasonCode.INVALID_TOOL_RESULT, "invalid run_id")
    try:
        require_valid_task_id(tool_result.task_id)
    except (TypeError, ValueError):
        return _invalid_result(batch_id, ReasonCode.INVALID_TOOL_RESULT, "invalid task_id")
    if tool_result.run_id is not None and tool_result.run_id != run_id:
        return _invalid_result(
            batch_id,
            ReasonCode.INVALID_TOOL_RESULT,
            "ToolResult run_id does not match ingestion run_id",
        )
    try:
        known_sku_set, canonical_known_skus = _known_sku_values(known_skus)
    except Exception:
        return _invalid_result(batch_id, ReasonCode.INVALID_TOOL_RESULT, "invalid known_skus")

    if not isinstance(tool_result.source_metadata, SourceMetadata) or not isinstance(
        tool_result.raw_result, SensitiveBytes
    ):
        return _invalid_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, "ToolResult boundary is incomplete"
        )
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
    if not isinstance(tool_result.parsed_result, TabularData):
        return _invalid_result(
            batch_id, ReasonCode.INVALID_TOOL_RESULT, "parsed_result is not TabularData", reference
        )
    data = tool_result.parsed_result
    try:
        headers = _validate_tabular_structure(data)
    except (TypeError, ValueError) as exc:
        return _invalid_result(batch_id, ReasonCode.INVALID_ROW_SHAPE, str(exc), reference)

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
    existing_facts = tuple(item for item in previous if item.contract_name == "PRODUCT_FACT")
    existing_assets = tuple(item for item in previous if item.contract_name == "CONTENT_ASSET")

    parsed_claims: list[list[str]] = []
    requested_by_sku: dict[str, set[str]] = {}
    for index, values in enumerate(data.rows, start=2):
        row_reference = _row_ref(data, index)
        raw = dict(zip(headers, values, strict=True))
        try:
            claims = _claims(raw.get("claim_fact_ids"))
            parsed_claims.append(claims)
            if claims:
                sku = raw.get("sku")
                if not isinstance(sku, str):
                    raise ValueError("invalid source SKU")
                require_valid_sku(sku)
                if sku not in known_sku_set:
                    raise ValueError("source SKU is not registered")
                for fact_id in claims:
                    requested_by_sku.setdefault(fact_id, set()).add(sku)
        except (TypeError, ValueError):
            return _row_invalid_result(
                batch_id,
                row_reference,
                ReasonCode.INVALID_SOURCE_VALUE,
                "row claim context is invalid",
                reference,
            )
    try:
        fact_context, fact_sku_by_id = _product_fact_context(
            requested_by_sku, existing_facts, known_sku_set
        )
    except ContractValidationError:
        return _invalid_result(
            batch_id,
            ReasonCode.CONTRACT_VALIDATION_FAILED,
            "referenced PRODUCT_FACT failed Contract validation",
            reference,
        )
    except _ReferenceError:
        return _invalid_result(
            batch_id,
            ReasonCode.INVALID_SOURCE_VALUE,
            "referenced PRODUCT_FACT context is invalid",
            reference,
        )

    mapping_fingerprint = _mapping_fingerprint(_mapping_payload(canonical_known_skus, fact_context))
    ingestion_identity = _ingestion_identity(
        _identity_payload(metadata.checksum_sha256, mapping_fingerprint)
    )
    if any(item.provenance.ingestion_identity == ingestion_identity for item in existing_assets):
        return BatchResult(
            batch_id=batch_id,
            status=BatchStatus.DUPLICATE,
            publish_eligible=False,
            ingestion_identity=ingestion_identity,
            summary="source duplicate / idempotent no-op",
            batch_reason=ReasonCode.SOURCE_DUPLICATE,
            target_contract="CONTENT_ASSET",
        )

    try:
        created_at = clock()
        if not isinstance(created_at, datetime):
            raise ValueError("clock must return datetime")
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
    except Exception as exc:
        return _invalid_result(batch_id, ReasonCode.INVALID_TOOL_RESULT, str(exc), reference)

    seen: dict[tuple[Any, ...], AcceptedRecord] = {}
    for item in existing_assets:
        key = item.natural_key
        if (
            not isinstance(key, tuple)
            or not key
            or not isinstance(item.canonical_business_hash, str)
            or key in seen
        ):
            return _invalid_result(
                batch_id,
                ReasonCode.INVALID_TOOL_RESULT,
                "ambiguous existing CONTENT_ASSET state",
                reference,
            )
        try:
            hash(key)
        except TypeError:
            return _invalid_result(
                batch_id,
                ReasonCode.INVALID_TOOL_RESULT,
                "invalid existing CONTENT_ASSET key",
                reference,
            )
        seen[key] = item

    accepted: list[AcceptedRecord] = []
    rejected: list[RejectedRecord] = []
    duplicates: list[DuplicateRecord] = []
    conflicts: list[ConflictRecord] = []
    for offset, values in enumerate(data.rows):
        row_reference = _row_ref(data, offset + 2)
        raw = dict(zip(headers, values, strict=True))
        try:
            missing = [
                field
                for field in _REQUIRED
                if raw.get(field) is None
                or (isinstance(raw.get(field), str) and not raw.get(field).strip())
            ]
            if missing:
                raise _RowError(
                    ReasonCode.MISSING_REQUIRED_SOURCE_FIELD, "missing required source field"
                )
            sku = raw["sku"]
            if not isinstance(sku, str):
                raise ValueError("invalid sku")
            require_valid_sku(sku)
            if sku not in known_sku_set:
                raise _RowError(ReasonCode.UNREGISTERED_SKU, "SKU is not registered")
            storage_uri = _storage_uri(raw["storage_uri"])
            data_as_of = _parse_datetime(raw["data_as_of"])
            record: dict[str, Any] = {
                "sku": sku,
                "asset_type": _asset_type(raw["asset_type"]),
                "title": _text(raw["title"], "title"),
                "mime_type": _text(raw["mime_type"], "mime_type"),
                "storage_uri": storage_uri,
                "checksum_sha256": _asset_checksum(raw["checksum_sha256"]),
                "version": _version(raw["version"]),
                "generated_by": _text(raw["generated_by"], "generated_by"),
                "claim_fact_ids": parsed_claims[offset],
                "status": "DRAFT",
                "approved_by": None,
                "source": metadata.source,
                "run_id": run_id,
                "task_id": tool_result.task_id,
                "data_as_of": raw["data_as_of"],
                "created_at": created_at.isoformat(),
                "updated_at": created_at.isoformat(),
            }
            try:
                validate_schema_only(
                    "CONTENT_ASSET",
                    {"asset_id": "asset_00000000000000000000000000", **record},
                )
            except ContractValidationError as exc:
                raise _RowError(
                    ReasonCode.CONTRACT_VALIDATION_FAILED,
                    "row rejected by Contract Schema validation",
                ) from exc
            key = _natural_key(record)
            business_hash = payload_sha256(_business_payload(record))
        except _RowError as exc:
            rejected.append(
                RejectedRecord(
                    row_reference,
                    exc.code,
                    exc.summary,
                    reference,
                    _safe_natural_key(raw, known_sku_set),
                )
            )
            continue
        except (TypeError, ValueError) as exc:
            code = (
                ReasonCode.INVALID_DATA_AS_OF
                if "datetime" in str(exc).lower() or "timezone" in str(exc).lower()
                else ReasonCode.INVALID_SOURCE_VALUE
            )
            rejected.append(
                RejectedRecord(
                    row_reference,
                    code,
                    "row rejected by validation",
                    reference,
                    _safe_natural_key(raw, known_sku_set),
                )
            )
            continue

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
            normalization_rules_applied=(),
            target_contract="CONTENT_ASSET",
            natural_key=key,
            canonical_business_hash=business_hash,
        )
        prior = seen.get(key)
        if prior is not None:
            if prior.canonical_business_hash == business_hash:
                duplicates.append(
                    DuplicateRecord(row_reference, key, ReasonCode.BUSINESS_DUPLICATE, provenance)
                )
            else:
                conflicts.append(
                    ConflictRecord(row_reference, key, ReasonCode.NATURAL_KEY_CONFLICT, reference)
                )
            continue

        try:
            asset_id = generate_asset_id()
            require_valid_asset_id(asset_id)
        except Exception as exc:
            return _invalid_result(batch_id, ReasonCode.INVALID_TOOL_RESULT, str(exc), reference)
        record["asset_id"] = asset_id
        try:
            validate_contract(
                "CONTENT_ASSET",
                record,
                known_skus=known_sku_set,
                fact_sku_by_id=fact_sku_by_id,
            )
        except ContractValidationError:
            rejected.append(
                RejectedRecord(
                    row_reference,
                    ReasonCode.CONTRACT_VALIDATION_FAILED,
                    "row rejected by validation",
                    reference,
                    key,
                )
            )
            continue
        candidate = AcceptedRecord("CONTENT_ASSET", record, key, business_hash, provenance)
        seen[key] = candidate
        accepted.append(candidate)

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
        target_contract="CONTENT_ASSET",
    )


class _RowError(ValueError):
    def __init__(self, code: ReasonCode, summary: str) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary
