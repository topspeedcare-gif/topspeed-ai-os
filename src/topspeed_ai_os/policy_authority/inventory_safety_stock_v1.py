"""Repository-owned immutable V1 inventory safety stock policy authority."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from datetime import datetime

from topspeed_ai_os.calculation.inventory_safety_stock import (
    InventorySafetyStockPolicyAuthority,
)
from topspeed_ai_os.core.canonical import payload_sha256

_POLICY_VERSION = "TOPSPEED_SAFETY_STOCK_POLICY_V1"
_APPROVAL_AUTHORITY = "TOPSPEED Human Architecture Owner"
_SOURCE = "topspeed.repository.policy_authority.inventory_safety_stock.v1"
_DATA_AS_OF = "2026-10-15T16:05:35+09:00"
_POLICY_HASH = "sha256:c1960068c6bb5a527c826bd1bbea6a2c021d29b3b9f439b2f77033bd1b20ba2a"
_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_RECORD_FIELDS = (
    "policy_version",
    "approval_authority",
    "authority_reference",
    "authority_status",
    "source",
    "data_as_of",
    "safety_stock_days",
    "input_hash",
)


@dataclass(frozen=True, slots=True)
class _InventorySafetyStockPolicyRecord:
    policy_version: str
    approval_authority: str
    authority_reference: str
    authority_status: str
    source: str
    data_as_of: str
    safety_stock_days: int
    input_hash: str


_POLICY_RECORD = _InventorySafetyStockPolicyRecord(
    policy_version=_POLICY_VERSION,
    approval_authority=_APPROVAL_AUTHORITY,
    authority_reference=_POLICY_VERSION,
    authority_status="APPROVED",
    source=_SOURCE,
    data_as_of=_DATA_AS_OF,
    safety_stock_days=7,
    input_hash=_POLICY_HASH,
)


def _producer_payload(record: _InventorySafetyStockPolicyRecord) -> dict[str, object]:
    return {
        "policy_version": record.policy_version,
        "approval_authority": record.approval_authority,
        "authority_reference": record.authority_reference,
        "authority_status": record.authority_status,
        "source": record.source,
        "data_as_of": record.data_as_of,
        "safety_stock_days": record.safety_stock_days,
    }


def _produce_inventory_safety_stock_policy_authority() -> InventorySafetyStockPolicyAuthority:
    record = _POLICY_RECORD
    if type(record) is not _InventorySafetyStockPolicyRecord:
        raise TypeError("_POLICY_RECORD must have exact private record identity")
    if tuple(field.name for field in fields(record)) != _RECORD_FIELDS:
        raise TypeError("policy record fields or order are invalid")
    if type(record.policy_version) is not str:
        raise TypeError("policy_version must be an exact str")
    if record.policy_version != _POLICY_VERSION:
        raise ValueError("unsupported policy_version")
    if type(record.approval_authority) is not str:
        raise TypeError("approval_authority must be an exact str")
    if record.approval_authority != _APPROVAL_AUTHORITY:
        raise ValueError("unsupported approval_authority")
    if type(record.authority_reference) is not str:
        raise TypeError("authority_reference must be an exact str")
    if record.authority_reference != _POLICY_VERSION:
        raise ValueError("unsupported authority_reference")
    if type(record.authority_status) is not str:
        raise TypeError("authority_status must be an exact str")
    if record.authority_status != "APPROVED":
        raise ValueError("authority_status must be APPROVED")
    if type(record.source) is not str:
        raise TypeError("source must be an exact str")
    if not record.source or record.source != _SOURCE:
        raise ValueError("source must equal the approved source")
    if type(record.data_as_of) is not str:
        raise TypeError("data_as_of must be an exact str")
    if record.data_as_of != _DATA_AS_OF:
        raise ValueError("data_as_of must equal the approved V1 value")
    try:
        parsed = datetime.fromisoformat(record.data_as_of)
    except ValueError as exc:
        raise ValueError("data_as_of must be a real Gregorian datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("data_as_of must include a timezone")
    if parsed.isoformat() != record.data_as_of:
        raise ValueError("data_as_of must round-trip canonically")
    if type(record.safety_stock_days) is not int:
        raise TypeError("safety_stock_days must be an exact int")
    if record.safety_stock_days != 7:
        raise ValueError("safety_stock_days must equal 7")
    if type(record.input_hash) is not str:
        raise TypeError("input_hash must be an exact str")
    if _HASH_PATTERN.fullmatch(record.input_hash) is None:
        raise ValueError("input_hash must be canonical lowercase sha256")
    recomputed = payload_sha256(_producer_payload(record))
    if record.input_hash != recomputed:
        raise ValueError("input_hash does not match the approved policy payload")

    produced = InventorySafetyStockPolicyAuthority(
        policy_version=record.policy_version,
        approval_authority=record.approval_authority,
        authority_reference=record.authority_reference,
        authority_status=record.authority_status,
        source=record.source,
        data_as_of=record.data_as_of,
        safety_stock_days=record.safety_stock_days,
        input_hash=record.input_hash,
    )
    if type(produced) is not InventorySafetyStockPolicyAuthority:
        raise TypeError("producer returned an unexpected carrier identity")
    if tuple(getattr(produced, name) for name in _RECORD_FIELDS) != tuple(
        getattr(record, name) for name in _RECORD_FIELDS
    ):
        raise ValueError("producer projection does not match policy record")
    return produced
