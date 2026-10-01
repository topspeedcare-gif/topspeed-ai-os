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
