"""Smoke test for the session-scoped SparkSession fixture."""
from __future__ import annotations

import pytest


@pytest.mark.integration
def test_spark_session_is_local(spark):
    assert spark.sparkContext.master.startswith("local")
    assert spark.conf.get("spark.sql.session.timeZone") == "UTC"


@pytest.mark.integration
def test_spark_session_can_create_dataframe(spark):
    rows = [(1, "a"), (2, "b")]
    df = spark.createDataFrame(rows, schema=["id", "name"])
    assert df.count() == 2
    assert df.columns == ["id", "name"]
