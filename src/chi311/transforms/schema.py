"""Explicit schemas for the Chicago 311 data.

Using an explicit schema on the Bronze Autoloader read avoids schema-drift
surprises and is required on Databricks Free Edition serverless where
schema inference can be memory-heavy on large JSON files.
"""
from __future__ import annotations

from pyspark.sql.types import StringType, StructField, StructType

CHI311_RAW_SCHEMA = StructType(
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
    ]
)

# Chicago bounding box used for coordinate validity checks.
CHICAGO_BBOX = {
    "lat_min": 41.6,
    "lat_max": 42.1,
    "lon_min": -87.95,
    "lon_max": -87.5,
}

# Canonical status values after upper-casing.
VALID_STATUSES = ("OPEN", "COMPLETED", "CANCELED")
