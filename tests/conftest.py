"""Pytest fixtures shared across unit and integration tests.

A local SparkSession is created once per test session and configured to
mimic the Databricks Free Edition runtime as closely as a local JVM allows:
- Delta Lake enabled via `io.delta:delta-spark_2.12:3.2.0`
- ANSI SQL on (Databricks default)
- Timezone fixed to UTC for deterministic timestamp assertions
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterator

import pytest

# PySpark forks workers using whatever interpreter is on $PATH; on macOS
# that's often a different minor version than the one running pytest. Pin
# both driver and worker to the interpreter invoking the tests before any
# SparkSession is created.
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)


@pytest.fixture(scope="session")
def spark():
    """Session-scoped local SparkSession with Delta Lake enabled."""
    from pyspark.sql import SparkSession

    builder = (
        SparkSession.builder.master("local[2]")
        .appName("chi311-tests")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.default.parallelism", "2")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.ansi.enabled", "true")
        .config("spark.ui.enabled", "false")
        .config(
            "spark.jars.packages",
            "io.delta:delta-spark_2.12:3.2.0",
        )
        .config(
            "spark.sql.extensions",
            "io.delta.sql.DeltaSparkSessionExtension",
        )
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
    )

    session = builder.getOrCreate()
    session.sparkContext.setLogLevel("WARN")
    yield session
    session.stop()


@pytest.fixture
def tmp_warehouse(tmp_path: Path) -> Iterator[Path]:
    """Per-test warehouse directory for Delta/Parquet writes."""
    warehouse = tmp_path / "warehouse"
    warehouse.mkdir()
    yield warehouse
    # tmp_path cleanup is handled by pytest


@pytest.fixture
def tmp_volume(tmp_path: Path) -> Path:
    """Per-test directory standing in for a Unity Catalog Volume."""
    volume = tmp_path / "volume"
    volume.mkdir()
    return volume
