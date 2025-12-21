# Databricks notebook source
# MAGIC %md
# MAGIC # Chicago 311 - Data Quality Checks with Great Expectations
# MAGIC 
# MAGIC **Purpose**: Comprehensive data validation using Great Expectations framework
# MAGIC 
# MAGIC **Framework Component**: Data Sourcing (Component 2) - Quality Validation
# MAGIC 
# MAGIC ## Findings from 00_setup_exploration.py
# MAGIC 
# MAGIC | Finding | Value | Implication |
# MAGIC |---------|-------|-------------|
# MAGIC | Null rates | Most fields <1% | Use strict `mostly=0.99` thresholds |
# MAGIC | Status values | Open, Completed, Canceled | 3 values only (note: Canceled, not Cancelled) |
# MAGIC | Ward | Numeric 1-50 | Chicago has 50 wards, not boroughs |
# MAGIC | Coordinates | 41.6-42.1 lat, -87.95 to -87.5 lon | Chicago bounding box |
# MAGIC | Duplicates | 0% | sr_number is unique |
# MAGIC | Info calls | 40% of volume | "311 INFORMATION ONLY CALL" in Ward 28 |
# MAGIC 
# MAGIC ## Quality Dimensions
# MAGIC 1. **Completeness**: Are required fields populated?
# MAGIC 2. **Validity**: Are values within expected ranges?
# MAGIC 3. **Consistency**: Do related fields align?
# MAGIC 4. **Timeliness**: Is data fresh?
# MAGIC 5. **Uniqueness**: Are there duplicates?

# COMMAND ----------

# MAGIC %pip install great_expectations==0.18.8

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import *
from datetime import datetime, timedelta
import json

import great_expectations as gx
from great_expectations.core import ExpectationSuite, ExpectationConfiguration

print(f"Great Expectations version: {gx.__version__}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Initialize Great Expectations Context
# MAGIC 
# MAGIC We use an **Ephemeral Data Context** which is ideal for Databricks notebooks.
# MAGIC It doesn't require persistent storage and works entirely in memory.

# COMMAND ----------

# Create ephemeral context (no persistent storage needed)
context = gx.get_context()

print("✓ Great Expectations context initialized")
print(f"  Context type: {type(context).__name__}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Load Sample Data
# MAGIC 
# MAGIC Load data from the Chicago Data Portal API for validation testing.

# COMMAND ----------

import requests
import pandas as pd

API_URL = "https://data.cityofchicago.org/resource/v6vf-nfxy.json"
params = {
    "$limit": 50000,
    "$order": "created_date DESC",
    "$where": f"created_date >= '{(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')}'"
}

print(f"Fetching data from Chicago Data Portal API...")
response = requests.get(API_URL, params=params)
pdf = pd.DataFrame(response.json())

# Convert to Spark DataFrame
df = spark.createDataFrame(pdf)

# Cast date columns to proper types
df = (df
    .withColumn("created_date", F.to_timestamp("created_date"))
    .withColumn("closed_date", F.to_timestamp("closed_date"))
    .withColumn("last_modified_date", F.to_timestamp("last_modified_date"))
    .withColumn("latitude", F.col("latitude").cast("double"))
    .withColumn("longitude", F.col("longitude").cast("double"))
    .withColumn("ward", F.col("ward").cast("integer"))
)

print(f"✓ Loaded {df.count():,} records")
df.printSchema()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Define Expectation Suites
# MAGIC 
# MAGIC Based on findings from `00_setup_exploration.py`:
# MAGIC - **Bronze**: Raw data validation (lenient) - validates API response
# MAGIC - **Silver**: Cleaned data validation (strict) - validates after transformations
# MAGIC - **Gold**: Aggregated data validation (business rules)
# MAGIC 
# MAGIC ### Key Thresholds from Exploration
# MAGIC 
# MAGIC | Field | Null Rate | Threshold |
# MAGIC |-------|-----------|-----------|
# MAGIC | sr_number | 0.0% | 100% (critical) |
# MAGIC | created_date | 0.0% | 100% (critical) |
# MAGIC | sr_type | 0.0% | 100% (critical) |
# MAGIC | status | 0.0% | 100% (critical) |
# MAGIC | ward | 0.2% | mostly=0.99 |
# MAGIC | latitude/longitude | 0.2% | mostly=0.99 |
# MAGIC | zip_code | 13.1% | mostly=0.85 |
# MAGIC | closed_date | 15.3% | mostly=0.85 (expected for open requests) |

# COMMAND ----------

# MAGIC %md
# MAGIC ### Bronze Layer Expectations

# COMMAND ----------

# Create Bronze expectation suite
bronze_suite = context.add_or_update_expectation_suite(
    expectation_suite_name="bronze_311_requests_suite"
)

# ============================================
# SCHEMA EXPECTATIONS
# ============================================
for col in ["sr_number", "created_date", "sr_type", "status", "ward", "latitude", "longitude"]:
    bronze_suite.add_expectation(
        ExpectationConfiguration(
            expectation_type="expect_column_to_exist",
            kwargs={"column": col}
        )
    )

# ============================================
# COMPLETENESS EXPECTATIONS (from exploration findings)
# ============================================

# Critical fields - 0% null rate observed
bronze_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_not_be_null",
        kwargs={"column": "sr_number"},
        meta={"dimension": "completeness", "severity": "critical", "observed_null_rate": "0.0%"}
    )
)
bronze_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_not_be_null",
        kwargs={"column": "created_date"},
        meta={"dimension": "completeness", "severity": "critical", "observed_null_rate": "0.0%"}
    )
)
bronze_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_not_be_null",
        kwargs={"column": "sr_type"},
        meta={"dimension": "completeness", "severity": "critical", "observed_null_rate": "0.0%"}
    )
)
bronze_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_not_be_null",
        kwargs={"column": "status"},
        meta={"dimension": "completeness", "severity": "critical", "observed_null_rate": "0.0%"}
    )
)

# Near-critical fields - <1% null rate observed
bronze_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_not_be_null",
        kwargs={"column": "ward", "mostly": 0.99},
        meta={"dimension": "completeness", "severity": "warning", "observed_null_rate": "0.2%"}
    )
)
bronze_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_not_be_null",
        kwargs={"column": "latitude", "mostly": 0.99},
        meta={"dimension": "completeness", "severity": "warning", "observed_null_rate": "0.2%"}
    )
)
bronze_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_not_be_null",
        kwargs={"column": "longitude", "mostly": 0.99},
        meta={"dimension": "completeness", "severity": "warning", "observed_null_rate": "0.2%"}
    )
)

# Expected nullable fields
bronze_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_not_be_null",
        kwargs={"column": "closed_date", "mostly": 0.80},
        meta={"dimension": "completeness", "severity": "info", "observed_null_rate": "15.3%", 
              "notes": "Nulls expected for open requests"}
    )
)

# ============================================
# UNIQUENESS EXPECTATIONS
# ============================================
bronze_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_be_unique",
        kwargs={"column": "sr_number"},
        meta={"dimension": "uniqueness", "severity": "warning", "observed_duplicate_rate": "0.0%"}
    )
)

# ============================================
# VALIDITY EXPECTATIONS - Status (from exploration)
# Chicago 311 uses: Open, Completed, Canceled (note: one 'l')
# ============================================
bronze_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_be_in_set",
        kwargs={
            "column": "status",
            "value_set": ["Open", "Completed", "Canceled"],
            "mostly": 0.99
        },
        meta={"dimension": "validity", "severity": "critical", 
              "notes": "Chicago uses 'Canceled' (one L), not 'Cancelled'"}
    )
)

# ============================================
# VALIDITY EXPECTATIONS - Ward (Chicago has 50 wards)
# ============================================
bronze_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_be_between",
        kwargs={"column": "ward", "min_value": 1, "max_value": 50, "mostly": 0.95},
        meta={"dimension": "validity", "severity": "warning", "notes": "Chicago has 50 wards"}
    )
)

# ============================================
# VALIDITY EXPECTATIONS - Chicago bounding box
# ============================================
bronze_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_be_between",
        kwargs={"column": "latitude", "min_value": 41.6, "max_value": 42.1, "mostly": 0.95},
        meta={"dimension": "validity", "severity": "warning", "notes": "Chicago latitude bounds"}
    )
)
bronze_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_be_between",
        kwargs={"column": "longitude", "min_value": -87.95, "max_value": -87.5, "mostly": 0.95},
        meta={"dimension": "validity", "severity": "warning", "notes": "Chicago longitude bounds"}
    )
)

# ============================================
# VOLUME EXPECTATIONS
# ============================================
bronze_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_table_row_count_to_be_between",
        kwargs={"min_value": 1000},
        meta={"dimension": "completeness", "severity": "critical"}
    )
)

print(f"✓ Bronze suite created with {len(bronze_suite.expectations)} expectations")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Silver Layer Expectations
# MAGIC 
# MAGIC Silver layer has stricter expectations after data cleaning:
# MAGIC - All nulls in required fields removed
# MAGIC - Coordinates validated
# MAGIC - Status standardized to uppercase

# COMMAND ----------

# Create Silver expectation suite (stricter than Bronze)
silver_suite = context.add_or_update_expectation_suite(
    expectation_suite_name="silver_311_requests_suite"
)

# ============================================
# COMPLETENESS - All required fields must be 100% non-null
# ============================================
for col in ["sr_number", "created_date", "sr_type", "status", "ward"]:
    silver_suite.add_expectation(
        ExpectationConfiguration(
            expectation_type="expect_column_values_to_not_be_null",
            kwargs={"column": col},
            meta={"dimension": "completeness", "severity": "critical"}
        )
    )

# ============================================
# VALIDITY - Standardized status values (uppercase)
# ============================================
silver_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_be_in_set",
        kwargs={
            "column": "status",
            "value_set": ["OPEN", "COMPLETED", "CANCELED"]
        },
        meta={"dimension": "validity", "severity": "critical", 
              "notes": "Standardized to uppercase in Silver layer"}
    )
)

# ============================================
# VALIDITY - Ward range (stricter in Silver)
# ============================================
silver_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_be_between",
        kwargs={"column": "ward", "min_value": 1, "max_value": 50, "mostly": 0.99},
        meta={"dimension": "validity", "severity": "critical"}
    )
)

# ============================================
# VALIDITY - Coordinates (stricter in Silver)
# ============================================
silver_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_be_between",
        kwargs={"column": "latitude", "min_value": 41.6, "max_value": 42.1, "mostly": 0.99},
        meta={"dimension": "validity", "severity": "critical"}
    )
)
silver_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_be_between",
        kwargs={"column": "longitude", "min_value": -87.95, "max_value": -87.5, "mostly": 0.99},
        meta={"dimension": "validity", "severity": "critical"}
    )
)

# ============================================
# UNIQUENESS
# ============================================
silver_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_column_values_to_be_unique",
        kwargs={"column": "sr_number"},
        meta={"dimension": "uniqueness", "severity": "critical"}
    )
)

# ============================================
# VOLUME
# ============================================
silver_suite.add_expectation(
    ExpectationConfiguration(
        expectation_type="expect_table_row_count_to_be_between",
        kwargs={"min_value": 1000},
        meta={"dimension": "completeness", "severity": "critical"}
    )
)

print(f"✓ Silver suite created with {len(silver_suite.expectations)} expectations")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Create Data Source and Batch

# COMMAND ----------

# Create a pandas datasource
datasource = context.sources.add_or_update_spark(name="chi311_spark")

# Add data asset for Bronze layer
data_asset = datasource.add_dataframe_asset(name="chi311_bronze_data")

# Build batch request
batch_request = data_asset.build_batch_request(dataframe=df)

print("✓ Data source configured")
print(f"  Datasource: chi311_spark")
print(f"  Asset: chi311_bronze_data")
print(f"  Records: {df.count():,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Run Validation - Bronze Layer

# COMMAND ----------

# Get validator for Bronze suite
bronze_validator = context.get_validator(
    batch_request=batch_request,
    expectation_suite_name="bronze_311_requests_suite"
)

# Run validation
bronze_results = bronze_validator.validate()

print("=" * 60)
print("BRONZE LAYER VALIDATION RESULTS")
print("=" * 60)
print(f"Overall Success: {'✓ PASSED' if bronze_results.success else '✗ FAILED'}")
print(f"Evaluated Expectations: {bronze_results.statistics['evaluated_expectations']}")
print(f"Successful: {bronze_results.statistics['successful_expectations']}")
print(f"Failed: {bronze_results.statistics['unsuccessful_expectations']}")
print(f"Success Rate: {bronze_results.statistics['success_percent']:.1f}%")

# COMMAND ----------

# Detailed Bronze results
bronze_details = []
for result in bronze_results.results:
    exp_type = result.expectation_config.expectation_type
    kwargs = result.expectation_config.kwargs
    column = kwargs.get("column", "table")
    success = "✓" if result.success else "✗"
    
    # Get observed value
    observed = result.result.get("observed_value", "N/A")
    if isinstance(observed, float):
        observed = f"{observed:.2%}" if observed <= 1 else f"{observed:,.0f}"
    
    bronze_details.append({
        "status": success,
        "expectation": exp_type.replace("expect_", ""),
        "column": column,
        "observed": str(observed)[:50],
        "success": result.success
    })

bronze_details_df = spark.createDataFrame(bronze_details)
display(bronze_details_df.orderBy("success", "column"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Run Validation - Silver Layer
# MAGIC 
# MAGIC Apply Silver layer transformations based on exploration findings:
# MAGIC 1. Standardize status to uppercase
# MAGIC 2. Filter invalid coordinates
# MAGIC 3. Remove rows without required fields

# COMMAND ----------

# Simulate Silver layer transformations
df_silver = (df
    # Standardize status to uppercase
    .withColumn("status", F.upper(F.col("status")))
    
    # Filter coordinates to Chicago bounds
    .withColumn("latitude",
        F.when(
            (F.col("latitude").between(41.6, 42.1)) & 
            (F.col("longitude").between(-87.95, -87.5)),
            F.col("latitude")
        )
    )
    .withColumn("longitude",
        F.when(
            F.col("latitude").isNotNull(),
            F.col("longitude")
        )
    )
    
    # Drop rows without required fields
    .filter(F.col("sr_number").isNotNull())
    .filter(F.col("created_date").isNotNull())
    .filter(F.col("sr_type").isNotNull())
    .filter(F.col("status").isNotNull())
    .filter(F.col("ward").isNotNull())
)

print(f"Silver layer: {df_silver.count():,} rows (from {df.count():,} Bronze rows)")
print(f"Rows filtered: {df.count() - df_silver.count():,}")

# COMMAND ----------

# Create new batch for Silver data
silver_asset = datasource.add_dataframe_asset(name="chi311_silver_data")
silver_batch = silver_asset.build_batch_request(dataframe=df_silver)

# Get validator for Silver suite
silver_validator = context.get_validator(
    batch_request=silver_batch,
    expectation_suite_name="silver_311_requests_suite"
)

# Run validation
silver_results = silver_validator.validate()

print("=" * 60)
print("SILVER LAYER VALIDATION RESULTS")
print("=" * 60)
print(f"Overall Success: {'✓ PASSED' if silver_results.success else '✗ FAILED'}")
print(f"Evaluated Expectations: {silver_results.statistics['evaluated_expectations']}")
print(f"Successful: {silver_results.statistics['successful_expectations']}")
print(f"Failed: {silver_results.statistics['unsuccessful_expectations']}")
print(f"Success Rate: {silver_results.statistics['success_percent']:.1f}%")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Failed Expectations Analysis

# COMMAND ----------

# Collect all failed expectations
failed_expectations = []

for result in bronze_results.results:
    if not result.success:
        failed_expectations.append({
            "layer": "Bronze",
            "expectation": result.expectation_config.expectation_type,
            "column": result.expectation_config.kwargs.get("column", "table"),
            "details": str(result.result)[:200]
        })

for result in silver_results.results:
    if not result.success:
        failed_expectations.append({
            "layer": "Silver",
            "expectation": result.expectation_config.expectation_type,
            "column": result.expectation_config.kwargs.get("column", "table"),
            "details": str(result.result)[:200]
        })

if failed_expectations:
    print("FAILED EXPECTATIONS:")
    print("-" * 60)
    for exp in failed_expectations:
        print(f"\n❌ [{exp['layer']}] {exp['expectation']}")
        print(f"   Column: {exp['column']}")
        print(f"   Details: {exp['details']}")
else:
    print("✓ All expectations passed!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Data Quality Insights from Exploration
# MAGIC 
# MAGIC ### Key Findings to Remember
# MAGIC 
# MAGIC | Finding | Value | Action |
# MAGIC |---------|-------|--------|
# MAGIC | Info calls | 40% of volume | Filter for forecasting: `sr_type != '311 INFORMATION ONLY CALL'` |
# MAGIC | Ward 28 dominance | 39% of requests | Due to info calls being assigned there |
# MAGIC | Instant closures | 82% resolve in 0 hours | Many are info calls or same-day service |
# MAGIC | Status values | Only 3 values | Simpler than expected SCD2 model |
# MAGIC | Weekend drop | 35-40% | Strong weekly seasonality for Prophet |

# COMMAND ----------

# Optional: Filter for service requests only (excluding info calls)
df_service_only = df.filter(F.col("sr_type") != "311 INFORMATION ONLY CALL")

print("SERVICE REQUESTS (excluding info calls):")
print(f"  All requests: {df.count():,}")
print(f"  Service requests: {df_service_only.count():,}")
print(f"  Info calls removed: {df.count() - df_service_only.count():,} ({(df.count() - df_service_only.count())/df.count()*100:.1f}%)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Generate Quality Report Summary

# COMMAND ----------

# Create summary report
report = {
    "run_timestamp": datetime.now().isoformat(),
    "bronze": {
        "success": bronze_results.success,
        "total_expectations": bronze_results.statistics['evaluated_expectations'],
        "passed": bronze_results.statistics['successful_expectations'],
        "failed": bronze_results.statistics['unsuccessful_expectations'],
        "success_rate": bronze_results.statistics['success_percent'],
        "row_count": df.count()
    },
    "silver": {
        "success": silver_results.success,
        "total_expectations": silver_results.statistics['evaluated_expectations'],
        "passed": silver_results.statistics['successful_expectations'],
        "failed": silver_results.statistics['unsuccessful_expectations'],
        "success_rate": silver_results.statistics['success_percent'],
        "row_count": df_silver.count()
    },
    "data_insights": {
        "total_records": df.count(),
        "service_requests": df_service_only.count(),
        "info_calls": df.count() - df_service_only.count(),
        "pct_info_calls": (df.count() - df_service_only.count()) / df.count() * 100
    }
}

print("=" * 60)
print("DATA QUALITY REPORT SUMMARY")
print("=" * 60)
print(f"Run Time: {report['run_timestamp']}")
print()
print("Bronze Layer:")
print(f"  Status: {'✓ PASSED' if report['bronze']['success'] else '✗ FAILED'}")
print(f"  Rows: {report['bronze']['row_count']:,}")
print(f"  Expectations: {report['bronze']['passed']}/{report['bronze']['total_expectations']} passed ({report['bronze']['success_rate']:.1f}%)")
print()
print("Silver Layer:")
print(f"  Status: {'✓ PASSED' if report['silver']['success'] else '✗ FAILED'}")
print(f"  Rows: {report['silver']['row_count']:,}")
print(f"  Expectations: {report['silver']['passed']}/{report['silver']['total_expectations']} passed ({report['silver']['success_rate']:.1f}%)")
print()
print("Data Insights:")
print(f"  Service Requests: {report['data_insights']['service_requests']:,}")
print(f"  Info Calls: {report['data_insights']['info_calls']:,} ({report['data_insights']['pct_info_calls']:.1f}%)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Save Validation Results

# COMMAND ----------

# Convert report to DataFrame for storage
report_df = spark.createDataFrame([{
    "run_timestamp": report["run_timestamp"],
    "bronze_success": report["bronze"]["success"],
    "bronze_pass_rate": report["bronze"]["success_rate"],
    "bronze_row_count": report["bronze"]["row_count"],
    "silver_success": report["silver"]["success"],
    "silver_pass_rate": report["silver"]["success_rate"],
    "silver_row_count": report["silver"]["row_count"],
    "service_request_count": report["data_insights"]["service_requests"],
    "info_call_count": report["data_insights"]["info_calls"],
    "report_json": json.dumps(report)
}])

# Uncomment to save to Unity Catalog (after creating schema)
# spark.sql("CREATE SCHEMA IF NOT EXISTS main.chi311")
# report_df.write.format("delta").mode("append").saveAsTable("main.chi311.data_quality_reports")

display(report_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 11. Quality Gate Decision

# COMMAND ----------

# Define quality gate thresholds
QUALITY_GATE_THRESHOLD = 80.0  # Minimum pass rate

bronze_passed = report["bronze"]["success_rate"] >= QUALITY_GATE_THRESHOLD
silver_passed = report["silver"]["success_rate"] >= QUALITY_GATE_THRESHOLD
overall_passed = bronze_passed and silver_passed

print("=" * 60)
print("QUALITY GATE EVALUATION")
print("=" * 60)
print(f"Threshold: {QUALITY_GATE_THRESHOLD}%")
print()
print(f"Bronze: {'✓ PASSED' if bronze_passed else '✗ FAILED'} ({report['bronze']['success_rate']:.1f}%)")
print(f"Silver: {'✓ PASSED' if silver_passed else '✗ FAILED'} ({report['silver']['success_rate']:.1f}%)")
print()

if overall_passed:
    print("✓ QUALITY GATE PASSED")
    print("  Data is ready for downstream processing.")
    dbutils.notebook.exit(json.dumps({"status": "PASSED", "report": report}))
else:
    print("✗ QUALITY GATE FAILED")
    print("  Review failed expectations before proceeding.")
    # Optionally fail the notebook
    # raise Exception(f"Quality gate failed")
    dbutils.notebook.exit(json.dumps({"status": "FAILED", "report": report}))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next Steps
# MAGIC 
# MAGIC **If quality gate passed:**
# MAGIC 1. Run **Feature Engineering** (Notebook 02)
# MAGIC 2. Data is ready for ML pipeline
# MAGIC 
# MAGIC **If quality gate failed:**
# MAGIC 1. Review failed expectations above
# MAGIC 2. Investigate data source issues
# MAGIC 3. Update cleaning logic in pipeline
# MAGIC 
# MAGIC ## Key Thresholds (from 00_setup_exploration.py)
# MAGIC 
# MAGIC | Layer | Field | Expectation | Threshold |
# MAGIC |-------|-------|-------------|-----------|
# MAGIC | Bronze | sr_number | not_null | 100% |
# MAGIC | Bronze | status | in_set | ["Open", "Completed", "Canceled"] |
# MAGIC | Bronze | ward | between | 1-50, mostly=0.95 |
# MAGIC | Bronze | latitude | between | 41.6-42.1, mostly=0.95 |
# MAGIC | Silver | status | in_set | ["OPEN", "COMPLETED", "CANCELED"] |
# MAGIC | Silver | all fields | not_null | 100% |
# MAGIC 
# MAGIC ## Great Expectations Resources
# MAGIC - [GE Documentation](https://docs.greatexpectations.io/)
# MAGIC - [Expectation Gallery](https://greatexpectations.io/expectations/)
# MAGIC - [GE with Databricks](https://docs.greatexpectations.io/docs/deployment_patterns/how_to_use_great_expectations_in_databricks/)
