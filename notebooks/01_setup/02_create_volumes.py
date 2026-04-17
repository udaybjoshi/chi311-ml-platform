# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - Create Volumes
# MAGIC
# MAGIC **Purpose**: Set up Unity Catalog Volumes for file storage.
# MAGIC
# MAGIC **Why Volumes** (not DBFS): on Databricks Free Edition, DBFS is
# MAGIC read-only for user data. Volumes are the governed location for raw
# MAGIC files, checkpoints, and ML artifacts, and they work out of the box
# MAGIC on serverless.
# MAGIC
# MAGIC **Prerequisite**: Run `01_create_catalog_schemas.py` first.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Volume Structure
# MAGIC
# MAGIC ```
# MAGIC /Volumes/<catalog>/raw/chi311_landing/
# MAGIC ├── initial/        # first bulk load (historical data)
# MAGIC ├── incremental/    # daily incremental files
# MAGIC └── archive/        # processed files (optional)
# MAGIC
# MAGIC /Volumes/<catalog>/bronze/chi311_checkpoint/
# MAGIC ├── autoloader/     # streaming checkpoint
# MAGIC └── schema/         # Autoloader inferred-schema location
# MAGIC
# MAGIC /Volumes/<catalog>/ml/chi311_models/
# MAGIC ├── prophet/        # exported Prophet models
# MAGIC ├── predictions/    # batch prediction outputs
# MAGIC └── features/       # feature-store exports
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ## Widget Parameters

# COMMAND ----------

dbutils.widgets.text("catalog_name", "workspace", "Catalog Name")
dbutils.widgets.dropdown("reset_volumes", "false", ["true", "false"], "Reset Volumes (DROP ALL)")

CATALOG_NAME = dbutils.widgets.get("catalog_name")
RESET_VOLUMES = dbutils.widgets.get("reset_volumes") == "true"

print(f"Catalog Name:  {CATALOG_NAME}")
print(f"Reset Volumes: {RESET_VOLUMES}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

VOLUMES = {
    "raw": {
        "chi311_landing": {
            "description": "Landing zone for raw JSON files from Chicago 311 API",
            "directories": ["initial", "incremental", "archive"],
        },
    },
    "bronze": {
        "chi311_checkpoint": {
            "description": "Checkpoint location for Autoloader streaming state",
            "directories": ["autoloader", "schema"],
        },
    },
    "ml": {
        "chi311_models": {
            "description": "Storage for exported ML models and artifacts",
            "directories": ["prophet", "predictions", "features"],
        },
    },
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helper Functions

# COMMAND ----------

def volume_exists(catalog: str, schema: str, volume: str) -> bool:
    try:
        spark.sql(f"DESCRIBE VOLUME {catalog}.{schema}.{volume}")
        return True
    except Exception as e:
        msg = str(e)
        if "VOLUME_NOT_FOUND" in msg or "does not exist" in msg or "TABLE_OR_VIEW_NOT_FOUND" in msg:
            return False
        raise


def create_volume(catalog: str, schema: str, volume: str, description: str) -> None:
    full = f"{catalog}.{schema}.{volume}"
    safe_desc = description.replace("'", "''")
    spark.sql(f"CREATE VOLUME IF NOT EXISTS {full} COMMENT '{safe_desc}'")
    print(f"  created: {full}")


def drop_volume(catalog: str, schema: str, volume: str) -> None:
    spark.sql(f"DROP VOLUME IF EXISTS {catalog}.{schema}.{volume}")
    print(f"  dropped: {catalog}.{schema}.{volume}")


def create_directory(path: str) -> None:
    dbutils.fs.mkdirs(path)
    print(f"    mkdir: {path}")


def volume_path(catalog: str, schema: str, volume: str) -> str:
    return f"/Volumes/{catalog}/{schema}/{volume}"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Set Catalog Context

# COMMAND ----------

spark.sql(f"USE CATALOG {CATALOG_NAME}")
print(f"Using catalog: {CATALOG_NAME}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Reset Volumes (Optional)

# COMMAND ----------

if RESET_VOLUMES:
    for schema_name, volumes in VOLUMES.items():
        for volume_name in volumes:
            if volume_exists(CATALOG_NAME, schema_name, volume_name):
                drop_volume(CATALOG_NAME, schema_name, volume_name)
else:
    print("Reset mode disabled - existing volumes preserved.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Create Volumes

# COMMAND ----------

for schema_name, volumes in VOLUMES.items():
    print(f"Schema: {schema_name}")
    for volume_name, cfg in volumes.items():
        if volume_exists(CATALOG_NAME, schema_name, volume_name):
            print(f"  exists:  {CATALOG_NAME}.{schema_name}.{volume_name}")
        else:
            create_volume(CATALOG_NAME, schema_name, volume_name, cfg["description"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Create Directory Structure

# COMMAND ----------

for schema_name, volumes in VOLUMES.items():
    for volume_name, cfg in volumes.items():
        base = volume_path(CATALOG_NAME, schema_name, volume_name)
        print(f"  {base}/")
        for directory in cfg.get("directories", []):
            create_directory(f"{base}/{directory}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: Verify

# COMMAND ----------

for schema_name in VOLUMES:
    print(f"Volumes in {CATALOG_NAME}.{schema_name}:")
    display(spark.sql(f"SHOW VOLUMES IN {CATALOG_NAME}.{schema_name}"))

# COMMAND ----------

for schema_name, volumes in VOLUMES.items():
    for volume_name in volumes:
        base = volume_path(CATALOG_NAME, schema_name, volume_name)
        print(f"{base}/")
        try:
            for f in dbutils.fs.ls(base):
                print(f"  |- {f.name}")
        except Exception as e:
            print(f"  (empty or error: {e})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6: Smoke-Test Write

# COMMAND ----------

# Verify we can actually write and read a file. This catches permission
# issues and quota problems early rather than at first real load.
test_path = f"{volume_path(CATALOG_NAME, 'raw', 'chi311_landing')}/.smoke_test"
dbutils.fs.put(test_path, '{"ok": true}', overwrite=True)
assert dbutils.fs.head(test_path).strip() == '{"ok": true}', "Smoke-test readback failed"
dbutils.fs.rm(test_path)
print(f"Smoke test passed: {test_path}")

# COMMAND ----------

dbutils.notebook.exit("SUCCESS")
