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
import topspeed_ai_os.calculation.inventory_demand_velocity as velocity_module
from topspeed_ai_os.calculation import (
    INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION,
    CalculationOutput,
    InventoryDemandVelocityError,
    InventoryDemandVelocityInputRef,
    InventoryDemandVelocityOutput,
    InventoryDemandVelocityResult,
    UnsupportedFormulaVersionError,
    calculate_inventory_demand_velocity,
)
from topspeed_ai_os.contracts import ContractValidationError
from topspeed_ai_os.core.ids import InvalidIdentifierError

RUN_ID = "run_" + "01J" + ("0" * 23)
OTHER_RUN_ID = "run_" + "01K" + ("0" * 23)
WINDOW_START = date(2026, 9, 1)
WINDOW_END = "2026-09-30"
HASH_FIELDS = ("channel", "stat_date", "sku", "units_sold", "source", "data_as_of")
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


class MutableString(str):
    pass


class TupleSubclass(tuple):
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


def _calculate(rows, **changes):
    arguments = {"run_id": RUN_ID, "window_end_date": WINDOW_END}
    arguments.update(changes)
    return calculate_inventory_demand_velocity(rows, **arguments)


def _independent_hash(row):
    payload = {field: row[field] for field in HASH_FIELDS}
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


def _ref(stat_date, *, channel="coupang", sku="TS-KITCHEN-001", number=1):
    return InventoryDemandVelocityInputRef(
        contract_name="CHANNEL_DAILY",
        natural_key=(channel, stat_date, sku),
        source="fixture",
        data_as_of="2026-09-30T00:00:00+00:00",
        input_hash=_hash(number),
    )


def _direct_success(**changes):
    references = tuple(
        _ref((WINDOW_START + timedelta(days=offset)).isoformat(), number=offset + 1)
        for offset in range(30)
    )
    values = {
        "metric_family": "INVENTORY_DEMAND_VELOCITY",
        "formula_version": INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION,
        "run_id": RUN_ID,
        "channel": "coupang",
        "sku": "TS-KITCHEN-001",
        "window_start_date": "2026-09-01",
        "window_end_date": WINDOW_END,
        "status": "SUCCESS",
        "outputs": (InventoryDemandVelocityOutput("avg_daily_units", "1"),),
        "input_refs": references,
        "errors": (),
    }
    values.update(changes)
    return InventoryDemandVelocityResult(**values)


def _codes(result):
    return tuple(error.code for error in result.errors)


def test_exact_public_exports_and_formula_constant():
    assert calculation_package.__all__ == FINAL_EXPORTS
    assert (
        INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION
        == "topspeed.calculation.inventory_demand_velocity.v1"
    )


def test_exact_public_function_signature():
    signature = inspect.signature(calculate_inventory_demand_velocity)
    parameters = list(signature.parameters.values())
    assert [parameter.name for parameter in parameters] == [
        "channel_daily",
        "run_id",
        "window_end_date",
        "formula_version",
    ]
    assert parameters[0].annotation == tuple[Mapping[str, object], ...]
    assert parameters[1].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters[1].default is inspect.Parameter.empty
    assert parameters[2].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters[2].default is inspect.Parameter.empty
    assert parameters[3].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters[3].default == INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION
    assert signature.return_annotation is InventoryDemandVelocityResult


def test_exact_tuple_is_accepted(records):
    assert _calculate(_complete_rows(records)).status == "SUCCESS"


@pytest.mark.parametrize("container", [[], {}, set(), (item for item in ())])
def test_non_tuple_containers_are_rejected_before_other_boundaries(container):
    with pytest.raises(TypeError):
        calculate_inventory_demand_velocity(
            container,
            run_id="invalid",
            window_end_date="invalid",
            formula_version="unsupported",
        )


def test_tuple_subclass_is_rejected(records):
    with pytest.raises(TypeError):
        _calculate(TupleSubclass(_complete_rows(records)))


def test_mapping_element_boundary_precedes_nonempty_and_formula():
    with pytest.raises(TypeError):
        calculate_inventory_demand_velocity(
            (None,), run_id="invalid", window_end_date="invalid", formula_version="unsupported"
        )


def test_empty_tuple_precedes_formula_boundary():
    with pytest.raises(ValueError, match="non-empty"):
        calculate_inventory_demand_velocity(
            (), run_id="invalid", window_end_date="invalid", formula_version="unsupported"
        )


def test_formula_boundary_precedes_run_id(records):
    rows = _complete_rows(records)
    with pytest.raises(TypeError):
        _calculate(rows, formula_version=MutableString(INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION))
    with pytest.raises(UnsupportedFormulaVersionError):
        _calculate(rows, run_id="invalid", formula_version="unsupported")


def test_run_id_boundary_precedes_window_date(records):
    rows = _complete_rows(records)
    with pytest.raises(TypeError):
        _calculate(rows, run_id=MutableString(RUN_ID), window_end_date="invalid")
    with pytest.raises(InvalidIdentifierError):
        _calculate(rows, run_id="invalid", window_end_date="invalid")


@pytest.mark.parametrize(
    "bad_date",
    [
        "2026-9-30",
        "2026/09/30",
        " 2026-09-30",
        "2026-09-30 ",
        "2026-02-30",
        "\uff12\uff10\uff12\uff16-\uff10\uff19-\uff13\uff10",
        "2026-09-30Z",
    ],
)
def test_window_date_rejects_noncanonical_or_impossible_forms(records, bad_date):
    with pytest.raises(ValueError):
        _calculate(_complete_rows(records), window_end_date=bad_date)


@pytest.mark.parametrize("bad_date", [None, date(2026, 9, 30), MutableString(WINDOW_END)])
def test_window_date_requires_exact_string(records, bad_date):
    with pytest.raises(TypeError):
        _calculate(_complete_rows(records), window_end_date=bad_date)


def test_window_boundary_precedes_contract_validation(records):
    invalid = _row(records, "2026-09-01")
    invalid.pop("orders")
    with pytest.raises(ValueError):
        _calculate((invalid,), window_end_date="invalid")


def test_h001_validates_in_original_order_and_stops_at_first_contract_failure(records, monkeypatch):
    first = _row(records, "2026-09-01")
    second = _row(records, "2026-09-02")
    second.pop("orders")
    third = _row(records, "2026-09-03")
    calls = []
    authority = velocity_module.validate_schema_only

    def recording_authority(contract_name, row):
        calls.append(row)
        authority(contract_name, row)

    monkeypatch.setattr(velocity_module, "validate_schema_only", recording_authority)
    with pytest.raises(ContractValidationError):
        _calculate((first, second, third))
    assert calls == [first, second]


def test_contract_validation_precedes_mixed_channel_and_sku(records):
    invalid = _row(records, "2026-09-01", channel="other", sku="TS-OTHER-002")
    invalid.pop("orders")
    with pytest.raises(ContractValidationError):
        _calculate((invalid, _row(records, "2026-09-02")))


def test_mixed_channel_precedes_mixed_sku(records):
    rows = (
        _row(records, "2026-09-01"),
        _row(records, "2026-09-02", channel="other", sku="TS-OTHER-002"),
    )
    with pytest.raises(ValueError, match="one channel"):
        _calculate(rows)


def test_mixed_sku_is_rejected_after_channel(records):
    rows = (
        _row(records, "2026-09-01"),
        _row(records, "2026-09-02", sku="TS-OTHER-002"),
    )
    with pytest.raises(ValueError, match="one SKU"):
        _calculate(rows)


def test_boundary_failure_creates_no_result(records, monkeypatch):
    def forbidden_result(*_args, **_kwargs):
        raise AssertionError("boundary failure must not create a result")

    monkeypatch.setattr(velocity_module, "InventoryDemandVelocityResult", forbidden_result)
    with pytest.raises(UnsupportedFormulaVersionError):
        _calculate(_complete_rows(records), formula_version="unsupported")


@pytest.mark.parametrize(
    ("units", "expected"),
    [
        (0, "0"),
        (1, "1"),
        (10**100, "1" + ("0" * 100)),
    ],
)
def test_success_zero_integer_and_large_units(records, units, expected):
    result = _calculate(_complete_rows(records, units))
    assert result.status == "SUCCESS"
    assert result.outputs == (InventoryDemandVelocityOutput("avg_daily_units", expected),)
    assert len(result.input_refs) == 30
    assert result.errors == ()


def test_success_mixed_units_exact_average_and_inclusive_endpoints(records):
    result = _calculate(_complete_rows(records, lambda offset: offset))
    assert result.outputs[0].value == "14.5"
    assert result.window_start_date == "2026-09-01"
    assert result.window_end_date == "2026-09-30"
    assert result.input_refs[0].natural_key[1] == "2026-09-01"
    assert result.input_refs[-1].natural_key[1] == "2026-09-30"


def test_input_permutation_is_structurally_invariant(records):
    rows = _complete_rows(records, lambda offset: offset)
    assert _calculate(rows) == _calculate(tuple(reversed(rows)))


def test_integer_rounding_below_and_above_half_boundary(records):
    below = _complete_rows(records, 0)
    below = (dict(below[0], units_sold=1), *below[1:])
    above = _complete_rows(records, 0)
    above = (dict(above[0], units_sold=2), *above[1:])
    assert _calculate(below).outputs[0].value == "0.0333"
    assert _calculate(above).outputs[0].value == "0.0667"


def test_round_half_up_primitive_below_at_and_above_exact_tie():
    assert velocity_module._round_scaled_units(14) == 0
    assert velocity_module._round_scaled_units(15) == 1
    assert velocity_module._round_scaled_units(16) == 1


def _context_state(context):
    return (
        context.prec,
        context.rounding,
        context.Emin,
        context.Emax,
        tuple(context.flags.items()),
        tuple(context.traps.items()),
    )


def test_ambient_decimal_context_does_not_affect_or_change_result(records):
    context = decimal.getcontext()
    original = context.copy()
    try:
        context.prec = 2
        context.rounding = decimal.ROUND_DOWN
        context.clear_flags()
        before = _context_state(context)
        result = _calculate(_complete_rows(records, lambda offset: offset))
        assert result.outputs[0].value == "14.5"
        assert _context_state(context) == before
    finally:
        decimal.setcontext(original)


def test_runtime_output_is_ascii_fixed_point_without_exponent(records):
    value = _calculate(_complete_rows(records, 0)).outputs[0].value
    assert value == "0"
    assert value.isascii()
    assert "e" not in value.lower()


def test_out_of_window_errors_collect_every_supplied_row(records):
    rows = (
        *_complete_rows(records),
        _row(records, "2026-08-30"),
        _row(records, "2026-08-31"),
    )
    result = _calculate(rows)
    errors = tuple(error for error in result.errors if error.code == "OUT_OF_WINDOW")
    assert tuple(error.stat_date for error in errors) == ("2026-08-30", "2026-08-31")
    assert all(len(error.input_hashes) == 1 for error in errors)
    assert result.outputs == ()


def test_duplicate_date_distinct_hashes_and_cardinality_above_two(records):
    base = _complete_rows(records)
    duplicates = (
        dict(base[0], units_sold=2),
        dict(base[0], units_sold=3),
    )
    result = _calculate(base + duplicates)
    errors = tuple(error for error in result.errors if error.code == "DUPLICATE_DATE")
    assert len(errors) == 1
    assert errors[0].stat_date == "2026-09-01"
    assert len(errors[0].input_hashes) == 3
    assert errors[0].input_hashes == tuple(sorted(errors[0].input_hashes))


def test_duplicate_equal_hashes_and_input_refs_preserve_cardinality(records):
    base = _complete_rows(records)
    result = _calculate((*base, deepcopy(base[0])))
    duplicate = next(error for error in result.errors if error.code == "DUPLICATE_DATE")
    assert duplicate.input_hashes == (duplicate.input_hashes[0],) * 2
    matching_refs = tuple(ref for ref in result.input_refs if ref.natural_key[1] == "2026-09-01")
    assert len(matching_refs) == 2
    assert matching_refs[0] == matching_refs[1]


def test_missing_dates_have_empty_hashes_and_no_synthetic_refs(records):
    result = _calculate(_complete_rows(records)[:-2])
    missing = tuple(error for error in result.errors if error.code == "MISSING_DATE")
    assert tuple(error.stat_date for error in missing) == ("2026-09-29", "2026-09-30")
    assert all(error.input_hashes == () for error in missing)
    assert len(result.input_refs) == 28


def test_negative_units_collect_one_error_per_negative_row(records):
    rows = list(_complete_rows(records))
    rows[0] = dict(rows[0], units_sold=-1)
    rows.append(deepcopy(rows[0]))
    result = _calculate(tuple(rows))
    negatives = tuple(error for error in result.errors if error.code == "NEGATIVE_UNITS_SOLD")
    assert len(negatives) == 2
    assert negatives[0] == negatives[1]
    assert "DUPLICATE_DATE" in _codes(result)


def test_all_four_error_codes_collect_and_follow_canonical_order(records):
    rows = list(_complete_rows(records)[:-1])
    outside = _row(records, "2026-08-31", -1)
    rows.extend((outside, deepcopy(outside)))
    result = _calculate(tuple(reversed(rows)))
    assert set(_codes(result)) == {
        "OUT_OF_WINDOW",
        "DUPLICATE_DATE",
        "MISSING_DATE",
        "NEGATIVE_UNITS_SOLD",
    }
    assert result.errors == tuple(sorted(result.errors, key=velocity_module._error_sort_key))
    assert result.outputs == ()
    assert len(result.input_refs) == len(rows)


def test_exact_six_field_hash_payload_and_natural_key(records):
    row = _row(records, "2026-09-01", 7)
    result = _calculate((row,))
    reference = result.input_refs[0]
    assert reference.contract_name == "CHANNEL_DAILY"
    assert reference.natural_key == (row["channel"], row["stat_date"], row["sku"])
    assert reference.source == row["source"]
    assert reference.data_as_of == row["data_as_of"]
    assert reference.input_hash == _independent_hash(row)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("channel", "other"),
        ("stat_date", "2026-09-02"),
        ("sku", "TS-OTHER-002"),
        ("units_sold", 2),
        ("source", "other_source"),
        ("data_as_of", "2026-09-30T01:00:00+00:00"),
    ],
)
def test_each_included_hash_field_changes_hash(records, field, replacement):
    original = _row(records, "2026-09-01")
    changed = deepcopy(original)
    changed[field] = replacement
    assert (
        _calculate((original,)).input_refs[0].input_hash
        != _calculate((changed,)).input_refs[0].input_hash
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("run_id", OTHER_RUN_ID),
        ("created_at", "2026-09-30T02:00:00+00:00"),
        ("orders", 999),
        ("gross_sales", "999"),
        ("refunds", 999),
        ("net_sales", "999"),
    ],
)
def test_each_excluded_row_field_does_not_change_hash(records, field, replacement):
    original = _row(records, "2026-09-01")
    changed = deepcopy(original)
    changed[field] = replacement
    assert _calculate((original,)).input_refs == _calculate((changed,)).input_refs


def test_calculation_run_id_does_not_change_hashes(records):
    rows = _complete_rows(records)
    first = _calculate(rows)
    second = _calculate(rows, run_id=OTHER_RUN_ID)
    assert first.run_id != second.run_id
    assert first.input_refs == second.input_refs
    assert first.outputs == second.outputs


def test_hash_payload_structure_excludes_formula_and_unrelated_fields():
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "topspeed_ai_os"
        / "calculation"
        / "inventory_demand_velocity.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_input_ref"
    )
    payload_assignment = next(
        node
        for node in function.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "payload"
    )
    assert tuple(key.value for key in payload_assignment.value.keys) == HASH_FIELDS


def test_input_refs_are_canonically_ordered(records):
    rows = tuple(reversed(_complete_rows(records)))
    result = _calculate(rows)
    keys = tuple((ref.natural_key[1], ref.input_hash) for ref in result.input_refs)
    assert keys == tuple(sorted(keys))


@pytest.mark.parametrize(
    ("carrier", "field_names"),
    [
        (InventoryDemandVelocityOutput, ("name", "value")),
        (
            InventoryDemandVelocityInputRef,
            ("contract_name", "natural_key", "source", "data_as_of", "input_hash"),
        ),
        (
            InventoryDemandVelocityError,
            ("code", "field", "stat_date", "input_hashes"),
        ),
        (
            InventoryDemandVelocityResult,
            (
                "metric_family",
                "formula_version",
                "run_id",
                "channel",
                "sku",
                "window_start_date",
                "window_end_date",
                "status",
                "outputs",
                "input_refs",
                "errors",
            ),
        ),
    ],
)
def test_carriers_are_frozen_slotted_dataclasses_with_exact_fields(carrier, field_names):
    assert is_dataclass(carrier)
    assert tuple(field.name for field in fields(carrier)) == field_names
    assert "__slots__" in carrier.__dict__


def test_deep_immutability_and_no_dynamic_attributes():
    result = _direct_success()
    with pytest.raises(FrozenInstanceError):
        result.status = "ERROR"
    with pytest.raises((FrozenInstanceError, TypeError)):
        result.new_field = "forbidden"
    with pytest.raises(TypeError):
        result.input_refs[0] = result.input_refs[0]
    assert not hasattr(result, "__dict__")
    assert all(not hasattr(item, "__dict__") for item in (*result.outputs, *result.input_refs))


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
        InventoryDemandVelocityOutput("avg_daily_units", value)


@pytest.mark.parametrize("value", ["0", "1", "0.0001", "12.3456", "100.01"])
def test_output_accepts_canonical_forms(value):
    assert InventoryDemandVelocityOutput("avg_daily_units", value).value == value


def test_carriers_reject_string_subclasses_and_wrong_fixed_literals():
    mutable = MutableString("avg_daily_units")
    mutable.state = []
    with pytest.raises(TypeError):
        InventoryDemandVelocityOutput(mutable, "1")
    with pytest.raises(ValueError):
        InventoryDemandVelocityOutput("metric", "1")
    with pytest.raises(ValueError):
        InventoryDemandVelocityInputRef(
            "OTHER",
            ("coupang", "2026-09-01", "TS-KITCHEN-001"),
            "source",
            "as-of",
            _hash(1),
        )


def test_input_error_and_result_carriers_reject_exact_string_subclasses():
    mutable = MutableString("mutable")
    mutable.state = []
    with pytest.raises(TypeError):
        InventoryDemandVelocityInputRef(
            "CHANNEL_DAILY",
            ("coupang", "2026-09-01", "TS-KITCHEN-001"),
            mutable,
            "as-of",
            _hash(1),
        )
    with pytest.raises(TypeError):
        InventoryDemandVelocityError(MutableString("MISSING_DATE"), "stat_date", "2026-09-01", ())
    with pytest.raises(TypeError):
        _direct_success(run_id=MutableString(RUN_ID))
    with pytest.raises(TypeError):
        _direct_success(channel=MutableString("coupang"))
    with pytest.raises(TypeError):
        _direct_success(status=MutableString("SUCCESS"))


@pytest.mark.parametrize("natural_key", [[], {}, set(), TupleSubclass(())])
def test_input_ref_requires_exact_natural_key_tuple(natural_key):
    with pytest.raises(TypeError):
        InventoryDemandVelocityInputRef("CHANNEL_DAILY", natural_key, "source", "as-of", _hash(1))


@pytest.mark.parametrize(
    "natural_key",
    [
        ("coupang", "2026-09-01"),
        ("coupang", "2026-09-01", "TS-KITCHEN-001", "extra"),
        ("coupang", date(2026, 9, 1), "TS-KITCHEN-001"),
        ("coupang", "invalid", "TS-KITCHEN-001"),
    ],
)
def test_input_ref_rejects_bad_natural_key_shape_or_values(natural_key):
    with pytest.raises((TypeError, ValueError)):
        InventoryDemandVelocityInputRef("CHANNEL_DAILY", natural_key, "source", "as-of", _hash(1))


@pytest.mark.parametrize(
    "arguments",
    [
        ("UNKNOWN", "stat_date", "2026-09-01", ()),
        ("MISSING_DATE", "units_sold", "2026-09-01", ()),
        ("MISSING_DATE", "stat_date", "2026-09-01", (_hash(1),)),
        ("OUT_OF_WINDOW", "stat_date", "2026-09-01", ()),
        ("NEGATIVE_UNITS_SOLD", "units_sold", "2026-09-01", (_hash(1), _hash(2))),
        ("DUPLICATE_DATE", "stat_date", "2026-09-01", (_hash(1),)),
        ("DUPLICATE_DATE", "stat_date", "2026-09-01", (_hash(2), _hash(1))),
    ],
)
def test_error_carrier_rejects_invalid_field_hash_shape_or_order(arguments):
    with pytest.raises(ValueError):
        InventoryDemandVelocityError(*arguments)


@pytest.mark.parametrize("bad_hashes", [[], set(), TupleSubclass((_hash(1),))])
def test_error_carrier_requires_exact_hash_tuple(bad_hashes):
    with pytest.raises(TypeError):
        InventoryDemandVelocityError("OUT_OF_WINDOW", "stat_date", "2026-09-01", bad_hashes)


def test_hash_strings_must_be_canonical():
    with pytest.raises(ValueError):
        _ref("2026-09-01", number=-1)
    with pytest.raises(ValueError):
        InventoryDemandVelocityError("OUT_OF_WINDOW", "stat_date", "2026-09-01", ("not-a-hash",))


def test_result_requires_exact_nested_tuples_and_carrier_identities():
    valid = _direct_success()
    with pytest.raises(TypeError):
        _direct_success(outputs=list(valid.outputs))
    with pytest.raises(TypeError):
        _direct_success(input_refs=TupleSubclass(valid.input_refs))
    with pytest.raises(TypeError):
        _direct_success(errors=(item for item in ()))
    with pytest.raises(TypeError):
        _direct_success(outputs=(CalculationOutput("contribution_margin", "1"),))


def test_result_enforces_fixed_literals_window_and_reference_coherence():
    with pytest.raises(ValueError):
        _direct_success(metric_family="OTHER")
    with pytest.raises(ValueError):
        _direct_success(formula_version="other")
    with pytest.raises(ValueError):
        _direct_success(window_start_date="2026-09-02")
    references = tuple(
        _ref(
            (WINDOW_START + timedelta(days=offset)).isoformat(),
            channel="other" if offset == 0 else "coupang",
            number=offset + 1,
        )
        for offset in range(30)
    )
    with pytest.raises(ValueError):
        _direct_success(input_refs=references)


def test_result_enforces_canonical_reference_order_and_success_shape():
    valid = _direct_success()
    with pytest.raises(ValueError):
        _direct_success(input_refs=tuple(reversed(valid.input_refs)))
    with pytest.raises(ValueError):
        _direct_success(outputs=())
    with pytest.raises(ValueError):
        _direct_success(
            errors=(
                InventoryDemandVelocityError(
                    "NEGATIVE_UNITS_SOLD", "units_sold", "2026-09-01", (_hash(1),)
                ),
            )
        )
    with pytest.raises(ValueError):
        _direct_success(input_refs=valid.input_refs[:-1])
    with pytest.raises(ValueError):
        _direct_success(status="PARTIAL")


def test_error_result_constructor_enforces_derivable_error_coherence(records):
    result = _calculate(_complete_rows(records)[:-1])
    assert result.status == "ERROR"
    with pytest.raises(ValueError):
        replace(result, errors=())
    wrong = InventoryDemandVelocityError("MISSING_DATE", "stat_date", "2026-09-28", ())
    with pytest.raises(ValueError):
        replace(result, errors=(wrong,))


def test_error_result_constructor_enforces_canonical_error_order(records):
    rows = _complete_rows(records)[:-2]
    result = _calculate(rows)
    assert len(result.errors) == 2
    with pytest.raises(ValueError):
        replace(result, errors=tuple(reversed(result.errors)))


def test_error_result_rejects_negative_error_without_matching_reference(records):
    result = _calculate(_complete_rows(records)[:-1])
    unmatched = InventoryDemandVelocityError(
        "NEGATIVE_UNITS_SOLD", "units_sold", "2026-09-01", (_hash(999),)
    )
    errors = tuple(sorted((*result.errors, unmatched), key=velocity_module._error_sort_key))
    with pytest.raises(ValueError):
        replace(result, errors=errors)


def test_source_dependent_negative_invariant_is_enforced_by_calculator(records):
    rows = list(_complete_rows(records))
    rows[5] = dict(rows[5], units_sold=-1)
    result = _calculate(tuple(rows))
    assert result.status == "ERROR"
    assert any(error.code == "NEGATIVE_UNITS_SOLD" for error in result.errors)


def test_input_mappings_are_not_mutated(records):
    rows = _complete_rows(records, lambda offset: offset)
    original = deepcopy(rows)
    _calculate(rows)
    assert rows == original


def test_h001_source_uses_only_schema_only_contract_authority():
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "topspeed_ai_os"
        / "calculation"
        / "inventory_demand_velocity.py"
    )
    source = source_path.read_text(encoding="utf-8")
    assert 'validate_schema_only("CHANNEL_DAILY", row)' in source
    assert "validate_contract" not in source
    assert "validate_record" not in source
    assert "known_skus" not in source


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
        / "inventory_demand_velocity.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module)
    assert imported_modules == {
        "collections",
        "collections.abc",
        "dataclasses",
        "datetime",
        "re",
        "typing",
        "topspeed_ai_os.contracts",
        "topspeed_ai_os.core.canonical",
        "topspeed_ai_os.core.ids",
        "contribution_margin",
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
