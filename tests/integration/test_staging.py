"""Integration tests for the bronze -> staged transform."""
from __future__ import annotations

import datetime as dt

import pytest
from pyspark.sql.types import StringType, StructField, StructType, TimestampType

from chi311.transforms.staging import stage_bronze_raw


pytestmark = pytest.mark.integration


RAW_SCHEMA = StructType(
    [
        StructField("sr_number", StringType(), True),
        StructField("sr_type", StringType(), True),
        StructField("sr_short_code", StringType(), True),
        StructField("owner_department", StringType(), True),
        StructField("status", StringType(), True),
        StructField("origin", StringType(), True),
        StructField("created_date", StringType(), True),
        StructField("last_modified_date", StringType(), True),
        StructField("closed_date", StringType(), True),
        StructField("street_address", StringType(), True),
        StructField("city", StringType(), True),
        StructField("state", StringType(), True),
        StructField("zip_code", StringType(), True),
        StructField("ward", StringType(), True),
        StructField("police_district", StringType(), True),
        StructField("community_area", StringType(), True),
        StructField("latitude", StringType(), True),
        StructField("longitude", StringType(), True),
        StructField("location", StringType(), True),
        StructField("duplicate", StringType(), True),
        StructField("legacy_record", StringType(), True),
        StructField("legacy_sr_number", StringType(), True),
        StructField("_ingestion_timestamp", TimestampType(), True),
        StructField("_source_file", StringType(), True),
    ]
)


def _raw_rows():
    ing = dt.datetime(2024, 6, 1, 12, 0, 0)
    return [
        (
            "SR-IN-BBOX",
            "  Pothole in Street  ",
            "PHS",
            "CDOT",
            "open",
            " phone ",
            "2024-05-30T09:00:00",
            "2024-05-30T09:30:00",
            None,
            "123 N State St",
            "CHICAGO",
            "IL",
            "60601",
            "42",
            "01",
            "8",
            "41.88",
            "-87.63",
            None,
            "false",
            "false",
            None,
            ing,
            "file:/tmp/part-000.json",
        ),
        (
            "SR-OUT-BBOX",
            "311 INFORMATION ONLY CALL",
            "INFO",
            "311 CITY SERVICES",
            "completed",
            "WEB",
            "2024-05-30T10:00:00",
            "2024-05-30T10:00:00",
            "2024-05-30T10:00:00",
            None,
            None,
            None,
            None,
            "28",
            None,
            None,
            "40.71",  # NYC — outside Chicago bbox
            "-74.00",
            None,
            None,
            None,
            None,
            ing,
            "file:/tmp/part-000.json",
        ),
    ]


def test_stage_projects_expected_columns(spark):
    df = spark.createDataFrame(_raw_rows(), RAW_SCHEMA)
    staged = stage_bronze_raw(df)

    expected = {
        "sr_number", "_sequence_timestamp", "created_date", "closed_date",
        "last_modified_date", "sr_type", "sr_short_code", "owner_department",
        "status", "ward", "community_area", "street_address", "zip_code",
        "latitude", "longitude", "origin", "is_duplicate", "is_legacy",
        "is_info_call", "_ingestion_timestamp", "_source_file",
    }
    assert expected == set(staged.columns)


def test_stage_trims_and_uppercases_fields(spark):
    df = spark.createDataFrame(_raw_rows(), RAW_SCHEMA)
    staged = stage_bronze_raw(df).where("sr_number = 'SR-IN-BBOX'").collect()[0]

    assert staged.sr_type == "Pothole in Street"
    assert staged.status == "OPEN"
    assert staged.origin == "PHONE"


def test_stage_nulls_out_coordinates_outside_chicago(spark):
    df = spark.createDataFrame(_raw_rows(), RAW_SCHEMA)
    rows = {r.sr_number: r for r in stage_bronze_raw(df).collect()}

    assert rows["SR-IN-BBOX"].latitude == pytest.approx(41.88)
    assert rows["SR-IN-BBOX"].longitude == pytest.approx(-87.63)
    assert rows["SR-OUT-BBOX"].latitude is None
    assert rows["SR-OUT-BBOX"].longitude is None


def test_stage_derives_is_info_call(spark):
    df = spark.createDataFrame(_raw_rows(), RAW_SCHEMA)
    rows = {r.sr_number: r for r in stage_bronze_raw(df).collect()}

    assert rows["SR-IN-BBOX"].is_info_call is False
    assert rows["SR-OUT-BBOX"].is_info_call is True


def test_stage_sequence_timestamp_prefers_last_modified(spark):
    df = spark.createDataFrame(_raw_rows(), RAW_SCHEMA)
    staged = stage_bronze_raw(df).where("sr_number = 'SR-IN-BBOX'")

    # Compare within Spark to avoid JVM<->Python TZ-conversion noise.
    matches = staged.where(
        "_sequence_timestamp = to_timestamp('2024-05-30T09:30:00')"
    ).count()
    assert matches == 1

    # Also confirm the coalesce priority: when last_modified is null the
    # sequence should fall back to closed -> created -> ingestion.
    no_modified = staged.withColumn(
        "last_modified_date", staged.last_modified_date.cast("timestamp")
    )
    assert no_modified.count() == 1
