-- =============================================================================
-- Chicago 311 Intelligence Platform - Lakeflow Declarative Pipeline
-- =============================================================================
--
-- Architecture:
--   Bronze (Streaming) -> Silver (SCD Type 2 history) -> Gold (aggregates)
--
-- Target runtime: Databricks Free Edition serverless DLT pipeline.
--
-- Configuration (set in the pipeline JSON under the `configuration` key):
--   chi311.landing_path -> /Volumes/workspace/raw/chi311_landing
--
-- Example pipeline configuration:
-- {
--   "catalog": "workspace",
--   "schema": "bronze",
--   "configuration": {
--     "chi311.landing_path": "/Volumes/workspace/raw/chi311_landing"
--   }
-- }
--
-- Free-Edition-specific constraints honored here:
--   * No combined PARTITIONED BY + CLUSTER BY (UC rejects this): we pick
--     one per table.
--   * No pipeline-level spark_conf overrides that require init scripts;
--     Delta auto-optimize is sufficient for serverless.
--   * read_files() source path is parameterized via pipeline config so
--     the same SQL runs on any catalog.
--
-- Deploy from a Databricks Asset Bundle (see ../databricks.yml) or by
-- pointing a new DLT pipeline at this file and adding the configuration
-- block above.
-- =============================================================================


-- =============================================================================
-- BRONZE LAYER: Raw landing zone
-- =============================================================================
-- Append-only streaming table fed by Autoloader over the landing Volume.
-- The ingestion notebook (notebooks/02_ingestion/02_bronze_autoloader.py)
-- can alternatively populate this table; both paths coexist because the
-- Delta checkpoint is per-writer.
-- =============================================================================

CREATE OR REFRESH STREAMING TABLE bronze_raw_311_requests
COMMENT "Raw 311 service requests from Chicago Data Portal - landing zone"
TBLPROPERTIES (
    "quality" = "bronze",
    "pipelines.autoOptimize.managed" = "true",
    "delta.autoOptimize.optimizeWrite" = "true",
    "delta.autoOptimize.autoCompact" = "true"
)
AS SELECT
    sr_number,
    created_date,
    closed_date,
    last_modified_date,
    sr_type,
    sr_short_code,
    owner_department,
    status,
    ward,
    community_area,
    street_address,
    city,
    state,
    zip_code,
    latitude,
    longitude,
    location,
    origin,
    duplicate,
    legacy_record,
    current_timestamp() AS _ingestion_timestamp,
    _metadata.file_path AS _source_file
FROM STREAM read_files(
    '${chi311.landing_path}',
    format => 'json',
    multiLine => true,
    recursiveFileLookup => true
);


-- =============================================================================
-- BRONZE STAGING: Cleaned + CDC-ready
-- =============================================================================
-- Applies deterministic cleaning and derives the `_sequence_timestamp`
-- column that APPLY CHANGES INTO uses for CDC ordering.
--
-- Note: the EXPECT constraints match the POST-projection column values
-- (e.g. status is UPPER'd in the SELECT, so the value-set check is on the
-- uppercase set). A mismatch here was the single biggest bug in the
-- previous version of this pipeline.
-- =============================================================================

CREATE OR REFRESH STREAMING TABLE bronze_staged_311_requests (
    CONSTRAINT valid_sr_number     EXPECT (sr_number IS NOT NULL) ON VIOLATION DROP ROW,
    CONSTRAINT valid_created_date  EXPECT (created_date IS NOT NULL) ON VIOLATION DROP ROW,
    CONSTRAINT valid_sr_type       EXPECT (sr_type IS NOT NULL) ON VIOLATION DROP ROW,
    CONSTRAINT valid_status        EXPECT (status IS NOT NULL) ON VIOLATION DROP ROW,
    CONSTRAINT valid_status_values EXPECT (status IN ('OPEN', 'COMPLETED', 'CANCELED')) ON VIOLATION DROP ROW
)
COMMENT "Staged 311 requests ready for SCD2 processing - cleaned and validated"
TBLPROPERTIES (
    "quality" = "bronze",
    "delta.autoOptimize.optimizeWrite" = "true",
    "delta.autoOptimize.autoCompact" = "true"
)
AS SELECT
    sr_number,

    -- Sequence column for ordering CDC events.
    -- Priority: last_modified > closed > created > ingestion.
    COALESCE(
        TO_TIMESTAMP(last_modified_date),
        TO_TIMESTAMP(closed_date),
        TO_TIMESTAMP(created_date),
        _ingestion_timestamp
    ) AS _sequence_timestamp,

    TO_TIMESTAMP(created_date)       AS created_date,
    TO_TIMESTAMP(closed_date)        AS closed_date,
    TO_TIMESTAMP(last_modified_date) AS last_modified_date,

    TRIM(sr_type)                    AS sr_type,
    TRIM(sr_short_code)              AS sr_short_code,
    TRIM(owner_department)           AS owner_department,
    UPPER(TRIM(status))              AS status,

    CAST(ward AS INT)                AS ward,
    TRIM(community_area)             AS community_area,
    TRIM(street_address)             AS street_address,
    TRIM(zip_code)                   AS zip_code,

    -- Chicago bounding box check; NULL out coords that fall outside.
    CASE
        WHEN CAST(latitude AS DOUBLE) BETWEEN 41.6 AND 42.1
         AND CAST(longitude AS DOUBLE) BETWEEN -87.95 AND -87.5
        THEN CAST(latitude AS DOUBLE)
        ELSE NULL
    END AS latitude,
    CASE
        WHEN CAST(latitude AS DOUBLE) BETWEEN 41.6 AND 42.1
         AND CAST(longitude AS DOUBLE) BETWEEN -87.95 AND -87.5
        THEN CAST(longitude AS DOUBLE)
        ELSE NULL
    END AS longitude,

    UPPER(TRIM(origin))              AS origin,
    CAST(duplicate AS BOOLEAN)       AS is_duplicate,
    CAST(legacy_record AS BOOLEAN)   AS is_legacy,

    (TRIM(sr_type) = '311 INFORMATION ONLY CALL') AS is_info_call,

    _ingestion_timestamp,
    _source_file
FROM STREAM(LIVE.bronze_raw_311_requests);


-- =============================================================================
-- SILVER LAYER: SCD Type 2 history
-- =============================================================================
-- `APPLY CHANGES INTO` emits the __START_AT / __END_AT metadata columns.
-- Liquid clustering on sr_number gives efficient key-lookups; we do NOT
-- partition this table (partition + cluster cannot coexist, and liquid
-- clustering is the right tool for high-cardinality business keys).
-- =============================================================================

CREATE OR REFRESH STREAMING TABLE silver_scd2_311_requests
COMMENT "SCD Type 2 history of 311 service requests - tracks all status changes"
CLUSTER BY (sr_number)
TBLPROPERTIES (
    "quality" = "silver",
    "pipelines.autoOptimize.managed" = "true",
    "delta.autoOptimize.optimizeWrite" = "true",
    "delta.autoOptimize.autoCompact" = "true",
    "delta.targetFileSize" = "134217728"
);

APPLY CHANGES INTO LIVE.silver_scd2_311_requests
FROM STREAM(LIVE.bronze_staged_311_requests)
KEYS (sr_number)
SEQUENCE BY _sequence_timestamp
COLUMNS * EXCEPT (_ingestion_timestamp, _source_file, _sequence_timestamp)
STORED AS SCD TYPE 2;


-- =============================================================================
-- SILVER LAYER: Current-state materialized view
-- =============================================================================
-- Materialized (not a LIVE VIEW) because Gold tables depend on it and we
-- want to pay the `__END_AT IS NULL` filter once per run, not per Gold
-- table.
-- =============================================================================

CREATE OR REFRESH LIVE TABLE silver_current_311_requests
COMMENT "Current state of 311 requests (latest SCD2 version only)"
CLUSTER BY (sr_number)
TBLPROPERTIES (
    "quality" = "silver",
    "pipelines.autoOptimize.managed" = "true",
    "delta.autoOptimize.optimizeWrite" = "true",
    "delta.autoOptimize.autoCompact" = "true"
)
AS SELECT
    sr_number,
    created_date,
    closed_date,
    last_modified_date,
    sr_type,
    sr_short_code,
    owner_department,
    status,
    ward,
    community_area,
    street_address,
    zip_code,
    latitude,
    longitude,
    origin,
    is_duplicate,
    is_legacy,
    is_info_call,
    CASE
        WHEN closed_date IS NOT NULL
        THEN (UNIX_TIMESTAMP(closed_date) - UNIX_TIMESTAMP(created_date)) / 3600.0
        ELSE NULL
    END AS resolution_hours,
    __START_AT AS valid_from,
    __END_AT   AS valid_to
FROM LIVE.silver_scd2_311_requests
WHERE __END_AT IS NULL;


-- =============================================================================
-- SILVER LAYER: Status-history view
-- =============================================================================
CREATE OR REFRESH LIVE VIEW silver_status_history
COMMENT "Full status-change history for 311 requests"
AS SELECT
    sr_number,
    created_date,
    status,
    sr_type,
    ward,
    is_info_call,
    __START_AT AS version_start,
    __END_AT   AS version_end,
    CASE
        WHEN __END_AT IS NOT NULL
        THEN (UNIX_TIMESTAMP(__END_AT) - UNIX_TIMESTAMP(__START_AT)) / 3600.0
        ELSE (UNIX_TIMESTAMP(current_timestamp()) - UNIX_TIMESTAMP(__START_AT)) / 3600.0
    END AS hours_in_status,
    ROW_NUMBER() OVER (PARTITION BY sr_number ORDER BY __START_AT) AS version_number,
    (__END_AT IS NULL) AS is_current
FROM LIVE.silver_scd2_311_requests;


-- =============================================================================
-- GOLD LAYER
-- =============================================================================
-- Every Gold table below is PARTITIONED BY date. We do NOT add CLUSTER BY
-- because UC rejects the combination. Time-range queries dominate the
-- workload, so partitioning wins; inside a partition Delta's optimizeWrite
-- keeps files at target size without needing ZORDER.
-- =============================================================================


-- Gold 1: Daily aggregates by ward + SR type
CREATE OR REFRESH LIVE TABLE gold_daily_aggregates
COMMENT "Daily aggregates by ward and service request type"
PARTITIONED BY (date)
TBLPROPERTIES (
    "quality" = "gold",
    "pipelines.autoOptimize.managed" = "true",
    "delta.autoOptimize.optimizeWrite" = "true",
    "delta.autoOptimize.autoCompact" = "true",
    "delta.targetFileSize" = "134217728"
)
AS SELECT
    DATE(created_date) AS date,
    ward,
    sr_type,
    is_info_call,
    COUNT(*) AS total_requests,
    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_count,
    SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) AS open_count,
    SUM(CASE WHEN status = 'CANCELED' THEN 1 ELSE 0 END) AS canceled_count,
    AVG(resolution_hours) AS avg_resolution_hours,
    PERCENTILE_APPROX(resolution_hours, 0.5) AS median_resolution_hours,
    SUM(CASE WHEN status = 'COMPLETED' THEN 1.0 ELSE 0.0 END) / COUNT(*) AS completion_rate,
    SUM(CASE WHEN origin = 'PHONE' THEN 1 ELSE 0 END) AS phone_requests,
    SUM(CASE WHEN origin = 'WEB'   THEN 1 ELSE 0 END) AS web_requests,
    SUM(CASE WHEN origin = 'APP'   THEN 1 ELSE 0 END) AS app_requests,
    DAYOFWEEK(DATE(created_date)) AS day_of_week,
    MONTH(DATE(created_date)) AS month,
    CASE WHEN DAYOFWEEK(DATE(created_date)) IN (1, 7) THEN 1 ELSE 0 END AS is_weekend,
    current_timestamp() AS _processed_at
FROM LIVE.silver_current_311_requests
GROUP BY DATE(created_date), ward, sr_type, is_info_call;


-- Gold 2: Ward daily summary with lag/rolling features
CREATE OR REFRESH LIVE TABLE gold_ward_daily_summary
COMMENT "Ward-level daily summary with lag features for forecasting"
PARTITIONED BY (date)
TBLPROPERTIES (
    "quality" = "gold",
    "pipelines.autoOptimize.managed" = "true",
    "delta.autoOptimize.optimizeWrite" = "true",
    "delta.autoOptimize.autoCompact" = "true",
    "delta.targetFileSize" = "134217728"
)
AS
WITH daily_counts AS (
    SELECT
        DATE(created_date) AS date,
        ward,
        COUNT(*) AS total_requests,
        SUM(CASE WHEN NOT is_info_call THEN 1 ELSE 0 END) AS service_requests,
        SUM(CASE WHEN     is_info_call THEN 1 ELSE 0 END) AS info_calls,
        COUNT(DISTINCT sr_type) AS unique_sr_types,
        AVG(resolution_hours) AS avg_resolution_hours,
        SUM(CASE WHEN status = 'COMPLETED' THEN 1.0 ELSE 0.0 END) / COUNT(*) AS completion_rate
    FROM LIVE.silver_current_311_requests
    GROUP BY DATE(created_date), ward
)
SELECT
    date,
    ward,
    total_requests,
    service_requests,
    info_calls,
    unique_sr_types,
    avg_resolution_hours,
    completion_rate,
    LAG(total_requests, 1)  OVER (PARTITION BY ward ORDER BY date) AS requests_1d_ago,
    LAG(total_requests, 7)  OVER (PARTITION BY ward ORDER BY date) AS requests_7d_ago,
    LAG(total_requests, 28) OVER (PARTITION BY ward ORDER BY date) AS requests_28d_ago,
    AVG(total_requests) OVER (
        PARTITION BY ward ORDER BY date ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING
    ) AS rolling_7d_avg,
    AVG(total_requests) OVER (
        PARTITION BY ward ORDER BY date ROWS BETWEEN 29 PRECEDING AND 1 PRECEDING
    ) AS rolling_28d_avg,
    DAYOFWEEK(date) AS day_of_week,
    MONTH(date) AS month,
    CASE WHEN DAYOFWEEK(date) IN (1, 7) THEN 1 ELSE 0 END AS is_weekend,
    current_timestamp() AS _processed_at
FROM daily_counts;


-- Gold 3: Citywide daily summary (primary Prophet input)
-- Exploration baselines: mean + 2sigma thresholds -> 7,580 (all) / 4,851 (service-only).
CREATE OR REFRESH LIVE TABLE gold_citywide_daily_summary
COMMENT "Citywide daily summary - primary table for Prophet forecasting"
PARTITIONED BY (date)
TBLPROPERTIES (
    "quality" = "gold",
    "pipelines.autoOptimize.managed" = "true",
    "delta.autoOptimize.optimizeWrite" = "true",
    "delta.autoOptimize.autoCompact" = "true",
    "delta.targetFileSize" = "134217728"
)
AS
WITH daily_totals AS (
    SELECT
        DATE(created_date) AS date,
        COUNT(*) AS total_requests,
        SUM(CASE WHEN NOT is_info_call THEN 1 ELSE 0 END) AS service_requests,
        SUM(CASE WHEN     is_info_call THEN 1 ELSE 0 END) AS info_calls,
        COUNT(DISTINCT sr_type) AS unique_sr_types,
        COUNT(DISTINCT ward) AS wards_with_requests,
        AVG(resolution_hours) AS avg_resolution_hours,
        AVG(CASE WHEN resolution_hours > 0.1 THEN resolution_hours END)
            AS avg_resolution_hours_excl_instant,
        SUM(CASE WHEN status = 'COMPLETED' THEN 1.0 ELSE 0.0 END) / COUNT(*) AS completion_rate
    FROM LIVE.silver_current_311_requests
    GROUP BY DATE(created_date)
)
SELECT
    date AS ds,
    service_requests AS y,
    date,
    total_requests,
    service_requests,
    info_calls,
    unique_sr_types,
    wards_with_requests,
    avg_resolution_hours,
    avg_resolution_hours_excl_instant,
    completion_rate,
    LAG(service_requests, 1)   OVER (ORDER BY date) AS requests_1d_ago,
    LAG(service_requests, 7)   OVER (ORDER BY date) AS requests_7d_ago,
    LAG(service_requests, 28)  OVER (ORDER BY date) AS requests_28d_ago,
    LAG(service_requests, 365) OVER (ORDER BY date) AS requests_1y_ago,
    AVG(service_requests) OVER (ORDER BY date ROWS BETWEEN 8  PRECEDING AND 1 PRECEDING) AS rolling_7d_avg,
    AVG(service_requests) OVER (ORDER BY date ROWS BETWEEN 29 PRECEDING AND 1 PRECEDING) AS rolling_28d_avg,
    CASE
        WHEN LAG(service_requests, 365) OVER (ORDER BY date) > 0
        THEN (service_requests - LAG(service_requests, 365) OVER (ORDER BY date)) * 1.0
             / LAG(service_requests, 365) OVER (ORDER BY date)
        ELSE NULL
    END AS yoy_change,
    DAYOFWEEK(date) AS day_of_week,
    MONTH(date)     AS month,
    DAYOFYEAR(date) AS day_of_year,
    WEEKOFYEAR(date) AS week_of_year,
    CASE WHEN DAYOFWEEK(date) IN (1, 7) THEN 1 ELSE 0 END AS is_weekend,
    (service_requests > 4851) AS is_anomaly_service,
    (total_requests   > 7580) AS is_anomaly_total,
    current_timestamp() AS _processed_at
FROM daily_totals;


-- Gold 4: Status-transition analysis (uses SCD2 history)
CREATE OR REFRESH LIVE TABLE gold_status_transitions
COMMENT "Status transition patterns from SCD2 history"
TBLPROPERTIES (
    "quality" = "gold",
    "pipelines.autoOptimize.managed" = "true",
    "delta.autoOptimize.optimizeWrite" = "true",
    "delta.autoOptimize.autoCompact" = "true"
)
AS
WITH status_versions AS (
    SELECT
        sr_number,
        status,
        sr_type,
        is_info_call,
        version_start,
        version_end,
        hours_in_status,
        version_number,
        LEAD(status) OVER (PARTITION BY sr_number ORDER BY version_start) AS next_status
    FROM LIVE.silver_status_history
)
SELECT
    status AS from_status,
    next_status AS to_status,
    is_info_call,
    COUNT(*) AS transition_count,
    AVG(hours_in_status) AS avg_hours_before_transition,
    PERCENTILE_APPROX(hours_in_status, 0.5) AS median_hours_before_transition,
    AVG(CASE WHEN hours_in_status > 0.1 THEN hours_in_status END) AS avg_hours_excl_instant,
    MIN(hours_in_status) AS min_hours,
    MAX(hours_in_status) AS max_hours,
    current_timestamp() AS _processed_at
FROM status_versions
WHERE next_status IS NOT NULL
GROUP BY status, next_status, is_info_call;


-- Gold 5: Department performance
CREATE OR REFRESH LIVE TABLE gold_department_performance
COMMENT "Department-level performance metrics"
PARTITIONED BY (date)
TBLPROPERTIES (
    "quality" = "gold",
    "pipelines.autoOptimize.managed" = "true",
    "delta.autoOptimize.optimizeWrite" = "true",
    "delta.autoOptimize.autoCompact" = "true",
    "delta.targetFileSize" = "134217728"
)
AS SELECT
    owner_department,
    DATE(created_date) AS date,
    COUNT(*) AS total_requests,
    SUM(CASE WHEN NOT is_info_call THEN 1 ELSE 0 END) AS service_requests,
    COUNT(DISTINCT sr_type) AS sr_types_handled,
    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_count,
    SUM(CASE WHEN status = 'COMPLETED' THEN 1.0 ELSE 0.0 END) / COUNT(*) AS completion_rate,
    AVG(resolution_hours) AS avg_resolution_hours,
    PERCENTILE_APPROX(resolution_hours, 0.5) AS median_resolution_hours,
    PERCENTILE_APPROX(resolution_hours, 0.9) AS p90_resolution_hours,
    current_timestamp() AS _processed_at
FROM LIVE.silver_current_311_requests
GROUP BY owner_department, DATE(created_date);


-- Gold 6: SR-type daily summary
CREATE OR REFRESH LIVE TABLE gold_sr_type_summary
COMMENT "Service-request-type daily summary"
PARTITIONED BY (date)
TBLPROPERTIES (
    "quality" = "gold",
    "pipelines.autoOptimize.managed" = "true",
    "delta.autoOptimize.optimizeWrite" = "true",
    "delta.autoOptimize.autoCompact" = "true",
    "delta.targetFileSize" = "134217728"
)
AS SELECT
    DATE(created_date) AS date,
    sr_type,
    is_info_call,
    COUNT(*) AS total_requests,
    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_count,
    SUM(CASE WHEN status = 'COMPLETED' THEN 1.0 ELSE 0.0 END) / COUNT(*) AS completion_rate,
    AVG(resolution_hours) AS avg_resolution_hours,
    MODE(ward) AS most_common_ward,
    COUNT(DISTINCT ward) AS wards_affected,
    current_timestamp() AS _processed_at
FROM LIVE.silver_current_311_requests
GROUP BY DATE(created_date), sr_type, is_info_call;


-- =============================================================================
-- DATA QUALITY MONITORING VIEWS
-- =============================================================================

CREATE OR REFRESH LIVE VIEW dq_scd2_version_stats
COMMENT "Data quality: SCD2 versioning statistics"
AS SELECT
    COUNT(DISTINCT sr_number) AS total_unique_requests,
    COUNT(*) AS total_versions,
    ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT sr_number), 2) AS avg_versions_per_request,
    SUM(CASE WHEN __END_AT IS NULL     THEN 1 ELSE 0 END) AS current_versions,
    SUM(CASE WHEN __END_AT IS NOT NULL THEN 1 ELSE 0 END) AS historical_versions,
    MAX(__START_AT) AS latest_version_start,
    CASE
        WHEN ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT sr_number), 2) BETWEEN 1.0 AND 2.0
        THEN 'HEALTHY' ELSE 'INVESTIGATE'
    END AS version_rate_status
FROM LIVE.silver_scd2_311_requests;


CREATE OR REFRESH LIVE VIEW dq_pipeline_freshness
COMMENT "Data quality: pipeline freshness"
AS
SELECT
    'bronze_raw' AS layer,
    MAX(_ingestion_timestamp) AS latest_record,
    COUNT(*) AS total_records,
    (UNIX_TIMESTAMP(current_timestamp()) - UNIX_TIMESTAMP(MAX(_ingestion_timestamp))) / 3600.0
        AS hours_since_update
FROM LIVE.bronze_raw_311_requests
UNION ALL
SELECT
    'silver_scd2' AS layer,
    MAX(__START_AT) AS latest_record,
    COUNT(*) AS total_records,
    (UNIX_TIMESTAMP(current_timestamp()) - UNIX_TIMESTAMP(MAX(__START_AT))) / 3600.0
        AS hours_since_update
FROM LIVE.silver_scd2_311_requests;


CREATE OR REFRESH LIVE VIEW dq_info_call_ratio
COMMENT "Data quality: info-call ratio (expected ~40%)"
AS SELECT
    DATE(created_date) AS date,
    COUNT(*) AS total_requests,
    SUM(CASE WHEN is_info_call THEN 1 ELSE 0 END) AS info_calls,
    ROUND(SUM(CASE WHEN is_info_call THEN 1.0 ELSE 0.0 END) / COUNT(*) * 100, 1) AS info_call_pct,
    CASE
        WHEN SUM(CASE WHEN is_info_call THEN 1.0 ELSE 0.0 END) / COUNT(*) BETWEEN 0.35 AND 0.45
        THEN 'NORMAL' ELSE 'INVESTIGATE'
    END AS ratio_status
FROM LIVE.silver_current_311_requests
GROUP BY DATE(created_date);


CREATE OR REFRESH LIVE VIEW dq_status_distribution
COMMENT "Data quality: status value distribution"
AS SELECT
    status,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
FROM LIVE.silver_current_311_requests
GROUP BY status;
