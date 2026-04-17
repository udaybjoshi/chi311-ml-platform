"""Centralised configuration for the Chicago 311 platform.

All notebook code and DLT pipeline SQL resolve their catalog/schema/volume
names through this module (or its Databricks-widget equivalents) so the
whole stack can be retargeted with a single environment variable.

Defaults match Databricks Free Edition (`workspace` catalog).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict


DEFAULT_CATALOG = "workspace"


@dataclass(frozen=True)
class Chi311Paths:
    """Resolved catalog / schema / volume / table paths for the project."""

    catalog: str = DEFAULT_CATALOG

    @property
    def schemas(self) -> Dict[str, str]:
        return {
            name: f"{self.catalog}.{name}"
            for name in ("raw", "bronze", "silver", "gold", "ml")
        }

    # --- Volumes ---------------------------------------------------------
    @property
    def landing_volume(self) -> str:
        return f"/Volumes/{self.catalog}/raw/chi311_landing"

    @property
    def landing_initial(self) -> str:
        return f"{self.landing_volume}/initial"

    @property
    def landing_incremental(self) -> str:
        return f"{self.landing_volume}/incremental"

    @property
    def landing_archive(self) -> str:
        return f"{self.landing_volume}/archive"

    @property
    def bronze_checkpoint(self) -> str:
        return f"/Volumes/{self.catalog}/bronze/chi311_checkpoint"

    @property
    def autoloader_checkpoint(self) -> str:
        return f"{self.bronze_checkpoint}/autoloader"

    @property
    def autoloader_schema(self) -> str:
        return f"{self.bronze_checkpoint}/schema"

    @property
    def ml_models(self) -> str:
        return f"/Volumes/{self.catalog}/ml/chi311_models"

    # --- Tables ----------------------------------------------------------
    @property
    def tables(self) -> Dict[str, str]:
        c = self.catalog
        return {
            "bronze_raw": f"{c}.bronze.bronze_raw_311_requests",
            "bronze_staged": f"{c}.bronze.bronze_staged_311_requests",
            "silver_scd2": f"{c}.silver.silver_scd2_311_requests",
            "silver_current": f"{c}.silver.silver_current_311_requests",
            "silver_status_history": f"{c}.silver.silver_status_history",
            "gold_daily": f"{c}.gold.gold_daily_aggregates",
            "gold_ward_daily": f"{c}.gold.gold_ward_daily_summary",
            "gold_citywide": f"{c}.gold.gold_citywide_daily_summary",
            "gold_status_transitions": f"{c}.gold.gold_status_transitions",
            "gold_department": f"{c}.gold.gold_department_performance",
            "gold_sr_type": f"{c}.gold.gold_sr_type_summary",
            "ml_predictions": f"{c}.ml.chi311_predictions",
            "ml_anomalies": f"{c}.ml.chi311_anomalies",
        }


def from_env(env: Dict[str, str] | None = None) -> Chi311Paths:
    """Build a Chi311Paths from an env-like mapping (defaults to os.environ).

    Reads CHI311_CATALOG if present.
    """
    source = os.environ if env is None else env
    return Chi311Paths(catalog=source.get("CHI311_CATALOG", DEFAULT_CATALOG))
