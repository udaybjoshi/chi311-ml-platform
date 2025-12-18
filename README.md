# NYC 311 Service Request Intelligence Platform

> **A Production-Grade ML Portfolio Project** demonstrating end-to-end machine learning engineering on Databricks Free Edition with Lakeflow Declarative Pipelines and MLflow.

[![Databricks](https://img.shields.io/badge/Databricks-Free%20Edition-FF3621?logo=databricks)](https://databricks.com)
[![MLflow](https://img.shields.io/badge/MLflow-Experiment%20Tracking-0194E2?logo=mlflow)](https://mlflow.org)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)](https://python.org)

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

NYC's 311 service handles **millions of non-emergency requests annually** - from noise complaints to infrastructure issues. City operations teams face a critical challenge: **detecting unusual spikes in service requests before they overwhelm resources**.

### Solution

This platform provides:
- **Demand Forecasting**: Predict future 311 request volumes using Prophet time series models
- **Anomaly Detection**: Identify unusual spikes using model-based thresholds
- **Operational Dashboard**: Real-time insights for resource planning

### Target Users

| User | Need | How This Helps |
|------|------|----------------|
| **City Operations Manager** | Plan staffing for upcoming week | 7-day demand forecasts by borough |
| **311 Call Center Supervisor** | Spot unusual activity | Real-time anomaly alerts |
| **Resource Planner** | Allocate resources by complaint type | Historical patterns + predictions |

---

## ML Portfolio Framework Alignment

This project follows the [8-component ML portfolio framework](docs/PORTFOLIO_FRAMEWORK.md) for production-grade projects:

| Component | Status | Implementation |
|-----------|--------|----------------|
| 1. **Problem Framing & Metrics** | ✅ | Business KPIs + ML metrics defined |
| 2. **Unique Data Sourcing** | ✅ | NYC Open Data API with continuous collection |
| 3. **Data Storage** | ✅ | Delta Lake on Unity Catalog (Medallion Architecture) |
| 4. **Feature Engineering** | ✅ | Temporal, categorical, and lag features |
| 5. **Labeling Strategy** | ✅ | Programmatic labeling via Prophet thresholds |
| 6. **Model Training & Evaluation** | ✅ | MLflow experiment tracking + hyperparameter tuning |
| 7. **Deployment** | ✅ | Batch predictions + Streamlit dashboard |
| 8. **Monitoring & Feedback** | ✅ | Prediction logging + data quality checks |

See [docs/PORTFOLIO_FRAMEWORK.md](docs/PORTFOLIO_FRAMEWORK.md) for detailed alignment documentation.

---

## Architecture

### High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NYC 311 INTELLIGENCE PLATFORM                       │
│                      (Databricks Free Edition + Lakeflow)                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  DATA INGESTION (Continuous Collection)                                     │
│  ┌─────────────────┐                                                        │
│  │ NYC Open Data   │ ──API──▶ Scheduled Jobs ──▶ Bronze Layer               │
│  │ Socrata API     │         (Daily at 3 AM)                                │
│  └─────────────────┘                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAKEFLOW DECLARATIVE PIPELINE (ETL)                                        │
│                                                                             │
│  ┌────────────┐      ┌────────────┐      ┌────────────┐                     │
│  │   BRONZE   │ ───▶ │   SILVER   │ ───▶ │    GOLD    │                     │
│  │  Raw JSON  │      │  Cleaned   │      │ Aggregates │                     │
│  │            │      │  Validated │      │  Features  │                     │
│  └────────────┘      └────────────┘      └────────────┘                     │
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

### Technology Stack

| Layer | Technology | Why This Choice |
|-------|------------|-----------------|
| **Compute** | Databricks Free Edition | Zero cost, serverless, full Lakeflow access |
| **Storage** | Delta Lake + Unity Catalog | ACID transactions, time travel, governance |
| **ETL** | Lakeflow Declarative Pipelines | Declarative SQL/Python, auto-optimization |
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
git clone https://github.com/YOUR_USERNAME/nyc311-intelligence-platform.git
cd nyc311-intelligence-platform
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
databricks workspace import_dir ./notebooks /Workspace/Users/YOUR_EMAIL/nyc311
```

### Step 4: Create Lakeflow Pipeline

1. Navigate to **Workflows** → **Lakeflow Declarative Pipelines**
2. Click **Create Pipeline**
3. Point to `pipelines/nyc311_medallion_pipeline.sql`
4. Run the pipeline

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

- **Source**: [NYC Open Data - 311 Service Requests](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9)
- **API**: Socrata Open Data API (SODA)
- **Update Frequency**: Daily incremental loads
- **Historical Depth**: 2+ years for seasonality modeling

### 3. Data Storage (Medallion Architecture)

**See:** [docs/DATA_ARCHITECTURE.md](docs/DATA_ARCHITECTURE.md)

| Layer | Table | Description | Retention |
|-------|-------|-------------|-----------|
| Bronze | `bronze.raw_311_requests` | Raw API responses | 90 days |
| Silver | `silver.cleaned_311_requests` | Validated, deduped | 2 years |
| Gold | `gold.daily_aggregates` | ML-ready features | Permanent |
| Gold | `gold.forecasts` | Model predictions | 90 days |
| Gold | `gold.anomalies` | Detected anomalies | 1 year |

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
- Borough encoding
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
nyc311-intelligence-platform/
│
├── README.md                           # You are here
├── requirements.txt                    # Python dependencies
├── pyproject.toml                      # Project metadata
│
├── docs/                               # Documentation
│   ├── PORTFOLIO_FRAMEWORK.md          # How this project maps to ML portfolio framework
│   ├── PROJECT_SCOPING.md              # Problem definition & success metrics
│   ├── DATA_SOURCING.md                # Data collection strategy
│   ├── DATA_ARCHITECTURE.md            # Medallion architecture design
│   ├── FEATURE_ENGINEERING.md          # Feature documentation
│   ├── LABELING_STRATEGY.md            # How anomalies are labeled
│   ├── MODEL_DEVELOPMENT.md            # Model training approach
│   ├── DEPLOYMENT.md                   # Deployment strategy
│   └── MONITORING.md                   # Monitoring & feedback loops
│
├── notebooks/                          # Databricks notebooks
│   ├── 00_setup_exploration.py         # Initial setup & EDA
│   ├── 01_data_quality_checks.py       # Data validation notebook
│   ├── 02_feature_engineering.py       # Feature development
│   ├── 03_model_experimentation.py     # Model experiments
│   ├── 04_ml_forecasting.py            # Production model training
│   └── 05_anomaly_detection.py         # Anomaly scoring
│
├── pipelines/                          # Lakeflow Declarative Pipelines
│   ├── nyc311_medallion_pipeline.sql   # Main ETL pipeline (SQL)
│   ├── nyc311_medallion_pipeline.py    # Main ETL pipeline (Python)
│   └── expectations/                   # Data quality rules
│       └── data_quality_rules.yaml
│
├── src/                                # Python source code
│   └── nyc311/
│       ├── __init__.py
│       ├── ingestion/
│       │   ├── __init__.py
│       │   └── api_client.py           # NYC Open Data API client
│       ├── features/
│       │   ├── __init__.py
│       │   └── transformers.py         # Feature engineering functions
│       ├── models/
│       │   ├── __init__.py
│       │   ├── forecaster.py           # Prophet model wrapper
│       │   └── anomaly_detector.py     # Anomaly detection logic
│       └── monitoring/
│           ├── __init__.py
│           └── logger.py               # Prediction logging
│
├── tests/                              # Test suite
│   ├── unit/
│   │   ├── test_api_client.py
│   │   ├── test_transformers.py
│   │   └── test_forecaster.py
│   └── integration/
│       └── test_pipeline.py
│
├── app/                                # Streamlit dashboard
│   ├── dashboard.py
│   ├── requirements.txt
│   └── components/
│       ├── forecasts.py
│       └── anomalies.py
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

---

## Future Enhancements

### Phase 2: Advanced Features
- [ ] Real-time streaming with Kafka
- [ ] Multi-step forecasting (7, 14, 30 days)
- [ ] Per-borough specialized models
- [ ] Weather data integration

### Phase 3: Production Hardening
- [ ] A/B testing framework for model versions
- [ ] Automated retraining triggers
- [ ] SLA monitoring and alerting
- [ ] Cost optimization analysis

---

## Learning Resources

Based on the ML portfolio framework, these resources helped build this project:

- 📕 [Designing Machine Learning Systems](https://www.oreilly.com/library/view/designing-machine-learning/9781098107956/) - Chip Huyen
- 📗 [Software Engineering for Data Scientists](https://www.oreilly.com/library/view/software-engineering-for/9781098136194/) - Catherine Nelson
- 📘 [Databricks Lakeflow Documentation](https://docs.databricks.com/en/ldp/)
- 📙 [MLflow Documentation](https://mlflow.org/docs/latest/index.html)

---

##  Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---


