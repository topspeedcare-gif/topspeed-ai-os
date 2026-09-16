from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from topspeed_ai_os.core.ids import generate_run_id, generate_task_id
from topspeed_ai_os.tools import (
    CoupangCredentials,
    ErrorCategory,
    ExecutionMode,
    HttpResponse,
    ProductionHttpTransport,
    RetryPolicy,
    StaticCredentialProvider,
    ToolFailure,
    ToolStatus,
    raw_sha256,
)
from topspeed_ai_os.tools.read import (
    CoupangEndpoint,
    CoupangHmacSigner,
    CoupangReadTool,
    verified_coupang_operation_count,
)

NOW = datetime(2026, 9, 16, 0, 0, tzinfo=UTC)
REQUEST_ID = "req_" + ("b" * 32)
FAKE_SECRET = "FAKE_COUPANG_SECRET_SENTINEL"
FAKE_ACCESS = "FAKE_COUPANG_ACCESS_SENTINEL"
ENDPOINT = CoupangEndpoint(
    operation="coupang.get_resource",
    path_template="/mock/read/{resource_id}",
    parameter_names=("resource_id",),
    allowed_query_names=("page",),
)


class FakeTransport:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
        follow_redirects: bool,
    ) -> HttpResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "timeout": timeout_seconds,
                "follow_redirects": follow_redirects,
            }
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def response(status=200, body=b'{"items":[]}', url=None, headers=None):
    return HttpResponse(
        status,
        headers or {"Content-Type": "application/json"},
        body,
        url or "https://api-gateway.coupang.com/mock/read/abc?page=1",
    )


def make_tool(outcomes, *, endpoint=ENDPOINT, sleeps=None):
    provider = StaticCredentialProvider(CoupangCredentials(FAKE_ACCESS, FAKE_SECRET, "FAKE_VENDOR"))
    transport = FakeTransport(outcomes)
    tool = CoupangReadTool(
        credential_provider=provider,
        transport=transport,
        endpoints=(endpoint,),
        timeout_seconds=7,
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0, max_delay_seconds=0),
        clock=lambda: NOW,
        sleeper=(sleeps.append if sleeps is not None else lambda _seconds: None),
        request_id_factory=lambda: REQUEST_ID,
    )
    return tool, provider, transport


def invoke(tool, **overrides):
    kwargs = {
        "operation": "coupang.get_resource",
        "parameters": {"resource_id": "abc"},
        "query": {"page": "1"},
    }
    kwargs.update(overrides)
    return tool.read(**kwargs)


def test_approved_get_success_is_typed_and_uses_raw_checksum():
    tool, provider, transport = make_tool([response()])
    result = invoke(tool)
    assert result.status is ToolStatus.SUCCESS
    assert result.execution_mode is ExecutionMode.MOCK
    assert result.operation == "coupang.get_resource"
    assert result.request_id == REQUEST_ID
    assert result.source_metadata.data_as_of is None
    assert result.source_metadata.checksum_sha256 == raw_sha256(b'{"items":[]}')
    assert result.parsed_result == {"items": []}
    assert provider.call_count == 1
    assert transport.calls[0]["method"] == "GET"
    assert transport.calls[0]["follow_redirects"] is False
    assert transport.calls[0]["timeout"] == 7


def test_explicit_operation_data_as_of_is_preserved():
    endpoint = CoupangEndpoint(
        operation=ENDPOINT.operation,
        path_template=ENDPOINT.path_template,
        parameter_names=ENDPOINT.parameter_names,
        allowed_query_names=ENDPOINT.allowed_query_names,
        data_as_of_path=("source", "asOf"),
    )
    tool, _, _ = make_tool(
        [response(body=b'{"items":[],"source":{"asOf":"2026-09-15T23:00:00Z"}}')],
        endpoint=endpoint,
    )
    result = invoke(tool)
    assert result.status is ToolStatus.SUCCESS
    assert result.source_metadata.data_as_of == datetime(2026, 9, 15, 23, 0, tzinfo=UTC)
    assert result.source_metadata.data_as_of != result.source_metadata.fetched_at


def test_missing_or_uncontracted_timestamp_is_not_inferred():
    contracted = CoupangEndpoint(
        operation=ENDPOINT.operation,
        path_template=ENDPOINT.path_template,
        parameter_names=ENDPOINT.parameter_names,
        allowed_query_names=ENDPOINT.allowed_query_names,
        data_as_of_path=("asOf",),
    )
    missing_tool, _, _ = make_tool(
        [response(body=b'{"updatedAt":"2026-09-15T00:00:00Z"}')], endpoint=contracted
    )
    generic_tool, _, _ = make_tool([response(body=b'{"updatedAt":"2026-09-15T00:00:00Z"}')])
    assert invoke(missing_tool).source_metadata.data_as_of is None
    assert invoke(generic_tool).source_metadata.data_as_of is None


@pytest.mark.parametrize("timestamp", ["2026-09-15T23:00:00", "not-a-timestamp", 123])
def test_invalid_explicit_data_as_of_is_typed_failure(timestamp):
    endpoint = CoupangEndpoint(
        operation=ENDPOINT.operation,
        path_template=ENDPOINT.path_template,
        parameter_names=ENDPOINT.parameter_names,
        allowed_query_names=ENDPOINT.allowed_query_names,
        data_as_of_path=("asOf",),
    )
    body = (
        f'{{"items":[],"asOf":{timestamp}}}'
        if isinstance(timestamp, int)
        else f'{{"items":[],"asOf":"{timestamp}"}}'
    ).encode()
    tool, _, _ = make_tool([response(body=body)], endpoint=endpoint)
    result = invoke(tool)
    assert result.status is ToolStatus.FAILED
    assert result.error.category is ErrorCategory.MALFORMED_SOURCE


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_business_write_operations_are_not_allowlisted(method):
    tool, provider, transport = make_tool([response()])
    result = invoke(tool, operation=f"coupang.{method.lower()}")
    assert result.status is ToolStatus.FAILED
    assert result.error.category is ErrorCategory.NOT_ALLOWLISTED
    assert provider.call_count == 0
    assert transport.calls == []


@pytest.mark.parametrize(
    "resource_id",
    ["../secret", "%2e%2e", "abc/def", "https://evil.example", "abc\\def"],
)
def test_url_and_path_bypass_is_blocked_before_credentials(resource_id):
    tool, provider, transport = make_tool([response()])
    result = invoke(tool, parameters={"resource_id": resource_id})
    assert result.error.category is ErrorCategory.NOT_ALLOWLISTED
    assert provider.call_count == 0
    assert transport.calls == []


def test_query_allowlist_is_checked_before_credentials():
    tool, provider, transport = make_tool([response()])
    result = invoke(tool, query={"access_token": "secret"})
    assert result.error.category is ErrorCategory.NOT_ALLOWLISTED
    assert provider.call_count == 0
    assert transport.calls == []


def test_sensitive_query_name_cannot_be_configured():
    with pytest.raises(ValueError, match="sensitive query"):
        CoupangEndpoint(
            operation="coupang.unsafe",
            path_template="/mock/read/{resource_id}",
            parameter_names=("resource_id",),
            allowed_query_names=("access_token",),
        )


def test_exact_host_and_redirect_destination_are_enforced():
    tool, _, transport = make_tool(
        [response(url="https://api-gateway.coupang.com.evil.example/mock/read/abc?page=1")]
    )
    result = invoke(tool)
    assert result.error.category is ErrorCategory.NOT_ALLOWLISTED
    assert len(transport.calls) == 1


def test_unverified_endpoint_cannot_be_used_in_live_mode():
    provider = StaticCredentialProvider(CoupangCredentials(FAKE_ACCESS, FAKE_SECRET, "vendor"))
    with pytest.raises(TypeError):
        CoupangReadTool(
            credential_provider=provider,
            transport=FakeTransport([response()]),
            endpoints=(ENDPOINT,),
            execution_mode=ExecutionMode.LIVE,  # type: ignore[call-arg]
        )


def test_verified_endpoint_preserves_live_mode_without_mock_spoofing():
    with pytest.raises(TypeError):
        CoupangEndpoint(
            operation=ENDPOINT.operation,
            path_template=ENDPOINT.path_template,
            parameter_names=ENDPOINT.parameter_names,
            verified_live=True,  # type: ignore[call-arg]
        )


def test_production_transport_cannot_register_arbitrary_live_endpoint():
    transport = ProductionHttpTransport(
        allowed_hosts=frozenset({"api-gateway.coupang.com"}),
    )
    provider = StaticCredentialProvider(CoupangCredentials(FAKE_ACCESS, FAKE_SECRET, "vendor"))
    with pytest.raises(ValueError, match="no verified operation"):
        CoupangReadTool(
            credential_provider=provider,
            transport=transport,
            endpoints=(ENDPOINT,),
        )
    assert verified_coupang_operation_count() == 0


def test_hmac_fixture_is_deterministic():
    signer = CoupangHmacSigner(lambda: NOW)
    url = "https://api-gateway.coupang.com/mock/read/abc?page=1"
    headers = signer.authorization_headers(
        method="GET",
        url=url,
        credentials=CoupangCredentials(FAKE_ACCESS, FAKE_SECRET, "FAKE_VENDOR"),
    )
    expected_authorization = (
        "CEA algorithm=HmacSHA256, "
        "access-key=FAKE_COUPANG_ACCESS_SENTINEL, signed-date=260916T000000Z, "
        "signature=0282304f5da7894627049a0f9a6544358d50c83a7f3148bb14b48675baff4f76"
    )
    assert headers["Authorization"] == expected_authorization


class MissingCredentialProvider:
    def get_credentials(self):
        raise ToolFailure(ErrorCategory.CONFIGURATION, "credentials are not configured")


def test_credential_missing_is_typed_without_transport_call():
    transport = FakeTransport([response()])
    tool = CoupangReadTool(
        credential_provider=MissingCredentialProvider(),
        transport=transport,
        endpoints=(ENDPOINT,),
        clock=lambda: NOW,
        request_id_factory=lambda: REQUEST_ID,
    )
    result = invoke(tool)
    assert result.error.category is ErrorCategory.CONFIGURATION
    assert transport.calls == []


class UnexpectedCredentialProvider:
    def get_credentials(self):
        raise RuntimeError("FAKE_SECRET_MUST_NOT_ESCAPE")


def test_unexpected_credential_exception_is_typed_and_redacted():
    transport = FakeTransport([response()])
    tool = CoupangReadTool(
        credential_provider=UnexpectedCredentialProvider(),
        transport=transport,
        endpoints=(ENDPOINT,),
        clock=lambda: NOW,
        request_id_factory=lambda: REQUEST_ID,
    )
    result = invoke(tool)
    assert result.error.category is ErrorCategory.UNKNOWN
    assert "FAKE_SECRET_MUST_NOT_ESCAPE" not in repr(result)
    assert transport.calls == []


@pytest.mark.parametrize(
    ("status", "category", "retryable", "attempts"),
    [
        (401, ErrorCategory.AUTHENTICATION, False, 1),
        (403, ErrorCategory.AUTHORIZATION, False, 1),
        (404, ErrorCategory.SOURCE_NOT_FOUND, False, 1),
        (400, ErrorCategory.UPSTREAM_ERROR, False, 1),
        (500, ErrorCategory.UPSTREAM_ERROR, True, 3),
    ],
)
def test_http_failures_are_typed_and_bounded(status, category, retryable, attempts):
    tool, _, transport = make_tool([response(status=status)] * 3)
    result = invoke(tool)
    assert result.status is ToolStatus.FAILED
    assert result.error.category is category
    assert result.error.retryable is retryable
    assert result.attempt_count == attempts
    assert len(transport.calls) == attempts


def test_rate_limit_retries_then_succeeds_with_one_request_id():
    sleeps: list[float] = []
    tool, _, transport = make_tool(
        [response(429, headers={"Retry-After": "0"}), response()], sleeps=sleeps
    )
    result = invoke(tool)
    assert result.status is ToolStatus.SUCCESS
    assert result.attempt_count == 2
    assert result.request_id == REQUEST_ID
    assert sleeps == [0.0]
    assert len(transport.calls) == 2


def test_timeout_is_bounded_and_retryable():
    tool, _, transport = make_tool([TimeoutError(), TimeoutError(), TimeoutError()])
    result = invoke(tool)
    assert result.error.category is ErrorCategory.TIMEOUT
    assert result.attempt_count == 3
    assert len(transport.calls) == 3


def test_unexpected_transport_exception_is_typed_and_redacted():
    tool, _, transport = make_tool([RuntimeError("FAKE_SECRET_MUST_NOT_ESCAPE")])
    result = invoke(tool)
    assert result.error.category is ErrorCategory.UNKNOWN
    assert result.attempt_count == 1
    assert "FAKE_SECRET_MUST_NOT_ESCAPE" not in repr(result)
    assert len(transport.calls) == 1


def test_malformed_json_and_schema_drift_are_distinct():
    malformed_tool, _, _ = make_tool([response(body=b"not-json")])
    drift_tool, _, _ = make_tool([response(body=b"[]")])
    assert invoke(malformed_tool).error.category is ErrorCategory.MALFORMED_SOURCE
    assert invoke(drift_tool).error.category is ErrorCategory.SOURCE_SCHEMA_CHANGED


def test_partial_response_is_not_reported_as_success():
    tool, _, _ = make_tool([response(status=206)])
    assert invoke(tool).status is ToolStatus.PARTIAL


def test_task_and_run_ids_are_preserved_byte_for_byte():
    task_id = generate_task_id()
    run_id = generate_run_id()
    tool, _, _ = make_tool([response()])
    result = invoke(tool, task_id=task_id, run_id=run_id)
    assert result.task_id == task_id
    assert result.run_id == run_id


def test_invalid_correlation_ids_fail_before_credentials_and_transport():
    tool, provider, transport = make_tool([response()])
    with pytest.raises(ValueError):
        invoke(tool, task_id="invalid")
    assert provider.call_count == 0
    assert transport.calls == []


def test_secret_and_raw_payload_are_absent_from_result_repr():
    payload = b'{"private":"customer-order"}'
    tool, _, _ = make_tool([response(body=payload)])
    result = invoke(tool)
    rendered = repr(result)
    assert FAKE_SECRET not in rendered
    assert FAKE_ACCESS not in rendered
    assert "customer-order" not in rendered


def test_execution_mode_string_cannot_spoof_mock_or_live():
    provider = StaticCredentialProvider(CoupangCredentials(FAKE_ACCESS, FAKE_SECRET, "vendor"))
    with pytest.raises(TypeError):
        CoupangReadTool(
            credential_provider=provider,
            transport=FakeTransport([response()]),
            endpoints=(ENDPOINT,),
            execution_mode="LIVE",  # type: ignore[call-arg]
        )
