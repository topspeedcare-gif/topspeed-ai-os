"""Allowlisted, GET-only Coupang Source reader.

Only module-owned endpoint contracts that were independently verified against official
Coupang documentation may run with LIVE executor provenance. Unit tests use injected
executors or unverified endpoints in MOCK mode and never perform network I/O.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import posixpath
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any
from urllib.parse import urlencode, urlsplit

from ..base import HttpResponse, HttpTransport, ReadTool
from ..checksum import raw_sha256
from ..credentials import CoupangCredentials, CredentialProvider
from ..errors import ToolFailure
from ..http import ProductionHttpTransport
from ..provenance import parse_source_data_as_of
from ..result import (
    ErrorCategory,
    ExecutionMode,
    SensitiveBytes,
    SourceMetadata,
    ToolResult,
    ToolStatus,
)
from ..retry import RetryPolicy, run_with_retry

COUPANG_API_HOST = "api-gateway.coupang.com"
_SAFE_PARAMETER = re.compile(r"^[A-Za-z0-9._~-]+$")
_SAFE_NUMBER = re.compile(r"^[0-9]+$")
_PLACEHOLDER = re.compile(r"{([A-Za-z][A-Za-z0-9_]*)}")
_SENSITIVE_QUERY_NAMES = frozenset(
    {"access_token", "token", "authorization", "signature", "secret", "refresh_token"}
)


@dataclass(frozen=True, slots=True)
class CoupangEndpoint:
    operation: str
    path_template: str
    parameter_names: tuple[str, ...]
    allowed_query_names: tuple[str, ...] = ()
    expected_json_type: type = dict
    data_as_of_path: tuple[str, ...] | None = None
    host: str = COUPANG_API_HOST
    numeric_parameter_names: tuple[str, ...] = ()
    success_status_codes: tuple[int, ...] = (200, 206)

    def __post_init__(self) -> None:
        if not self.operation.startswith("coupang.") or "://" in self.operation:
            raise ValueError("operation must be a symbolic coupang.* name")
        if self.host != COUPANG_API_HOST:
            raise ValueError("Coupang host is not allowlisted")
        if (
            not self.path_template.startswith("/")
            or ".." in self.path_template
            or "//" in self.path_template
            or any(marker in self.path_template for marker in ("?", "#", "%", "\\"))
        ):
            raise ValueError("unsafe Coupang path template")
        placeholders = tuple(_PLACEHOLDER.findall(self.path_template))
        if placeholders != self.parameter_names or len(set(placeholders)) != len(placeholders):
            raise ValueError("parameter_names must exactly match unique path placeholders")
        if len(set(self.numeric_parameter_names)) != len(self.numeric_parameter_names) or not set(
            self.numeric_parameter_names
        ).issubset(self.parameter_names):
            raise ValueError("numeric_parameter_names must be unique path parameters")
        if len(set(self.allowed_query_names)) != len(self.allowed_query_names):
            raise ValueError("duplicate allowed query name")
        if any(_SAFE_PARAMETER.fullmatch(name) is None for name in self.allowed_query_names):
            raise ValueError("unsafe allowed query name")
        if set(name.lower() for name in self.allowed_query_names) & _SENSITIVE_QUERY_NAMES:
            raise ValueError("sensitive query names cannot be allowlisted")
        if (
            not self.success_status_codes
            or len(set(self.success_status_codes)) != len(self.success_status_codes)
            or any(
                not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599
                for status in self.success_status_codes
            )
        ):
            raise ValueError("success_status_codes must contain unique HTTP status codes")
        if self.data_as_of_path is not None and (
            not self.data_as_of_path
            or any(not name or not isinstance(name, str) for name in self.data_as_of_path)
        ):
            raise ValueError("data_as_of_path must contain explicit response field names")

    def build_url(
        self,
        parameters: Mapping[str, str],
        query: Mapping[str, str],
    ) -> str:
        if set(parameters) != set(self.parameter_names):
            raise ToolFailure(
                ErrorCategory.MALFORMED_INPUT,
                "Coupang path parameters do not match the operation contract",
            )
        path = self.path_template
        for name in self.parameter_names:
            value = parameters[name]
            pattern = _SAFE_NUMBER if name in self.numeric_parameter_names else _SAFE_PARAMETER
            if not isinstance(value, str) or pattern.fullmatch(value) is None:
                raise ToolFailure(
                    ErrorCategory.NOT_ALLOWLISTED, "Unsafe Coupang resource identifier"
                )
            path = path.replace(f"{{{name}}}", value)
        if posixpath.normpath(path) != path:
            raise ToolFailure(ErrorCategory.NOT_ALLOWLISTED, "Coupang path is not normalized")
        if not set(query).issubset(self.allowed_query_names):
            raise ToolFailure(ErrorCategory.NOT_ALLOWLISTED, "Coupang query is not allowlisted")
        if any(
            not isinstance(value, str) or _SAFE_PARAMETER.fullmatch(value) is None
            for value in query.values()
        ):
            raise ToolFailure(ErrorCategory.NOT_ALLOWLISTED, "Unsafe Coupang query value")
        query_string = urlencode(sorted(query.items()))
        suffix = f"?{query_string}" if query_string else ""
        return f"https://{self.host}{path}{suffix}"

    def allows_url(self, url: str) -> bool:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != self.host
            or parsed.port is not None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            return False
        if posixpath.normpath(parsed.path) != parsed.path or "%" in parsed.path:
            return False
        pattern = re.escape(self.path_template)
        for name in self.parameter_names:
            value_pattern = (
                _SAFE_NUMBER.pattern[1:-1]
                if name in self.numeric_parameter_names
                else _SAFE_PARAMETER.pattern[1:-1]
            )
            pattern = pattern.replace(re.escape(f"{{{name}}}"), value_pattern)
        if re.fullmatch(pattern, parsed.path) is None:
            return False
        if not parsed.query:
            return True
        query_parts = parsed.query.split("&")
        if any(not part or part.count("=") != 1 or "%" in part for part in query_parts):
            return False
        query_items = [part.split("=", 1) for part in query_parts]
        query_names = [name for name, _value in query_items]
        if len(set(query_names)) != len(query_names):
            return False
        return set(query_names).issubset(self.allowed_query_names) and all(
            _SAFE_PARAMETER.fullmatch(value) is not None for _name, value in query_items
        )

    def extract_data_as_of(self, payload: Any) -> datetime | None:
        if self.data_as_of_path is None:
            return None
        current = payload
        for index, name in enumerate(self.data_as_of_path):
            if not isinstance(current, Mapping):
                raise ToolFailure(
                    ErrorCategory.MALFORMED_SOURCE,
                    "Coupang data_as_of path does not match the response",
                )
            if name not in current:
                return None
            current = current[name]
            if index < len(self.data_as_of_path) - 1 and current is None:
                raise ToolFailure(
                    ErrorCategory.MALFORMED_SOURCE,
                    "Coupang data_as_of path does not match the response",
                )
        try:
            return parse_source_data_as_of(current)
        except ValueError as exc:
            raise ToolFailure(
                ErrorCategory.MALFORMED_SOURCE,
                "Coupang data_as_of is invalid",
            ) from exc


# Official contract source:
# 상품 조회 — https://developers.coupang.com/ko/api/products/querying-product
# HMAC 인증 — https://developers.coupang.com/ko/getting-started/open-api-test-guide
# Verified: 2026-09-17
GET_SELLER_PRODUCT_ENDPOINT = CoupangEndpoint(
    operation="coupang.get_seller_product",
    path_template="/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{sellerProductId}",
    parameter_names=("sellerProductId",),
    numeric_parameter_names=("sellerProductId",),
    allowed_query_names=(),
    success_status_codes=(200,),
    expected_json_type=dict,
    data_as_of_path=None,
)

_VERIFIED_LIVE_ENDPOINTS: Mapping[str, CoupangEndpoint] = MappingProxyType(
    {GET_SELLER_PRODUCT_ENDPOINT.operation: GET_SELLER_PRODUCT_ENDPOINT}
)


def verified_coupang_operation_count() -> int:
    return len(_VERIFIED_LIVE_ENDPOINTS)


@dataclass(frozen=True, slots=True)
class CoupangHmacSigner:
    clock: Callable[[], datetime]

    def authorization_headers(
        self,
        *,
        method: str,
        url: str,
        credentials: CoupangCredentials,
    ) -> dict[str, str]:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("signing clock must return a timezone-aware datetime")
        now = now.astimezone(UTC)
        signed_date = now.strftime("%y%m%dT%H%M%SZ")
        parsed = urlsplit(url)
        message = f"{signed_date}{method}{parsed.path}{parsed.query}".encode()
        signature = hmac.new(credentials.secret_key.encode(), message, hashlib.sha256).hexdigest()
        authorization = (
            "CEA algorithm=HmacSHA256, "
            f"access-key={credentials.access_key}, signed-date={signed_date}, "
            f"signature={signature}"
        )
        return {"Authorization": authorization, "X-Requested-By": credentials.vendor_id}


class CoupangReadTool(ReadTool):
    def __init__(
        self,
        *,
        credential_provider: CredentialProvider[CoupangCredentials],
        transport: HttpTransport,
        endpoints: Sequence[CoupangEndpoint],
        timeout_seconds: float = 10.0,
        retry_policy: RetryPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
        request_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        endpoint_map = {endpoint.operation: endpoint for endpoint in endpoints}
        if len(endpoint_map) != len(endpoints):
            raise ValueError("duplicate Coupang operation")
        is_production_transport = type(transport) is ProductionHttpTransport
        mode = transport.execution_mode if is_production_transport else ExecutionMode.MOCK
        if is_production_transport:
            if transport.allowed_hosts != frozenset({COUPANG_API_HOST}):
                raise ValueError("Coupang production transport has an invalid host allowlist")
            if mode is ExecutionMode.LIVE and any(
                _VERIFIED_LIVE_ENDPOINTS.get(endpoint.operation) != endpoint
                for endpoint in endpoints
            ):
                raise ValueError("Coupang LIVE mode has no verified operation contract")
        super().__init__(
            tool_name="coupang_read",
            _execution_mode=mode,
            clock=clock,
            request_id_factory=request_id_factory,
        )
        self._credential_provider = credential_provider
        self._transport = transport
        self._endpoints = endpoint_map
        self._timeout_seconds = timeout_seconds
        self._retry_policy = retry_policy or RetryPolicy()
        self._sleeper = sleeper or time.sleep
        self._signer = CoupangHmacSigner(self._now)

    def read(
        self,
        *,
        operation: str,
        parameters: Mapping[str, str],
        query: Mapping[str, str] | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> ToolResult:
        context = self._prepare_invocation(task_id=task_id, run_id=run_id)
        endpoint = self._endpoints.get(operation)
        if endpoint is None:
            return self._failure_result(
                operation,
                context,
                ToolFailure(ErrorCategory.NOT_ALLOWLISTED, "Coupang operation is not allowlisted"),
                1,
            )
        try:
            url = endpoint.build_url(parameters, query or {})
            credentials = self._credential_provider.get_credentials()
        except ToolFailure as failure:
            return self._failure_result(operation, context, failure, 1)
        except Exception:
            return self._failure_result(
                operation,
                context,
                ToolFailure(ErrorCategory.UNKNOWN, "Coupang credential lookup failed"),
                1,
            )

        def invoke() -> HttpResponse:
            headers = self._signer.authorization_headers(
                method="GET", url=url, credentials=credentials
            )
            try:
                response = self._transport.request(
                    method="GET",
                    url=url,
                    headers=headers,
                    timeout_seconds=self._timeout_seconds,
                    follow_redirects=False,
                )
            except TimeoutError as exc:
                raise ToolFailure(ErrorCategory.TIMEOUT, "Coupang read timed out", True) from exc
            except OSError as exc:
                raise ToolFailure(
                    ErrorCategory.NETWORK, "Coupang network read failed", True
                ) from exc
            except ToolFailure:
                raise
            except Exception as exc:
                raise ToolFailure(
                    ErrorCategory.UNKNOWN,
                    "Coupang read failed unexpectedly",
                ) from exc
            self._raise_for_status(response, endpoint.success_status_codes)
            if not endpoint.allows_url(response.url):
                raise ToolFailure(
                    ErrorCategory.NOT_ALLOWLISTED,
                    "Coupang redirect destination is not allowlisted",
                )
            return response

        response, failure, attempts = run_with_retry(invoke, self._retry_policy, self._sleeper)
        if failure is not None or response is None:
            return self._failure_result(operation, context, failure, attempts)  # type: ignore[arg-type]

        fetched_at = self._now()
        checksum = raw_sha256(response.body)
        try:
            parsed: Any = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._failure_result(
                operation,
                context,
                ToolFailure(ErrorCategory.MALFORMED_SOURCE, "Coupang returned malformed JSON"),
                attempts,
            )
        if not isinstance(parsed, endpoint.expected_json_type):
            return self._failure_result(
                operation,
                context,
                ToolFailure(
                    ErrorCategory.SOURCE_SCHEMA_CHANGED,
                    "Coupang response shape changed",
                ),
                attempts,
            )
        try:
            data_as_of = endpoint.extract_data_as_of(parsed)
        except ToolFailure as source_failure:
            return self._failure_result(operation, context, source_failure, attempts)
        status = ToolStatus.PARTIAL if response.status_code == 206 else ToolStatus.SUCCESS
        metadata = SourceMetadata(
            source="coupang",
            source_uri=url,
            fetched_at=fetched_at,
            data_as_of=data_as_of,
            checksum_sha256=checksum,
            content_type=response.headers.get("Content-Type"),
            http_status=response.status_code,
        )
        return ToolResult(
            tool_name=self.tool_name,
            operation=operation,
            request_id=context.request_id,
            status=status,
            execution_mode=self.execution_mode,
            task_id=context.task_id,
            run_id=context.run_id,
            source_metadata=metadata,
            raw_result=SensitiveBytes(response.body),
            parsed_result=parsed,
            attempt_count=attempts,
        )

    @staticmethod
    def _raise_for_status(response: HttpResponse, success_status_codes: tuple[int, ...]) -> None:
        status = response.status_code
        if status in success_status_codes:
            return
        if status == 401:
            raise ToolFailure(
                ErrorCategory.AUTHENTICATION,
                "Coupang authentication failed",
                http_status=status,
            )
        if status == 403:
            raise ToolFailure(
                ErrorCategory.AUTHORIZATION,
                "Coupang authorization failed",
                http_status=status,
            )
        if status == 404:
            raise ToolFailure(
                ErrorCategory.SOURCE_NOT_FOUND,
                "Coupang resource was not found",
                http_status=status,
            )
        if status == 429:
            raise ToolFailure(
                ErrorCategory.RATE_LIMIT,
                "Coupang rate limit reached",
                True,
                status,
                response.headers.get("Retry-After"),
            )
        if 500 <= status < 600:
            raise ToolFailure(
                ErrorCategory.UPSTREAM_ERROR,
                "Coupang upstream service failed",
                True,
                status,
            )
        raise ToolFailure(
            ErrorCategory.UPSTREAM_ERROR,
            "Coupang returned an unexpected HTTP status",
            http_status=status,
        )

    def _failure_result(
        self,
        operation: str,
        context: Any,
        failure: ToolFailure,
        attempts: int,
    ) -> ToolResult:
        return ToolResult(
            tool_name=self.tool_name,
            operation=operation,
            request_id=context.request_id,
            status=ToolStatus.FAILED,
            execution_mode=self.execution_mode,
            task_id=context.task_id,
            run_id=context.run_id,
            source_metadata=None,
            error=failure.to_error(attempts),
            attempt_count=attempts,
        )
