# Databricks notebook source
# MAGIC %md
# MAGIC # 01 - Create Catalog and Schemas
# MAGIC 
# MAGIC **Purpose**: Set up Unity Catalog structure for the Chicago 311 project
# MAGIC 
# MAGIC **Methodology**: Following Databricks Free Edition best practices with Unity Catalog
# MAGIC 
# MAGIC **Run**: Once during initial setup
# MAGIC 
# MAGIC **Prerequisites**:
# MAGIC - Databricks Free Edition account
# MAGIC - Unity Catalog enabled (default in Free Edition)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Unity Catalog Structure
# MAGIC 
# MAGIC ```
# MAGIC workspace (catalog)
# MAGIC ├── raw      (schema) - Volumes for raw files
# MAGIC ├── bronze   (schema) - Raw Delta tables from Autoloader
# MAGIC ├── silver   (schema) - Cleaned + SCD2 tables
# MAGIC ├── gold     (schema) - Aggregated tables for analytics
# MAGIC └── ml       (schema) - ML models and predictions
# MAGIC ```
# MAGIC 
# MAGIC **Three-Level Namespace**: `catalog.schema.table`
# MAGIC 
# MAGIC Example: `workspace.silver.silver_scd2_311_requests`

# COMMAND ----------

# MAGIC %md
# MAGIC ## Widget Parameters

# COMMAND ----------

# Create widgets for configuration
dbutils.widgets.text("catalog_name", "workspace", "Catalog Name")
dbutils.widgets.dropdown("reset_schemas", "false", ["true", "false"], "Reset Schemas (DROP ALL)")

# Get widget values
CATALOG_NAME = dbutils.widgets.get("catalog_name")
RESET_SCHEMAS = dbutils.widgets.get("reset_schemas") == "true"

print(f"Catalog Name: {CATALOG_NAME}")
print(f"Reset Schemas: {RESET_SCHEMAS}")

if RESET_SCHEMAS:
    print("\n⚠️ WARNING: Reset mode enabled - existing schemas will be dropped!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

# Schema names following Medallion Architecture
SCHEMAS = {
    "raw": {
        "description": "Raw file storage in Volumes - landing zone for API data",
        "managed_location": None  # Use default managed location
    },
    "bronze": {
        "description": "Raw Delta tables from Autoloader ingestion - data as-is from source",
        "managed_location": None
    },
    "silver": {
        "description": "Cleaned and SCD2 tracked tables - validated and transformed",
        "managed_location": None
    },
    "gold": {
        "description": "Aggregated tables for analytics and ML - business-ready data",
        "managed_location": None
    },
    "ml": {
        "description": "MLflow models, predictions, and feature tables",
        "managed_location": None
    }
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helper Functions

# COMMAND ----------

def catalog_exists(catalog_name: str) -> bool:
    """Check if a catalog exists"""
    try:
        catalogs = spark.sql("SHOW CATALOGS").collect()
        catalog_names = [row.catalog for row in catalogs]
        return catalog_name in catalog_names
    except Exception as e:
        print(f"Error checking catalogs: {e}")
        return False


def schema_exists(catalog_name: str, schema_name: str) -> bool:
    """Check if a schema exists in a catalog"""
    try:
        schemas = spark.sql(f"SHOW SCHEMAS IN {catalog_name}").collect()
        schema_names = [row.databaseName for row in schemas]
        return schema_name in schema_names
    except Exception as e:
        print(f"Error checking schemas: {e}")
        return False


def create_schema(catalog_name: str, schema_name: str, description: str) -> bool:
    """Create a schema with proper error handling"""
    full_name = f"{catalog_name}.{schema_name}"
    try:
        spark.sql(f"""
            CREATE SCHEMA IF NOT EXISTS {full_name}
            COMMENT '{description}'
        """)
        print(f"Created schema: {full_name}")
        return True
    except Exception as e:
        print(f"Failed to create schema {full_name}: {e}")
        return False


def drop_schema(catalog_name: str, schema_name: str) -> bool:
    """Drop a schema and all its contents"""
    full_name = f"{catalog_name}.{schema_name}"
    try:
        spark.sql(f"DROP SCHEMA IF EXISTS {full_name} CASCADE")
        print(f"🗑️ Dropped schema: {full_name}")
        return True
    except Exception as e:
        print(f"Failed to drop schema {full_name}: {e}")
        return False

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Verify Catalog Exists
# MAGIC 
# MAGIC In Databricks Free Edition, the `workspace` catalog is pre-created.

# COMMAND ----------

print(f"Checking catalog: {CATALOG_NAME}")
print("-" * 50)

if catalog_exists(CATALOG_NAME):
    print(f"Catalog '{CATALOG_NAME}' exists")
else:
    print(f"⚠️ Catalog '{CATALOG_NAME}' not found")
    print("Attempting to create...")
    try:
        spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG_NAME}")
        print(f"Created catalog: {CATALOG_NAME}")
    except Exception as e:
        print(f"Failed to create catalog: {e}")
        print("\nNote: In Databricks Free Edition, use the pre-created 'workspace' catalog")
        dbutils.notebook.exit("FAILED: Could not create or find catalog")

# Set as current catalog
spark.sql(f"USE CATALOG {CATALOG_NAME}")
print(f"\n Using catalog: {CATALOG_NAME}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Reset Schemas (Optional)
# MAGIC 
# MAGIC If `reset_schemas` is true, drop all existing schemas first.
# MAGIC 
# MAGIC ⚠️ **WARNING**: This will delete all tables and data in these schemas!

# COMMAND ----------

if RESET_SCHEMAS:
    print("Resetting schemas...")
    print("-" * 50)
    
    # Confirm reset
    confirm = True  # In production, you might want user confirmation
    
    if confirm:
        for schema_name in SCHEMAS.keys():
            if schema_exists(CATALOG_NAME, schema_name):
                drop_schema(CATALOG_NAME, schema_name)
            else:
                print(f"Schema '{schema_name}' doesn't exist, skipping")
    else:
        print("Reset cancelled")
else:
    print("Reset mode disabled - existing schemas will be preserved")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Create Schemas

# COMMAND ----------

print(f"\nCreating schemas in catalog '{CATALOG_NAME}':")
print("-" * 50)

created_count = 0
existing_count = 0
failed_count = 0

for schema_name, config in SCHEMAS.items():
    if schema_exists(CATALOG_NAME, schema_name):
        print(f"⏭️ Schema '{schema_name}' already exists")
        existing_count += 1
    else:
        if create_schema(CATALOG_NAME, schema_name, config["description"]):
            created_count += 1
        else:
            failed_count += 1

print(f"\n{'='*50}")
print(f"Summary: Created={created_count}, Existing={existing_count}, Failed={failed_count}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Verify Setup

# COMMAND ----------

print(f"\n Schemas in catalog '{CATALOG_NAME}':")
print("-" * 60)

# Get all schemas
schemas_df = spark.sql(f"SHOW SCHEMAS IN {CATALOG_NAME}")
display(schemas_df)

# COMMAND ----------

# Detailed schema information
print("\n📊 Schema Details:")
print("-" * 60)

for schema_name in SCHEMAS.keys():
    try:
        desc = spark.sql(f"DESCRIBE SCHEMA EXTENDED {CATALOG_NAME}.{schema_name}").collect()
        print(f"\n{CATALOG_NAME}.{schema_name}:")
        for row in desc:
            print(f"  {row.info_name}: {row.info_value}")
    except Exception as e:
        print(f"\n{CATALOG_NAME}.{schema_name}: Error - {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: Set Default Schema

# COMMAND ----------

# Set bronze as default for most operations
default_schema = "bronze"
spark.sql(f"USE SCHEMA {default_schema}")
print(f"Default schema set to: {CATALOG_NAME}.{default_schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Output: Configuration for Other Notebooks

# COMMAND ----------

# Configuration dictionary for use in other notebooks
config = {
    "catalog": CATALOG_NAME,
    "schemas": {
        "raw": f"{CATALOG_NAME}.raw",
        "bronze": f"{CATALOG_NAME}.bronze",
        "silver": f"{CATALOG_NAME}.silver",
        "gold": f"{CATALOG_NAME}.gold",
        "ml": f"{CATALOG_NAME}.ml"
    },
    "tables": {
        "bronze_raw": f"{CATALOG_NAME}.bronze.bronze_raw_311_requests",
        "silver_scd2": f"{CATALOG_NAME}.silver.silver_scd2_311_requests",
        "silver_current": f"{CATALOG_NAME}.silver.silver_current_311_requests",
        "gold_daily": f"{CATALOG_NAME}.gold.gold_daily_aggregates",
        "gold_citywide": f"{CATALOG_NAME}.gold.gold_citywide_daily_summary"
    }
}

print("📋 Configuration for other notebooks:")
print("-" * 50)
for key, value in config.items():
    print(f"{key}: {value}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary
# MAGIC 
# MAGIC Created Unity Catalog structure for Chicago 311 project:
# MAGIC 
# MAGIC | Schema | Full Path | Purpose |
# MAGIC |--------|-----------|---------|
# MAGIC | `raw` | `workspace.raw` | Volumes for raw JSON files from API |
# MAGIC | `bronze` | `workspace.bronze` | Raw Delta tables (Autoloader output) |
# MAGIC | `silver` | `workspace.silver` | Cleaned data with SCD Type 2 history |
# MAGIC | `gold` | `workspace.gold` | Aggregated tables for dashboards & ML |
# MAGIC | `ml` | `workspace.ml` | MLflow models and predictions |
# MAGIC 
# MAGIC **Next Step**: Run `02_create_volumes.py` to create file storage volumes

# COMMAND ----------

# Return success status
dbutils.notebook.exit("SUCCESS")