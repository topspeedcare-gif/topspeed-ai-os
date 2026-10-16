"""Canonical policy authority carrier for inventory safety stock."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from topspeed_ai_os.core.canonical import payload_sha256

_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_POLICY_VERSION = "TOPSPEED_SAFETY_STOCK_POLICY_V1"
_APPROVAL_AUTHORITY = "TOPSPEED Human Architecture Owner"
_SOURCE = "topspeed.repository.policy_authority.inventory_safety_stock.v1"
_DATA_AS_OF = "2026-10-15T16:05:35+09:00"
_POLICY_HASH = "sha256:c1960068c6bb5a527c826bd1bbea6a2c021d29b3b9f439b2f77033bd1b20ba2a"


def _policy_payload(
    policy_version: str,
    approval_authority: str,
    authority_reference: str,
    authority_status: str,
    source: str,
    data_as_of: str,
    safety_stock_days: int,
) -> dict[str, object]:
    return {
        "policy_version": policy_version,
        "approval_authority": approval_authority,
        "authority_reference": authority_reference,
        "authority_status": authority_status,
        "source": source,
        "data_as_of": data_as_of,
        "safety_stock_days": safety_stock_days,
    }


def _validate_data_as_of(value: str) -> None:
    if value != _DATA_AS_OF:
        raise ValueError("data_as_of must equal the approved V1 value")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("data_as_of must be a real Gregorian datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("data_as_of must include a timezone")
    if parsed.isoformat() != value:
        raise ValueError("data_as_of must round-trip canonically")


@dataclass(frozen=True, slots=True)
class InventorySafetyStockPolicyAuthority:
    """Immutable, validated V1 policy authority projection."""

    policy_version: str
    approval_authority: str
    authority_reference: str
    authority_status: Literal["APPROVED"]
    source: str
    data_as_of: str
    safety_stock_days: int
    input_hash: str

    def __post_init__(self) -> None:
        for field, value in (
            ("policy_version", self.policy_version),
            ("approval_authority", self.approval_authority),
            ("authority_reference", self.authority_reference),
            ("authority_status", self.authority_status),
            ("source", self.source),
            ("data_as_of", self.data_as_of),
            ("input_hash", self.input_hash),
        ):
            if type(value) is not str:
                raise TypeError(f"{field} must be an exact str")
        if type(self.safety_stock_days) is not int:
            raise TypeError("safety_stock_days must be an exact int")
        if self.policy_version != _POLICY_VERSION:
            raise ValueError("unsupported policy_version")
        if self.approval_authority != _APPROVAL_AUTHORITY:
            raise ValueError("unsupported approval_authority")
        if self.authority_reference != _POLICY_VERSION:
            raise ValueError("unsupported authority_reference")
        if self.authority_status != "APPROVED":
            raise ValueError("authority_status must be APPROVED")
        if not self.source:
            raise ValueError("source must be non-empty")
        _validate_data_as_of(self.data_as_of)
        if self.safety_stock_days != 7:
            raise ValueError("safety_stock_days must equal 7")
        if _HASH_PATTERN.fullmatch(self.input_hash) is None:
            raise ValueError("input_hash must be canonical lowercase sha256")
        expected_hash = payload_sha256(
            _policy_payload(
                self.policy_version,
                self.approval_authority,
                self.authority_reference,
                self.authority_status,
                self.source,
                self.data_as_of,
                self.safety_stock_days,
            )
        )
        if self.input_hash != expected_hash or self.input_hash != _POLICY_HASH:
            raise ValueError("input_hash does not match the approved policy payload")
