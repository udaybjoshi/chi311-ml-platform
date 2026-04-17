"""Integration tests for the SCD2 -> current-state projection."""
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

from chi311.transforms.silver import current_from_scd2


pytestmark = pytest.mark.integration


SCD2_SCHEMA = StructType(
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
        StructField("__START_AT", TimestampType(), True),
        StructField("__END_AT", TimestampType(), True),
    ]
)


def _ts(y, mo, d, h=0, mi=0):
    return dt.datetime(y, mo, d, h, mi)


def test_current_filters_out_superseded_versions(spark):
    rows = [
        # SR1: v1 (open) superseded by v2 (completed, current)
        (
            "SR1", _ts(2024, 1, 1), None, _ts(2024, 1, 1),
            "Pothole", "PHS", "CDOT", "OPEN", 42, "8", "123 N State",
            "60601", 41.88, -87.63, "PHONE", False, False, False,
            _ts(2024, 1, 1), _ts(2024, 1, 5),
        ),
        (
            "SR1", _ts(2024, 1, 1), _ts(2024, 1, 5, 14), _ts(2024, 1, 5, 14),
            "Pothole", "PHS", "CDOT", "COMPLETED", 42, "8", "123 N State",
            "60601", 41.88, -87.63, "PHONE", False, False, False,
            _ts(2024, 1, 5, 14), None,
        ),
        # SR2: still open, single version
        (
            "SR2", _ts(2024, 2, 1), None, _ts(2024, 2, 1),
            "Graffiti", "GRF", "DSS", "OPEN", 1, "1", "X",
            "60610", 41.90, -87.70, "WEB", False, False, False,
            _ts(2024, 2, 1), None,
        ),
    ]
    df = spark.createDataFrame(rows, SCD2_SCHEMA)
    current = current_from_scd2(df).collect()

    by_sr = {r.sr_number: r for r in current}
    assert set(by_sr) == {"SR1", "SR2"}
    assert by_sr["SR1"].status == "COMPLETED"
    assert by_sr["SR2"].status == "OPEN"


def test_current_computes_resolution_hours(spark):
    rows = [
        (
            "SR1", _ts(2024, 1, 1, 0, 0), _ts(2024, 1, 1, 6, 0), _ts(2024, 1, 1, 6, 0),
            "Pothole", "PHS", "CDOT", "COMPLETED", 42, "8", "123", "60601",
            41.88, -87.63, "PHONE", False, False, False,
            _ts(2024, 1, 1, 6, 0), None,
        ),
        (
            "SR2", _ts(2024, 2, 1), None, _ts(2024, 2, 1),
            "Graffiti", "GRF", "DSS", "OPEN", 1, "1", "X", "60610",
            41.9, -87.7, "WEB", False, False, False,
            _ts(2024, 2, 1), None,
        ),
    ]
    df = spark.createDataFrame(rows, SCD2_SCHEMA)
    current = {r.sr_number: r for r in current_from_scd2(df).collect()}

    # 6h difference
    assert current["SR1"].resolution_hours == pytest.approx(6.0)
    # Still open -> null
    assert current["SR2"].resolution_hours is None


def test_current_renames_scd2_columns(spark):
    rows = [
        (
            "SR1", _ts(2024, 1, 1), None, _ts(2024, 1, 1),
            "Pothole", "PHS", "CDOT", "OPEN", 42, "8", "123", "60601",
            41.88, -87.63, "PHONE", False, False, False,
            _ts(2024, 1, 1), None,
        ),
    ]
    df = spark.createDataFrame(rows, SCD2_SCHEMA)
    current = current_from_scd2(df)

    assert "valid_from" in current.columns
    assert "valid_to" in current.columns
    assert "__START_AT" not in current.columns
    assert "__END_AT" not in current.columns
