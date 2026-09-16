from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from topspeed_ai_os.core.canonical import (
    CanonicalizationError,
    canonical_json,
    payload_sha256,
    verify_payload_hash,
)


def test_canonical_json_is_key_order_independent():
    left = {"b": 2, "a": {"y": 2, "x": 1}}
    right = {"a": {"x": 1, "y": 2}, "b": 2}
    assert canonical_json(left) == canonical_json(right)
    assert payload_sha256(left) == payload_sha256(right)


def test_canonical_json_handles_exact_decimal_and_timezone():
    payload = {
        "amount": Decimal("12900.00"),
        "at": datetime(2026, 9, 16, 0, 0, tzinfo=UTC),
        "title": "탑스피드",
    }
    output = canonical_json(payload).decode("utf-8")
    assert '"amount":"12900.00"' in output
    assert '"at":"2026-09-16T00:00:00+00:00"' in output
    assert "탑스피드" in output


def test_payload_tampering_is_detected():
    payload = {"daily_budget": 300000, "campaign_id": "cmp_123"}
    digest = payload_sha256(payload)
    assert verify_payload_hash(payload, digest)
    assert not verify_payload_hash({**payload, "daily_budget": 300001}, digest)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), Decimal("NaN")])
def test_non_finite_numbers_are_rejected(value):
    with pytest.raises(CanonicalizationError):
        canonical_json({"value": value})


def test_naive_datetime_is_rejected_by_canonicalizer():
    with pytest.raises(CanonicalizationError):
        canonical_json({"at": datetime(2026, 9, 16, 0, 0)})
