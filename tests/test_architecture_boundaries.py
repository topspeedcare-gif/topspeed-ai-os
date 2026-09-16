from __future__ import annotations

import ast
from pathlib import Path


def test_phase_two_has_no_legacy_or_external_runtime_imports():
    source_root = Path(__file__).parents[1] / "src"
    forbidden_roots = {
        "topspeed_lifeos",
        "slack_sdk",
        "sqlalchemy",
        "psycopg",
        "sqlite3",
        "openai",
        "langchain",
        "boto3",
        "googleapiclient",
    }
    violations: list[str] = []

    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = {node.module.split(".")[0]}
            else:
                continue
            for root in roots & forbidden_roots:
                violations.append(f"{path.relative_to(source_root)} imports {root}")

    assert violations == []


def test_phase_two_contains_no_execution_adapter_directory():
    source_root = Path(__file__).parents[1] / "src" / "topspeed_ai_os"
    forbidden = ["gateways", "agents", "execution", "connectors", "database"]
    assert [name for name in forbidden if (source_root / name).exists()] == []
