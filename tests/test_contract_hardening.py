from __future__ import annotations

import pytest
from conftest import FACT_ID, OTHER_SKU, SKU

from topspeed_ai_os.contracts import (
    ContractValidationError,
    validate_contract,
    validate_record,
    validate_schema_only,
)

DECIMAL_FIELDS = (
    ("PRODUCT_MASTER", "purchase_cost"),
    ("PRODUCT_MASTER", "sale_price"),
    ("PRODUCT_MASTER", "fee_rate"),
    ("PRODUCT_MASTER", "fulfillment_cost"),
    ("PRODUCT_MASTER", "expected_return_cost"),
    ("PRODUCT_MASTER", "other_variable_cost"),
    ("PRODUCT_MASTER", "contribution_margin"),
    ("PRODUCT_MASTER", "contribution_margin_rate"),
    ("CHANNEL_DAILY", "gross_sales"),
    ("CHANNEL_DAILY", "net_sales"),
    ("CHANNEL_DAILY", "refund_amount"),
    ("CHANNEL_DAILY", "channel_fees"),
    ("CHANNEL_DAILY", "settlement_amount"),
    ("CHANNEL_DAILY", "conversion_rate"),
    ("AD_DAILY", "ad_spend"),
    ("AD_DAILY", "ad_revenue"),
    ("AD_DAILY", "ctr"),
    ("AD_DAILY", "cvr"),
    ("AD_DAILY", "roas"),
    ("INVENTORY", "avg_daily_units"),
    ("INVENTORY", "stock_days"),
    ("AI_RUN_LOG", "human_edit_ratio"),
)

RATIO_FIELDS = (
    ("PRODUCT_MASTER", "fee_rate"),
    ("PRODUCT_MASTER", "contribution_margin_rate"),
    ("CHANNEL_DAILY", "conversion_rate"),
    ("AD_DAILY", "ctr"),
    ("AD_DAILY", "cvr"),
    ("AI_RUN_LOG", "human_edit_ratio"),
)

SKU_CONTRACTS = (
    "PRODUCT_FACT",
    "CHANNEL_DAILY",
    "AD_DAILY",
    "INVENTORY",
    "CONTENT_ASSET",
    "APPROVAL_QUEUE",
    "AI_RUN_LOG",
)


@pytest.mark.parametrize(("contract_name", "field"), DECIMAL_FIELDS)
@pytest.mark.parametrize(
    "invalid_value",
    [
        0.1,
        12900.55,
        float("nan"),
        float("inf"),
        float("-inf"),
        "1e3",
        "12,900",
        "12,900원",
        "01.20",
        ".5",
        "1.",
    ],
    ids=[
        "float-0.1",
        "float-12900.55",
        "nan",
        "infinity",
        "negative-infinity",
        "exponent",
        "thousands-separator",
        "decorated-amount",
        "leading-zero",
        "missing-integer-part",
        "missing-fractional-part",
    ],
)
def test_decimal_fields_reject_noncanonical_representations(
    contract_name, field, invalid_value, records
):
    record = records()[contract_name]
    record[field] = invalid_value
    with pytest.raises(ContractValidationError):
        validate_schema_only(contract_name, record)


@pytest.mark.parametrize(
    ("contract_name", "field", "valid_value"),
    [
        ("PRODUCT_MASTER", "sale_price", "0"),
        ("PRODUCT_MASTER", "purchase_cost", "5200"),
        ("PRODUCT_MASTER", "contribution_margin", "-12.5"),
        ("CHANNEL_DAILY", "gross_sales", "12900.55"),
        ("AD_DAILY", "roas", "3.4442"),
    ],
)
def test_decimal_fields_accept_canonical_strings(contract_name, field, valid_value, records):
    record = records()[contract_name]
    record[field] = valid_value
    validate_schema_only(contract_name, record)


@pytest.mark.parametrize(("contract_name", "field"), RATIO_FIELDS)
@pytest.mark.parametrize("valid_value", ["0", "1"])
def test_ratio_fields_accept_inclusive_bounds(contract_name, field, valid_value, records):
    record = records()[contract_name]
    record[field] = valid_value
    validate_schema_only(contract_name, record)


@pytest.mark.parametrize(("contract_name", "field"), RATIO_FIELDS)
@pytest.mark.parametrize("invalid_value", ["-0.001", "1.001", "-1", "2"])
def test_ratio_fields_reject_out_of_range_values(contract_name, field, invalid_value, records):
    record = records()[contract_name]
    record[field] = invalid_value
    with pytest.raises(ContractValidationError):
        validate_schema_only(contract_name, record)


@pytest.mark.parametrize(
    ("contract_name", "field", "value"),
    [
        ("AD_DAILY", "roas", "1000.5"),
        ("PRODUCT_MASTER", "sale_price", "1290000"),
        ("PRODUCT_MASTER", "contribution_margin", "-500"),
    ],
)
def test_non_ratio_decimals_do_not_receive_ratio_bounds(contract_name, field, value, records):
    record = records()[contract_name]
    record[field] = value
    validate_schema_only(contract_name, record)


@pytest.mark.parametrize("contract_name", SKU_CONTRACTS)
def test_full_validation_requires_known_skus_context(contract_name, records):
    record = records()[contract_name]
    with pytest.raises(ContractValidationError, match="known_skus context is required"):
        validate_contract(contract_name, record, fact_sku_by_id={FACT_ID: SKU})


def test_full_validation_rejects_unregistered_sku(records):
    record = records()["AD_DAILY"]
    with pytest.raises(ContractValidationError, match="not registered"):
        validate_contract("AD_DAILY", record, known_skus={OTHER_SKU})


def test_full_validation_accepts_registered_sku(records):
    validate_contract("AD_DAILY", records()["AD_DAILY"], known_skus={SKU})


@pytest.mark.parametrize("contract_name", ["APPROVAL_QUEUE", "AI_RUN_LOG"])
def test_full_validation_allows_explicit_null_sku_without_sku_context(contract_name, records):
    record = records()[contract_name]
    record["sku"] = None
    validate_contract(contract_name, record)


def test_schema_only_does_not_claim_sku_referential_integrity(records):
    validate_schema_only("AD_DAILY", records()["AD_DAILY"])


def test_validate_record_compatibility_api_is_fail_closed(records):
    with pytest.raises(ContractValidationError, match="known_skus context is required"):
        validate_record("AD_DAILY", records()["AD_DAILY"])


def test_content_asset_claims_require_fact_context(records):
    with pytest.raises(ContractValidationError, match="fact_sku_by_id context is required"):
        validate_contract("CONTENT_ASSET", records()["CONTENT_ASSET"], known_skus={SKU})


def test_content_asset_rejects_unknown_fact(records):
    with pytest.raises(ContractValidationError, match="unknown PRODUCT_FACT"):
        validate_contract(
            "CONTENT_ASSET",
            records()["CONTENT_ASSET"],
            known_skus={SKU},
            fact_sku_by_id={},
        )


def test_content_asset_rejects_cross_sku_fact(records):
    with pytest.raises(ContractValidationError, match="belongs to"):
        validate_contract(
            "CONTENT_ASSET",
            records()["CONTENT_ASSET"],
            known_skus={SKU},
            fact_sku_by_id={FACT_ID: OTHER_SKU},
        )


def test_content_asset_accepts_same_sku_fact(records):
    validate_contract(
        "CONTENT_ASSET",
        records()["CONTENT_ASSET"],
        known_skus={SKU},
        fact_sku_by_id={FACT_ID: SKU},
    )


@pytest.mark.parametrize("approval_status", ["PENDING", "APPROVED", "EXECUTED"])
def test_fail_audit_cannot_enter_approval_or_execution_path(approval_status, records):
    record = records()["APPROVAL_QUEUE"]
    record["audit_status"] = "FAIL"
    record["approval_status"] = approval_status
    with pytest.raises(ContractValidationError, match="FAIL audit"):
        validate_schema_only("APPROVAL_QUEUE", record)


@pytest.mark.parametrize("audit_status", ["PASS", "WARN"])
@pytest.mark.parametrize("approval_status", ["PENDING", "APPROVED", "EXECUTED"])
def test_non_fail_audit_normal_combinations_remain_valid(audit_status, approval_status, records):
    record = records()["APPROVAL_QUEUE"]
    record["audit_status"] = audit_status
    record["approval_status"] = approval_status
    validate_schema_only("APPROVAL_QUEUE", record)


@pytest.mark.parametrize("approval_status", ["REJECTED", "EXPIRED", "CANCELLED", "FAILED"])
def test_fail_audit_only_allows_non_progressing_terminal_states(approval_status, records):
    record = records()["APPROVAL_QUEUE"]
    record["audit_status"] = "FAIL"
    record["approval_status"] = approval_status
    validate_schema_only("APPROVAL_QUEUE", record)
