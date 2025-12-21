# Databricks notebook source
# MAGIC %md
# MAGIC # Chicago 311 Service Request Intelligence - Setup & Exploration
# MAGIC
# MAGIC **Purpose**: Initial environment setup and exploratory data analysis to inform data quality rules and pipeline design.
# MAGIC
# MAGIC **ML Portfolio Framework**: Component 1 - Problem Framing & Metrics
# MAGIC
# MAGIC ## Why This Notebook First?
# MAGIC
# MAGIC Before writing any pipeline code or data quality rules, we need to understand:
# MAGIC 1. **What does the raw data look like?** - Schema, types, sample values
# MAGIC 2. **What are the data quality issues?** - Nulls, invalid values, duplicates
# MAGIC 3. **What are the temporal patterns?** - Seasonality for forecasting
# MAGIC 4. **How do status changes work?** - Critical for SCD Type 2 design
# MAGIC 5. **What thresholds should we set?** - Informs Great Expectations rules
# MAGIC
# MAGIC ## Outputs of This Notebook
# MAGIC
# MAGIC | Output | Used By |
# MAGIC |--------|---------|
# MAGIC | Null rate analysis | Great Expectations `mostly` thresholds |
# MAGIC | Valid value sets | Great Expectations `expect_column_values_to_be_in_set` |
# MAGIC | Coordinate bounds | Great Expectations lat/long validation |
# MAGIC | Status transitions | SCD Type 2 pipeline design |
# MAGIC | Volume patterns | Prophet seasonality configuration |

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Environment Setup

# COMMAND ----------

# Install required packages (uncomment on first run)
%pip install requests pandas plotly

# COMMAND ----------

import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from pyspark.sql import functions as F
from pyspark.sql.types import *
from collections import Counter

print(f"Setup complete. Timestamp: {datetime.now().isoformat()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Data Source Configuration
# MAGIC
# MAGIC **Chicago Data Portal - 311 Service Requests**
# MAGIC
# MAGIC | Property | Value |
# MAGIC |----------|-------|
# MAGIC | API Endpoint | `https://data.cityofchicago.org/resource/v6vf-nfxy.json` |
# MAGIC | Update Frequency | Daily |
# MAGIC | Historical Data | 2018 to present |
# MAGIC | Annual Volume | ~2 million records/year |
# MAGIC | Rate Limit | 1,000 requests/hour (unauthenticated) |

# COMMAND ----------

# Chicago Data Portal API configuration
API_BASE_URL = "https://data.cityofchicago.org/resource/v6vf-nfxy.json"
APP_TOKEN = None  # Optional: Add Socrata app token for higher rate limits

def fetch_data(limit: int = 10000, days_back: int = 90, order: str = "created_date DESC") -> pd.DataFrame:
    """
    Fetch data from Chicago 311 API for exploration.
    
    Args:
        limit: Maximum records to fetch
        days_back: How many days of history to fetch
        order: Sort order for results
        
    Returns:
        DataFrame with raw API response
    """
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%dT00:00:00')
    
    params = {
        "$limit": limit,
        "$order": order,
        "$where": f"created_date >= '{start_date}'"
    }
    
    if APP_TOKEN:
        params["$$app_token"] = APP_TOKEN
    
    print(f"Fetching up to {limit:,} records from last {days_back} days...")
    response = requests.get(API_BASE_URL, params=params)
    response.raise_for_status()
    
    data = response.json()
    
    if not data:
        print("⚠️  API returned empty response. Trying without date filter...")
        params_simple = {"$limit": limit, "$order": order}
        response = requests.get(API_BASE_URL, params=params_simple)
        data = response.json()
    
    df = pd.DataFrame(data)
    print(f"✓ Retrieved {len(df):,} records")
    return df

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Fetch Sample Data

# COMMAND ----------

# Fetch 90 days of data for comprehensive EDA
raw_df = fetch_data(limit=100000, days_back=90)

if raw_df.empty:
    print("\n⚠️  No data retrieved. Check API connectivity.")
else:
    print(f"\nDataset shape: {raw_df.shape[0]:,} rows × {raw_df.shape[1]} columns")
    print(f"Date range: {raw_df['created_date'].min()} to {raw_df['created_date'].max()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Schema Analysis
# MAGIC
# MAGIC Understanding the schema is critical for:
# MAGIC - Defining Bronze layer expectations
# MAGIC - Identifying required vs optional fields
# MAGIC - Planning type conversions for Silver layer

# COMMAND ----------

# Full schema overview
print("=" * 60)
print("SCHEMA ANALYSIS")
print("=" * 60)

schema_info = []
for col in raw_df.columns:
    # Handle columns with unhashable types (dicts, lists)
    try:
        unique_count = raw_df[col].nunique()
    except TypeError:
        unique_count = -1  # Use -1 to indicate nested/unhashable
    
    try:
        sample_val = str(raw_df[col].dropna().iloc[0])[:50] if raw_df[col].notna().any() else "N/A"
    except:
        sample_val = "N/A"
    
    schema_info.append({
        "column": col,
        "dtype": str(raw_df[col].dtype),
        "non_null": int(raw_df[col].notna().sum()),
        "null_pct": f"{raw_df[col].isna().mean():.1%}",
        "unique": unique_count,
        "sample": sample_val
    })

schema_df = pd.DataFrame(schema_info)

# Use print() instead of display() to avoid Arrow conversion issues
print(schema_df.to_string())

# COMMAND ----------

# MAGIC %md
# MAGIC ### Key Fields for Pipeline
# MAGIC
# MAGIC Based on our use case (forecasting + SCD2 lifecycle tracking), these are the critical fields:

# COMMAND ----------

# Define key fields by category - Chicago 311 schema
KEY_FIELDS = {
    "identifiers": ["sr_number"],
    "timestamps": ["created_date", "closed_date", "last_modified_date"],
    "status": ["status"],
    "classification": ["sr_type", "sr_short_code", "owner_department"],
    "location": ["ward", "community_area", "street_address", "latitude", "longitude", "zip_code"],
    "metadata": ["origin", "duplicate", "legacy_record"]
}

# Flatten and check availability
all_key_fields = [f for fields in KEY_FIELDS.values() for f in fields]
available = [f for f in all_key_fields if f in raw_df.columns]
missing = [f for f in all_key_fields if f not in raw_df.columns]

print("KEY FIELDS AVAILABILITY")
print("=" * 60)
for category, fields in KEY_FIELDS.items():
    print(f"\n{category.upper()}:")
    for f in fields:
        status = "✓" if f in raw_df.columns else "✗ MISSING"
        print(f"  {status} {f}")

if missing:
    print(f"\n⚠️  Missing fields: {missing}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Data Quality Assessment
# MAGIC
# MAGIC This analysis directly informs our Great Expectations rules.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 5.1 Null Rate Analysis
# MAGIC
# MAGIC **Output**: `mostly` thresholds for `expect_column_values_to_not_be_null`

# COMMAND ----------

# Calculate null rates for key fields
null_analysis = []
for field in available:
    null_rate = raw_df[field].isna().mean()
    null_analysis.append({
        "field": field,
        "null_rate": null_rate,
        "null_pct": f"{null_rate:.1%}",
        "recommendation": (
            "CRITICAL - must be non-null" if null_rate < 0.01 else
            "mostly=0.99" if null_rate < 0.05 else
            "mostly=0.95" if null_rate < 0.10 else
            "mostly=0.90" if null_rate < 0.15 else
            "mostly=0.85 or nullable"
        )
    })

null_df = pd.DataFrame(null_analysis).sort_values("null_rate")

print("NULL RATE ANALYSIS → Great Expectations 'mostly' thresholds")
print("=" * 60)
display(null_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 5.2 Valid Value Sets
# MAGIC
# MAGIC **Output**: `value_set` for `expect_column_values_to_be_in_set`

# COMMAND ----------

# Analyze categorical fields
categorical_fields = ["status", "sr_type", "owner_department", "origin", "ward"]

print("VALID VALUE SETS → Great Expectations 'value_set' parameter")
print("=" * 60)

for field in categorical_fields:
    if field in raw_df.columns:
        value_counts = raw_df[field].value_counts(dropna=False)
        print(f"\n{field.upper()} ({len(value_counts)} unique values):")
        print("-" * 40)
        
        # Show top values with counts
        for val, count in value_counts.head(10).items():
            pct = count / len(raw_df) * 100
            val_display = str(val)[:40] if val else "NULL"
            print(f"  {val_display}: {count:,} ({pct:.1f}%)")
        
        if len(value_counts) > 10:
            print(f"  ... and {len(value_counts) - 10} more values")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 5.3 Ward Values (Critical for Silver Layer)
# MAGIC
# MAGIC Ward is the geographic dimension (equivalent to NYC borough):

# COMMAND ----------

# Ward analysis
if 'ward' in raw_df.columns:
    ward_values = raw_df['ward'].value_counts(dropna=False)
    
    print("WARD VALUES → Geographic dimension for aggregation")
    print("=" * 60)
    print(f"\nTotal unique wards: {raw_df['ward'].nunique()}")
    print(f"Null rate: {raw_df['ward'].isna().mean():.1%}")
    
    print("\nTop 10 wards by volume:")
    for val, count in ward_values.head(10).items():
        pct = count / len(raw_df) * 100
        val_display = f"Ward {val}" if val else "NULL"
        print(f"  {val_display}: {count:,} ({pct:.1f}%)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 5.4 Coordinate Validation
# MAGIC
# MAGIC **Output**: `min_value`/`max_value` for `expect_column_values_to_be_between`

# COMMAND ----------

# Chicago bounding box analysis
if 'latitude' in raw_df.columns and 'longitude' in raw_df.columns:
    # Convert to numeric
    raw_df['latitude'] = pd.to_numeric(raw_df['latitude'], errors='coerce')
    raw_df['longitude'] = pd.to_numeric(raw_df['longitude'], errors='coerce')
    
    # Filter to non-null coordinates
    coords = raw_df[['latitude', 'longitude']].dropna()
    
    print("COORDINATE BOUNDS → Great Expectations lat/long validation")
    print("=" * 60)
    print(f"\nRecords with coordinates: {len(coords):,} ({len(coords)/len(raw_df)*100:.1f}%)")
    print(f"\nLatitude:")
    print(f"  Min: {coords['latitude'].min():.4f}")
    print(f"  Max: {coords['latitude'].max():.4f}")
    print(f"  Mean: {coords['latitude'].mean():.4f}")
    print(f"\nLongitude:")
    print(f"  Min: {coords['longitude'].min():.4f}")
    print(f"  Max: {coords['longitude'].max():.4f}")
    print(f"  Mean: {coords['longitude'].mean():.4f}")
    
    # Chicago bounding box
    CHICAGO_BOUNDS = {
        "lat_min": 41.6,
        "lat_max": 42.1,
        "lon_min": -87.95,
        "lon_max": -87.5
    }
    
    in_bounds = (
        (coords['latitude'].between(CHICAGO_BOUNDS['lat_min'], CHICAGO_BOUNDS['lat_max'])) &
        (coords['longitude'].between(CHICAGO_BOUNDS['lon_min'], CHICAGO_BOUNDS['lon_max']))
    ).mean()
    
    print(f"\nRecords within Chicago bounds: {in_bounds:.1%}")
    print(f"\nRecommended GE expectation:")
    print(f"  latitude: between {CHICAGO_BOUNDS['lat_min']} and {CHICAGO_BOUNDS['lat_max']}, mostly=0.90")
    print(f"  longitude: between {CHICAGO_BOUNDS['lon_min']} and {CHICAGO_BOUNDS['lon_max']}, mostly=0.90")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 5.5 Uniqueness Check
# MAGIC
# MAGIC **Output**: Validates `expect_column_values_to_be_unique` for `sr_number`

# COMMAND ----------

# Check for duplicate sr_numbers
if 'sr_number' in raw_df.columns:
    total = len(raw_df)
    unique = raw_df['sr_number'].nunique()
    duplicates = total - unique
    
    print("UNIQUENESS CHECK → sr_number validation")
    print("=" * 60)
    print(f"Total records: {total:,}")
    print(f"Unique SR numbers: {unique:,}")
    print(f"Duplicates: {duplicates:,} ({duplicates/total*100:.2f}%)")
    
    if duplicates > 0:
        # Show duplicate examples
        dup_keys = raw_df[raw_df['sr_number'].duplicated(keep=False)]['sr_number'].unique()[:5]
        print(f"\nExample duplicate SR numbers: {list(dup_keys)}")
        print("\n⚠️  Note: Duplicates in API response may indicate:")
        print("  1. Record updates (same key, different status) - Expected for SCD2")
        print("  2. API pagination issues - Need deduplication")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Status Field Analysis (Critical for SCD2)
# MAGIC
# MAGIC Understanding status values and transitions is essential for SCD Type 2 implementation.

# COMMAND ----------

# Status value analysis
if 'status' in raw_df.columns:
    print("STATUS VALUES → SCD Type 2 design")
    print("=" * 60)
    
    status_counts = raw_df['status'].value_counts(dropna=False)
    print("\nStatus distribution:")
    for status, count in status_counts.items():
        pct = count / len(raw_df) * 100
        print(f"  {status}: {count:,} ({pct:.1f}%)")
    
    print("\nExpected status transitions:")
    print("  Open → In Progress → Completed")
    print("  Open → Cancelled")
    print("  Open → Duplicate")
    
    print("\nSCD2 implications:")
    print("  - Each status change creates a new version")
    print("  - __START_AT = when record entered this status")
    print("  - __END_AT = when record left this status (null if current)")
    print("  - Track using last_modified_date")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 6.1 Status Change Detection Fields
# MAGIC
# MAGIC For SCD2 incremental loading, we need to identify WHICH fields indicate a status change:

# COMMAND ----------

# Analyze timestamp fields that indicate changes
timestamp_fields = ['created_date', 'closed_date', 'last_modified_date']

print("TIMESTAMP FIELDS → SCD2 change detection")
print("=" * 60)

for field in timestamp_fields:
    if field in raw_df.columns:
        non_null = raw_df[field].notna().sum()
        pct = non_null / len(raw_df) * 100
        print(f"\n{field}:")
        print(f"  Non-null: {non_null:,} ({pct:.1f}%)")
        
        if non_null > 0:
            raw_df[f'{field}_parsed'] = pd.to_datetime(raw_df[field], errors='coerce')
            min_date = raw_df[f'{field}_parsed'].min()
            max_date = raw_df[f'{field}_parsed'].max()
            print(f"  Range: {min_date} to {max_date}")

print("\n" + "=" * 60)
print("RECOMMENDATION for fetch_changes_since():")
print("  Use OR condition on:")
print("    - created_date > timestamp (new records)")
print("    - last_modified_date > timestamp (status changes)")
print("    - closed_date > timestamp (recently closed)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 6.2 Resolution Time Analysis (Lifecycle Analytics)
# MAGIC
# MAGIC This analysis previews the kind of insights SCD2 will enable:

# COMMAND ----------

# Resolution time analysis
if 'created_date' in raw_df.columns and 'closed_date' in raw_df.columns:
    # Parse dates
    raw_df['created_dt'] = pd.to_datetime(raw_df['created_date'], errors='coerce')
    raw_df['closed_dt'] = pd.to_datetime(raw_df['closed_date'], errors='coerce')
    
    # Calculate resolution time (only for closed requests)
    closed_requests = raw_df[raw_df['closed_dt'].notna()].copy()
    closed_requests['resolution_hours'] = (
        closed_requests['closed_dt'] - closed_requests['created_dt']
    ).dt.total_seconds() / 3600
    
    # Filter reasonable values (0 to 30 days)
    valid_resolution = closed_requests[
        (closed_requests['resolution_hours'] >= 0) & 
        (closed_requests['resolution_hours'] <= 720)  # 30 days
    ]
    
    print("RESOLUTION TIME ANALYSIS → Lifecycle Analytics Preview")
    print("=" * 60)
    print(f"\nClosed requests: {len(closed_requests):,}")
    print(f"With valid resolution time: {len(valid_resolution):,}")
    
    if len(valid_resolution) > 0:
        print(f"\nResolution time statistics (hours):")
        print(f"  Mean: {valid_resolution['resolution_hours'].mean():.1f}")
        print(f"  Median: {valid_resolution['resolution_hours'].median():.1f}")
        print(f"  25th percentile: {valid_resolution['resolution_hours'].quantile(0.25):.1f}")
        print(f"  75th percentile: {valid_resolution['resolution_hours'].quantile(0.75):.1f}")
        print(f"  95th percentile: {valid_resolution['resolution_hours'].quantile(0.95):.1f}")
        
        # Resolution time by ward
        if 'ward' in valid_resolution.columns:
            print(f"\nMedian resolution time by top wards (hours):")
            ward_resolution = valid_resolution.groupby('ward')['resolution_hours'].median().sort_values()
            for ward, hours in ward_resolution.head(10).items():
                print(f"  Ward {ward}: {hours:.1f}")

# COMMAND ----------

# Resolution time distribution
if 'resolution_hours' in valid_resolution.columns and len(valid_resolution) > 0:
    fig = px.histogram(
        valid_resolution[valid_resolution['resolution_hours'] <= 168],  # Up to 7 days
        x='resolution_hours',
        nbins=50,
        title='Resolution Time Distribution (Requests Closed Within 7 Days)',
        labels={'resolution_hours': 'Resolution Time (Hours)', 'count': 'Number of Requests'}
    )
    fig.add_vline(x=valid_resolution['resolution_hours'].median(), 
                  line_dash="dash", line_color="red",
                  annotation_text=f"Median: {valid_resolution['resolution_hours'].median():.1f}h")
    fig.show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Temporal Patterns (Forecasting Inputs)
# MAGIC
# MAGIC Understanding seasonality patterns informs Prophet configuration.

# COMMAND ----------

# Parse created_date for temporal analysis
raw_df['created_dt'] = pd.to_datetime(raw_df['created_date'], errors='coerce')
raw_df['date'] = raw_df['created_dt'].dt.date

# Daily volume
daily_counts = raw_df.groupby('date').size().reset_index(name='count')
daily_counts['date'] = pd.to_datetime(daily_counts['date'])

print("TEMPORAL PATTERNS → Prophet seasonality configuration")
print("=" * 60)
print(f"\nDaily volume statistics:")
print(f"  Mean: {daily_counts['count'].mean():.0f}")
print(f"  Std: {daily_counts['count'].std():.0f}")
print(f"  Min: {daily_counts['count'].min()}")
print(f"  Max: {daily_counts['count'].max()}")
print(f"  Coefficient of Variation: {daily_counts['count'].std() / daily_counts['count'].mean():.2f}")

# COMMAND ----------

# Daily volume trend
fig = px.line(
    daily_counts, 
    x='date', 
    y='count',
    title='Daily 311 Request Volume (Last 90 Days)',
    labels={'date': 'Date', 'count': 'Number of Requests'}
)
fig.add_hline(y=daily_counts['count'].mean(), line_dash="dash", line_color="red",
              annotation_text=f"Mean: {daily_counts['count'].mean():.0f}")
fig.update_layout(hovermode='x unified')
fig.show()

# COMMAND ----------

# Day of week patterns
raw_df['day_of_week'] = raw_df['created_dt'].dt.day_name()
raw_df['day_num'] = raw_df['created_dt'].dt.dayofweek

dow_counts = raw_df.groupby(['day_num', 'day_of_week']).size().reset_index(name='count')
dow_counts = dow_counts.sort_values('day_num')

fig = px.bar(
    dow_counts,
    x='day_of_week',
    y='count',
    title='Request Volume by Day of Week',
    labels={'day_of_week': 'Day', 'count': 'Total Requests'},
    color='count',
    color_continuous_scale='Blues'
)
fig.show()

# Weekend vs weekday
weekend_avg = raw_df[raw_df['day_num'] >= 5].groupby('date').size().mean()
weekday_avg = raw_df[raw_df['day_num'] < 5].groupby('date').size().mean()
print(f"\nWeekday average: {weekday_avg:.0f}")
print(f"Weekend average: {weekend_avg:.0f}")
print(f"Weekend drop: {(1 - weekend_avg/weekday_avg)*100:.1f}%")

# COMMAND ----------

# Hourly patterns (Chicago 311 has created_hour field)
if 'created_hour' in raw_df.columns:
    raw_df['hour'] = pd.to_numeric(raw_df['created_hour'], errors='coerce')
else:
    raw_df['hour'] = raw_df['created_dt'].dt.hour

hourly_counts = raw_df.groupby('hour').size().reset_index(name='count')

fig = px.bar(
    hourly_counts,
    x='hour',
    y='count',
    title='Request Volume by Hour of Day',
    labels={'hour': 'Hour (0-23)', 'count': 'Total Requests'},
    color='count',
    color_continuous_scale='Oranges'
)
fig.show()

# COMMAND ----------

# Re-analyze patterns WITHOUT info calls
service_df = raw_df[raw_df['sr_type'] != '311 INFORMATION ONLY CALL']
print(f"Service requests only: {len(service_df):,}")

# Daily volume (service only)
service_daily = service_df.groupby('date').size().reset_index(name='count')
print(f"\nDaily service volume statistics:")
print(f"  Mean: {service_daily['count'].mean():.0f}")
print(f"  Std: {service_daily['count'].std():.0f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Geographic Distribution

# COMMAND ----------

# Ward distribution
if 'ward' in raw_df.columns:
    ward_daily = raw_df.groupby(['date', 'ward']).size().reset_index(name='count')
    ward_daily['date'] = pd.to_datetime(ward_daily['date'])
    
    # Top 5 wards
    top_wards = raw_df['ward'].value_counts().head(5).index.tolist()
    ward_daily_top = ward_daily[ward_daily['ward'].isin(top_wards)]
    
    fig = px.line(
        ward_daily_top,
        x='date',
        y='count',
        color='ward',
        title='Daily Request Volume by Top 5 Wards',
        labels={'date': 'Date', 'count': 'Requests', 'ward': 'Ward'}
    )
    fig.update_layout(hovermode='x unified')
    fig.show()

# COMMAND ----------

# Ward summary
if 'ward' in raw_df.columns:
    ward_summary = raw_df.groupby('ward').agg(
        total_requests=('sr_number', 'count'),
        pct_closed=('status', lambda x: (x == 'Completed').mean() if len(x) > 0 else 0),
    ).reset_index()
    
    if 'resolution_hours' in raw_df.columns:
        resolution_by_ward = raw_df.groupby('ward')['resolution_hours'].mean()
        ward_summary = ward_summary.merge(
            resolution_by_ward.reset_index().rename(columns={'resolution_hours': 'avg_resolution_hours'}),
            on='ward',
            how='left'
        )
    
    print("WARD SUMMARY")
    print("=" * 60)
    display(ward_summary.sort_values('total_requests', ascending=False).head(15))

# COMMAND ----------

# Investigate Ward 28 dominance
print("Ward 28 SR Type breakdown:")
print(raw_df[raw_df['ward'] == '28']['sr_type'].value_counts().head(10))

print("\nWard 28 vs Others - SR Type comparison:")
ward_28_types = set(raw_df[raw_df['ward'] == '28']['sr_type'].unique())
other_types = set(raw_df[raw_df['ward'] != '28']['sr_type'].unique())
print(f"Types unique to Ward 28: {ward_28_types - other_types}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Service Request Type Analysis

# COMMAND ----------

# Top SR types
if 'sr_type' in raw_df.columns:
    sr_counts = raw_df.groupby('sr_type').size().reset_index(name='count')
    top_sr = sr_counts.nlargest(20, 'count')
    
    fig = px.bar(
        top_sr,
        x='count',
        y='sr_type',
        orientation='h',
        title='Top 20 Service Request Types',
        labels={'sr_type': 'Service Request Type', 'count': 'Total Requests'},
        color='count',
        color_continuous_scale='Viridis'
    )
    fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=600)
    fig.show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Key Findings Summary
# MAGIC
# MAGIC ### Data Quality Findings → Great Expectations Configuration

# COMMAND ----------

print("=" * 70)
print("KEY FINDINGS → GREAT EXPECTATIONS CONFIGURATION")
print("=" * 70)

print("""
┌─────────────────────────────────────────────────────────────────────┐
│ BRONZE LAYER EXPECTATIONS                                           │
├─────────────────────────────────────────────────────────────────────┤
│ Column              │ Expectation                    │ Threshold    │
├─────────────────────────────────────────────────────────────────────┤
│ sr_number           │ not_be_null                    │ 100%         │
│ sr_number           │ be_unique                      │ warning only │
│ created_date        │ not_be_null                    │ 100%         │
│ sr_type             │ not_be_null                    │ mostly=0.95  │
│ status              │ not_be_null                    │ mostly=0.95  │
│ ward                │ not_be_null                    │ mostly=0.90  │
│ latitude            │ be_between(41.6, 42.1)         │ mostly=0.90  │
│ longitude           │ be_between(-87.95, -87.5)      │ mostly=0.90  │
│ table               │ row_count >= 1000              │ critical     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ SILVER LAYER EXPECTATIONS (stricter after cleaning)                 │
├─────────────────────────────────────────────────────────────────────┤
│ All Bronze expectations PLUS:                                       │
│ ward                │ be_in_set (valid wards 1-50)   │ 100%         │
│ latitude            │ be_between                     │ mostly=0.99  │
│ longitude           │ be_between                     │ mostly=0.99  │
│ status              │ be_in_set                      │ mostly=0.99  │
└─────────────────────────────────────────────────────────────────────┘
""")

# COMMAND ----------

print("=" * 70)
print("KEY FINDINGS → SCD TYPE 2 CONFIGURATION")
print("=" * 70)

print("""
┌─────────────────────────────────────────────────────────────────────┐
│ SCD TYPE 2 DESIGN                                                   │
├─────────────────────────────────────────────────────────────────────┤
│ Business Key        │ sr_number                                     │
│ Sequence Column     │ last_modified_date                            │
│ Tracked Columns     │ status, closed_date                           │
│ Change Detection    │ created_date, last_modified_date,             │
│                     │ closed_date (for incremental fetch)           │
├─────────────────────────────────────────────────────────────────────┤
│ Expected Transitions:                                               │
│   Open → In Progress → Completed                                    │
│   Open → Cancelled                                                  │
│   Open → Duplicate                                                  │
├─────────────────────────────────────────────────────────────────────┤
│ Version Rate:       │ ~1.5-3.0 versions per request (target)        │
└─────────────────────────────────────────────────────────────────────┘
""")

# COMMAND ----------

print("=" * 70)
print("KEY FINDINGS → PROPHET FORECASTING CONFIGURATION")
print("=" * 70)

print(f"""
┌─────────────────────────────────────────────────────────────────────┐
│ PROPHET CONFIGURATION                                               │
├─────────────────────────────────────────────────────────────────────┤
│ Seasonality:                                                        │
│   Weekly            │ STRONG - {(1 - weekend_avg/weekday_avg)*100:.0f}% weekend drop               │
│   Daily             │ MODERATE - peak at business hours              │
│   Yearly            │ EXPECTED - need more data to confirm           │
├─────────────────────────────────────────────────────────────────────┤
│ Baseline:                                                           │
│   Daily Mean        │ {daily_counts['count'].mean():.0f} requests                             │
│   Daily Std         │ {daily_counts['count'].std():.0f} requests                              │
│   CV                │ {daily_counts['count'].std() / daily_counts['count'].mean():.2f}                                         │
├─────────────────────────────────────────────────────────────────────┤
│ Anomaly Threshold:  │ > mean + 2*std = {daily_counts['count'].mean() + 2*daily_counts['count'].std():.0f} requests           │
└─────────────────────────────────────────────────────────────────────┘
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 11. Save Exploration Results

# COMMAND ----------

# Create summary DataFrame for reference
exploration_summary = {
    "metric": [
        "total_records",
        "date_range_start",
        "date_range_end",
        "daily_mean",
        "daily_std",
        "weekend_drop_pct",
        "null_rate_ward",
        "null_rate_latitude",
        "sr_number_duplicates_pct",
        "median_resolution_hours",
        "exploration_timestamp"
    ],
    "value": [
        str(len(raw_df)),
        str(raw_df['created_dt'].min().date()) if raw_df['created_dt'].notna().any() else "N/A",
        str(raw_df['created_dt'].max().date()) if raw_df['created_dt'].notna().any() else "N/A",
        f"{daily_counts['count'].mean():.0f}",
        f"{daily_counts['count'].std():.0f}",
        f"{(1 - weekend_avg/weekday_avg)*100:.1f}",
        f"{raw_df['ward'].isna().mean()*100:.1f}" if 'ward' in raw_df.columns else "N/A",
        f"{raw_df['latitude'].isna().mean()*100:.1f}" if 'latitude' in raw_df.columns else "N/A",
        f"{(len(raw_df) - raw_df['sr_number'].nunique())/len(raw_df)*100:.2f}",
        f"{valid_resolution['resolution_hours'].median():.1f}" if 'resolution_hours' in valid_resolution.columns and len(valid_resolution) > 0 else "N/A",
        datetime.now().isoformat()
    ]
}

summary_df = spark.createDataFrame(pd.DataFrame(exploration_summary))

# Uncomment after creating schema: main.chi311
# summary_df.write.format("delta").mode("overwrite").saveAsTable("main.chi311.exploration_summary")

display(summary_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 12. Next Steps
# MAGIC
# MAGIC | Step | Notebook | Purpose |
# MAGIC |------|----------|---------|
# MAGIC | 1 | `01_data_quality_checks.py` | Implement Great Expectations suites based on findings |
# MAGIC | 2 | `chi311_scd2_pipeline.sql` | Build Lakeflow pipeline with SCD Type 2 |
# MAGIC | 3 | `02_feature_engineering.py` | Create temporal and lag features |
# MAGIC | 4 | `03_model_experimentation.py` | Train Prophet with identified seasonality |
# MAGIC | 5 | `04_ml_forecasting.py` | Production model training with MLflow |
# MAGIC | 6 | `05_anomaly_detection.py` | Detect anomalies using thresholds |
# MAGIC
# MAGIC ### Key Decisions Made:
# MAGIC
# MAGIC 1. **Great Expectations thresholds** derived from actual null rates
# MAGIC 2. **Ward validation** rules defined for Silver layer
# MAGIC 3. **SCD2 change detection** uses `created_date`, `last_modified_date`, `closed_date`
# MAGIC 4. **Prophet seasonality** confirmed: strong weekly, moderate daily
# MAGIC 5. **Anomaly threshold** baseline: mean + 2*std

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC **Document History**
# MAGIC
# MAGIC | Version | Date | Changes |
# MAGIC |---------|------|---------|
# MAGIC | 1.0 | 2024-12-20 | Initial exploration with Chicago 311 data |
