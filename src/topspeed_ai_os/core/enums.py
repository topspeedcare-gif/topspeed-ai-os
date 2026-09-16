"""Enums frozen by Architecture Freeze v1 and Data Contract v1."""

from enum import StrEnum


class Skill(StrEnum):
    SOURCING = "sourcing"
    LAUNCH = "launch"
    ADS_OPS = "ads_ops"
    CONTENT = "content"
    INVENTORY = "inventory"
    DATA = "data"


class AuditStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class ResultStatus(StrEnum):
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Stage(StrEnum):
    SOURCE = "SOURCE"
    TEST = "TEST"
    SCALE = "SCALE"
    CORE = "CORE"
    EXIT = "EXIT"


class Grade(StrEnum):
    S = "S"
    A = "A"
    B = "B"
    T = "T"
    X = "X"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ProductStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"


class VerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class AssetType(StrEnum):
    COPY = "COPY"
    IMAGE_BRIEF = "IMAGE_BRIEF"
    IMAGE = "IMAGE"
    DETAIL_PAGE = "DETAIL_PAGE"
    AD_CREATIVE = "AD_CREATIVE"


class AssetStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"
