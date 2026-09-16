from __future__ import annotations

import pytest

from topspeed_ai_os.core.enums import ApprovalStatus, AuditStatus, Grade, ResultStatus, Skill, Stage
from topspeed_ai_os.core.state_machine import (
    InvalidApprovalTransitionError,
    can_transition_approval,
    validate_approval_transition,
)


def test_frozen_enum_values():
    assert {item.value for item in Skill} == {
        "sourcing",
        "launch",
        "ads_ops",
        "content",
        "inventory",
        "data",
    }
    assert {item.value for item in AuditStatus} == {"PASS", "WARN", "FAIL"}
    assert {item.value for item in ApprovalStatus} == {
        "PENDING",
        "APPROVED",
        "REJECTED",
        "EXPIRED",
        "CANCELLED",
        "EXECUTED",
        "FAILED",
    }
    assert {item.value for item in ResultStatus} == {
        "STARTED",
        "SUCCEEDED",
        "BLOCKED",
        "FAILED",
        "CANCELLED",
    }
    assert {item.value for item in Stage} == {"SOURCE", "TEST", "SCALE", "CORE", "EXIT"}
    assert {item.value for item in Grade} == {"S", "A", "B", "T", "X"}


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("PENDING", "APPROVED"),
        ("PENDING", "REJECTED"),
        ("PENDING", "EXPIRED"),
        ("PENDING", "CANCELLED"),
        ("APPROVED", "EXECUTED"),
        ("APPROVED", "FAILED"),
        ("APPROVED", "EXPIRED"),
        ("APPROVED", "CANCELLED"),
    ],
)
def test_allowed_approval_transitions(current, target):
    assert can_transition_approval(current, target)
    validate_approval_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("PENDING", "EXECUTED"),
        ("APPROVED", "REJECTED"),
        ("REJECTED", "APPROVED"),
        ("EXPIRED", "PENDING"),
        ("EXECUTED", "FAILED"),
        ("CANCELLED", "APPROVED"),
    ],
)
def test_forbidden_approval_transitions(current, target):
    assert not can_transition_approval(current, target)
    with pytest.raises(InvalidApprovalTransitionError):
        validate_approval_transition(current, target)


def test_unknown_approval_status_is_rejected():
    with pytest.raises(InvalidApprovalTransitionError):
        validate_approval_transition("UNKNOWN", "APPROVED")
