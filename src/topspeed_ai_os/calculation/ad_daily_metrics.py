"""Pure AD_DAILY advertising-metrics calculation."""

import decimal
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from topspeed_ai_os.contracts import validate_schema_only
from topspeed_ai_os.contracts.logical_types import parse_canonical_decimal
from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.core.ids import require_valid_run_id

from .contribution_margin import UnsupportedFormulaVersionError

AD_METRICS_FORMULA_VERSION = "topspeed.calculation.ad_metrics.v1"

_METRIC_FAMILY = "AD_DAILY_ADVERTISING_METRICS"
_METRICS = ("ctr", "cvr", "roas")
_PRIMITIVE_FIELDS = ("impressions", "clicks", "ad_spend", "ad_orders", "ad_revenue")
_CROSS_FIELD_ERRORS = (("ctr", "clicks/impressions"), ("cvr", "ad_orders/clicks"))
_ZERO_DENOMINATOR_FIELDS = {
    "ctr": "impressions",
    "cvr": "clicks",
    "roas": "ad_spend",
}


def _require_exact_str(value: object, field: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field} must be an exact str")


def _require_exact_tuple(value: object, field: str, item_type: type[object]) -> None:
    if type(value) is not tuple:
        raise TypeError(f"{field} must be an exact tuple")
    if any(type(item) is not item_type for item in value):
        raise TypeError(f"{field} items must be exact {item_type.__name__} instances")


def _validate_canonical_output(value: str) -> None:
    if not value or value.startswith("-") or value.count(".") > 1:
        raise ValueError("value must be a canonical nonnegative fixed-point string")
    whole, separator, fractional = value.partition(".")
    if not whole.isascii() or not whole.isdigit():
        raise ValueError("value must be a canonical nonnegative fixed-point string")
    if separator and (
        not fractional.isascii()
        or not fractional.isdigit()
        or len(fractional) > 4
        or fractional.endswith("0")
    ):
        raise ValueError("value must have one to four non-trailing-zero fractional digits")
    if all(character in {"0", "."} for character in value) and value != "0":
        raise ValueError("numeric zero must be exactly '0'")


@dataclass(frozen=True, slots=True)
class AdvertisingMetricOutput:
    metric: Literal["ctr", "cvr", "roas"]
    value: str

    def __post_init__(self) -> None:
        _require_exact_str(self.metric, "metric")
        _require_exact_str(self.value, "value")
        if self.metric not in _METRICS:
            raise ValueError(f"unsupported metric: {self.metric!r}")
        _validate_canonical_output(self.value)


@dataclass(frozen=True, slots=True)
class AdvertisingMetricsInputRef:
    contract_name: str
    natural_key: tuple[str, str, str, str, str | None]
    source: str
    data_as_of: str
    input_hash: str

    def __post_init__(self) -> None:
        _require_exact_str(self.contract_name, "contract_name")
        if self.contract_name != "AD_DAILY":
            raise ValueError("contract_name must be 'AD_DAILY'")
        if type(self.natural_key) is not tuple or len(self.natural_key) != 5:
            raise TypeError("natural_key must be an exact five-item tuple")
        if any(type(item) is not str for item in self.natural_key[:4]):
            raise TypeError("the first four natural_key items must be exact str values")
        if self.natural_key[4] is not None and type(self.natural_key[4]) is not str:
            raise TypeError("natural_key ad_group_id must be an exact str or None")
        _require_exact_str(self.source, "source")
        _require_exact_str(self.data_as_of, "data_as_of")
        _require_exact_str(self.input_hash, "input_hash")


@dataclass(frozen=True, slots=True)
class AdvertisingMetricsError:
    code: Literal["INVALID_INPUT", "ZERO_DENOMINATOR"]
    metric: Literal["ctr", "cvr", "roas"] | None
    field: str

    def __post_init__(self) -> None:
        _require_exact_str(self.code, "code")
        if self.metric is not None:
            _require_exact_str(self.metric, "metric")
        _require_exact_str(self.field, "field")

        if self.code == "INVALID_INPUT":
            primitive = self.metric is None and self.field in _PRIMITIVE_FIELDS
            cross_field = (self.metric, self.field) in _CROSS_FIELD_ERRORS
            if not (primitive or cross_field):
                raise ValueError("unreachable INVALID_INPUT error")
        elif self.code == "ZERO_DENOMINATOR":
            if self.metric not in _ZERO_DENOMINATOR_FIELDS:
                raise ValueError("unreachable ZERO_DENOMINATOR metric")
            if self.field != _ZERO_DENOMINATOR_FIELDS[self.metric]:
                raise ValueError("unreachable ZERO_DENOMINATOR field")
        else:
            raise ValueError(f"unsupported error code: {self.code!r}")


@dataclass(frozen=True, slots=True)
class AdvertisingMetricsResult:
    metric_family: str
    formula_version: str
    run_id: str
    sku: str
    status: Literal["SUCCESS", "PARTIAL", "ERROR"]
    outputs: tuple[AdvertisingMetricOutput, ...]
    input_refs: tuple[AdvertisingMetricsInputRef, ...]
    errors: tuple[AdvertisingMetricsError, ...]

    def __post_init__(self) -> None:
        _require_exact_str(self.metric_family, "metric_family")
        _require_exact_str(self.formula_version, "formula_version")
        _require_exact_str(self.run_id, "run_id")
        _require_exact_str(self.sku, "sku")
        _require_exact_str(self.status, "status")
        _require_exact_tuple(self.outputs, "outputs", AdvertisingMetricOutput)
        _require_exact_tuple(self.input_refs, "input_refs", AdvertisingMetricsInputRef)
        _require_exact_tuple(self.errors, "errors", AdvertisingMetricsError)

        if self.metric_family != _METRIC_FAMILY:
            raise ValueError(f"metric_family must be {_METRIC_FAMILY!r}")
        if self.formula_version != AD_METRICS_FORMULA_VERSION:
            raise ValueError(f"formula_version must be {AD_METRICS_FORMULA_VERSION!r}")
        if self.status not in {"SUCCESS", "PARTIAL", "ERROR"}:
            raise ValueError(f"unsupported status: {self.status!r}")
        if len(self.input_refs) != 1:
            raise ValueError("input_refs must contain exactly one AD_DAILY reference")
        if self.sku != self.input_refs[0].natural_key[2]:
            raise ValueError("sku must equal input_refs[0].natural_key[2]")

        if self.status == "SUCCESS":
            if tuple(output.metric for output in self.outputs) != _METRICS or self.errors:
                raise ValueError("invalid SUCCESS result")
        elif self.status == "PARTIAL":
            self._validate_partial()
        else:
            self._validate_error()

    def _validate_partial(self) -> None:
        if not self.errors or any(error.code != "ZERO_DENOMINATOR" for error in self.errors):
            raise ValueError("PARTIAL requires one or more ZERO_DENOMINATOR errors")
        output_metrics = tuple(output.metric for output in self.outputs)
        error_metrics = tuple(error.metric for error in self.errors)
        expected_outputs = tuple(metric for metric in _METRICS if metric in output_metrics)
        expected_errors = tuple(metric for metric in _METRICS if metric in error_metrics)
        if output_metrics != expected_outputs or error_metrics != expected_errors:
            raise ValueError("PARTIAL metrics must be unique and canonically ordered")
        if set(output_metrics) & set(error_metrics):
            raise ValueError("PARTIAL output and error metrics must be disjoint")
        if set(output_metrics) | set(error_metrics) != set(_METRICS):
            raise ValueError("PARTIAL output and error metrics must cover all metrics")

    def _validate_error(self) -> None:
        if (
            self.outputs
            or not self.errors
            or any(error.code != "INVALID_INPUT" for error in self.errors)
        ):
            raise ValueError("ERROR requires no outputs and ordered INVALID_INPUT errors")
        if all(error.metric is None for error in self.errors):
            fields = tuple(error.field for error in self.errors)
            expected = tuple(field for field in _PRIMITIVE_FIELDS if field in fields)
            if fields != expected:
                raise ValueError("primitive INVALID_INPUT errors must be unique and ordered")
            return
        if any(error.metric is None for error in self.errors):
            raise ValueError("primitive and cross-field INVALID_INPUT errors cannot coexist")
        pairs = tuple((error.metric, error.field) for error in self.errors)
        expected_pairs = tuple(pair for pair in _CROSS_FIELD_ERRORS if pair in pairs)
        if pairs != expected_pairs:
            raise ValueError("cross-field INVALID_INPUT errors must be unique and ordered")


def _input_ref(ad_daily: Mapping[str, object]) -> AdvertisingMetricsInputRef:
    payload = {
        "channel": ad_daily["channel"],
        "stat_date": ad_daily["stat_date"],
        "sku": ad_daily["sku"],
        "campaign_id": ad_daily["campaign_id"],
        "ad_group_id": ad_daily.get("ad_group_id"),
        "impressions": ad_daily["impressions"],
        "clicks": ad_daily["clicks"],
        "ad_spend": ad_daily["ad_spend"],
        "ad_orders": ad_daily["ad_orders"],
        "ad_revenue": ad_daily["ad_revenue"],
        "source_file_hash": ad_daily.get("source_file_hash"),
        "source": ad_daily["source"],
        "data_as_of": ad_daily["data_as_of"],
    }
    return AdvertisingMetricsInputRef(
        contract_name="AD_DAILY",
        natural_key=(
            ad_daily["channel"],
            ad_daily["stat_date"],
            ad_daily["sku"],
            ad_daily["campaign_id"],
            ad_daily.get("ad_group_id"),
        ),
        source=ad_daily["source"],
        data_as_of=ad_daily["data_as_of"],
        input_hash=payload_sha256(payload),
    )


def _rounded_ratio(numerator: int, denominator: int) -> str:
    quotient, remainder = divmod(numerator * 10_000, denominator)
    if 2 * remainder >= denominator:
        quotient += 1
    if quotient == 0:
        return "0"
    whole, fractional = divmod(quotient, 10_000)
    if fractional == 0:
        return str(whole)
    return f"{whole}.{fractional:04d}".rstrip("0")


def _coefficient_and_exponent(value: decimal.Decimal) -> tuple[int, int]:
    value_tuple = value.as_tuple()
    coefficient = 0
    for digit in value_tuple.digits:
        coefficient = coefficient * 10 + digit
    if not isinstance(value_tuple.exponent, int):
        raise decimal.InvalidOperation("non-finite Decimal")
    return coefficient, value_tuple.exponent


def _rounded_roas(ad_revenue: decimal.Decimal, ad_spend: decimal.Decimal) -> str:
    revenue_coefficient, revenue_exponent = _coefficient_and_exponent(ad_revenue)
    spend_coefficient, spend_exponent = _coefficient_and_exponent(ad_spend)
    exponent_delta = revenue_exponent - spend_exponent
    if exponent_delta >= 0:
        numerator = revenue_coefficient * (10**exponent_delta)
        denominator = spend_coefficient
    else:
        numerator = revenue_coefficient
        denominator = spend_coefficient * (10 ** (-exponent_delta))
    return _rounded_ratio(numerator, denominator)


def _result(
    *,
    run_id: str,
    sku: str,
    status: Literal["SUCCESS", "PARTIAL", "ERROR"],
    outputs: tuple[AdvertisingMetricOutput, ...],
    input_ref: AdvertisingMetricsInputRef,
    errors: tuple[AdvertisingMetricsError, ...],
) -> AdvertisingMetricsResult:
    return AdvertisingMetricsResult(
        metric_family=_METRIC_FAMILY,
        formula_version=AD_METRICS_FORMULA_VERSION,
        run_id=run_id,
        sku=sku,
        status=status,
        outputs=outputs,
        input_refs=(input_ref,),
        errors=errors,
    )


def calculate_ad_daily_metrics(
    ad_daily: Mapping[str, object],
    *,
    run_id: str,
    formula_version: str = AD_METRICS_FORMULA_VERSION,
) -> AdvertisingMetricsResult:
    if not isinstance(ad_daily, Mapping):
        raise TypeError("ad_daily must be a Mapping")

    validate_schema_only("AD_DAILY", ad_daily)
    validated_run_id = require_valid_run_id(run_id)
    if formula_version != AD_METRICS_FORMULA_VERSION:
        raise UnsupportedFormulaVersionError(f"unsupported formula version: {formula_version!r}")

    input_ref = _input_ref(ad_daily)
    ad_spend = parse_canonical_decimal(ad_daily["ad_spend"])
    ad_revenue = parse_canonical_decimal(ad_daily["ad_revenue"])
    primitive_values = (
        ad_daily["impressions"],
        ad_daily["clicks"],
        ad_spend,
        ad_daily["ad_orders"],
        ad_revenue,
    )
    primitive_errors = tuple(
        AdvertisingMetricsError(code="INVALID_INPUT", metric=None, field=field)
        for field, value in zip(_PRIMITIVE_FIELDS, primitive_values, strict=True)
        if value < 0
    )
    if primitive_errors:
        return _result(
            run_id=validated_run_id,
            sku=ad_daily["sku"],
            status="ERROR",
            outputs=(),
            input_ref=input_ref,
            errors=primitive_errors,
        )

    cross_field_errors: list[AdvertisingMetricsError] = []
    if ad_daily["clicks"] > ad_daily["impressions"]:
        cross_field_errors.append(
            AdvertisingMetricsError(code="INVALID_INPUT", metric="ctr", field="clicks/impressions")
        )
    if ad_daily["ad_orders"] > ad_daily["clicks"]:
        cross_field_errors.append(
            AdvertisingMetricsError(code="INVALID_INPUT", metric="cvr", field="ad_orders/clicks")
        )
    if cross_field_errors:
        return _result(
            run_id=validated_run_id,
            sku=ad_daily["sku"],
            status="ERROR",
            outputs=(),
            input_ref=input_ref,
            errors=tuple(cross_field_errors),
        )

    denominator_errors: list[AdvertisingMetricsError] = []
    outputs: list[AdvertisingMetricOutput] = []
    if ad_daily["impressions"] == 0:
        denominator_errors.append(
            AdvertisingMetricsError(code="ZERO_DENOMINATOR", metric="ctr", field="impressions")
        )
    else:
        outputs.append(
            AdvertisingMetricOutput(
                metric="ctr",
                value=_rounded_ratio(ad_daily["clicks"], ad_daily["impressions"]),
            )
        )
    if ad_daily["clicks"] == 0:
        denominator_errors.append(
            AdvertisingMetricsError(code="ZERO_DENOMINATOR", metric="cvr", field="clicks")
        )
    else:
        outputs.append(
            AdvertisingMetricOutput(
                metric="cvr",
                value=_rounded_ratio(ad_daily["ad_orders"], ad_daily["clicks"]),
            )
        )
    if ad_spend.is_zero():
        denominator_errors.append(
            AdvertisingMetricsError(code="ZERO_DENOMINATOR", metric="roas", field="ad_spend")
        )
    else:
        outputs.append(
            AdvertisingMetricOutput(metric="roas", value=_rounded_roas(ad_revenue, ad_spend))
        )

    return _result(
        run_id=validated_run_id,
        sku=ad_daily["sku"],
        status="PARTIAL" if denominator_errors else "SUCCESS",
        outputs=tuple(outputs),
        input_ref=input_ref,
        errors=tuple(denominator_errors),
    )
