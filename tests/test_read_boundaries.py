from __future__ import annotations

import ast
import inspect
from pathlib import Path

from topspeed_ai_os.tools.read import CoupangReadTool, DriveOperation, DriveReadTool


def test_phase_three_tools_have_no_forbidden_runtime_dependencies():
    tools_root = Path(__file__).parents[1] / "src" / "topspeed_ai_os" / "tools"
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
    for path in tools_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = {node.module.split(".")[0]}
            else:
                continue
            violations.extend(sorted(roots & forbidden_roots))
    assert violations == []


def test_business_http_transport_calls_are_get_only():
    source_path = (
        Path(__file__).parents[1] / "src" / "topspeed_ai_os" / "tools" / "read" / "coupang.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    methods: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "request":
            continue
        method = next(keyword.value for keyword in node.keywords if keyword.arg == "method")
        assert isinstance(method, ast.Constant) and isinstance(method.value, str)
        methods.append(method.value)
    assert methods == ["GET"]


def test_public_source_tool_actions_are_read_only():
    assert {operation.value for operation in DriveOperation} == {
        "drive.get_metadata",
        "drive.download_file",
        "drive.export_file",
    }
    for tool_class in (CoupangReadTool, DriveReadTool):
        public_actions = {
            name
            for name, member in tool_class.__dict__.items()
            if inspect.isfunction(member) and not name.startswith("_")
        }
        assert public_actions == {"read"}
