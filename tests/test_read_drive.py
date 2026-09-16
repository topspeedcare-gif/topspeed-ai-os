from __future__ import annotations

from datetime import UTC, datetime

import pytest

from topspeed_ai_os.core.ids import generate_run_id, generate_task_id
from topspeed_ai_os.tools import (
    BearerCredentials,
    ErrorCategory,
    ExecutionMode,
    RetryPolicy,
    StaticCredentialProvider,
    ToolFailure,
    ToolStatus,
    raw_sha256,
)
from topspeed_ai_os.tools.read.drive import (
    DRIVE_METADATA_READONLY_SCOPE,
    DRIVE_READONLY_SCOPE,
    DriveOperation,
    DriveReadTool,
    DriveResponse,
)

NOW = datetime(2026, 9, 16, 0, 0, tzinfo=UTC)
REQUEST_ID = "req_" + ("c" * 32)
FILE_ID = "safe-file_123"
FAKE_TOKEN = "FAKE_DRIVE_TOKEN_SENTINEL"
METADATA = {
    "id": FILE_ID,
    "name": "source.xlsx",
    "mimeType": "application/octet-stream",
    "modifiedTime": "2026-09-15T12:00:00Z",
}


class FakeDriveClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def _next(self, operation, **kwargs):
        self.calls.append({"operation": operation, **kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def get_metadata(self, **kwargs):
        return self._next("metadata", **kwargs)

    def download_file(self, **kwargs):
        return self._next("download", **kwargs)

    def export_file(self, **kwargs):
        return self._next("export", **kwargs)


def drive_response(raw=b'{"id":"safe-file_123"}', metadata=None):
    return DriveResponse(raw, metadata or METADATA, "application/octet-stream", 200)


def make_tool(outcomes, scopes=None, sleeps=None):
    provider = StaticCredentialProvider(
        BearerCredentials(FAKE_TOKEN, frozenset(scopes or {DRIVE_READONLY_SCOPE}))
    )
    client = FakeDriveClient(outcomes)
    tool = DriveReadTool(
        credential_provider=provider,
        client=client,
        timeout_seconds=9,
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0, max_delay_seconds=0),
        clock=lambda: NOW,
        sleeper=(sleeps.append if sleeps is not None else lambda _seconds: None),
        request_id_factory=lambda: REQUEST_ID,
    )
    return tool, provider, client


def test_readonly_scope_metadata_read_and_source_metadata():
    tool, provider, client = make_tool([drive_response()], scopes={DRIVE_METADATA_READONLY_SCOPE})
    result = tool.read(operation=DriveOperation.GET_METADATA, file_id=FILE_ID)
    assert result.status is ToolStatus.SUCCESS
    assert result.execution_mode is ExecutionMode.MOCK
    assert result.operation == "drive.get_metadata"
    assert result.request_id == REQUEST_ID
    assert result.source_metadata.source_uri == f"drive://file/{FILE_ID}"
    assert result.source_metadata.checksum_sha256 == raw_sha256(b'{"id":"safe-file_123"}')
    assert result.parsed_result["id"] == FILE_ID
    assert provider.call_count == 1
    assert client.calls[0]["operation"] == "metadata"
    assert client.calls[0]["timeout_seconds"] == 9


def test_modified_time_is_not_inferred_as_data_as_of():
    tool, _, _ = make_tool([drive_response()])
    result = tool.read(operation=DriveOperation.GET_METADATA, file_id=FILE_ID)
    assert result.source_metadata.modified_time == "2026-09-15T12:00:00Z"
    assert result.source_metadata.data_as_of is None


def test_explicit_typed_source_data_as_of_is_preserved():
    explicit = DriveResponse(
        b'{"id":"safe-file_123"}',
        METADATA,
        source_data_as_of="2026-09-15T10:30:00+09:00",
    )
    tool, _, _ = make_tool([explicit])
    result = tool.read(operation=DriveOperation.GET_METADATA, file_id=FILE_ID)
    assert result.status is ToolStatus.SUCCESS
    assert result.source_metadata.data_as_of.isoformat() == "2026-09-15T10:30:00+09:00"
    assert result.source_metadata.modified_time == METADATA["modifiedTime"]


@pytest.mark.parametrize("timestamp", ["2026-09-15T10:30:00", "not-a-timestamp", ""])
def test_invalid_typed_source_data_as_of_is_failure(timestamp):
    response = DriveResponse(
        b'{"id":"safe-file_123"}',
        METADATA,
        source_data_as_of=timestamp,
    )
    tool, _, _ = make_tool([response])
    result = tool.read(operation=DriveOperation.GET_METADATA, file_id=FILE_ID)
    assert result.status is ToolStatus.FAILED
    assert result.error.category is ErrorCategory.MALFORMED_SOURCE


def test_raw_download_preserves_bytes_and_hides_token():
    raw = b"private-source-bytes"
    tool, _, client = make_tool([drive_response(raw)])
    result = tool.read(operation=DriveOperation.DOWNLOAD_FILE, file_id=FILE_ID)
    assert result.raw_result.reveal() == raw
    assert result.parsed_result is None
    assert FAKE_TOKEN not in repr(result)
    assert client.calls[0]["access_token"] == FAKE_TOKEN


@pytest.mark.parametrize(
    ("export_format", "mime_type"),
    [
        ("pdf", "application/pdf"),
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ("txt", "text/plain"),
    ],
)
def test_export_format_allowlist(export_format, mime_type):
    tool, _, client = make_tool([drive_response(b"export")])
    result = tool.read(
        operation=DriveOperation.EXPORT_FILE,
        file_id=FILE_ID,
        export_format=export_format,
    )
    assert result.status is ToolStatus.SUCCESS
    assert client.calls[0]["mime_type"] == mime_type


@pytest.mark.parametrize("export_format", ["html", "zip", "exe", "../pdf", None])
def test_unapproved_export_format_is_rejected_before_credentials(export_format):
    tool, provider, client = make_tool([drive_response()])
    result = tool.read(
        operation=DriveOperation.EXPORT_FILE,
        file_id=FILE_ID,
        export_format=export_format,
    )
    assert result.error.category is ErrorCategory.UNSUPPORTED_FORMAT
    assert provider.call_count == 0
    assert client.calls == []


@pytest.mark.parametrize("file_id", ["../file", "a/b", "%2e%2e", "https://evil.example"])
def test_arbitrary_url_and_unsafe_file_id_are_rejected(file_id):
    tool, provider, client = make_tool([drive_response()])
    result = tool.read(operation=DriveOperation.DOWNLOAD_FILE, file_id=file_id)
    assert result.error.category is ErrorCategory.MALFORMED_INPUT
    assert provider.call_count == 0
    assert client.calls == []


@pytest.mark.parametrize(
    "scope",
    [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive.metadata",
    ],
)
def test_write_or_broad_scope_is_rejected(scope):
    tool, _, client = make_tool([drive_response()], scopes={scope})
    result = tool.read(operation=DriveOperation.GET_METADATA, file_id=FILE_ID)
    assert result.error.category is ErrorCategory.CONFIGURATION
    assert client.calls == []


def test_metadata_only_scope_cannot_download():
    tool, _, client = make_tool([drive_response()], scopes={DRIVE_METADATA_READONLY_SCOPE})
    result = tool.read(operation=DriveOperation.DOWNLOAD_FILE, file_id=FILE_ID)
    assert result.error.category is ErrorCategory.AUTHORIZATION
    assert client.calls == []


def test_write_operation_is_not_exposed_or_accepted():
    tool, provider, client = make_tool([drive_response()])
    result = tool.read(operation="drive.delete_file", file_id=FILE_ID)  # type: ignore[arg-type]
    assert result.error.category is ErrorCategory.NOT_ALLOWLISTED
    assert provider.call_count == 0
    assert client.calls == []
    assert not hasattr(tool, "create_file")
    assert not hasattr(tool, "delete_file")


@pytest.mark.parametrize(
    ("failure", "category", "attempts"),
    [
        (
            ToolFailure(ErrorCategory.AUTHENTICATION, "auth", False, 401),
            ErrorCategory.AUTHENTICATION,
            1,
        ),
        (
            ToolFailure(ErrorCategory.AUTHORIZATION, "forbidden", False, 403),
            ErrorCategory.AUTHORIZATION,
            1,
        ),
        (
            ToolFailure(ErrorCategory.SOURCE_NOT_FOUND, "missing", False, 404),
            ErrorCategory.SOURCE_NOT_FOUND,
            1,
        ),
        (
            ToolFailure(ErrorCategory.RATE_LIMIT, "rate", True, 429, "0"),
            ErrorCategory.RATE_LIMIT,
            3,
        ),
        (
            ToolFailure(ErrorCategory.UPSTREAM_ERROR, "upstream", True, 500),
            ErrorCategory.UPSTREAM_ERROR,
            3,
        ),
    ],
)
def test_typed_client_failures_and_bounded_retry(failure, category, attempts):
    tool, _, client = make_tool([failure, failure, failure])
    result = tool.read(operation=DriveOperation.DOWNLOAD_FILE, file_id=FILE_ID)
    assert result.error.category is category
    assert result.attempt_count == attempts
    assert len(client.calls) == attempts


@pytest.mark.parametrize(
    ("status", "category", "attempts"),
    [
        (401, ErrorCategory.AUTHENTICATION, 1),
        (403, ErrorCategory.AUTHORIZATION, 1),
        (404, ErrorCategory.SOURCE_NOT_FOUND, 1),
        (429, ErrorCategory.RATE_LIMIT, 3),
        (500, ErrorCategory.UPSTREAM_ERROR, 3),
        (302, ErrorCategory.UPSTREAM_ERROR, 1),
        (201, ErrorCategory.UPSTREAM_ERROR, 1),
        (206, ErrorCategory.UPSTREAM_ERROR, 1),
    ],
)
def test_tool_maps_raw_drive_response_status_fail_closed(status, category, attempts):
    response = DriveResponse(
        b"response",
        METADATA,
        http_status=status,
        headers={"Retry-After": "0"},
    )
    tool, _, client = make_tool([response] * attempts)
    result = tool.read(operation=DriveOperation.DOWNLOAD_FILE, file_id=FILE_ID)
    assert result.status is ToolStatus.FAILED
    assert result.error.category is category
    assert result.attempt_count == attempts
    assert len(client.calls) == attempts


def test_timeout_retries_then_succeeds_with_stable_request_id():
    tool, _, client = make_tool([TimeoutError(), drive_response(b"ok")])
    result = tool.read(operation=DriveOperation.DOWNLOAD_FILE, file_id=FILE_ID)
    assert result.status is ToolStatus.SUCCESS
    assert result.attempt_count == 2
    assert result.request_id == REQUEST_ID
    assert len(client.calls) == 2


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"id": "different"},
        {"id": 123},
    ],
)
def test_malformed_metadata_is_rejected(metadata):
    tool, _, _ = make_tool([DriveResponse(b"{}", metadata)])
    result = tool.read(operation=DriveOperation.GET_METADATA, file_id=FILE_ID)
    assert result.error.category is ErrorCategory.MALFORMED_SOURCE


def test_task_and_run_ids_are_preserved():
    task_id = generate_task_id()
    run_id = generate_run_id()
    tool, _, _ = make_tool([drive_response()])
    result = tool.read(
        operation=DriveOperation.GET_METADATA,
        file_id=FILE_ID,
        task_id=task_id,
        run_id=run_id,
    )
    assert result.task_id == task_id
    assert result.run_id == run_id


def test_invalid_ids_fail_before_credentials_or_client():
    tool, provider, client = make_tool([drive_response()])
    with pytest.raises(ValueError):
        tool.read(operation=DriveOperation.GET_METADATA, file_id=FILE_ID, run_id="bad")
    assert provider.call_count == 0
    assert client.calls == []


def test_token_does_not_appear_in_error_or_result_repr():
    failure = ToolFailure(ErrorCategory.AUTHENTICATION, "Drive authentication failed", False, 401)
    tool, _, _ = make_tool([failure])
    result = tool.read(operation=DriveOperation.GET_METADATA, file_id=FILE_ID)
    assert FAKE_TOKEN not in repr(result)
    assert FAKE_TOKEN not in result.error.redacted_summary


class UnexpectedCredentialProvider:
    def get_credentials(self):
        raise RuntimeError("FAKE_TOKEN_MUST_NOT_ESCAPE")


def test_unexpected_credential_exception_is_typed_and_redacted():
    client = FakeDriveClient([drive_response()])
    tool = DriveReadTool(
        credential_provider=UnexpectedCredentialProvider(),
        client=client,
        clock=lambda: NOW,
        request_id_factory=lambda: REQUEST_ID,
    )
    result = tool.read(operation=DriveOperation.GET_METADATA, file_id=FILE_ID)
    assert result.error.category is ErrorCategory.UNKNOWN
    assert "FAKE_TOKEN_MUST_NOT_ESCAPE" not in repr(result)
    assert client.calls == []


def test_unexpected_client_exception_is_typed_and_redacted():
    tool, _, client = make_tool([RuntimeError("FAKE_TOKEN_MUST_NOT_ESCAPE")])
    result = tool.read(operation=DriveOperation.GET_METADATA, file_id=FILE_ID)
    assert result.error.category is ErrorCategory.UNKNOWN
    assert result.attempt_count == 1
    assert "FAKE_TOKEN_MUST_NOT_ESCAPE" not in repr(result)
    assert len(client.calls) == 1


def test_fake_drive_client_cannot_be_marked_live_by_constructor_override():
    provider = StaticCredentialProvider(
        BearerCredentials(FAKE_TOKEN, frozenset({DRIVE_READONLY_SCOPE}))
    )
    with pytest.raises(TypeError):
        DriveReadTool(
            credential_provider=provider,
            client=FakeDriveClient([drive_response()]),
            execution_mode=ExecutionMode.LIVE,  # type: ignore[call-arg]
        )
