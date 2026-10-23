"""Explicit two-file, stdout-only operator boundary; no repeat grant is activated here."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from topspeed_ai_os.calculation.coupang_period_aggregate_inventory_assessment import (
    _assess_coupang_period_aggregate_inventory,
    _produce_coupang_inventory_availability_observation,
    _produce_coupang_vendor_item_period_aggregate,
)
from topspeed_ai_os.core.ids import generate_run_id
from topspeed_ai_os.tools.read.coupang_wing_export import (
    CoupangWingExportReadTool,
    _completed_period_close,
)

_INPUT_ROOT = Path(r"C:\TOPSPEED_AI_OS_INPUT\COUPANG")
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class _SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default message can echo an untrusted path or raw argument.
        raise ValueError("Invalid invocation")


def _input_paths(sales_file: str, inventory_file: str) -> tuple[Path, Path]:
    root = _INPUT_ROOT.resolve(strict=True)
    repository = _REPOSITORY_ROOT.resolve(strict=True)
    paths = []
    for value in (sales_file, inventory_file):
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("Explicit absolute inputs are required")
        path = path.resolve(strict=True)
        if (
            not path.is_relative_to(root)
            or path.is_relative_to(repository)
            or path.suffix.lower() != ".xlsx"
            or not path.is_file()
        ):
            raise ValueError("Input boundary is not authorized")
        paths.append(path)
    if paths[0].samefile(paths[1]):
        raise ValueError("Distinct input files are required")
    return paths[0], paths[1]


def _run(arguments: argparse.Namespace) -> dict[str, object]:
    _completed_period_close(arguments.period_start, arguments.period_end, arguments.period_timezone)
    sales_path, inventory_path = _input_paths(arguments.sales_file, arguments.inventory_file)
    # No discovery, classification or rewriting: load each explicit file once.
    sales_bytes = sales_path.read_bytes()
    inventory_bytes = inventory_path.read_bytes()
    run_id = generate_run_id()
    tool = CoupangWingExportReadTool(clock=lambda: datetime.now(UTC))
    sales = tool.read(
        raw_bytes=sales_bytes,
        export_kind="SALES_PERIOD_AGGREGATE",
        period_start=arguments.period_start,
        period_end=arguments.period_end,
        period_timezone=arguments.period_timezone,
        run_id=run_id,
    )
    inventory = tool.read(
        raw_bytes=inventory_bytes, export_kind="INVENTORY_HEALTH_OBSERVATION", run_id=run_id
    )
    aggregate = _produce_coupang_vendor_item_period_aggregate(sales)
    observation = _produce_coupang_inventory_availability_observation(inventory)
    result = _assess_coupang_period_aggregate_inventory(aggregate, observation, run_id=run_id)
    return {
        "status": "SUCCESS",
        "run_id": result.run_id,
        "channel": result.channel,
        "internal_sku": result.internal_sku,
        "period_start": result.period_start_date,
        "period_end": result.period_end_date,
        "period_days": result.period_days,
        "sales_workbook_created_at": aggregate.exported_at,
        "inventory_observed_at": result.inventory_observed_at,
        "net_sold_units": result.net_sold_units,
        "avg_daily_units": result.avg_daily_units,
        "indicative_safety_stock_days": result.indicative_safety_stock_days,
        "indicative_safety_stock_qty": result.indicative_safety_stock_qty,
        "available_qty": result.available_qty,
        "inbound_qty": result.inbound_qty,
        "customer_return_units": result.customer_return_units,
        "assessment_status": result.status,
        "sales_source_checksum": aggregate.source_checksum,
        "inventory_source_checksum": observation.source_checksum,
        "aggregate_input_hash": aggregate.input_hash,
        "inventory_input_hash": observation.input_hash,
        "assessment_input_hash": result.input_hash,
    }


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _SafeParser(description=__doc__, allow_abbrev=False)
        for name in (
            "sales-file",
            "inventory-file",
            "period-start",
            "period-end",
            "period-timezone",
        ):
            parser.add_argument("--" + name, required=True)
        output = _run(parser.parse_args(argv))
        encoded = json.dumps(output, ensure_ascii=False, sort_keys=True)
    except Exception:
        # Untrusted exceptions can contain raw rows, file paths or a traceback.
        print("Coupang assessment failed; no assessment produced.", file=sys.stderr)
        return 1
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
