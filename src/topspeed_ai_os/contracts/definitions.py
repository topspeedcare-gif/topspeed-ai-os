"""Authoritative JSON Schema definitions derived from Data Contract v1."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from topspeed_ai_os.core.enums import (
    ApprovalStatus,
    AssetStatus,
    AssetType,
    AuditStatus,
    Grade,
    ProductStatus,
    ResultStatus,
    RiskLevel,
    Skill,
    Stage,
    VerificationStatus,
)

from .logical_types import DECIMAL_PATTERN

CONTRACT_NAMES = (
    "PRODUCT_MASTER",
    "PRODUCT_FACT",
    "CHANNEL_DAILY",
    "AD_DAILY",
    "INVENTORY",
    "CONTENT_ASSET",
    "APPROVAL_QUEUE",
    "AI_RUN_LOG",
)

_ULID = r"[0-7][0-9A-HJKMNP-TV-Z]{25}"
_DATETIME_PATTERN = r"(?:Z|[+-][0-9]{2}:[0-9]{2})$"


def _string(*, pattern: str | None = None, uri: bool = False) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string", "minLength": 1}
    if pattern:
        schema["pattern"] = pattern
    if uri:
        schema["format"] = "uri"
    return schema


def _integer() -> dict[str, Any]:
    return {"type": "integer"}


def _decimal(*, minimum: str | None = None, maximum: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "string",
        "pattern": DECIMAL_PATTERN,
        "format": "canonical-decimal",
        "x-logical-type": "DECIMAL",
    }
    if minimum is not None or maximum is not None:
        schema["x-decimal-range"] = {
            key: value
            for key, value in (("minimum", minimum), ("maximum", maximum))
            if value is not None
        }
    return schema


def _ratio() -> dict[str, Any]:
    return _decimal(minimum="0", maximum="1")


def _date() -> dict[str, Any]:
    return {"type": "string", "format": "date"}


def _datetime() -> dict[str, Any]:
    return {
        "type": "string",
        "format": "date-time",
        "pattern": _DATETIME_PATTERN,
        "x-timezone-required": True,
    }


def _enum(enum_type: type[Any]) -> dict[str, Any]:
    return {"type": "string", "enum": [item.value for item in enum_type]}


def _json() -> dict[str, Any]:
    return {"type": ["object", "array"]}


def _object() -> dict[str, Any]:
    return {"type": "object"}


def _array(item_schema: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item_schema, "uniqueItems": True}


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [deepcopy(schema), {"type": "null"}]}


SKU = _string(pattern=r"^[A-Z0-9]+(?:-[A-Z0-9]+)+$")
TASK_ID = _string(pattern=rf"^task_{_ULID}$")
RUN_ID = _string(pattern=rf"^run_{_ULID}$")
APPROVAL_ID = _string(pattern=rf"^apr_{_ULID}$")
IDEMPOTENCY_KEY = _string(pattern=rf"^idem_{_ULID}$")
FACT_ID = _string(pattern=rf"^fact_{_ULID}$")
ASSET_ID = _string(pattern=rf"^asset_{_ULID}$")
LOG_ID = _string(pattern=rf"^log_{_ULID}$")
SHA256 = _string(pattern=r"^sha256:[0-9a-f]{64}$")


CONTRACT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "PRODUCT_MASTER": {
        "properties": {
            "sku": SKU,
            "product_name": _string(),
            "category": _string(),
            "channel_ids": _nullable(_object()),
            "stage": _enum(Stage),
            "grade": _nullable(_enum(Grade)),
            "status": _enum(ProductStatus),
            "supplier": _nullable(_string()),
            "currency": _string(pattern=r"^[A-Z]{3}$"),
            "purchase_cost": _nullable(_decimal()),
            "sale_price": _nullable(_decimal()),
            "fee_rate": _nullable(_ratio()),
            "fulfillment_cost": _nullable(_decimal()),
            "expected_return_cost": _nullable(_decimal()),
            "other_variable_cost": _nullable(_decimal()),
            "contribution_margin": _nullable(_decimal()),
            "contribution_margin_rate": _nullable(_ratio()),
            "source": _string(),
            "data_as_of": _datetime(),
            "created_at": _datetime(),
            "updated_at": _datetime(),
        },
        "required": {
            "sku",
            "product_name",
            "category",
            "stage",
            "status",
            "currency",
            "source",
            "data_as_of",
            "created_at",
            "updated_at",
        },
    },
    "PRODUCT_FACT": {
        "properties": {
            "fact_id": FACT_ID,
            "sku": SKU,
            "fact_type": _string(),
            "fact_value": _json(),
            "unit": _nullable(_string()),
            "verification_status": _enum(VerificationStatus),
            "source": _string(),
            "source_uri": _nullable(_string(uri=True)),
            "source_checksum": _nullable(SHA256),
            "verified_at": _nullable(_datetime()),
            "valid_from": _nullable(_date()),
            "valid_to": _nullable(_date()),
            "run_id": _nullable(RUN_ID),
            "task_id": _nullable(TASK_ID),
            "data_as_of": _datetime(),
            "created_at": _datetime(),
        },
        "required": {
            "fact_id",
            "sku",
            "fact_type",
            "fact_value",
            "verification_status",
            "source",
            "data_as_of",
            "created_at",
        },
    },
    "CHANNEL_DAILY": {
        "properties": {
            "channel": _string(),
            "stat_date": _date(),
            "sku": SKU,
            "channel_product_id": _nullable(_string()),
            "gross_sales": _decimal(),
            "net_sales": _decimal(),
            "orders": _integer(),
            "units_sold": _integer(),
            "refunds": _integer(),
            "refund_amount": _decimal(),
            "channel_fees": _nullable(_decimal()),
            "settlement_amount": _nullable(_decimal()),
            "page_views": _nullable(_integer()),
            "conversion_rate": _nullable(_ratio()),
            "run_id": RUN_ID,
            "source": _string(),
            "data_as_of": _datetime(),
            "created_at": _datetime(),
        },
        "required": {
            "channel",
            "stat_date",
            "sku",
            "gross_sales",
            "net_sales",
            "orders",
            "units_sold",
            "refunds",
            "refund_amount",
            "run_id",
            "source",
            "data_as_of",
            "created_at",
        },
    },
    "AD_DAILY": {
        "properties": {
            "channel": _string(),
            "stat_date": _date(),
            "sku": SKU,
            "campaign_id": _string(),
            "campaign_name": _nullable(_string()),
            "ad_group_id": _nullable(_string()),
            "impressions": _integer(),
            "clicks": _integer(),
            "ad_spend": _decimal(),
            "ad_orders": _integer(),
            "ad_units": _nullable(_integer()),
            "ad_revenue": _decimal(),
            "ctr": _nullable(_ratio()),
            "cvr": _nullable(_ratio()),
            "roas": _nullable(_decimal()),
            "source_file_hash": _nullable(SHA256),
            "run_id": RUN_ID,
            "source": _string(),
            "data_as_of": _datetime(),
            "created_at": _datetime(),
        },
        "required": {
            "channel",
            "stat_date",
            "sku",
            "campaign_id",
            "impressions",
            "clicks",
            "ad_spend",
            "ad_orders",
            "ad_revenue",
            "run_id",
            "source",
            "data_as_of",
            "created_at",
        },
    },
    "INVENTORY": {
        "properties": {
            "snapshot_at": _datetime(),
            "sku": SKU,
            "location": _string(),
            "on_hand_qty": _integer(),
            "available_qty": _integer(),
            "reserved_qty": _integer(),
            "inbound_qty": _integer(),
            "avg_daily_units": _nullable(_decimal()),
            "stock_days": _nullable(_decimal()),
            "lead_time_days": _nullable(_integer()),
            "safety_stock_qty": _nullable(_integer()),
            "reorder_point_qty": _nullable(_integer()),
            "recommended_order_qty": _nullable(_integer()),
            "run_id": RUN_ID,
            "source": _string(),
            "data_as_of": _datetime(),
            "created_at": _datetime(),
        },
        "required": {
            "snapshot_at",
            "sku",
            "location",
            "on_hand_qty",
            "available_qty",
            "reserved_qty",
            "inbound_qty",
            "run_id",
            "source",
            "data_as_of",
            "created_at",
        },
    },
    "CONTENT_ASSET": {
        "properties": {
            "asset_id": ASSET_ID,
            "sku": SKU,
            "asset_type": _enum(AssetType),
            "title": _string(),
            "storage_uri": _string(uri=True),
            "checksum_sha256": SHA256,
            "mime_type": _string(),
            "version": _integer(),
            "status": _enum(AssetStatus),
            "claim_fact_ids": _array(FACT_ID),
            "generated_by": _string(),
            "task_id": TASK_ID,
            "run_id": RUN_ID,
            "approved_by": _nullable(_string()),
            "source": _string(),
            "data_as_of": _datetime(),
            "created_at": _datetime(),
            "updated_at": _datetime(),
        },
        "required": {
            "asset_id",
            "sku",
            "asset_type",
            "title",
            "storage_uri",
            "checksum_sha256",
            "mime_type",
            "version",
            "status",
            "claim_fact_ids",
            "generated_by",
            "task_id",
            "run_id",
            "source",
            "data_as_of",
            "created_at",
            "updated_at",
        },
    },
    "APPROVAL_QUEUE": {
        "properties": {
            "approval_id": APPROVAL_ID,
            "task_id": TASK_ID,
            "run_id": RUN_ID,
            "sku": _nullable(SKU),
            "action_type": _string(),
            "target_type": _string(),
            "target_id": _string(),
            "proposed_payload": _json(),
            "payload_hash": SHA256,
            "before_value": _json(),
            "after_value": _json(),
            "risk_level": _enum(RiskLevel),
            "audit_status": _enum(AuditStatus),
            "audit_summary": _string(),
            "approval_status": _enum(ApprovalStatus),
            "requested_by": _string(),
            "approved_by": _nullable(_string()),
            "requested_at": _datetime(),
            "decided_at": _nullable(_datetime()),
            "expires_at": _datetime(),
            "execution_tool": _string(),
            "idempotency_key": IDEMPOTENCY_KEY,
            "source": _string(),
            "data_as_of": _datetime(),
            "error": _nullable(_string()),
            "created_at": _datetime(),
            "updated_at": _datetime(),
        },
        "required": {
            "approval_id",
            "task_id",
            "run_id",
            "action_type",
            "target_type",
            "target_id",
            "proposed_payload",
            "payload_hash",
            "before_value",
            "after_value",
            "risk_level",
            "audit_status",
            "audit_summary",
            "approval_status",
            "requested_by",
            "requested_at",
            "expires_at",
            "execution_tool",
            "idempotency_key",
            "source",
            "data_as_of",
            "created_at",
            "updated_at",
        },
    },
    "AI_RUN_LOG": {
        "properties": {
            "log_id": LOG_ID,
            "event_seq": _integer(),
            "event_type": _string(),
            "run_id": RUN_ID,
            "task_id": TASK_ID,
            "parent_run_id": _nullable(RUN_ID),
            "agent": _string(),
            "skill": _nullable(_enum(Skill)),
            "sku": _nullable(SKU),
            "source": _json(),
            "data_as_of": _nullable(_datetime()),
            "input_summary": _string(),
            "output_summary": _string(),
            "tool_name": _nullable(_string()),
            "approval_id": _nullable(APPROVAL_ID),
            "approval_status": _nullable(_enum(ApprovalStatus)),
            "audit_status": _nullable(_enum(AuditStatus)),
            "before_value": _nullable(_json()),
            "after_value": _nullable(_json()),
            "result": _enum(ResultStatus),
            "error_code": _nullable(_string()),
            "error": _nullable(_string()),
            "human_edit_ratio": _nullable(_ratio()),
            "idempotency_key": _nullable(IDEMPOTENCY_KEY),
            "started_at": _datetime(),
            "finished_at": _nullable(_datetime()),
            "created_at": _datetime(),
        },
        "required": {
            "log_id",
            "event_seq",
            "event_type",
            "run_id",
            "task_id",
            "agent",
            "source",
            "input_summary",
            "output_summary",
            "result",
            "started_at",
            "created_at",
        },
    },
}


def build_schema(contract_name: str) -> dict[str, Any]:
    """Build one standalone Draft 2020-12 JSON Schema."""

    try:
        definition = CONTRACT_DEFINITIONS[contract_name]
    except KeyError as exc:
        raise KeyError(f"unknown contract: {contract_name}") from exc

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://topspeed.local/contracts/v1/{contract_name.lower()}.schema.json",
        "title": contract_name,
        "type": "object",
        "additionalProperties": False,
        "properties": deepcopy(definition["properties"]),
        "required": sorted(definition["required"]),
    }
