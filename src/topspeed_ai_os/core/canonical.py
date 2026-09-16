"""Deterministic payload serialization and SHA-256 verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class CanonicalizationError(ValueError):
    """Raised when a payload cannot be represented deterministically."""


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError("NaN and Infinity are not allowed")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CanonicalizationError("non-finite Decimal is not allowed")
        normalized = format(value, "f")
        if Decimal(normalized) == 0:
            normalized = "0"
        return normalized
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CanonicalizationError("datetime must include a timezone")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalizationError("JSON object keys must be strings")
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize(item) for item in value]
    raise CanonicalizationError(f"unsupported payload value: {type(value).__name__}")


def canonical_json(payload: Any) -> bytes:
    """Return UTF-8 canonical JSON with stable key order and no insignificant whitespace."""

    normalized = _normalize(payload)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def payload_sha256(payload: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_json(payload)).hexdigest()}"


def verify_payload_hash(payload: Any, expected_hash: str) -> bool:
    if not isinstance(expected_hash, str):
        return False
    return hmac.compare_digest(payload_sha256(payload), expected_hash)
