"""Gold-layer transforms.

Each function mirrors one of the DLT `gold_*` tables but takes a plain
DataFrame input so it can be unit-tested without DLT's ``LIVE`` binding.
"""
from __future__ import annotations

from pyspark.sql import DataFrame, Window, functions as F


def daily_aggregates(silver_current: DataFrame) -> DataFrame:
    """Daily aggregates by ward, sr_type, is_info_call.

    Mirrors ``gold_daily_aggregates``.
    """
    return (
        silver_current.withColumn("date", F.to_date("created_date"))
        .groupBy("date", "ward", "sr_type", "is_info_call")
        .agg(
            F.count(F.lit(1)).alias("total_requests"),
            F.sum(F.when(F.col("status") == "COMPLETED", 1).otherwise(0)).alias("completed_count"),
            F.sum(F.when(F.col("status") == "OPEN", 1).otherwise(0)).alias("open_count"),
            F.sum(F.when(F.col("status") == "CANCELED", 1).otherwise(0)).alias("canceled_count"),
            F.avg("resolution_hours").alias("avg_resolution_hours"),
            F.expr("percentile_approx(resolution_hours, 0.5)").alias("median_resolution_hours"),
            (
                F.sum(F.when(F.col("status") == "COMPLETED", 1.0).otherwise(0.0))
                / F.count(F.lit(1))
            ).alias("completion_rate"),
        )
        .withColumn("day_of_week", F.dayofweek("date"))
        .withColumn("month", F.month("date"))
        .withColumn(
            "is_weekend", F.when(F.dayofweek("date").isin(1, 7), 1).otherwise(0)
        )
    )


def ward_daily_summary(silver_current: DataFrame) -> DataFrame:
    """Per-ward daily summary with lag/rolling features.

    Mirrors ``gold_ward_daily_summary``.
    """
    daily = (
        silver_current.withColumn("date", F.to_date("created_date"))
        .groupBy("date", "ward")
        .agg(
            F.count(F.lit(1)).alias("total_requests"),
            F.sum(F.when(F.col("is_info_call"), 0).otherwise(1)).alias("service_requests"),
            F.sum(F.when(F.col("is_info_call"), 1).otherwise(0)).alias("info_calls"),
            F.countDistinct("sr_type").alias("unique_sr_types"),
            F.avg("resolution_hours").alias("avg_resolution_hours"),
            (
                F.sum(F.when(F.col("status") == "COMPLETED", 1.0).otherwise(0.0))
                / F.count(F.lit(1))
            ).alias("completion_rate"),
        )
    )

    w = Window.partitionBy("ward").orderBy("date")
    w_7 = w.rowsBetween(-8, -1)
    w_28 = w.rowsBetween(-29, -1)

    return (
        daily.withColumn("requests_1d_ago", F.lag("total_requests", 1).over(w))
        .withColumn("requests_7d_ago", F.lag("total_requests", 7).over(w))
        .withColumn("requests_28d_ago", F.lag("total_requests", 28).over(w))
        .withColumn("rolling_7d_avg", F.avg("total_requests").over(w_7))
        .withColumn("rolling_28d_avg", F.avg("total_requests").over(w_28))
        .withColumn("day_of_week", F.dayofweek("date"))
        .withColumn("month", F.month("date"))
        .withColumn(
            "is_weekend", F.when(F.dayofweek("date").isin(1, 7), 1).otherwise(0)
        )
    )


# Anomaly thresholds from exploration (mean + 2σ).
ANOMALY_THRESHOLD_SERVICE = 4851
ANOMALY_THRESHOLD_TOTAL = 7580


def citywide_daily_summary(silver_current: DataFrame) -> DataFrame:
    """Citywide daily summary, primary input to Prophet.

    Mirrors ``gold_citywide_daily_summary`` (shape: ds/y for Prophet plus
    lag + rolling features and anomaly flags).
    """
    daily = (
        silver_current.withColumn("date", F.to_date("created_date"))
        .groupBy("date")
        .agg(
            F.count(F.lit(1)).alias("total_requests"),
            F.sum(F.when(F.col("is_info_call"), 0).otherwise(1)).alias("service_requests"),
            F.sum(F.when(F.col("is_info_call"), 1).otherwise(0)).alias("info_calls"),
            F.countDistinct("sr_type").alias("unique_sr_types"),
            F.countDistinct("ward").alias("wards_with_requests"),
            F.avg("resolution_hours").alias("avg_resolution_hours"),
            (
                F.sum(F.when(F.col("status") == "COMPLETED", 1.0).otherwise(0.0))
                / F.count(F.lit(1))
            ).alias("completion_rate"),
        )
    )

    w = Window.orderBy("date")
    w_7 = w.rowsBetween(-8, -1)
    w_28 = w.rowsBetween(-29, -1)

    return (
        daily.withColumn("ds", F.col("date"))
        .withColumn("y", F.col("service_requests"))
        .withColumn("requests_1d_ago", F.lag("service_requests", 1).over(w))
        .withColumn("requests_7d_ago", F.lag("service_requests", 7).over(w))
        .withColumn("requests_28d_ago", F.lag("service_requests", 28).over(w))
        .withColumn("rolling_7d_avg", F.avg("service_requests").over(w_7))
        .withColumn("rolling_28d_avg", F.avg("service_requests").over(w_28))
        .withColumn("day_of_week", F.dayofweek("date"))
        .withColumn("month", F.month("date"))
        .withColumn("day_of_year", F.dayofyear("date"))
        .withColumn(
            "is_weekend", F.when(F.dayofweek("date").isin(1, 7), 1).otherwise(0)
        )
        .withColumn(
            "is_anomaly_service",
            F.col("service_requests") > F.lit(ANOMALY_THRESHOLD_SERVICE),
        )
        .withColumn(
            "is_anomaly_total",
            F.col("total_requests") > F.lit(ANOMALY_THRESHOLD_TOTAL),
        )
    )
