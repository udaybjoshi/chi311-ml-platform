"""Unit tests for chi311.ingestion.api_client.

These tests cover the pure-Python portion of the ingestion pipeline. HTTP is
stubbed with the `responses` library so tests are deterministic and do not
require network access.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses

from chi311.ingestion.api_client import (
    APIConfig,
    Chicago311APIClient,
    DataQualityReport,
    IncrementalLoader,
)

API_URL = APIConfig().base_url


# ---------------------------------------------------------------------------
# APIConfig
# ---------------------------------------------------------------------------


def test_api_config_defaults():
    cfg = APIConfig()
    assert cfg.base_url.startswith("https://data.cityofchicago.org/")
    assert cfg.timeout == 30
    assert cfg.max_retries == 3
    assert cfg.page_size == 10000


def test_api_config_from_env_uses_env_vars(monkeypatch):
    monkeypatch.setenv("CHI_OPENDATA_URL", "https://example.test/resource.json")
    monkeypatch.setenv("CHI_OPENDATA_APP_TOKEN", "TOKEN123")

    cfg = APIConfig.from_env()

    assert cfg.base_url == "https://example.test/resource.json"
    assert cfg.app_token == "TOKEN123"


def test_api_config_from_env_falls_back_to_defaults(monkeypatch):
    monkeypatch.delenv("CHI_OPENDATA_URL", raising=False)
    monkeypatch.delenv("CHI_OPENDATA_APP_TOKEN", raising=False)

    cfg = APIConfig.from_env()

    assert cfg.base_url == APIConfig.base_url
    assert cfg.app_token is None


# ---------------------------------------------------------------------------
# DataQualityReport
# ---------------------------------------------------------------------------


def _make_report(**overrides):
    defaults = dict(
        total_records=100,
        null_sr_number=0,
        null_created_date=0,
        null_ward=0,
        invalid_coordinates=0,
        duplicate_keys=0,
        date_range=("2024-01-01", "2024-01-02"),
    )
    defaults.update(overrides)
    return DataQualityReport(**defaults)


def test_dq_report_empty_is_valid():
    report = DataQualityReport(
        total_records=0,
        null_sr_number=0,
        null_created_date=0,
        null_ward=0,
        invalid_coordinates=0,
        duplicate_keys=0,
        date_range=(None, None),
    )
    assert report.is_valid is True


def test_dq_report_clean_data_is_valid():
    assert _make_report().is_valid is True


def test_dq_report_high_null_rate_is_invalid():
    # 6% null rate on sr_number exceeds 5% threshold
    report = _make_report(total_records=100, null_sr_number=6)
    assert report.is_valid is False


def test_dq_report_high_duplicate_rate_is_invalid():
    report = _make_report(total_records=100, duplicate_keys=6)
    assert report.is_valid is False


def test_dq_report_to_dict_shape():
    report = _make_report()
    d = report.to_dict()
    assert set(d) >= {
        "total_records",
        "null_sr_number",
        "null_created_date",
        "null_ward",
        "invalid_coordinates",
        "duplicate_keys",
        "date_range_start",
        "date_range_end",
        "is_valid",
    }
    assert d["is_valid"] is True


# ---------------------------------------------------------------------------
# Chicago311APIClient — record validation
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    return Chicago311APIClient()


def test_validate_records_empty(client):
    report = client.validate_records([])
    assert report.total_records == 0
    assert report.is_valid is True


def test_validate_records_counts_nulls(client):
    records = [
        {"sr_number": "SR1", "created_date": "2024-01-01T00:00:00", "ward": "28"},
        {"sr_number": None, "created_date": "2024-01-01T00:00:00", "ward": "28"},
        {"sr_number": "SR3", "created_date": None, "ward": None},
    ]
    report = client.validate_records(records)
    assert report.total_records == 3
    assert report.null_sr_number == 1
    assert report.null_created_date == 1
    assert report.null_ward == 1


def test_validate_records_flags_off_bbox_coordinates(client):
    records = [
        # Inside Chicago bbox
        {
            "sr_number": "SR1",
            "created_date": "2024-01-01T00:00:00",
            "latitude": "41.88",
            "longitude": "-87.63",
        },
        # Outside bbox (NYC-ish)
        {
            "sr_number": "SR2",
            "created_date": "2024-01-01T00:00:00",
            "latitude": "40.71",
            "longitude": "-74.00",
        },
        # Non-numeric
        {
            "sr_number": "SR3",
            "created_date": "2024-01-01T00:00:00",
            "latitude": "abc",
            "longitude": "xyz",
        },
    ]
    report = client.validate_records(records)
    assert report.invalid_coordinates == 2


def test_validate_records_detects_duplicate_sr_numbers(client):
    records = [
        {"sr_number": "SR1", "created_date": "2024-01-01T00:00:00"},
        {"sr_number": "SR1", "created_date": "2024-01-02T00:00:00"},
        {"sr_number": "SR2", "created_date": "2024-01-03T00:00:00"},
    ]
    report = client.validate_records(records)
    assert report.duplicate_keys == 1


def test_validate_records_computes_date_range(client):
    records = [
        {"sr_number": "SR1", "created_date": "2024-03-05T00:00:00"},
        {"sr_number": "SR2", "created_date": "2024-01-10T00:00:00"},
        {"sr_number": "SR3", "created_date": "2024-02-15T00:00:00"},
    ]
    report = client.validate_records(records)
    assert report.date_range == ("2024-01-10T00:00:00", "2024-03-05T00:00:00")


# ---------------------------------------------------------------------------
# Chicago311APIClient — HTTP interactions (stubbed)
# ---------------------------------------------------------------------------


@responses.activate
def test_fetch_page_sends_app_token_header():
    cfg = APIConfig(app_token="S3CR3T", page_size=10)
    client = Chicago311APIClient(cfg)

    responses.add(responses.GET, cfg.base_url, json=[{"sr_number": "SR1"}], status=200)

    client._fetch_page(where="created_date > '2024-01-01'")

    assert len(responses.calls) == 1
    sent = responses.calls[0].request
    assert sent.headers["X-App-Token"] == "S3CR3T"
    assert "%24where=" in sent.url or "$where=" in sent.url


@responses.activate
def test_fetch_all_paginates_until_empty():
    cfg = APIConfig(page_size=2)
    client = Chicago311APIClient(cfg)

    # Page 1 (full), page 2 (full), page 3 (empty -> stop)
    responses.add(
        responses.GET,
        cfg.base_url,
        json=[{"sr_number": "SR1"}, {"sr_number": "SR2"}],
        status=200,
    )
    responses.add(
        responses.GET,
        cfg.base_url,
        json=[{"sr_number": "SR3"}, {"sr_number": "SR4"}],
        status=200,
    )
    responses.add(responses.GET, cfg.base_url, json=[], status=200)

    records = list(client.fetch_all())

    assert [r["sr_number"] for r in records] == ["SR1", "SR2", "SR3", "SR4"]
    assert len(responses.calls) == 3


@responses.activate
def test_fetch_all_stops_on_short_page():
    cfg = APIConfig(page_size=10)
    client = Chicago311APIClient(cfg)

    # Only 2 records returned on a page size of 10 -> last page.
    responses.add(
        responses.GET,
        cfg.base_url,
        json=[{"sr_number": "SR1"}, {"sr_number": "SR2"}],
        status=200,
    )

    records = list(client.fetch_all())

    assert len(records) == 2
    assert len(responses.calls) == 1


@responses.activate
def test_fetch_all_respects_max_records():
    cfg = APIConfig(page_size=10)
    client = Chicago311APIClient(cfg)

    # Server would return 10; we cap at 3.
    responses.add(
        responses.GET,
        cfg.base_url,
        json=[{"sr_number": f"SR{i}"} for i in range(10)],
        status=200,
    )

    records = list(client.fetch_all(max_records=3))

    assert [r["sr_number"] for r in records] == ["SR0", "SR1", "SR2"]


@responses.activate
def test_fetch_changes_since_deduplicates_by_most_recent_update():
    cfg = APIConfig(page_size=50)
    client = Chicago311APIClient(cfg)

    responses.add(
        responses.GET,
        cfg.base_url,
        json=[
            {"sr_number": "SR1", "last_modified_date": "2024-01-01T00:00:00"},
            {"sr_number": "SR1", "last_modified_date": "2024-02-01T00:00:00"},  # wins
            {"sr_number": "SR2", "last_modified_date": "2024-01-15T00:00:00"},
        ],
        status=200,
    )
    # Second call returns empty to terminate fetch_all pagination.
    responses.add(responses.GET, cfg.base_url, json=[], status=200)

    records = client.fetch_changes_since("2023-12-01T00:00:00")

    by_sr = {r["sr_number"]: r for r in records}
    assert set(by_sr) == {"SR1", "SR2"}
    assert by_sr["SR1"]["last_modified_date"] == "2024-02-01T00:00:00"


# ---------------------------------------------------------------------------
# IncrementalLoader — state management
# ---------------------------------------------------------------------------


@responses.activate
def test_incremental_loader_first_run_uses_recent_window(tmp_path: Path):
    cfg = APIConfig(page_size=50)
    client = Chicago311APIClient(cfg)
    state_file = tmp_path / "state.json"
    loader = IncrementalLoader(client, state_file=str(state_file), scd2_mode=False)

    # First run -> fetch_recent(days=7)
    responses.add(
        responses.GET,
        cfg.base_url,
        json=[
            {
                "sr_number": "SR1",
                "created_date": "2024-01-10T00:00:00",
                "last_modified_date": "2024-01-10T00:00:00",
            }
        ],
        status=200,
    )
    # Pagination terminator
    responses.add(responses.GET, cfg.base_url, json=[], status=200)

    records, report = loader.load_incremental(initial_lookback_days=7)

    assert len(records) == 1
    assert report.is_valid is True
    assert state_file.exists()

    # State persists the latest created_date seen.
    state = json.loads(state_file.read_text())
    assert state["last_loaded_timestamp"] == "2024-01-10T00:00:00"
    assert state["scd2_mode"] is False


@responses.activate
def test_incremental_loader_subsequent_run_uses_saved_state(tmp_path: Path):
    cfg = APIConfig(page_size=50)
    client = Chicago311APIClient(cfg)
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps({"last_loaded_timestamp": "2024-01-10T00:00:00", "scd2_mode": True})
    )
    loader = IncrementalLoader(client, state_file=str(state_file), scd2_mode=True)

    responses.add(
        responses.GET,
        cfg.base_url,
        json=[
            {
                "sr_number": "SR2",
                "created_date": "2024-01-12T00:00:00",
                "last_modified_date": "2024-01-12T00:00:00",
            }
        ],
        status=200,
    )
    responses.add(responses.GET, cfg.base_url, json=[], status=200)

    records, _ = loader.load_incremental()

    assert [r["sr_number"] for r in records] == ["SR2"]
    sent_url = responses.calls[0].request.url
    # Either URL-encoded or raw, the saved timestamp must appear in the query.
    assert "2024-01-10T00%3A00%3A00" in sent_url or "2024-01-10T00:00:00" in sent_url
