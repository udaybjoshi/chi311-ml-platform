# Databricks notebook source
# MAGIC %md
# MAGIC # 05.00 - Run Full Pipeline (manual entry point)
# MAGIC
# MAGIC **Purpose**: Human-runnable entrypoint that chains the four stages
# MAGIC in order. Intended for ad-hoc runs / smoke tests from the UI; the
# MAGIC scheduled production run goes through the serverless Job defined
# MAGIC in `databricks.yml`.
# MAGIC
# MAGIC Stages:
# MAGIC 1. API -> Landing Volume (incremental)
# MAGIC 2. Landing -> Bronze (Autoloader)
# MAGIC 3. Data-quality gate on Bronze/Silver
# MAGIC 4. Train forecast + score anomalies
# MAGIC
# MAGIC The DLT pipeline (Silver + Gold) is triggered by the Job task
# MAGIC before step 3; when running this entrypoint interactively, start
# MAGIC the DLT pipeline manually between steps 2 and 3.

# COMMAND ----------

dbutils.widgets.text("catalog_name", "workspace", "Catalog")
dbutils.widgets.dropdown("load_type", "incremental", ["initial", "incremental"], "Load type")
dbutils.widgets.text("days_back", "1", "Incremental days back")

CATALOG = dbutils.widgets.get("catalog_name")
LOAD_TYPE = dbutils.widgets.get("load_type")
DAYS_BACK = dbutils.widgets.get("days_back")

common_args = {"catalog_name": CATALOG}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stage 1: Ingest API -> Landing Volume

# COMMAND ----------

result = dbutils.notebook.run(
    "../02_ingestion/01_api_to_volume",
    timeout_seconds=60 * 30,
    arguments={**common_args, "load_type": LOAD_TYPE, "days_back": DAYS_BACK},
)
print(f"Stage 1 (API -> Volume): {result}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stage 2: Autoloader -> Bronze Delta

# COMMAND ----------

result = dbutils.notebook.run(
    "../02_ingestion/02_bronze_autoloader",
    timeout_seconds=60 * 30,
    arguments={**common_args, "source_path": "all"},
)
print(f"Stage 2 (Autoloader -> Bronze): {result}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stage 3: Data Quality Gate
# MAGIC
# MAGIC Assumes the DLT pipeline has already produced the Silver + Gold
# MAGIC tables (run it from the Workflows UI between stages 2 and 3, or
# MAGIC rely on the Job task defined in `databricks.yml`).

# COMMAND ----------

result = dbutils.notebook.run(
    "../03_data_quality/01_data_quality_checks",
    timeout_seconds=60 * 15,
    arguments={**common_args, "fail_on_gate": "true"},
)
print(f"Stage 3 (Data Quality): {result}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stage 4: Train Forecast + Score Anomalies

# COMMAND ----------

result = dbutils.notebook.run(
    "../04_ml/01_train_forecast",
    timeout_seconds=60 * 45,
    arguments=common_args,
)
print(f"Stage 4 (Forecast): {result}")

# COMMAND ----------

dbutils.notebook.exit("SUCCESS: all stages completed")
