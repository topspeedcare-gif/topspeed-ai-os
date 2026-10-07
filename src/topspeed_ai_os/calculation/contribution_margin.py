"""Pure PRODUCT_MASTER contribution-margin calculation."""

import decimal
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from topspeed_ai_os.contracts import validate_schema_only
from topspeed_ai_os.contracts.logical_types import parse_canonical_decimal
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.core.ids import require_valid_run_id

CONTRIBUTION_MARGIN_METRIC = "CONTRIBUTION_MARGIN"
CONTRIBUTION_MARGIN_FORMULA_VERSION = "topspeed.calculation.contribution_margin.v1"

_FORMULA_FIELDS = (
    "sale_price",
    "purchase_cost",
    "fee_rate",
    "fulfillment_cost",
    "expected_return_cost",
    "other_variable_cost",
)


@dataclass(frozen=True, slots=True)
class CalculationOutput:
    name: Literal["contribution_margin", "contribution_margin_rate"]
    value: str


@dataclass(frozen=True, slots=True)
class CalculationInputRef:
    contract_name: str
    natural_key: tuple[str, ...]
    source: str
    data_as_of: str
    input_hash: str


@dataclass(frozen=True, slots=True)
class CalculationError:
    code: Literal["MISSING_INPUT", "ZERO_SALE_PRICE", "INVALID_INPUT"]
    field: Literal[
        "sale_price",
        "purchase_cost",
        "fee_rate",
        "fulfillment_cost",
        "expected_return_cost",
        "other_variable_cost",
    ]


@dataclass(frozen=True, slots=True)
class CalculationResult:
    metric: str
    formula_version: str
    run_id: str
    sku: str
    status: Literal["SUCCESS", "ERROR"]
    outputs: tuple[CalculationOutput, ...]
    input_refs: tuple[CalculationInputRef, ...]
    errors: tuple[CalculationError, ...]


class UnsupportedFormulaVersionError(ValueError):
    """Raised when a caller requests an unsupported formula version."""


def _input_ref(product_master: Mapping[str, object]) -> CalculationInputRef:
    payload = {
        "sku": product_master["sku"],
        "currency": product_master["currency"],
        "sale_price": product_master.get("sale_price"),
        "purchase_cost": product_master.get("purchase_cost"),
        "fee_rate": product_master.get("fee_rate"),
        "fulfillment_cost": product_master.get("fulfillment_cost"),
        "expected_return_cost": product_master.get("expected_return_cost"),
        "other_variable_cost": product_master.get("other_variable_cost"),
        "source": product_master["source"],
        "data_as_of": product_master["data_as_of"],
    }
    return CalculationInputRef(
        contract_name="PRODUCT_MASTER",
        natural_key=(product_master["sku"],),
        source=product_master["source"],
        data_as_of=product_master["data_as_of"],
        input_hash=payload_sha256(payload),
    )


def _new_decimal_context(precision: int) -> decimal.Context:
    context = decimal.Context(
        prec=precision,
        rounding=decimal.ROUND_HALF_UP,
        Emin=decimal.MIN_EMIN,
        Emax=decimal.MAX_EMAX,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[],
    )
    for signal in (
        decimal.Inexact,
        decimal.Rounded,
        decimal.InvalidOperation,
        decimal.DivisionByZero,
        decimal.Overflow,
    ):
        context.traps[signal] = True
    context.clear_flags()
    return context


def _coefficient_digits(value: decimal.Decimal) -> int:
    return len(value.as_tuple().digits)


def _exponent(value: decimal.Decimal) -> int:
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise decimal.InvalidOperation("non-finite Decimal")
    return exponent


def _calculate_margin(values: tuple[decimal.Decimal, ...]) -> decimal.Decimal:
    (
        sale_price,
        purchase_cost,
        fee_rate,
        fulfillment_cost,
        expected_return_cost,
        other_variable_cost,
    ) = values

    product_coefficient_digits = _coefficient_digits(sale_price) + _coefficient_digits(fee_rate)
    fee_context = _new_decimal_context(max(product_coefficient_digits, 1))
    fee_amount = fee_context.multiply(sale_price, fee_rate)

    monetary_terms = (
        sale_price,
        purchase_cost,
        fee_amount,
        fulfillment_cost,
        expected_return_cost,
        other_variable_cost,
    )
    common_exponent = min(_exponent(term) for term in monetary_terms)
    aligned_maximum = max(
        _coefficient_digits(term) + max(0, _exponent(term) - common_exponent)
        for term in monetary_terms
    )
    margin_precision = max(product_coefficient_digits, aligned_maximum + 1, 1)
    margin_context = _new_decimal_context(margin_precision)

    contribution_margin = sale_price
    for term in monetary_terms[1:]:
        contribution_margin = margin_context.subtract(contribution_margin, term)
    return contribution_margin


def _unsigned_coefficient(value: decimal.Decimal) -> int:
    digits = value.as_tuple().digits
    return int("".join(str(digit) for digit in digits))


def _round_rate(
    contribution_margin: decimal.Decimal,
    sale_price: decimal.Decimal,
) -> decimal.Decimal:
    margin_tuple = contribution_margin.as_tuple()
    margin_coefficient = _unsigned_coefficient(contribution_margin)
    sale_coefficient = _unsigned_coefficient(sale_price)
    exponent_delta = _exponent(contribution_margin) - _exponent(sale_price) + 4

    if exponent_delta >= 0:
        numerator = margin_coefficient * (10**exponent_delta)
        denominator = sale_coefficient
    else:
        numerator = margin_coefficient
        denominator = sale_coefficient * (10 ** (-exponent_delta))

    quotient, remainder = divmod(numerator, denominator)
    if 2 * remainder >= denominator:
        quotient += 1

    sign = margin_tuple.sign if quotient else 0
    digits = tuple(int(character) for character in str(quotient))
    return decimal.Decimal((sign, digits, -4))


def _canonical_output(value: decimal.Decimal) -> str:
    if value.is_zero():
        return "0"
    output = format(value, "f")
    if "." in output:
        output = output.rstrip("0").rstrip(".")
    return output


def calculate_product_master_contribution_margin(
    product_master: Mapping[str, object],
    *,
    run_id: str,
    formula_version: str = CONTRIBUTION_MARGIN_FORMULA_VERSION,
) -> CalculationResult:
    if not isinstance(product_master, Mapping):
        raise TypeError("product_master must be a Mapping")

    validate_schema_only("PRODUCT_MASTER", product_master)
    validated_run_id = require_valid_run_id(run_id)
    if formula_version != CONTRIBUTION_MARGIN_FORMULA_VERSION:
        raise UnsupportedFormulaVersionError(f"unsupported formula version: {formula_version!r}")

    input_ref = _input_ref(product_master)
    parsed_values = tuple(
        None
        if product_master.get(field) is None
        else parse_canonical_decimal(product_master[field])
        for field in _FORMULA_FIELDS
    )

    errors: list[CalculationError] = []
    for field, value in zip(_FORMULA_FIELDS, parsed_values, strict=True):
        if value is None:
            errors.append(CalculationError(code="MISSING_INPUT", field=field))
        elif field == "sale_price" and value.is_zero():
            errors.append(CalculationError(code="ZERO_SALE_PRICE", field=field))
        elif (
            (field == "sale_price" and value < 0)
            or (field == "fee_rate" and (value < 0 or value > 1))
            or (field not in {"sale_price", "fee_rate"} and value < 0)
        ):
            errors.append(CalculationError(code="INVALID_INPUT", field=field))

    if errors:
        return CalculationResult(
            metric=CONTRIBUTION_MARGIN_METRIC,
            formula_version=CONTRIBUTION_MARGIN_FORMULA_VERSION,
            run_id=validated_run_id,
            sku=product_master["sku"],
            status="ERROR",
            outputs=(),
            input_refs=(input_ref,),
            errors=tuple(errors),
        )

    complete_values = tuple(value for value in parsed_values if value is not None)
    contribution_margin = _calculate_margin(complete_values)
    contribution_margin_rate = _round_rate(contribution_margin, complete_values[0])
    return CalculationResult(
        metric=CONTRIBUTION_MARGIN_METRIC,
        formula_version=CONTRIBUTION_MARGIN_FORMULA_VERSION,
        run_id=validated_run_id,
        sku=product_master["sku"],
        status="SUCCESS",
        outputs=(
            CalculationOutput(
                name="contribution_margin",
                value=_canonical_output(contribution_margin),
            ),
            CalculationOutput(
                name="contribution_margin_rate",
                value=_canonical_output(contribution_margin_rate),
            ),
        ),
        input_refs=(input_ref,),
        errors=(),
    )
