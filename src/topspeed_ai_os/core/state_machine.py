"""Approval state transitions defined by Data Contract v1."""

from __future__ import annotations

from .enums import ApprovalStatus

_ALLOWED_APPROVAL_TRANSITIONS: dict[ApprovalStatus, frozenset[ApprovalStatus]] = {
    ApprovalStatus.PENDING: frozenset(
        {
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.EXPIRED,
            ApprovalStatus.CANCELLED,
        }
    ),
    ApprovalStatus.APPROVED: frozenset(
        {
            ApprovalStatus.EXECUTED,
            ApprovalStatus.FAILED,
            ApprovalStatus.EXPIRED,
            ApprovalStatus.CANCELLED,
        }
    ),
}


class InvalidApprovalTransitionError(ValueError):
    """Raised when an approval state transition is not allowed."""


def can_transition_approval(
    current: ApprovalStatus | str,
    target: ApprovalStatus | str,
) -> bool:
    current_status = ApprovalStatus(current)
    target_status = ApprovalStatus(target)
    return target_status in _ALLOWED_APPROVAL_TRANSITIONS.get(current_status, frozenset())


def validate_approval_transition(
    current: ApprovalStatus | str,
    target: ApprovalStatus | str,
) -> None:
    try:
        current_status = ApprovalStatus(current)
        target_status = ApprovalStatus(target)
    except ValueError as exc:
        raise InvalidApprovalTransitionError(str(exc)) from exc

    if not can_transition_approval(current_status, target_status):
        raise InvalidApprovalTransitionError(
            f"approval transition {current_status.value} -> {target_status.value} is not allowed"
        )
