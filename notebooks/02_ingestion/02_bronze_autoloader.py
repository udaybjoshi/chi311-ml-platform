# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - Bronze Layer Autoloader
# MAGIC
# MAGIC **Purpose**: Incrementally ingest JSON files from the landing Volume
# MAGIC into the Bronze Delta table.
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

CATALOG = dbutils.widgets.get("catalog_name")
SOURCE_PATH_TYPE = dbutils.widgets.get("source_path")

# Paths derived from the catalog parameter.
LANDING_PATH = f"/Volumes/{CATALOG}/raw/chi311_landing"
INITIAL_PATH = f"{LANDING_PATH}/initial"
INCREMENTAL_PATH = f"{LANDING_PATH}/incremental"
BRONZE_TABLE = f"{CATALOG}.bronze.bronze_raw_311_requests"
CHECKPOINT_PATH = f"/Volumes/{CATALOG}/bronze/chi311_checkpoint/autoloader"
SCHEMA_PATH = f"/Volumes/{CATALOG}/bronze/chi311_checkpoint/schema"

SOURCE_PATH = {
    "initial": INITIAL_PATH,
    "incremental": INCREMENTAL_PATH,
    "all": LANDING_PATH,
}[SOURCE_PATH_TYPE]

print(f"Catalog:         {CATALOG}")
print(f"Source path:     {SOURCE_PATH}")
print(f"Bronze table:    {BRONZE_TABLE}")
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

autoloader_options = {
    "cloudFiles.format": "json",
    "cloudFiles.schemaLocation": SCHEMA_PATH,
    "cloudFiles.inferColumnTypes": "false",
    "recursiveFileLookup": "true",  # pick up initial/ and incremental/ subdirs
    # Multi-line JSON: our landing files are one JSON array per file.
    "multiLine": "true",
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Read + Write to Bronze Delta Table

# COMMAND ----------

df_stream = (
    spark.readStream.format("cloudFiles")
    .options(**autoloader_options)
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
