import ast
import decimal
import inspect
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, is_dataclass
from fractions import Fraction
from pathlib import Path

import pytest

import topspeed_ai_os.calculation as calculation_package
from topspeed_ai_os.calculation import (
    CONTRIBUTION_MARGIN_FORMULA_VERSION,
    CONTRIBUTION_MARGIN_METRIC,
    CalculationError,
    CalculationInputRef,
    CalculationOutput,
    CalculationResult,
    UnsupportedFormulaVersionError,
    calculate_product_master_contribution_margin,
)
from topspeed_ai_os.contracts import ContractValidationError
from topspeed_ai_os.core.ids import InvalidIdentifierError

RUN_ID = "run_" + "01J" + ("0" * 23)
OTHER_RUN_ID = "run_" + "01K" + ("0" * 23)
FORMULA_FIELDS = (
    "sale_price",
    "purchase_cost",
    "fee_rate",
    "fulfillment_cost",
    "expected_return_cost",
    "other_variable_cost",
)
EXPECTED_HASH = "sha256:9a8b765328e2861130cf5aef8995c6646bd9929e6414b99ba36e771b670150e5"


def _product(records):
    return records()["PRODUCT_MASTER"]


def _outputs(result):
    return {output.name: output.value for output in result.outputs}


def _formula_record(records, **changes):
    record = _product(records)
    record.update(
        {
            "sale_price": "1",
            "purchase_cost": "0",
            "fee_rate": "0",
            "fulfillment_cost": "0",
            "expected_return_cost": "0",
            "other_variable_cost": "0",
        }
    )
    record.update(changes)
    return record


def _fraction(source):
    negative = source.startswith("-")
    unsigned = source[1:] if negative else source
    if "." in unsigned:
        whole, fractional = unsigned.split(".")
        value = Fraction(int(whole + fractional), 10 ** len(fractional))
    else:
        value = Fraction(int(unsigned), 1)
    return -value if negative else value


def _fraction_to_canonical(value):
    if value == 0:
        return "0"
    negative = value < 0
    numerator = abs(value.numerator)
    denominator = value.denominator
    twos = 0
    fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    assert denominator == 1
    scale = max(twos, fives)
    numerator *= (2 ** (scale - twos)) * (5 ** (scale - fives))
    digits = str(numerator)
    if scale:
        digits = digits.rjust(scale + 1, "0")
        output = digits[:-scale] + "." + digits[-scale:]
        output = output.rstrip("0").rstrip(".")
    else:
        output = digits
    return ("-" if negative else "") + output


def _exact_reference(record):
    sale_price = _fraction(record["sale_price"])
    margin = (
        sale_price
        - _fraction(record["purchase_cost"])
        - (sale_price * _fraction(record["fee_rate"]))
        - _fraction(record["fulfillment_cost"])
        - _fraction(record["expected_return_cost"])
        - _fraction(record["other_variable_cost"])
    )
    absolute_scaled_rate = abs(margin / sale_price) * 10000
    quotient, remainder = divmod(
        absolute_scaled_rate.numerator,
        absolute_scaled_rate.denominator,
    )
    if 2 * remainder >= absolute_scaled_rate.denominator:
        quotient += 1
    rounded_rate = Fraction(quotient, 10000)
    if margin < 0:
        rounded_rate = -rounded_rate
    return _fraction_to_canonical(margin), _fraction_to_canonical(rounded_rate)


def _context_state(context):
    return (
        context.prec,
        context.rounding,
        context.Emin,
        context.Emax,
        context.capitals,
        context.clamp,
        tuple((signal.__name__, value) for signal, value in context.traps.items()),
        tuple((signal.__name__, value) for signal, value in context.flags.items()),
    )


def _restore_context(target, source):
    target.prec = source.prec
    target.rounding = source.rounding
    target.Emin = source.Emin
    target.Emax = source.Emax
    target.capitals = source.capitals
    target.clamp = source.clamp
    for signal, value in source.traps.items():
        target.traps[signal] = value
    for signal, value in source.flags.items():
        target.flags[signal] = value


class MutableString(str):
    pass


class TupleSubclass(tuple):
    pass


def _mutable_string():
    value = MutableString("mutable")
    value.mutable_state = []
    return value


def _valid_carrier(carrier, **changes):
    if carrier is CalculationOutput:
        values = {
            "name": "contribution_margin",
            "value": "1",
        }
    elif carrier is CalculationInputRef:
        values = {
            "contract_name": "PRODUCT_MASTER",
            "natural_key": ("TS-TEST-001",),
            "source": "manual_verified",
            "data_as_of": "2026-09-16T09:00:00+09:00",
            "input_hash": "sha256:" + ("a" * 64),
        }
    elif carrier is CalculationError:
        values = {
            "code": "MISSING_INPUT",
            "field": "sale_price",
        }
    elif carrier is CalculationResult:
        values = {
            "metric": "CONTRIBUTION_MARGIN",
            "formula_version": CONTRIBUTION_MARGIN_FORMULA_VERSION,
            "run_id": RUN_ID,
            "sku": "TS-TEST-001",
            "status": "SUCCESS",
            "outputs": (_valid_carrier(CalculationOutput),),
            "input_refs": (_valid_carrier(CalculationInputRef),),
            "errors": (_valid_carrier(CalculationError),),
        }
    else:
        raise AssertionError(f"unsupported carrier: {carrier}")
    values.update(changes)
    return carrier(**values)


SCALAR_FIELDS = (
    (CalculationOutput, "name"),
    (CalculationOutput, "value"),
    (CalculationInputRef, "contract_name"),
    (CalculationInputRef, "source"),
    (CalculationInputRef, "data_as_of"),
    (CalculationInputRef, "input_hash"),
    (CalculationError, "code"),
    (CalculationError, "field"),
    (CalculationResult, "metric"),
    (CalculationResult, "formula_version"),
    (CalculationResult, "run_id"),
    (CalculationResult, "sku"),
    (CalculationResult, "status"),
)


def test_exact_public_exports_and_constants():
    expected = [
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
    assert calculation_package.__all__ == expected
    assert CONTRIBUTION_MARGIN_METRIC == "CONTRIBUTION_MARGIN"
    assert CONTRIBUTION_MARGIN_FORMULA_VERSION == "topspeed.calculation.contribution_margin.v1"


def test_exact_public_function_signature():
    signature = inspect.signature(calculate_product_master_contribution_margin)
    parameters = list(signature.parameters.values())
    assert [parameter.name for parameter in parameters] == [
        "product_master",
        "run_id",
        "formula_version",
    ]
    assert parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameters[1].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters[1].default is inspect.Parameter.empty
    assert parameters[2].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters[2].default == CONTRIBUTION_MARGIN_FORMULA_VERSION
    assert signature.return_annotation is CalculationResult


@pytest.mark.parametrize(
    ("carrier", "field_names"),
    [
        (CalculationOutput, ("name", "value")),
        (
            CalculationInputRef,
            ("contract_name", "natural_key", "source", "data_as_of", "input_hash"),
        ),
        (CalculationError, ("code", "field")),
        (
            CalculationResult,
            (
                "metric",
                "formula_version",
                "run_id",
                "sku",
                "status",
                "outputs",
                "input_refs",
                "errors",
            ),
        ),
    ],
)
def test_carriers_are_frozen_slot_dataclasses_with_exact_fields(carrier, field_names):
    assert is_dataclass(carrier)
    assert tuple(field.name for field in fields(carrier)) == field_names
    assert "__slots__" in carrier.__dict__


def test_carriers_and_result_containers_are_immutable(records):
    result = calculate_product_master_contribution_margin(_product(records), run_id=RUN_ID)
    with pytest.raises(FrozenInstanceError):
        result.status = "ERROR"
    assert not hasattr(result, "__dict__")
    assert isinstance(result.outputs, tuple)
    assert isinstance(result.input_refs, tuple)
    assert isinstance(result.errors, tuple)
    with pytest.raises(AttributeError):
        result.outputs.append(CalculationOutput("contribution_margin", "0"))


def test_valid_direct_carrier_constructors_accept_exact_strings_and_tuples():
    output = _valid_carrier(CalculationOutput)
    input_ref = _valid_carrier(CalculationInputRef)
    error = _valid_carrier(CalculationError)
    result = _valid_carrier(
        CalculationResult,
        outputs=(output,),
        input_refs=(input_ref,),
        errors=(error,),
    )
    assert output == CalculationOutput("contribution_margin", "1")
    assert input_ref.natural_key == ("TS-TEST-001",)
    assert error == CalculationError("MISSING_INPUT", "sale_price")
    assert result.outputs == (output,)
    assert result.input_refs == (input_ref,)
    assert result.errors == (error,)
    assert type(result.outputs) is tuple
    assert type(result.input_refs) is tuple
    assert type(result.errors) is tuple


@pytest.mark.parametrize(("carrier", "field"), SCALAR_FIELDS)
@pytest.mark.parametrize(
    "invalid_factory",
    [
        pytest.param(list, id="list"),
        pytest.param(dict, id="dict"),
        pytest.param(set, id="set"),
        pytest.param(bytearray, id="bytearray"),
        pytest.param(_mutable_string, id="mutable-str-subclass"),
    ],
)
def test_every_scalar_field_rejects_non_exact_string_values(
    carrier,
    field,
    invalid_factory,
):
    invalid = invalid_factory()
    with pytest.raises(TypeError):
        _valid_carrier(carrier, **{field: invalid})


@pytest.mark.parametrize(
    "natural_key",
    [
        pytest.param(["TS-TEST-001"], id="list"),
        pytest.param({"TS-TEST-001": True}, id="dict"),
        pytest.param({"TS-TEST-001"}, id="set"),
        pytest.param(bytearray(b"TS"), id="bytearray"),
        pytest.param((), id="empty-tuple"),
        pytest.param(("A", "B"), id="multi-item-tuple"),
        pytest.param((123,), id="non-string-item"),
        pytest.param(TupleSubclass(("TS-TEST-001",)), id="tuple-subclass"),
    ],
)
def test_input_ref_rejects_invalid_natural_key_without_coercion(natural_key):
    with pytest.raises(TypeError):
        _valid_carrier(CalculationInputRef, natural_key=natural_key)


def _invalid_result_container(kind, item):
    if kind == "list":
        return [item]
    if kind == "dict":
        return {"item": item}
    if kind == "set":
        return {item}
    if kind == "bytearray":
        return bytearray()
    if kind == "generator":
        return (value for value in (item,))
    if kind == "tuple-subclass":
        return TupleSubclass((item,))
    raise AssertionError(f"unsupported container kind: {kind}")


@pytest.mark.parametrize("field", ["outputs", "input_refs", "errors"])
@pytest.mark.parametrize(
    "container_kind",
    ["list", "dict", "set", "bytearray", "generator", "tuple-subclass"],
)
def test_result_rejects_non_exact_tuple_containers_without_conversion(
    field,
    container_kind,
):
    item_by_field = {
        "outputs": _valid_carrier(CalculationOutput),
        "input_refs": _valid_carrier(CalculationInputRef),
        "errors": _valid_carrier(CalculationError),
    }
    invalid = _invalid_result_container(container_kind, item_by_field[field])
    with pytest.raises(TypeError):
        _valid_carrier(CalculationResult, **{field: invalid})


@pytest.mark.parametrize(
    ("field", "wrong_item"),
    [
        ("outputs", "not-output"),
        ("input_refs", "not-ref"),
        ("errors", "not-error"),
        ("outputs", CalculationInputRef),
        ("input_refs", CalculationError),
        ("errors", CalculationOutput),
    ],
)
def test_result_rejects_wrong_exact_tuple_element_types(field, wrong_item):
    item = wrong_item if isinstance(wrong_item, str) else _valid_carrier(wrong_item)
    with pytest.raises(TypeError):
        _valid_carrier(CalculationResult, **{field: (item,)})


def test_valid_result_graph_is_deeply_immutable():
    output = _valid_carrier(CalculationOutput)
    input_ref = _valid_carrier(CalculationInputRef)
    error = _valid_carrier(CalculationError)
    result = _valid_carrier(
        CalculationResult,
        outputs=(output,),
        input_refs=(input_ref,),
        errors=(error,),
    )

    with pytest.raises(FrozenInstanceError):
        result.status = "ERROR"
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        result.new_attribute = "rejected"
    with pytest.raises(TypeError):
        result.outputs[0] = output
    with pytest.raises(TypeError):
        result.input_refs[0] = input_ref
    with pytest.raises(TypeError):
        result.errors[0] = error
    with pytest.raises(FrozenInstanceError):
        output.value = "2"
    with pytest.raises(FrozenInstanceError):
        input_ref.source = "changed"
    with pytest.raises(FrozenInstanceError):
        error.code = "INVALID_INPUT"


def test_published_fixture_success_shape_values_and_hash(records):
    result = calculate_product_master_contribution_margin(_product(records), run_id=RUN_ID)
    assert result == CalculationResult(
        metric="CONTRIBUTION_MARGIN",
        formula_version="topspeed.calculation.contribution_margin.v1",
        run_id=RUN_ID,
        sku="TS-KITCHEN-001",
        status="SUCCESS",
        outputs=(
            CalculationOutput("contribution_margin", "3356.8"),
            CalculationOutput("contribution_margin_rate", "0.2602"),
        ),
        input_refs=(
            CalculationInputRef(
                contract_name="PRODUCT_MASTER",
                natural_key=("TS-KITCHEN-001",),
                source="manual_verified",
                data_as_of="2026-09-16T09:00:00+09:00",
                input_hash=EXPECTED_HASH,
            ),
        ),
        errors=(),
    )


def test_preexisting_derived_fields_do_not_affect_result_or_hash(records):
    original = _product(records)
    changed = deepcopy(original)
    changed["contribution_margin"] = "-999999.000"
    changed["contribution_margin_rate"] = "0.9999"
    assert calculate_product_master_contribution_margin(
        original, run_id=RUN_ID
    ) == calculate_product_master_contribution_margin(changed, run_id=RUN_ID)


def test_success_input_ref_preserves_exact_source_values(records):
    record = _product(records)
    result = calculate_product_master_contribution_margin(record, run_id=RUN_ID)
    assert result.input_refs == (
        CalculationInputRef(
            contract_name="PRODUCT_MASTER",
            natural_key=(record["sku"],),
            source=record["source"],
            data_as_of=record["data_as_of"],
            input_hash=EXPECTED_HASH,
        ),
    )


@pytest.mark.parametrize("non_mapping", [None, [], "PRODUCT_MASTER", 1])
def test_non_mapping_input_raises_type_error_before_other_boundaries(non_mapping):
    with pytest.raises(TypeError):
        calculate_product_master_contribution_margin(
            non_mapping,
            run_id="invalid",
            formula_version="unsupported",
        )


def test_wrong_contract_shape_propagates_contract_error(records):
    with pytest.raises(ContractValidationError):
        calculate_product_master_contribution_margin(
            records()["CHANNEL_DAILY"],
            run_id=RUN_ID,
        )


@pytest.mark.parametrize("required_field", ["sku", "currency", "source", "data_as_of"])
def test_missing_required_contract_field_propagates_contract_error(records, required_field):
    record = _product(records)
    del record[required_field]
    with pytest.raises(ContractValidationError):
        calculate_product_master_contribution_margin(record, run_id=RUN_ID)


@pytest.mark.parametrize(
    "invalid_decimal",
    [5000, 0.5, "1e3", "01", "-01", "NaN", "Infinity", "-Infinity"],
)
def test_contract_invalid_decimal_creates_no_result(records, invalid_decimal):
    record = _product(records)
    record["sale_price"] = invalid_decimal
    with pytest.raises(ContractValidationError):
        calculate_product_master_contribution_margin(record, run_id=RUN_ID)


def test_invalid_contract_precedes_invalid_run_id_and_formula(records):
    record = _product(records)
    record["sale_price"] = "01"
    with pytest.raises(ContractValidationError):
        calculate_product_master_contribution_margin(
            record,
            run_id="invalid",
            formula_version="unsupported",
        )


def test_invalid_run_id_propagates_existing_identifier_error(records):
    with pytest.raises(InvalidIdentifierError):
        calculate_product_master_contribution_margin(
            _product(records),
            run_id="run_invalid",
        )


def test_invalid_run_id_precedes_unsupported_formula(records):
    with pytest.raises(InvalidIdentifierError):
        calculate_product_master_contribution_margin(
            _product(records),
            run_id="invalid",
            formula_version="unsupported",
        )


def test_unsupported_formula_has_exact_error_type_and_no_mutable_state(records):
    with pytest.raises(UnsupportedFormulaVersionError) as captured:
        calculate_product_master_contribution_margin(
            _product(records),
            run_id=RUN_ID,
            formula_version="topspeed.calculation.contribution_margin.v2",
        )
    assert isinstance(captured.value, ValueError)
    assert captured.value.__dict__ == {}


@pytest.mark.parametrize("field", FORMULA_FIELDS)
@pytest.mark.parametrize("representation", ["omitted", "null"])
def test_each_missing_or_null_formula_field_returns_one_missing_error(
    records,
    field,
    representation,
):
    record = _product(records)
    if representation == "omitted":
        del record[field]
    else:
        record[field] = None
    result = calculate_product_master_contribution_margin(record, run_id=RUN_ID)
    assert result.status == "ERROR"
    assert result.outputs == ()
    assert len(result.input_refs) == 1
    assert result.errors == (CalculationError("MISSING_INPUT", field),)


def test_multiple_semantic_errors_are_complete_unique_and_ordered(records):
    record = _product(records)
    del record["sale_price"]
    record["purchase_cost"] = None
    del record["fee_rate"]
    record["fulfillment_cost"] = None
    del record["expected_return_cost"]
    record["other_variable_cost"] = None
    result = calculate_product_master_contribution_margin(record, run_id=RUN_ID)
    assert result.status == "ERROR"
    assert result.outputs == ()
    assert result.errors == tuple(
        CalculationError("MISSING_INPUT", field) for field in FORMULA_FIELDS
    )
    assert len({error.field for error in result.errors}) == len(result.errors)


def test_omitted_and_explicit_null_project_to_the_same_hash(records):
    omitted = _product(records)
    explicit_null = deepcopy(omitted)
    del omitted["purchase_cost"]
    explicit_null["purchase_cost"] = None
    omitted_result = calculate_product_master_contribution_margin(omitted, run_id=RUN_ID)
    null_result = calculate_product_master_contribution_margin(explicit_null, run_id=RUN_ID)
    assert omitted_result.input_refs[0].input_hash == null_result.input_refs[0].input_hash


def test_formula_arithmetic_is_not_started_when_semantic_errors_exist(records, monkeypatch):
    record = _product(records)
    record["purchase_cost"] = None

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Decimal Context must not be constructed")

    monkeypatch.setattr(decimal, "Context", fail_if_called)
    result = calculate_product_master_contribution_margin(record, run_id=RUN_ID)
    assert result.status == "ERROR"
    assert result.errors == (CalculationError("MISSING_INPUT", "purchase_cost"),)


def test_zero_sale_price_returns_zero_sale_price_error(records):
    result = calculate_product_master_contribution_margin(
        _formula_record(records, sale_price="0"),
        run_id=RUN_ID,
    )
    assert result.status == "ERROR"
    assert result.errors == (CalculationError("ZERO_SALE_PRICE", "sale_price"),)


def test_negative_sale_price_returns_invalid_input(records):
    result = calculate_product_master_contribution_margin(
        _formula_record(records, sale_price="-1"),
        run_id=RUN_ID,
    )
    assert result.status == "ERROR"
    assert result.errors == (CalculationError("INVALID_INPUT", "sale_price"),)


@pytest.mark.parametrize(
    "field",
    [
        "purchase_cost",
        "fulfillment_cost",
        "expected_return_cost",
        "other_variable_cost",
    ],
)
def test_each_negative_cost_returns_invalid_input(records, field):
    result = calculate_product_master_contribution_margin(
        _formula_record(records, **{field: "-0.0001"}),
        run_id=RUN_ID,
    )
    assert result.status == "ERROR"
    assert result.errors == (CalculationError("INVALID_INPUT", field),)


@pytest.mark.parametrize("fee_rate", ["0", "0.0000", "1", "1.000"])
def test_fee_rate_inclusive_boundaries_succeed(records, fee_rate):
    result = calculate_product_master_contribution_margin(
        _formula_record(records, fee_rate=fee_rate),
        run_id=RUN_ID,
    )
    assert result.status == "SUCCESS"
    assert result.errors == ()


@pytest.mark.parametrize("fee_rate", ["-0.0001", "1.0001"])
def test_contract_rejects_out_of_range_fee_before_result(records, fee_rate):
    with pytest.raises(ContractValidationError):
        calculate_product_master_contribution_margin(
            _formula_record(records, fee_rate=fee_rate),
            run_id=RUN_ID,
        )


def test_negative_margin_and_rate_are_success_without_clamping(records):
    result = calculate_product_master_contribution_margin(
        _formula_record(records, purchase_cost="2.5"),
        run_id=RUN_ID,
    )
    assert result.status == "SUCCESS"
    assert result.errors == ()
    assert _outputs(result) == {
        "contribution_margin": "-1.5",
        "contribution_margin_rate": "-1.5",
    }


@pytest.mark.parametrize(
    ("margin", "expected_rate"),
    [
        ("0.000049", "0"),
        ("0.000050", "0.0001"),
        ("0.000051", "0.0001"),
        ("-0.000049", "0"),
        ("-0.000050", "-0.0001"),
        ("-0.000051", "-0.0001"),
    ],
)
def test_exact_positive_and_negative_half_up_boundaries(records, margin, expected_rate):
    purchase_cost = _fraction_to_canonical(Fraction(1, 1) - _fraction(margin))
    result = calculate_product_master_contribution_margin(
        _formula_record(records, purchase_cost=purchase_cost),
        run_id=RUN_ID,
    )
    assert result.status == "SUCCESS"
    assert _outputs(result)["contribution_margin"] == _fraction_to_canonical(_fraction(margin))
    assert _outputs(result)["contribution_margin_rate"] == expected_rate


def test_rate_rounding_does_not_double_round(records):
    record = _formula_record(records, purchase_cost="0.9999500001")
    result = calculate_product_master_contribution_margin(record, run_id=RUN_ID)
    assert _outputs(result) == {
        "contribution_margin": "0.0000499999",
        "contribution_margin_rate": "0",
    }


@pytest.mark.parametrize(
    "formula_values",
    [
        {
            "sale_price": "123456789012345678901234567890.0000",
            "purchase_cost": "0.000000000000000000000000000001",
            "fee_rate": "0.12345678901234567890",
            "fulfillment_cost": "98765432109876543210.00000001",
            "expected_return_cost": "0.00000000000000000009",
            "other_variable_cost": "123456789.123456789",
        },
        {
            "sale_price": "0.000000000000000000000000000001",
            "purchase_cost": "0.000000000000000000000000000000",
            "fee_rate": "0.000000000000000000000000000001",
            "fulfillment_cost": "0",
            "expected_return_cost": "0.000000000000000000000000000000",
            "other_variable_cost": "0.000000000000000000000000000000",
        },
        {
            "sale_price": "5000.00",
            "purchase_cost": "4999.9999",
            "fee_rate": "0.00000001",
            "fulfillment_cost": "0.00001",
            "expected_return_cost": "0.000010",
            "other_variable_cost": "0.0000100",
        },
        {
            "sale_price": "99999999999999999999.9999",
            "purchase_cost": "99999999999999999999.9998",
            "fee_rate": "0",
            "fulfillment_cost": "0.00001",
            "expected_return_cost": "0.00002",
            "other_variable_cost": "0.00003",
        },
    ],
)
def test_precision_edges_match_independent_integer_rational_reference(records, formula_values):
    record = _formula_record(records, **formula_values)
    expected_margin, expected_rate = _exact_reference(record)
    result = calculate_product_master_contribution_margin(record, run_id=RUN_ID)
    assert result.status == "SUCCESS"
    assert _outputs(result) == {
        "contribution_margin": expected_margin,
        "contribution_margin_rate": expected_rate,
    }


def test_calculated_negative_zero_is_serialized_as_positive_zero(records):
    record = _formula_record(
        records,
        purchase_cost="1",
        fee_rate="-0",
        fulfillment_cost="-0.0",
        expected_return_cost="0.00",
        other_variable_cost="-0.000",
    )
    result = calculate_product_master_contribution_margin(record, run_id=RUN_ID)
    assert _outputs(result) == {
        "contribution_margin": "0",
        "contribution_margin_rate": "0",
    }


@pytest.mark.parametrize(
    ("precision", "rounding", "emin", "emax", "trap_value"),
    [
        (2, decimal.ROUND_DOWN, -2, 2, False),
        (50, decimal.ROUND_CEILING, -99, 99, True),
        (7, decimal.ROUND_FLOOR, -7, 7, False),
    ],
)
def test_ambient_and_default_decimal_context_independence(
    records,
    precision,
    rounding,
    emin,
    emax,
    trap_value,
):
    expected = calculate_product_master_contribution_margin(_product(records), run_id=RUN_ID)
    active = decimal.getcontext()
    saved_active = active.copy()
    saved_default = decimal.DefaultContext.copy()
    try:
        active.prec = precision
        active.rounding = rounding
        active.Emin = emin
        active.Emax = emax
        active.capitals = 0
        active.clamp = 1
        for signal in active.traps:
            active.traps[signal] = trap_value
        active.clear_flags()

        decimal.DefaultContext.prec = max(1, precision - 1)
        decimal.DefaultContext.rounding = decimal.ROUND_UP
        decimal.DefaultContext.Emin = emin - 1
        decimal.DefaultContext.Emax = emax + 1
        decimal.DefaultContext.capitals = 0
        decimal.DefaultContext.clamp = 1
        for signal in decimal.DefaultContext.traps:
            decimal.DefaultContext.traps[signal] = not trap_value
        decimal.DefaultContext.clear_flags()

        active_before = _context_state(active)
        default_before = _context_state(decimal.DefaultContext)
        actual = calculate_product_master_contribution_margin(_product(records), run_id=RUN_ID)
        assert actual == expected
        assert actual.input_refs[0].input_hash == expected.input_refs[0].input_hash
        assert _context_state(active) == active_before
        assert _context_state(decimal.DefaultContext) == default_before
    finally:
        decimal.setcontext(saved_active)
        _restore_context(decimal.DefaultContext, saved_default)


def test_each_success_uses_fresh_hardened_contexts(records, monkeypatch):
    real_context = decimal.Context
    created = []

    def recording_context(*args, **kwargs):
        context = real_context(*args, **kwargs)
        created.append(context)
        return context

    monkeypatch.setattr(decimal, "Context", recording_context)
    first = calculate_product_master_contribution_margin(_product(records), run_id=RUN_ID)
    first_contexts = tuple(created)
    second = calculate_product_master_contribution_margin(_product(records), run_id=RUN_ID)
    second_contexts = tuple(created[len(first_contexts) :])
    assert first == second
    assert len(first_contexts) == 2
    assert len(second_contexts) == 2
    assert not ({id(item) for item in first_contexts} & {id(item) for item in second_contexts})

    trapped = {
        decimal.Inexact,
        decimal.Rounded,
        decimal.InvalidOperation,
        decimal.DivisionByZero,
        decimal.Overflow,
    }
    for context in (*first_contexts, *second_contexts):
        assert context.rounding == decimal.ROUND_HALF_UP
        assert context.Emin == decimal.MIN_EMIN
        assert context.Emax == decimal.MAX_EMAX
        assert context.capitals == 1
        assert context.clamp == 0
        assert {signal for signal, enabled in context.traps.items() if enabled} == trapped
        assert not any(context.flags.values())


def test_trailing_zero_source_exponents_do_not_trigger_rounding_signals(records):
    record = _formula_record(
        records,
        sale_price="5000.000000",
        purchase_cost="1200.000",
        fee_rate="0.1000",
        fulfillment_cost="200.00",
        expected_return_cost="30.0000",
        other_variable_cost="20.0",
    )
    result = calculate_product_master_contribution_margin(record, run_id=RUN_ID)
    assert _outputs(result) == {
        "contribution_margin": "3050",
        "contribution_margin_rate": "0.61",
    }


def test_exact_fee_multiplication_and_aligned_carry(records):
    record = _formula_record(
        records,
        sale_price="9999999999999999.9999",
        purchase_cost="8888888888888888.8888",
        fee_rate="0.9999999999999999",
        fulfillment_cost="0.00001",
        expected_return_cost="0.00001",
        other_variable_cost="0.00001",
    )
    expected_margin, expected_rate = _exact_reference(record)
    result = calculate_product_master_contribution_margin(record, run_id=RUN_ID)
    assert _outputs(result) == {
        "contribution_margin": expected_margin,
        "contribution_margin_rate": expected_rate,
    }


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("sku", "TS-KITCHEN-002"),
        ("currency", "USD"),
        ("sale_price", "12901"),
        ("purchase_cost", "5201"),
        ("fee_rate", "0.109"),
        ("fulfillment_cost", "2501"),
        ("expected_return_cost", "351"),
        ("other_variable_cost", "101"),
        ("source", "manual_verified_v2"),
        ("data_as_of", "2026-09-16T09:00:01+09:00"),
    ],
)
def test_each_exact_hash_field_changes_input_hash(records, field, replacement):
    original = _product(records)
    changed = deepcopy(original)
    changed[field] = replacement
    original_hash = (
        calculate_product_master_contribution_margin(
            original,
            run_id=RUN_ID,
        )
        .input_refs[0]
        .input_hash
    )
    changed_hash = (
        calculate_product_master_contribution_margin(
            changed,
            run_id=RUN_ID,
        )
        .input_refs[0]
        .input_hash
    )
    assert changed_hash != original_hash


def test_lexically_equivalent_decimal_inputs_have_distinct_hashes(records):
    results = []
    for source in ("5000", "5000.0", "5000.00"):
        record = _product(records)
        record["sale_price"] = source
        results.append(calculate_product_master_contribution_margin(record, run_id=RUN_ID))
    assert len({result.input_refs[0].input_hash for result in results}) == 3


def test_run_id_changes_only_result_run_id(records):
    first = calculate_product_master_contribution_margin(_product(records), run_id=RUN_ID)
    second = calculate_product_master_contribution_margin(_product(records), run_id=OTHER_RUN_ID)
    assert first.run_id == RUN_ID
    assert second.run_id == OTHER_RUN_ID
    assert first.input_refs == second.input_refs
    assert first.status == second.status
    assert first.outputs == second.outputs
    assert first.errors == second.errors
    assert first == CalculationResult(
        metric=second.metric,
        formula_version=second.formula_version,
        run_id=RUN_ID,
        sku=second.sku,
        status=second.status,
        outputs=second.outputs,
        input_refs=second.input_refs,
        errors=second.errors,
    )


def test_identical_exact_inputs_have_structural_value_equality(records):
    first_record = _product(records)
    second_record = deepcopy(first_record)
    first = calculate_product_master_contribution_margin(first_record, run_id=RUN_ID)
    second = calculate_product_master_contribution_margin(second_record, run_id=RUN_ID)
    assert first == second
    assert first is not second


@pytest.mark.parametrize("semantic_error", ["missing", "zero"])
def test_input_mapping_is_unchanged_after_success_and_error(records, semantic_error):
    record = _product(records)
    if semantic_error == "missing":
        record["purchase_cost"] = None
    elif semantic_error == "zero":
        record["sale_price"] = "0"
    before = deepcopy(record)
    calculate_product_master_contribution_margin(record, run_id=RUN_ID)
    assert record == before


def test_hash_payload_has_exact_keys_and_excludes_formula_and_run_id():
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "topspeed_ai_os"
        / "calculation"
        / "contribution_margin.py"
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
        and any(isinstance(target, ast.Name) and target.id == "payload" for target in node.targets)
    )
    keys = tuple(key.value for key in payload_assignment.value.keys)
    assert keys == (
        "sku",
        "currency",
        "sale_price",
        "purchase_cost",
        "fee_rate",
        "fulfillment_cost",
        "expected_return_cost",
        "other_variable_cost",
        "source",
        "data_as_of",
    )
    assert "run_id" not in keys
    assert "formula_version" not in keys
    assert "contribution_margin" not in keys
    assert "contribution_margin_rate" not in keys


def test_production_imports_are_inside_exact_allowlist():
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "topspeed_ai_os"
        / "calculation"
        / "contribution_margin.py"
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
        "decimal",
        "typing",
        "topspeed_ai_os.contracts",
        "topspeed_ai_os.contracts.logical_types",
        "topspeed_ai_os.core.canonical",
        "topspeed_ai_os.core.ids",
    }


def test_production_has_no_external_or_nondeterministic_capability_names():
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "topspeed_ai_os"
        / "calculation"
        / "contribution_margin.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_names = {
        "open",
        "eval",
        "exec",
        "compile",
        "getcontext",
        "setcontext",
        "DefaultContext",
        "datetime",
        "time",
        "random",
        "secrets",
        "uuid",
        "subprocess",
        "socket",
        "environ",
        "getenv",
        "generate_run_id",
    }
    used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    used_attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert forbidden_names.isdisjoint(used_names | used_attributes)


def test_error_result_has_exact_shape_and_input_ref(records):
    record = _product(records)
    record["sale_price"] = None
    result = calculate_product_master_contribution_margin(record, run_id=RUN_ID)
    assert result.metric == CONTRIBUTION_MARGIN_METRIC
    assert result.formula_version == CONTRIBUTION_MARGIN_FORMULA_VERSION
    assert result.run_id == RUN_ID
    assert result.sku == record["sku"]
    assert result.status == "ERROR"
    assert result.outputs == ()
    assert len(result.input_refs) == 1
    assert result.input_refs[0].contract_name == "PRODUCT_MASTER"
    assert result.input_refs[0].natural_key == (record["sku"],)
    assert result.input_refs[0].source == record["source"]
    assert result.input_refs[0].data_as_of == record["data_as_of"]
    assert result.errors == (CalculationError("MISSING_INPUT", "sale_price"),)
