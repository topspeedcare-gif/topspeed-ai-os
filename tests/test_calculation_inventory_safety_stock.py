from __future__ import annotations

import ast
import decimal
import hashlib
import inspect
import json
from dataclasses import FrozenInstanceError, fields
from datetime import date, timedelta
from pathlib import Path

import pytest

import topspeed_ai_os.calculation as calculation
import topspeed_ai_os.calculation.inventory_safety_stock as safety_stock
from topspeed_ai_os.calculation import (
    INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION,
    INVENTORY_SAFETY_STOCK_FORMULA_VERSION,
    InventoryDemandVelocityInputRef,
    InventoryDemandVelocityOutput,
    InventoryDemandVelocityResult,
    InventorySafetyStockInputRef,
    InventorySafetyStockOutput,
    InventorySafetyStockPolicyAuthority,
    InventorySafetyStockResult,
    UnsupportedFormulaVersionError,
    calculate_inventory_demand_velocity,
    calculate_inventory_safety_stock,
)
from topspeed_ai_os.core.ids import InvalidIdentifierError
from topspeed_ai_os.policy_authority import inventory_safety_stock_v1 as producer

RUN_ID = "run_01J" + "0" * 23
OTHER_RUN_ID = "run_01K" + "0" * 23
START = date(2026, 9, 1)
END = "2026-09-30"
SKU = "TS-KITCHEN-001"
CHANNEL = "coupang"
POLICY_VERSION = "TOPSPEED_SAFETY_STOCK_POLICY_V1"
POLICY_AUTHORITY = "TOPSPEED Human Architecture Owner"
POLICY_SOURCE = "topspeed.repository.policy_authority.inventory_safety_stock.v1"
FINAL_EXPORTS = [
    "AD_METRICS_FORMULA_VERSION",
    "AdvertisingMetricOutput",
    "AdvertisingMetricsError",
    "AdvertisingMetricsInputRef",
    "AdvertisingMetricsResult",
    "CONTRIBUTION_MARGIN_FORMULA_VERSION",
    "CONTRIBUTION_MARGIN_METRIC",
    "CalculationError",
    "CalculationInputRef",
    "CalculationOutput",
    "CalculationResult",
    "UnsupportedFormulaVersionError",
    "calculate_ad_daily_metrics",
    "calculate_product_master_contribution_margin",
    "INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION",
    "InventoryDemandVelocityError",
    "InventoryDemandVelocityInputRef",
    "InventoryDemandVelocityOutput",
    "InventoryDemandVelocityResult",
    "calculate_inventory_demand_velocity",
    "INVENTORY_STOCK_DAYS_FORMULA_VERSION",
    "InventoryStockDaysError",
    "InventoryStockDaysInputRef",
    "InventoryStockDaysOutput",
    "InventoryStockDaysResult",
    "calculate_inventory_stock_days",
    "INVENTORY_SAFETY_STOCK_FORMULA_VERSION",
    "InventorySafetyStockPolicyAuthority",
    "InventorySafetyStockInputRef",
    "InventorySafetyStockOutput",
    "InventorySafetyStockResult",
    "calculate_inventory_safety_stock",
]
DEMAND_REF_FIELDS = (
    "kind",
    "metric_family",
    "formula_version",
    "policy_version",
    "approval_authority",
    "authority_reference",
    "authority_status",
    "source",
    "data_as_of",
    "channel",
    "sku",
    "window_start_date",
    "window_end_date",
    "avg_daily_units",
    "safety_stock_days",
    "input_hash",
    "upstream_input_refs",
)
RESULT_FIELDS = (
    "metric_family",
    "formula_version",
    "policy_version",
    "run_id",
    "channel",
    "sku",
    "window_start_date",
    "window_end_date",
    "status",
    "outputs",
    "input_refs",
    "errors",
    "input_hash",
)


class StrChild(str):
    pass


class IntChild(int):
    pass


class TupleChild(tuple):
    pass


class DemandRefChild(InventoryDemandVelocityInputRef):
    pass


class SafetyRefChild(InventorySafetyStockInputRef):
    pass


class SafetyOutputChild(InventorySafetyStockOutput):
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


def _upstream_refs(*, repeated_hash: bool = False):
    common_hash = "sha256:" + "a" * 64
    return tuple(
        InventoryDemandVelocityInputRef(
            contract_name="CHANNEL_DAILY",
            natural_key=(CHANNEL, (START + timedelta(days=index)).isoformat(), SKU),
            source="fixture-source",
            data_as_of="2026-09-30T00:00:00+00:00",
            input_hash=common_hash if repeated_hash else f"sha256:{index + 1:064x}",
        )
        for index in range(30)
    )


def _direct_demand(value: str = "1") -> InventoryDemandVelocityResult:
    return InventoryDemandVelocityResult(
        metric_family="INVENTORY_DEMAND_VELOCITY",
        formula_version=INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION,
        run_id=RUN_ID,
        channel=CHANNEL,
        sku=SKU,
        window_start_date=START.isoformat(),
        window_end_date=END,
        status="SUCCESS",
        outputs=(InventoryDemandVelocityOutput("avg_daily_units", value),),
        input_refs=_upstream_refs(),
        errors=(),
    )


def _actual_demand(records, units: int = 1) -> InventoryDemandVelocityResult:
    template = records()["CHANNEL_DAILY"]
    rows = []
    for index in range(30):
        row = dict(template)
        row["stat_date"] = (START + timedelta(days=index)).isoformat()
        row["units_sold"] = units
        rows.append(row)
    return calculate_inventory_demand_velocity(tuple(rows), run_id=RUN_ID, window_end_date=END)


def _policy_authority() -> InventorySafetyStockPolicyAuthority:
    authority = producer._produce_inventory_safety_stock_policy_authority()
    assert type(authority) is InventorySafetyStockPolicyAuthority
    return authority


def _demand_payload(
    *,
    value: str = "1",
    refs: tuple[InventoryDemandVelocityInputRef, ...] | None = None,
    channel: str = CHANNEL,
    sku: str = SKU,
    start: str = START.isoformat(),
    end: str = END,
) -> dict[str, object]:
    upstream = refs if refs is not None else _upstream_refs()
    return {
        "metric_family": "INVENTORY_DEMAND_VELOCITY",
        "formula_version": INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION,
        "channel": channel,
        "sku": sku,
        "window_start_date": start,
        "window_end_date": end,
        "avg_daily_units": value,
        "input_refs": [
            {
                "contract_name": ref.contract_name,
                "natural_key": list(ref.natural_key),
                "source": ref.source,
                "data_as_of": ref.data_as_of,
                "input_hash": ref.input_hash,
            }
            for ref in upstream
        ],
    }


def _demand_ref(value: str = "1", *, refs=None, **overrides) -> InventorySafetyStockInputRef:
    upstream = refs if refs is not None else _upstream_refs()
    values = {
        "kind": "DEMAND_VELOCITY",
        "metric_family": "INVENTORY_DEMAND_VELOCITY",
        "formula_version": INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION,
        "policy_version": None,
        "approval_authority": None,
        "authority_reference": None,
        "authority_status": None,
        "source": None,
        "data_as_of": None,
        "channel": CHANNEL,
        "sku": SKU,
        "window_start_date": START.isoformat(),
        "window_end_date": END,
        "avg_daily_units": value,
        "safety_stock_days": None,
        "input_hash": _independent_hash(_demand_payload(value=value, refs=upstream)),
        "upstream_input_refs": upstream,
    }
    values.update(overrides)
    return InventorySafetyStockInputRef(**values)


def _policy_payload(authority: InventorySafetyStockPolicyAuthority) -> dict[str, object]:
    return {
        "policy_version": authority.policy_version,
        "approval_authority": authority.approval_authority,
        "authority_reference": authority.authority_reference,
        "authority_status": authority.authority_status,
        "source": authority.source,
        "data_as_of": authority.data_as_of,
        "safety_stock_days": authority.safety_stock_days,
    }


def _policy_ref(authority=None, **overrides) -> InventorySafetyStockInputRef:
    policy = authority or _policy_authority()
    values = {
        "kind": "SAFETY_STOCK_POLICY",
        "metric_family": None,
        "formula_version": None,
        "policy_version": policy.policy_version,
        "approval_authority": policy.approval_authority,
        "authority_reference": policy.authority_reference,
        "authority_status": policy.authority_status,
        "source": policy.source,
        "data_as_of": policy.data_as_of,
        "channel": None,
        "sku": None,
        "window_start_date": None,
        "window_end_date": None,
        "avg_daily_units": None,
        "safety_stock_days": policy.safety_stock_days,
        "input_hash": _independent_hash(_policy_payload(policy)),
        "upstream_input_refs": (),
    }
    values.update(overrides)
    return InventorySafetyStockInputRef(**values)


def _final_hash(demand_ref: InventorySafetyStockInputRef, policy_ref: InventorySafetyStockInputRef):
    return _independent_hash(
        {
            "formula_version": INVENTORY_SAFETY_STOCK_FORMULA_VERSION,
            "demand_input_hash": demand_ref.input_hash,
            "policy_authority_hash": policy_ref.input_hash,
        }
    )


def _quantity(value: str) -> int:
    whole, _, fraction = value.partition(".")
    scale = 10 ** len(fraction)
    numerator = int(whole + fraction)
    return (numerator * 7 + scale - 1) // scale


def _direct_result(**overrides) -> InventorySafetyStockResult:
    demand_ref = _demand_ref()
    policy_ref = _policy_ref()
    values = {
        "metric_family": "INVENTORY_SAFETY_STOCK",
        "formula_version": INVENTORY_SAFETY_STOCK_FORMULA_VERSION,
        "policy_version": POLICY_VERSION,
        "run_id": RUN_ID,
        "channel": CHANNEL,
        "sku": SKU,
        "window_start_date": START.isoformat(),
        "window_end_date": END,
        "status": "SUCCESS",
        "outputs": (InventorySafetyStockOutput("safety_stock_qty", 7),),
        "input_refs": (demand_ref, policy_ref),
        "errors": (),
        "input_hash": _final_hash(demand_ref, policy_ref),
    }
    values.update(overrides)
    return InventorySafetyStockResult(**values)


def _calculate(value="1", **kwargs):
    policy = kwargs.pop("policy_authority", None) or _policy_authority()
    return calculate_inventory_safety_stock(_direct_demand(value), policy, run_id=RUN_ID, **kwargs)


def test_six_public_symbols_order_and_formula_literal():
    assert calculation.__all__ == FINAL_EXPORTS
    safety_symbols = [
        name for name in calculation.__all__ if name.startswith("InventorySafetyStock")
    ]
    assert safety_symbols == [
        "InventorySafetyStockPolicyAuthority",
        "InventorySafetyStockInputRef",
        "InventorySafetyStockOutput",
        "InventorySafetyStockResult",
    ]
    assert calculation.__all__[-6:] == [
        "INVENTORY_SAFETY_STOCK_FORMULA_VERSION",
        "InventorySafetyStockPolicyAuthority",
        "InventorySafetyStockInputRef",
        "InventorySafetyStockOutput",
        "InventorySafetyStockResult",
        "calculate_inventory_safety_stock",
    ]
    assert INVENTORY_SAFETY_STOCK_FORMULA_VERSION == (
        "topspeed.calculation.inventory_safety_stock.v1"
    )


def test_exact_function_signature_and_canonical_carrier_reuse():
    signature = inspect.signature(calculate_inventory_safety_stock)
    assert list(signature.parameters) == [
        "demand_velocity",
        "policy_authority",
        "run_id",
        "formula_version",
    ]
    params = list(signature.parameters.values())
    assert params[0].annotation is InventoryDemandVelocityResult
    assert params[1].annotation is InventorySafetyStockPolicyAuthority
    assert params[2].annotation is str and params[2].kind is inspect.Parameter.KEYWORD_ONLY
    assert params[3].annotation is str and params[3].kind is inspect.Parameter.KEYWORD_ONLY
    assert params[3].default == INVENTORY_SAFETY_STOCK_FORMULA_VERSION
    assert signature.return_annotation is InventorySafetyStockResult
    assert calculation.InventorySafetyStockPolicyAuthority is InventorySafetyStockPolicyAuthority
    assert type(_policy_authority()) is InventorySafetyStockPolicyAuthority


def test_input_reference_exact_frozen_slotted_contract():
    assert tuple(field.name for field in fields(InventorySafetyStockInputRef)) == DEMAND_REF_FIELDS
    ref = _demand_ref()
    assert type(ref) is InventorySafetyStockInputRef
    assert not hasattr(ref, "__dict__")
    with pytest.raises(FrozenInstanceError):
        ref.kind = "changed"  # type: ignore[misc]
    assert not any(
        getattr(field, "_field_type", None).__class__.__name__ == "_InitVar"
        for field in fields(InventorySafetyStockInputRef)
    )


@pytest.mark.parametrize(
    ("field", "value", "exception"),
    [
        ("kind", StrChild("DEMAND_VELOCITY"), TypeError),
        ("metric_family", StrChild("INVENTORY_DEMAND_VELOCITY"), TypeError),
        ("channel", StrChild(CHANNEL), TypeError),
        ("safety_stock_days", True, TypeError),
        ("safety_stock_days", IntChild(7), TypeError),
        ("upstream_input_refs", TupleChild(_upstream_refs()), TypeError),
        ("upstream_input_refs", (object(),) * 30, TypeError),
    ],
)
def test_input_reference_exact_types(field, value, exception):
    with pytest.raises(exception):
        _demand_ref(**{field: value})


def test_input_reference_rejects_nested_carrier_subclasses_and_has_no_source_channel():
    original = _upstream_refs()[0]
    child = DemandRefChild(
        contract_name=original.contract_name,
        natural_key=original.natural_key,
        source=original.source,
        data_as_of=original.data_as_of,
        input_hash=original.input_hash,
    )
    refs = (child, *_upstream_refs()[1:])
    with pytest.raises(TypeError):
        _demand_ref(refs=refs)
    assert "source_result" not in {field.name for field in fields(InventorySafetyStockInputRef)}
    assert "source_status" not in {field.name for field in fields(InventorySafetyStockInputRef)}
    assert "source_output_count" not in {
        field.name for field in fields(InventorySafetyStockInputRef)
    }
    # Constructor validates its declared projection only; source-result identity/status/output
    # are deliberately checked by calculate_inventory_safety_stock before projection.
    assert _demand_ref().kind == "DEMAND_VELOCITY"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "-1",
        "-0.1",
        "+1",
        "01",
        "1.",
        ".1",
        "1e2",
        "1E2",
        "1.0",
        "1.0000",
        "1.00001",
        "NaN",
        "Infinity",
    ],
)
def test_demand_reference_rejects_noncanonical_numeric(value):
    with pytest.raises(ValueError):
        _demand_ref(value)


def test_demand_reference_constructor_enforces_window_count_order_and_coherence():
    refs = _upstream_refs()
    with pytest.raises(ValueError, match="30 upstream"):
        _demand_ref(refs=refs[:-1])
    with pytest.raises(ValueError, match="canonically ordered"):
        _demand_ref(refs=tuple(reversed(refs)))
    altered = list(refs)
    altered[0] = InventoryDemandVelocityInputRef(
        "CHANNEL_DAILY",
        ("other-channel", refs[0].natural_key[1], SKU),
        refs[0].source,
        refs[0].data_as_of,
        refs[0].input_hash,
    )
    with pytest.raises(ValueError, match="channel and SKU"):
        _demand_ref(refs=tuple(altered))
    duplicated_date = list(refs)
    duplicated_date[1] = InventoryDemandVelocityInputRef(
        "CHANNEL_DAILY",
        (CHANNEL, refs[0].natural_key[1], SKU),
        refs[1].source,
        refs[1].data_as_of,
        refs[1].input_hash,
    )
    duplicated_date.sort(key=lambda ref: (ref.natural_key[1], ref.input_hash))
    with pytest.raises(ValueError, match="cover the complete"):
        _demand_ref(refs=tuple(duplicated_date))


def test_demand_hash_preserves_reference_order_repeated_hashes_and_cardinality():
    refs = _upstream_refs(repeated_hash=True)
    ref = _demand_ref(refs=refs)
    payload = _demand_payload(refs=refs)
    assert tuple(payload) == (
        "metric_family",
        "formula_version",
        "channel",
        "sku",
        "window_start_date",
        "window_end_date",
        "avg_daily_units",
        "input_refs",
    )
    assert len(payload["input_refs"]) == 30
    assert len({entry["input_hash"] for entry in payload["input_refs"]}) == 1
    assert all(
        type(entry["natural_key"]) is list and len(entry["natural_key"]) == 3
        for entry in payload["input_refs"]
    )
    assert ref.upstream_input_refs == refs
    assert ref.input_hash == _independent_hash(payload)
    bad = dict(
        kind=ref.kind,
        metric_family=ref.metric_family,
        formula_version=ref.formula_version,
        policy_version=ref.policy_version,
        approval_authority=ref.approval_authority,
        authority_reference=ref.authority_reference,
        authority_status=ref.authority_status,
        source=ref.source,
        data_as_of=ref.data_as_of,
        channel=ref.channel,
        sku=ref.sku,
        window_start_date=ref.window_start_date,
        window_end_date=ref.window_end_date,
        avg_daily_units=ref.avg_daily_units,
        safety_stock_days=ref.safety_stock_days,
        input_hash="sha256:" + "0" * 64,
        upstream_input_refs=refs,
    )
    with pytest.raises(ValueError, match="input_hash"):
        InventorySafetyStockInputRef(**bad)


def test_policy_reference_constructor_enforces_exact_projection_and_hash():
    authority = _policy_authority()
    ref = _policy_ref(authority)
    assert ref.kind == "SAFETY_STOCK_POLICY"
    assert ref.input_hash == authority.input_hash == _independent_hash(_policy_payload(authority))
    assert tuple(_policy_payload(authority)) == (
        "policy_version",
        "approval_authority",
        "authority_reference",
        "authority_status",
        "source",
        "data_as_of",
        "safety_stock_days",
    )
    for changes in (
        {"policy_version": "OTHER"},
        {"approval_authority": "Other"},
        {"authority_reference": "OTHER"},
        {"authority_status": "PENDING"},
        {"source": ""},
        {"source": "other.source"},
        {"data_as_of": "2026-10-15T16:05:35"},
        {"data_as_of": "2026-10-15T16:05:35.000000+09:00"},
        {"safety_stock_days": 8},
        {"upstream_input_refs": _upstream_refs()},
    ):
        with pytest.raises((TypeError, ValueError)):
            _policy_ref(authority, **changes)


def test_output_carrier_exact_fields_and_rejections():
    assert tuple(field.name for field in fields(InventorySafetyStockOutput)) == ("name", "value")
    assert InventorySafetyStockOutput("safety_stock_qty", 0).value == 0
    for name, value, exception in (
        (StrChild("safety_stock_qty"), 0, TypeError),
        ("other", 0, ValueError),
        ("safety_stock_qty", True, TypeError),
        ("safety_stock_qty", IntChild(1), TypeError),
        ("safety_stock_qty", -1, ValueError),
        ("safety_stock_qty", 1.0, TypeError),
        ("safety_stock_qty", decimal.Decimal("1"), TypeError),
    ):
        with pytest.raises(exception):
            InventorySafetyStockOutput(name, value)


def test_result_carrier_exact_shape_frozen_and_recomputed():
    assert tuple(field.name for field in fields(InventorySafetyStockResult)) == RESULT_FIELDS
    result = _direct_result()
    assert type(result) is InventorySafetyStockResult
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.status = "ERROR"  # type: ignore[misc]
    assert tuple(ref.kind for ref in result.input_refs) == (
        "DEMAND_VELOCITY",
        "SAFETY_STOCK_POLICY",
    )
    assert result.errors == () and type(result.errors) is tuple
    for changes, exception in (
        ({"run_id": "invalid"}, InvalidIdentifierError),
        ({"outputs": ()}, ValueError),
        ({"outputs": TupleChild((InventorySafetyStockOutput("safety_stock_qty", 7),))}, TypeError),
        ({"input_refs": ()}, ValueError),
        ({"errors": (None,)}, ValueError),
        ({"input_hash": "sha256:" + "0" * 64}, ValueError),
        ({"outputs": (InventorySafetyStockOutput("safety_stock_qty", 8),)}, ValueError),
        ({"channel": "other"}, ValueError),
        ({"sku": "TS-OTHER-001"}, ValueError),
        ({"policy_version": "OTHER"}, ValueError),
    ):
        with pytest.raises(exception):
            _direct_result(**changes)


def test_result_constructor_rejects_nested_subclasses_and_nonexact_fields():
    result = _direct_result()
    demand_ref, policy_ref = result.input_refs
    child_ref = SafetyRefChild(
        **{field.name: getattr(demand_ref, field.name) for field in fields(demand_ref)}
    )
    with pytest.raises(TypeError):
        _direct_result(input_refs=(child_ref, policy_ref))
    child_output = SafetyOutputChild("safety_stock_qty", 7)
    with pytest.raises(TypeError):
        _direct_result(outputs=(child_output,))
    for changes in (
        {"run_id": StrChild(RUN_ID)},
        {"channel": StrChild(CHANNEL)},
        {"status": StrChild("SUCCESS")},
        {"outputs": TupleChild(result.outputs)},
        {"input_refs": TupleChild(result.input_refs)},
        {"errors": TupleChild(())},
        {"status": "ERROR"},
    ):
        with pytest.raises((TypeError, ValueError)):
            _direct_result(**changes)


def test_normal_path_uses_existing_producer_and_demand_calculation(records):
    demand = _actual_demand(records)
    policy = _policy_authority()
    assert demand.status == "SUCCESS"
    result = calculate_inventory_safety_stock(demand, policy, run_id=RUN_ID)
    assert result.outputs == (InventorySafetyStockOutput("safety_stock_qty", 7),)
    assert result.status == "SUCCESS"
    assert result.run_id == RUN_ID


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", 0),
        ("0.0001", 1),
        ("0.1428", 1),
        ("0.1429", 2),
        ("1", 7),
        ("1.0001", 8),
        ("999999999999999999999999999999999999", 6999999999999999999999999999999999993),
    ],
)
def test_exact_integer_ceiling_and_large_arithmetic(value, expected):
    result = _calculate(value)
    assert type(result.outputs[0].value) is int
    assert result.outputs[0].value == expected


def test_run_id_non_interference_for_output_status_and_final_hash():
    demand = _direct_demand("1.25")
    policy = _policy_authority()
    first = calculate_inventory_safety_stock(demand, policy, run_id=RUN_ID)
    second = calculate_inventory_safety_stock(demand, policy, run_id=OTHER_RUN_ID)
    assert first.run_id != second.run_id
    assert first.outputs == second.outputs
    assert first.status == second.status
    assert first.input_hash == second.input_hash


def test_all_three_hash_layers_independently_recompute_exact_payloads():
    demand = _direct_demand("1.25")
    policy = _policy_authority()
    result = calculate_inventory_safety_stock(demand, policy, run_id=RUN_ID)
    demand_ref, policy_ref = result.input_refs
    policy_payload = _policy_payload(policy)
    demand_payload = _demand_payload(value="1.25")
    final_payload = {
        "formula_version": INVENTORY_SAFETY_STOCK_FORMULA_VERSION,
        "demand_input_hash": demand_ref.input_hash,
        "policy_authority_hash": policy_ref.input_hash,
    }
    assert _independent_hash(policy_payload) == policy_ref.input_hash
    assert _independent_hash(demand_payload) == demand_ref.input_hash
    assert _independent_hash(final_payload) == result.input_hash
    assert tuple(final_payload) == ("formula_version", "demand_input_hash", "policy_authority_hash")
    assert "run_id" not in final_payload and "safety_stock_qty" not in final_payload
    assert "lead_time_days" not in repr((policy_payload, demand_payload, final_payload))


def test_real_demand_result_fully_rehashed_and_exact_ref_projection(records):
    demand = _actual_demand(records)
    result = calculate_inventory_safety_stock(demand, _policy_authority(), run_id=RUN_ID)
    demand_ref = result.input_refs[0]
    assert demand_ref.upstream_input_refs == demand.input_refs
    assert demand_ref.input_hash == _independent_hash(
        _demand_payload(value=demand.outputs[0].value, refs=demand.input_refs)
    )
    projected = _demand_payload(value=demand.outputs[0].value, refs=demand.input_refs)["input_refs"]
    assert len(projected) == len(demand.input_refs) == 30
    assert projected[0]["source"] == demand.input_refs[0].source
    assert projected[0]["data_as_of"] == demand.input_refs[0].data_as_of


def test_decimal_ambient_and_default_contexts_are_unchanged():
    ambient = decimal.getcontext()
    ambient.prec = 2
    ambient.rounding = decimal.ROUND_FLOOR
    before_ambient = (ambient.prec, ambient.rounding, dict(ambient.flags), dict(ambient.traps))
    default = decimal.DefaultContext
    before_default = (default.prec, default.rounding, dict(default.flags), dict(default.traps))
    assert _calculate("12345678901234567890.1234").outputs[0].value == 86419752308641975231
    assert (
        ambient.prec,
        ambient.rounding,
        dict(ambient.flags),
        dict(ambient.traps),
    ) == before_ambient
    assert (
        default.prec,
        default.rounding,
        dict(default.flags),
        dict(default.traps),
    ) == before_default


def test_entry_point_exact_twelve_step_precedence_and_exception_identity(monkeypatch):
    demand = _direct_demand()
    policy = _policy_authority()

    class DemandChild(InventoryDemandVelocityResult):
        __slots__ = ()

    class PolicyChild(InventorySafetyStockPolicyAuthority):
        __slots__ = ()

    with pytest.raises(TypeError):
        calculate_inventory_safety_stock(
            DemandChild(**{f.name: getattr(demand, f.name) for f in fields(demand)}),
            object(),
            run_id=1,
            formula_version=1,
        )

    errored = _direct_demand()
    object.__setattr__(errored, "status", "ERROR")
    with pytest.raises(ValueError):
        calculate_inventory_safety_stock(errored, object(), run_id=1, formula_version=1)

    malformed_output = _direct_demand()
    object.__setattr__(malformed_output.outputs[0], "name", "other")
    with pytest.raises(ValueError):
        calculate_inventory_safety_stock(malformed_output, object(), run_id=1, formula_version=1)

    malformed_window = _direct_demand()
    object.__setattr__(malformed_window, "window_start_date", "2026-09-02")
    with pytest.raises(ValueError):
        calculate_inventory_safety_stock(malformed_window, object(), run_id=1, formula_version=1)

    with pytest.raises(TypeError):
        calculate_inventory_safety_stock(
            demand,
            PolicyChild(**{f.name: getattr(policy, f.name) for f in fields(policy)}),
            run_id=1,
            formula_version=1,
        )

    bad_policy = _policy_authority()
    object.__setattr__(bad_policy, "input_hash", "sha256:" + "0" * 64)
    with pytest.raises(ValueError):
        calculate_inventory_safety_stock(
            demand, bad_policy, run_id=1, formula_version="unsupported"
        )

    with pytest.raises(TypeError):
        calculate_inventory_safety_stock(
            demand,
            policy,
            run_id="bad",
            formula_version=StrChild(INVENTORY_SAFETY_STOCK_FORMULA_VERSION),
        )
    with pytest.raises(UnsupportedFormulaVersionError):
        calculate_inventory_safety_stock(
            demand, policy, run_id="bad", formula_version="unsupported"
        )
    with pytest.raises(TypeError):
        calculate_inventory_safety_stock(demand, policy, run_id=StrChild(RUN_ID))
    with pytest.raises(InvalidIdentifierError):
        calculate_inventory_safety_stock(demand, policy, run_id="bad")

    original_ref = safety_stock.InventorySafetyStockInputRef

    def fail_projection(**kwargs):
        raise ValueError("projection sentinel")

    monkeypatch.setattr(safety_stock, "InventorySafetyStockInputRef", fail_projection)
    with pytest.raises(ValueError, match="projection sentinel"):
        calculate_inventory_safety_stock(demand, policy, run_id=RUN_ID)
    monkeypatch.setattr(safety_stock, "InventorySafetyStockInputRef", original_ref)


def test_policy_hash_mismatch_and_policy_scalar_boundaries():
    policy = _policy_authority()
    assert policy.input_hash == _independent_hash(_policy_payload(policy))
    wrong = _policy_authority()
    object.__setattr__(wrong, "source", "")
    with pytest.raises(ValueError):
        _calculate(policy_authority=wrong)
    for bad in (StrChild(policy.policy_version),):
        altered = _policy_authority()
        object.__setattr__(altered, "policy_version", bad)
        with pytest.raises(TypeError):
            _calculate(policy_authority=altered)


def test_demand_identity_status_and_hash_fail_closed():
    demand = _direct_demand()
    wrong_identity = _direct_demand()
    object.__setattr__(wrong_identity, "metric_family", "OTHER")
    with pytest.raises(ValueError):
        calculate_inventory_safety_stock(wrong_identity, _policy_authority(), run_id=RUN_ID)
    wrong_formula = _direct_demand()
    object.__setattr__(wrong_formula, "formula_version", "unsupported")
    with pytest.raises(ValueError):
        calculate_inventory_safety_stock(wrong_formula, _policy_authority(), run_id=RUN_ID)
    invalid_refs = _direct_demand()
    object.__setattr__(invalid_refs, "input_refs", invalid_refs.input_refs[:-1])
    with pytest.raises(ValueError):
        calculate_inventory_safety_stock(invalid_refs, _policy_authority(), run_id=RUN_ID)
    assert demand.status == "SUCCESS"


def test_fourteen_reference_value_has_no_runtime_capability_or_hash_role():
    source = Path(safety_stock.__file__).read_text(encoding="utf-8")
    assert "lead_time_days" not in source
    assert "supplier" not in source.lower()
    result = _calculate("1")
    assert result.outputs[0].value == 7
    assert result.input_refs[1].safety_stock_days == 7
    assert "lead_time_days" not in result.input_hash


def test_runtime_has_no_forbidden_capability_imports_or_calls():
    tree = ast.parse(Path(safety_stock.__file__).read_text(encoding="utf-8"))
    forbidden = {
        "os",
        "pathlib",
        "socket",
        "requests",
        "urllib",
        "random",
        "secrets",
        "uuid",
        "sqlite3",
        "subprocess",
    }
    imported = set()
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
    assert not (forbidden & imported)
    assert not ({"open", "getenv", "time", "now", "today", "token_bytes", "randint"} & called)


def test_canonical_carrier_fields_and_no_duplicate_policy_class():
    path = Path(safety_stock.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    class_names = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
    assert class_names.count("InventorySafetyStockPolicyAuthority") == 1
    assert producer.InventorySafetyStockPolicyAuthority is InventorySafetyStockPolicyAuthority
    assert producer._produce_inventory_safety_stock_policy_authority().__class__ is (
        InventorySafetyStockPolicyAuthority
    )
