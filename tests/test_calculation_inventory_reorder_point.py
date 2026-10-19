from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields
from datetime import date, timedelta
from types import MappingProxyType

import pytest

import topspeed_ai_os.calculation as calculation
import topspeed_ai_os.calculation.inventory_reorder_point as reorder_point
from topspeed_ai_os.calculation.inventory_demand_velocity import (
    calculate_inventory_demand_velocity,
)
from topspeed_ai_os.calculation.inventory_reorder_point import (
    InventoryReorderPointAuthorityRef,
    _InventorySafetyStockProjection,
    _project_inventory_safety_stock_for_reorder_point,
)
from topspeed_ai_os.calculation.inventory_safety_stock import (
    INVENTORY_SAFETY_STOCK_FORMULA_VERSION,
    InventorySafetyStockResult,
    calculate_inventory_safety_stock,
)
from topspeed_ai_os.contracts import ContractValidationError
from topspeed_ai_os.core.ids import InvalidIdentifierError
from topspeed_ai_os.policy_authority import inventory_safety_stock_v1 as policy_authority

RUN_ID = "run_01J" + "0" * 23
SKU = "TS-KITCHEN-001"
CHANNEL = "coupang"
WINDOW_END = date(2026, 9, 30)
WINDOW_START = WINDOW_END - timedelta(days=29)
POLICY_SOURCE = "topspeed.repository.policy_authority.inventory_safety_stock.v1"
POLICY_REFERENCE = "TOPSPEED_SAFETY_STOCK_POLICY_V1"
POLICY_DATA_AS_OF = "2026-10-15T16:05:35+09:00"
AUTHORITY_FIELDS = (
    "kind",
    "sku",
    "value",
    "authority_reference",
    "authority_status",
    "formula_version",
    "source",
    "data_as_of",
    "input_hash",
)
PROJECTION_FIELDS = ("inventory", "authority")


class StrChild(str):
    pass


class IntChild(int):
    pass


class TupleChild(tuple):
    pass


class AuthorityChild(InventoryReorderPointAuthorityRef):
    pass


class ProjectionChild(_InventorySafetyStockProjection):
    pass


def _independent_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _authority_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": "SAFETY_STOCK_POLICY",
        "sku": SKU,
        "value": 7,
        "authority_reference": ("TOPSPEED_SAFETY_STOCK_POLICY_V1@sha256:" + "a" * 64),
        "authority_status": "APPROVED",
        "formula_version": INVENTORY_SAFETY_STOCK_FORMULA_VERSION,
        "source": POLICY_SOURCE,
        "data_as_of": POLICY_DATA_AS_OF,
    }
    payload.update(overrides)
    return payload


def _authority(**overrides: object) -> InventoryReorderPointAuthorityRef:
    payload = _authority_payload(**overrides)
    return InventoryReorderPointAuthorityRef(
        **payload,
        input_hash=_independent_hash(payload),
    )


def _safety_stock_result(records) -> InventorySafetyStockResult:
    daily = records()["CHANNEL_DAILY"]
    rows = []
    for offset in range(30):
        row = dict(daily)
        row["channel"] = CHANNEL
        row["sku"] = SKU
        row["stat_date"] = (WINDOW_START + timedelta(days=offset)).isoformat()
        row["units_sold"] = 1
        rows.append(row)
    demand = calculate_inventory_demand_velocity(
        tuple(rows), run_id=RUN_ID, window_end_date=WINDOW_END.isoformat()
    )
    assert demand.status == "SUCCESS"
    authority = policy_authority._produce_inventory_safety_stock_policy_authority()
    return calculate_inventory_safety_stock(demand, authority, run_id=RUN_ID)


def _inventory(records, *, sku: str = SKU) -> dict[str, object]:
    source = dict(records()["INVENTORY"])
    source.pop("safety_stock_qty")
    source["sku"] = sku
    return source


def _produce(records, *, inventory=None, safety_stock=None):
    return _project_inventory_safety_stock_for_reorder_point(
        _inventory(records) if inventory is None else inventory,
        _safety_stock_result(records) if safety_stock is None else safety_stock,
    )


def test_authority_field_order_frozen_slots_and_no_extra_state():
    assert (
        tuple(field.name for field in fields(InventoryReorderPointAuthorityRef)) == AUTHORITY_FIELDS
    )
    authority = _authority()
    assert type(authority) is InventoryReorderPointAuthorityRef
    assert not hasattr(authority, "__dict__")
    with pytest.raises(FrozenInstanceError):
        authority.sku = "changed"  # type: ignore[misc]
    assert "__slots__" in InventoryReorderPointAuthorityRef.__dict__


@pytest.mark.parametrize(
    ("kind", "value", "status", "formula_version"),
    [
        ("LEAD_TIME_SUPPLIER_CONTRACT", None, "VERIFIED", None),
        ("LEAD_TIME_SUPPLIER_CONTRACT", 0, "VERIFIED", None),
        ("SAFETY_STOCK_POLICY", None, "APPROVED", INVENTORY_SAFETY_STOCK_FORMULA_VERSION),
        ("SAFETY_STOCK_POLICY", 0, "APPROVED", INVENTORY_SAFETY_STOCK_FORMULA_VERSION),
    ],
)
def test_authority_enforces_both_kind_invariant_sets(kind, value, status, formula_version):
    payload = _authority_payload(
        kind=kind,
        value=value,
        authority_reference="future-authority-reference"
        if kind.startswith("LEAD_TIME")
        else ("TOPSPEED_SAFETY_STOCK_POLICY_V1@sha256:" + "a" * 64),
        authority_status=status,
        formula_version=formula_version,
    )
    authority = InventoryReorderPointAuthorityRef(
        **payload,
        input_hash=_independent_hash(payload),
    )
    assert authority.kind == kind


@pytest.mark.parametrize(
    ("field", "value", "exception"),
    [
        ("kind", StrChild("SAFETY_STOCK_POLICY"), TypeError),
        ("sku", StrChild(SKU), TypeError),
        ("value", True, TypeError),
        ("value", IntChild(7), TypeError),
        ("authority_reference", StrChild("x"), TypeError),
        ("authority_status", StrChild("APPROVED"), TypeError),
        ("formula_version", StrChild(INVENTORY_SAFETY_STOCK_FORMULA_VERSION), TypeError),
        ("source", StrChild(POLICY_SOURCE), TypeError),
        ("data_as_of", StrChild(POLICY_DATA_AS_OF), TypeError),
        ("input_hash", StrChild("sha256:" + "a" * 64), TypeError),
        ("value", -1, None),
        ("kind", "OTHER", None),
    ],
)
def test_authority_rejects_invalid_exact_types_and_values(field, value, exception):
    payload = _authority_payload(**{field: value})
    payload.pop("input_hash", None)
    if exception is not None:
        input_hash = (
            StrChild("sha256:" + "a" * 64) if field == "input_hash" else ("sha256:" + "a" * 64)
        )
        with pytest.raises(exception):
            InventoryReorderPointAuthorityRef(**payload, input_hash=input_hash)
    else:
        with pytest.raises(ValueError):
            InventoryReorderPointAuthorityRef(**payload, input_hash="sha256:" + "a" * 64)


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-15T16:05:35",
        "not-a-date",
        "2026-02-30T00:00:00+00:00",
        "2026-10-15T16:05:35.000000+09:00",
        "2026-10-15T16:05:35+09:00:30",
        "2026-10-15T16:05:35+09:00:30.5",
    ],
)
def test_authority_rejects_noncanonical_or_timezone_free_datetime(value):
    payload = _authority_payload(data_as_of=value)
    with pytest.raises(ValueError):
        InventoryReorderPointAuthorityRef(**payload, input_hash=_independent_hash(payload))


def test_authority_accepts_canonical_z_and_recomputes_its_hash():
    z_datetime = "2026-10-15T07:05:35Z"
    payload = _authority_payload(data_as_of=z_datetime)
    expected_hash = _independent_hash(payload)
    authority = InventoryReorderPointAuthorityRef(**payload, input_hash=expected_hash)
    assert authority.data_as_of == z_datetime
    assert authority.input_hash == expected_hash
    assert authority.input_hash == _independent_hash(
        _authority_payload(data_as_of=authority.data_as_of)
    )


def test_authority_retains_canonical_hh_mm_offset_acceptance():
    authority = _authority(data_as_of="2026-10-15T16:05:35+09:00")
    assert authority.data_as_of == "2026-10-15T16:05:35+09:00"
    negative_offset = _authority(data_as_of="2026-10-15T16:05:35-05:00")
    assert negative_offset.data_as_of == "2026-10-15T16:05:35-05:00"


def test_authority_recomputes_hash_and_rejects_tampering():
    authority = _authority()
    payload = _authority_payload()
    assert authority.input_hash == _independent_hash(payload)
    with pytest.raises(ValueError, match="input_hash"):
        InventoryReorderPointAuthorityRef(**payload, input_hash="sha256:" + "b" * 64)


def test_projection_carrier_field_order_types_and_pair_coherence(records):
    projection = _produce(records)
    assert (
        tuple(field.name for field in fields(_InventorySafetyStockProjection)) == PROJECTION_FIELDS
    )
    assert type(projection.inventory) is MappingProxyType
    assert type(projection.authority) is InventoryReorderPointAuthorityRef
    assert not hasattr(projection, "__dict__")
    with pytest.raises(FrozenInstanceError):
        projection.authority = _authority()  # type: ignore[misc]
    with pytest.raises(TypeError):
        _InventorySafetyStockProjection({}, projection.authority)
    with pytest.raises(TypeError):
        _InventorySafetyStockProjection(
            projection.inventory,
            AuthorityChild(
                **{
                    **_authority_payload(),
                    "input_hash": _independent_hash(_authority_payload()),
                }
            ),
        )
    with pytest.raises(ValueError):
        _InventorySafetyStockProjection(
            MappingProxyType({**dict(projection.inventory), "sku": "OTHER"}),
            projection.authority,
        )


def test_producer_signature_is_exact_and_private():
    signature = inspect.signature(_project_inventory_safety_stock_for_reorder_point)
    assert tuple(signature.parameters) == ("inventory", "safety_stock")
    parameters = tuple(signature.parameters.values())
    assert all(
        parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD for parameter in parameters
    )
    assert all(parameter.default is inspect.Parameter.empty for parameter in parameters)
    assert signature.return_annotation is _InventorySafetyStockProjection
    assert not hasattr(calculation, "InventoryReorderPointAuthorityRef")
    assert not hasattr(calculation, "_project_inventory_safety_stock_for_reorder_point")
    assert not any("ReorderPoint" in name for name in calculation.__all__)


def test_success_is_fresh_read_only_projection_with_exact_paired_authority(records):
    source = _inventory(records)
    before = dict(source)
    safety_stock = _safety_stock_result(records)
    projection = _project_inventory_safety_stock_for_reorder_point(source, safety_stock)
    assert source == before
    assert projection.inventory is not source
    assert type(projection.inventory) is MappingProxyType
    assert dict(projection.inventory) == {**before, "safety_stock_qty": 7}
    assert projection.inventory["sku"] == projection.authority.sku == safety_stock.sku
    assert projection.inventory["safety_stock_qty"] == projection.authority.value == 7
    assert projection.authority.kind == "SAFETY_STOCK_POLICY"
    assert projection.authority.authority_status == "APPROVED"
    assert projection.authority.formula_version == safety_stock.formula_version
    policy_ref = safety_stock.input_refs[1]
    assert projection.authority.source == policy_ref.source
    assert projection.authority.data_as_of == policy_ref.data_as_of
    assert projection.authority.authority_reference == (
        f"{POLICY_REFERENCE}@{safety_stock.input_hash}"
    )
    assert projection.authority.input_hash == _independent_hash(
        _authority_payload(
            sku=safety_stock.sku,
            value=7,
            authority_reference=f"{POLICY_REFERENCE}@{safety_stock.input_hash}",
            source=policy_ref.source,
            data_as_of=policy_ref.data_as_of,
        )
    )
    with pytest.raises(TypeError):
        projection.inventory["safety_stock_qty"] = 999  # type: ignore[index]


def test_projection_preserves_location_without_demand_channel_equality(records):
    source = _inventory(records)
    source["location"] = "warehouse-seoul"
    safety_stock = _safety_stock_result(records)
    result = _project_inventory_safety_stock_for_reorder_point(source, safety_stock)
    assert result.inventory["location"] == "warehouse-seoul"
    assert safety_stock.channel == CHANNEL


@pytest.mark.parametrize("existing", [None, 0])
def test_existing_safety_stock_key_is_rejected_without_replacement(records, existing):
    source = _inventory(records)
    source["safety_stock_qty"] = existing
    before = dict(source)
    with pytest.raises(ValueError, match="must not contain"):
        _produce(records, inventory=source)
    assert source == before


def test_mapping_and_contract_fail_before_safety_stock_result_inspection(records, monkeypatch):
    calls = []

    def validator(name, value):
        calls.append((name, value))
        raise ContractValidationError(name, ["sentinel"])

    monkeypatch.setattr(reorder_point, "validate_schema_only", validator)
    with pytest.raises(ContractValidationError) as raised:
        _project_inventory_safety_stock_for_reorder_point({}, object())
    assert raised.value.contract_name == "INVENTORY"
    assert calls == [("INVENTORY", {})]


def test_source_contract_exception_identity_is_preserved(records, monkeypatch):
    sentinel = ContractValidationError("INVENTORY", ["sentinel"])

    def validator(_name, _value):
        raise sentinel

    monkeypatch.setattr(reorder_point, "validate_schema_only", validator)
    with pytest.raises(ContractValidationError) as raised:
        _produce(records)
    assert raised.value is sentinel


def test_invalid_run_id_exception_is_preserved(records):
    result = _safety_stock_result(records)
    object.__setattr__(result, "run_id", "invalid")
    with pytest.raises(InvalidIdentifierError):
        _produce(records, safety_stock=result)


def test_mapping_access_exception_during_projection_is_preserved(records):
    sentinel = RuntimeError("mapping iteration sentinel")

    class FailingMapping(Mapping):
        def __init__(self, values):
            self.values = values
            self.calls = 0

        def __iter__(self):
            self.calls += 1
            if self.calls > 1:
                raise sentinel

            return iter(self.values)

        def __getitem__(self, key):
            return self.values[key]

        def __len__(self):
            return len(self.values)

    source = FailingMapping(_inventory(records))
    with pytest.raises(RuntimeError) as raised:
        _produce(records, inventory=source)
    assert raised.value is sentinel


def test_projected_schema_exception_identity_is_preserved(records, monkeypatch):
    sentinel = ContractValidationError("INVENTORY", ["projected sentinel"])
    calls = 0

    def validator(name, value):
        nonlocal calls
        calls += 1
        if calls == 2:
            assert type(value) is MappingProxyType
            raise sentinel

    monkeypatch.setattr(reorder_point, "validate_schema_only", validator)
    with pytest.raises(ContractValidationError) as raised:
        _produce(records)
    assert raised.value is sentinel
    assert calls == 2


@pytest.mark.parametrize(
    ("mutation", "exception"),
    [
        (lambda result: object.__setattr__(result, "formula_version", "wrong"), ValueError),
        (lambda result: object.__setattr__(result, "outputs", ()), ValueError),
        (
            lambda result: object.__setattr__(result.outputs[0], "value", 8),
            ValueError,
        ),
        (
            lambda result: object.__setattr__(
                result.input_refs[0], "input_hash", "sha256:" + "b" * 64
            ),
            ValueError,
        ),
        (
            lambda result: object.__setattr__(result.input_refs[1], "source", "tampered.source"),
            ValueError,
        ),
        (lambda result: object.__setattr__(result, "input_hash", "sha256:" + "c" * 64), ValueError),
    ],
)
def test_tampered_safety_stock_result_and_references_are_revalidated(records, mutation, exception):
    result = _safety_stock_result(records)
    mutation(result)
    with pytest.raises(exception):
        _produce(records, safety_stock=result)


def test_precedence_stops_at_mapping_schema_absent_key_and_exact_result_identity(
    records, monkeypatch
):
    source = _inventory(records)
    calls = []
    monkeypatch.setattr(
        reorder_point, "validate_schema_only", lambda name, value: calls.append(name)
    )
    with pytest.raises(TypeError):
        _project_inventory_safety_stock_for_reorder_point(object(), object())
    assert calls == []

    with pytest.raises(TypeError):
        _project_inventory_safety_stock_for_reorder_point(source, object())
    assert calls == ["INVENTORY"]

    existing = {**source, "safety_stock_qty": None}
    with pytest.raises(ValueError):
        _project_inventory_safety_stock_for_reorder_point(existing, object())
    assert calls == ["INVENTORY", "INVENTORY"]

    with pytest.raises(TypeError):
        _project_inventory_safety_stock_for_reorder_point(source, object())
    assert calls == ["INVENTORY", "INVENTORY", "INVENTORY"]


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda result: object.__setattr__(result, "metric_family", "wrong"), ValueError),
        (lambda result: object.__setattr__(result, "outputs", []), TypeError),
        (lambda result: object.__setattr__(result.outputs[0], "value", True), TypeError),
        (lambda result: object.__setattr__(result, "input_refs", ()), ValueError),
        (
            lambda result: object.__setattr__(result.input_refs[0], "avg_daily_units", "2"),
            ValueError,
        ),
    ],
)
def test_combined_faults_obey_result_validation_precedence(records, mutator, expected):
    result = _safety_stock_result(records)
    mutator(result)
    with pytest.raises(expected):
        _produce(records, safety_stock=result)


def test_later_precedence_faults_do_not_mask_earlier_faults(records):
    # Step 6 literal validation precedes output shape (step 7).
    result = _safety_stock_result(records)
    object.__setattr__(result, "formula_version", "unsupported")
    object.__setattr__(result, "outputs", ())
    with pytest.raises(ValueError, match="formula_version"):
        _produce(records, safety_stock=result)

    # Step 7 output validation precedes reference order (step 8).
    result = _safety_stock_result(records)
    object.__setattr__(result.outputs[0], "name", "wrong")
    object.__setattr__(result, "input_refs", ())
    with pytest.raises(ValueError, match="output name"):
        _produce(records, safety_stock=result)

    # Step 8 reference order precedes demand-reference revalidation (step 9).
    result = _safety_stock_result(records)
    object.__setattr__(result.input_refs[0], "input_hash", "sha256:" + "b" * 64)
    object.__setattr__(result, "input_refs", tuple(reversed(result.input_refs)))
    with pytest.raises(ValueError, match="ordered"):
        _produce(records, safety_stock=result)

    # Step 9 demand-reference validation precedes policy-reference validation (step 10).
    result = _safety_stock_result(records)
    object.__setattr__(result.input_refs[0], "input_hash", "sha256:" + "b" * 64)
    object.__setattr__(result.input_refs[1], "source", "tampered.source")
    with pytest.raises(ValueError, match="demand input_hash"):
        _produce(records, safety_stock=result)

    # Step 10 policy-reference validation precedes result/final-hash validation (step 11).
    result = _safety_stock_result(records)
    object.__setattr__(result.input_refs[1], "source", "tampered.source")
    object.__setattr__(result, "input_hash", "sha256:" + "c" * 64)
    with pytest.raises(ValueError, match="policy"):
        _produce(records, safety_stock=result)

    # Step 11 result validation precedes inventory/result SKU comparison (step 12).
    result = _safety_stock_result(records)
    object.__setattr__(result, "input_hash", "sha256:" + "c" * 64)
    source = _inventory(records, sku="TS-OTHER-002")
    with pytest.raises(ValueError, match="input_hash"):
        _produce(records, inventory=source, safety_stock=result)


def test_inventory_sku_mismatch_is_rejected_after_valid_result(records):
    source = _inventory(records, sku="TS-OTHER-002")
    with pytest.raises(ValueError, match="SKU"):
        _produce(records, inventory=source)
    assert "safety_stock_qty" not in source


def test_public_reorder_point_api_remains_unactivated():
    public_names = {
        "INVENTORY_REORDER_POINT_FORMULA_VERSION",
        "InventoryReorderPointAuthorityRef",
        "InventoryReorderPointError",
        "InventoryReorderPointInputRef",
        "InventoryReorderPointOutput",
        "InventoryReorderPointResult",
        "calculate_inventory_reorder_point",
    }
    assert public_names.isdisjoint(calculation.__all__)
    assert public_names.isdisjoint(vars(calculation))
    assert reorder_point.InventoryReorderPointAuthorityRef is InventoryReorderPointAuthorityRef
    assert not any(
        name.startswith("calculate_inventory_reorder_point") for name in vars(reorder_point)
    )
