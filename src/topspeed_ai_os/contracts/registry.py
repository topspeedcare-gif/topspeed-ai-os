"""JSON Schema loading plus engine-independent cross-record checks."""

from __future__ import annotations

import json
from collections.abc import Mapping, Set
from decimal import Decimal
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, ValidationError, validators

from topspeed_ai_os.core.canonical import CanonicalizationError, verify_payload_hash

from .definitions import CONTRACT_NAMES
from .logical_types import InvalidDecimalError, is_canonical_decimal, parse_canonical_decimal

_FORMAT_CHECKER = FormatChecker()
_NON_PROGRESSING_FAIL_STATUSES = frozenset({"REJECTED", "EXPIRED", "CANCELLED", "FAILED"})


@_FORMAT_CHECKER.checks("canonical-decimal")
def _check_canonical_decimal(value: object) -> bool:
    return is_canonical_decimal(value)


def _validate_decimal_range(
    validator: Any,
    range_definition: Mapping[str, str],
    instance: object,
    schema: Mapping[str, Any],
) -> Any:
    del validator, schema
    try:
        value = parse_canonical_decimal(instance)
    except InvalidDecimalError:
        return

    minimum = range_definition.get("minimum")
    maximum = range_definition.get("maximum")
    if minimum is not None and value < Decimal(minimum):
        yield ValidationError(f"{instance!r} is less than decimal minimum {minimum!r}")
    if maximum is not None and value > Decimal(maximum):
        yield ValidationError(f"{instance!r} is greater than decimal maximum {maximum!r}")


_ContractSchemaValidator = validators.extend(
    Draft202012Validator,
    {"x-decimal-range": _validate_decimal_range},
)


class ContractValidationError(ValueError):
    """Raised when a record violates schema or cross-record invariants."""

    def __init__(self, contract_name: str, findings: list[str]) -> None:
        self.contract_name = contract_name
        self.findings = tuple(findings)
        super().__init__(f"{contract_name} validation failed: {'; '.join(findings)}")


def load_schema(contract_name: str) -> dict[str, Any]:
    if contract_name not in CONTRACT_NAMES:
        raise KeyError(f"unknown contract: {contract_name}")
    resource = files("topspeed_ai_os.contracts").joinpath(
        "schemas", f"{contract_name.lower()}.schema.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def _format_path(path: Any) -> str:
    parts = [str(item) for item in path]
    return ".".join(parts) if parts else "$"


def _schema_findings(contract_name: str, record: Mapping[str, Any]) -> list[str]:
    schema = load_schema(contract_name)
    validator = _ContractSchemaValidator(schema, format_checker=_FORMAT_CHECKER)
    errors = sorted(validator.iter_errors(dict(record)), key=lambda error: list(error.path))
    return [f"{_format_path(error.path)}: {error.message}" for error in errors]


def _single_record_findings(contract_name: str, record: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []

    if contract_name == "APPROVAL_QUEUE":
        audit_status = record.get("audit_status")
        approval_status = record.get("approval_status")
        if audit_status == "FAIL" and approval_status not in _NON_PROGRESSING_FAIL_STATUSES:
            findings.append(
                "approval_status: FAIL audit cannot enter an approval or execution path"
            )

        try:
            hash_matches = verify_payload_hash(
                record.get("proposed_payload"), record.get("payload_hash")
            )
        except CanonicalizationError as exc:
            findings.append(f"proposed_payload: cannot be canonicalized: {exc}")
        else:
            if not hash_matches:
                findings.append("payload_hash: does not match canonical proposed_payload")

    return findings


def validate_schema_only(contract_name: str, record: Mapping[str, Any]) -> None:
    """Validate rules decidable from one record, without claiming referential integrity."""

    findings = _schema_findings(contract_name, record)
    findings.extend(_single_record_findings(contract_name, record))
    if findings:
        raise ContractValidationError(contract_name, findings)


def validate_contract(
    contract_name: str,
    record: Mapping[str, Any],
    *,
    known_skus: Set[str] | None = None,
    fact_sku_by_id: Mapping[str, str] | None = None,
) -> None:
    """Perform fail-closed operational validation of a Data Contract record.

    In addition to single-record rules, ``known_skus`` enforces PRODUCT_MASTER
    referential integrity. CONTENT_ASSET claim facts require ``fact_sku_by_id``.
    """

    findings = _schema_findings(contract_name, record)
    findings.extend(_single_record_findings(contract_name, record))

    sku = record.get("sku")
    if contract_name != "PRODUCT_MASTER" and sku is not None:
        if known_skus is None:
            findings.append("sku: known_skus context is required for full validation")
        elif sku not in known_skus:
            findings.append(f"sku: {sku!r} is not registered in PRODUCT_MASTER")

    claim_fact_ids = record.get("claim_fact_ids")
    if contract_name == "CONTENT_ASSET" and isinstance(claim_fact_ids, list) and claim_fact_ids:
        if fact_sku_by_id is None:
            findings.append(
                "claim_fact_ids: fact_sku_by_id context is required when claims are present"
            )
        elif isinstance(sku, str):
            for fact_id in claim_fact_ids:
                fact_sku = fact_sku_by_id.get(fact_id)
                if fact_sku is None:
                    findings.append(f"claim_fact_ids: unknown PRODUCT_FACT {fact_id!r}")
                elif fact_sku != sku:
                    findings.append(
                        f"claim_fact_ids: {fact_id!r} belongs to {fact_sku!r}, not {sku!r}"
                    )

    if findings:
        raise ContractValidationError(contract_name, findings)


def validate_record(
    contract_name: str,
    record: Mapping[str, Any],
    *,
    known_skus: Set[str] | None = None,
    fact_sku_by_id: Mapping[str, str] | None = None,
) -> None:
    """Backward-compatible alias for fail-closed operational validation."""

    validate_contract(
        contract_name,
        record,
        known_skus=known_skus,
        fact_sku_by_id=fact_sku_by_id,
    )
