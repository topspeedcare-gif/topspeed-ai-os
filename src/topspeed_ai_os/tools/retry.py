"""Bounded retry policy for idempotent read operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from .errors import ToolFailure

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.1
    max_delay_seconds: float = 2.0
    retry_after_cap_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if min(self.base_delay_seconds, self.max_delay_seconds, self.retry_after_cap_seconds) < 0:
            raise ValueError("retry delays cannot be negative")

    def delay_for(self, failure: ToolFailure, attempt: int) -> float:
        if failure.retry_after is not None:
            try:
                parsed = float(failure.retry_after)
            except (TypeError, ValueError):
                parsed = -1
            if 0 <= parsed <= self.retry_after_cap_seconds:
                return parsed
        return min(self.base_delay_seconds * (2 ** (attempt - 1)), self.max_delay_seconds)


def run_with_retry(
    operation: Callable[[], T],
    policy: RetryPolicy,
    sleeper: Callable[[float], None],
) -> tuple[T | None, ToolFailure | None, int]:
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation(), None, attempt
        except ToolFailure as failure:
            if not failure.retryable or attempt >= policy.max_attempts:
                return None, failure, attempt
            sleeper(policy.delay_for(failure, attempt))
    raise AssertionError("retry loop exhausted without a result")
