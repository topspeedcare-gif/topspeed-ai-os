from __future__ import annotations

from datetime import UTC, datetime

import pytest

from topspeed_ai_os.tools import (
    ErrorCategory,
    ExecutionMode,
    RetryPolicy,
    SensitiveBytes,
    SourceMetadata,
    ToolError,
    ToolResult,
    ToolStatus,
    raw_sha256,
)
from topspeed_ai_os.tools.credentials import BearerCredentials, CoupangCredentials
from topspeed_ai_os.tools.errors import ToolFailure
from topspeed_ai_os.tools.redaction import sanitized_source_uri
from topspeed_ai_os.tools.retry import run_with_retry

NOW = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)
REQUEST_ID = "req_" + ("a" * 32)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (b"same", b"same"),
        (b"\xef\xbb\xbfvalue", b"value"),
        (b"a\nb\n", b"a\r\nb\r\n"),
        (b"xlsx-a", b"xlsx-b"),
    ],
)
def test_raw_checksum_is_byte_exact(left, right):
    left_hash = raw_sha256(left)
    right_hash = raw_sha256(right)
    if left == right:
        assert left_hash == right_hash
    else:
        assert left_hash != right_hash
    assert left_hash.startswith("sha256:")
    assert len(left_hash) == 71
    assert left_hash == left_hash.lower()


def test_sensitive_bytes_and_tool_result_repr_hide_payload():
    secret_payload = b"customer-order-private-value"
    result = ToolResult(
        tool_name="test_read",
        operation="test.read",
        request_id=REQUEST_ID,
        status=ToolStatus.SUCCESS,
        execution_mode=ExecutionMode.MOCK,
        task_id=None,
        run_id=None,
        source_metadata=SourceMetadata(
            source="test",
            source_uri="test://source/1",
            fetched_at=NOW,
            data_as_of=None,
            checksum_sha256=raw_sha256(secret_payload),
        ),
        raw_result=SensitiveBytes(secret_payload),
        parsed_result={"private": "value"},
    )
    assert secret_payload.decode() not in repr(result)
    assert "private" not in repr(result)
    assert result.raw_result.reveal() == secret_payload


def test_credential_repr_is_redacted():
    coupang = CoupangCredentials("FAKE_ACCESS", "FAKE_SECRET", "vendor")
    bearer = BearerCredentials("FAKE_TOKEN", frozenset({"readonly"}))
    assert "FAKE_ACCESS" not in repr(coupang)
    assert "FAKE_SECRET" not in repr(coupang)
    assert "FAKE_TOKEN" not in repr(bearer)


def test_source_metadata_requires_aware_fetched_at():
    with pytest.raises(ValueError, match="timezone-aware"):
        SourceMetadata(
            source="test",
            source_uri="test://source/1",
            fetched_at=datetime(2026, 9, 16),
            data_as_of=None,
            checksum_sha256=raw_sha256(b"x"),
        )


def test_source_metadata_does_not_infer_data_as_of():
    metadata = SourceMetadata(
        source="test",
        source_uri="test://source/1",
        fetched_at=NOW,
        data_as_of=None,
        checksum_sha256=raw_sha256(b"x"),
        modified_time="2026-09-15T00:00:00Z",
    )
    assert metadata.data_as_of is None
    assert metadata.modified_time == "2026-09-15T00:00:00Z"


def test_tool_result_enforces_status_error_relationship():
    error = ToolError(ErrorCategory.UNKNOWN, "safe", False)
    with pytest.raises(ValueError, match="requires an error"):
        ToolResult(
            "test",
            "test.read",
            REQUEST_ID,
            ToolStatus.FAILED,
            ExecutionMode.MOCK,
            None,
            None,
            None,
        )
    with pytest.raises(ValueError, match="cannot contain"):
        ToolResult(
            "test",
            "test.read",
            REQUEST_ID,
            ToolStatus.SUCCESS,
            ExecutionMode.MOCK,
            None,
            None,
            None,
            error=error,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "SUCCESS"), ("execution_mode", "MOCK")],
)
def test_tool_result_rejects_string_enum_spoofing(field, value):
    arguments = {
        "tool_name": "test",
        "operation": "test.read",
        "request_id": REQUEST_ID,
        "status": ToolStatus.SUCCESS,
        "execution_mode": ExecutionMode.MOCK,
        "task_id": None,
        "run_id": None,
        "source_metadata": SourceMetadata(
            source="test",
            source_uri="test://source/1",
            fetched_at=NOW,
            data_as_of=None,
            checksum_sha256=raw_sha256(b"x"),
        ),
    }
    arguments[field] = value
    with pytest.raises(TypeError):
        ToolResult(**arguments)


def test_retry_policy_is_bounded_and_uses_retry_after_without_real_sleep():
    attempts = 0
    sleeps: list[float] = []

    def operation():
        nonlocal attempts
        attempts += 1
        raise ToolFailure(
            ErrorCategory.RATE_LIMIT,
            "rate limited",
            True,
            429,
            "999999",
        )

    value, failure, count = run_with_retry(
        operation,
        RetryPolicy(max_attempts=3, base_delay_seconds=0.25, max_delay_seconds=0.5),
        sleeps.append,
    )
    assert value is None
    assert failure.category is ErrorCategory.RATE_LIMIT
    assert count == attempts == 3
    assert sleeps == [0.25, 0.5]


@pytest.mark.parametrize(
    "uri",
    [
        "https://user@example.com/file",
        "https://example.com/file?token=secret",
        "https://example.com/file?signature=secret",
        "https://example.com/file?to%6ben=secret",
    ],
)
def test_sensitive_source_uri_is_rejected(uri):
    with pytest.raises(ValueError):
        sanitized_source_uri(uri)


def test_source_uri_fragment_is_removed_without_changing_safe_query():
    assert (
        sanitized_source_uri("https://example.com/file?page=1#fragment")
        == "https://example.com/file?page=1"
    )
