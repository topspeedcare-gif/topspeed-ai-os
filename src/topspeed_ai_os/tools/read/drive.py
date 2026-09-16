"""Operation-based Google Drive Source reader with read-only scopes."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import urlencode

from ..base import HttpResponse, ReadTool
from ..checksum import raw_sha256
from ..credentials import BearerCredentials, CredentialProvider
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

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DRIVE_METADATA_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.metadata.readonly"
DRIVE_API_HOST = "www.googleapis.com"
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
    headers: Mapping[str, str] = field(default_factory=dict)
    source_data_as_of: str | None = None


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


class ProductionDriveClient:
    """Concrete GET-only client for the documented Google Drive read surface."""

    __slots__ = ("_transport",)

    def __init__(self, transport: ProductionHttpTransport) -> None:
        if type(transport) is not ProductionHttpTransport:
            raise TypeError("ProductionDriveClient requires ProductionHttpTransport")
        if transport.allowed_hosts != frozenset({DRIVE_API_HOST}):
            raise ValueError("Drive production transport has an invalid host allowlist")
        self._transport = transport

    @property
    def execution_mode(self) -> ExecutionMode:
        return self._transport.execution_mode

    def get_metadata(
        self, *, file_id: str, access_token: str, timeout_seconds: float
    ) -> DriveResponse:
        self._require_file_id(file_id)
        query = urlencode({"fields": "id,name,mimeType,modifiedTime"})
        response = self._get(
            f"https://{DRIVE_API_HOST}/drive/v3/files/{file_id}?{query}",
            access_token,
            timeout_seconds,
        )
        return DriveResponse(
            raw_bytes=response.body,
            metadata=self._decode_metadata(response.body) if response.status_code == 200 else {},
            content_type=response.headers.get("Content-Type"),
            http_status=response.status_code,
            headers=response.headers,
        )

    def download_file(
        self, *, file_id: str, access_token: str, timeout_seconds: float
    ) -> DriveResponse:
        self._require_file_id(file_id)
        metadata_response = self.get_metadata(
            file_id=file_id,
            access_token=access_token,
            timeout_seconds=timeout_seconds,
        )
        if metadata_response.http_status != 200:
            return metadata_response
        response = self._get(
            f"https://{DRIVE_API_HOST}/drive/v3/files/{file_id}?alt=media",
            access_token,
            timeout_seconds,
        )
        return DriveResponse(
            raw_bytes=response.body,
            metadata=metadata_response.metadata,
            content_type=response.headers.get("Content-Type"),
            http_status=response.status_code,
            headers=response.headers,
        )

    def export_file(
        self,
        *,
        file_id: str,
        mime_type: str,
        access_token: str,
        timeout_seconds: float,
    ) -> DriveResponse:
        self._require_file_id(file_id)
        if mime_type not in _EXPORT_FORMATS.values():
            raise ToolFailure(
                ErrorCategory.UNSUPPORTED_FORMAT,
                "Drive export MIME type is not allowlisted",
            )
        metadata_response = self.get_metadata(
            file_id=file_id,
            access_token=access_token,
            timeout_seconds=timeout_seconds,
        )
        if metadata_response.http_status != 200:
            return metadata_response
        query = urlencode({"mimeType": mime_type})
        response = self._get(
            f"https://{DRIVE_API_HOST}/drive/v3/files/{file_id}/export?{query}",
            access_token,
            timeout_seconds,
        )
        return DriveResponse(
            raw_bytes=response.body,
            metadata=metadata_response.metadata,
            content_type=response.headers.get("Content-Type"),
            http_status=response.status_code,
            headers=response.headers,
        )

    def _get(self, url: str, access_token: str, timeout_seconds: float) -> HttpResponse:
        return self._transport.request(
            method="GET",
            url=url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout_seconds=timeout_seconds,
            follow_redirects=False,
        )

    @staticmethod
    def _decode_metadata(raw_bytes: bytes) -> Mapping[str, Any]:
        try:
            parsed = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _require_file_id(file_id: str) -> None:
        if _FILE_ID.fullmatch(file_id) is None:
            raise ToolFailure(
                ErrorCategory.MALFORMED_INPUT,
                "Invalid Drive file identifier",
            )

    def __repr__(self) -> str:
        return "ProductionDriveClient(<redacted transport>)"


class DriveReadTool(ReadTool):
    def __init__(
        self,
        *,
        credential_provider: CredentialProvider[BearerCredentials],
        client: DriveClient,
        timeout_seconds: float = 10.0,
        retry_policy: RetryPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
        request_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        mode = (
            client.execution_mode if type(client) is ProductionDriveClient else ExecutionMode.MOCK
        )
        super().__init__(
            tool_name="drive_read",
            _execution_mode=mode,
            clock=clock,
            request_id_factory=request_id_factory,
        )
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
                    response = self._client.get_metadata(
                        file_id=file_id,
                        access_token=credentials.access_token,
                        timeout_seconds=self._timeout_seconds,
                    )
                elif operation is DriveOperation.DOWNLOAD_FILE:
                    response = self._client.download_file(
                        file_id=file_id,
                        access_token=credentials.access_token,
                        timeout_seconds=self._timeout_seconds,
                    )
                else:
                    response = self._client.export_file(
                        file_id=file_id,
                        mime_type=_EXPORT_FORMATS[export_format],  # type: ignore[index]
                        access_token=credentials.access_token,
                        timeout_seconds=self._timeout_seconds,
                    )
                self._raise_for_status(response)
                return response
            except ToolFailure:
                raise
            except TimeoutError as exc:
                raise ToolFailure(ErrorCategory.TIMEOUT, "Drive read timed out", True) from exc
            except OSError as exc:
                raise ToolFailure(ErrorCategory.NETWORK, "Drive network read failed", True) from exc
            except Exception as exc:
                raise ToolFailure(
                    ErrorCategory.UNKNOWN,
                    "Drive read failed unexpectedly",
                ) from exc

        response, failure, attempts = run_with_retry(invoke, self._retry_policy, self._sleeper)
        if failure is not None or response is None:
            return self._failed(operation.value, context, failure, attempts)  # type: ignore[arg-type]
        fetched_at = self._now()
        if not isinstance(response.raw_bytes, bytes):
            return self._failed(
                operation.value,
                context,
                ToolFailure(ErrorCategory.MALFORMED_SOURCE, "Drive response body is malformed"),
                attempts,
            )
        checksum = raw_sha256(response.raw_bytes)
        try:
            metadata = dict(response.metadata)
        except (TypeError, ValueError):
            metadata = {}
        if not isinstance(metadata.get("id"), str) or metadata.get("id") != file_id:
            return self._failed(
                operation.value,
                context,
                ToolFailure(ErrorCategory.MALFORMED_SOURCE, "Drive metadata is malformed"),
                attempts,
            )
        if operation is DriveOperation.GET_METADATA and not response.raw_bytes:
            return self._failed(
                operation.value,
                context,
                ToolFailure(ErrorCategory.MALFORMED_SOURCE, "Drive metadata body is empty"),
                attempts,
            )
        try:
            data_as_of = (
                parse_source_data_as_of(response.source_data_as_of)
                if response.source_data_as_of is not None
                else None
            )
        except ValueError:
            return self._failed(
                operation.value,
                context,
                ToolFailure(ErrorCategory.MALFORMED_SOURCE, "Drive data_as_of is invalid"),
                attempts,
            )
        source_metadata = SourceMetadata(
            source="google_drive",
            source_uri=f"drive://file/{file_id}",
            fetched_at=fetched_at,
            data_as_of=data_as_of,
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
    def _raise_for_status(response: DriveResponse) -> None:
        status = response.http_status
        if status == 200:
            return
        if status == 401:
            raise ToolFailure(
                ErrorCategory.AUTHENTICATION,
                "Drive authentication failed",
                http_status=status,
            )
        if status == 403:
            raise ToolFailure(
                ErrorCategory.AUTHORIZATION,
                "Drive authorization failed",
                http_status=status,
            )
        if status == 404:
            raise ToolFailure(
                ErrorCategory.SOURCE_NOT_FOUND,
                "Drive file was not found",
                http_status=status,
            )
        if status == 429:
            raise ToolFailure(
                ErrorCategory.RATE_LIMIT,
                "Drive rate limit reached",
                True,
                status,
                response.headers.get("Retry-After"),
            )
        if 500 <= status < 600:
            raise ToolFailure(
                ErrorCategory.UPSTREAM_ERROR,
                "Drive upstream service failed",
                True,
                status,
            )
        if 300 <= status < 400:
            raise ToolFailure(
                ErrorCategory.UPSTREAM_ERROR,
                "Drive redirect response was rejected",
                http_status=status,
            )
        raise ToolFailure(
            ErrorCategory.UPSTREAM_ERROR,
            "Drive returned an unexpected HTTP status",
            http_status=status,
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
