"""Unit tests for chi311.ml.forecaster (no Prophet import)."""
from __future__ import annotations

import pandas as pd
import pytest

from chi311.ml.forecaster import (
    ForecastResult,
    build_prophet_input,
    score_anomalies,
    summarize_anomaly_runs,
)


def test_forecast_result_flags_anomaly_above_band():
    r = ForecastResult(
        ds=pd.Timestamp("2024-01-01"),
        yhat=3000.0,
        yhat_lower=2500.0,
        yhat_upper=3500.0,
        actual=4000.0,
    )
    assert r.is_anomaly is True
    assert r.anomaly_score == pytest.approx((4000 - 3500) / 3500)


def test_forecast_result_below_band_not_anomaly():
    r = ForecastResult(
        ds=pd.Timestamp("2024-01-01"),
        yhat=3000.0,
        yhat_lower=2500.0,
        yhat_upper=3500.0,
        actual=3400.0,
    )
    assert r.is_anomaly is False


def test_forecast_result_without_actual_is_not_anomaly():
    r = ForecastResult(
        ds=pd.Timestamp("2024-01-01"),
        yhat=3000.0,
        yhat_lower=2500.0,
        yhat_upper=3500.0,
    )
    assert r.is_anomaly is False
    assert r.anomaly_score is None


def test_build_prophet_input_normalises_shape():
    rows = [
        {"ds": "2024-01-02", "y": 10},
        {"ds": "2024-01-01", "y": 5},
        # duplicate date — should be summed
        {"ds": "2024-01-01", "y": 7},
        {"ds": "2024-01-03", "y": "nan"},
    ]
    out = build_prophet_input(rows)

    assert list(out.columns) == ["ds", "y"]
    assert out["ds"].tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")]
    assert out["y"].tolist() == [12.0, 10.0]


def test_build_prophet_input_accepts_custom_column_names():
    rows = [{"date": "2024-01-01", "count": 42}]
    out = build_prophet_input(rows, ds_column="date", y_column="count")
    assert out.loc[0, "ds"] == pd.Timestamp("2024-01-01")
    assert out.loc[0, "y"] == 42


def test_build_prophet_input_empty_returns_empty_frame():
    out = build_prophet_input([])
    assert out.empty
    assert list(out.columns) == ["ds", "y"]


def test_score_anomalies_flags_exceedances_only():
    actuals = pd.DataFrame(
        {
            "ds": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "y": [3200, 4500, 2800],
        }
    )
    forecast = pd.DataFrame(
        {
            "ds": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "yhat": [3000, 3000, 3000],
            "yhat_lower": [2500, 2500, 2500],
            "yhat_upper": [3500, 3500, 3500],
        }
    )

    scored = score_anomalies(actuals, forecast)

    assert scored["is_anomaly"].tolist() == [False, True, False]
    anomaly_row = scored.loc[scored["is_anomaly"]].iloc[0]
    assert anomaly_row["anomaly_score"] == pytest.approx((4500 - 3500) / 3500)


def test_score_anomalies_rejects_missing_columns():
    actuals = pd.DataFrame({"ds": ["2024-01-01"], "y": [1]})
    bad_forecast = pd.DataFrame({"ds": ["2024-01-01"], "yhat": [1]})
    with pytest.raises(ValueError, match="missing columns"):
        score_anomalies(actuals, bad_forecast)


def test_summarize_anomaly_runs_collapses_consecutive_days():
    scored = pd.DataFrame(
        {
            "ds": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-05", "2024-01-06", "2024-01-10"]
            ),
            "is_anomaly": [True, True, True, True, True],
            "actual": [4000, 4200, 4100, 4050, 3900],
        }
    )
    runs = summarize_anomaly_runs(scored)

    assert len(runs) == 3
    assert runs[0]["start"] == pd.Timestamp("2024-01-01")
    assert runs[0]["end"] == pd.Timestamp("2024-01-02")
    assert runs[0]["peak_actual"] == 4200
    assert runs[1]["start"] == pd.Timestamp("2024-01-05")
    assert runs[1]["end"] == pd.Timestamp("2024-01-06")
    assert runs[2]["start"] == pd.Timestamp("2024-01-10")
    assert runs[2]["end"] == pd.Timestamp("2024-01-10")


def test_summarize_anomaly_runs_empty():
    scored = pd.DataFrame(columns=["ds", "is_anomaly", "actual"])
    assert summarize_anomaly_runs(scored) == []
