"""Pure deterministic evaluation of published workflow state transitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .schema_validator import (
    ValidationDiagnostic,
    compute_idempotency_key,
    validate_workflow_state,
)

_STAGES = (
    "AUDIT1_DRAFT",
    "AUDIT2_WORK_ORDER_REVIEW",
    "BUILDER_IMPLEMENTATION",
    "AUDIT1_IMPLEMENTATION_AUDIT",
    "AUDIT2_IMPLEMENTATION_REAUDIT",
    "PUBLICATION_READY",
)
_NEXT_STAGE = {stage: _STAGES[index + 1] for index, stage in enumerate(_STAGES[:-1])}
_NEXT_STAGE["PUBLICATION_READY"] = None
_WORKFLOW_IMMUTABLE_FIELDS = (
    "schema_version",
    "workflow_run_id",
    "work_item_id",
    "phase",
    "slice",
    "baseline_sha",
    "scope_hash",
    "parent_scope_hash",
    "work_order_ref",
    "approved_work_order_sha256",
)
_TRANSITION_IMMUTABLE_FIELDS = (
    *_WORKFLOW_IMMUTABLE_FIELDS,
    "stage",
    "actor",
    "transition_id",
    "idempotency_key",
    "pre_stage_sha",
    "created_at",
    "human_approval_required",
)
_LIFECYCLE_EDGES = frozenset(
    {
        ("PENDING", "RUNNING"),
        ("PENDING", "STOPPED"),
        ("PENDING", "RECONCILIATION_REQUIRED"),
        ("RUNNING", "COMPLETED"),
        ("RUNNING", "STOPPED"),
        ("RUNNING", "RECONCILIATION_REQUIRED"),
    }
)


@dataclass(frozen=True, slots=True)
class TransitionDecision:
    """Side-effect-free transition and replay decision."""

    allowed: bool
    executable: bool
    is_replay: bool
    automatic_next_transition: str | None
    expected_next_stage: str | None
    errors: tuple[ValidationDiagnostic, ...]


def _diagnostic(path: str, reason: str, message: str) -> ValidationDiagnostic:
    return ValidationDiagnostic(path, reason, message)


def _state_invariants(state: Mapping[str, Any], label: str) -> list[ValidationDiagnostic]:
    status = state["transition_status"]
    verdict = state["verdict"]
    completed_at = state["completed_at"]
    error_code = state["error_code"]
    expected = state["expected_next_stage"]
    stage = state["stage"]
    errors: list[ValidationDiagnostic] = []

    if status in {"PENDING", "RUNNING"}:
        if verdict is not None:
            errors.append(
                _diagnostic(f"{label}.verdict", "STATUS_VERDICT_MATRIX", f"{status} requires null")
            )
        if completed_at is not None:
            errors.append(
                _diagnostic(
                    f"{label}.completed_at", "STATUS_TIME_MATRIX", f"{status} requires null"
                )
            )
        if expected is not None:
            errors.append(
                _diagnostic(
                    f"{label}.expected_next_stage",
                    "PRE_TERMINAL_ROUTING",
                    f"{status} cannot route automatically",
                )
            )
    elif completed_at is None:
        errors.append(
            _diagnostic(
                f"{label}.completed_at",
                "STATUS_TIME_MATRIX",
                f"{status} requires a completion timestamp",
            )
        )

    if status == "COMPLETED":
        if verdict is None:
            errors.append(
                _diagnostic(
                    f"{label}.verdict", "STATUS_VERDICT_MATRIX", "COMPLETED requires a verdict"
                )
            )
        elif verdict != "PASS":
            errors.append(
                _diagnostic(
                    f"{label}.verdict",
                    "STOP_REQUIRED",
                    "FAIL or BLOCKED must not be reclassified as COMPLETED",
                )
            )
        published_next = _NEXT_STAGE[stage]
        if expected != published_next:
            errors.append(
                _diagnostic(
                    f"{label}.expected_next_stage",
                    "EXPECTED_NEXT_STAGE",
                    f"must be {published_next!r}",
                )
            )
    elif status == "STOPPED":
        if verdict not in {None, "FAIL", "BLOCKED"}:
            errors.append(
                _diagnostic(
                    f"{label}.verdict",
                    "STATUS_VERDICT_MATRIX",
                    "STOPPED preserves FAIL/BLOCKED or has no Actor verdict",
                )
            )
        if verdict is None and error_code is None:
            errors.append(
                _diagnostic(
                    f"{label}.error_code",
                    "STOP_REASON_REQUIRED",
                    "STOPPED without an Actor verdict requires error_code",
                )
            )
        if expected is not None:
            errors.append(
                _diagnostic(
                    f"{label}.expected_next_stage",
                    "STOP_ROUTING",
                    "STOPPED requires null",
                )
            )
    elif status == "RECONCILIATION_REQUIRED":
        if error_code is None:
            errors.append(
                _diagnostic(
                    f"{label}.error_code",
                    "RECONCILIATION_REASON_REQUIRED",
                    "RECONCILIATION_REQUIRED requires error_code",
                )
            )
        if expected is not None:
            errors.append(
                _diagnostic(
                    f"{label}.expected_next_stage",
                    "STOP_ROUTING",
                    "RECONCILIATION_REQUIRED requires null",
                )
            )
    return errors


def _schema_errors(state: object, label: str) -> list[ValidationDiagnostic]:
    result = validate_workflow_state(state)
    return [
        ValidationDiagnostic(f"{label}{error.path[1:]}", error.rule, error.message)
        for error in result.errors
    ]


def _idempotency_errors(state: Mapping[str, Any], label: str) -> list[ValidationDiagnostic]:
    try:
        expected_key = compute_idempotency_key(state)
    except (TypeError, ValueError) as exc:
        return [
            _diagnostic(
                f"{label}.idempotency_key",
                "IDEMPOTENCY_KEY_INVALID",
                f"canonical idempotency key could not be computed: {type(exc).__name__}: {exc}",
            )
        ]
    if state["idempotency_key"] != expected_key:
        return [
            _diagnostic(
                f"{label}.idempotency_key",
                "IDEMPOTENCY_KEY_MISMATCH",
                "stored idempotency_key does not match the canonical inputs",
            )
        ]
    return []


def _decision(
    *,
    allowed: bool,
    executable: bool = False,
    replay: bool = False,
    next_stage: str | None = None,
    errors: list[ValidationDiagnostic] | None = None,
) -> TransitionDecision:
    ordered = tuple(sorted(errors or []))
    return TransitionDecision(
        allowed=allowed,
        executable=executable,
        is_replay=replay,
        automatic_next_transition=next_stage if allowed else None,
        expected_next_stage=next_stage if allowed else None,
        errors=ordered,
    )


def evaluate_transition(
    previous_state: Mapping[str, Any], proposed_state: Mapping[str, Any]
) -> TransitionDecision:
    """Evaluate one lifecycle or fixed-stage transition without invoking any Actor."""

    errors = _schema_errors(previous_state, "previous_state")
    errors.extend(_schema_errors(proposed_state, "proposed_state"))
    if errors:
        return _decision(allowed=False, errors=errors)

    errors.extend(_idempotency_errors(previous_state, "previous_state"))
    errors.extend(_idempotency_errors(proposed_state, "proposed_state"))
    if errors:
        return _decision(allowed=False, errors=errors)

    errors.extend(_state_invariants(previous_state, "previous_state"))
    errors.extend(_state_invariants(proposed_state, "proposed_state"))
    if errors:
        return _decision(allowed=False, errors=errors)

    if (
        previous_state["transition_status"] == "COMPLETED"
        and previous_state["idempotency_key"] == proposed_state["idempotency_key"]
    ):
        return _decision(
            allowed=False,
            replay=True,
            errors=[
                _diagnostic(
                    "proposed_state.idempotency_key",
                    "COMPLETED_REPLAY",
                    "a completed Transition is never executable again",
                )
            ],
        )

    for field in _WORKFLOW_IMMUTABLE_FIELDS:
        if previous_state[field] != proposed_state[field]:
            errors.append(
                _diagnostic(
                    f"proposed_state.{field}",
                    "WORKFLOW_INVARIANT",
                    "must equal previous_state",
                )
            )
    if errors:
        return _decision(allowed=False, errors=errors)

    previous_stage = previous_state["stage"]
    proposed_stage = proposed_state["stage"]
    if proposed_stage == previous_stage:
        for field in _TRANSITION_IMMUTABLE_FIELDS:
            if previous_state[field] != proposed_state[field]:
                errors.append(
                    _diagnostic(
                        f"proposed_state.{field}",
                        "TRANSITION_INVARIANT",
                        "must equal previous_state during one Transition lifecycle",
                    )
                )
        status_edge = (
            previous_state["transition_status"],
            proposed_state["transition_status"],
        )
        if status_edge not in _LIFECYCLE_EDGES:
            errors.append(
                _diagnostic(
                    "proposed_state.transition_status",
                    "INVALID_LIFECYCLE_EDGE",
                    f"transition {status_edge[0]} -> {status_edge[1]} is not allowed",
                )
            )
        return _decision(
            allowed=not errors,
            executable=False,
            next_stage=proposed_state["expected_next_stage"] if not errors else None,
            errors=errors,
        )

    expected_stage = _NEXT_STAGE[previous_stage]
    if proposed_stage != expected_stage:
        return _decision(
            allowed=False,
            errors=[
                _diagnostic(
                    "proposed_state.stage",
                    "INVALID_STAGE_EDGE",
                    f"expected {expected_stage!r}, got {proposed_stage!r}",
                )
            ],
        )
    if previous_state["transition_status"] != "COMPLETED" or previous_state["verdict"] != "PASS":
        return _decision(
            allowed=False,
            errors=[
                _diagnostic(
                    "previous_state.transition_status",
                    "PREVIOUS_STAGE_NOT_ROUTABLE",
                    "only COMPLETED/PASS may enter the next fixed stage",
                )
            ],
        )
    if proposed_state["transition_status"] != "PENDING":
        return _decision(
            allowed=False,
            errors=[
                _diagnostic(
                    "proposed_state.transition_status",
                    "NEW_STAGE_NOT_PENDING",
                    "the next Transition must begin as PENDING",
                )
            ],
        )
    return _decision(
        allowed=True,
        executable=True,
        next_stage=proposed_stage,
    )
