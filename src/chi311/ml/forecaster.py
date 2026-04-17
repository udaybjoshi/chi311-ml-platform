"""Prophet-friendly helpers.

The actual Prophet model is trained inside the Databricks notebook so that
MLflow autolog captures the run. This module only holds the pieces that
can be unit-tested without importing Prophet itself (which is heavy and
has native deps).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd


@dataclass
class ForecastResult:
    """Prediction for a single day with uncertainty band + anomaly flag."""

    ds: pd.Timestamp
    yhat: float
    yhat_lower: float
    yhat_upper: float
    actual: float | None = None

    @property
    def is_anomaly(self) -> bool:
        """True when observed volume exceeds the upper 95% band."""
        if self.actual is None:
            return False
        return bool(self.actual > self.yhat_upper)

    @property
    def anomaly_score(self) -> float | None:
        """Relative magnitude of the exceedance. None if no actual value."""
        if self.actual is None or self.yhat_upper <= 0:
            return None
        return (self.actual - self.yhat_upper) / self.yhat_upper


def build_prophet_input(
    rows: Iterable[dict],
    ds_column: str = "ds",
    y_column: str = "y",
) -> pd.DataFrame:
    """Build the canonical Prophet frame (`ds` date + `y` float).

    Accepts any iterable of row-dicts (e.g. `.collect()` on a Spark
    DataFrame converted to dicts, or a pandas.DataFrame.to_dict('records')).
    Dedupes on `ds` by summing `y`, sorts ascending, and coerces `ds` to
    timestamp. Prophet is brittle about duplicate dates and unsorted input,
    so we normalise here.
    """
    df = pd.DataFrame(list(rows))
    if df.empty:
        return pd.DataFrame(columns=["ds", "y"])

    out = df[[ds_column, y_column]].rename(columns={ds_column: "ds", y_column: "y"})
    out["ds"] = pd.to_datetime(out["ds"])
    out["y"] = pd.to_numeric(out["y"], errors="coerce")
    out = out.dropna(subset=["ds", "y"])

    out = out.groupby("ds", as_index=False)["y"].sum().sort_values("ds").reset_index(drop=True)
    return out


def score_anomalies(
    actuals: pd.DataFrame,
    forecast: pd.DataFrame,
    ds_col: str = "ds",
    y_col: str = "y",
) -> pd.DataFrame:
    """Join actuals to Prophet forecast output and flag anomalies.

    `forecast` is the Prophet model's .predict() output which has columns
    ds / yhat / yhat_lower / yhat_upper. Returns a frame with the same
    columns plus `actual`, `is_anomaly`, and `anomaly_score`.
    """
    needed = {"ds", "yhat", "yhat_lower", "yhat_upper"}
    missing = needed - set(forecast.columns)
    if missing:
        raise ValueError(f"forecast is missing columns: {sorted(missing)}")

    fc = forecast.copy()
    fc["ds"] = pd.to_datetime(fc["ds"])

    act = actuals.copy()
    act["ds"] = pd.to_datetime(act[ds_col])
    act = act[[ "ds", y_col]].rename(columns={y_col: "actual"})

    merged = fc.merge(act, on="ds", how="left")
    merged["is_anomaly"] = merged["actual"].notna() & (merged["actual"] > merged["yhat_upper"])

    # Guard against zero/negative upper bounds (Prophet can emit them for
    # very small y). Rows with a non-positive denom get NaN instead of inf.
    denom = merged["yhat_upper"].where(merged["yhat_upper"] > 0)
    merged["anomaly_score"] = (merged["actual"] - merged["yhat_upper"]) / denom
    merged.loc[~merged["is_anomaly"], "anomaly_score"] = pd.NA

    return merged


def summarize_anomaly_runs(scored: pd.DataFrame) -> Sequence[dict]:
    """Collapse consecutive anomaly days into runs for alerting."""
    if scored.empty:
        return []
    anomalies = scored.loc[scored["is_anomaly"]].sort_values("ds").reset_index(drop=True)
    if anomalies.empty:
        return []

    runs = []
    run_start = anomalies["ds"].iloc[0]
    run_end = run_start
    run_peak = float(anomalies["actual"].iloc[0])

    for i in range(1, len(anomalies)):
        ds = anomalies["ds"].iloc[i]
        actual = float(anomalies["actual"].iloc[i])
        if (ds - run_end).days == 1:
            run_end = ds
            run_peak = max(run_peak, actual)
        else:
            runs.append({"start": run_start, "end": run_end, "peak_actual": run_peak})
            run_start = ds
            run_end = ds
            run_peak = actual
    runs.append({"start": run_start, "end": run_end, "peak_actual": run_peak})
    return runs
