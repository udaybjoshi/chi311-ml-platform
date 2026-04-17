"""Integration tests for the Spark-native DQ check suites."""
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

from chi311.quality import bronze_checks, run_checks, silver_checks


pytestmark = pytest.mark.integration


STAGED_SCHEMA = StructType(
    [
        StructField("sr_number", StringType(), True),
        StructField("created_date", TimestampType(), True),
        StructField("sr_type", StringType(), True),
        StructField("status", StringType(), True),
        StructField("ward", IntegerType(), True),
        StructField("latitude", DoubleType(), True),
        StructField("longitude", DoubleType(), True),
    ]
)

SILVER_SCHEMA = StructType(
    [
        StructField("sr_number", StringType(), True),
        StructField("created_date", TimestampType(), True),
        StructField("closed_date", TimestampType(), True),
        StructField("sr_type", StringType(), True),
        StructField("status", StringType(), True),
        StructField("ward", IntegerType(), True),
        StructField("latitude", DoubleType(), True),
        StructField("longitude", DoubleType(), True),
        StructField("is_info_call", BooleanType(), True),
        StructField("resolution_hours", DoubleType(), True),
    ]
)


def _results_by_name(results):
    return {r.check.name: r for r in results}


def test_bronze_checks_pass_on_clean_data(spark):
    rows = [
        ("SR1", dt.datetime(2024, 1, 1), "Pothole", "OPEN", 42, 41.88, -87.63),
        ("SR2", dt.datetime(2024, 1, 2), "Graffiti", "COMPLETED", 1, 41.90, -87.70),
    ]
    df = spark.createDataFrame(rows, STAGED_SCHEMA)

    results = _results_by_name(run_checks(df, bronze_checks()))

    for name, r in results.items():
        assert r.passed, f"{name} failed unexpectedly: {r.to_dict()}"


def test_bronze_catches_nulls_and_bad_status(spark):
    rows = [
        ("SR1", dt.datetime(2024, 1, 1), "Pothole", "OPEN", 42, 41.88, -87.63),
        (None, dt.datetime(2024, 1, 2), "Graffiti", "OPEN", 1, 41.90, -87.70),
        ("SR3", None, None, "CLOSED", 999, 41.90, -87.70),  # bad status + ward
    ]
    df = spark.createDataFrame(rows, STAGED_SCHEMA)

    results = _results_by_name(run_checks(df, bronze_checks()))

    assert results["bronze.sr_number_not_null"].violations == 1
    assert results["bronze.created_date_not_null"].violations == 1
    assert results["bronze.sr_type_not_null"].violations == 1
    # status_in_known_values also flags "CLOSED"
    assert results["bronze.status_in_known_values"].violations == 1
    # ward 999 is out of [1, 50]
    assert results["bronze.ward_in_range"].violations == 1


def test_bronze_detects_duplicate_sr_numbers(spark):
    rows = [
        ("SR1", dt.datetime(2024, 1, 1), "Pothole", "OPEN", 42, 41.88, -87.63),
        ("SR1", dt.datetime(2024, 1, 1), "Pothole", "OPEN", 42, 41.88, -87.63),
        ("SR1", dt.datetime(2024, 1, 1), "Pothole", "OPEN", 42, 41.88, -87.63),
        ("SR2", dt.datetime(2024, 1, 2), "Graffiti", "COMPLETED", 1, 41.90, -87.70),
    ]
    df = spark.createDataFrame(rows, STAGED_SCHEMA)

    results = _results_by_name(run_checks(df, bronze_checks()))

    # 3 rows of SR1 -> 2 surplus duplicates.
    assert results["bronze.sr_number_unique"].violations == 2


def test_silver_checks_pass_on_clean_data(spark):
    rows = [
        (
            "SR1",
            dt.datetime(2024, 1, 1),
            dt.datetime(2024, 1, 1, 6),
            "Pothole",
            "COMPLETED",
            42,
            41.88,
            -87.63,
            False,
            6.0,
        ),
    ]
    df = spark.createDataFrame(rows, SILVER_SCHEMA)

    for name, r in _results_by_name(run_checks(df, silver_checks())).items():
        assert r.passed, f"{name} failed: {r.to_dict()}"


def test_silver_rejects_off_bbox_coordinates(spark):
    rows = [
        ("SR1", dt.datetime(2024, 1, 1), None, "Pothole", "OPEN", 42, 40.71, -74.00, False, None),
    ]
    df = spark.createDataFrame(rows, SILVER_SCHEMA)

    results = _results_by_name(run_checks(df, silver_checks()))

    assert results["silver.latitude_in_chicago_bbox"].violations == 1
    assert results["silver.longitude_in_chicago_bbox"].violations == 1


def test_quality_result_to_dict_shape(spark):
    df = spark.createDataFrame(
        [("SR1", dt.datetime(2024, 1, 1), "Pothole", "OPEN", 42, 41.88, -87.63)],
        STAGED_SCHEMA,
    )
    results = run_checks(df, bronze_checks())
    shape = results[0].to_dict()
    assert set(shape) == {
        "name",
        "description",
        "severity",
        "total_rows",
        "violations",
        "violation_rate",
        "passed",
    }
