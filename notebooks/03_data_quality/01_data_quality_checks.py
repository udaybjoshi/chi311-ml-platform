# Databricks notebook source
# MAGIC %md
# MAGIC # Chicago 311 - Data Quality Checks (Spark-native)
# MAGIC
# MAGIC **Purpose**: Assert completeness, validity, and uniqueness invariants
# MAGIC on the Bronze-staged and Silver-current tables, and write a structured
# MAGIC report to the `ml` schema for downstream monitoring.
# MAGIC
# MAGIC **Design choice for Free Edition**:
# MAGIC - The prior implementation used Great Expectations with a Pandas
# MAGIC   datasource. That works but adds a 100+ MB dependency, pulls data
# MAGIC   into driver memory, and cannot scale beyond serverless memory limits.
# MAGIC - This notebook delegates to `chi311.quality.spark_checks`, which
# MAGIC   are unit-tested Spark SQL predicates. Checks run in-cluster, handle
# MAGIC   arbitrary table sizes, and require no extra `%pip install`s.
# MAGIC - A Great-Expectations-friendly fallback is preserved in the
# MAGIC   `great_expectations/` directory for richer local profiling runs.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Widget Parameters

# COMMAND ----------

dbutils.widgets.text("catalog_name", "workspace", "Catalog Name")
dbutils.widgets.text("pass_threshold", "0.95", "Minimum pass ratio for quality gate")
dbutils.widgets.dropdown("fail_on_gate", "true", ["true", "false"], "Raise on gate failure")

CATALOG = dbutils.widgets.get("catalog_name")
PASS_THRESHOLD = float(dbutils.widgets.get("pass_threshold"))
FAIL_ON_GATE = dbutils.widgets.get("fail_on_gate") == "true"

print(f"Catalog:        {CATALOG}")
print(f"Pass threshold: {PASS_THRESHOLD}")
print(f"Fail on gate:   {FAIL_ON_GATE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Imports
# MAGIC
# MAGIC This notebook assumes the `src/` directory of this repo is on the
# MAGIC cluster's Python path — either because the job is configured with a
# MAGIC Databricks Asset Bundle (see `databricks.yml`) or because the
# MAGIC notebook is running inside a Databricks Git Folder.

# COMMAND ----------

import json
import os
import sys
from datetime import datetime, timezone

# Best-effort: if running from a Git folder, add the repo's src/ to sys.path.
for candidate in ("../../src", "../src", "/Workspace/Repos/src"):
    abs_path = os.path.abspath(candidate)
    if os.path.isdir(abs_path) and abs_path not in sys.path:
        sys.path.insert(0, abs_path)

from chi311.quality import bronze_checks, run_checks, silver_checks  # noqa: E402

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run Bronze Checks

# COMMAND ----------

BRONZE_STAGED = f"{CATALOG}.bronze.bronze_staged_311_requests"
SILVER_CURRENT = f"{CATALOG}.silver.silver_current_311_requests"

df_bronze = spark.table(BRONZE_STAGED)
bronze_results = run_checks(df_bronze, bronze_checks())

print("Bronze results:")
for r in bronze_results:
    flag = "PASS" if r.passed else "FAIL"
    print(f"  [{flag}] {r.check.name}: {r.violations}/{r.total_rows} violations")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run Silver Checks

# COMMAND ----------

df_silver = spark.table(SILVER_CURRENT)
silver_results = run_checks(df_silver, silver_checks())

print("Silver results:")
for r in silver_results:
    flag = "PASS" if r.passed else "FAIL"
    print(f"  [{flag}] {r.check.name}: {r.violations}/{r.total_rows} violations")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Compute Gate

# COMMAND ----------

all_results = bronze_results + silver_results
total = len(all_results)
passed = sum(1 for r in all_results if r.passed)
pass_ratio = passed / total if total else 1.0

print(f"Overall: {passed}/{total} checks passed  (ratio={pass_ratio:.3f})")

critical_failures = [
    r for r in all_results if not r.passed and r.check.severity == "critical"
]
if critical_failures:
    print("\nCritical failures:")
    for r in critical_failures:
        print(f"  - {r.check.name}: {r.violations}/{r.total_rows}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Persist Report

# COMMAND ----------

report_rows = [
    {
        **r.to_dict(),
        "layer": r.check.name.split(".", 1)[0],
        "run_at": datetime.now(timezone.utc),
    }
    for r in all_results
]

report_df = spark.createDataFrame(report_rows)
report_table = f"{CATALOG}.ml.chi311_data_quality_reports"

(
    report_df.write.mode("append")
    .option("mergeSchema", "true")
    .saveAsTable(report_table)
)

print(f"Wrote {len(report_rows)} rows to {report_table}")
display(report_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Gate Decision

# COMMAND ----------

gate_passed = pass_ratio >= PASS_THRESHOLD and not critical_failures

exit_payload = json.dumps(
    {
        "status": "PASSED" if gate_passed else "FAILED",
        "pass_ratio": pass_ratio,
        "total_checks": total,
        "passed_checks": passed,
        "critical_failures": [r.check.name for r in critical_failures],
    }
)

if not gate_passed and FAIL_ON_GATE:
    raise AssertionError(f"Quality gate FAILED: {exit_payload}")

dbutils.notebook.exit(exit_payload)
