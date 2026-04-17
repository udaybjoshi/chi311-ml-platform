# Databricks notebook source
# MAGIC %md
# MAGIC # 01 - Create Catalog and Schemas
# MAGIC
# MAGIC **Purpose**: Set up Unity Catalog schema structure for the Chicago 311 project.
# MAGIC
# MAGIC **Runtime**: Databricks Free Edition (serverless) or any workspace with Unity Catalog.
# MAGIC
# MAGIC **Run**: Once during initial setup.
# MAGIC
# MAGIC **Free-Edition constraints honored here**:
# MAGIC - We do NOT attempt `CREATE CATALOG` — Free Edition ships with a
# MAGIC   pre-created `workspace` catalog and account-level catalog creation
# MAGIC   privileges are not granted. We fail fast if the catalog is missing.
# MAGIC - Only `USE CATALOG` / `CREATE SCHEMA` / `DESCRIBE SCHEMA` are used;
# MAGIC   all are supported on serverless SQL/PySpark.
# MAGIC - No managed-location arguments — Free Edition uses a single managed
# MAGIC   storage location per catalog.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Unity Catalog Structure
# MAGIC
# MAGIC ```
# MAGIC workspace (catalog)         <- Free-Edition default
# MAGIC ├── raw      (schema)       <- Volumes for raw API files
# MAGIC ├── bronze   (schema)       <- Raw Delta tables (Autoloader output)
# MAGIC ├── silver   (schema)       <- Cleaned + SCD2 tables
# MAGIC ├── gold     (schema)       <- Aggregates for analytics / ML
# MAGIC └── ml       (schema)       <- MLflow predictions / features
# MAGIC ```
# MAGIC
# MAGIC Three-level namespace: `catalog.schema.table`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Widget Parameters

# COMMAND ----------

dbutils.widgets.text("catalog_name", "workspace", "Catalog Name")
dbutils.widgets.dropdown("reset_schemas", "false", ["true", "false"], "Reset Schemas (DROP ALL)")

CATALOG_NAME = dbutils.widgets.get("catalog_name")
RESET_SCHEMAS = dbutils.widgets.get("reset_schemas") == "true"

print(f"Catalog Name:  {CATALOG_NAME}")
print(f"Reset Schemas: {RESET_SCHEMAS}")
if RESET_SCHEMAS:
    print("\nWARNING: Reset mode enabled - existing schemas will be dropped (CASCADE).")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

# Schema names follow Medallion Architecture + dedicated ML namespace.
SCHEMAS = {
    "raw":    "Raw file storage in Volumes - landing zone for API data",
    "bronze": "Raw Delta tables from Autoloader ingestion - data as-is from source",
    "silver": "Cleaned and SCD2-tracked tables - validated and transformed",
    "gold":   "Aggregated tables for analytics and ML - business-ready data",
    "ml":     "MLflow predictions and feature tables",
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helper Functions

# COMMAND ----------

def catalog_exists(catalog_name: str) -> bool:
    rows = spark.sql("SHOW CATALOGS").collect()
    return catalog_name in {row.catalog for row in rows}


def schema_exists(catalog_name: str, schema_name: str) -> bool:
    rows = spark.sql(f"SHOW SCHEMAS IN {catalog_name}").collect()
    # Column is `databaseName` in Spark; defensive lookup for both names.
    names = {getattr(row, "databaseName", None) or getattr(row, "namespace", None) for row in rows}
    return schema_name in names


def create_schema(catalog_name: str, schema_name: str, description: str) -> None:
    full = f"{catalog_name}.{schema_name}"
    spark.sql(
        f"CREATE SCHEMA IF NOT EXISTS {full} COMMENT '{description.replace(chr(39), chr(39)*2)}'"
    )
    print(f"  created: {full}")


def drop_schema(catalog_name: str, schema_name: str) -> None:
    full = f"{catalog_name}.{schema_name}"
    spark.sql(f"DROP SCHEMA IF EXISTS {full} CASCADE")
    print(f"  dropped: {full}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Verify Catalog Exists
# MAGIC
# MAGIC Free Edition does not allow catalog creation. If the catalog is
# MAGIC missing we fail fast with a clear message rather than silently creating
# MAGIC something the user cannot manage.

# COMMAND ----------

if not catalog_exists(CATALOG_NAME):
    dbutils.notebook.exit(
        f"FAILED: catalog '{CATALOG_NAME}' does not exist. "
        "On Databricks Free Edition use the pre-created 'workspace' catalog."
    )

spark.sql(f"USE CATALOG {CATALOG_NAME}")
print(f"Using catalog: {CATALOG_NAME}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Reset Schemas (Optional)

# COMMAND ----------

if RESET_SCHEMAS:
    print("Resetting schemas (CASCADE):")
    for schema_name in SCHEMAS:
        if schema_exists(CATALOG_NAME, schema_name):
            drop_schema(CATALOG_NAME, schema_name)
        else:
            print(f"  skip (missing): {CATALOG_NAME}.{schema_name}")
else:
    print("Reset mode disabled - existing schemas preserved.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Create Schemas

# COMMAND ----------

created, existing = 0, 0
for schema_name, description in SCHEMAS.items():
    if schema_exists(CATALOG_NAME, schema_name):
        print(f"  exists: {CATALOG_NAME}.{schema_name}")
        existing += 1
    else:
        create_schema(CATALOG_NAME, schema_name, description)
        created += 1

print(f"\nSummary: created={created}, existing={existing}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Verify

# COMMAND ----------

display(spark.sql(f"SHOW SCHEMAS IN {CATALOG_NAME}"))

for schema_name in SCHEMAS:
    count = spark.sql(f"SHOW TABLES IN {CATALOG_NAME}.{schema_name}").count()
    print(f"  {CATALOG_NAME}.{schema_name}: {count} tables")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Output: Configuration for Other Notebooks

# COMMAND ----------

config = {
    "catalog": CATALOG_NAME,
    "schemas": {s: f"{CATALOG_NAME}.{s}" for s in SCHEMAS},
    "tables": {
        "bronze_raw":      f"{CATALOG_NAME}.bronze.bronze_raw_311_requests",
        "bronze_staged":   f"{CATALOG_NAME}.bronze.bronze_staged_311_requests",
        "silver_scd2":     f"{CATALOG_NAME}.silver.silver_scd2_311_requests",
        "silver_current":  f"{CATALOG_NAME}.silver.silver_current_311_requests",
        "gold_daily":      f"{CATALOG_NAME}.gold.gold_daily_aggregates",
        "gold_citywide":   f"{CATALOG_NAME}.gold.gold_citywide_daily_summary",
    },
}

print("Config for downstream notebooks:")
for k, v in config.items():
    print(f"  {k}: {v}")

# COMMAND ----------

dbutils.notebook.exit("SUCCESS")
