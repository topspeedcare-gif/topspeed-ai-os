"""Source URI and error redaction helpers."""

from __future__ import annotations

from urllib.parse import unquote_plus, urlsplit, urlunsplit

_SENSITIVE_QUERY_NAMES = frozenset(
    {"access_token", "token", "authorization", "signature", "secret", "refresh_token"}
)


def sanitized_source_uri(uri: str) -> str:
    parsed = urlsplit(uri)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("source URI userinfo is not allowed")
    if parsed.query:
        for pair in parsed.query.split("&"):
            name = unquote_plus(pair.partition("=")[0]).lower()
            if name in _SENSITIVE_QUERY_NAMES:
                raise ValueError("source URI contains a sensitive query parameter")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
