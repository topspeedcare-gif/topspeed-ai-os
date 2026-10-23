"""Synthetic operator-boundary regressions; no real export is opened or persisted."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_calculation_coupang_period_aggregate_inventory_assessment import (
    INVENTORY,
    RUN,
    book,
)

_SCRIPT = Path(__file__).resolve().parents[1] / "tools/run_coupang_l_repeatable_completed_30d.py"
_SPEC = importlib.util.spec_from_file_location("repeatable_coupang_runner", _SCRIPT)
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)
_OUTPUT_KEYS = {
    "status",
    "run_id",
    "channel",
    "internal_sku",
    "period_start",
    "period_end",
    "period_days",
    "sales_workbook_created_at",
    "inventory_observed_at",
    "net_sold_units",
    "avg_daily_units",
    "indicative_safety_stock_days",
    "indicative_safety_stock_qty",
    "available_qty",
    "inbound_qty",
    "customer_return_units",
    "assessment_status",
    "sales_source_checksum",
    "inventory_source_checksum",
    "aggregate_input_hash",
    "inventory_input_hash",
    "assessment_input_hash",
}


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    root = tmp_path / "inputs"
    root.mkdir()
    sales = root / "synthetic-sales.xlsx"
    inventory = root / "synthetic-inventory.xlsx"
    sales.write_bytes(book())
    inventory.write_bytes(book(INVENTORY))
    monkeypatch.setattr(runner, "_INPUT_ROOT", root)
    monkeypatch.setattr(runner, "generate_run_id", lambda: RUN)
    monkeypatch.setattr(
        runner, "datetime", SimpleNamespace(now=lambda tz: datetime(2030, 1, 1, tzinfo=UTC))
    )
    return root, sales, inventory


def arguments(sales, inventory, start="2026-09-20", end="2026-10-19"):
    return [
        "--sales-file",
        str(sales),
        "--inventory-file",
        str(inventory),
        "--period-start",
        start,
        "--period-end",
        end,
        "--period-timezone",
        "Asia/Seoul",
    ]


def assert_redacted_failure(capsys, *private_strings):
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "Coupang assessment failed; no assessment produced.\n"
    assert "Traceback" not in output.err
    assert "SUCCESS" not in output.err
    for value in private_strings:
        assert str(value) not in output.err


def test_success_has_exact_json_keys_and_each_explicit_file_is_read_once(
    inputs, monkeypatch, capsys
):
    root, sales, inventory = inputs
    original = Path.read_bytes
    original_open = Path.open
    reads, opens = [], []
    raw_sales, raw_inventory = original(sales), original(inventory)
    snapshot = {path.name: original(path) for path in root.iterdir()}

    def read_bytes(path):
        reads.append(path)
        return original(path)

    def open_file(path, mode="r", *args, **kwargs):
        assert path in (sales, inventory)
        assert mode == "rb"
        opens.append(path)
        return original_open(path, mode, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("SYNTHETIC-FORBIDDEN-DISCOVERY-NETWORK-ENVIRONMENT-WRITE")

    environment_getitem = type(os.environ).__getitem__

    def credential_guard(environment, key):
        # argparse may inspect terminal/locale settings; that is not credential access.
        if any(
            part in key.upper()
            for part in ("SECRET", "TOKEN", "PASSWORD", "CREDENTIAL", "API_KEY", "ACCESS_KEY")
        ):
            forbidden()
        return environment_getitem(environment, key)

    with monkeypatch.context() as gates:
        gates.setattr(Path, "read_bytes", read_bytes)
        gates.setattr(Path, "open", open_file)
        for name in ("glob", "rglob", "iterdir", "write_bytes", "write_text", "mkdir", "touch"):
            gates.setattr(Path, name, forbidden)
        gates.setattr(os, "scandir", forbidden)
        gates.setattr(os, "listdir", forbidden)
        gates.setattr(os, "getenv", forbidden)
        gates.setattr(type(os.environ), "__getitem__", credential_guard)
        gates.setattr(socket, "socket", forbidden)
        gates.setattr(subprocess, "run", forbidden)
        assert runner.main(arguments(sales, inventory)) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert len(output.out.splitlines()) == 1
    result = json.loads(output.out)
    assert set(result) == _OUTPUT_KEYS
    assert result["status"] == "SUCCESS"
    assert result["run_id"] == RUN
    assert result["channel"] == "COUPANG"
    assert result["internal_sku"] == "TS-WAIST-BRACE-L"
    assert result["period_start"] == "2026-09-20"
    assert result["period_end"] == "2026-10-19"
    assert result["period_days"] == 30
    assert (
        result["sales_workbook_created_at"]
        == result["inventory_observed_at"]
        == ("2026-10-20T00:00:00+09:00")
    )
    assert result["net_sold_units"] == 17
    assert result["avg_daily_units"] == "0.5667"
    assert result["indicative_safety_stock_days"] == 7
    assert result["indicative_safety_stock_qty"] == 4
    assert result["available_qty"] == 12
    assert result["inbound_qty"] == 4
    assert result["customer_return_units"] == 3
    assert result["assessment_status"] == "ABOVE_OR_EQUAL_INDICATIVE_SAFETY_STOCK"
    assert result["sales_source_checksum"] == "sha256:" + hashlib.sha256(raw_sales).hexdigest()
    assert (
        result["inventory_source_checksum"] == "sha256:" + hashlib.sha256(raw_inventory).hexdigest()
    )
    for name in ("aggregate_input_hash", "inventory_input_hash", "assessment_input_hash"):
        assert result[name].startswith("sha256:") and len(result[name]) == 71
    assert reads == opens == [sales, inventory]
    assert str(root) not in output.out
    assert "15587136792" not in output.out
    assert "92849878174" not in output.out
    assert "61654574" not in output.out
    assert snapshot == {path.name: original(path) for path in root.iterdir()}


def test_other_completed_period_requires_no_source_change(inputs, capsys):
    _, sales, inventory = inputs
    close = "2027-01-14T00:00:00+09:00"
    sales.write_bytes(book(created=close))
    inventory.write_bytes(book(INVENTORY, created=close))
    assert runner.main(arguments(sales, inventory, "2026-12-15", "2027-01-13")) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["period_start"] == "2026-12-15"
    assert result["period_end"] == "2027-01-13"
    assert result["inventory_observed_at"] == close
    assert result["net_sold_units"] == 17


@pytest.mark.parametrize(
    "fault",
    ["outside", "repository", "same", "hardlink", "not_xlsx", "directory", "missing", "relative"],
)
def test_path_boundaries_reject_before_any_source_read(
    inputs, tmp_path, monkeypatch, capsys, fault
):
    root, sales, inventory = inputs
    if fault == "outside":
        sales = tmp_path / "outside.xlsx"
        sales.write_bytes(b"SYNTHETIC-NOT-A-WORKBOOK")
    elif fault == "repository":
        # Model an approved-root junction that resolves to the repository. The
        # independently canonical repository exclusion must still reject it.
        monkeypatch.setattr(runner, "_REPOSITORY_ROOT", root)
    elif fault == "same":
        inventory = sales
    elif fault == "hardlink":
        inventory = root / "same-inode.xlsx"
        inventory.hardlink_to(sales)
    elif fault == "not_xlsx":
        sales = root / "synthetic.txt"
        sales.write_bytes(b"SYNTHETIC-NOT-XLSX")
    elif fault == "directory":
        sales = root / "directory.xlsx"
        sales.mkdir()
    elif fault == "missing":
        sales = root / "missing.xlsx"
    else:
        sales = Path("relative.xlsx")

    def forbidden(*args, **kwargs):
        raise AssertionError("SYNTHETIC-INPUT-MUST-NOT-BE-READ")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    assert runner.main(arguments(sales, inventory)) != 0
    assert_redacted_failure(capsys, sales, inventory)


def test_resolved_alias_cannot_escape_approved_root(inputs, tmp_path, monkeypatch, capsys):
    root, _, inventory = inputs
    alias = root / "synthetic-alias.xlsx"
    target = tmp_path / "outside.xlsx"
    target.write_bytes(b"SYNTHETIC-OUTSIDE-INPUT")
    resolve = Path.resolve

    def resolved(path, *args, **kwargs):
        return target if path == alias else resolve(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("SYNTHETIC-ESCAPED-PATH-MUST-NOT-BE-READ")

    monkeypatch.setattr(Path, "resolve", resolved)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    assert runner.main(arguments(alias, inventory)) != 0
    assert_redacted_failure(capsys, alias, target)


@pytest.mark.parametrize(
    "fault", ["missing_argument", "unknown_argument", "bad_period", "bad_zone"]
)
def test_invalid_cli_does_not_read_inputs_or_echo_arguments(inputs, monkeypatch, capsys, fault):
    _, sales, inventory = inputs
    args = arguments(sales, inventory)
    if fault == "missing_argument":
        args = args[:-1]
    elif fault == "unknown_argument":
        args += ["--private", "SYNTHETIC-PRIVATE-VALUE"]
    elif fault == "bad_period":
        args[args.index("--period-start") + 1] = "2026-09-21"
    else:
        args[-1] = "+09:00"

    def forbidden(*args, **kwargs):
        raise AssertionError("SYNTHETIC-INPUT-MUST-NOT-BE-READ")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    assert runner.main(args) != 0
    assert_redacted_failure(capsys, sales, inventory, "SYNTHETIC-PRIVATE-VALUE")


@pytest.mark.parametrize(
    "fault", ["raw", "wrong_sku", "preclose_inventory", "source", "producer", "assessment", "io"]
)
def test_failure_never_emits_partial_result_or_raw_exception(inputs, monkeypatch, capsys, fault):
    _, sales, inventory = inputs
    if fault == "raw":
        sales.write_bytes(b"SYNTHETIC-PRIVATE-RAW-ROW")
    elif fault == "wrong_sku":
        sales.write_bytes(
            book(rows=[("99999999999", "88888888888", "SYNTHETIC-MODE", "9", "0", "9")])
        )
    elif fault == "preclose_inventory":
        inventory.write_bytes(book(INVENTORY, created="2026-10-31T23:59:59+09:00"))
        sales.write_bytes(book(created="2026-11-01T00:00:00+09:00"))
    else:

        def broken(*args, **kwargs):
            raise RuntimeError(f"SYNTHETIC-PRIVATE-RAW-ROW {sales}")

        if fault == "source":
            monkeypatch.setattr(runner.CoupangWingExportReadTool, "read", broken)
        elif fault == "producer":
            monkeypatch.setattr(
                runner, "_produce_coupang_inventory_availability_observation", broken
            )
        elif fault == "assessment":
            monkeypatch.setattr(runner, "_assess_coupang_period_aggregate_inventory", broken)
        else:
            monkeypatch.setattr(Path, "read_bytes", broken)
    args = arguments(sales, inventory)
    if fault == "preclose_inventory":
        args = arguments(sales, inventory, "2026-10-02", "2026-10-31")
    assert runner.main(args) != 0
    assert_redacted_failure(capsys, sales, inventory, "SYNTHETIC-PRIVATE-RAW-ROW")


def test_real_command_process_has_safe_failure_exit_and_empty_stdout():
    result = subprocess.run(
        [sys.executable, "-B", str(_SCRIPT), "--unknown=SYNTHETIC-PRIVATE-CLI"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == "Coupang assessment failed; no assessment produced.\n"
