import ast
import decimal
import hashlib
import inspect
import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, is_dataclass
from fractions import Fraction
from pathlib import Path

import pytest

import topspeed_ai_os.calculation as calculation_package
import topspeed_ai_os.calculation.ad_daily_metrics as ad_metrics_module
from topspeed_ai_os.calculation import (
    AD_METRICS_FORMULA_VERSION,
    CONTRIBUTION_MARGIN_FORMULA_VERSION,
    CONTRIBUTION_MARGIN_METRIC,
    AdvertisingMetricOutput,
    AdvertisingMetricsError,
    AdvertisingMetricsInputRef,
    AdvertisingMetricsResult,
    CalculationInputRef,
    CalculationOutput,
    CalculationResult,
    UnsupportedFormulaVersionError,
    calculate_ad_daily_metrics,
    calculate_product_master_contribution_margin,
)
from topspeed_ai_os.calculation.contribution_margin import (
    CalculationResult as ContributionMarginResultIdentity,
)
from topspeed_ai_os.contracts import ContractValidationError
from topspeed_ai_os.core.ids import InvalidIdentifierError

RUN_ID = "run_" + "01J" + ("0" * 23)
OTHER_RUN_ID = "run_" + "01K" + ("0" * 23)
METRICS = ("ctr", "cvr", "roas")
HASH_FIELDS = (
    "channel",
    "stat_date",
    "sku",
    "campaign_id",
    "ad_group_id",
    "impressions",
    "clicks",
    "ad_spend",
    "ad_orders",
    "ad_revenue",
    "source_file_hash",
    "source",
    "data_as_of",
)


class MutableString(str):
    pass


class TupleSubclass(tuple):
    pass


def _ad_daily(records, **changes):
    record = records()["AD_DAILY"]
    record.update(changes)
    return record


def _formula_record(records, **changes):
    record = _ad_daily(
        records,
        impressions=100,
        clicks=20,
        ad_orders=5,
        ad_spend="40",
        ad_revenue="100",
    )
    record.update(changes)
    return record


def _output_map(result):
    return {output.metric: output.value for output in result.outputs}


def _independent_round(numerator, denominator):
    scaled = Fraction(numerator, denominator) * 10_000
    quotient, remainder = divmod(scaled.numerator, scaled.denominator)
    if 2 * remainder >= scaled.denominator:
        quotient += 1
    if quotient == 0:
        return "0"
    whole, fractional = divmod(quotient, 10_000)
    if fractional == 0:
        return str(whole)
    return f"{whole}.{fractional:04d}".rstrip("0")


def _decimal_fraction(source):
    negative = source.startswith("-")
    unsigned = source[1:] if negative else source
    if "." in unsigned:
        whole, fractional = unsigned.split(".")
        value = Fraction(int(whole + fractional), 10 ** len(fractional))
    else:
        value = Fraction(int(unsigned), 1)
    return -value if negative else value


def _independent_hash(record):
    payload = {field: record.get(field) for field in HASH_FIELDS}
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(serialized).hexdigest()}"


def _input_ref(*, sku="TS-TEST-001"):
    return AdvertisingMetricsInputRef(
        contract_name="AD_DAILY",
        natural_key=("coupang_ads", "2026-09-15", sku, "cmp_1", None),
        source="fixture",
        data_as_of="2026-09-16T09:00:00+09:00",
        input_hash="sha256:" + ("a" * 64),
    )


def _direct_result(*, status="SUCCESS", run_id=RUN_ID, sku="TS-TEST-001"):
    if status == "SUCCESS":
        outputs = tuple(AdvertisingMetricOutput(metric, "1") for metric in METRICS)
        errors = ()
    elif status == "PARTIAL":
        outputs = (AdvertisingMetricOutput("ctr", "0.5"),)
        errors = (
            AdvertisingMetricsError("ZERO_DENOMINATOR", "cvr", "clicks"),
            AdvertisingMetricsError("ZERO_DENOMINATOR", "roas", "ad_spend"),
        )
    else:
        outputs = ()
        errors = (AdvertisingMetricsError("INVALID_INPUT", None, "impressions"),)
    return AdvertisingMetricsResult(
        metric_family="AD_DAILY_ADVERTISING_METRICS",
        formula_version=AD_METRICS_FORMULA_VERSION,
        run_id=run_id,
        sku=sku,
        status=status,
        outputs=outputs,
        input_refs=(_input_ref(sku=sku),),
        errors=errors,
    )


def test_exact_public_exports_constants_and_contribution_identities():
    assert calculation_package.__all__ == [
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
    ]
    assert AD_METRICS_FORMULA_VERSION == "topspeed.calculation.ad_metrics.v1"
    assert calculation_package.CalculationResult is ContributionMarginResultIdentity
    assert calculation_package.UnsupportedFormulaVersionError is UnsupportedFormulaVersionError


def test_exact_public_function_signature_and_return_annotation():
    signature = inspect.signature(calculate_ad_daily_metrics)
    parameters = list(signature.parameters.values())
    assert [parameter.name for parameter in parameters] == [
        "ad_daily",
        "run_id",
        "formula_version",
    ]
    assert parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameters[1].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters[1].default is inspect.Parameter.empty
    assert parameters[2].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters[2].default == AD_METRICS_FORMULA_VERSION
    assert signature.return_annotation is AdvertisingMetricsResult


@pytest.mark.parametrize("non_mapping", [None, [], "AD_DAILY", 1])
def test_non_mapping_fails_before_other_boundaries(non_mapping):
    with pytest.raises(TypeError):
        calculate_ad_daily_metrics(non_mapping, run_id="invalid", formula_version="unsupported")


@pytest.mark.parametrize(
    ("change", "value"),
    [("missing", None), ("impressions", "100"), ("ad_spend", 10)],
)
def test_contract_failures_precede_run_id_and_formula(records, change, value):
    record = _ad_daily(records)
    if change == "missing":
        record.pop("clicks")
    else:
        record[change] = value
    with pytest.raises(ContractValidationError):
        calculate_ad_daily_metrics(record, run_id="invalid", formula_version="unsupported")


def test_invalid_run_id_precedes_unsupported_formula(records):
    with pytest.raises(InvalidIdentifierError):
        calculate_ad_daily_metrics(
            _ad_daily(records), run_id="invalid", formula_version="unsupported"
        )


def test_unsupported_formula_reuses_existing_exception(records):
    with pytest.raises(UnsupportedFormulaVersionError):
        calculate_ad_daily_metrics(
            _ad_daily(records), run_id=RUN_ID, formula_version="topspeed.calculation.ad_metrics.v2"
        )


def test_unsupported_formula_precedes_input_ref_construction(records, monkeypatch):
    def fail_if_called(_record):
        raise AssertionError("input reference must not be constructed")

    monkeypatch.setattr(ad_metrics_module, "_input_ref", fail_if_called)
    with pytest.raises(UnsupportedFormulaVersionError):
        calculate_ad_daily_metrics(_ad_daily(records), run_id=RUN_ID, formula_version="unsupported")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("impressions", -1),
        ("clicks", -1),
        ("ad_spend", "-0.01"),
        ("ad_orders", -1),
        ("ad_revenue", "-0.01"),
    ],
)
def test_each_primitive_violation_returns_exact_error(records, field, value):
    result = calculate_ad_daily_metrics(_formula_record(records, **{field: value}), run_id=RUN_ID)
    assert result.status == "ERROR"
    assert result.outputs == ()
    assert result.errors == (AdvertisingMetricsError("INVALID_INPUT", None, field),)
    assert len(result.input_refs) == 1


def test_multiple_primitive_errors_are_complete_and_ordered(records):
    record = _formula_record(
        records,
        impressions=-1,
        clicks=-2,
        ad_spend="-3",
        ad_orders=-4,
        ad_revenue="-5",
    )
    result = calculate_ad_daily_metrics(record, run_id=RUN_ID)
    assert tuple(error.field for error in result.errors) == (
        "impressions",
        "clicks",
        "ad_spend",
        "ad_orders",
        "ad_revenue",
    )


def test_primitive_errors_short_circuit_later_phases(records, monkeypatch):
    def fail_if_called(*_args):
        raise AssertionError("arithmetic must not run")

    monkeypatch.setattr(ad_metrics_module, "_rounded_ratio", fail_if_called)
    record = _formula_record(records, impressions=-1, clicks=10, ad_spend="0")
    result = calculate_ad_daily_metrics(record, run_id=RUN_ID)
    assert result.errors == (AdvertisingMetricsError("INVALID_INPUT", None, "impressions"),)


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        (
            {"impressions": 1, "clicks": 2, "ad_orders": 1},
            (AdvertisingMetricsError("INVALID_INPUT", "ctr", "clicks/impressions"),),
        ),
        (
            {"impressions": 10, "clicks": 2, "ad_orders": 3},
            (AdvertisingMetricsError("INVALID_INPUT", "cvr", "ad_orders/clicks"),),
        ),
        (
            {"impressions": 1, "clicks": 2, "ad_orders": 3},
            (
                AdvertisingMetricsError("INVALID_INPUT", "ctr", "clicks/impressions"),
                AdvertisingMetricsError("INVALID_INPUT", "cvr", "ad_orders/clicks"),
            ),
        ),
    ],
)
def test_cross_field_errors_are_complete_and_ordered(records, changes, expected):
    result = calculate_ad_daily_metrics(_formula_record(records, **changes), run_id=RUN_ID)
    assert result.status == "ERROR"
    assert result.outputs == ()
    assert result.errors == expected


def test_cross_field_error_precedes_zero_denominator(records, monkeypatch):
    def fail_if_called(*_args):
        raise AssertionError("arithmetic must not run")

    monkeypatch.setattr(ad_metrics_module, "_rounded_ratio", fail_if_called)
    result = calculate_ad_daily_metrics(
        _formula_record(records, impressions=0, clicks=1, ad_orders=0, ad_spend="0"),
        run_id=RUN_ID,
    )
    assert result.status == "ERROR"
    assert result.errors == (AdvertisingMetricsError("INVALID_INPUT", "ctr", "clicks/impressions"),)


@pytest.mark.parametrize(
    (
        "impressions_zero",
        "clicks_zero",
        "spend_zero",
        "status",
        "output_metrics",
        "error_metrics",
    ),
    [
        (False, False, False, "SUCCESS", ("ctr", "cvr", "roas"), ()),
        (False, False, True, "PARTIAL", ("ctr", "cvr"), ("roas",)),
        (False, True, False, "PARTIAL", ("ctr", "roas"), ("cvr",)),
        (False, True, True, "PARTIAL", ("ctr",), ("cvr", "roas")),
        (True, False, False, "ERROR", (), ("ctr",)),
        (True, False, True, "ERROR", (), ("ctr",)),
        (True, True, False, "PARTIAL", ("roas",), ("ctr", "cvr")),
        (True, True, True, "PARTIAL", (), ("ctr", "cvr", "roas")),
    ],
)
def test_all_eight_denominator_patterns_respect_precedence(
    records,
    impressions_zero,
    clicks_zero,
    spend_zero,
    status,
    output_metrics,
    error_metrics,
):
    impressions = 0 if impressions_zero else 10
    clicks = 0 if clicks_zero else 2
    record = _formula_record(
        records,
        impressions=impressions,
        clicks=clicks,
        ad_orders=0,
        ad_spend="0" if spend_zero else "2",
        ad_revenue="4",
    )
    result = calculate_ad_daily_metrics(record, run_id=RUN_ID)
    assert result.status == status
    assert tuple(output.metric for output in result.outputs) == output_metrics
    assert tuple(error.metric for error in result.errors) == error_metrics
    assert result.run_id == RUN_ID
    assert result.sku == record["sku"] == result.input_refs[0].natural_key[2]


def test_hand_calculated_fixture_outputs(records):
    record = _ad_daily(records)
    result = calculate_ad_daily_metrics(record, run_id=RUN_ID)
    assert result.status == "SUCCESS"
    assert _output_map(result) == {
        "ctr": _independent_round(1030, 82500),
        "cvr": _independent_round(52, 1030),
        "roas": _independent_round(709500, 206000),
    }
    assert _output_map(result) == {"ctr": "0.0125", "cvr": "0.0505", "roas": "3.4442"}


@pytest.mark.parametrize(
    ("impressions", "expected"),
    [(20001, "0"), (20000, "0.0001"), (19999, "0.0001")],
)
def test_ctr_values_below_at_and_above_half_up_tie(records, impressions, expected):
    result = calculate_ad_daily_metrics(
        _formula_record(records, impressions=impressions, clicks=1, ad_orders=0), run_id=RUN_ID
    )
    assert _output_map(result)["ctr"] == expected


@pytest.mark.parametrize(
    ("spend", "expected"),
    [("20001", "0"), ("20000", "0.0001"), ("19999", "0.0001")],
)
def test_roas_values_below_at_and_above_half_up_tie(records, spend, expected):
    result = calculate_ad_daily_metrics(
        _formula_record(records, ad_spend=spend, ad_revenue="1"), run_id=RUN_ID
    )
    assert _output_map(result)["roas"] == expected


def test_exact_rounding_has_no_double_rounding(records):
    record = _formula_record(records, impressions=20_000, clicks=2, ad_orders=1)
    result = calculate_ad_daily_metrics(record, run_id=RUN_ID)
    assert _output_map(result)["ctr"] == "0.0001"
    assert _output_map(result)["cvr"] == "0.5"


def test_very_large_integer_coefficients_are_exact(records):
    impressions = (10**250) + 1
    clicks = 10**249
    result = calculate_ad_daily_metrics(
        _formula_record(records, impressions=impressions, clicks=clicks, ad_orders=0), run_id=RUN_ID
    )
    assert _output_map(result)["ctr"] == _independent_round(clicks, impressions)


def test_large_positive_and_negative_decimal_exponent_deltas(records):
    huge = "1" + ("0" * 220)
    tiny = "0." + ("0" * 219) + "1"
    large_result = calculate_ad_daily_metrics(
        _formula_record(records, ad_revenue=huge, ad_spend=tiny), run_id=RUN_ID
    )
    small_result = calculate_ad_daily_metrics(
        _formula_record(records, ad_revenue=tiny, ad_spend=huge), run_id=RUN_ID
    )
    assert _output_map(large_result)["roas"] == "1" + ("0" * 440)
    assert _output_map(small_result)["roas"] == "0"


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


def test_ambient_decimal_context_does_not_affect_or_change_result(records):
    context = decimal.getcontext()
    original = context.copy()
    try:
        context.prec = 2
        context.rounding = decimal.ROUND_DOWN
        context.clear_flags()
        before = _context_state(decimal.getcontext())
        result = calculate_ad_daily_metrics(_ad_daily(records), run_id=RUN_ID)
        after = _context_state(decimal.getcontext())
        assert _output_map(result) == {"ctr": "0.0125", "cvr": "0.0505", "roas": "3.4442"}
        assert after == before
    finally:
        decimal.setcontext(original)


def test_negative_zero_and_zero_revenue_behavior(records):
    partial = calculate_ad_daily_metrics(
        _formula_record(records, ad_spend="-0.000", ad_revenue="-0"), run_id=RUN_ID
    )
    success = calculate_ad_daily_metrics(
        _formula_record(records, ad_spend="1.00", ad_revenue="-0.000"), run_id=RUN_ID
    )
    assert partial.status == "PARTIAL"
    assert partial.errors[-1] == AdvertisingMetricsError("ZERO_DENOMINATOR", "roas", "ad_spend")
    assert _output_map(success)["roas"] == "0"


@pytest.mark.parametrize(
    ("carrier", "field_names"),
    [
        (AdvertisingMetricOutput, ("metric", "value")),
        (
            AdvertisingMetricsInputRef,
            ("contract_name", "natural_key", "source", "data_as_of", "input_hash"),
        ),
        (AdvertisingMetricsError, ("code", "metric", "field")),
        (
            AdvertisingMetricsResult,
            (
                "metric_family",
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


@pytest.mark.parametrize("status", ["SUCCESS", "PARTIAL", "ERROR"])
def test_valid_direct_construction_and_deep_immutability(status):
    result = _direct_result(status=status)
    with pytest.raises(FrozenInstanceError):
        result.status = "ERROR"
    with pytest.raises((FrozenInstanceError, TypeError)):
        result.new_field = "no"
    with pytest.raises(TypeError):
        result.outputs[0] = AdvertisingMetricOutput("ctr", "1")
    assert not hasattr(result, "__dict__")
    assert all(not hasattr(item, "__dict__") for item in (*result.outputs, *result.input_refs))


def test_direct_constructor_requires_only_exact_run_id_string_not_core_grammar():
    result = _direct_result(run_id="not-a-core-run-id")
    assert result.run_id == "not-a-core-run-id"
    with pytest.raises(TypeError):
        _direct_result(run_id=MutableString(RUN_ID))


def test_direct_constructor_requires_exact_sku_string_and_coherence_not_sku_grammar():
    result = _direct_result(sku="not core sku")
    assert result.sku == "not core sku" == result.input_refs[0].natural_key[2]
    with pytest.raises(TypeError):
        _direct_result(sku=MutableString("TS-TEST-001"))
    with pytest.raises(ValueError):
        AdvertisingMetricsResult(
            metric_family="AD_DAILY_ADVERTISING_METRICS",
            formula_version=AD_METRICS_FORMULA_VERSION,
            run_id=RUN_ID,
            sku="TS-OTHER-002",
            status="SUCCESS",
            outputs=tuple(AdvertisingMetricOutput(metric, "1") for metric in METRICS),
            input_refs=(_input_ref(),),
            errors=(),
        )


@pytest.mark.parametrize(
    "value",
    [
        "-1",
        "1.0000",
        "0.0",
        "1e2",
        "1.",
        "0.12345",
        pytest.param("\u00b2", id="superscript-two"),
        pytest.param("\u0660", id="arabic-indic-zero"),
        pytest.param("\u0661", id="arabic-indic-one"),
        pytest.param("\uff11", id="fullwidth-one"),
        pytest.param("1\u0660", id="ascii-arabic-indic"),
        pytest.param("\u06601", id="arabic-indic-ascii"),
    ],
)
def test_output_rejects_noncanonical_published_representations(value):
    with pytest.raises(ValueError):
        AdvertisingMetricOutput("ctr", value)


@pytest.mark.parametrize("value", ["0", "0.5", "1", "12.3456"])
def test_output_accepts_published_canonical_representations(value):
    assert AdvertisingMetricOutput("roas", value).value == value


def test_runtime_calculated_outputs_are_ascii_canonical(records):
    result = calculate_ad_daily_metrics(_ad_daily(records), run_id=RUN_ID)
    assert all(output.value.isascii() for output in result.outputs)


def test_exact_scalar_types_reject_mutable_string_subclasses():
    mutable = MutableString("ctr")
    mutable.state = []
    with pytest.raises(TypeError):
        AdvertisingMetricOutput(mutable, "1")
    with pytest.raises(TypeError):
        AdvertisingMetricsError(MutableString("INVALID_INPUT"), None, "clicks")
    with pytest.raises(TypeError):
        AdvertisingMetricsInputRef(
            "AD_DAILY",
            ("channel", "2026-01-01", "TS-TEST-001", "campaign", None),
            mutable,
            "2026-01-01T00:00:00+00:00",
            "hash",
        )


@pytest.mark.parametrize("bad_key", [[], {}, set(), (item for item in []), TupleSubclass(())])
def test_input_ref_rejects_wrong_natural_key_containers(bad_key):
    with pytest.raises(TypeError):
        AdvertisingMetricsInputRef("AD_DAILY", bad_key, "source", "as-of", "hash")


@pytest.mark.parametrize(
    "natural_key",
    [
        ("channel", "date", "sku", "campaign"),
        ("channel", "date", "sku", "campaign", None, "extra"),
        ("channel", "date", object(), "campaign", None),
        ("channel", "date", "sku", "campaign", 1),
    ],
)
def test_input_ref_rejects_invalid_length_and_item_types(natural_key):
    with pytest.raises(TypeError):
        AdvertisingMetricsInputRef("AD_DAILY", natural_key, "source", "as-of", "hash")


@pytest.mark.parametrize(
    "args",
    [
        ("INVALID_INPUT", "roas", "ad_spend"),
        ("INVALID_INPUT", None, "unknown"),
        ("ZERO_DENOMINATOR", "ctr", "clicks"),
        ("ZERO_DENOMINATOR", None, "impressions"),
        ("UNKNOWN", None, "impressions"),
    ],
)
def test_error_carrier_rejects_unreachable_combinations(args):
    with pytest.raises(ValueError):
        AdvertisingMetricsError(*args)


def test_result_rejects_wrong_containers_and_nested_types():
    valid = _direct_result()
    values = {
        "metric_family": valid.metric_family,
        "formula_version": valid.formula_version,
        "run_id": valid.run_id,
        "sku": valid.sku,
        "status": valid.status,
        "outputs": valid.outputs,
        "input_refs": valid.input_refs,
        "errors": valid.errors,
    }
    for field, bad in (
        ("outputs", list(valid.outputs)),
        ("input_refs", TupleSubclass(valid.input_refs)),
        ("errors", (item for item in valid.errors)),
        ("outputs", (CalculationOutput("contribution_margin", "1"),)),
        ("input_refs", (CalculationInputRef("PRODUCT_MASTER", ("SKU",), "s", "d", "h"),)),
    ):
        with pytest.raises(TypeError):
            AdvertisingMetricsResult(**(values | {field: bad}))


def test_result_rejects_invalid_status_specific_whole_states():
    reference = (_input_ref(),)
    with pytest.raises(ValueError):
        AdvertisingMetricsResult(
            "AD_DAILY_ADVERTISING_METRICS",
            AD_METRICS_FORMULA_VERSION,
            RUN_ID,
            "TS-TEST-001",
            "SUCCESS",
            (AdvertisingMetricOutput("ctr", "1"),),
            reference,
            (),
        )
    with pytest.raises(ValueError):
        AdvertisingMetricsResult(
            "AD_DAILY_ADVERTISING_METRICS",
            AD_METRICS_FORMULA_VERSION,
            RUN_ID,
            "TS-TEST-001",
            "PARTIAL",
            (AdvertisingMetricOutput("ctr", "1"),),
            reference,
            (AdvertisingMetricsError("ZERO_DENOMINATOR", "ctr", "impressions"),),
        )
    with pytest.raises(ValueError):
        AdvertisingMetricsResult(
            "AD_DAILY_ADVERTISING_METRICS",
            AD_METRICS_FORMULA_VERSION,
            RUN_ID,
            "TS-TEST-001",
            "ERROR",
            (),
            reference,
            (
                AdvertisingMetricsError("INVALID_INPUT", None, "clicks"),
                AdvertisingMetricsError("INVALID_INPUT", None, "impressions"),
            ),
        )


def test_every_result_has_exact_input_reference_and_provenance(records):
    cases = (
        _formula_record(records),
        _formula_record(records, clicks=0, ad_orders=0),
        _formula_record(records, impressions=-1),
    )
    for record in cases:
        result = calculate_ad_daily_metrics(record, run_id=RUN_ID)
        assert len(result.input_refs) == 1
        assert result.run_id == RUN_ID
        assert result.sku == record["sku"] == result.input_refs[0].natural_key[2]
        assert result.input_refs[0].contract_name == "AD_DAILY"


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("channel", "other_ads"),
        ("stat_date", "2026-09-14"),
        ("sku", "TS-OTHER-002"),
        ("campaign_id", "cmp_other"),
        ("ad_group_id", "grp_other"),
        ("impressions", 82501),
        ("clicks", 1029),
        ("ad_spend", "206001"),
        ("ad_orders", 51),
        ("ad_revenue", "709501"),
        ("source_file_hash", "sha256:" + ("b" * 64)),
        ("source", "other_source"),
        ("data_as_of", "2026-09-16T08:00:00+09:00"),
    ],
)
def test_each_included_hash_field_independently_changes_hash(records, field, replacement):
    original = _ad_daily(records)
    changed = deepcopy(original)
    changed[field] = replacement
    original_result = calculate_ad_daily_metrics(original, run_id=RUN_ID)
    changed_result = calculate_ad_daily_metrics(changed, run_id=RUN_ID)
    assert original_result.input_refs[0].input_hash == _independent_hash(original)
    assert changed_result.input_refs[0].input_hash == _independent_hash(changed)
    assert changed_result.input_refs[0].input_hash != original_result.input_refs[0].input_hash


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("run_id", OTHER_RUN_ID),
        ("created_at", "2026-09-17T09:10:00+09:00"),
        ("campaign_name", "other campaign"),
        ("ad_units", 999),
        ("ctr", "0.9999"),
        ("cvr", "0.9999"),
        ("roas", "999"),
    ],
)
def test_each_excluded_record_field_is_semantically_non_interfering(records, field, replacement):
    original = _ad_daily(records)
    changed = deepcopy(original)
    changed[field] = replacement
    assert calculate_ad_daily_metrics(original, run_id=RUN_ID) == calculate_ad_daily_metrics(
        changed, run_id=RUN_ID
    )


def test_lexically_distinct_decimal_inputs_have_distinct_hashes_and_equal_metrics(records):
    results = []
    for lexical in ("10", "10.0", "10.00"):
        record = _formula_record(records, ad_spend=lexical, ad_revenue=lexical)
        results.append(calculate_ad_daily_metrics(record, run_id=RUN_ID))
    assert len({result.input_refs[0].input_hash for result in results}) == 3
    assert {_output_map(result)["roas"] for result in results} == {"1"}


def test_optional_nulls_project_to_explicit_json_null(records):
    record = _ad_daily(records)
    record.pop("ad_group_id")
    record.pop("source_file_hash")
    result = calculate_ad_daily_metrics(record, run_id=RUN_ID)
    assert result.input_refs[0].natural_key[-1] is None
    assert result.input_refs[0].input_hash == _independent_hash(record)


def test_calculation_run_id_changes_only_result_run_id(records):
    record = _ad_daily(records)
    first = calculate_ad_daily_metrics(record, run_id=RUN_ID)
    second = calculate_ad_daily_metrics(record, run_id=OTHER_RUN_ID)
    assert first.run_id == RUN_ID
    assert second.run_id == OTHER_RUN_ID
    assert first.input_refs == second.input_refs
    assert first.status == second.status
    assert first.outputs == second.outputs
    assert first.errors == second.errors
    assert first.sku == second.sku


def test_exact_hash_payload_is_structurally_fixed_and_excludes_formula_version():
    source_path = (
        Path(__file__).parents[1] / "src" / "topspeed_ai_os" / "calculation" / "ad_daily_metrics.py"
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
    keys = tuple(key.value for key in payload_assignment.value.keys)
    assert keys == HASH_FIELDS
    assert "formula_version" not in keys


def test_exact_natural_key_and_source_values(records):
    record = _ad_daily(records, ad_group_id=None, source_file_hash=None)
    reference = calculate_ad_daily_metrics(record, run_id=RUN_ID).input_refs[0]
    assert reference.natural_key == (
        record["channel"],
        record["stat_date"],
        record["sku"],
        record["campaign_id"],
        None,
    )
    assert reference.source == record["source"]
    assert reference.data_as_of == record["data_as_of"]


def test_replay_is_structurally_equal_and_input_is_not_mutated(records):
    record = _ad_daily(records)
    original = deepcopy(record)
    first = calculate_ad_daily_metrics(record, run_id=RUN_ID)
    second = calculate_ad_daily_metrics(record, run_id=RUN_ID)
    assert first == second
    assert record == original


def test_production_imports_are_exactly_deterministic_dependencies():
    source_path = (
        Path(__file__).parents[1] / "src" / "topspeed_ai_os" / "calculation" / "ad_daily_metrics.py"
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
        "contribution_margin",
    }


def test_production_has_no_external_or_nondeterministic_capabilities_or_aliases():
    source_path = (
        Path(__file__).parents[1] / "src" / "topspeed_ai_os" / "calculation" / "ad_daily_metrics.py"
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
        "requests",
        "urllib",
    }
    used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    used_attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert forbidden_names.isdisjoint(used_names | used_attributes)


def test_contribution_margin_api_and_behavior_remain_unchanged(records):
    record = records()["PRODUCT_MASTER"]
    result = calculate_product_master_contribution_margin(record, run_id=RUN_ID)
    assert isinstance(result, CalculationResult)
    assert result.metric == CONTRIBUTION_MARGIN_METRIC
    assert result.formula_version == CONTRIBUTION_MARGIN_FORMULA_VERSION
    assert {output.name: output.value for output in result.outputs} == {
        "contribution_margin": "3356.8",
        "contribution_margin_rate": "0.2602",
    }
