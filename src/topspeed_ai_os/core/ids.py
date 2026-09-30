"""Creation and validation of stable TOPSPEED identifiers."""

from __future__ import annotations

import re
import secrets
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_PATTERN = r"[0-7][0-9A-HJKMNP-TV-Z]{25}"
_PREFIX_PATTERNS = {
    "task": re.compile(rf"^task_{_ULID_PATTERN}$"),
    "run": re.compile(rf"^run_{_ULID_PATTERN}$"),
    "apr": re.compile(rf"^apr_{_ULID_PATTERN}$"),
    "idem": re.compile(rf"^idem_{_ULID_PATTERN}$"),
    "fact": re.compile(rf"^fact_{_ULID_PATTERN}$"),
}
_SKU_PATTERN = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)+$")
_SKU_SEGMENT_CLEANER = re.compile(r"[^A-Z0-9]+")


class InvalidIdentifierError(ValueError):
    """Raised when an identifier does not match its contract."""


def _encode_crockford(value: int, length: int) -> str:
    chars = ["0"] * length
    for index in range(length - 1, -1, -1):
        chars[index] = _CROCKFORD[value & 31]
        value >>= 5
    if value:
        raise ValueError("value does not fit requested Crockford length")
    return "".join(chars)


def _generate_ulid() -> str:
    timestamp_ms = time.time_ns() // 1_000_000
    if timestamp_ms >= 1 << 48:
        raise OverflowError("timestamp exceeds ULID 48-bit range")
    randomness = int.from_bytes(secrets.token_bytes(10), "big")
    return _encode_crockford((timestamp_ms << 80) | randomness, 26)


def _generate_prefixed(prefix: str) -> str:
    return f"{prefix}_{_generate_ulid()}"


def _validate_prefixed(value: object, prefix: str) -> bool:
    return isinstance(value, str) and _PREFIX_PATTERNS[prefix].fullmatch(value) is not None


def generate_task_id() -> str:
    return _generate_prefixed("task")


def generate_run_id() -> str:
    return _generate_prefixed("run")


def generate_approval_id() -> str:
    return _generate_prefixed("apr")


def generate_idempotency_key() -> str:
    return _generate_prefixed("idem")


def generate_fact_id() -> str:
    return _generate_prefixed("fact")


def generate_sku(*segments: str) -> str:
    """Build an internal SKU from at least two explicit, non-empty segments."""

    normalized = [
        _SKU_SEGMENT_CLEANER.sub("-", segment.strip().upper()).strip("-") for segment in segments
    ]
    if len(normalized) < 2 or any(not segment for segment in normalized):
        raise InvalidIdentifierError("SKU requires at least two non-empty segments")
    sku = "-".join(normalized)
    require_valid_sku(sku)
    return sku


def validate_task_id(value: object) -> bool:
    return _validate_prefixed(value, "task")


def validate_run_id(value: object) -> bool:
    return _validate_prefixed(value, "run")


def validate_approval_id(value: object) -> bool:
    return _validate_prefixed(value, "apr")


def validate_idempotency_key(value: object) -> bool:
    return _validate_prefixed(value, "idem")


def validate_fact_id(value: object) -> bool:
    return _validate_prefixed(value, "fact")


def validate_sku(value: object) -> bool:
    return isinstance(value, str) and _SKU_PATTERN.fullmatch(value) is not None


def _require(value: str, predicate: object, label: str) -> str:
    if not callable(predicate) or not predicate(value):
        raise InvalidIdentifierError(f"invalid {label}: {value!r}")
    return value


def require_valid_task_id(value: str) -> str:
    return _require(value, validate_task_id, "task_id")


def require_valid_run_id(value: str) -> str:
    return _require(value, validate_run_id, "run_id")


def require_valid_approval_id(value: str) -> str:
    return _require(value, validate_approval_id, "approval_id")


def require_valid_idempotency_key(value: str) -> str:
    return _require(value, validate_idempotency_key, "idempotency_key")


def require_valid_fact_id(value: str) -> str:
    return _require(value, validate_fact_id, "fact_id")


def require_valid_sku(value: str) -> str:
    return _require(value, validate_sku, "sku")
