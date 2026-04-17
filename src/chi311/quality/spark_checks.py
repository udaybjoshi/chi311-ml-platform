"""Lightweight Spark-native data-quality checks.

Rationale: Great Expectations works on Databricks but is heavy-weight
relative to Free Edition's serverless limits, and its Spark backend has
ergonomics issues on UC-enabled workspaces. These helpers cover the same
bronze/silver invariants the old GE notebook asserted, as pure Spark SQL,
so we can:
  - Run them on serverless with no extra dependencies.
  - Unit-test them against a local SparkSession.
  - Keep the GE notebook/assets for reference and optional richer runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional

from pyspark.sql import DataFrame, functions as F


@dataclass(frozen=True)
class QualityCheck:
    name: str
    description: str
    # A predicate that receives the DataFrame and returns the count of
    # rows violating the rule. Zero means pass.
    violation_count: Callable[[DataFrame], int]
    severity: str = "critical"  # "critical" | "warning" | "info"


@dataclass(frozen=True)
class QualityResult:
    check: QualityCheck
    total_rows: int
    violations: int

    @property
    def passed(self) -> bool:
        return self.violations == 0

    @property
    def violation_rate(self) -> float:
        return 0.0 if self.total_rows == 0 else self.violations / self.total_rows

    def to_dict(self) -> dict:
        return {
            "name": self.check.name,
            "description": self.check.description,
            "severity": self.check.severity,
            "total_rows": self.total_rows,
            "violations": self.violations,
            "violation_rate": self.violation_rate,
            "passed": self.passed,
        }


# ---------------------------------------------------------------------------
# Reusable predicate builders
# ---------------------------------------------------------------------------


def _null_count(df: DataFrame, column: str) -> int:
    return df.where(F.col(column).isNull()).count()


def _not_in_set_count(df: DataFrame, column: str, values: Iterable[str]) -> int:
    return df.where(~F.col(column).isin(list(values)) | F.col(column).isNull()).count()


def _out_of_range_count(
    df: DataFrame, column: str, min_value: float, max_value: float
) -> int:
    col = F.col(column).cast("double")
    return df.where(
        col.isNotNull() & ((col < F.lit(min_value)) | (col > F.lit(max_value)))
    ).count()


def _duplicate_count(df: DataFrame, column: str) -> int:
    dupes = (
        df.where(F.col(column).isNotNull())
        .groupBy(column)
        .agg(F.count("*").alias("n"))
        .where(F.col("n") > 1)
        .agg(F.coalesce(F.sum(F.col("n") - 1), F.lit(0)).alias("dupes"))
        .collect()[0]["dupes"]
    )
    return int(dupes)


# ---------------------------------------------------------------------------
# Check suites
# ---------------------------------------------------------------------------


def bronze_checks() -> List[QualityCheck]:
    """Checks for the staged-bronze / bronze_raw DataFrame (pre-SCD2)."""
    return [
        QualityCheck(
            "bronze.sr_number_not_null",
            "sr_number must not be null in Bronze.",
            lambda df: _null_count(df, "sr_number"),
        ),
        QualityCheck(
            "bronze.created_date_not_null",
            "created_date must not be null in Bronze.",
            lambda df: _null_count(df, "created_date"),
        ),
        QualityCheck(
            "bronze.sr_type_not_null",
            "sr_type must not be null in Bronze.",
            lambda df: _null_count(df, "sr_type"),
        ),
        QualityCheck(
            "bronze.status_not_null",
            "status must not be null in Bronze.",
            lambda df: _null_count(df, "status"),
        ),
        QualityCheck(
            "bronze.status_in_known_values",
            "status must be one of OPEN / COMPLETED / CANCELED after staging.",
            lambda df: _not_in_set_count(df, "status", ("OPEN", "COMPLETED", "CANCELED")),
        ),
        QualityCheck(
            "bronze.ward_in_range",
            "ward must be in [1, 50] when present.",
            lambda df: _out_of_range_count(df, "ward", 1, 50),
            severity="warning",
        ),
        QualityCheck(
            "bronze.sr_number_unique",
            "sr_number must be unique in a single batch (post-dedup).",
            lambda df: _duplicate_count(df, "sr_number"),
            severity="warning",
        ),
    ]


def silver_checks() -> List[QualityCheck]:
    """Stricter checks for silver_current_311_requests."""
    return [
        QualityCheck(
            "silver.sr_number_not_null",
            "sr_number must not be null in Silver.",
            lambda df: _null_count(df, "sr_number"),
        ),
        QualityCheck(
            "silver.ward_not_null",
            "ward must not be null in Silver.",
            lambda df: _null_count(df, "ward"),
        ),
        QualityCheck(
            "silver.status_in_canonical_set",
            "status must be OPEN / COMPLETED / CANCELED.",
            lambda df: _not_in_set_count(df, "status", ("OPEN", "COMPLETED", "CANCELED")),
        ),
        QualityCheck(
            "silver.latitude_in_chicago_bbox",
            "latitude must be in the Chicago bbox when present.",
            lambda df: _out_of_range_count(df, "latitude", 41.6, 42.1),
        ),
        QualityCheck(
            "silver.longitude_in_chicago_bbox",
            "longitude must be in the Chicago bbox when present.",
            lambda df: _out_of_range_count(df, "longitude", -87.95, -87.5),
        ),
        QualityCheck(
            "silver.sr_number_unique",
            "sr_number must be unique in the current-state view.",
            lambda df: _duplicate_count(df, "sr_number"),
        ),
    ]


def run_checks(
    df: DataFrame,
    checks: Iterable[QualityCheck],
    total_rows: Optional[int] = None,
) -> List[QualityResult]:
    """Evaluate each check against df; return a list of QualityResults."""
    total = df.count() if total_rows is None else total_rows
    results: List[QualityResult] = []
    for check in checks:
        violations = check.violation_count(df)
        results.append(
            QualityResult(check=check, total_rows=total, violations=int(violations))
        )
    return results
