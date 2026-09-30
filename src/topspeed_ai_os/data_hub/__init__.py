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
from .inventory import INVENTORY_SCHEMA, ingest_inventory
from .product_fact import PRODUCT_FACT_SCHEMA, ingest_product_fact
from .product_master import PRODUCT_MASTER_SCHEMA, ingest_product_master

__all__ = [
    "AD_DAILY_SCHEMA",
    "CHANNEL_DAILY_SCHEMA",
    "DERIVE_NET_SALES_RULE",
    "INVENTORY_SCHEMA",
    "PRODUCT_FACT_SCHEMA",
    "PRODUCT_MASTER_SCHEMA",
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
    "ingest_inventory",
    "ingest_product_fact",
    "ingest_product_master",
]
