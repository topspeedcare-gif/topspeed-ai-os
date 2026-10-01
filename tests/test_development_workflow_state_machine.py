from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path

import pytest

from topspeed_ai_os.development_workflow import (
    compute_idempotency_key,
    evaluate_transition,
)

STAGES = (
    "AUDIT1_DRAFT",
    "AUDIT2_WORK_ORDER_REVIEW",
    "BUILDER_IMPLEMENTATION",
    "AUDIT1_IMPLEMENTATION_AUDIT",
    "AUDIT2_IMPLEMENTATION_REAUDIT",
    "PUBLICATION_READY",
)
NEXT_STAGE = {stage: STAGES[index + 1] for index, stage in enumerate(STAGES[:-1])}
NEXT_STAGE["PUBLICATION_READY"] = None
SHA1 = "a" * 40
SHA256 = "b" * 64
COMPLETED_AT = "2026-10-01T09:10:00+09:00"


def state_for(
    stage: str,
    status: str,
    *,
    verdict: str | None = None,
    error_code: str | None = None,
    transition_id: str | None = None,
    actor: str = "any-non-empty-actor",
) -> dict[str, object]:
    terminal = status in {"COMPLETED", "STOPPED", "RECONCILIATION_REQUIRED"}
    expected_next_stage = NEXT_STAGE[stage] if status == "COMPLETED" and verdict == "PASS" else None
    state: dict[str, object] = {
        "schema_version": "development_workflow_state.v1",
        "workflow_run_id": "workflow-001",
        "work_item_id": "step-1",
        "phase": "DEVELOPMENT_WORKFLOW",
        "slice": None,
        "stage": stage,
        "actor": actor,
        "transition_id": transition_id or f"transition-{stage}",
        "idempotency_key": "0" * 64,
        "transition_status": status,
        "baseline_sha": SHA1,
        "pre_stage_sha": SHA1,
        "post_stage_sha": SHA1 if terminal else None,
        "result_sha": SHA1 if verdict is not None else None,
        "scope_hash": "c" * 64,
        "parent_scope_hash": None,
        "attempt": 1,
        "verdict": verdict,
        "findings": [],
        "work_order_ref": "docs/work-orders/step-1.md",
        "approved_work_order_sha256": SHA256,
        "evidence_refs": [],
        "actual_changed_paths": [],
        "actual_operation_classes": [],
        "expected_next_stage": expected_next_stage,
        "human_approval_required": stage == "PUBLICATION_READY",
        "error_code": error_code,
        "created_at": "2026-10-01T09:00:00+09:00",
        "completed_at": COMPLETED_AT if terminal else None,
    }
    state["idempotency_key"] = compute_idempotency_key(state)
    return state


def lifecycle_pair(
    status: str,
    *,
    verdict: str | None = None,
    error_code: str | None = None,
    stage: str = "BUILDER_IMPLEMENTATION",
):
    previous = state_for(stage, "RUNNING")
    proposed = deepcopy(previous)
    proposed.update(
        {
            "transition_status": status,
            "verdict": verdict,
            "error_code": error_code,
            "completed_at": COMPLETED_AT,
            "post_stage_sha": SHA1,
            "result_sha": SHA1 if verdict is not None else None,
            "expected_next_stage": NEXT_STAGE[stage]
            if status == "COMPLETED" and verdict == "PASS"
            else None,
        }
    )
    return previous, proposed


@pytest.mark.parametrize("current,next_stage", tuple(NEXT_STAGE.items())[:-1])
def test_every_published_normal_stage_edge_is_allowed(current, next_stage):
    previous = state_for(current, "COMPLETED", verdict="PASS")
    proposed = state_for(next_stage, "PENDING")
    decision = evaluate_transition(previous, proposed)
    assert decision.allowed
    assert decision.executable
    assert decision.expected_next_stage == next_stage


def test_stage_skip_is_rejected():
    previous = state_for("AUDIT1_DRAFT", "COMPLETED", verdict="PASS")
    proposed = state_for("BUILDER_IMPLEMENTATION", "PENDING")
    decision = evaluate_transition(previous, proposed)
    assert not decision.allowed
    assert any(error.rule == "INVALID_STAGE_EDGE" for error in decision.errors)


def test_stage_reverse_is_rejected():
    previous = state_for("BUILDER_IMPLEMENTATION", "COMPLETED", verdict="PASS")
    proposed = state_for("AUDIT2_WORK_ORDER_REVIEW", "PENDING")
    assert not evaluate_transition(previous, proposed).allowed


def test_publication_ready_has_null_next_stage():
    previous, proposed = lifecycle_pair("COMPLETED", verdict="PASS", stage="PUBLICATION_READY")
    decision = evaluate_transition(previous, proposed)
    assert decision.allowed
    assert decision.expected_next_stage is None
    assert proposed["expected_next_stage"] is None


@pytest.mark.parametrize("stage", STAGES)
def test_valid_completed_pass_has_exact_next_stage(stage):
    previous, proposed = lifecycle_pair("COMPLETED", verdict="PASS", stage=stage)
    decision = evaluate_transition(previous, proposed)
    assert decision.allowed
    assert decision.expected_next_stage == NEXT_STAGE[stage]
    assert proposed["expected_next_stage"] == NEXT_STAGE[stage]


@pytest.mark.parametrize("verdict", ["FAIL", "BLOCKED"])
def test_actor_stop_verdict_is_preserved(verdict):
    previous, proposed = lifecycle_pair("STOPPED", verdict=verdict)
    decision = evaluate_transition(previous, proposed)
    assert decision.allowed
    assert proposed["verdict"] == verdict
    assert proposed["transition_status"] == "STOPPED"
    assert decision.expected_next_stage is None


def test_unexpected_verdict_is_rejected_not_reclassified():
    previous = state_for("BUILDER_IMPLEMENTATION", "RUNNING")
    proposed = deepcopy(previous)
    proposed.update(
        {
            "transition_status": "STOPPED",
            "verdict": "WARN",
            "completed_at": COMPLETED_AT,
        }
    )
    decision = evaluate_transition(previous, proposed)
    assert not decision.allowed
    assert proposed["verdict"] == "WARN"
    assert any(error.rule == "anyOf" for error in decision.errors)


def test_stopped_has_no_automatic_next_transition():
    previous = state_for("AUDIT1_DRAFT", "STOPPED", verdict="FAIL")
    proposed = state_for("AUDIT2_WORK_ORDER_REVIEW", "PENDING")
    decision = evaluate_transition(previous, proposed)
    assert not decision.allowed
    assert decision.automatic_next_transition is None


@pytest.mark.parametrize("status", ["PENDING", "RUNNING"])
@pytest.mark.parametrize(
    ("field", "invalid"),
    [("verdict", "PASS"), ("completed_at", COMPLETED_AT)],
)
def test_nonterminal_status_matrix_requires_nulls(status, field, invalid):
    previous = state_for("BUILDER_IMPLEMENTATION", "PENDING")
    proposed = state_for("BUILDER_IMPLEMENTATION", status)
    proposed[field] = invalid
    decision = evaluate_transition(previous, proposed)
    assert not decision.allowed
    assert any(error.path.endswith(field) for error in decision.errors)


def test_completed_null_verdict_is_rejected():
    previous, proposed = lifecycle_pair("COMPLETED", verdict=None)
    decision = evaluate_transition(previous, proposed)
    assert not decision.allowed
    assert any(error.path.endswith("verdict") for error in decision.errors)


@pytest.mark.parametrize("verdict", ["FAIL", "BLOCKED"])
def test_stopped_valid_verdict_is_preserved(verdict):
    previous, proposed = lifecycle_pair("STOPPED", verdict=verdict)
    assert evaluate_transition(previous, proposed).allowed
    assert proposed["verdict"] == verdict


def test_stopped_null_verdict_requires_error_code():
    previous, proposed = lifecycle_pair("STOPPED", verdict=None, error_code=None)
    decision = evaluate_transition(previous, proposed)
    assert not decision.allowed
    assert any(error.rule == "STOP_REASON_REQUIRED" for error in decision.errors)


def test_stopped_null_verdict_with_error_code_is_allowed():
    previous, proposed = lifecycle_pair(
        "STOPPED", verdict=None, error_code="IMPLEMENTATION_LOCAL_VALIDATION"
    )
    assert evaluate_transition(previous, proposed).allowed


def test_reconciliation_required_requires_error_code():
    previous, proposed = lifecycle_pair("RECONCILIATION_REQUIRED", error_code=None)
    decision = evaluate_transition(previous, proposed)
    assert not decision.allowed
    assert any(error.rule == "RECONCILIATION_REASON_REQUIRED" for error in decision.errors)


def test_reconciliation_required_with_error_code_is_allowed():
    previous, proposed = lifecycle_pair("RECONCILIATION_REQUIRED", error_code="SCOPE_DRIFT")
    assert evaluate_transition(previous, proposed).allowed


def test_same_transition_input_has_same_deterministic_result():
    previous = state_for("AUDIT1_DRAFT", "COMPLETED", verdict="PASS")
    proposed = state_for("AUDIT2_WORK_ORDER_REVIEW", "PENDING")
    assert evaluate_transition(previous, proposed) == evaluate_transition(
        deepcopy(previous), deepcopy(proposed)
    )


def test_transition_evaluation_does_not_mutate_inputs():
    previous = state_for("AUDIT1_DRAFT", "COMPLETED", verdict="PASS")
    proposed = state_for("AUDIT2_WORK_ORDER_REVIEW", "PENDING")
    before = deepcopy((previous, proposed))
    evaluate_transition(previous, proposed)
    assert (previous, proposed) == before


def test_completed_replay_is_not_executable():
    completed = state_for("AUDIT1_DRAFT", "COMPLETED", verdict="PASS")
    decision = evaluate_transition(completed, deepcopy(completed))
    assert not decision.allowed
    assert not decision.executable
    assert decision.is_replay
    assert any(error.rule == "COMPLETED_REPLAY" for error in decision.errors)


def test_forged_previous_idempotency_key_is_rejected():
    previous = state_for("BUILDER_IMPLEMENTATION", "PENDING")
    proposed = deepcopy(previous)
    proposed["transition_status"] = "RUNNING"
    previous["idempotency_key"] = "f" * 64
    decision = evaluate_transition(previous, proposed)
    assert not decision.allowed
    assert any(
        error.path == "previous_state.idempotency_key" and error.rule == "IDEMPOTENCY_KEY_MISMATCH"
        for error in decision.errors
    )


def test_forged_proposed_idempotency_key_is_rejected():
    previous = state_for("BUILDER_IMPLEMENTATION", "PENDING")
    proposed = deepcopy(previous)
    proposed["transition_status"] = "RUNNING"
    proposed["idempotency_key"] = "f" * 64
    decision = evaluate_transition(previous, proposed)
    assert not decision.allowed
    assert any(
        error.path == "proposed_state.idempotency_key" and error.rule == "IDEMPOTENCY_KEY_MISMATCH"
        for error in decision.errors
    )


def test_same_forged_idempotency_key_in_both_states_is_rejected():
    previous = state_for("BUILDER_IMPLEMENTATION", "PENDING")
    proposed = deepcopy(previous)
    proposed["transition_status"] = "RUNNING"
    previous["idempotency_key"] = "f" * 64
    proposed["idempotency_key"] = "f" * 64
    decision = evaluate_transition(previous, proposed)
    assert not decision.allowed
    assert sum(error.rule == "IDEMPOTENCY_KEY_MISMATCH" for error in decision.errors) == 2


def test_canonical_input_change_with_stale_key_is_rejected_first():
    previous = state_for("BUILDER_IMPLEMENTATION", "PENDING")
    proposed = deepcopy(previous)
    proposed["transition_status"] = "RUNNING"
    proposed["actor"] = "changed-actor"
    decision = evaluate_transition(previous, proposed)
    assert not decision.allowed
    assert any(error.rule == "IDEMPOTENCY_KEY_MISMATCH" for error in decision.errors)
    assert not any(error.rule == "TRANSITION_INVARIANT" for error in decision.errors)


def test_attempt_only_change_preserves_canonical_key_semantics():
    previous = state_for("BUILDER_IMPLEMENTATION", "PENDING")
    proposed = deepcopy(previous)
    proposed["transition_status"] = "RUNNING"
    proposed["attempt"] = 2
    assert proposed["idempotency_key"] == compute_idempotency_key(proposed)
    assert evaluate_transition(previous, proposed).allowed


def test_correct_key_pending_to_running_remains_allowed():
    previous = state_for("BUILDER_IMPLEMENTATION", "PENDING")
    proposed = deepcopy(previous)
    proposed["transition_status"] = "RUNNING"
    decision = evaluate_transition(previous, proposed)
    assert decision.allowed
    assert not decision.executable


def test_forged_key_cannot_bypass_completed_replay_protection():
    previous = state_for("AUDIT1_DRAFT", "COMPLETED", verdict="PASS")
    proposed = deepcopy(previous)
    previous["idempotency_key"] = "f" * 64
    proposed["idempotency_key"] = "f" * 64
    decision = evaluate_transition(previous, proposed)
    assert not decision.allowed
    assert not decision.executable
    assert any(error.rule == "IDEMPOTENCY_KEY_MISMATCH" for error in decision.errors)


def test_schema_invalid_states_stop_before_transition_logic():
    previous = state_for("AUDIT1_DRAFT", "COMPLETED", verdict="PASS")
    proposed = state_for("AUDIT2_WORK_ORDER_REVIEW", "PENDING")
    proposed["stage"] = "UNKNOWN"
    decision = evaluate_transition(previous, proposed)
    assert not decision.allowed
    assert not decision.executable


STEP1_SOURCE_ROOT = (
    Path(__file__).resolve().parents[1] / "src" / "topspeed_ai_os" / "development_workflow"
)

_APPROVED_IMPORTS_BY_FILE = {
    "__init__.py": frozenset(
        {
            "__future__.annotations",
            ".schema_validator.ValidationDiagnostic",
            ".schema_validator.ValidationResult",
            ".schema_validator.compute_idempotency_key",
            ".schema_validator.compute_scope_hash",
            ".schema_validator.validate_workflow_state",
            ".state_machine.TransitionDecision",
            ".state_machine.evaluate_transition",
        }
    ),
    "schema_validator.py": frozenset(
        {
            "__future__.annotations",
            "collections.abc.Mapping",
            "collections.abc.Sequence",
            "dataclasses.dataclass",
            "hashlib",
            "json",
            "jsonschema.Draft202012Validator",
            "jsonschema.FormatChecker",
            "jsonschema.SchemaError",
            "pathlib.Path",
            "re",
            "typing.Any",
        }
    ),
    "state_machine.py": frozenset(
        {
            "__future__.annotations",
            ".schema_validator.ValidationDiagnostic",
            ".schema_validator.compute_idempotency_key",
            ".schema_validator.validate_workflow_state",
            "collections.abc.Mapping",
            "dataclasses.dataclass",
            "typing.Any",
        }
    ),
}
_APPROVED_IMPORTS = frozenset().union(*_APPROVED_IMPORTS_BY_FILE.values())

_APPROVED_DEFINITIONS_BY_FILE = {
    "__init__.py": frozenset(),
    "schema_validator.py": frozenset(
        {
            "ValidationDiagnostic",
            "ValidationResult",
            "ValidationResult.valid",
            "_canonical_sha256",
            "_canonical_string_array",
            "_error_key",
            "_format_path",
            "_is_safe_path",
            "_load_schema",
            "_require_field",
            "_require_mapping",
            "_require_non_empty_string",
            "_require_pattern",
            "compute_idempotency_key",
            "compute_scope_hash",
            "validate_workflow_state",
        }
    ),
    "state_machine.py": frozenset(
        {
            "TransitionDecision",
            "_decision",
            "_diagnostic",
            "_idempotency_errors",
            "_schema_errors",
            "_state_invariants",
            "evaluate_transition",
        }
    ),
}

_APPROVED_EXTERNAL_CALLS = frozenset(
    {
        ".schema_validator.ValidationDiagnostic",
        ".schema_validator.compute_idempotency_key",
        ".schema_validator.validate_workflow_state",
        "dataclasses.dataclass",
        "hashlib.sha256",
        "json.dumps",
        "json.load",
        "jsonschema.Draft202012Validator",
        "jsonschema.Draft202012Validator.check_schema",
        "jsonschema.FormatChecker",
        "jsonschema.SchemaError",
        "pathlib.Path",
        "re.compile",
    }
)
_APPROVED_BUILTIN_CALLS = frozenset(
    {
        "ValueError",
        "bool",
        "enumerate",
        "frozenset",
        "isinstance",
        "set",
        "sorted",
        "str",
        "tuple",
        "type",
    }
)
_APPROVED_METHOD_CALLS = frozenset(
    {
        "_SCHEMA_PATH.resolve",
        "diagnostics.append",
        "errors.append",
        "errors.extend",
        "hashlib.sha256().hexdigest",
        "items.append",
        "join",
        "json.dumps().encode",
        "jsonschema.Draft202012Validator().iter_errors",
        "path.split",
        "path.startswith",
        "pathlib.Path().resolve",
        "pattern.fullmatch",
        "re.compile().match",
    }
)
_DYNAMIC_ESCAPE_CALLS = frozenset(
    {"__import__", "compile", "eval", "exec", "getattr", "globals", "locals"}
)


def _import_origin(node: ast.ImportFrom, imported_name: str) -> str:
    module = f"{'.' * node.level}{node.module or ''}"
    return f"{module}.{imported_name}" if module else imported_name


def _bound_name(alias: ast.alias, *, from_import: bool) -> str:
    if alias.asname:
        return alias.asname
    return alias.name if from_import else alias.name.split(".", 1)[0]


class Step1BoundaryAnalyzer(ast.NodeVisitor):
    """Fail-closed, test-only capability analysis for the approved STEP 1 runtime."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.allowed_imports = _APPROVED_IMPORTS_BY_FILE.get(filename, _APPROVED_IMPORTS)
        self.allowed_definitions = _APPROVED_DEFINITIONS_BY_FILE.get(filename, frozenset())
        self.aliases: dict[str, str] = {}
        self.local_definitions: set[str] = set()
        self.violations: list[str] = []
        self._class_stack: list[str] = []

    def analyze(self, source: str) -> tuple[str, ...]:
        tree = ast.parse(source, filename=self.filename)
        self._collect_import_aliases(tree)
        self._collect_assignment_aliases(tree)
        self.visit(tree)
        return tuple(sorted(set(self.violations)))

    def _violation(self, node: ast.AST, category: str, detail: str) -> None:
        self.violations.append(f"{category}:{getattr(node, 'lineno', 0)}:{detail}")

    def _collect_import_aliases(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    origin = alias.name
                    if origin not in self.allowed_imports:
                        self._violation(node, "IMPORT", origin)
                    binding = _bound_name(alias, from_import=False)
                    self.aliases[binding] = origin if alias.asname else binding
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    origin = _import_origin(node, alias.name)
                    if alias.name == "*" or origin not in self.allowed_imports:
                        self._violation(node, "IMPORT", origin)
                    self.aliases[_bound_name(alias, from_import=True)] = origin

    def _collect_assignment_aliases(self, tree: ast.AST) -> None:
        assignments: list[tuple[ast.AST, ast.AST]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                assignments.extend((target, node.value) for target in node.targets)
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                assignments.append((node.target, node.value))
        for _ in range(len(assignments) + 1):
            changed = False
            for target, value in assignments:
                if not isinstance(target, ast.Name):
                    continue
                origin = self._resolve(value)
                if not origin or origin == target.id or self.aliases.get(target.id) == origin:
                    continue
                if self._root_name(value) in self.aliases:
                    self.aliases[target.id] = origin
                    changed = True
            if not changed:
                break

    def _resolve(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return self.aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            parent = self._resolve(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        if isinstance(node, ast.Call):
            called = self._resolve(node.func)
            return f"{called}()" if called else ""
        if isinstance(node, ast.Subscript):
            return self._resolve(node.value)
        return ""

    @staticmethod
    def _root_name(node: ast.AST) -> str | None:
        while isinstance(node, (ast.Attribute, ast.Call, ast.Subscript)):
            node = node.value if isinstance(node, (ast.Attribute, ast.Subscript)) else node.func
        return node.id if isinstance(node, ast.Name) else None

    def _definition_name(self, name: str) -> str:
        return ".".join((*self._class_stack, name))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified = self._definition_name(node.name)
        self.local_definitions.add(node.name)
        if qualified not in self.allowed_definitions:
            self._violation(node, "DEFINITION", qualified)
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        qualified = self._definition_name(node.name)
        self.local_definitions.add(node.name)
        if qualified not in self.allowed_definitions:
            self._violation(node, "DEFINITION", qualified)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._violation(node, "DEFINITION", self._definition_name(node.name))
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._violation(node, "DEFINITION", "lambda")
        self.generic_visit(node)

    def _check_schema_open(self, node: ast.Call, called: str) -> None:
        mode = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
        encoding_values = [
            keyword.value.value
            for keyword in node.keywords
            if keyword.arg == "encoding" and isinstance(keyword.value, ast.Constant)
        ]
        if called != "schema_path.open":
            self._violation(node, "FILE_PATH", called)
        if mode != "r":
            self._violation(node, "FILE_MODE", repr(mode))
        if encoding_values != ["utf-8"] or any(
            keyword.arg not in {"encoding"} for keyword in node.keywords
        ):
            self._violation(node, "FILE_ENCODING", called)

    def visit_Call(self, node: ast.Call) -> None:
        called = self._resolve(node.func)
        raw_called = self._resolve_without_aliases(node.func)
        direct_name = node.func.id if isinstance(node.func, ast.Name) else None
        method = node.func.attr if isinstance(node.func, ast.Attribute) else None

        if direct_name in _DYNAMIC_ESCAPE_CALLS or called.split(".", 1)[0] in {
            "importlib",
            "__import__",
        }:
            self._violation(node, "DYNAMIC", called)
        elif method == "open" or direct_name == "open" or called == "io.open":
            self._check_schema_open(node, raw_called)
        elif (
            called in _APPROVED_EXTERNAL_CALLS
            or called in _APPROVED_METHOD_CALLS
            or direct_name in _APPROVED_BUILTIN_CALLS
            or direct_name in self.local_definitions
        ):
            pass
        else:
            self._violation(node, "CALL", called or ast.dump(node.func, include_attributes=False))
        self.generic_visit(node)

    @staticmethod
    def _resolve_without_aliases(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = Step1BoundaryAnalyzer._resolve_without_aliases(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        if isinstance(node, ast.Call):
            called = Step1BoundaryAnalyzer._resolve_without_aliases(node.func)
            return f"{called}()" if called else ""
        return ""


def analyze_step1_boundary(source: str, filename: str = "<synthetic>") -> tuple[str, ...]:
    return Step1BoundaryAnalyzer(filename).analyze(source)


class FakeRunner:
    """Test-only fixture returning one predefined deterministic result."""

    def __init__(self, result: dict[str, object]) -> None:
        self.result = deepcopy(result)
        self.calls = 0

    def run(self) -> dict[str, object]:
        self.calls += 1
        return deepcopy(self.result)


def test_no_real_actor_is_invoked_and_fake_runner_is_test_only():
    runner = FakeRunner({"verdict": "PASS"})
    previous = state_for("AUDIT1_DRAFT", "COMPLETED", verdict="PASS")
    proposed = state_for("AUDIT2_WORK_ORDER_REVIEW", "PENDING")
    assert evaluate_transition(previous, proposed).allowed
    assert runner.calls == 0
    assert runner.run() == {"verdict": "PASS"}

    source_root = (
        Path(__file__).resolve().parents[1] / "src" / "topspeed_ai_os" / "development_workflow"
    )
    runtime_classes = []
    runtime_calls = []
    for path in source_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        runtime_classes.extend(
            node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        )
        runtime_calls.extend(node for node in ast.walk(tree) if isinstance(node, ast.Call))
    assert not any("runner" in name.lower() or "actor" in name.lower() for name in runtime_classes)
    assert not any(
        isinstance(call.func, ast.Name)
        and ("runner" in call.func.id.lower() or "actor" in call.func.id.lower())
        for call in runtime_calls
    )


@pytest.mark.parametrize(
    "forbidden_root",
    [
        "git",
        "subprocess",
        "socket",
        "requests",
        "httpx",
        "urllib",
        "os",
        "topspeed_ai_os.tools",
        "topspeed_ai_os.data_hub",
        "topspeed_ai_os.contracts",
        "topspeed_ai_os.approval",
        "topspeed_ai_os.business_runtime",
    ],
)
def test_step1_runtime_has_no_forbidden_boundary_import(forbidden_root):
    source_root = (
        Path(__file__).resolve().parents[1] / "src" / "topspeed_ai_os" / "development_workflow"
    )
    imported: set[str] = set()
    for path in source_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    assert not any(
        name == forbidden_root or name.startswith(f"{forbidden_root}.") for name in imported
    )


def test_step1_runtime_has_no_forbidden_execution_or_file_mutation_call():
    source_root = (
        Path(__file__).resolve().parents[1] / "src" / "topspeed_ai_os" / "development_workflow"
    )
    forbidden_qualified_prefixes = (
        "subprocess.",
        "os.system",
        "os.popen",
        "os.getenv",
        "os.putenv",
        "socket.",
        "requests.",
        "httpx.",
        "urllib.",
        "git.",
        "Repo.",
    )
    forbidden_mutation_methods = {
        "write",
        "writelines",
        "write_text",
        "write_bytes",
        "touch",
        "mkdir",
        "unlink",
        "rmdir",
        "rename",
        "replace",
        "remove",
    }

    def qualified_name(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = qualified_name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    open_calls = []
    for path in source_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = qualified_name(node.func)
            assert not called.startswith(forbidden_qualified_prefixes)
            assert called.rsplit(".", 1)[-1] not in forbidden_mutation_methods
            assert "runner" not in called.lower()
            assert "actor" not in called.lower()
            if called == "open" or called.endswith(".open"):
                open_calls.append(node)

    assert len(open_calls) == 1
    schema_open = open_calls[0]
    assert schema_open.args
    assert isinstance(schema_open.args[0], ast.Constant)
    assert schema_open.args[0].value == "r"
    assert any(
        keyword.arg == "encoding"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value == "utf-8"
        for keyword in schema_open.keywords
    )


@pytest.mark.parametrize(
    "runtime_path",
    sorted(STEP1_SOURCE_ROOT.glob("*.py")),
    ids=lambda path: path.name,
)
def test_strict_boundary_analyzer_accepts_current_step1_runtime(runtime_path):
    source = runtime_path.read_text(encoding="utf-8")
    assert analyze_step1_boundary(source, runtime_path.name) == ()


@pytest.mark.parametrize(
    ("case", "source"),
    [
        (
            "network alternative",
            'import http.client as hc\nhc.HTTPSConnection("example.com")',
        ),
        (
            "file-write alias",
            'from io import open as fopen\nfopen("x.txt", "w")',
        ),
        (
            "credential capability",
            'import keyring\nkeyring.get_password("service", "user")',
        ),
        (
            "Git alternative",
            'from dulwich.repo import Repo\nRepo(".")',
        ),
        (
            "business execution alias",
            "from arbitrary_business_module import dispatch as execute\nexecute()",
        ),
        (
            "Runner synonym",
            "class Executor:\n    def execute(self):\n        pass\n\nExecutor().execute()",
        ),
    ],
)
def test_strict_boundary_analyzer_rejects_required_mutations(case, source):
    violations = analyze_step1_boundary(source)
    assert violations, case


@pytest.mark.parametrize(
    "source",
    [
        'import hashlib as hashing\nhashing.sha256(b"x").hexdigest()',
        'from pathlib import Path as ImportedPath\nImportedPath("state.json")',
        (
            "from pathlib import Path as ImportedPath\n"
            "PathAlias = ImportedPath\n"
            'PathAlias("state.json")'
        ),
    ],
)
def test_strict_boundary_analyzer_normalizes_approved_import_aliases(source):
    assert analyze_step1_boundary(source) == ()


def test_strict_boundary_analyzer_rejects_unknown_import_by_default():
    violations = analyze_step1_boundary("import apparently_harmless_module")
    assert any(item.startswith("IMPORT:") for item in violations)


@pytest.mark.parametrize(
    "source",
    [
        'import hashlib as hashing\nhashing.new("sha256")',
        "MysteryClient()",
        "executor.resolve()",
    ],
)
def test_strict_boundary_analyzer_rejects_unknown_call_or_constructor(source):
    violations = analyze_step1_boundary(source)
    assert any(item.startswith("CALL:") for item in violations)


@pytest.mark.parametrize(
    "source",
    [
        'eval("1 + 1")',
        'exec("pass")',
        'compile("pass", "<memory>", "exec")',
        '__import__("module")',
        'import importlib\nimportlib.import_module("module")',
        "globals()",
        "locals()",
        'getattr(target, "execute")()',
    ],
)
def test_strict_boundary_analyzer_rejects_dynamic_escape_hatches(source):
    violations = analyze_step1_boundary(source)
    assert any(item.startswith("DYNAMIC:") for item in violations)


def test_strict_boundary_analyzer_rejects_dynamic_file_mode():
    source = 'schema_path.open(mode, encoding="utf-8")'
    violations = analyze_step1_boundary(source)
    assert any(item.startswith("FILE_MODE:") for item in violations)


@pytest.mark.parametrize("mode", ["w", "a", "x", "r+", "w+", "a+", "x+"])
def test_strict_boundary_analyzer_rejects_file_mutation_modes(mode):
    source = f'schema_path.open("{mode}", encoding="utf-8")'
    violations = analyze_step1_boundary(source)
    assert any(item.startswith("FILE_MODE:") for item in violations)


@pytest.mark.parametrize(
    "method",
    [
        "mkdir",
        "remove",
        "rename",
        "replace",
        "rmdir",
        "touch",
        "unlink",
        "write",
        "write_bytes",
        "write_text",
        "writelines",
    ],
)
def test_strict_boundary_analyzer_rejects_file_mutation_methods(method):
    source = f'path.{method}("payload")'
    violations = analyze_step1_boundary(source)
    assert any(item.startswith("CALL:") for item in violations)


def test_strict_boundary_analyzer_allows_published_schema_utf8_read_only_open():
    source = 'schema_path.open("r", encoding="utf-8")'
    assert analyze_step1_boundary(source) == ()


def test_fake_runner_has_no_external_or_nondeterministic_dependency():
    first = FakeRunner({"verdict": "PASS", "findings": []})
    second = FakeRunner({"verdict": "PASS", "findings": []})
    assert first.run() == second.run()


def test_package_root_exports_all_approved_public_responsibilities():
    import topspeed_ai_os.development_workflow as workflow

    assert set(workflow.__all__) >= {
        "validate_workflow_state",
        "compute_idempotency_key",
        "compute_scope_hash",
        "evaluate_transition",
    }
