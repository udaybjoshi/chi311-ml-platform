"""Integration tests for gold transforms (daily / ward / citywide)."""
from __future__ import annotations

import datetime as dt

import pytest
from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from chi311.transforms.gold import (
    ANOMALY_THRESHOLD_SERVICE,
    citywide_daily_summary,
    daily_aggregates,
    ward_daily_summary,
)


pytestmark = pytest.mark.integration


SILVER_SCHEMA = StructType(
    [
        StructField("sr_number", StringType(), False),
        StructField("created_date", TimestampType(), True),
        StructField("closed_date", TimestampType(), True),
        StructField("last_modified_date", TimestampType(), True),
        StructField("sr_type", StringType(), True),
        StructField("sr_short_code", StringType(), True),
        StructField("owner_department", StringType(), True),
        StructField("status", StringType(), True),
        StructField("ward", IntegerType(), True),
        StructField("community_area", StringType(), True),
        StructField("street_address", StringType(), True),
        StructField("zip_code", StringType(), True),
        StructField("latitude", DoubleType(), True),
        StructField("longitude", DoubleType(), True),
        StructField("origin", StringType(), True),
        StructField("is_duplicate", BooleanType(), True),
        StructField("is_legacy", BooleanType(), True),
        StructField("is_info_call", BooleanType(), True),
        StructField("resolution_hours", DoubleType(), True),
        StructField("valid_from", TimestampType(), True),
        StructField("valid_to", TimestampType(), True),
    ]
)


def _row(sr, d, ward, sr_type, status, info=False, res=None):
    created = dt.datetime(d.year, d.month, d.day, 9, 0)
    closed = None
    if res is not None:
        closed = created + dt.timedelta(hours=res)
    return (
        sr, created, closed, created, sr_type, None, None, status,
        ward, None, None, None, 41.88, -87.63, "PHONE", False, False, info,
        res, created, None,
    )


def test_daily_aggregates_counts_status_breakdown(spark):
    day = dt.date(2024, 3, 1)
    rows = [
        _row("SR1", day, 42, "Pothole", "COMPLETED", res=2.0),
        _row("SR2", day, 42, "Pothole", "COMPLETED", res=4.0),
        _row("SR3", day, 42, "Pothole", "OPEN"),
        _row("SR4", day, 42, "Pothole", "CANCELED"),
    ]
    df = spark.createDataFrame(rows, SILVER_SCHEMA)
    agg = daily_aggregates(df).collect()

    assert len(agg) == 1
    r = agg[0]
    assert r.total_requests == 4
    assert r.completed_count == 2
    assert r.open_count == 1
    assert r.canceled_count == 1
    assert r.completion_rate == pytest.approx(0.5)
    assert r.avg_resolution_hours == pytest.approx(3.0)


def test_ward_daily_summary_lag_features(spark):
    base = dt.date(2024, 3, 1)
    rows = []
    # 10 days, one row per day in ward 42, known counts: 100, 110, 90, 95, 100, 120, 80, 70, 130, 140
    counts = [100, 110, 90, 95, 100, 120, 80, 70, 130, 140]
    sr = 0
    for i, c in enumerate(counts):
        d = base + dt.timedelta(days=i)
        for _ in range(c):
            sr += 1
            rows.append(_row(f"SR{sr}", d, 42, "Pothole", "COMPLETED", res=1.0))
    df = spark.createDataFrame(rows, SILVER_SCHEMA)

    out = {r.date: r for r in ward_daily_summary(df).collect()}
    # day-2 (index 1): requests_1d_ago = 100 (day-1)
    assert out[base + dt.timedelta(days=1)].requests_1d_ago == 100
    # day-8 (index 7): requests_7d_ago = 100 (day-1)
    assert out[base + dt.timedelta(days=7)].requests_7d_ago == 100


def test_citywide_daily_summary_exposes_prophet_columns(spark):
    day = dt.date(2024, 3, 1)
    rows = [
        _row("SR1", day, 42, "Pothole", "COMPLETED"),
        _row("SR2", day, 42, "Pothole", "OPEN"),
        _row("SR3", day, 28, "311 INFORMATION ONLY CALL", "COMPLETED", info=True),
    ]
    df = spark.createDataFrame(rows, SILVER_SCHEMA)
    out = citywide_daily_summary(df).collect()[0]

    # Prophet alias columns
    assert out.ds == day
    # service_requests excludes info calls -> 2
    assert out.y == 2
    assert out.service_requests == 2
    assert out.info_calls == 1
    assert out.total_requests == 3
    assert out.wards_with_requests == 2


def test_citywide_daily_summary_flags_anomalies(spark):
    day = dt.date(2024, 3, 1)
    rows = [
        _row(f"SR{i}", day, 42, "Pothole", "COMPLETED")
        for i in range(ANOMALY_THRESHOLD_SERVICE + 10)
    ]
    df = spark.createDataFrame(rows, SILVER_SCHEMA)
    out = citywide_daily_summary(df).collect()[0]

    assert out.is_anomaly_service is True
