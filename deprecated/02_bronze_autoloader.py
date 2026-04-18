# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - Bronze Layer Autoloader (DEPRECATED)
# MAGIC
# MAGIC **Status**: Superseded by the DLT pipeline in
# MAGIC `pipelines/chi311_scd2_pipeline.sql`, which reads the landing Volume
# MAGIC directly via `STREAM read_files(...)`. Two concurrent writers to the
# MAGIC same Bronze Delta table conflict, so only one should be active.
# MAGIC
# MAGIC Kept here as a fallback for environments where DLT is unavailable
# MAGIC (notably, if a future workspace strips Lakeflow Declarative Pipelines
# MAGIC from the Free tier) or for local debugging without a DLT run.
# MAGIC
# MAGIC **Purpose (historical)**: Incrementally ingest JSON files from the
# MAGIC landing Volume into the Bronze Delta table.
# MAGIC
# MAGIC **Pattern**: Volume (JSON) -> Autoloader (Structured Streaming with
# MAGIC `cloudFiles`) -> Bronze (Delta).
# MAGIC
# MAGIC **Key features**:
# MAGIC - Incremental file discovery via checkpointed `cloudFiles` source.
# MAGIC - Exactly-once delivery guaranteed by the streaming checkpoint.
# MAGIC - Explicit schema (see `src/chi311/transforms/schema.py`) to avoid
# MAGIC   schema-inference churn on serverless.
# MAGIC - `trigger(availableNow=True)`: processes the current backlog and
# MAGIC   exits, which is what serverless Jobs on Free Edition should use
# MAGIC   (no always-on streams).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

# COMMAND ----------

# MAGIC %md
# MAGIC ## Widget Parameters

# COMMAND ----------

dbutils.widgets.text("catalog_name", "workspace", "Catalog Name")
dbutils.widgets.dropdown("source_path", "all", ["all", "initial", "incremental"], "Source Path")
dbutils.widgets.dropdown(
    "reader_mode", "autoloader", ["autoloader", "filestream"],
    "Reader Mode (filestream = workaround for UC managed-Volume overlap)",
)
dbutils.widgets.dropdown(
    "reset_checkpoint", "false", ["true", "false"],
    "Reset checkpoint before run (recovers from contamination)",
)

CATALOG = dbutils.widgets.get("catalog_name")
SOURCE_PATH_TYPE = dbutils.widgets.get("source_path")
READER_MODE = dbutils.widgets.get("reader_mode")
RESET_CHECKPOINT = dbutils.widgets.get("reset_checkpoint") == "true"

# Paths derived from the catalog parameter.
LANDING_PATH = f"/Volumes/{CATALOG}/raw/chi311_landing"
INITIAL_PATH = f"{LANDING_PATH}/initial"
INCREMENTAL_PATH = f"{LANDING_PATH}/incremental"
BRONZE_TABLE = f"{CATALOG}.bronze.bronze_raw_311_requests"

# Checkpoint paths are scoped by (reader_mode, source_path). Sharing one
# checkpoint across modes leaks offsets between runs and was the root
# cause of the "LOCATION_OVERLAP on .../incremental/..." error when the
# Autoloader re-resolved stale offsets after a mode switch.
CHECKPOINT_BASE = f"/Volumes/{CATALOG}/bronze/chi311_checkpoint"
CHECKPOINT_PATH = f"{CHECKPOINT_BASE}/{READER_MODE}/{SOURCE_PATH_TYPE}"
SCHEMA_PATH = f"{CHECKPOINT_BASE}/schema/{SOURCE_PATH_TYPE}"

SOURCE_PATH = {
    "initial": INITIAL_PATH,
    "incremental": INCREMENTAL_PATH,
    "all": LANDING_PATH,
}[SOURCE_PATH_TYPE]

if RESET_CHECKPOINT:
    try:
        dbutils.fs.rm(CHECKPOINT_PATH, recurse=True)
        print(f"Removed checkpoint: {CHECKPOINT_PATH}")
    except Exception as e:
        print(f"Checkpoint reset skipped: {e}")

print(f"Catalog:         {CATALOG}")
print(f"Source path:     {SOURCE_PATH}")
print(f"Bronze table:    {BRONZE_TABLE}")
print(f"Reader mode:     {READER_MODE}")
print(f"Checkpoint path: {CHECKPOINT_PATH}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Explicit Bronze Schema
# MAGIC
# MAGIC Kept in sync with `src/chi311/transforms/schema.py::CHI311_RAW_SCHEMA`.
# MAGIC Explicit schemas avoid Autoloader's schema-inference pass (which can
# MAGIC be memory-heavy on the initial-load files on serverless).

# COMMAND ----------

chi311_schema = StructType(
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

# COMMAND ----------

# MAGIC %md
# MAGIC ## Autoloader Configuration

# COMMAND ----------

# MAGIC %md
# MAGIC ## Read + Write to Bronze Delta Table
# MAGIC
# MAGIC **Reader modes**:
# MAGIC - `autoloader`: `cloudFiles` source. Preferred in most environments.
# MAGIC   On Databricks Free Edition with managed Volumes, this can fail with
# MAGIC   `UnityCatalogServiceException: LOCATION_OVERLAP ... CheckPathAccess`
# MAGIC   because `cloudFiles` resolves Volume paths to the underlying
# MAGIC   `s3://dbstorage-prod-.../__unitystorage/...` URL and UC refuses to
# MAGIC   grant path access to its own managed-storage location.
# MAGIC - `filestream`: plain `format("json")` Structured Streaming source.
# MAGIC   Reads files through the Volume abstraction (no raw-S3 resolution)
# MAGIC   and sidesteps the UC check. Loses `cloudFiles`' notification-mode
# MAGIC   optimizations, but on Free Edition those don't apply anyway.

# COMMAND ----------

# Re-read widgets (self-contained cell).
CATALOG = dbutils.widgets.get("catalog_name")
READER_MODE = dbutils.widgets.get("reader_mode")
SOURCE_PATH_TYPE = dbutils.widgets.get("source_path")
LANDING_PATH = f"/Volumes/{CATALOG}/raw/chi311_landing"
SOURCE_PATH = {
    "initial": f"{LANDING_PATH}/initial",
    "incremental": f"{LANDING_PATH}/incremental",
    "all": LANDING_PATH,
}[SOURCE_PATH_TYPE]
BRONZE_TABLE = f"{CATALOG}.bronze.bronze_raw_311_requests"
CHECKPOINT_PATH = f"/Volumes/{CATALOG}/bronze/chi311_checkpoint/{READER_MODE}/{SOURCE_PATH_TYPE}"
SCHEMA_PATH = f"/Volumes/{CATALOG}/bronze/chi311_checkpoint/schema/{SOURCE_PATH_TYPE}"

if READER_MODE == "autoloader":
    df_stream = (
        spark.readStream.format("cloudFiles")
        .options(**{
            "cloudFiles.format": "json",
            "cloudFiles.schemaLocation": SCHEMA_PATH,
            "cloudFiles.inferColumnTypes": "false",
            "recursiveFileLookup": "true",
            "multiLine": "true",
        })
        .schema(chi311_schema)
        .load(SOURCE_PATH)
    )
else:  # filestream fallback (Free-Edition-safe)
    df_stream = (
        spark.readStream.format("json")
        .options(**{
            "recursiveFileLookup": "true",
            "multiLine": "true",
        })
        .schema(chi311_schema)
        .load(SOURCE_PATH)
    )

df_bronze = df_stream.withColumn(
    "_ingestion_timestamp", F.current_timestamp()
).withColumn(
    "_source_file", F.col("_metadata.file_path")
)

query = (
    df_bronze.writeStream.format("delta")
    .outputMode("append")
    .option("checkpointLocation", f"{CHECKPOINT_PATH}/bronze")
    .option("mergeSchema", "true")
    .trigger(availableNow=True)
    .toTable(BRONZE_TABLE)
)

query.awaitTermination()
print(f"Bronze write completed to: {BRONZE_TABLE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify Bronze Table

# COMMAND ----------

df_bronze_check = spark.table(BRONZE_TABLE)
record_count = df_bronze_check.count()
print(f"Total records in {BRONZE_TABLE}: {record_count:,}")

print("\nRecent ingestions (hourly):")
display(
    df_bronze_check.groupBy(
        F.date_trunc("hour", "_ingestion_timestamp").alias("ingestion_hour")
    )
    .count()
    .orderBy(F.desc("ingestion_hour"))
    .limit(10)
)

# COMMAND ----------

print("Sample records:")
display(df_bronze_check.limit(5))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Table History

# COMMAND ----------

display(spark.sql(f"DESCRIBE HISTORY {BRONZE_TABLE}"))

# COMMAND ----------

dbutils.notebook.exit(
    f"SUCCESS: {record_count:,} rows in {BRONZE_TABLE}"
)
