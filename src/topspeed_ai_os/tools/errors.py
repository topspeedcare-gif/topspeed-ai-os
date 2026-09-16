"""Internal typed failures converted into redacted ToolError values."""

from __future__ import annotations

from dataclasses import dataclass

from .result import ErrorCategory, ToolError


@dataclass(frozen=True, slots=True)
class ToolFailure(Exception):
    category: ErrorCategory
    safe_summary: str
    retryable: bool = False
    http_status: int | None = None
    retry_after: str | None = None

    def to_error(self, attempt: int) -> ToolError:
        return ToolError(
            category=self.category,
            redacted_summary=self.safe_summary,
            retryable=self.retryable,
            http_status=self.http_status,
            attempt=attempt,
        )

    def __str__(self) -> str:
        return self.safe_summary
