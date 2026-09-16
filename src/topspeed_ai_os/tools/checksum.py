"""Checksum helpers for raw Source bytes."""

from __future__ import annotations

import hashlib


def raw_sha256(raw_bytes: bytes) -> str:
    """Hash the exact bytes acquired from the Source."""

    if not isinstance(raw_bytes, bytes):
        raise TypeError("raw_bytes must be bytes")
    return f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"
