"""Common read-tool invocation and transport boundaries."""

from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from topspeed_ai_os.core.ids import require_valid_run_id, require_valid_task_id

from .result import ExecutionMode


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes
    url: str


class HttpTransport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
        follow_redirects: bool,
    ) -> HttpResponse: ...


@dataclass(frozen=True, slots=True)
class InvocationContext:
    request_id: str
    task_id: str | None
    run_id: str | None


class ReadTool:
    def __init__(
        self,
        *,
        tool_name: str,
        _execution_mode: ExecutionMode,
        clock: Callable[[], datetime] | None = None,
        request_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(_execution_mode, ExecutionMode):
            raise TypeError("_execution_mode must be an ExecutionMode")
        self.tool_name = tool_name
        self.execution_mode = _execution_mode
        self._clock = clock or (lambda: datetime.now(UTC))
        self._request_id_factory = request_id_factory or (lambda: f"req_{secrets.token_hex(16)}")

    def _prepare_invocation(
        self,
        *,
        task_id: str | None,
        run_id: str | None,
    ) -> InvocationContext:
        if task_id is not None:
            require_valid_task_id(task_id)
        if run_id is not None:
            require_valid_run_id(run_id)
        return InvocationContext(self._request_id_factory(), task_id, run_id)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("tool clock must return a timezone-aware datetime")
        return value
