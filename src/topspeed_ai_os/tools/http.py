"""Fail-closed production HTTPS transport for read-only GET acquisition."""

from __future__ import annotations

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .base import HttpResponse
from .errors import ToolFailure
from .result import ErrorCategory, ExecutionMode


@dataclass(frozen=True, slots=True)
class LowLevelHttpRequest:
    method: str
    url: str
    headers: Mapping[str, str] = field(repr=False)
    timeout_seconds: float
    follow_redirects: bool


class LowLevelHttpExecutor(Protocol):
    def execute(self, request: LowLevelHttpRequest) -> HttpResponse: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True, slots=True)
class UrlLibGetExecutor:
    """Standard-library executor that never follows redirects."""

    def execute(self, request: LowLevelHttpRequest) -> HttpResponse:
        if request.method != "GET" or request.follow_redirects:
            raise ToolFailure(
                ErrorCategory.NOT_ALLOWLISTED,
                "Production HTTP executor permits only non-redirecting GET",
            )
        opener = build_opener(_NoRedirectHandler())
        outbound = Request(request.url, headers=dict(request.headers), method="GET")
        try:
            with opener.open(outbound, timeout=request.timeout_seconds) as response:
                return HttpResponse(
                    status_code=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read(),
                    url=response.geturl(),
                )
        except HTTPError as error:
            try:
                body = error.read()
                status_code = error.code
                headers = dict(error.headers.items()) if error.headers is not None else {}
                response_url = error.geturl()
            finally:
                error.close()
            return HttpResponse(
                status_code=status_code,
                headers=headers,
                body=body,
                url=response_url,
            )


class ProductionHttpTransport:
    """Concrete production transport with an immutable exact-host allowlist."""

    __slots__ = ("_allowed_hosts", "_execution_mode", "_executor")

    def __init__(
        self,
        *,
        allowed_hosts: frozenset[str],
        executor: LowLevelHttpExecutor | None = None,
    ) -> None:
        if not allowed_hosts or any(
            not host or host != host.lower() or ":" in host for host in allowed_hosts
        ):
            raise ValueError("allowed_hosts must contain exact lowercase host names")
        selected_executor = executor or UrlLibGetExecutor()
        self._allowed_hosts = frozenset(allowed_hosts)
        self._executor = selected_executor
        self._execution_mode = (
            ExecutionMode.LIVE
            if type(selected_executor) is UrlLibGetExecutor
            else ExecutionMode.MOCK
        )

    @property
    def allowed_hosts(self) -> frozenset[str]:
        return self._allowed_hosts

    @property
    def execution_mode(self) -> ExecutionMode:
        return self._execution_mode

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
        follow_redirects: bool,
    ) -> HttpResponse:
        if method != "GET":
            raise ToolFailure(ErrorCategory.NOT_ALLOWLISTED, "Production HTTP is GET-only")
        if follow_redirects:
            raise ToolFailure(ErrorCategory.NOT_ALLOWLISTED, "HTTP redirects are disabled")
        if timeout_seconds <= 0:
            raise ToolFailure(ErrorCategory.CONFIGURATION, "HTTP timeout must be positive")
        self._validate_url(url)
        response = self._executor.execute(
            LowLevelHttpRequest(
                method="GET",
                url=url,
                headers=dict(headers),
                timeout_seconds=timeout_seconds,
                follow_redirects=False,
            )
        )
        self._validate_url(response.url)
        return response

    def _validate_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in self._allowed_hosts
            or parsed.port is not None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ToolFailure(ErrorCategory.NOT_ALLOWLISTED, "HTTPS target is not allowlisted")
        if (
            not parsed.path.startswith("/")
            or "\\" in parsed.path
            or "%" in parsed.path
            or "//" in parsed.path
            or posixpath.normpath(parsed.path) != parsed.path
        ):
            raise ToolFailure(ErrorCategory.NOT_ALLOWLISTED, "HTTPS path is not normalized")

    def __repr__(self) -> str:
        return f"ProductionHttpTransport(allowed_hosts={sorted(self._allowed_hosts)!r})"
