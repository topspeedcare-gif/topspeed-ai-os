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

__all__ = [
    "AD_DAILY_SCHEMA",
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
]
