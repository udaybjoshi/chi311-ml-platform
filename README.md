# Chicago 311 Service Request Intelligence Platform

> **A Production-Grade ML Portfolio Project** demonstrating end-to-end machine learning engineering on Databricks Free Edition with Lakeflow Declarative Pipelines, SCD Type 2 history tracking, and MLflow.

[![Databricks](https://img.shields.io/badge/Databricks-Free%20Edition-FF3621?logo=databricks)](https://databricks.com)
[![MLflow](https://img.shields.io/badge/MLflow-Experiment%20Tracking-0194E2?logo=mlflow)](https://mlflow.org)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)](https://python.org)
[![SCD2](https://img.shields.io/badge/SCD-Type%202-green)](docs/DATA_ARCHITECTURE.md)
[![Great Expectations](https://img.shields.io/badge/Great%20Expectations-Data%20Quality-orange)](https://greatexpectations.io)

---

## Table of Contents

1. [Project Overview](#-project-overview)
2. [ML Portfolio Framework Alignment](#-ml-portfolio-framework-alignment)
3. [Architecture](#-architecture)
4. [Quick Start](#-quick-start)
5. [Component Deep Dives](#-component-deep-dives)
6. [Project Structure](#-project-structure)
7. [Success Metrics](#-success-metrics)
8. [Future Enhancements](#-future-enhancements)

---

## Project Overview

### Problem Statement

Chicago's 311 service handles **millions of non-emergency requests annually** - from pothole repairs to garbage collection issues. City operations teams face a critical challenge: **detecting unusual spikes in service requests before they overwhelm resources**.

### Solution

This platform provides:
- **Demand Forecasting**: Predict future 311 request volumes using Prophet time series models
- **Anomaly Detection**: Identify unusual spikes using model-based thresholds
- **Operational Dashboard**: Real-time insights for resource planning
- **Historical Analysis**: Full lifecycle tracking of requests via SCD Type 2

### Target Users

| User | Need | How This Helps |
|------|------|----------------|
| **City Operations Manager** | Plan staffing for upcoming week | 7-day demand forecasts by ward |
| **311 Call Center Supervisor** | Spot unusual activity | Real-time anomaly alerts |
| **Resource Planner** | Allocate resources by service type | Historical patterns + predictions |
| **Data Analyst** | Understand request lifecycle | Time-in-status analysis via SCD2 |

---

## ML Portfolio Framework Alignment

This project follows the [8-component ML portfolio framework](docs/PORTFOLIO_FRAMEWORK.md) for production-grade projects:

| Component | Status | Implementation |
|-----------|--------|----------------|
| 1. **Problem Framing & Metrics** | ✅ | Business KPIs + ML metrics defined |
| 2. **Unique Data Sourcing** | ✅ | Chicago Data Portal API with continuous collection |
| 3. **Data Storage** | ✅ | Delta Lake with SCD Type 2 (Medallion Architecture) |
| 4. **Feature Engineering** | ✅ | Temporal, categorical, and lag features |
| 5. **Labeling Strategy** | ✅ | Programmatic labeling via Prophet thresholds |
| 6. **Model Training & Evaluation** | ✅ | MLflow experiment tracking + hyperparameter tuning |
| 7. **Deployment** | ✅ | Batch predictions + Streamlit dashboard |
| 8. **Monitoring & Feedback** | ✅ | Prediction logging + Great Expectations data quality |

See [docs/PORTFOLIO_FRAMEWORK.md](docs/PORTFOLIO_FRAMEWORK.md) for detailed alignment documentation.

---

## Architecture

### High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CHICAGO 311 INTELLIGENCE PLATFORM                      │
│                      (Databricks Free Edition + Lakeflow)                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  DATA INGESTION (Continuous Collection)                                     │
│  ┌─────────────────┐                                                        │
│  │ Chicago Data    │ ──API──▶ Scheduled Jobs ──▶ Bronze Layer               │
│  │ Portal API      │         (Daily at 6 AM)                                │
│  └─────────────────┘                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAKEFLOW DECLARATIVE PIPELINE (ETL with SCD Type 2)                        │
│                                                                             │
│  ┌────────────────┐     ┌─────────────────────┐     ┌────────────────┐      │
│  │    BRONZE      │     │       SILVER        │     │      GOLD      │      │
│  │  ┌──────────┐  │     │  ┌───────────────┐  │     │ ┌────────────┐ │      │
│  │  │ Raw JSON │  │ ──▶ │  │  SCD Type 2   │  │ ──▶ │ │ Aggregates │ │      │
│  │  │ Landing  │  │     │  │  History      │  │     │ │ Features   │ │      │
│  │  └──────────┘  │     │  │ __START_AT    │  │     │ └────────────┘ │      │
│  │  ┌──────────┐  │     │  │ __END_AT      │  │     │ ┌────────────┐ │      │
│  │  │ Staged   │  │     │  └───────────────┘  │     │ │ Status     │ │      │
│  │  │ Cleaned  │  │     │         │           │     │ │ Transitions│ │      │
│  │  └──────────┘  │     │         ▼           │     │ └────────────┘ │      │
│  └────────────────┘     │  ┌───────────────┐  │     └────────────────┘      │
│                         │  │Current View   │  │                             │
│  APPLY CHANGES INTO ──▶ │  │(__END_AT=NULL)│  │                             │
│                         │  └───────────────┘  │                             │
│                         └─────────────────────┘                             │
│                                                                             │
│  Data Quality Expectations enforced at each layer                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ML PIPELINE (MLflow Tracked)                                               │
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐          │
│  │ Feature Store   │───▶│ Prophet Model   │───▶│ Anomaly Scorer  │          │
│  │ (Gold Tables)   │    │ Training        │    │ (Thresholds)    │          │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘          │
│                                │                        │                   │
│                                ▼                        ▼                   │
│                         ┌─────────────┐         ┌─────────────┐             │
│                         │   MLflow    │         │  Anomalies  │             │
│                         │ Experiments │         │   Table     │             │
│                         └─────────────┘         └─────────────┘             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SERVING & MONITORING                                                       │
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐          │
│  │   Streamlit     │    │  Prediction     │    │   Data Drift    │          │
│  │   Dashboard     │    │    Logging      │    │   Detection     │          │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### SCD Type 2: Why It Matters

311 service requests **change over time** (Open → Completed or Open → Canceled). SCD Type 2 preserves this history:

```
┌────────────┬──────────────┬─────────────────────┬─────────────────────┐
│ sr_number  │ status       │ __START_AT          │ __END_AT            │
├────────────┼──────────────┼─────────────────────┼─────────────────────┤
│ SR12345    │ Open         │ 2024-12-01 09:00:00 │ 2024-12-05 14:00:00 │
│ SR12345    │ Completed    │ 2024-12-05 14:00:00 │ NULL                │
└────────────┴──────────────┴─────────────────────┴─────────────────────┘
```

> **Note**: Chicago 311 uses only 3 status values: **Open**, **Completed**, **Canceled** (one 'l'). 
> Most requests (82%) close instantly. The simplified status model means fewer SCD2 versions per request (~1.2 avg).

This enables:
- ✅ **Time-in-Status Analysis**: "How long do noise complaints stay open?"
- ✅ **Point-in-Time Queries**: "What was the status on December 10th?"
- ✅ **Lifecycle Analytics**: "What's the typical path from Open to Completed?"

### Technology Stack

| Layer | Technology | Why This Choice |
|-------|------------|-----------------|
| **Compute** | Databricks Free Edition | Zero cost, serverless, full Lakeflow access |
| **Storage** | Delta Lake + Unity Catalog | ACID transactions, time travel, governance |
| **ETL** | Lakeflow Declarative Pipelines | Declarative SQL/Python, auto-optimization |
| **SCD2** | `APPLY CHANGES INTO` | Built-in CDC handling for history tracking |
| **Data Quality** | Great Expectations | Declarative expectations, data docs, profiling |
| **ML Tracking** | MLflow | Native Databricks integration, experiment management |
| **Forecasting** | Prophet | Handles seasonality, missing data, outliers |
| **Dashboard** | Streamlit | Fast prototyping, Python native |
| **CI/CD** | GitHub Actions | Free tier, Databricks CLI integration |

---

## Quick Start

### Prerequisites

- [Databricks Free Edition Account](https://docs.databricks.com/en/getting-started/free-edition.html)
- Python 3.11+
- Git

### Step 1: Clone Repository

```bash
git clone https://github.com/udaybjoshi/chi311-intelligence-platform.git
cd chi311-intelligence-platform
```

### Step 2: Set Up Databricks Free Edition

1. Sign up at [Databricks Free Edition](https://www.databricks.com/try-databricks#account)
2. Choose "Express Setup" (no cloud account needed)
3. Create a workspace

### Step 3: Import Notebooks

```bash
# Option A: Import via Databricks UI
# Navigate to Workspace → Import → Upload notebooks folder

# Option B: Use Databricks CLI
pip install databricks-cli
databricks configure --token
databricks workspace import_dir ./notebooks /Workspace/Users/YOUR_EMAIL/chi311
```

### Step 4: Create Lakeflow Pipeline

1. Navigate to **Workflows** → **Lakeflow Declarative Pipelines**
2. Click **Create Pipeline**
3. Point to `pipelines/chi311_scd2_pipeline.sql`
4. Configure: **Serverless**, **Development mode**
5. Run the pipeline

### Step 5: Run ML Training

1. Open `notebooks/04_ml_forecasting.py`
2. Attach to serverless compute
3. Run all cells

### Step 6: Launch Dashboard (Local)

```bash
cd app
pip install -r requirements.txt
streamlit run dashboard.py
```

---

## Component Deep Dives

### 1. Problem Framing & Success Metrics

**See:** [docs/PROJECT_SCOPING.md](docs/PROJECT_SCOPING.md)

| Metric Type | Metric | Target | Current |
|-------------|--------|--------|---------|
| **Business** | Anomaly Detection Lead Time | >2 hours before spike | TBD |
| **Business** | False Positive Rate | <15% | TBD |
| **ML** | Forecast MAPE | <15% | TBD |
| **ML** | Anomaly Precision | >0.80 | TBD |

### 2. Data Sourcing

**See:** [docs/DATA_SOURCING.md](docs/DATA_SOURCING.md)

- **Source**: Chicago Data Portal (Socrata API)
- **Endpoint**: `https://data.cityofchicago.org/resource/v6vf-nfxy.json`
- **Volume**: ~5,000 requests/day (all) / ~3,000/day (service requests only)
- **Collection**: Daily incremental loads

#### Key Findings from Data Exploration

| Finding | Value | Implication |
|---------|-------|-------------|
| **Info Calls** | 40% of volume | "311 INFORMATION ONLY CALL" - exclude for demand forecasting |
| **Service Requests** | ~3,000/day | True service demand after filtering info calls |
| **Status Values** | Open, Completed, Canceled | Only 3 values (note: "Canceled" with one 'l') |
| **Completion Rate** | 83.7% | High efficiency - most requests close quickly |
| **Instant Closures** | 82% | Resolve in 0 hours (info calls + same-day service) |
| **Weekend Drop** | 35-40% | Strong weekly seasonality for Prophet |
| **Peak Hours** | 10am-3pm | Daily seasonality pattern |
| **Ward 28 Dominance** | 39% of requests | Due to info calls being assigned there |

#### Data Quality Summary

| Field | Null Rate | Threshold |
|-------|-----------|-----------|
| sr_number, created_date, sr_type, status | 0.0% | Critical - must be non-null |
| ward, latitude, longitude | 0.2% | mostly=0.99 |
| zip_code | 13.1% | mostly=0.85 |
| closed_date | 15.3% | Expected for open requests |

#### Forecasting Baseline

| Metric | All Requests | Service Only |
|--------|--------------|--------------|
| Daily Mean | 5,000 | 3,001 |
| Daily Std | 1,290 | 925 |
| Anomaly Threshold (mean + 2σ) | 7,580 | 4,851 |

### 3. Data Storage (Medallion + SCD2)

**See:** [docs/DATA_ARCHITECTURE.md](docs/DATA_ARCHITECTURE.md)

| Layer | Table | Description | SCD Type |
|-------|-------|-------------|----------|
| Bronze | `bronze_raw_311_requests` | Raw JSON landing | Append-only |
| Bronze | `bronze_staged_311_requests` | Cleaned, ready for CDC | Append-only |
| Silver | `silver_scd2_311_requests` | Full history | **SCD Type 2** |
| Silver | `silver_current_311_requests` | Current state view | View |
| Silver | `silver_status_history` | Status change history | View |
| Gold | `gold_daily_aggregates` | ML features | Derived |
| Gold | `gold_citywide_daily_summary` | Prophet input | Derived |
| Gold | `gold_status_transitions` | Lifecycle analytics | Derived |

**Key SCD2 Query Patterns:**

```sql
-- Current state only
SELECT * FROM silver_current_311_requests WHERE status = 'OPEN';

-- Full history for a request
SELECT * FROM silver_scd2_311_requests 
WHERE sr_number = 'SR12345' ORDER BY __START_AT;

-- Point-in-time query
SELECT * FROM silver_scd2_311_requests
WHERE sr_number = 'SR12345'
  AND __START_AT <= '2024-12-10'
  AND (__END_AT > '2024-12-10' OR __END_AT IS NULL);

-- Time-in-status analysis
SELECT status, AVG(hours_in_status) as avg_hours
FROM silver_status_history
GROUP BY status;
```

### 4. Feature Engineering

**See:** [docs/FEATURE_ENGINEERING.md](docs/FEATURE_ENGINEERING.md)

**Temporal Features:**
- Day of week, month, quarter
- Is weekend, is holiday
- Days since last spike

**Lag Features:**
- 7-day rolling average
- 28-day rolling average
- Year-over-year comparison

**Categorical Features:**
- Ward encoding
- Complaint type groupings
- Agency assignment

### 5. Labeling Strategy (Anomaly Detection)

**See:** [docs/LABELING_STRATEGY.md](docs/LABELING_STRATEGY.md)

We use **programmatic labeling** via Prophet model thresholds:

```python
# Anomaly = Actual > Upper 95% Confidence Interval
is_anomaly = actual_count > forecast_upper_bound
anomaly_score = (actual_count - forecast_upper_bound) / forecast_upper_bound
```

### 6. Model Training & Evaluation

**See:** [docs/MODEL_DEVELOPMENT.md](docs/MODEL_DEVELOPMENT.md)

- **Algorithm**: Prophet (handles missing data, holidays, multiple seasonalities)
- **Hyperparameter Tuning**: Grid search on validation set
- **Evaluation**: Time-series cross-validation with expanding window
- **Tracking**: All experiments logged to MLflow

### 7. Deployment

**See:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

| Deployment Type | Description | Update Frequency |
|-----------------|-------------|------------------|
| **Batch Predictions** | Daily forecasts written to Gold table | Every 24 hours |
| **Streamlit Dashboard** | Interactive visualization | Real-time query |

### 8. Monitoring & Feedback

**See:** [docs/MONITORING.md](docs/MONITORING.md)

**Logged for every prediction:**
- Timestamp
- Input features
- Predicted value
- Confidence interval
- Model version

**Alerts:**
- Data quality expectation failures
- Prediction accuracy degradation (MAPE > threshold)
- Missing data in source API

---

## Project Structure

```
chi311-intelligence-platform/
│
├── README.md                           # You are here
├── requirements.txt                    # Python dependencies
│
├── docs/                               # Documentation
│   ├── PORTFOLIO_FRAMEWORK.md          # How this project maps to ML portfolio framework
│   ├── PROJECT_SCOPING.md              # Problem definition & success metrics
│   ├── DATA_SOURCING.md                # Data collection strategy
│   ├── DATA_ARCHITECTURE.md            # Medallion + SCD2 architecture design
│   ├── FEATURE_ENGINEERING.md          # Feature documentation
│   ├── LABELING_STRATEGY.md            # How anomalies are labeled
│   ├── MODEL_DEVELOPMENT.md            # Model training approach
│   ├── DEPLOYMENT.md                   # Deployment strategy
│   └── MONITORING.md                   # Monitoring & feedback loops
│
├── notebooks/                          # Databricks notebooks
│   ├── 00_setup_exploration.py         # Initial setup & EDA
│   ├── 01_data_quality_checks.py       # Great Expectations validation
│   ├── 02_feature_engineering.py       # Feature development
│   ├── 03_model_experimentation.py     # Model experiments
│   ├── 04_ml_forecasting.py            # Production model training
│   ├── 05_anomaly_detection.py         # Anomaly scoring
│   └── poc_incremental_scd2.py         # SCD2 proof of concept demo
│
├── pipelines/                          # Lakeflow Declarative Pipelines
│   ├── chi311_scd2_pipeline.sql        # Main ETL with SCD Type 2
│   └── expectations/                   # Legacy expectations (deprecated)
│       └── data_quality_rules.yaml
│
├── great_expectations/                 # Great Expectations configuration
│   ├── great_expectations.yml          # GE configuration
│   └── expectations/                   # Expectation suites
│       ├── bronze_311_requests_suite.json
│       ├── silver_311_requests_suite.json
│       └── gold_daily_aggregates_suite.json
│
├── src/                                # Python source code
│   └── chi311/
│       ├── __init__.py
│       ├── ingestion/
│       │   ├── __init__.py
│       │   └── api_client.py           # Chicago Data Portal API client
│       ├── features/
│       │   ├── __init__.py
│       │   └── transformers.py         # Feature engineering functions
│       ├── models/
│       │   ├── __init__.py
│       │   └── forecaster.py           # Prophet model wrapper
│       ├── monitoring/
│       │   ├── __init__.py
│       │   └── logger.py               # Prediction logging
│       └── quality/
│           ├── __init__.py
│           └── ge_validator.py         # Great Expectations utilities
│
├── tests/                              # Test suite
│   ├── unit/
│   │   └── test_api_client.py
│   └── integration/
│       └── test_pipeline.py
│
├── app/                                # Streamlit dashboard
│   └── dashboard.py
│
└── .github/
    └── workflows/
        ├── ci.yml                      # Continuous integration
        └── deploy.yml                  # Deployment automation
```

---

## Success Metrics

### Business Metrics

| Metric | Description | Target | Measurement |
|--------|-------------|--------|-------------|
| **Detection Lead Time** | Hours before spike is detected | ≥2 hours | Compare alert time vs actual spike |
| **False Positive Rate** | % of alerts that weren't real spikes | ≤15% | Manual review of alerts |
| **Resource Efficiency** | Staff hours saved via forecasting | 10%+ | Operations team feedback |

### ML Metrics

| Metric | Description | Target | Current |
|--------|-------------|--------|---------|
| **MAPE** | Mean Absolute Percentage Error | ≤15% | - |
| **RMSE** | Root Mean Squared Error | ≤200 | - |
| **Anomaly Precision** | True positives / All flagged | ≥0.80 | - |
| **Anomaly Recall** | True positives / All actual anomalies | ≥0.70 | - |

### Data Engineering Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| **SCD2 Version Rate** | Avg versions per request | 1.2-1.5 |
| **Pipeline Latency** | Bronze to Gold processing time | <30 min |
| **Data Freshness** | Hours since latest record | <24 hours |

---

## Future Enhancements

### Phase 2: Advanced Features
- [ ] Real-time streaming with Kafka
- [ ] Multi-step forecasting (7, 14, 30 days)
- [ ] Per-ward specialized models
- [ ] Weather data integration

### Phase 3: Production Hardening
- [ ] A/B testing framework for model versions
- [ ] Automated retraining triggers
- [ ] SLA monitoring and alerting
- [ ] Cost optimization analysis

### Phase 4: Advanced Data Engineering
- [ ] SCD Type 4 (separate current dimension)
- [ ] Data Vault modeling for complex relationships
- [ ] Real-time CDC from operational systems

---

## Learning Resources

Based on the ML portfolio framework, these resources helped build this project:

- 📕 [Designing Machine Learning Systems](https://www.oreilly.com/library/view/designing-machine-learning/9781098107956/) - Chip Huyen
- 📗 [Software Engineering for Data Scientists](https://www.oreilly.com/library/view/software-engineering-for/9781098136194/) - Catherine Nelson
- 📘 [Databricks Lakeflow Documentation](https://docs.databricks.com/en/dlt/)
- 📙 [MLflow Documentation](https://mlflow.org/docs/latest/index.html)
- 📓 [The Data Warehouse Toolkit](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/books/data-warehouse-dw-toolkit/) - Kimball (SCD patterns)

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

