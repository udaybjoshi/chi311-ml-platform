"""Bronze -> staged-bronze transform.

Mirrors the `bronze_staged_311_requests` DLT table definition but as a plain
PySpark function so it can be unit-tested on a local SparkSession. The DLT
SQL calls this same shape via CTAS.
"""
from __future__ import annotations

from pyspark.sql import DataFrame, functions as F

from chi311.transforms.schema import CHICAGO_BBOX


def stage_bronze_raw(df: DataFrame) -> DataFrame:
    """Clean raw bronze rows into the staged shape used for SCD2 CDC.

    - Casts dates to timestamps.
    - Standardises status/origin to upper-case, trims string fields.
    - Replaces coordinates outside the Chicago bbox with NULL.
    - Derives ``is_info_call`` and ``_sequence_timestamp`` (the column that
      DLT's ``APPLY CHANGES INTO`` sequences on).

    The input DataFrame is expected to have (at minimum) the raw Chicago
    311 string columns plus ``_ingestion_timestamp``.
    """
    lat = F.col("latitude").cast("double")
    lon = F.col("longitude").cast("double")
    in_bbox = (
        lat.between(CHICAGO_BBOX["lat_min"], CHICAGO_BBOX["lat_max"])
        & lon.between(CHICAGO_BBOX["lon_min"], CHICAGO_BBOX["lon_max"])
    )

    created_ts = F.to_timestamp("created_date")
    closed_ts = F.to_timestamp("closed_date")
    modified_ts = F.to_timestamp("last_modified_date")

    return df.select(
        F.col("sr_number"),
        F.coalesce(modified_ts, closed_ts, created_ts, F.col("_ingestion_timestamp"))
        .alias("_sequence_timestamp"),
        created_ts.alias("created_date"),
        closed_ts.alias("closed_date"),
        modified_ts.alias("last_modified_date"),
        F.trim(F.col("sr_type")).alias("sr_type"),
        F.trim(F.col("sr_short_code")).alias("sr_short_code"),
        F.trim(F.col("owner_department")).alias("owner_department"),
        F.upper(F.trim(F.col("status"))).alias("status"),
        F.col("ward").cast("int").alias("ward"),
        F.trim(F.col("community_area")).alias("community_area"),
        F.trim(F.col("street_address")).alias("street_address"),
        F.trim(F.col("zip_code")).alias("zip_code"),
        F.when(in_bbox, lat).alias("latitude"),
        F.when(in_bbox, lon).alias("longitude"),
        F.upper(F.trim(F.col("origin"))).alias("origin"),
        F.col("duplicate").cast("boolean").alias("is_duplicate"),
        F.col("legacy_record").cast("boolean").alias("is_legacy"),
        (F.trim(F.col("sr_type")) == F.lit("311 INFORMATION ONLY CALL"))
        .alias("is_info_call"),
        F.col("_ingestion_timestamp"),
        F.col("_source_file"),
    )
