"""PHASE 3 read-only tool interfaces and typed results."""

from .base import HttpResponse, HttpTransport, ReadTool
from .checksum import raw_sha256
from .credentials import (
    BearerCredentials,
    CoupangCredentials,
    CredentialProvider,
    EnvironmentBearerCredentialProvider,
    EnvironmentCoupangCredentialProvider,
    StaticCredentialProvider,
)
from .errors import ToolFailure
from .result import (
    ErrorCategory,
    ExecutionMode,
    SensitiveBytes,
    SourceMetadata,
    ToolError,
    ToolResult,
    ToolStatus,
)
from .retry import RetryPolicy

__all__ = [
    "BearerCredentials",
    "CoupangCredentials",
    "CredentialProvider",
    "EnvironmentBearerCredentialProvider",
    "EnvironmentCoupangCredentialProvider",
    "ErrorCategory",
    "ExecutionMode",
    "HttpResponse",
    "HttpTransport",
    "ReadTool",
    "RetryPolicy",
    "SensitiveBytes",
    "SourceMetadata",
    "StaticCredentialProvider",
    "ToolError",
    "ToolFailure",
    "ToolResult",
    "ToolStatus",
    "raw_sha256",
]
