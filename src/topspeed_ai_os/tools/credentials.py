"""Credential adapter boundary with redacted value objects."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from .errors import ToolFailure
from .result import ErrorCategory

CredentialT = TypeVar("CredentialT")
_COUPANG_MARKETS = frozenset({"KR", "TW"})


def require_valid_coupang_market(value: str) -> str:
    if not isinstance(value, str) or value not in _COUPANG_MARKETS:
        raise ToolFailure(
            ErrorCategory.CONFIGURATION,
            "Coupang market configuration must be exactly KR or TW",
        )
    return value


class CredentialProvider(Protocol, Generic[CredentialT]):
    def get_credentials(self) -> CredentialT: ...


@dataclass(frozen=True, slots=True)
class CoupangCredentials:
    access_key: str = field(repr=False)
    secret_key: str = field(repr=False)
    vendor_id: str
    market: str = "KR"

    def __repr__(self) -> str:
        return (
            f"CoupangCredentials(<redacted>, vendor_id={self.vendor_id!r}, market={self.market!r})"
        )


@dataclass(frozen=True, slots=True)
class BearerCredentials:
    access_token: str = field(repr=False)
    scopes: frozenset[str]

    def __repr__(self) -> str:
        return f"BearerCredentials(<redacted>, scopes={sorted(self.scopes)!r})"


@dataclass(slots=True)
class StaticCredentialProvider(Generic[CredentialT]):
    credentials: CredentialT = field(repr=False)
    call_count: int = 0

    def get_credentials(self) -> CredentialT:
        self.call_count += 1
        return self.credentials


@dataclass(frozen=True, slots=True)
class EnvironmentCoupangCredentialProvider:
    environment: Mapping[str, str] = field(default_factory=lambda: os.environ, repr=False)
    access_key_name: str = "TOPSPEED_COUPANG_ACCESS_KEY"
    secret_key_name: str = "TOPSPEED_COUPANG_SECRET_KEY"
    vendor_id_name: str = "TOPSPEED_COUPANG_VENDOR_ID"
    market_name: str = "TOPSPEED_COUPANG_MARKET"

    def get_credentials(self) -> CoupangCredentials:
        values = [
            self.environment.get(self.access_key_name),
            self.environment.get(self.secret_key_name),
            self.environment.get(self.vendor_id_name),
        ]
        if not all(values):
            raise ToolFailure(
                ErrorCategory.CONFIGURATION,
                "Coupang credentials are not configured",
            )
        market = (
            "KR"
            if self.market_name not in self.environment
            else require_valid_coupang_market(self.environment[self.market_name])
        )
        return CoupangCredentials(
            values[0],
            values[1],
            values[2],
            market,  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class EnvironmentBearerCredentialProvider:
    scopes: frozenset[str]
    environment: Mapping[str, str] = field(default_factory=lambda: os.environ, repr=False)
    token_name: str = "TOPSPEED_DRIVE_ACCESS_TOKEN"

    def get_credentials(self) -> BearerCredentials:
        token = self.environment.get(self.token_name)
        if not token:
            raise ToolFailure(
                ErrorCategory.CONFIGURATION,
                "Drive credentials are not configured",
            )
        return BearerCredentials(token, self.scopes)
