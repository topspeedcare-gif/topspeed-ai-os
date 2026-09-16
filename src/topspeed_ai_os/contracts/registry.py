"""JSON Schema loading plus engine-independent cross-record checks."""

from __future__ import annotations

import json
from collections.abc import Mapping, Set
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from topspeed_ai_os.core.canonical import CanonicalizationError, verify_payload_hash

from .definitions import CONTRACT_NAMES


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


def validate_record(
    contract_name: str,
    record: Mapping[str, Any],
    *,
    known_skus: Set[str] | None = None,
    fact_sku_by_id: Mapping[str, str] | None = None,
) -> None:
    """Validate one record without requiring a database engine.

    ``known_skus`` models PRODUCT_MASTER referential integrity. For CONTENT_ASSET,
    ``fact_sku_by_id`` additionally prevents claims from referencing another SKU.
    """

    schema = load_schema(contract_name)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(dict(record)), key=lambda error: list(error.path))
    findings = [f"{_format_path(error.path)}: {error.message}" for error in errors]

    sku = record.get("sku")
    if (
        contract_name != "PRODUCT_MASTER"
        and sku is not None
        and known_skus is not None
        and sku not in known_skus
    ):
        findings.append(f"sku: {sku!r} is not registered in PRODUCT_MASTER")

    if contract_name == "CONTENT_ASSET" and fact_sku_by_id is not None and isinstance(sku, str):
        for fact_id in record.get("claim_fact_ids", []):
            fact_sku = fact_sku_by_id.get(fact_id)
            if fact_sku is None:
                findings.append(f"claim_fact_ids: unknown PRODUCT_FACT {fact_id!r}")
            elif fact_sku != sku:
                findings.append(f"claim_fact_ids: {fact_id!r} belongs to {fact_sku!r}, not {sku!r}")

    if (
        contract_name == "APPROVAL_QUEUE"
        and record.get("audit_status") == "FAIL"
        and record.get("approval_status") == "PENDING"
    ):
        findings.append("approval_status: FAIL audit cannot create PENDING approval")

    if contract_name == "APPROVAL_QUEUE":
        try:
            hash_matches = verify_payload_hash(
                record.get("proposed_payload"), record.get("payload_hash")
            )
        except CanonicalizationError as exc:
            findings.append(f"proposed_payload: cannot be canonicalized: {exc}")
        else:
            if not hash_matches:
                findings.append("payload_hash: does not match canonical proposed_payload")

    if findings:
        raise ContractValidationError(contract_name, findings)
