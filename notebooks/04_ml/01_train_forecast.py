# Databricks notebook source
# MAGIC %md
# MAGIC # 04.01 - Train Prophet Forecast and Score Anomalies
# MAGIC
# MAGIC **Purpose**: Train a Prophet model on citywide daily service-request
# MAGIC volume, log the run to MLflow, and score the most recent window for
# MAGIC anomalies.
# MAGIC
# MAGIC **Inputs** : `gold_citywide_daily_summary` (ds / y and features).
# MAGIC **Outputs**: MLflow run; `ml.chi311_predictions`; `ml.chi311_anomalies`.
# MAGIC
# MAGIC **Free-Edition notes**:
# MAGIC - Prophet is not pre-installed; we install with `%pip` and restart.
# MAGIC - We use MLflow autolog; no Model Serving endpoint is created
# MAGIC   (limited on Free Edition). Models are registered to UC for later
# MAGIC   batch use.

# COMMAND ----------

# MAGIC %pip install -q prophet==1.1.5

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Widgets

# COMMAND ----------

dbutils.widgets.text("catalog_name", "workspace", "Catalog Name")
dbutils.widgets.text("forecast_horizon_days", "14", "Forecast Horizon (days)")
dbutils.widgets.text("model_name", "chi311_prophet_citywide", "Model name in UC")

CATALOG = dbutils.widgets.get("catalog_name")
HORIZON = int(dbutils.widgets.get("forecast_horizon_days"))
MODEL_NAME = dbutils.widgets.get("model_name")

UC_MODEL_NAME = f"{CATALOG}.ml.{MODEL_NAME}"
GOLD_TABLE = f"{CATALOG}.gold.gold_citywide_daily_summary"
PRED_TABLE = f"{CATALOG}.ml.chi311_predictions"
ANOM_TABLE = f"{CATALOG}.ml.chi311_anomalies"

print(f"Catalog:            {CATALOG}")
print(f"Gold input:         {GOLD_TABLE}")
print(f"Horizon (days):     {HORIZON}")
print(f"UC model name:      {UC_MODEL_NAME}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Imports

# COMMAND ----------

import os
import sys
from datetime import datetime, timezone

# Make chi311 importable when notebook is run from a Git Folder.
for candidate in ("../../src", "../src", "/Workspace/Repos/src"):
    abs_path = os.path.abspath(candidate)
    if os.path.isdir(abs_path) and abs_path not in sys.path:
        sys.path.insert(0, abs_path)

import mlflow
import pandas as pd
from prophet import Prophet

from chi311.ml.forecaster import build_prophet_input, score_anomalies, summarize_anomaly_runs

mlflow.autolog(log_models=False)  # we'll log the Prophet model manually
mlflow.set_registry_uri("databricks-uc")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Gold Input

# COMMAND ----------

gold_pdf = spark.table(GOLD_TABLE).select("ds", "y").toPandas()
train_df = build_prophet_input(gold_pdf.to_dict("records"))

if len(train_df) < 30:
    raise ValueError(
        f"Prophet needs at least ~30 rows; only {len(train_df)} available in {GOLD_TABLE}"
    )

print(f"Training rows: {len(train_df):,}")
print(f"Date range:    {train_df['ds'].min().date()} -> {train_df['ds'].max().date()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Train + Log to MLflow

# COMMAND ----------

with mlflow.start_run(run_name=f"prophet-{datetime.now(timezone.utc).isoformat()}"):
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        interval_width=0.95,
    )
    model.fit(train_df)

    future = model.make_future_dataframe(periods=HORIZON, freq="D")
    forecast = model.predict(future)

    # In-sample eval: MAPE on the last 28 days.
    eval_window = train_df.tail(28).merge(forecast[["ds", "yhat"]], on="ds", how="left")
    if eval_window["y"].min() > 0:
        mape = ((eval_window["y"] - eval_window["yhat"]).abs() / eval_window["y"]).mean()
        mlflow.log_metric("mape_last_28d", float(mape))
        print(f"MAPE (last 28d): {mape:.3f}")

    mlflow.log_param("horizon_days", HORIZON)
    mlflow.log_param("training_rows", len(train_df))
    mlflow.prophet.log_model(
        model, artifact_path="model", registered_model_name=UC_MODEL_NAME
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Persist Predictions + Score Anomalies

# COMMAND ----------

pred_df = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
pred_df["_run_at"] = datetime.now(timezone.utc)

spark.createDataFrame(pred_df).write.mode("overwrite").option(
    "overwriteSchema", "true"
).saveAsTable(PRED_TABLE)
print(f"Wrote {len(pred_df):,} rows to {PRED_TABLE}")

# COMMAND ----------

scored = score_anomalies(train_df, forecast)
anomaly_df = scored.loc[scored["is_anomaly"]].copy()
anomaly_df["_run_at"] = datetime.now(timezone.utc)

if len(anomaly_df):
    spark.createDataFrame(anomaly_df[[
        "ds", "actual", "yhat", "yhat_lower", "yhat_upper",
        "anomaly_score", "_run_at",
    ]]).write.mode("append").option("mergeSchema", "true").saveAsTable(ANOM_TABLE)

runs = summarize_anomaly_runs(scored)
print(f"Anomaly days: {len(anomaly_df)}; runs: {len(runs)}")
for r in runs[-5:]:
    print(f"  {r['start'].date()} -> {r['end'].date()} (peak={r['peak_actual']:.0f})")

# COMMAND ----------

dbutils.notebook.exit(
    f"SUCCESS: {len(pred_df)} predictions, {len(anomaly_df)} anomalies"
)
