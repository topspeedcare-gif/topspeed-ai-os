from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from inspect import signature

import pytest

from topspeed_ai_os import policy_authority
from topspeed_ai_os.calculation import __all__ as calculation_all
from topspeed_ai_os.calculation.inventory_safety_stock import (
    InventorySafetyStockPolicyAuthority,
)
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.policy_authority import inventory_safety_stock_v1 as producer_module

_EXPECTED_HASH = "sha256:c1960068c6bb5a527c826bd1bbea6a2c021d29b3b9f439b2f77033bd1b20ba2a"
_EXPECTED_NAMES = (
    "policy_version",
    "approval_authority",
    "authority_reference",
    "authority_status",
    "source",
    "data_as_of",
    "safety_stock_days",
    "input_hash",
)
_APPROVED_VALUES = {
    "policy_version": "TOPSPEED_SAFETY_STOCK_POLICY_V1",
    "approval_authority": "TOPSPEED Human Architecture Owner",
    "authority_reference": "TOPSPEED_SAFETY_STOCK_POLICY_V1",
    "authority_status": "APPROVED",
    "source": "topspeed.repository.policy_authority.inventory_safety_stock.v1",
    "data_as_of": "2026-10-15T16:05:35+09:00",
    "safety_stock_days": 7,
    "input_hash": _EXPECTED_HASH,
}


def _carrier(**overrides: object) -> InventorySafetyStockPolicyAuthority:
    return InventorySafetyStockPolicyAuthority(**(_APPROVED_VALUES | overrides))


def test_carrier_is_canonical_frozen_slotted_and_has_exact_fields() -> None:
    assert tuple(field.name for field in fields(InventorySafetyStockPolicyAuthority)) == (
        *_EXPECTED_NAMES,
    )
    authority = _carrier()
    assert type(authority) is InventorySafetyStockPolicyAuthority
    assert not hasattr(authority, "__dict__")
    with pytest.raises(FrozenInstanceError):
        authority.source = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value", "exception"),
    [
        ("policy_version", "OTHER", ValueError),
        ("approval_authority", "Other Owner", ValueError),
        ("authority_reference", "OTHER", ValueError),
        ("authority_status", "PENDING", ValueError),
        ("source", "", ValueError),
        ("data_as_of", "2026-10-15T16:04:23+09:00", ValueError),
        ("data_as_of", "2026-10-15T16:05:35", ValueError),
        ("data_as_of", "not-a-date", ValueError),
        ("safety_stock_days", 8, ValueError),
        ("safety_stock_days", True, TypeError),
        ("input_hash", "sha256:" + "A" * 64, ValueError),
        ("input_hash", "sha256:" + "0" * 64, ValueError),
        (
            "policy_version",
            type("StrChild", (str,), {})(_APPROVED_VALUES["policy_version"]),
            TypeError,
        ),
        ("safety_stock_days", type("IntChild", (int,), {})(7), TypeError),
    ],
)
def test_carrier_rejects_invalid_values(
    field: str, value: object, exception: type[Exception]
) -> None:
    with pytest.raises(exception):
        _carrier(**{field: value})


def test_carrier_hash_uses_exact_approved_payload() -> None:
    payload = {key: value for key, value in _APPROVED_VALUES.items() if key != "input_hash"}
    assert payload_sha256(payload) == _EXPECTED_HASH
    assert _carrier().input_hash == _EXPECTED_HASH


def test_producer_record_and_signature_are_exact_and_internal() -> None:
    record = producer_module._POLICY_RECORD
    assert tuple(field.name for field in fields(type(record))) == _EXPECTED_NAMES
    assert type(record).__name__ == "_InventorySafetyStockPolicyRecord"
    assert not hasattr(record, "__dict__")
    assert (
        signature(producer_module._produce_inventory_safety_stock_policy_authority).parameters == {}
    )
    assert record.data_as_of == "2026-10-15T16:05:35+09:00"
    assert record.input_hash == _EXPECTED_HASH
    assert not hasattr(policy_authority, "_POLICY_RECORD")
    assert not hasattr(policy_authority, "_produce_inventory_safety_stock_policy_authority")
    assert "InventorySafetyStockPolicyAuthority" not in policy_authority.__dict__
    assert not any(name.startswith("INVENTORY_SAFETY_STOCK") for name in calculation_all)
    assert "InventorySafetyStockPolicyAuthority" not in calculation_all


def test_producer_returns_fresh_exact_equal_carriers() -> None:
    first = producer_module._produce_inventory_safety_stock_policy_authority()
    second = producer_module._produce_inventory_safety_stock_policy_authority()
    assert type(first) is InventorySafetyStockPolicyAuthority
    assert first == second
    assert first is not second
    assert tuple(getattr(first, name) for name in _EXPECTED_NAMES) == tuple(
        _APPROVED_VALUES[name] for name in _EXPECTED_NAMES
    )


def test_producer_rejects_tampered_record_and_propagates_hash_errors(monkeypatch) -> None:
    original = producer_module._POLICY_RECORD
    values = {name: getattr(original, name) for name in _EXPECTED_NAMES}
    values["input_hash"] = "sha256:" + "0" * 64
    monkeypatch.setattr(
        producer_module,
        "_POLICY_RECORD",
        producer_module._InventorySafetyStockPolicyRecord(**values),
    )
    with pytest.raises(ValueError):
        producer_module._produce_inventory_safety_stock_policy_authority()


def test_producer_requires_exact_record_identity(monkeypatch) -> None:
    monkeypatch.setattr(producer_module, "_POLICY_RECORD", object())
    with pytest.raises(TypeError, match="exact private record identity"):
        producer_module._produce_inventory_safety_stock_policy_authority()


def test_producer_requires_exact_record_fields_and_order(monkeypatch) -> None:
    monkeypatch.setattr(producer_module, "fields", lambda record: ())
    with pytest.raises(TypeError, match="fields or order"):
        producer_module._produce_inventory_safety_stock_policy_authority()


@pytest.mark.parametrize(
    ("first_field", "first_value", "next_field", "next_value", "expected"),
    [
        ("policy_version", "OTHER", "approval_authority", None, ValueError),
        ("approval_authority", "OTHER", "authority_reference", None, ValueError),
        ("authority_reference", "OTHER", "authority_status", None, ValueError),
        ("authority_status", "PENDING", "source", None, ValueError),
        ("source", "", "data_as_of", None, ValueError),
        ("data_as_of", "2026-10-15T16:04:23+09:00", "safety_stock_days", None, ValueError),
        ("safety_stock_days", 8, "input_hash", None, ValueError),
        ("policy_version", None, "approval_authority", "OTHER", TypeError),
        ("approval_authority", None, "authority_reference", "OTHER", TypeError),
        ("authority_reference", None, "authority_status", "PENDING", TypeError),
        ("authority_status", None, "source", "", TypeError),
        ("source", None, "data_as_of", "bad", TypeError),
        ("data_as_of", None, "safety_stock_days", True, TypeError),
        ("safety_stock_days", True, "input_hash", None, TypeError),
    ],
)
def test_producer_stops_at_higher_precedence_combined_fault(
    monkeypatch,
    first_field: str,
    first_value: object,
    next_field: str,
    next_value: object,
    expected: type[Exception],
) -> None:
    original = producer_module._POLICY_RECORD
    changes = {first_field: first_value}
    changes[next_field] = next_value
    monkeypatch.setattr(producer_module, "_POLICY_RECORD", replace(original, **changes))
    with pytest.raises(expected):
        producer_module._produce_inventory_safety_stock_policy_authority()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("policy_version", 1),
        ("approval_authority", 1),
        ("authority_reference", 1),
        ("authority_status", 1),
        ("source", 1),
        ("data_as_of", 1),
        ("input_hash", 1),
        ("policy_version", type("StrChild", (str,), {})(_APPROVED_VALUES["policy_version"])),
        (
            "approval_authority",
            type("StrChild", (str,), {})(_APPROVED_VALUES["approval_authority"]),
        ),
        (
            "authority_reference",
            type("StrChild", (str,), {})(_APPROVED_VALUES["authority_reference"]),
        ),
        ("authority_status", type("StrChild", (str,), {})("APPROVED")),
        ("source", type("StrChild", (str,), {})(_APPROVED_VALUES["source"])),
        ("data_as_of", type("StrChild", (str,), {})(_APPROVED_VALUES["data_as_of"])),
        ("input_hash", type("StrChild", (str,), {})(_EXPECTED_HASH)),
        ("safety_stock_days", 7.0),
        ("safety_stock_days", type("IntChild", (int,), {})(7)),
        ("safety_stock_days", True),
    ],
)
def test_producer_enforces_exact_builtin_field_types(
    monkeypatch, field: str, value: object
) -> None:
    record = replace(producer_module._POLICY_RECORD, **{field: value})
    monkeypatch.setattr(producer_module, "_POLICY_RECORD", record)
    with pytest.raises(TypeError):
        producer_module._produce_inventory_safety_stock_policy_authority()


@pytest.mark.parametrize(
    "value",
    [
        "not-a-date",
        "2026-10-15T16:05:35",
        "2026-10-15T16:05:35.000000+09:00",
        "2026-10-15T16:04:23+09:00",
    ],
)
def test_producer_rejects_invalid_approved_datetime(monkeypatch, value: str) -> None:
    monkeypatch.setattr(
        producer_module,
        "_POLICY_RECORD",
        replace(producer_module._POLICY_RECORD, data_as_of=value),
    )
    with pytest.raises(ValueError):
        producer_module._produce_inventory_safety_stock_policy_authority()


def test_producer_preserves_step_19_hash_exception(monkeypatch) -> None:
    error = ValueError("canonical hash sentinel")

    def fail_hash(payload):
        raise error

    monkeypatch.setattr(producer_module, "payload_sha256", fail_hash)
    with pytest.raises(ValueError) as raised:
        producer_module._produce_inventory_safety_stock_policy_authority()
    assert raised.value is error


def test_producer_preserves_step_21_carrier_constructor_exception(monkeypatch) -> None:
    error = TypeError("carrier constructor sentinel")

    def fail_constructor(**kwargs):
        raise error

    monkeypatch.setattr(producer_module, "InventorySafetyStockPolicyAuthority", fail_constructor)
    with pytest.raises(TypeError) as raised:
        producer_module._produce_inventory_safety_stock_policy_authority()
    assert raised.value is error


def test_producer_rejects_wrong_step_22_carrier_identity(monkeypatch) -> None:
    monkeypatch.setattr(
        producer_module, "InventorySafetyStockPolicyAuthority", lambda **kwargs: object()
    )
    with pytest.raises(TypeError, match="unexpected carrier identity"):
        producer_module._produce_inventory_safety_stock_policy_authority()


def test_producer_rejects_step_22_projection_mismatch(monkeypatch) -> None:
    canonical = InventorySafetyStockPolicyAuthority

    class AlternateCarrier(canonical):
        __slots__ = ()

        def __post_init__(self) -> None:
            pass

        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            object.__setattr__(self, "source", "alternate.source")

    monkeypatch.setattr(producer_module, "InventorySafetyStockPolicyAuthority", AlternateCarrier)
    with pytest.raises(ValueError, match="projection"):
        producer_module._produce_inventory_safety_stock_policy_authority()


def test_private_policy_record_is_frozen_slotted_and_has_no_extra_state() -> None:
    record = producer_module._POLICY_RECORD
    assert tuple(field.name for field in fields(record)) == _EXPECTED_NAMES
    assert tuple(type(record).__dataclass_fields__) == _EXPECTED_NAMES
    assert not hasattr(record, "__dict__")
    with pytest.raises(FrozenInstanceError):
        record.source = "changed"  # type: ignore[misc]
