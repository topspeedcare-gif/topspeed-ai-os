"""Typed invocation results shared by every PHASE 3 read tool."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

_REQUEST_ID_PATTERN = re.compile(r"^req_[0-9a-f]{32}$")
_CHECKSUM_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class ToolStatus(StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ExecutionMode(StrEnum):
    MOCK = "MOCK"
    LIVE = "LIVE"


class ErrorCategory(StrEnum):
    NOT_ALLOWLISTED = "NOT_ALLOWLISTED"
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    SOURCE_SCHEMA_CHANGED = "SOURCE_SCHEMA_CHANGED"
    MALFORMED_SOURCE = "MALFORMED_SOURCE"
    MALFORMED_INPUT = "MALFORMED_INPUT"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    CONFIGURATION = "CONFIGURATION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class SensitiveBytes:
    """Raw bytes whose repr never exposes Source payload content."""

    _value: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self._value, bytes):
            raise TypeError("SensitiveBytes requires bytes")

    def reveal(self) -> bytes:
        return self._value

    def __repr__(self) -> str:
        return f"SensitiveBytes(<redacted>, length={len(self._value)})"


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    source: str
    source_uri: str
    fetched_at: datetime
    data_as_of: datetime | None
    checksum_sha256: str
    content_type: str | None = None
    http_status: int | None = None
    modified_time: str | None = None
    source_specific_metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not self.source or not self.source_uri:
            raise ValueError("source and source_uri are required")
        _require_aware(self.fetched_at, "fetched_at")
        if self.data_as_of is not None:
            _require_aware(self.data_as_of, "data_as_of")
        if _CHECKSUM_PATTERN.fullmatch(self.checksum_sha256) is None:
            raise ValueError("checksum_sha256 must use sha256:<lowercase 64 hex>")


@dataclass(frozen=True, slots=True)
class ToolError:
    category: ErrorCategory
    redacted_summary: str
    retryable: bool
    http_status: int | None = None
    attempt: int | None = None

    def __post_init__(self) -> None:
        if not self.redacted_summary:
            raise ValueError("redacted_summary is required")


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_name: str
    operation: str
    request_id: str
    status: ToolStatus
    execution_mode: ExecutionMode
    task_id: str | None
    run_id: str | None
    source_metadata: SourceMetadata | None
    raw_result: SensitiveBytes | None = field(default=None, repr=False)
    parsed_result: Any = field(default=None, repr=False)
    error: ToolError | None = None
    attempt_count: int = 1
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.tool_name or not self.operation:
            raise ValueError("tool_name and operation are required")
        if not isinstance(self.status, ToolStatus):
            raise TypeError("status must be a ToolStatus")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("execution_mode must be an ExecutionMode")
        if _REQUEST_ID_PATTERN.fullmatch(self.request_id) is None:
            raise ValueError("invalid request_id")
        if self.attempt_count < 1:
            raise ValueError("attempt_count must be positive")
        if self.status is ToolStatus.FAILED and self.error is None:
            raise ValueError("FAILED result requires an error")
        if self.status is ToolStatus.SUCCESS and self.error is not None:
            raise ValueError("SUCCESS result cannot contain an error")
        if self.status is not ToolStatus.FAILED and self.source_metadata is None:
            raise ValueError("non-FAILED result requires source metadata")
