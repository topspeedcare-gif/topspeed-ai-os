"""Logical type validators shared by every Data Contract v1 schema."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

DECIMAL_PATTERN = r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"
_DECIMAL_RE = re.compile(DECIMAL_PATTERN)


class InvalidDecimalError(ValueError):
    """Raised when an external DECIMAL is not a canonical decimal string."""


def parse_canonical_decimal(value: object) -> Decimal:
    """Parse the only supported external DECIMAL representation.

    Contract DECIMAL values are plain JSON strings. JSON numbers, exponent notation,
    non-finite values, leading-zero forms, and decorated amounts are rejected.
    """

    if not isinstance(value, str) or _DECIMAL_RE.fullmatch(value) is None:
        raise InvalidDecimalError("must be a canonical decimal string")
    try:
        decimal_value = Decimal(value)
    except InvalidOperation as exc:  # Defensive: the regular expression is authoritative.
        raise InvalidDecimalError("must be a canonical decimal string") from exc
    if not decimal_value.is_finite():
        raise InvalidDecimalError("must be finite")
    return decimal_value


def is_canonical_decimal(value: object) -> bool:
    try:
        parse_canonical_decimal(value)
    except InvalidDecimalError:
        return False
    return True
