from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest

from topspeed_ai_os.core.canonical import payload_sha256
from topspeed_ai_os.core.ids import (
    generate_approval_id,
    generate_idempotency_key,
    generate_run_id,
    generate_task_id,
)

SKU = "TS-KITCHEN-001"
OTHER_SKU = "TS-BAG-002"
ULID = "01J" + ("0" * 23)
FACT_ID = f"fact_{ULID}"
ASSET_ID = f"asset_{ULID}"
LOG_ID = f"log_{ULID}"
NOW = "2026-09-16T09:10:00+09:00"
AS_OF = "2026-09-16T09:00:00+09:00"
CHECKSUM = "sha256:" + ("a" * 64)


@pytest.fixture
def records() -> Callable[[], dict[str, dict[str, Any]]]:
    def build() -> dict[str, dict[str, Any]]:
        task_id = generate_task_id()
        run_id = generate_run_id()
        approval_id = generate_approval_id()
        idempotency_key = generate_idempotency_key()
        proposed_payload = {"daily_budget": 300000}

        values: dict[str, dict[str, Any]] = {
            "PRODUCT_MASTER": {
                "sku": SKU,
                "product_name": "스테인리스 배수구 거름망",
                "category": "주방용품",
                "channel_ids": {"coupang_vendor_item_id": "12345"},
                "stage": "TEST",
                "grade": "B",
                "status": "ACTIVE",
                "supplier": "SUP-001",
                "currency": "KRW",
                "purchase_cost": "5200",
                "sale_price": "12900",
                "fee_rate": "0.108",
                "fulfillment_cost": "2500",
                "expected_return_cost": "350",
                "other_variable_cost": "100",
                "contribution_margin": "3356.8",
                "contribution_margin_rate": "0.2602",
                "source": "manual_verified",
                "data_as_of": AS_OF,
                "created_at": NOW,
                "updated_at": NOW,
            },
            "PRODUCT_FACT": {
                "fact_id": FACT_ID,
                "sku": SKU,
                "fact_type": "material",
                "fact_value": {"value": "STS304"},
                "unit": "mm",
                "verification_status": "VERIFIED",
                "source": "supplier_certificate",
                "source_uri": "drive://file/abc",
                "source_checksum": CHECKSUM,
                "verified_at": NOW,
                "valid_from": "2026-01-01",
                "valid_to": "2027-01-01",
                "run_id": run_id,
                "task_id": task_id,
                "data_as_of": AS_OF,
                "created_at": NOW,
            },
            "CHANNEL_DAILY": {
                "channel": "coupang",
                "stat_date": "2026-09-15",
                "sku": SKU,
                "channel_product_id": "987654",
                "gross_sales": "1290000",
                "net_sales": "1225500",
                "orders": 102,
                "units_sold": 108,
                "refunds": 5,
                "refund_amount": "64500",
                "channel_fees": "132354",
                "settlement_amount": "1093146",
                "page_views": 3410,
                "conversion_rate": "0.0299",
                "run_id": run_id,
                "source": "coupang_api/orders",
                "data_as_of": AS_OF,
                "created_at": NOW,
            },
            "AD_DAILY": {
                "channel": "coupang_ads",
                "stat_date": "2026-09-15",
                "sku": SKU,
                "campaign_id": "cmp_123",
                "campaign_name": "키친_테스트",
                "ad_group_id": "grp_10",
                "impressions": 82500,
                "clicks": 1030,
                "ad_spend": "206000",
                "ad_orders": 52,
                "ad_units": 55,
                "ad_revenue": "709500",
                "ctr": "0.0125",
                "cvr": "0.0505",
                "roas": "3.4442",
                "source_file_hash": CHECKSUM,
                "run_id": run_id,
                "source": "coupang_ad_xlsx",
                "data_as_of": AS_OF,
                "created_at": NOW,
            },
            "INVENTORY": {
                "snapshot_at": AS_OF,
                "sku": SKU,
                "location": "coupang_fulfillment",
                "on_hand_qty": 320,
                "available_qty": 285,
                "reserved_qty": 20,
                "inbound_qty": 100,
                "avg_daily_units": "24.5",
                "stock_days": "11.63",
                "lead_time_days": 14,
                "safety_stock_qty": 98,
                "reorder_point_qty": 441,
                "recommended_order_qty": 356,
                "run_id": run_id,
                "source": "coupang_api/inventory",
                "data_as_of": AS_OF,
                "created_at": NOW,
            },
            "CONTENT_ASSET": {
                "asset_id": ASSET_ID,
                "sku": SKU,
                "asset_type": "DETAIL_PAGE",
                "title": "상세페이지 초안 v1",
                "storage_uri": "drive://file/xyz",
                "checksum_sha256": CHECKSUM,
                "mime_type": "text/markdown",
                "version": 1,
                "status": "DRAFT",
                "claim_fact_ids": [FACT_ID],
                "generated_by": "content_skill",
                "task_id": task_id,
                "run_id": run_id,
                "approved_by": None,
                "source": "product_fact",
                "data_as_of": AS_OF,
                "created_at": NOW,
                "updated_at": NOW,
            },
            "APPROVAL_QUEUE": {
                "approval_id": approval_id,
                "task_id": task_id,
                "run_id": run_id,
                "sku": SKU,
                "action_type": "AD_BUDGET_UPDATE",
                "target_type": "campaign",
                "target_id": "cmp_123",
                "proposed_payload": proposed_payload,
                "payload_hash": payload_sha256(proposed_payload),
                "before_value": {"daily_budget": 200000},
                "after_value": {"daily_budget": 300000},
                "risk_level": "HIGH",
                "audit_status": "WARN",
                "audit_summary": "최근 1일 데이터 지연",
                "approval_status": "PENDING",
                "requested_by": "owner",
                "approved_by": None,
                "requested_at": NOW,
                "decided_at": None,
                "expires_at": "2026-09-16T12:10:00+09:00",
                "execution_tool": "coupang_ads_write_v1",
                "idempotency_key": idempotency_key,
                "source": "ad_daily",
                "data_as_of": AS_OF,
                "error": None,
                "created_at": NOW,
                "updated_at": NOW,
            },
            "AI_RUN_LOG": {
                "log_id": LOG_ID,
                "event_seq": 7,
                "event_type": "AUDIT_COMPLETED",
                "run_id": run_id,
                "task_id": task_id,
                "parent_run_id": None,
                "agent": "hq_orchestrator",
                "skill": "ads_ops",
                "sku": SKU,
                "source": ["ad_daily:2026-09-15"],
                "data_as_of": AS_OF,
                "input_summary": "예산 20만→30만원 제안",
                "output_summary": "WARN, 승인 요청 생성",
                "tool_name": "ad_metrics_calculator_v1",
                "approval_id": approval_id,
                "approval_status": "PENDING",
                "audit_status": "WARN",
                "before_value": {"daily_budget": 200000},
                "after_value": {"daily_budget": 300000},
                "result": "BLOCKED",
                "error_code": None,
                "error": None,
                "human_edit_ratio": "0.12",
                "idempotency_key": idempotency_key,
                "started_at": NOW,
                "finished_at": "2026-09-16T10:10:02+09:00",
                "created_at": "2026-09-16T10:10:02+09:00",
            },
        }
        return deepcopy(values)

    return build
