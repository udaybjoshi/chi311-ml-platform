# Project Scoping Document

**NYC 311 Service Request Intelligence Platform**

*ML Portfolio Framework: Component 1 - Problem Framing & Metrics*

---

## Executive Summary

This document defines the scope, success criteria, and constraints for the NYC 311 Service Request Intelligence Platform. The platform provides demand forecasting, anomaly detection, and lifecycle analytics for NYC's 311 non-emergency service system.

**Key Differentiators:**
- SCD Type 2 tracking for full request lifecycle history
- Great Expectations for declarative data quality
- Production-grade patterns on zero-cost infrastructure

---

## Problem Statement

### Current State

NYC 311 operations teams currently lack:
1. **Visibility into demand spikes** until resources are already overwhelmed
2. **Historical lifecycle tracking** - when status changes occur and how long requests stay in each state
3. **Proactive resource allocation** based on predicted demand
4. **Data quality assurance** on incoming service request data

This results in:
- Delayed response times during high-demand periods
- Inefficient staffing (overstaffed on slow days, understaffed on busy days)
- No insight into operational bottlenecks (e.g., requests stuck "In Progress")
- Reactive rather than proactive operations

### Desired State

A platform that provides:
1. **7-day demand forecasts** for staffing optimization
2. **Anomaly alerts** 2+ hours before spikes overwhelm resources
3. **Request lifecycle analytics** - time-in-status, transition patterns
4. **Automated data quality gates** preventing bad data from reaching analytics

---

## Target Users

| User | Role | Primary Need | How Platform Helps |
|------|------|--------------|-------------------|
| **Operations Manager** | Oversee daily 311 ops | Early warning of demand spikes | Anomaly alerts 2+ hours ahead |
| **Call Center Supervisor** | Staff scheduling | Forecast next-day volume | 7-day volume predictions |
| **Resource Planner** | Capacity planning | Trend analysis & seasonality | Historical patterns + forecasts |
| **Data Analyst** | Performance reporting | Request lifecycle insights | SCD2 time-in-status analytics |
| **Data Engineer** | Pipeline reliability | Data quality assurance | Great Expectations validation |

### Primary User Story

> As a **311 Operations Manager**, I want to **receive alerts when service request volumes are unusually high** so that I can **reallocate staff before response times degrade**.

### Secondary User Story

> As a **Data Analyst**, I want to **understand how long requests stay in each status** so that I can **identify operational bottlenecks and improve resolution times**.

---

## Success Metrics

### Business Metrics

| Metric | Target | Measurement Method | Priority |
|--------|--------|-------------------|----------|
| Detection Lead Time | ≥2 hours | Time between alert and actual spike | P0 |
| False Positive Rate | ≤15% | % of alerts that were not true spikes | P0 |
| Staffing Efficiency | +10% | Reduction in overtime during spikes | P1 |
| Response Time SLA | 95% maintained | % of requests resolved within SLA | P1 |

### Machine Learning Metrics

| Metric | Target | Purpose | Measurement |
|--------|--------|---------|-------------|
| Forecast MAPE | ≤15% | Daily volume prediction accuracy | Mean Absolute Percentage Error |
| Forecast RMSE | ≤200 | Absolute error magnitude | Root Mean Squared Error |
| Anomaly Precision | ≥0.80 | Avoid false alarms | True Positives / Predicted Positives |
| Anomaly Recall | ≥0.70 | Catch real anomalies | True Positives / Actual Positives |
| Coverage | ≥0.95 | Confidence interval reliability | % actuals within predicted CI |

### Data Engineering Metrics

| Metric | Target | Purpose | Measurement |
|--------|--------|---------|-------------|
| Pipeline Latency | <30 min | Bronze to Gold processing time | End-to-end duration |
| Data Freshness | <24 hours | Time since latest record | Max created_date lag |
| Quality Gate Pass Rate | ≥95% | Data meeting expectations | GE validation success rate |
| SCD2 Version Rate | 1.5-3.0 | History tracking effectiveness | Avg versions per request |

### Proxy Metrics

Since we cannot directly measure business impact in a portfolio project:
- **Forecast accuracy** serves as proxy for staffing efficiency
- **Precision/Recall** serves as proxy for alert quality
- **Time-in-status** serves as proxy for operational bottleneck identification

---

## Technical Approach

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA INGESTION                              │
│  NYC Open Data API → API Client → Databricks Volume             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  DATA QUALITY (Great Expectations)              │
│  Bronze Expectations → Silver Expectations → Gold Expectations  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               LAKEFLOW PIPELINE (Medallion + SCD2)              │
│  Bronze (Raw) → Silver (SCD2 History) → Gold (Aggregates)       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ML PIPELINE (MLflow)                         │
│  Feature Engineering → Prophet Training → Anomaly Detection     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SERVING & MONITORING                          │
│  Streamlit Dashboard ← Batch Predictions ← Prediction Logging   │
└─────────────────────────────────────────────────────────────────┘
```

### Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **History Tracking** | SCD Type 2 | Enables lifecycle analytics (time-in-status, transitions) |
| **Data Quality** | Great Expectations | Declarative, reusable, self-documenting |
| **ETL Framework** | Lakeflow Declarative Pipelines | Native SCD2 support via APPLY CHANGES INTO |
| **Forecasting** | Prophet | Handles seasonality, holidays, missing data automatically |
| **Experiment Tracking** | MLflow | Native Databricks integration |
| **Serving** | Batch + Streamlit | Fits Free Edition constraints |

---

## Constraints

### Budget

| Constraint | Limit | Impact |
|------------|-------|--------|
| Compute Cost | $0 | Databricks Free Edition only |
| Cloud Infrastructure | $0 | No AWS/GCP/Azure compute |
| API Costs | $0 | Only free-tier APIs |
| Storage | Free tier | Databricks managed storage |

### Databricks Free Edition Quotas

| Resource | Limit | Mitigation |
|----------|-------|------------|
| All-Purpose Clusters | 1 concurrent | Schedule jobs sequentially |
| SQL Warehouse | 2X-Small | Optimize queries |
| Lakeflow Pipelines | Limited | Single pipeline with all layers |
| Storage | 15 GB | Retain 2 years history max |

### Latency Requirements

| Requirement | Acceptable Latency | Rationale |
|-------------|-------------------|-----------|
| Data Ingestion | 6 hours | Daily batch is sufficient |
| Pipeline Processing | 30 minutes | Bronze → Gold transformation |
| Dashboard Refresh | 15 minutes | Near real-time not required |
| Anomaly Alerts | 1 hour | Still provides 2+ hour lead time |

### Data Constraints

| Constraint | Details |
|------------|---------|
| Source | NYC Open Data Portal (public API) |
| Privacy | No PII - geographic data only |
| History | 2+ years for seasonality modeling |
| Volume | ~8,000-12,000 records/day |
| Freshness | API updates every 24 hours |

---

## Scope

### In Scope

#### Phase 1: Data Platform (This Release)

| Component | Deliverable | Status |
|-----------|-------------|--------|
| **Data Ingestion** | API client with SCD2 support (fetch new + updated records) | ✅ |
| **Data Quality** | Great Expectations suites for Bronze/Silver/Gold | ✅ |
| **Data Pipeline** | Lakeflow pipeline with SCD Type 2 | ✅ |
| **Feature Engineering** | Temporal, lag, and categorical features | ✅ |
| **Forecasting** | Prophet model with MLflow tracking | ✅ |
| **Anomaly Detection** | Threshold-based detection on forecast residuals | ✅ |
| **Dashboard** | Streamlit visualization | ✅ |
| **Monitoring** | Prediction logging, accuracy tracking | ✅ |

#### Lifecycle Analytics (Enabled by SCD2)

| Analysis | Query Pattern | Business Value |
|----------|---------------|----------------|
| Time-in-Status | AVG(hours_in_status) by status | Identify bottlenecks |
| Status Transitions | COUNT by from_status → to_status | Understand workflow |
| Point-in-Time | Status on specific date | Historical reporting |
| Resolution Velocity | Time from Open → Closed | SLA compliance |

### Out of Scope

| Item | Reason | Future Phase |
|------|--------|--------------|
| Real-time streaming | Batch sufficient, Free Edition limits | Phase 3 |
| Borough-level models | Increases complexity, diminishing returns | Phase 2 |
| Complaint type prediction | Different ML problem | Phase 2 |
| Weather data integration | Adds external dependency | Phase 2 |
| Model Serving API | Not available in Free Edition | Phase 3 |
| Automated retraining | Requires job orchestration | Phase 2 |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| API rate limiting | Medium | High | Exponential backoff, local caching |
| Model accuracy degradation | Medium | Medium | Weekly monitoring, drift detection |
| Databricks quota exceeded | Low | High | Optimize scheduling, single pipeline |
| Data quality issues | Medium | Medium | Great Expectations gates at each layer |
| Seasonality shift (COVID-like) | Low | High | Periodic retraining, regime detection |
| SCD2 table growth | Medium | Low | Retention policy, partition pruning |

---

## Alternatives Considered

### History Tracking

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **SCD Type 2** | Full history, time-in-status | More storage, complexity | ✅ Selected |
| SCD Type 1 | Simple, less storage | Loses history | ❌ |
| SCD Type 3 | Previous + current | Limited history | ❌ |
| Event Sourcing | Complete audit trail | Overkill for this use case | ❌ |

### Data Quality Framework

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **Great Expectations** | Declarative, data docs, profiling | Learning curve | ✅ Selected |
| Custom PySpark | Full control | More code to maintain | ❌ |
| Lakeflow Expectations | Native integration | Limited to DLT pipelines | ❌ (supplementary) |
| dbt tests | Good for SQL | Requires dbt setup | ❌ |

### Forecasting Approach

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **Prophet** | Handles seasonality, holidays | Slower on large data | ✅ Selected |
| ARIMA | Well-understood, fast | Manual seasonality config | ❌ |
| XGBoost | Flexible, fast | Requires more features | ❌ Phase 2 |
| LSTM | Captures complex patterns | Overkill, needs more data | ❌ |

### Deployment

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **Batch + Streamlit** | Free, simple, interactive | Not real-time | ✅ Selected |
| Model Serving Endpoint | Production-grade | Not in Free Edition | ❌ |
| Scheduled Notebook | Easy | Less interactive | ❌ |

---

## Timeline

### Realistic Build Order

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| 1. Discovery & Foundation | Week 1 | API client, EDA notebook, data sourcing docs |
| 2. Data Quality Framework | Week 2 | Great Expectations setup, Bronze suite, validator |
| 3. Data Pipeline | Week 2-3 | Lakeflow pipeline (Bronze/Silver/Gold), SCD2 |
| 4. Feature Engineering | Week 3 | Feature transformers, feature notebook |
| 5. Model Development | Week 4 | Prophet training, MLflow tracking, anomaly detection |
| 6. Monitoring & Serving | Week 5 | Prediction logging, Streamlit dashboard |
| 7. Testing & CI/CD | Week 6 | Unit tests, integration tests, GitHub Actions |
| 8. Polish & Documentation | Week 6 | README, architecture docs, cleanup |

**Total: ~6 weeks** (part-time, portfolio project pace)

---

## Definition of Done

### Pipeline Complete When:
- [ ] Bronze layer ingests raw API data
- [ ] Great Expectations validates Bronze data (≥95% pass rate)
- [ ] Silver layer implements SCD Type 2 with APPLY CHANGES INTO
- [ ] Great Expectations validates Silver data (≥95% pass rate)
- [ ] Gold layer produces daily aggregates
- [ ] Great Expectations validates Gold data (≥95% pass rate)
- [ ] Pipeline runs end-to-end without errors

### ML Complete When:
- [ ] Prophet model achieves MAPE ≤15% on test set
- [ ] Experiments tracked in MLflow
- [ ] Best model registered in MLflow Model Registry
- [ ] Anomaly detection identifies spikes with precision ≥0.80

### Platform Complete When:
- [ ] Dashboard displays forecasts and anomalies
- [ ] Predictions logged for monitoring
- [ ] CI/CD pipeline runs tests on PR
- [ ] Documentation covers all components
- [ ] README provides complete setup instructions

---

## Approval Checklist

- [x] Problem clearly defined with business impact
- [x] Target users identified with specific needs
- [x] Success metrics are measurable and realistic
- [x] Constraints documented (budget, compute, data)
- [x] Scope boundaries clear (in/out of scope)
- [x] Technical approach justified with alternatives
- [x] Risks assessed with mitigations
- [x] Timeline realistic for portfolio project
- [x] Definition of Done specified


---

## References

- [NYC Open Data - 311 Service Requests](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9)
- [Databricks Free Edition](https://docs.databricks.com/en/getting-started/free-edition.html)
- [Great Expectations Documentation](https://docs.greatexpectations.io/)
- [Prophet Documentation](https://facebook.github.io/prophet/)
- [Kimball SCD Types](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/type-2/)
