from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest

from topspeed_ai_os.tools import (
    BearerCredentials,
    ErrorCategory,
    ExecutionMode,
    HttpResponse,
    ProductionHttpTransport,
    StaticCredentialProvider,
    ToolFailure,
    ToolStatus,
    raw_sha256,
)
from topspeed_ai_os.tools.read.drive import (
    DRIVE_API_HOST,
    DRIVE_READONLY_SCOPE,
    DriveOperation,
    DriveReadTool,
    ProductionDriveClient,
)

NOW = datetime(2026, 9, 17, 0, 0, tzinfo=UTC)
REQUEST_ID = "req_" + ("e" * 32)
FILE_ID = "safe-file_123"
FAKE_TOKEN = "FAKE_PRODUCTION_TOKEN_SENTINEL"
METADATA_BODY = (
    b'{"id":"safe-file_123","name":"source.csv",'
    b'"mimeType":"text/csv","modifiedTime":"2026-09-16T00:00:00Z"}'
)
MALFORMED_METADATA_BODY = b'{"id":"safe-file_123","name":"source.csv","mimeType":"text/csv"}'


class RecordingExecutor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def http_response(*, url, status=200, body=b"raw", headers=None):
    return HttpResponse(
        status_code=status,
        headers=headers or {"Content-Type": "application/octet-stream"},
        body=body,
        url=url,
    )


def make_production_drive_tool(responses):
    executor = RecordingExecutor(responses)
    transport = ProductionHttpTransport(
        allowed_hosts=frozenset({DRIVE_API_HOST}),
        executor=executor,
    )
    client = ProductionDriveClient(transport)
    provider = StaticCredentialProvider(
        BearerCredentials(FAKE_TOKEN, frozenset({DRIVE_READONLY_SCOPE}))
    )
    tool = DriveReadTool(
        credential_provider=provider,
        client=client,
        clock=lambda: NOW,
        request_id_factory=lambda: REQUEST_ID,
    )
    return tool, executor


def test_production_http_transport_preserves_get_response_and_security_controls():
    url = "https://api-gateway.coupang.com/verified/read?id=1"
    executor = RecordingExecutor(
        [http_response(url=url, status=206, body=b"exact-raw", headers={"X-Source": "test"})]
    )
    transport = ProductionHttpTransport(
        allowed_hosts=frozenset({"api-gateway.coupang.com"}),
        executor=executor,
    )
    response = transport.request(
        method="GET",
        url=url,
        headers={"Authorization": "FAKE_SECRET_HEADER"},
        timeout_seconds=7,
        follow_redirects=False,
    )
    request = executor.requests[0]
    assert request.method == "GET"
    assert request.url == url
    assert request.timeout_seconds == 7
    assert request.follow_redirects is False
    assert "FAKE_SECRET_HEADER" not in repr(request)
    assert response.status_code == 206
    assert response.headers == {"X-Source": "test"}
    assert response.body == b"exact-raw"


@pytest.mark.parametrize(
    ("method", "url", "follow_redirects"),
    [
        ("POST", "https://api-gateway.coupang.com/read", False),
        ("GET", "http://api-gateway.coupang.com/read", False),
        ("GET", "https://api-gateway.coupang.com.evil.example/read", False),
        ("GET", "https://api-gateway.coupang.com/read", True),
        ("GET", "https://api-gateway.coupang.com/a/../read", False),
    ],
)
def test_production_http_transport_rejects_non_read_or_untrusted_target(
    method, url, follow_redirects
):
    executor = RecordingExecutor([])
    transport = ProductionHttpTransport(
        allowed_hosts=frozenset({"api-gateway.coupang.com"}),
        executor=executor,
    )
    with pytest.raises(ToolFailure) as failure:
        transport.request(
            method=method,
            url=url,
            headers={},
            timeout_seconds=1,
            follow_redirects=follow_redirects,
        )
    assert failure.value.category is ErrorCategory.NOT_ALLOWLISTED
    assert executor.requests == []


def test_production_http_transport_revalidates_response_url():
    requested = "https://api-gateway.coupang.com/read"
    executor = RecordingExecutor(
        [http_response(url="https://evil.example/read", status=302, body=b"redirect")]
    )
    transport = ProductionHttpTransport(
        allowed_hosts=frozenset({"api-gateway.coupang.com"}),
        executor=executor,
    )
    with pytest.raises(ToolFailure) as failure:
        transport.request(
            method="GET",
            url=requested,
            headers={},
            timeout_seconds=1,
            follow_redirects=False,
        )
    assert failure.value.category is ErrorCategory.NOT_ALLOWLISTED


def test_production_drive_client_with_test_executor_is_mock_mode():
    metadata_url = (
        f"https://{DRIVE_API_HOST}/drive/v3/files/{FILE_ID}"
        "?fields=id%2Cname%2CmimeType%2CmodifiedTime"
    )
    download_url = f"https://{DRIVE_API_HOST}/drive/v3/files/{FILE_ID}?alt=media"
    executor = RecordingExecutor(
        [
            http_response(
                url=metadata_url,
                body=METADATA_BODY,
                headers={"Content-Type": "application/json"},
            ),
            http_response(
                url=download_url,
                body=b"sku,value\nTS-001,1\n",
                headers={"Content-Type": "text/csv"},
            ),
        ]
    )
    transport = ProductionHttpTransport(
        allowed_hosts=frozenset({DRIVE_API_HOST}),
        executor=executor,
    )
    client = ProductionDriveClient(transport)
    provider = StaticCredentialProvider(
        BearerCredentials(FAKE_TOKEN, frozenset({DRIVE_READONLY_SCOPE}))
    )
    tool = DriveReadTool(
        credential_provider=provider,
        client=client,
        clock=lambda: NOW,
        request_id_factory=lambda: REQUEST_ID,
    )
    result = tool.read(operation=DriveOperation.DOWNLOAD_FILE, file_id=FILE_ID)
    assert result.status is ToolStatus.SUCCESS
    assert result.execution_mode is ExecutionMode.MOCK
    assert result.raw_result.reveal() == b"sku,value\nTS-001,1\n"
    assert result.source_metadata.checksum_sha256 == raw_sha256(b"sku,value\nTS-001,1\n")
    assert [request.method for request in executor.requests] == ["GET", "GET"]
    assert [request.follow_redirects for request in executor.requests] == [False, False]
    assert [request.url for request in executor.requests] == [metadata_url, download_url]
    assert all(FAKE_TOKEN not in repr(request) for request in executor.requests)
    assert FAKE_TOKEN not in repr(result)


def test_production_drive_live_mode_requires_concrete_network_executor():
    transport = ProductionHttpTransport(allowed_hosts=frozenset({DRIVE_API_HOST}))
    client = ProductionDriveClient(transport)
    provider = StaticCredentialProvider(
        BearerCredentials(FAKE_TOKEN, frozenset({DRIVE_READONLY_SCOPE}))
    )
    tool = DriveReadTool(credential_provider=provider, client=client)
    assert transport.execution_mode is ExecutionMode.LIVE
    assert client.execution_mode is ExecutionMode.LIVE
    assert tool.execution_mode is ExecutionMode.LIVE


def test_production_drive_public_surface_has_no_write_operation():
    public_actions = {
        name
        for name, member in ProductionDriveClient.__dict__.items()
        if inspect.isfunction(member) and not name.startswith("_")
    }
    assert public_actions == {"get_metadata", "download_file", "export_file"}


def test_production_get_metadata_malformed_schema_stops_after_metadata_get():
    metadata_url = (
        f"https://{DRIVE_API_HOST}/drive/v3/files/{FILE_ID}"
        "?fields=id%2Cname%2CmimeType%2CmodifiedTime"
    )
    tool, executor = make_production_drive_tool(
        [http_response(url=metadata_url, body=MALFORMED_METADATA_BODY)]
    )

    result = tool.read(operation=DriveOperation.GET_METADATA, file_id=FILE_ID)

    assert result.status is ToolStatus.FAILED
    assert result.error.category is ErrorCategory.MALFORMED_SOURCE
    assert result.error.retryable is False
    assert result.attempt_count == 1
    assert len(executor.requests) == 1
    assert executor.requests[0].method == "GET"


def test_production_metadata_http_failure_is_not_reclassified_as_schema_failure():
    metadata_url = (
        f"https://{DRIVE_API_HOST}/drive/v3/files/{FILE_ID}"
        "?fields=id%2Cname%2CmimeType%2CmodifiedTime"
    )
    tool, executor = make_production_drive_tool(
        [http_response(url=metadata_url, status=404, body=b"not-found")]
    )

    result = tool.read(operation=DriveOperation.GET_METADATA, file_id=FILE_ID)

    assert result.status is ToolStatus.FAILED
    assert result.error.category is ErrorCategory.SOURCE_NOT_FOUND
    assert result.error.http_status == 404
    assert result.attempt_count == 1
    assert len(executor.requests) == 1


def test_production_download_malformed_metadata_blocks_content_get():
    metadata_url = (
        f"https://{DRIVE_API_HOST}/drive/v3/files/{FILE_ID}"
        "?fields=id%2Cname%2CmimeType%2CmodifiedTime"
    )
    download_url = f"https://{DRIVE_API_HOST}/drive/v3/files/{FILE_ID}?alt=media"
    tool, executor = make_production_drive_tool(
        [
            http_response(url=metadata_url, body=MALFORMED_METADATA_BODY),
            http_response(url=download_url, body=b"must-not-be-consumed"),
        ]
    )

    result = tool.read(operation=DriveOperation.DOWNLOAD_FILE, file_id=FILE_ID)

    assert result.status is ToolStatus.FAILED
    assert result.error.category is ErrorCategory.MALFORMED_SOURCE
    assert result.error.retryable is False
    assert result.attempt_count == 1
    assert len(executor.requests) == 1
    assert len(executor.responses) == 1
    assert executor.requests[0].method == "GET"


def test_production_export_malformed_metadata_blocks_export_get():
    metadata_url = (
        f"https://{DRIVE_API_HOST}/drive/v3/files/{FILE_ID}"
        "?fields=id%2Cname%2CmimeType%2CmodifiedTime"
    )
    export_url = (
        f"https://{DRIVE_API_HOST}/drive/v3/files/{FILE_ID}/export?mimeType=application%2Fpdf"
    )
    tool, executor = make_production_drive_tool(
        [
            http_response(url=metadata_url, body=MALFORMED_METADATA_BODY),
            http_response(url=export_url, body=b"must-not-be-consumed"),
        ]
    )

    result = tool.read(
        operation=DriveOperation.EXPORT_FILE,
        file_id=FILE_ID,
        export_format="pdf",
    )

    assert result.status is ToolStatus.FAILED
    assert result.error.category is ErrorCategory.MALFORMED_SOURCE
    assert result.error.retryable is False
    assert result.attempt_count == 1
    assert len(executor.requests) == 1
    assert len(executor.responses) == 1
    assert executor.requests[0].method == "GET"


def test_production_drive_export_uses_allowlisted_get_url():
    metadata_url = (
        f"https://{DRIVE_API_HOST}/drive/v3/files/{FILE_ID}"
        "?fields=id%2Cname%2CmimeType%2CmodifiedTime"
    )
    export_url = (
        f"https://{DRIVE_API_HOST}/drive/v3/files/{FILE_ID}/export?mimeType=application%2Fpdf"
    )
    executor = RecordingExecutor(
        [
            http_response(url=metadata_url, body=METADATA_BODY),
            http_response(url=export_url, body=b"pdf-bytes"),
        ]
    )
    transport = ProductionHttpTransport(
        allowed_hosts=frozenset({DRIVE_API_HOST}),
        executor=executor,
    )
    response = ProductionDriveClient(transport).export_file(
        file_id=FILE_ID,
        mime_type="application/pdf",
        access_token=FAKE_TOKEN,
        timeout_seconds=3,
    )
    assert response.raw_bytes == b"pdf-bytes"
    assert [request.method for request in executor.requests] == ["GET", "GET"]
    assert [request.follow_redirects for request in executor.requests] == [False, False]
    assert [request.url for request in executor.requests] == [metadata_url, export_url]


@pytest.mark.parametrize(
    ("file_id", "mime_type", "category"),
    [
        ("../unsafe", "application/pdf", ErrorCategory.MALFORMED_INPUT),
        (FILE_ID, "text/html", ErrorCategory.UNSUPPORTED_FORMAT),
    ],
)
def test_production_drive_client_rejects_unapproved_target_before_network(
    file_id, mime_type, category
):
    executor = RecordingExecutor([])
    transport = ProductionHttpTransport(
        allowed_hosts=frozenset({DRIVE_API_HOST}),
        executor=executor,
    )
    client = ProductionDriveClient(transport)
    with pytest.raises(ToolFailure) as failure:
        client.export_file(
            file_id=file_id,
            mime_type=mime_type,
            access_token=FAKE_TOKEN,
            timeout_seconds=1,
        )
    assert failure.value.category is category
    assert executor.requests == []
