# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - Bronze Layer Autoloader
# MAGIC 
# MAGIC **Purpose**: Incrementally ingest JSON files from Volume into Bronze Delta table
# MAGIC 
# MAGIC **Pattern**: Volume (JSON) → Autoloader (Streaming) → Bronze (Delta)
# MAGIC 
# MAGIC **Key Features**:
# MAGIC - **Incremental Processing**: Only processes new files (idempotent)
# MAGIC - **Schema Evolution**: Handles new columns automatically
# MAGIC - **Checkpointing**: Tracks processed files for exactly-once semantics
# MAGIC 
# MAGIC **Technology**: Spark Structured Streaming with cloudFiles (Autoloader)

# COMMAND ----------

# MAGIC %md
# MAGIC ## What is Autoloader?
# MAGIC 
# MAGIC Autoloader is Databricks' recommended way to ingest files incrementally:
# MAGIC 
# MAGIC ```
# MAGIC Day 1: Process 10 files ✓ (checkpoint updated)
# MAGIC Day 2: Process 5 NEW files only (not all 15)
# MAGIC Day 3: Process 3 NEW files only (not all 18)
# MAGIC ```
# MAGIC 
# MAGIC **Benefits**:
# MAGIC - Automatically discovers new files
# MAGIC - Handles schema changes
# MAGIC - Exactly-once processing guarantee
# MAGIC - Scales to millions of files

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import *
from delta.tables import DeltaTable

# Catalog and schema
CATALOG = "workspace"
BRONZE_SCHEMA = "bronze"

# Source paths (Volumes)
LANDING_PATH = f"/Volumes/{CATALOG}/raw/chi311_landing"
INITIAL_PATH = f"{LANDING_PATH}/initial"
INCREMENTAL_PATH = f"{LANDING_PATH}/incremental"

# Target table
BRONZE_TABLE = f"{CATALOG}.{BRONZE_SCHEMA}.bronze_raw_311_requests"

# Checkpoint location (for streaming state)
CHECKPOINT_PATH = f"/Volumes/{CATALOG}/bronze/chi311_checkpoint/autoloader"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Widget Parameters

# COMMAND ----------

dbutils.widgets.dropdown("processing_mode", "batch", ["batch", "streaming"], "Processing Mode")
dbutils.widgets.dropdown("source_path", "all", ["all", "initial", "incremental"], "Source Path")

processing_mode = dbutils.widgets.get("processing_mode")
source_path_type = dbutils.widgets.get("source_path")

# Determine source path
if source_path_type == "initial":
    SOURCE_PATH = INITIAL_PATH
elif source_path_type == "incremental":
    SOURCE_PATH = INCREMENTAL_PATH
else:
    SOURCE_PATH = LANDING_PATH  # Process all subdirectories

print(f"Processing Mode: {processing_mode}")
print(f"Source Path: {SOURCE_PATH}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Define Schema
# MAGIC 
# MAGIC Explicit schema for Chicago 311 data (from exploration findings)

# COMMAND ----------

# Chicago 311 schema based on exploration
chi311_schema = StructType([
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
    StructField("legacy_sr_number", StringType(), True)
])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Autoloader Configuration

# COMMAND ----------

# Autoloader options
autoloader_options = {
    "cloudFiles.format": "json",
    "cloudFiles.schemaLocation": f"{CHECKPOINT_PATH}/schema",
    "cloudFiles.inferColumnTypes": "true",
    "cloudFiles.schemaEvolutionMode": "addNewColumns",  # Handle new columns
    "recursiveFileLookup": "true"  # Look in subdirectories
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Read with Autoloader

# COMMAND ----------

# Create streaming DataFrame using Autoloader
df_stream = (
    spark.readStream
    .format("cloudFiles")
    .options(**autoloader_options)
    .schema(chi311_schema)  # Use explicit schema
    .load(SOURCE_PATH)
)

# Add ingestion metadata
df_bronze = df_stream.withColumn(
    "_ingestion_timestamp", F.current_timestamp()
).withColumn(
    "_source_file", F.input_file_name()
)

print("Streaming DataFrame created")
print(f"Columns: {df_bronze.columns}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write to Bronze Delta Table

# COMMAND ----------

if processing_mode == "streaming":
    # Continuous streaming mode
    query = (
        df_bronze.writeStream
        .format("delta")
        .outputMode("append")
        .option("checkpointLocation", f"{CHECKPOINT_PATH}/bronze")
        .option("mergeSchema", "true")
        .trigger(availableNow=True)  # Process all available, then stop
        .toTable(BRONZE_TABLE)
    )
    
    # Wait for completion
    query.awaitTermination()
    print(f"Streaming write completed to: {BRONZE_TABLE}")

else:
    # Batch mode using trigger once
    query = (
        df_bronze.writeStream
        .format("delta")
        .outputMode("append")
        .option("checkpointLocation", f"{CHECKPOINT_PATH}/bronze")
        .option("mergeSchema", "true")
        .trigger(availableNow=True)
        .toTable(BRONZE_TABLE)
    )
    
    # Wait for completion
    query.awaitTermination()
    print(f"Batch write completed to: {BRONZE_TABLE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Alternative: Trigger Once with foreachBatch
# MAGIC 
# MAGIC For more control over the write process

# COMMAND ----------

# # Uncomment to use foreachBatch pattern
# def write_to_bronze(batch_df, batch_id):
#     """Write each micro-batch to Bronze table"""
#     print(f"Processing batch {batch_id} with {batch_df.count()} records")
    
#     batch_df.write \
#         .format("delta") \
#         .mode("append") \
#         .option("mergeSchema", "true") \
#         .saveAsTable(BRONZE_TABLE)

# query = (
#     df_bronze.writeStream
#     .foreachBatch(write_to_bronze)
#     .option("checkpointLocation", f"{CHECKPOINT_PATH}/bronze")
#     .trigger(availableNow=True)
#     .start()
# )
# query.awaitTermination()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify Bronze Table

# COMMAND ----------

# Check table exists and get stats
print(f"Bronze Table: {BRONZE_TABLE}")
print("-" * 60)

df_bronze_check = spark.table(BRONZE_TABLE)
record_count = df_bronze_check.count()
print(f"Total Records: {record_count:,}")

# Show recent ingestions
print("\nRecent Ingestions:")
display(
    df_bronze_check
    .groupBy(F.date_trunc("hour", "_ingestion_timestamp").alias("ingestion_hour"))
    .count()
    .orderBy(F.desc("ingestion_hour"))
    .limit(10)
)

# COMMAND ----------

# Show sample records
print("\nSample Records:")
display(df_bronze_check.limit(5))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Table History

# COMMAND ----------

# Show Delta table history
display(spark.sql(f"DESCRIBE HISTORY {BRONZE_TABLE}"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary
# MAGIC 
# MAGIC | Metric | Value |
# MAGIC |--------|-------|
# MAGIC | Source Path | {SOURCE_PATH} |
# MAGIC | Target Table | {BRONZE_TABLE} |
# MAGIC | Processing Mode | {processing_mode} |
# MAGIC | Total Records | {record_count:,} |
# MAGIC 
# MAGIC **Autoloader Benefits Used**:
# MAGIC - Incremental file discovery
# MAGIC - Schema evolution support
# MAGIC - Exactly-once processing via checkpoints
# MAGIC - Recursive directory scanning
# MAGIC 
# MAGIC **Next Step**: 
# MAGIC - Run Lakeflow DLT Pipeline for Silver + Gold transformations
# MAGIC - Or run `03_data_quality/01_data_quality_checks.py` for validation