"""Deterministic PHASE 4 data hub adapter primitives."""

from .adapter import (
    AD_DAILY_SCHEMA,
    AcceptedRecord,
    BatchResult,
    BatchStatus,
    ConflictRecord,
    DuplicateRecord,
    InMemoryReferencePublisher,
    MappingEntry,
    Provenance,
    ReasonCode,
    RejectedRecord,
    SourceBatch,
    ingest_ad_daily,
)
from .channel_daily import CHANNEL_DAILY_SCHEMA, DERIVE_NET_SALES_RULE, ingest_channel_daily

__all__ = [
    "AD_DAILY_SCHEMA",
    "CHANNEL_DAILY_SCHEMA",
    "DERIVE_NET_SALES_RULE",
    "AcceptedRecord",
    "BatchResult",
    "BatchStatus",
    "ConflictRecord",
    "DuplicateRecord",
    "InMemoryReferencePublisher",
    "MappingEntry",
    "Provenance",
    "ReasonCode",
    "RejectedRecord",
    "SourceBatch",
    "ingest_ad_daily",
    "ingest_channel_daily",
]
