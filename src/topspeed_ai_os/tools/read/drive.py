"""Operation-based Google Drive Source reader with read-only scopes."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from ..base import ReadTool
from ..checksum import raw_sha256
from ..credentials import BearerCredentials, CredentialProvider
from ..errors import ToolFailure
from ..result import (
    ErrorCategory,
    ExecutionMode,
    SensitiveBytes,
    SourceMetadata,
    ToolResult,
    ToolStatus,
)
from ..retry import RetryPolicy, run_with_retry

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DRIVE_METADATA_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.metadata.readonly"
_ALLOWED_SCOPES = frozenset({DRIVE_READONLY_SCOPE, DRIVE_METADATA_READONLY_SCOPE})
_FILE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_EXPORT_FORMATS = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt": "text/plain",
}


class DriveOperation(StrEnum):
    GET_METADATA = "drive.get_metadata"
    DOWNLOAD_FILE = "drive.download_file"
    EXPORT_FILE = "drive.export_file"


@dataclass(frozen=True, slots=True)
class DriveResponse:
    raw_bytes: bytes
    metadata: Mapping[str, Any]
    content_type: str | None = None
    http_status: int = 200


class DriveClient(Protocol):
    def get_metadata(
        self, *, file_id: str, access_token: str, timeout_seconds: float
    ) -> DriveResponse: ...

    def download_file(
        self, *, file_id: str, access_token: str, timeout_seconds: float
    ) -> DriveResponse: ...

    def export_file(
        self,
        *,
        file_id: str,
        mime_type: str,
        access_token: str,
        timeout_seconds: float,
    ) -> DriveResponse: ...


class DriveReadTool(ReadTool):
    def __init__(
        self,
        *,
        credential_provider: CredentialProvider[BearerCredentials],
        client: DriveClient,
        execution_mode: ExecutionMode,
        timeout_seconds: float = 10.0,
        retry_policy: RetryPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
        request_id_factory: Callable[[], str] | None = None,
    ) -> None:
        super().__init__(
            tool_name="drive_read",
            execution_mode=execution_mode,
            clock=clock,
            request_id_factory=request_id_factory,
        )
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._credential_provider = credential_provider
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._retry_policy = retry_policy or RetryPolicy()
        self._sleeper = sleeper or time.sleep

    def read(
        self,
        *,
        operation: DriveOperation,
        file_id: str,
        export_format: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> ToolResult:
        context = self._prepare_invocation(task_id=task_id, run_id=run_id)
        if not isinstance(operation, DriveOperation):
            return self._failed(
                str(operation),
                context,
                ToolFailure(ErrorCategory.NOT_ALLOWLISTED, "Drive operation is not allowlisted"),
                1,
            )
        if _FILE_ID.fullmatch(file_id) is None:
            return self._failed(
                operation.value,
                context,
                ToolFailure(ErrorCategory.MALFORMED_INPUT, "Invalid Drive file identifier"),
                1,
            )
        if operation is DriveOperation.EXPORT_FILE and export_format not in _EXPORT_FORMATS:
            return self._failed(
                operation.value,
                context,
                ToolFailure(ErrorCategory.UNSUPPORTED_FORMAT, "Drive export format is not allowed"),
                1,
            )
        try:
            credentials = self._credential_provider.get_credentials()
            self._validate_scopes(credentials, operation)
        except ToolFailure as failure:
            return self._failed(operation.value, context, failure, 1)
        except Exception:
            return self._failed(
                operation.value,
                context,
                ToolFailure(ErrorCategory.UNKNOWN, "Drive credential lookup failed"),
                1,
            )

        def invoke() -> DriveResponse:
            try:
                if operation is DriveOperation.GET_METADATA:
                    return self._client.get_metadata(
                        file_id=file_id,
                        access_token=credentials.access_token,
                        timeout_seconds=self._timeout_seconds,
                    )
                if operation is DriveOperation.DOWNLOAD_FILE:
                    return self._client.download_file(
                        file_id=file_id,
                        access_token=credentials.access_token,
                        timeout_seconds=self._timeout_seconds,
                    )
                return self._client.export_file(
                    file_id=file_id,
                    mime_type=_EXPORT_FORMATS[export_format],  # type: ignore[index]
                    access_token=credentials.access_token,
                    timeout_seconds=self._timeout_seconds,
                )
            except TimeoutError as exc:
                raise ToolFailure(ErrorCategory.TIMEOUT, "Drive read timed out", True) from exc
            except OSError as exc:
                raise ToolFailure(ErrorCategory.NETWORK, "Drive network read failed", True) from exc
            except ToolFailure:
                raise
            except Exception as exc:
                raise ToolFailure(
                    ErrorCategory.UNKNOWN,
                    "Drive read failed unexpectedly",
                ) from exc

        response, failure, attempts = run_with_retry(invoke, self._retry_policy, self._sleeper)
        if failure is not None or response is None:
            return self._failed(operation.value, context, failure, attempts)  # type: ignore[arg-type]
        fetched_at = self._now()
        checksum = raw_sha256(response.raw_bytes)
        metadata = dict(response.metadata)
        if not isinstance(metadata.get("id"), str) or metadata.get("id") != file_id:
            return self._failed(
                operation.value,
                context,
                ToolFailure(ErrorCategory.MALFORMED_SOURCE, "Drive metadata is malformed"),
                attempts,
            )
        source_metadata = SourceMetadata(
            source="google_drive",
            source_uri=f"drive://file/{file_id}",
            fetched_at=fetched_at,
            data_as_of=None,
            checksum_sha256=checksum,
            content_type=response.content_type or metadata.get("mimeType"),
            http_status=response.http_status,
            modified_time=metadata.get("modifiedTime"),
            source_specific_metadata={"name": metadata.get("name")},
        )
        parsed: Any = metadata if operation is DriveOperation.GET_METADATA else None
        return ToolResult(
            tool_name=self.tool_name,
            operation=operation.value,
            request_id=context.request_id,
            status=ToolStatus.SUCCESS,
            execution_mode=self.execution_mode,
            task_id=context.task_id,
            run_id=context.run_id,
            source_metadata=source_metadata,
            raw_result=SensitiveBytes(response.raw_bytes),
            parsed_result=parsed,
            attempt_count=attempts,
        )

    @staticmethod
    def _validate_scopes(credentials: BearerCredentials, operation: DriveOperation) -> None:
        if not credentials.scopes or not credentials.scopes.issubset(_ALLOWED_SCOPES):
            raise ToolFailure(
                ErrorCategory.CONFIGURATION,
                "Drive credential scopes are not read-only",
            )
        if (
            operation is not DriveOperation.GET_METADATA
            and DRIVE_READONLY_SCOPE not in credentials.scopes
        ):
            raise ToolFailure(
                ErrorCategory.AUTHORIZATION,
                "Drive credential lacks file read scope",
            )

    def _failed(
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
