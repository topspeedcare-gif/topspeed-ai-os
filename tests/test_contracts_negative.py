from __future__ import annotations

import pytest
from conftest import FACT_ID, OTHER_SKU, SKU

from topspeed_ai_os.contracts import CONTRACT_NAMES, ContractValidationError, load_schema
from topspeed_ai_os.contracts.registry import validate_record


@pytest.mark.parametrize("contract_name", CONTRACT_NAMES)
def test_missing_required_field_is_rejected(contract_name, records):
    record = records()[contract_name]
    required_field = load_schema(contract_name)["required"][0]
    record.pop(required_field)
    with pytest.raises(ContractValidationError):
        validate_record(contract_name, record, known_skus={SKU})


@pytest.mark.parametrize("contract_name", CONTRACT_NAMES)
def test_unknown_field_is_rejected(contract_name, records):
    record = records()[contract_name]
    record["unexpected_field"] = True
    with pytest.raises(ContractValidationError):
        validate_record(contract_name, record, known_skus={SKU})


@pytest.mark.parametrize(
    ("contract_name", "field"),
    [
        ("PRODUCT_MASTER", "data_as_of"),
        ("PRODUCT_FACT", "created_at"),
        ("CHANNEL_DAILY", "data_as_of"),
        ("AD_DAILY", "created_at"),
        ("INVENTORY", "snapshot_at"),
        ("CONTENT_ASSET", "updated_at"),
        ("APPROVAL_QUEUE", "expires_at"),
        ("AI_RUN_LOG", "started_at"),
    ],
)
def test_timezone_free_datetime_is_rejected(contract_name, field, records):
    record = records()[contract_name]
    record[field] = "2026-09-16T09:10:00"
    with pytest.raises(ContractValidationError):
        validate_record(contract_name, record, known_skus={SKU})


@pytest.mark.parametrize(
    ("contract_name", "field", "invalid_value"),
    [
        ("PRODUCT_MASTER", "stage", "GROW"),
        ("PRODUCT_MASTER", "grade", "C"),
        ("PRODUCT_FACT", "verification_status", "VALID"),
        ("CONTENT_ASSET", "asset_type", "VIDEO"),
        ("APPROVAL_QUEUE", "audit_status", "OK"),
        ("APPROVAL_QUEUE", "approval_status", "WAITING"),
        ("AI_RUN_LOG", "skill", "finance"),
        ("AI_RUN_LOG", "result", "DONE"),
    ],
)
def test_unknown_enum_is_rejected(contract_name, field, invalid_value, records):
    record = records()[contract_name]
    record[field] = invalid_value
    with pytest.raises(ContractValidationError):
        validate_record(contract_name, record, known_skus={SKU})


def test_unregistered_sku_is_rejected(records):
    record = records()["AD_DAILY"]
    with pytest.raises(ContractValidationError, match="not registered"):
        validate_record("AD_DAILY", record, known_skus={OTHER_SKU})


def test_cross_sku_content_fact_is_rejected(records):
    record = records()["CONTENT_ASSET"]
    with pytest.raises(ContractValidationError, match="belongs to"):
        validate_record(
            "CONTENT_ASSET",
            record,
            known_skus={SKU},
            fact_sku_by_id={FACT_ID: OTHER_SKU},
        )


def test_unknown_content_fact_is_rejected(records):
    record = records()["CONTENT_ASSET"]
    with pytest.raises(ContractValidationError, match="unknown PRODUCT_FACT"):
        validate_record(
            "CONTENT_ASSET",
            record,
            known_skus={SKU},
            fact_sku_by_id={},
        )


def test_fail_audit_cannot_be_pending_approval(records):
    record = records()["APPROVAL_QUEUE"]
    record["audit_status"] = "FAIL"
    record["approval_status"] = "PENDING"
    with pytest.raises(ContractValidationError, match="FAIL audit"):
        validate_record("APPROVAL_QUEUE", record, known_skus={SKU})


def test_tampered_approval_payload_is_rejected(records):
    record = records()["APPROVAL_QUEUE"]
    record["proposed_payload"]["daily_budget"] = 300001
    with pytest.raises(ContractValidationError, match="does not match"):
        validate_record("APPROVAL_QUEUE", record, known_skus={SKU})


def test_non_canonical_approval_payload_is_contract_error(records):
    record = records()["APPROVAL_QUEUE"]
    record["proposed_payload"]["daily_budget"] = float("nan")
    with pytest.raises(ContractValidationError, match="cannot be canonicalized"):
        validate_record("APPROVAL_QUEUE", record, known_skus={SKU})


def test_wrong_id_prefix_is_rejected(records):
    record = records()["APPROVAL_QUEUE"]
    record["approval_id"] = record["run_id"]
    with pytest.raises(ContractValidationError):
        validate_record("APPROVAL_QUEUE", record, known_skus={SKU})


def test_invalid_decimal_is_rejected(records):
    record = records()["PRODUCT_MASTER"]
    record["sale_price"] = "12,900원"
    with pytest.raises(ContractValidationError):
        validate_record("PRODUCT_MASTER", record)
