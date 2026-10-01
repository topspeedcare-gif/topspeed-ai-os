"""Published-schema validation and canonical hashing for workflow state."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, SchemaError

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "architecture"
    / "schemas"
    / "development_workflow_state_v1.schema.json"
)

_IDEMPOTENCY_FIELDS = (
    "schema_version",
    "workflow_run_id",
    "work_item_id",
    "stage",
    "actor",
    "approved_work_order_sha256",
    "pre_stage_sha",
)
_SCOPE_FIELDS = (
    "schema_version",
    "work_item_id",
    "approved_work_order_id",
    "approved_work_order_sha256",
    "baseline_sha",
    "phase",
    "slice",
    "allowed_paths",
    "allowed_operation_classes",
)
_STAGES = frozenset(
    {
        "AUDIT1_DRAFT",
        "AUDIT2_WORK_ORDER_REVIEW",
        "BUILDER_IMPLEMENTATION",
        "AUDIT1_IMPLEMENTATION_AUDIT",
        "AUDIT2_IMPLEMENTATION_REAUDIT",
        "PUBLICATION_READY",
    }
)
_OPERATION_CLASSES = frozenset(
    {
        "DOC_WRITE",
        "SOURCE_WRITE",
        "TEST_WRITE",
        "CONFIG_WRITE",
        "LOCAL_COMMIT",
        "READ_ONLY_VALIDATION",
    }
)
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DRIVE_PATH = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True, slots=True, order=True)
class ValidationDiagnostic:
    """One stable, implementation-local validation diagnostic."""

    path: str
    rule: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Structured validation outcome with deterministic diagnostic order."""

    is_valid: bool
    errors: tuple[ValidationDiagnostic, ...]

    @property
    def valid(self) -> bool:
        return self.is_valid


def _format_path(path: Sequence[object]) -> str:
    if not path:
        return "$"
    value = "$"
    for part in path:
        value += f"[{part}]" if isinstance(part, int) else f".{part}"
    return value


def _error_key(error: Any) -> tuple[tuple[tuple[str, str], ...], str, str, str]:
    path = tuple((type(part).__name__, str(part)) for part in error.absolute_path)
    schema_path = "/".join(str(part) for part in error.absolute_schema_path)
    return path, str(error.validator), schema_path, error.message


def _load_schema(schema_path: Path) -> Mapping[str, Any]:
    with schema_path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    if not isinstance(schema, Mapping):
        raise SchemaError("published schema root must be an object")
    return schema


def validate_workflow_state(
    state: object,
) -> ValidationResult:
    """Validate state without mutating it, using the published Draft 2020-12 schema."""

    diagnostics: list[ValidationDiagnostic] = []
    try:
        selected_schema = _load_schema(_SCHEMA_PATH.resolve())
        Draft202012Validator.check_schema(selected_schema)
        validator = Draft202012Validator(selected_schema, format_checker=FormatChecker())
    except (OSError, json.JSONDecodeError, SchemaError, ValueError, TypeError) as exc:
        diagnostics.append(
            ValidationDiagnostic("$schema", "SCHEMA_INVALID", f"{type(exc).__name__}: {exc}")
        )
        return ValidationResult(False, tuple(diagnostics))

    for error in sorted(validator.iter_errors(state), key=_error_key):
        diagnostics.append(
            ValidationDiagnostic(
                _format_path(tuple(error.absolute_path)),
                str(error.validator),
                error.message,
            )
        )
    return ValidationResult(not diagnostics, tuple(diagnostics))


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _require_field(source: Mapping[str, Any], field: str) -> Any:
    if field not in source:
        raise ValueError(f"missing required canonical field: {field}")
    return source[field]


def _require_non_empty_string(field: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _require_pattern(field: str, value: object, pattern: re.Pattern[str]) -> str:
    text = _require_non_empty_string(field, value)
    if pattern.fullmatch(text) is None:
        raise ValueError(f"{field} has an invalid format")
    return text


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compute_idempotency_key(canonical_source: Mapping[str, Any]) -> str:
    """Hash exactly the published replay inputs; ``attempt`` and other fields are excluded."""

    source = _require_mapping(canonical_source, "idempotency input")
    values = {field: _require_field(source, field) for field in _IDEMPOTENCY_FIELDS}
    for field in ("workflow_run_id", "work_item_id", "actor"):
        values[field] = _require_non_empty_string(field, values[field])
    if values["schema_version"] != "development_workflow_state.v1":
        raise ValueError("schema_version is not the published V1 value")
    if values["stage"] not in _STAGES:
        raise ValueError("stage is not a published value")
    values["approved_work_order_sha256"] = _require_pattern(
        "approved_work_order_sha256", values["approved_work_order_sha256"], _SHA256
    )
    values["pre_stage_sha"] = _require_pattern("pre_stage_sha", values["pre_stage_sha"], _SHA1)
    return _canonical_sha256(values)


def _is_safe_path(path: str) -> bool:
    return (
        bool(path)
        and not path.startswith("/")
        and _DRIVE_PATH.match(path) is None
        and "\\" not in path
        and "\r" not in path
        and "\n" not in path
        and "//" not in path
        and ".." not in path.split("/")
    )


def _canonical_string_array(field: str, value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be an array")
    items: list[str] = []
    for item in value:
        items.append(_require_non_empty_string(field, item))
    return sorted(set(items))


def compute_scope_hash(canonical_source: Mapping[str, Any]) -> str:
    """Hash the exact normalized Work Order scope defined by the published contract."""

    source = _require_mapping(canonical_source, "scope input")
    values = {field: _require_field(source, field) for field in _SCOPE_FIELDS}
    for field in ("work_item_id", "approved_work_order_id", "phase"):
        values[field] = _require_non_empty_string(field, values[field])
    if values["schema_version"] != "development_workflow_state.v1":
        raise ValueError("schema_version is not the published V1 value")
    if values["slice"] is not None:
        values["slice"] = _require_non_empty_string("slice", values["slice"])
    values["approved_work_order_sha256"] = _require_pattern(
        "approved_work_order_sha256", values["approved_work_order_sha256"], _SHA256
    )
    values["baseline_sha"] = _require_pattern("baseline_sha", values["baseline_sha"], _SHA1)

    paths = _canonical_string_array("allowed_paths", values["allowed_paths"])
    invalid_paths = [path for path in paths if not _is_safe_path(path)]
    if invalid_paths:
        raise ValueError(f"allowed_paths contains an unsafe path: {invalid_paths[0]}")
    operation_classes = _canonical_string_array(
        "allowed_operation_classes", values["allowed_operation_classes"]
    )
    invalid_classes = [item for item in operation_classes if item not in _OPERATION_CLASSES]
    if invalid_classes:
        raise ValueError(
            f"allowed_operation_classes contains an unpublished value: {invalid_classes[0]}"
        )
    values["allowed_paths"] = paths
    values["allowed_operation_classes"] = operation_classes
    return _canonical_sha256(values)
