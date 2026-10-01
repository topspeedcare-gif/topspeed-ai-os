from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from topspeed_ai_os.development_workflow import (
    compute_idempotency_key,
    compute_scope_hash,
    validate_workflow_state,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "architecture"
    / "schemas"
    / "development_workflow_state_v1.schema.json"
)
SHA1 = "a" * 40
SHA256 = "b" * 64


def valid_state() -> dict[str, object]:
    state: dict[str, object] = {
        "schema_version": "development_workflow_state.v1",
        "workflow_run_id": "workflow-001",
        "work_item_id": "step-1",
        "phase": "DEVELOPMENT_WORKFLOW",
        "slice": None,
        "stage": "AUDIT1_DRAFT",
        "actor": "independent-actor-name",
        "transition_id": "transition-001",
        "idempotency_key": "0" * 64,
        "transition_status": "PENDING",
        "baseline_sha": SHA1,
        "pre_stage_sha": SHA1,
        "post_stage_sha": None,
        "result_sha": None,
        "scope_hash": "c" * 64,
        "parent_scope_hash": None,
        "attempt": 1,
        "verdict": None,
        "findings": [],
        "work_order_ref": "docs/work-orders/step-1.md",
        "approved_work_order_sha256": SHA256,
        "evidence_refs": [],
        "actual_changed_paths": [],
        "actual_operation_classes": [],
        "expected_next_stage": None,
        "human_approval_required": False,
        "error_code": None,
        "created_at": "2026-10-01T09:00:00+09:00",
        "completed_at": None,
    }
    state["idempotency_key"] = compute_idempotency_key(state)
    return state


def scope_input() -> dict[str, object]:
    return {
        "schema_version": "development_workflow_state.v1",
        "work_item_id": "step-1",
        "approved_work_order_id": "STEP1-FINAL",
        "approved_work_order_sha256": SHA256,
        "baseline_sha": SHA1,
        "phase": "DEVELOPMENT_WORKFLOW",
        "slice": None,
        "allowed_paths": ["src/example.py", "tests/test_example.py"],
        "allowed_operation_classes": ["SOURCE_WRITE", "TEST_WRITE"],
    }


def test_published_schema_meta_validation_passes():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_valid_state_passes():
    result = validate_workflow_state(valid_state())
    assert result.is_valid
    assert result.errors == ()


def test_missing_required_field_is_rejected():
    state = valid_state()
    del state["actor"]
    result = validate_workflow_state(state)
    assert not result.is_valid
    assert any(error.rule == "required" for error in result.errors)


def test_unknown_property_is_rejected():
    state = valid_state()
    state["unknown"] = True
    result = validate_workflow_state(state)
    assert not result.is_valid
    assert any(error.rule == "additionalProperties" for error in result.errors)


def test_invalid_field_type_is_rejected():
    state = valid_state()
    state["attempt"] = "1"
    result = validate_workflow_state(state)
    assert not result.is_valid
    assert any(error.path == "$.attempt" and error.rule == "type" for error in result.errors)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stage", "UNKNOWN"),
        ("transition_status", "UNKNOWN"),
        ("verdict", "WARN"),
    ],
)
def test_invalid_published_enum_is_rejected(field, value):
    state = valid_state()
    state[field] = value
    result = validate_workflow_state(state)
    assert not result.is_valid
    assert any(error.path == f"$.{field}" for error in result.errors)


def test_empty_actor_is_rejected_structurally():
    state = valid_state()
    state["actor"] = ""
    assert not validate_workflow_state(state).is_valid


def test_non_empty_actor_is_not_rejected_by_an_invented_enum():
    state = valid_state()
    state["actor"] = "a future independently named actor"
    assert validate_workflow_state(state).is_valid


def test_invalid_git_sha_is_rejected():
    state = valid_state()
    state["baseline_sha"] = "A" * 40
    assert not validate_workflow_state(state).is_valid


def test_invalid_sha256_is_rejected():
    state = valid_state()
    state["scope_hash"] = "sha256:" + ("c" * 64)
    assert not validate_workflow_state(state).is_valid


@pytest.mark.parametrize(
    "path",
    ["/absolute/path.md", "C:/absolute/path.md"],
)
def test_absolute_path_is_rejected(path):
    state = valid_state()
    state["work_order_ref"] = path
    assert not validate_workflow_state(state).is_valid


def test_backslash_path_is_rejected():
    state = valid_state()
    state["work_order_ref"] = "docs\\work-order.md"
    assert not validate_workflow_state(state).is_valid


def test_parent_traversal_path_is_rejected():
    state = valid_state()
    state["work_order_ref"] = "docs/../work-order.md"
    assert not validate_workflow_state(state).is_valid


def test_validation_error_order_is_deterministic():
    state = valid_state()
    state["attempt"] = "bad"
    state["actor"] = ""
    state["stage"] = "UNKNOWN"
    first = validate_workflow_state(state)
    second = validate_workflow_state(state)
    assert first == second
    assert first.errors == tuple(sorted(first.errors))


def test_schema_validation_does_not_mutate_input():
    state = valid_state()
    before = deepcopy(state)
    validate_workflow_state(state)
    assert state == before


def test_idempotency_same_canonical_input_has_same_key():
    state = valid_state()
    assert compute_idempotency_key(state) == compute_idempotency_key(deepcopy(state))


def test_idempotency_attempt_change_has_same_key():
    state = valid_state()
    changed = {**state, "attempt": 99}
    assert compute_idempotency_key(state) == compute_idempotency_key(changed)


def test_idempotency_canonical_input_change_has_different_key():
    state = valid_state()
    changed = {**state, "actor": "another-non-empty-actor"}
    assert compute_idempotency_key(state) != compute_idempotency_key(changed)


def test_idempotency_missing_canonical_field_fails_closed():
    state = valid_state()
    del state["pre_stage_sha"]
    with pytest.raises(ValueError, match="pre_stage_sha"):
        compute_idempotency_key(state)


def test_idempotency_uses_exact_canonical_field_set_only():
    state = valid_state()
    fields = {
        name: state[name]
        for name in (
            "schema_version",
            "workflow_run_id",
            "work_item_id",
            "stage",
            "actor",
            "approved_work_order_sha256",
            "pre_stage_sha",
        )
    }
    expected_bytes = json.dumps(
        fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert (
        compute_idempotency_key({**state, "ignored": "value"})
        == hashlib.sha256(expected_bytes).hexdigest()
    )


def test_scope_hash_same_canonical_input_has_same_hash():
    value = scope_input()
    assert compute_scope_hash(value) == compute_scope_hash(deepcopy(value))


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("allowed_paths", ["tests/test_example.py", "src/example.py"]),
        (
            "allowed_operation_classes",
            ["TEST_WRITE", "SOURCE_WRITE"],
        ),
    ],
)
def test_scope_hash_array_order_change_has_same_hash(field, changed):
    value = scope_input()
    reordered = {**value, field: changed}
    assert compute_scope_hash(value) == compute_scope_hash(reordered)


@pytest.mark.parametrize(
    "field",
    ["allowed_paths", "allowed_operation_classes"],
)
def test_scope_hash_array_duplicate_has_same_hash(field):
    value = scope_input()
    duplicated = {**value, field: [*value[field], value[field][0]]}
    assert compute_scope_hash(value) == compute_scope_hash(duplicated)


def test_scope_hash_null_slice_is_explicit_and_deterministic():
    value = scope_input()
    expected = {
        **value,
        "allowed_paths": sorted(set(value["allowed_paths"])),
        "allowed_operation_classes": sorted(set(value["allowed_operation_classes"])),
    }
    encoded = json.dumps(
        expected, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert b'"slice":null' in encoded
    assert compute_scope_hash(value) == hashlib.sha256(encoded).hexdigest()


def test_scope_hash_canonical_input_change_has_different_hash():
    value = scope_input()
    assert compute_scope_hash(value) != compute_scope_hash({**value, "phase": "OTHER"})


def test_scope_hash_missing_required_input_fails_closed():
    value = scope_input()
    del value["approved_work_order_id"]
    with pytest.raises(ValueError, match="approved_work_order_id"):
        compute_scope_hash(value)


@pytest.mark.parametrize(
    "path",
    ["/absolute.py", "C:/absolute.py", "src\\module.py", "src/../module.py"],
)
def test_scope_hash_invalid_path_fails_closed(path):
    value = scope_input()
    value["allowed_paths"] = [path]
    with pytest.raises(ValueError, match="unsafe path"):
        compute_scope_hash(value)


def test_public_hash_outputs_are_lowercase_64_character_hex():
    for value in (compute_idempotency_key(valid_state()), compute_scope_hash(scope_input())):
        assert len(value) == 64
        assert value == value.lower()
        int(value, 16)
