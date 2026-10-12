"""Deterministic calculation primitives."""

from .ad_daily_metrics import (
    AD_METRICS_FORMULA_VERSION,
    AdvertisingMetricOutput,
    AdvertisingMetricsError,
    AdvertisingMetricsInputRef,
    AdvertisingMetricsResult,
    calculate_ad_daily_metrics,
)
from .contribution_margin import (
    CONTRIBUTION_MARGIN_FORMULA_VERSION,
    CONTRIBUTION_MARGIN_METRIC,
    CalculationError,
    CalculationInputRef,
    CalculationOutput,
    CalculationResult,
    UnsupportedFormulaVersionError,
    calculate_product_master_contribution_margin,
)
from .inventory_demand_velocity import (
    INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION,
    InventoryDemandVelocityError,
    InventoryDemandVelocityInputRef,
    InventoryDemandVelocityOutput,
    InventoryDemandVelocityResult,
    calculate_inventory_demand_velocity,
)

# Approved public API order is normative.
# ruff: ignore[RUF022]
__all__ = [
    "AD_METRICS_FORMULA_VERSION",
    "AdvertisingMetricOutput",
    "AdvertisingMetricsError",
    "AdvertisingMetricsInputRef",
    "AdvertisingMetricsResult",
    "CONTRIBUTION_MARGIN_FORMULA_VERSION",
    "CONTRIBUTION_MARGIN_METRIC",
    "CalculationError",
    "CalculationInputRef",
    "CalculationOutput",
    "CalculationResult",
    "UnsupportedFormulaVersionError",
    "calculate_ad_daily_metrics",
    "calculate_product_master_contribution_margin",
    "INVENTORY_DEMAND_VELOCITY_FORMULA_VERSION",
    "InventoryDemandVelocityError",
    "InventoryDemandVelocityInputRef",
    "InventoryDemandVelocityOutput",
    "InventoryDemandVelocityResult",
    "calculate_inventory_demand_velocity",
]
