# Data Sourcing Strategy

## Chicago 311 Service Request Data

### Data Source Overview

| Attribute | Value |
|-----------|-------|
| **Source** | Chicago Data Portal |
| **Dataset** | 311 Service Requests |
| **API** | Socrata Open Data API (SODA) |
| **Endpoint** | `https://data.cityofchicago.org/resource/v6vf-nfxy.json` |
| **Update Frequency** | Daily |
| **Historical Depth** | 2018 - Present |
| **Daily Volume** | ~5,000 total / ~3,000 service requests |
| **Cost** | Free (no API key required for basic access) |

---

## Key Findings from Data Exploration

> These findings are from `notebooks/00_setup_exploration.py` analysis of 50,000 recent records.

### Volume Statistics

| Metric | All Requests | Service Only |
|--------|--------------|--------------|
| **Daily Mean** | 5,000 | 3,001 |
| **Daily Std Dev** | 1,290 | 925 |
| **Anomaly Threshold** (mean + 2σ) | 7,580 | 4,851 |

### Status Values

Chicago 311 uses only **3 status values** (simpler than expected):

| Status | Percentage | Notes |
|--------|------------|-------|
| **Completed** | 83.7% | Includes instant closures |
| **Open** | 15.1% | Pending resolution |
| **Canceled** | 1.2% | Note: one 'l', not 'Cancelled' |

### Info Calls vs Service Requests

| Type | Percentage | Description |
|------|------------|-------------|
| **Info Calls** | 40% | "311 INFORMATION ONLY CALL" |
| **Service Requests** | 60% | Actual service needs |

> **Important**: Filter out info calls for forecasting: `sr_type != '311 INFORMATION ONLY CALL'`

### Resolution Time

| Metric | Value |
|--------|-------|
| **Instant Closures** | 82% resolve in 0 hours |
| **Same-Day Resolution** | 87% |
| **Meaningful Resolution Time** | Exclude instant closures for analysis |

### Temporal Patterns

| Pattern | Finding |
|---------|---------|
| **Weekend Drop** | 35-40% fewer requests |
| **Peak Hours** | 10 AM - 3 PM |
| **Weekly Seasonality** | Strong (use in Prophet) |

### Geographic Distribution

| Finding | Value |
|---------|-------|
| **Ward 28 Dominance** | 39% of all requests |
| **Reason** | Info calls administratively assigned to Ward 28 |
| **Chicago Wards** | 50 total (numbered 1-50) |
| **Coordinate Bounds** | Lat: 41.6-42.1, Lon: -87.95 to -87.5 |

---

## Why This Data Source?

### Uniqueness

Unlike typical portfolio projects using Kaggle datasets, this data:
- Is **continuously updated** (new records daily)
- Requires **API interaction** (not a static CSV)
- Has **real operational value** (used by Chicago government)
- Contains **natural patterns** (seasonality, trends, anomalies)

### Authenticity

- Official government data
- Used in production by Chicago 311 operations
- Cited in academic research and journalism

### SCD Type 2 Suitability

- Status changes over time (Open → Completed)
- `last_modified_date` field enables change tracking
- Simple status model (3 values) = cleaner history

---

## API Details

### Endpoint

```
https://data.cityofchicago.org/resource/v6vf-nfxy.json
```

### Key Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `$limit` | Records per request (max 50,000) | `$limit=10000` |
| `$offset` | Pagination offset | `$offset=50000` |
| `$where` | SQL-like filter | `$where=created_date > '2024-01-01'` |
| `$select` | Column selection | `$select=sr_number,created_date` |
| `$order` | Sort order | `$order=created_date DESC` |
| `$$app_token` | App token (optional, increases rate limit) | |

### Rate Limits

| Access Type | Rate Limit | Our Approach |
|-------------|------------|--------------|
| Anonymous | 1,000 requests/hour | Sufficient for daily batch |
| With App Token | 10,000 requests/hour | Register if needed |

### Sample Request

```python
import requests
from datetime import datetime, timedelta

API_URL = "https://data.cityofchicago.org/resource/v6vf-nfxy.json"

params = {
    "$limit": 50000,
    "$order": "created_date DESC",
    "$where": f"created_date >= '{(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')}'"
}

response = requests.get(API_URL, params=params)
data = response.json()

print(f"Fetched {len(data)} records")
```

---

## Data Schema

### Key Fields

| Field | Type | Description | Used For |
|-------|------|-------------|----------|
| `sr_number` | string | Primary identifier | Business key (SCD2) |
| `created_date` | timestamp | Request creation time | Time series analysis |
| `closed_date` | timestamp | Request closure time | Resolution time calc |
| `last_modified_date` | timestamp | Last update time | SCD2 sequencing |
| `sr_type` | string | Request category | Aggregation, filtering |
| `sr_short_code` | string | Short category code | Grouping |
| `status` | string | Open/Completed/Canceled | SCD2 tracking |
| `owner_department` | string | Responsible department | Performance analysis |
| `ward` | integer | Chicago ward (1-50) | Geographic analysis |
| `community_area` | string | Community area name | Geographic grouping |
| `latitude` | float | GPS latitude | Validation, mapping |
| `longitude` | float | GPS longitude | Validation, mapping |
| `origin` | string | Request channel | Channel analysis |
| `duplicate` | boolean | Duplicate flag | Filtering |
| `legacy_record` | boolean | Pre-migration flag | Filtering |

### Field Quality (from Exploration)

| Field | Null Rate | Quality Notes |
|-------|-----------|---------------|
| `sr_number` | 0.0% | Always present (critical) |
| `created_date` | 0.0% | Always present (critical) |
| `sr_type` | 0.0% | Always present (critical) |
| `status` | 0.0% | Always present (critical) |
| `ward` | 0.2% | Use `mostly=0.99` threshold |
| `latitude` | 0.2% | Use `mostly=0.99` threshold |
| `longitude` | 0.2% | Use `mostly=0.99` threshold |
| `zip_code` | 13.1% | Use `mostly=0.85` threshold |
| `closed_date` | 15.3% | Expected for open requests |

---

## Data Quality Thresholds

### Great Expectations Configuration

Based on exploration findings, use these thresholds:

```python
# Bronze Layer (lenient)
bronze_expectations = {
    "sr_number": {"not_null": True},
    "created_date": {"not_null": True},
    "sr_type": {"not_null": True},
    "status": {
        "not_null": True,
        "in_set": ["Open", "Completed", "Canceled"]
    },
    "ward": {
        "not_null": {"mostly": 0.99},
        "between": {"min": 1, "max": 50, "mostly": 0.95}
    },
    "latitude": {
        "not_null": {"mostly": 0.99},
        "between": {"min": 41.6, "max": 42.1, "mostly": 0.95}
    },
    "longitude": {
        "not_null": {"mostly": 0.99},
        "between": {"min": -87.95, "max": -87.5, "mostly": 0.95}
    }
}

# Silver Layer (strict - after cleaning)
silver_expectations = {
    "status": {"in_set": ["OPEN", "COMPLETED", "CANCELED"]},  # Uppercase
    "ward": {"between": {"min": 1, "max": 50, "mostly": 0.99}},
    "latitude": {"between": {"min": 41.6, "max": 42.1, "mostly": 0.99}}
}
```

### Data Quality Gate

| Metric | Threshold | Action |
|--------|-----------|--------|
| Null rate (critical fields) | 0% | Fail pipeline |
| Null rate (ward, coords) | < 1% | Warning |
| Status value violations | < 1% | Drop rows |
| Coordinate out of bounds | < 5% | Set to NULL |
| Overall pass rate | ≥ 80% | Gate decision |

---

## Continuous Data Collection

### Strategy: Incremental Loading via SCD2

Rather than bulk loading, the pipeline uses **APPLY CHANGES INTO**:

1. Stream new records from JSON files
2. Compare with existing data by `sr_number`
3. Create new version if status changed
4. Maintain full history with `__START_AT` / `__END_AT`

### SCD Type 2 Expectations

| Metric | Expected Value | Notes |
|--------|----------------|-------|
| Avg versions per request | 1.2 - 1.5 | Most close instantly |
| Status transitions | Open → Completed (83%) | Simple flow |
| | Open → Canceled (1%) | Rare |

### Scheduling

| Environment | Schedule | Tool |
|-------------|----------|------|
| Databricks | Daily 6 AM CT | Lakeflow Pipeline |
| Local Dev | Manual trigger | Python script |

---

## Data Volume Estimates

### Daily Volume

| Type | Count |
|------|-------|
| All requests | ~5,000 |
| Service requests (excl. info calls) | ~3,000 |
| Info calls | ~2,000 |

### Storage Estimates

| Time Range | Approx Records | Storage (Delta) |
|------------|----------------|-----------------|
| 1 day | ~5,000 | ~1 MB |
| 1 month | ~150,000 | ~30 MB |
| 1 year | ~1.8 million | ~350 MB |
| 2 years | ~3.6 million | ~700 MB |

---

## Forecasting Baseline

Use these baselines from exploration for anomaly detection:

### Service Requests Only (Recommended)

```python
baseline_service = {
    "mean": 3001,
    "std": 925,
    "anomaly_threshold": 4851,  # mean + 2σ
    "weekend_factor": 0.60      # 40% drop
}
```

### All Requests

```python
baseline_all = {
    "mean": 5000,
    "std": 1290,
    "anomaly_threshold": 7580,  # mean + 2σ
    "weekend_factor": 0.62      # 38% drop
}
```

### Prophet Configuration

```python
prophet_config = {
    "yearly_seasonality": True,
    "weekly_seasonality": True,
    "daily_seasonality": False,  # Not enough granularity
    "changepoint_prior_scale": 0.05,
    "seasonality_prior_scale": 10.0
}
```

---

## Alternative Data Sources Considered

| Source | Pros | Cons | Decision |
|--------|------|------|----------|
| **Chicago Data Portal** | Official, free, real-time | Rate limits | ✅ Selected |
| NYC 311 Data | Larger volume | Different city | ❌ Switched to Chicago |
| Kaggle Chicago 311 | Pre-cleaned | Static, outdated | ❌ |
| Web scraping | Custom data | Legal issues, maintenance | ❌ |

---

## Future Enhancements

### Phase 2 Data Sources

| Source | Purpose | Integration |
|--------|---------|-------------|
| Weather API | Correlation with complaints | Feature engineering |
| Chicago Events API | Explain anomalies | Labeling validation |
| Holiday Calendar | Seasonality features | Already in Prophet |

### External Data Integration Pattern

```python
# Example: Weather data enrichment
def enrich_with_weather(df):
    weather_df = fetch_weather_data(
        df['date'].min(), 
        df['date'].max(),
        location="Chicago"
    )
    return df.merge(weather_df, on='date', how='left')
```

---

## Security & Compliance

### Data Classification

- **Public Data**: No PII, no access restrictions
- **Government Source**: Officially published for public use

### Usage Terms

- Chicago Data Portal Terms of Use apply
- Attribution required for public display
- No restrictions on analysis or derived works

---

## Implementation Files

| File | Purpose |
|------|---------|
| `notebooks/00_setup_exploration.py` | Initial data exploration & findings |
| `notebooks/01_data_quality_checks.py` | Great Expectations validation |
| `pipelines/chi311_scd2_pipeline.sql` | Lakeflow pipeline with SCD2 |
| `pipelines/expectations/data_quality_rules.yaml` | DQ rule definitions |

---

## Quick Reference: Filtering Patterns

### Exclude Info Calls (for forecasting)

```sql
WHERE sr_type != '311 INFORMATION ONLY CALL'
-- or
WHERE is_info_call = FALSE
```

### Current Records Only (from SCD2)

```sql
WHERE __END_AT IS NULL
```

### Valid Coordinates Only

```sql
WHERE latitude BETWEEN 41.6 AND 42.1
  AND longitude BETWEEN -87.95 AND -87.5
```

### Exclude Instant Closures (for resolution analysis)

```sql
WHERE resolution_hours > 0.1
```

---

## References

- [Chicago Data Portal](https://data.cityofchicago.org/)
- [311 Service Requests Dataset](https://data.cityofchicago.org/Service-Requests/311-Service-Requests/v6vf-nfxy)
- [Socrata API Documentation](https://dev.socrata.com/)
- [Chicago Ward Map](https://www.chicago.gov/city/en/depts/dgs/supp_info/citywide_702702702702702702702702702702702702702702702702.html)
