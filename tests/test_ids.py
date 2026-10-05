from __future__ import annotations

import pytest

from topspeed_ai_os.core.ids import (
    InvalidIdentifierError,
    generate_approval_id,
    generate_asset_id,
    generate_fact_id,
    generate_idempotency_key,
    generate_run_id,
    generate_sku,
    generate_task_id,
    require_valid_asset_id,
    require_valid_fact_id,
    require_valid_sku,
    validate_approval_id,
    validate_asset_id,
    validate_fact_id,
    validate_idempotency_key,
    validate_run_id,
    validate_sku,
    validate_task_id,
)


@pytest.mark.parametrize(
    ("factory", "validator", "prefix"),
    [
        (generate_task_id, validate_task_id, "task_"),
        (generate_run_id, validate_run_id, "run_"),
        (generate_approval_id, validate_approval_id, "apr_"),
        (generate_idempotency_key, validate_idempotency_key, "idem_"),
        (generate_fact_id, validate_fact_id, "fact_"),
        (generate_asset_id, validate_asset_id, "asset_"),
    ],
)
def test_generated_ids_have_valid_prefix_and_format(factory, validator, prefix):
    value = factory()
    assert value.startswith(prefix)
    assert validator(value)


def test_generated_ids_do_not_collide_in_sample():
    values = {generate_run_id() for _ in range(5_000)}
    assert len(values) == 5_000


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        (validate_task_id, "task_not-a-ulid"),
        (validate_run_id, "task_01J00000000000000000000000"),
        (validate_approval_id, "apr_01I00000000000000000000000"),
        (validate_idempotency_key, "idem_"),
        (validate_fact_id, "run_01J00000000000000000000000"),
        (validate_fact_id, "fact_01I00000000000000000000000"),
        (validate_asset_id, "fact_01J00000000000000000000000"),
        (validate_asset_id, "asset_01I00000000000000000000000"),
        (validate_asset_id, "asset_01J0000000000000000000000"),
        (validate_asset_id, ""),
        (validate_asset_id, None),
        (validate_asset_id, True),
    ],
)
def test_invalid_prefixed_ids_are_rejected(validator, value):
    assert not validator(value)


def test_sku_generation_and_validation():
    assert generate_sku("ts", "kitchen", "001") == "TS-KITCHEN-001"
    assert generate_sku("top speed", "waist brace", "xl") == "TOP-SPEED-WAIST-BRACE-XL"
    assert validate_sku("TS-KITCHEN-001")
    assert not validate_sku("ts-kitchen-001")


def test_invalid_sku_raises():
    with pytest.raises(InvalidIdentifierError):
        generate_sku("only-one")
    with pytest.raises(InvalidIdentifierError):
        require_valid_sku("TS")


def test_require_valid_fact_id_uses_existing_identifier_error_convention():
    value = generate_fact_id()
    assert require_valid_fact_id(value) == value
    with pytest.raises(InvalidIdentifierError, match="invalid fact_id"):
        require_valid_fact_id("fact_not-a-ulid")


def test_require_valid_asset_id_uses_existing_identifier_error_convention():
    value = generate_asset_id()
    assert require_valid_asset_id(value) == value
    with pytest.raises(InvalidIdentifierError, match="invalid asset_id"):
        require_valid_asset_id("asset_not-a-ulid")
