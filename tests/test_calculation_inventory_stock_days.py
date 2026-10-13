import ast
import decimal
import hashlib
import inspect
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from datetime import date, timedelta
from pathlib import Path

import pytest

import topspeed_ai_os.calculation as calculation_package
import topspeed_ai_os.calculation.inventory_stock_days as stock_days_module
from topspeed_ai_os.calculation import (
    INVENTORY_STOCK_DAYS_FORMULA_VERSION,
    InventoryDemandVelocityInputRef,
    InventoryDemandVelocityOutput,
    InventoryDemandVelocityResult,
    InventoryStockDaysError,
    InventoryStockDaysInputRef,
    InventoryStockDaysOutput,
    InventoryStockDaysResult,
    UnsupportedFormulaVersionError,
    calculate_inventory_demand_velocity,
    calculate_inventory_stock_days,
)
from topspeed_ai_os.contracts import ContractValidationError
from topspeed_ai_os.core.ids import InvalidIdentifierError

RUN_ID = "run_" + "01J" + ("0" * 23)
OTHER_RUN_ID = "run_" + "01K" + ("0" * 23)
WINDOW_START = date(2026, 9, 1)
WINDOW_END = "2026-09-30"
HASH_FIELDS = (
    "snapshot_at",
    "sku",
    "location",
    "available_qty",
    "source",
    "data_as_of",
)
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
]


class MutableString(str):
    pass


class TupleSubclass(tuple):
    pass


class MappingInventory(dict):
    pass


class DemandResultSubclass(InventoryDemandVelocityResult):
    pass


def _row(records, stat_date, units_sold=1, **changes):
    row = records()["CHANNEL_DAILY"]
    row.update(stat_date=stat_date, units_sold=units_sold)
    row.update(changes)
    return row


def _complete_rows(records, units=1):
    values = tuple(units(offset) for offset in range(30)) if callable(units) else (units,) * 30
    return tuple(
        _row(records, (WINDOW_START + timedelta(days=offset)).isoformat(), values[offset])
        for offset in range(30)
    )


def _demand(records, units=1, **changes):
    result = calculate_inventory_demand_velocity(
        _complete_rows(records, units),
        run_id=RUN_ID,
        window_end_date=WINDOW_END,
    )
    return replace(result, **changes) if changes else result


def _demand_for_sku(records, sku):
    rows = tuple(dict(row, sku=sku) for row in _complete_rows(records))
    return calculate_inventory_demand_velocity(
        rows,
        run_id=RUN_ID,
        window_end_date=WINDOW_END,
    )


def _inventory(records, **changes):
    inventory = records()["INVENTORY"]
    inventory.update(changes)
    return inventory


def _calculate(records, *, inventory_changes=None, demand=None, **changes):
    inventory = _inventory(records, **(inventory_changes or {}))
    demand_result = _demand(records) if demand is None else demand
    arguments = {"run_id": RUN_ID}
    arguments.update(changes)
    return calculate_inventory_stock_days(inventory, demand_result, **arguments)


def _canonical_hash(payload):
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(serialized).hexdigest()}"


def _hash(number):
    return f"sha256:{number:064x}"


def _decimal_context_state(context):
    return {
        "prec": context.prec,
        "rounding": context.rounding,
        "Emin": context.Emin,
        "Emax": context.Emax,
        "capitals": context.capitals,
        "clamp": context.clamp,
        "traps": tuple(
            sorted((signal.__name__, enabled) for signal, enabled in context.traps.items())
        ),
        "flags": tuple(
            sorted((signal.__name__, enabled) for signal, enabled in context.flags.items())
        ),
    }


def _demand_payload(demand):
    return {
        "metric_family": demand.metric_family,
        "formula_version": demand.formula_version,
        "channel": demand.channel,
        "sku": demand.sku,
        "window_start_date": demand.window_start_date,
        "window_end_date": demand.window_end_date,
        "avg_daily_units": demand.outputs[0].value,
        "input_refs": [
            {
                "contract_name": ref.contract_name,
                "natural_key": list(ref.natural_key),
                "source": ref.source,
                "data_as_of": ref.data_as_of,
                "input_hash": ref.input_hash,
            }
            for ref in demand.input_refs
        ],
    }


def _subclassed_demand(demand):
    return DemandResultSubclass(*(getattr(demand, field.name) for field in fields(demand)))


def test_exact_public_exports_formula_constant_and_identities():
    assert calculation_package.__all__ == FINAL_EXPORTS
    assert INVENTORY_STOCK_DAYS_FORMULA_VERSION == "topspeed.calculation.inventory_stock_days.v1"
    assert calculation_package.InventoryStockDaysResult is InventoryStockDaysResult
    assert calculation_package.calculate_inventory_stock_days is calculate_inventory_stock_days


def test_exact_public_function_signature():
    signature = inspect.signature(calculate_inventory_stock_days)
    parameters = list(signature.parameters.values())
    assert [parameter.name for parameter in parameters] == [
        "inventory",
        "demand_velocity",
        "run_id",
        "formula_version",
    ]
    assert parameters[0].annotation == Mapping[str, object]
    assert parameters[1].annotation is InventoryDemandVelocityResult
    assert parameters[2].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters[2].default is inspect.Parameter.empty
    assert parameters[3].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters[3].default == INVENTORY_STOCK_DAYS_FORMULA_VERSION
    assert signature.return_annotation is InventoryStockDaysResult


def test_mapping_subclass_inventory_is_accepted(records):
    inventory = MappingInventory(_inventory(records))
    result = calculate_inventory_stock_days(inventory, _demand(records), run_id=RUN_ID)
    assert result.status == "SUCCESS"


@pytest.mark.parametrize("inventory", [None, [], (), "inventory", 1])
def test_non_mapping_inventory_is_first_boundary(inventory):
    with pytest.raises(TypeError):
        calculate_inventory_stock_days(
            inventory,
            object(),
            run_id="invalid",
            formula_version="unsupported",
        )


def test_contract_validation_precedes_demand_identity(records):
    inventory = _inventory(records)
    inventory.pop("sku")
    with pytest.raises(ContractValidationError):
        calculate_inventory_stock_days(
            inventory,
            object(),
            run_id="invalid",
            formula_version="unsupported",
        )


def test_exact_schema_only_authority_and_argument(records, monkeypatch):
    calls = []
    authority = stock_days_module.validate_schema_only

    def recording_authority(contract_name, record):
        calls.append((contract_name, record))
        return authority(contract_name, record)

    inventory = _inventory(records)
    monkeypatch.setattr(stock_days_module, "validate_schema_only", recording_authority)
    calculate_inventory_stock_days(inventory, _demand(records), run_id=RUN_ID)
    assert calls == [("INVENTORY", inventory)]


def test_contract_exception_instance_propagates_unchanged(records, monkeypatch):
    sentinel = ContractValidationError("INVENTORY", ["sentinel"])

    def failing_authority(contract_name, record):
        raise sentinel

    monkeypatch.setattr(stock_days_module, "validate_schema_only", failing_authority)
    with pytest.raises(ContractValidationError) as captured:
        _calculate(records)
    assert captured.value is sentinel


def test_demand_requires_exact_result_identity_after_contract(records):
    demand = _demand(records)
    with pytest.raises(TypeError):
        calculate_inventory_stock_days(
            _inventory(records),
            _subclassed_demand(demand),
            run_id=RUN_ID,
        )


def test_demand_error_status_precedes_formula_boundary(records):
    demand = calculate_inventory_demand_velocity(
        _complete_rows(records)[:-1],
        run_id=RUN_ID,
        window_end_date=WINDOW_END,
    )
    with pytest.raises(ValueError):
        calculate_inventory_stock_days(
            _inventory(records),
            demand,
            run_id="invalid",
            formula_version="unsupported",
        )


def test_formula_version_rejects_str_subclass_before_supported_comparison(records):
    with pytest.raises(TypeError):
        _calculate(records, formula_version=MutableString(INVENTORY_STOCK_DAYS_FORMULA_VERSION))


def test_supported_type_wrong_formula_uses_existing_exception(records):
    with pytest.raises(UnsupportedFormulaVersionError):
        _calculate(records, formula_version="unsupported")


def test_formula_boundary_precedes_run_id_boundary(records):
    with pytest.raises(UnsupportedFormulaVersionError):
        _calculate(records, formula_version="unsupported", run_id="invalid")


def test_run_id_rejects_str_subclass_before_core_authority(records):
    with pytest.raises(TypeError):
        _calculate(records, run_id=MutableString(RUN_ID))


def test_invalid_run_id_propagates_core_exception(records):
    with pytest.raises(InvalidIdentifierError):
        _calculate(records, run_id="invalid")


def test_core_run_id_exception_instance_propagates_unchanged(records, monkeypatch):
    sentinel = InvalidIdentifierError("sentinel")

    def failing_authority(value):
        raise sentinel

    monkeypatch.setattr(stock_days_module, "require_valid_run_id", failing_authority)
    with pytest.raises(InvalidIdentifierError) as captured:
        _calculate(records)
    assert captured.value is sentinel


def test_run_id_boundary_precedes_sku_coherence(records):
    demand = _demand_for_sku(records, "TS-OTHER-002")
    with pytest.raises(InvalidIdentifierError):
        _calculate(records, demand=demand, run_id="invalid")


def test_exact_sku_mismatch_is_rejected(records):
    demand = _demand_for_sku(records, "TS-OTHER-002")
    with pytest.raises(ValueError):
        _calculate(records, demand=demand)


def test_unequal_location_and_channel_are_accepted_and_preserved(records):
    result = _calculate(records)
    assert result.location == "coupang_fulfillment"
    assert result.demand_channel == "coupang"
    assert result.location != result.demand_channel


def test_output_shape_boundary_precedes_output_value_boundary(records):
    demand = _demand(records)
    object.__setattr__(demand, "outputs", ())
    with pytest.raises(ValueError):
        _calculate(records, demand=demand)


@pytest.mark.parametrize("value", [MutableString("1"), "1.0000", "01", "-1", "1e0"])
def test_demand_output_value_boundary_rejects_noncanonical_values(records, value):
    demand = _demand(records)
    object.__setattr__(demand.outputs[0], "value", value)
    with pytest.raises((TypeError, ValueError)):
        _calculate(records, demand=demand)


def test_boundary_failure_creates_no_result(records, monkeypatch):
    def forbidden_result(*args, **kwargs):
        raise AssertionError("result construction must not occur")

    monkeypatch.setattr(stock_days_module, "InventoryStockDaysResult", forbidden_result)
    with pytest.raises(UnsupportedFormulaVersionError):
        _calculate(records, formula_version="unsupported")


def test_positive_demand_success_and_authoritative_formula(records):
    demand = _demand(records, outputs=(InventoryDemandVelocityOutput("avg_daily_units", "24.5"),))
    result = _calculate(records, demand=demand)
    assert result.status == "SUCCESS"
    assert result.outputs == (InventoryStockDaysOutput("stock_days", "11.6327"),)
    assert result.reason is None
    assert result.errors == ()


def test_zero_available_positive_demand_is_success_zero(records):
    result = _calculate(records, inventory_changes={"available_qty": 0})
    assert result.status == "SUCCESS"
    assert result.outputs == (InventoryStockDaysOutput("stock_days", "0"),)


def test_negative_available_is_exact_error_without_arithmetic(records, monkeypatch):
    def forbidden_parse(value):
        raise AssertionError("negative inventory must not enter arithmetic")

    monkeypatch.setattr(stock_days_module, "_parse_fixed_point", forbidden_parse)
    result = _calculate(records, inventory_changes={"available_qty": -1})
    assert result.status == "ERROR"
    assert result.outputs == ()
    assert result.reason is None
    assert result.errors == (
        InventoryStockDaysError(
            "INVALID_INPUT",
            "available_qty",
            (result.input_refs[0].input_hash,),
        ),
    )


def test_zero_demand_is_exact_partial_outcome(records):
    demand = _demand(records, outputs=(InventoryDemandVelocityOutput("avg_daily_units", "0"),))
    result = _calculate(records, demand=demand)
    assert result.status == "PARTIAL"
    assert result.outputs == (InventoryStockDaysOutput("stock_days", None),)
    assert result.reason == "ZERO_DEMAND"
    assert result.errors == ()


@pytest.mark.parametrize(
    ("available_qty", "demand_value", "expected"),
    [
        (1, "20000", "0.0001"),
        (1, "40000", "0"),
        (1, "3", "0.3333"),
        (2, "3", "0.6667"),
        (1162996, "100000", "11.63"),
        (10**80, "0.0001", "1" + ("0" * 84)),
    ],
)
def test_exact_rational_half_up_rounding(records, available_qty, demand_value, expected):
    demand = _demand(
        records,
        outputs=(InventoryDemandVelocityOutput("avg_daily_units", demand_value),),
    )
    result = _calculate(
        records,
        inventory_changes={"available_qty": available_qty},
        demand=demand,
    )
    assert result.outputs[0].value == expected


def test_decimal_context_and_default_context_do_not_affect_result(records):
    demand = _demand(records, outputs=(InventoryDemandVelocityOutput("avg_daily_units", "3"),))
    original_context = decimal.getcontext().copy()
    original_default = decimal.DefaultContext.copy()
    try:
        decimal.getcontext().prec = 2
        decimal.getcontext().rounding = decimal.ROUND_DOWN
        decimal.DefaultContext.prec = 3
        decimal.DefaultContext.rounding = decimal.ROUND_UP
        context_before_first = _decimal_context_state(decimal.getcontext())
        default_before_first = _decimal_context_state(decimal.DefaultContext)
        first = _calculate(records, demand=demand)
        assert _decimal_context_state(decimal.getcontext()) == context_before_first
        assert _decimal_context_state(decimal.DefaultContext) == default_before_first
        decimal.getcontext().prec = 50
        decimal.getcontext().rounding = decimal.ROUND_FLOOR
        decimal.DefaultContext.prec = 60
        decimal.DefaultContext.rounding = decimal.ROUND_CEILING
        context_before_second = _decimal_context_state(decimal.getcontext())
        default_before_second = _decimal_context_state(decimal.DefaultContext)
        second = _calculate(records, demand=demand)
        assert _decimal_context_state(decimal.getcontext()) == context_before_second
        assert _decimal_context_state(decimal.DefaultContext) == default_before_second
    finally:
        decimal.setcontext(original_context)
        decimal.DefaultContext.prec = original_default.prec
        decimal.DefaultContext.rounding = original_default.rounding
    assert first == second


@pytest.mark.parametrize(
    "value",
    [
        "-1",
        "+1",
        "01",
        "00",
        "0.0",
        "1.0000",
        "1.",
        ".1",
        "1e2",
        "0.12345",
        "²",
        "\u0661",
        "\uff11",
    ],
)
def test_output_rejects_noncanonical_forms(value):
    with pytest.raises(ValueError):
        InventoryStockDaysOutput("stock_days", value)


@pytest.mark.parametrize("value", [None, "0", "1", "0.0001", "12.3456", "100.01"])
def test_output_accepts_exact_approved_forms(value):
    assert InventoryStockDaysOutput("stock_days", value).value == value


def test_output_rejects_string_subclasses_and_wrong_name():
    with pytest.raises(TypeError):
        InventoryStockDaysOutput(MutableString("stock_days"), "1")
    with pytest.raises(TypeError):
        InventoryStockDaysOutput("stock_days", MutableString("1"))
    with pytest.raises(ValueError):
        InventoryStockDaysOutput("metric", "1")


@pytest.mark.parametrize(
    ("carrier", "field_names"),
    [
        (InventoryStockDaysOutput, ("name", "value")),
        (InventoryStockDaysError, ("code", "field", "input_hashes")),
        (
            InventoryStockDaysInputRef,
            (
                "kind",
                "contract_name",
                "natural_key",
                "source",
                "data_as_of",
                "input_hash",
                "metric_family",
                "formula_version",
                "channel",
                "sku",
                "window_start_date",
                "window_end_date",
                "avg_daily_units",
                "upstream_input_refs",
            ),
        ),
        (
            InventoryStockDaysResult,
            (
                "metric_family",
                "formula_version",
                "run_id",
                "sku",
                "location",
                "demand_channel",
                "snapshot_at",
                "window_start_date",
                "window_end_date",
                "status",
                "outputs",
                "input_refs",
                "reason",
                "errors",
                "input_hash",
            ),
        ),
    ],
)
def test_carriers_are_frozen_slotted_dataclasses_with_exact_fields(carrier, field_names):
    assert is_dataclass(carrier)
    assert tuple(field.name for field in fields(carrier)) == field_names
    assert "__slots__" in carrier.__dict__


def test_deep_immutability_and_no_dynamic_attributes(records):
    result = _calculate(records)
    with pytest.raises(FrozenInstanceError):
        result.status = "ERROR"
    with pytest.raises((FrozenInstanceError, TypeError)):
        result.new_field = "forbidden"
    with pytest.raises(TypeError):
        result.input_refs[0] = result.input_refs[0]
    assert not hasattr(result, "__dict__")
    assert all(not hasattr(item, "__dict__") for item in (*result.outputs, *result.input_refs))


@pytest.mark.parametrize(
    "arguments",
    [
        ("OTHER", "available_qty", (_hash(1),)),
        ("INVALID_INPUT", "other", (_hash(1),)),
        ("INVALID_INPUT", "available_qty", ()),
        ("INVALID_INPUT", "available_qty", (_hash(1), _hash(2))),
        ("INVALID_INPUT", "available_qty", ("invalid",)),
    ],
)
def test_error_rejects_invalid_literals_hash_cardinality_and_hash_form(arguments):
    with pytest.raises(ValueError):
        InventoryStockDaysError(*arguments)


@pytest.mark.parametrize("hashes", [[_hash(1)], TupleSubclass((_hash(1),)), {_hash(1)}])
def test_error_requires_exact_hash_tuple(hashes):
    with pytest.raises(TypeError):
        InventoryStockDaysError("INVALID_INPUT", "available_qty", hashes)


def test_error_rejects_exact_string_subclasses():
    with pytest.raises(TypeError):
        InventoryStockDaysError(MutableString("INVALID_INPUT"), "available_qty", (_hash(1),))
    with pytest.raises(TypeError):
        InventoryStockDaysError("INVALID_INPUT", "available_qty", (MutableString(_hash(1)),))


def test_inventory_reference_exact_projection_and_kind_shape(records):
    result = _calculate(records)
    ref = result.input_refs[0]
    inventory = _inventory(records)
    assert ref.kind == "INVENTORY"
    assert ref.contract_name == "INVENTORY"
    assert ref.natural_key == (
        inventory["snapshot_at"],
        inventory["sku"],
        inventory["location"],
    )
    assert ref.source == inventory["source"]
    assert ref.data_as_of == inventory["data_as_of"]
    assert ref.sku == inventory["sku"]
    assert ref.upstream_input_refs == ()
    assert all(
        getattr(ref, field) is None
        for field in (
            "metric_family",
            "formula_version",
            "channel",
            "window_start_date",
            "window_end_date",
            "avg_daily_units",
        )
    )


def test_demand_reference_exact_projection_and_preserved_upstream_refs(records):
    demand = _demand(records)
    result = _calculate(records, demand=demand)
    ref = result.input_refs[1]
    assert ref.kind == "DEMAND_VELOCITY"
    assert ref.contract_name is None
    assert ref.natural_key is None
    assert ref.source is None
    assert ref.data_as_of is None
    assert ref.metric_family == demand.metric_family
    assert ref.formula_version == demand.formula_version
    assert ref.channel == demand.channel
    assert ref.sku == demand.sku
    assert ref.window_start_date == demand.window_start_date
    assert ref.window_end_date == demand.window_end_date
    assert ref.avg_daily_units == demand.outputs[0].value
    assert ref.upstream_input_refs is demand.input_refs


def test_inventory_reference_rejects_wrong_combinations(records):
    ref = _calculate(records).input_refs[0]
    with pytest.raises(ValueError):
        replace(ref, kind="OTHER")
    with pytest.raises(ValueError):
        replace(ref, contract_name="OTHER")
    with pytest.raises(ValueError):
        replace(ref, natural_key=(ref.natural_key[0], "TS-OTHER-002", ref.natural_key[2]))
    with pytest.raises(ValueError):
        replace(ref, channel="coupang")
    with pytest.raises(ValueError):
        replace(ref, upstream_input_refs=_demand(records).input_refs)


def test_demand_reference_rejects_wrong_combinations_and_fixed_literals(records):
    ref = _calculate(records).input_refs[1]
    with pytest.raises(ValueError):
        replace(ref, contract_name="INVENTORY")
    with pytest.raises(ValueError):
        replace(ref, metric_family="OTHER")
    with pytest.raises(ValueError):
        replace(ref, formula_version="other")
    with pytest.raises(ValueError):
        replace(ref, channel=None)
    with pytest.raises(ValueError):
        replace(ref, avg_daily_units=None)


def test_input_reference_rejects_exact_string_subclasses(records):
    inventory_ref, demand_ref = _calculate(records).input_refs
    for changes in (
        {"kind": MutableString(inventory_ref.kind)},
        {"contract_name": MutableString(inventory_ref.contract_name)},
        {"source": MutableString(inventory_ref.source)},
        {"data_as_of": MutableString(inventory_ref.data_as_of)},
        {"input_hash": MutableString(inventory_ref.input_hash)},
        {"sku": MutableString(inventory_ref.sku)},
        {
            "natural_key": (
                MutableString(inventory_ref.natural_key[0]),
                inventory_ref.natural_key[1],
                inventory_ref.natural_key[2],
            )
        },
    ):
        with pytest.raises(TypeError):
            replace(inventory_ref, **changes)
    for field in (
        "metric_family",
        "formula_version",
        "channel",
        "window_start_date",
        "window_end_date",
        "avg_daily_units",
    ):
        with pytest.raises(TypeError):
            replace(demand_ref, **{field: MutableString(getattr(demand_ref, field))})


def test_input_reference_rejects_tuple_and_nested_carrier_subclasses(records):
    inventory_ref, demand_ref = _calculate(records).input_refs
    with pytest.raises(TypeError):
        replace(inventory_ref, natural_key=TupleSubclass(inventory_ref.natural_key))
    with pytest.raises(TypeError):
        replace(demand_ref, upstream_input_refs=TupleSubclass(demand_ref.upstream_input_refs))
    subclassed = InventoryDemandVelocityInputRef(
        "CHANNEL_DAILY",
        ("coupang", "2026-09-01", "TS-KITCHEN-001"),
        "source",
        "as-of",
        _hash(1),
    )

    class RefSubclass(InventoryDemandVelocityInputRef):
        pass

    nested = RefSubclass(*(getattr(subclassed, field.name) for field in fields(subclassed)))
    with pytest.raises(TypeError):
        replace(demand_ref, upstream_input_refs=(nested, *demand_ref.upstream_input_refs[1:]))


def test_demand_reference_enforces_window_order_cardinality_and_coherence(records):
    demand_ref = _calculate(records).input_refs[1]
    with pytest.raises(ValueError):
        replace(demand_ref, window_start_date="2026-09-02")
    with pytest.raises(ValueError):
        replace(demand_ref, upstream_input_refs=demand_ref.upstream_input_refs[:-1])
    with pytest.raises(ValueError):
        replace(demand_ref, upstream_input_refs=tuple(reversed(demand_ref.upstream_input_refs)))
    incoherent = replace(
        demand_ref.upstream_input_refs[0], natural_key=("other", "2026-09-01", demand_ref.sku)
    )
    with pytest.raises(ValueError):
        replace(demand_ref, upstream_input_refs=(incoherent, *demand_ref.upstream_input_refs[1:]))


def test_demand_reference_recomputes_exact_projected_hash(records):
    demand_ref = _calculate(records).input_refs[1]
    with pytest.raises(ValueError):
        replace(demand_ref, input_hash=_hash(999))
    with pytest.raises(ValueError):
        replace(demand_ref, avg_daily_units="2")


def test_result_rejects_exact_string_and_tuple_subclasses(records):
    result = _calculate(records)
    for field in (
        "metric_family",
        "formula_version",
        "run_id",
        "sku",
        "location",
        "demand_channel",
        "snapshot_at",
        "window_start_date",
        "window_end_date",
        "status",
        "input_hash",
    ):
        with pytest.raises(TypeError):
            replace(result, **{field: MutableString(getattr(result, field))})
    with pytest.raises(TypeError):
        replace(result, outputs=TupleSubclass(result.outputs))
    with pytest.raises(TypeError):
        replace(result, input_refs=list(result.input_refs))
    with pytest.raises(TypeError):
        replace(result, errors=(item for item in ()))


def test_result_enforces_fixed_literals_and_provenance_coherence(records):
    result = _calculate(records)
    for changes in (
        {"metric_family": "OTHER"},
        {"formula_version": "other"},
        {"status": "UNKNOWN"},
        {"reason": "OTHER"},
        {"sku": "TS-OTHER-002"},
        {"location": "other"},
        {"demand_channel": "other"},
        {"snapshot_at": "2026-09-17T00:00:00+09:00"},
        {"window_start_date": "2026-09-02"},
        {"window_end_date": "2026-10-01"},
        {"input_refs": tuple(reversed(result.input_refs))},
        {"input_hash": _hash(999)},
    ):
        with pytest.raises(ValueError):
            replace(result, **changes)


def test_result_enforces_all_three_exact_shapes(records):
    success = _calculate(records)
    partial = _calculate(
        records,
        demand=_demand(records, outputs=(InventoryDemandVelocityOutput("avg_daily_units", "0"),)),
    )
    error = _calculate(records, inventory_changes={"available_qty": -1})
    with pytest.raises(ValueError):
        replace(success, outputs=())
    with pytest.raises(ValueError):
        replace(success, reason="ZERO_DEMAND")
    with pytest.raises(ValueError):
        replace(partial, reason=None)
    with pytest.raises(ValueError):
        replace(partial, outputs=(InventoryStockDaysOutput("stock_days", "0"),))
    with pytest.raises(ValueError):
        replace(error, errors=())
    with pytest.raises(ValueError):
        replace(error, outputs=(InventoryStockDaysOutput("stock_days", "0"),))
    wrong_error = InventoryStockDaysError("INVALID_INPUT", "available_qty", (_hash(999),))
    with pytest.raises(ValueError):
        replace(error, errors=(wrong_error,))


def test_inventory_hash_payload_is_exact_and_independently_reproduced(records):
    inventory = _inventory(records)
    result = calculate_inventory_stock_days(inventory, _demand(records), run_id=RUN_ID)
    payload = {field: inventory[field] for field in HASH_FIELDS}
    assert result.input_refs[0].input_hash == _canonical_hash(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("snapshot_at", "2026-09-16T09:01:00+09:00"),
        ("sku", "TS-KITCHEN-002"),
        ("location", "other_location"),
        ("available_qty", 286),
        ("source", "other_source"),
        ("data_as_of", "2026-09-16T09:01:00+09:00"),
    ],
)
def test_each_included_inventory_field_changes_inventory_hash(records, field, value):
    baseline_inventory = _inventory(records)
    baseline_demand = _demand(records)
    if field == "sku":
        baseline_demand = _demand_for_sku(records, value)
    baseline = calculate_inventory_stock_days(baseline_inventory, _demand(records), run_id=RUN_ID)
    changed = calculate_inventory_stock_days(
        _inventory(records, **{field: value}),
        baseline_demand,
        run_id=RUN_ID,
    )
    assert changed.input_refs[0].input_hash != baseline.input_refs[0].input_hash


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("on_hand_qty", 999),
        ("reserved_qty", 999),
        ("inbound_qty", 999),
        ("avg_daily_units", "999"),
        ("stock_days", "999"),
        ("lead_time_days", 99),
        ("safety_stock_qty", 99),
        ("reorder_point_qty", 99),
        ("recommended_order_qty", 99),
        ("run_id", OTHER_RUN_ID),
        ("created_at", "2026-09-16T09:11:00+09:00"),
    ],
)
def test_each_excluded_inventory_field_does_not_change_hash(records, field, value):
    baseline = _calculate(records)
    changed = _calculate(records, inventory_changes={field: value})
    assert changed.input_refs[0].input_hash == baseline.input_refs[0].input_hash
    assert changed.input_hash == baseline.input_hash


def test_demand_hash_payload_is_exact_and_independently_reproduced(records):
    demand = _demand(records)
    result = _calculate(records, demand=demand)
    assert result.input_refs[1].input_hash == _canonical_hash(_demand_payload(demand))
    assert result.input_refs[1].upstream_input_refs == demand.input_refs


def test_every_demand_hash_payload_field_is_sensitive(records):
    demand = _demand(records)
    payload = _demand_payload(demand)
    baseline = _canonical_hash(payload)
    changes = {
        "metric_family": "OTHER",
        "formula_version": "other",
        "channel": "other",
        "sku": "TS-OTHER-002",
        "window_start_date": "2026-09-02",
        "window_end_date": "2026-10-01",
        "avg_daily_units": "2",
        "input_refs": [*payload["input_refs"][:-1]],
    }
    for field, value in changes.items():
        changed = dict(payload)
        changed[field] = value
        assert _canonical_hash(changed) != baseline


def test_demand_hash_preserves_order_cardinality_and_projection_values(records):
    demand = _demand(records)
    payload = _demand_payload(demand)
    assert len(payload["input_refs"]) == 30
    assert [item["natural_key"] for item in payload["input_refs"]] == [
        list(ref.natural_key) for ref in demand.input_refs
    ]
    assert all(
        tuple(item) == ("contract_name", "natural_key", "source", "data_as_of", "input_hash")
        for item in (tuple(projected) for projected in payload["input_refs"])
    )


def test_identical_repeated_upstream_hashes_preserve_cardinality(records):
    demand = _demand(records)
    repeated_refs = tuple(replace(ref, input_hash=_hash(1)) for ref in demand.input_refs)
    demand = replace(demand, input_refs=repeated_refs)
    result = _calculate(records, demand=demand)
    embedded = result.input_refs[1].upstream_input_refs
    assert len(embedded) == 30
    assert tuple(ref.input_hash for ref in embedded) == (_hash(1),) * 30


def test_caller_run_ids_are_excluded_from_all_hashes(records):
    first = _calculate(records, run_id=RUN_ID)
    second = _calculate(records, run_id=OTHER_RUN_ID)
    assert first.run_id != second.run_id
    assert replace(first, run_id=second.run_id) == second
    assert first.input_hash == second.input_hash


def test_final_hash_is_exact_and_independently_reproduced(records):
    result = _calculate(records)
    expected = _canonical_hash(
        {
            "formula_version": INVENTORY_STOCK_DAYS_FORMULA_VERSION,
            "inventory_input_hash": result.input_refs[0].input_hash,
            "demand_input_hash": result.input_refs[1].input_hash,
        }
    )
    assert result.input_hash == expected


def test_same_validated_inputs_are_structurally_deterministic(records):
    inventory = _inventory(records)
    demand = _demand(records)
    first = calculate_inventory_stock_days(inventory, demand, run_id=RUN_ID)
    second = calculate_inventory_stock_days(inventory, demand, run_id=RUN_ID)
    assert first == second


def test_inputs_and_upstream_result_are_not_mutated(records):
    inventory = _inventory(records)
    demand = _demand(records)
    original_inventory = deepcopy(inventory)
    original_demand = deepcopy(demand)
    calculate_inventory_stock_days(inventory, demand, run_id=RUN_ID)
    assert inventory == original_inventory
    assert demand == original_demand


def test_source_uses_exact_contract_authority_and_no_forbidden_substitution():
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "topspeed_ai_os"
        / "calculation"
        / "inventory_stock_days.py"
    )
    source = source_path.read_text(encoding="utf-8")
    assert 'validate_schema_only("INVENTORY", inventory)' in source
    assert "validate_contract" not in source
    assert "validate_record" not in source
    assert "known_skus" not in source
    assert "PRODUCT_MASTER" not in source


def _attribute_path(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return tuple(reversed(parts))
    return ()


def test_production_has_only_deterministic_dependencies_and_no_forbidden_capabilities():
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "topspeed_ai_os"
        / "calculation"
        / "inventory_stock_days.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module)
    assert imported_modules == {
        "collections.abc",
        "dataclasses",
        "datetime",
        "re",
        "typing",
        "topspeed_ai_os.contracts",
        "topspeed_ai_os.core.canonical",
        "topspeed_ai_os.core.ids",
        "contribution_margin",
        "inventory_demand_velocity",
    }

    forbidden_names = {
        "open",
        "eval",
        "exec",
        "compile",
        "getcontext",
        "setcontext",
        "today",
        "now",
        "utcnow",
        "time",
        "random",
        "secrets",
        "uuid",
        "subprocess",
        "socket",
        "environ",
        "getenv",
        "generate_run_id",
        "requests",
        "urllib",
    }
    used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    used_attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert (forbidden_names - {"compile"}).isdisjoint(used_names | used_attributes)
    call_targets = {
        _attribute_path(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    assert ("compile",) not in call_targets
    assert ("builtins", "compile") not in call_targets
    assert ("re", "compile") in call_targets


def test_no_new_skip_skipif_or_xfail_marks_exist():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    attribute_paths = {
        _attribute_path(node) for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    forbidden_markers = {
        ("pytest", "mark", "skip"),
        ("pytest", "mark", "skipif"),
        ("pytest", "mark", "xfail"),
    }
    assert forbidden_markers.isdisjoint(attribute_paths)
