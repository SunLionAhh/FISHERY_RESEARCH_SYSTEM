-- S03 迁移 0005：每日统计、缺测状态与产物清单
-- 纪律：所有正式统计必须绑定 analysis_runs（含参数/映射/算法版本快照）且来自 build_mask 硬掩码源。
-- 本迁移只追加表/视图，不修改 S01/S02 任何既有表或数据。

CREATE TABLE IF NOT EXISTS daily_statistics (
    stat_id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id                  TEXT NOT NULL REFERENCES devices(device_id),
    observed_date              TEXT NOT NULL,                 -- 观测日 YYYY-MM-DD（本地日期，不假定连续）
    status                     TEXT NOT NULL,                 -- COMPLETE/PARTIAL/MISSING/QC_FAILED/UPLOADED_LATE/REPROCESSED/UNKNOWN/BLOCKED
    observation_status         TEXT NOT NULL,                 -- COMPLETE/PARTIAL/MISSING/QC_FAILED/UNKNOWN
    upload_status              TEXT NOT NULL,                 -- NORMAL/UPLOADED_LATE/REPROCESSED/BLOCKED
    run_id                     TEXT REFERENCES analysis_runs(run_id),
    parameter_version          INTEGER,
    mapping_version            INTEGER,
    algorithm_version          TEXT NOT NULL,

    -- 记录数（分子/分母见 10_TEST_REPORTS/s03_verification/metric_definitions.csv）
    raw_records                INTEGER,
    valid_records              INTEGER,
    invalid_records            INTEGER,
    fully_masked_records       INTEGER,
    timestamp_formats_json     TEXT,
    timestamp_resolution_s     INTEGER,
    valid_observation_duration_s REAL,
    observation_span_s         REAL,
    planned_window_s           INTEGER,
    coverage_ratio             REAL,
    valid_record_ratio         REAL,

    -- 信号槽位与掩码取舍（一律来自 build_mask，禁止零填充）
    signal_slots_per_record    INTEGER,
    raw_signal_slots           INTEGER,
    kept_samples               INTEGER,
    excluded_samples           INTEGER,
    excluded_by_reason_json    TEXT,
    near_field_excluded_samples INTEGER,
    bottom_excluded_samples    INTEGER,

    -- 区内信号强度分布（仅 kept_values）
    signal_mean                REAL,
    signal_stddev              REAL,
    signal_min                 REAL,
    signal_max                 REAL,
    signal_p10                 REAL,
    signal_p25                 REAL,
    signal_median              REAL,
    signal_p75                 REAL,
    signal_p90                 REAL,
    signal_p95                 REAL,
    signal_p99                 REAL,
    signal_histogram_json      TEXT,
    quantile_method            TEXT,

    -- 候选回波事件（阈值算法 V1；仅为候选，非物种/鱼量结论）
    candidate_events           INTEGER,
    candidate_event_rate_per_hour REAL,
    candidate_event_algorithm  TEXT,

    -- 环境参考
    water_temp_mean            REAL,
    water_temp_min             REAL,
    water_temp_max             REAL,
    water_temp_records         INTEGER,

    -- 时间分布与缺测
    hourly_activity_json       TEXT,
    missing_intervals_json     TEXT,
    missing_interval_count     INTEGER,

    -- 追溯
    file_sha256                TEXT,
    dataset_id                 TEXT,
    qc_notes                   TEXT,
    blockage_reasons           TEXT,
    report_path                TEXT,
    created_at                 TEXT NOT NULL,
    UNIQUE (device_id, observed_date, run_id)
);

CREATE INDEX IF NOT EXISTS idx_daily_stat_device_date ON daily_statistics(device_id, observed_date DESC, stat_id DESC);
CREATE INDEX IF NOT EXISTS idx_daily_stat_run ON daily_statistics(run_id);

CREATE TABLE IF NOT EXISTS s03_artifacts (
    artifact_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT,
    device_id     TEXT,
    observed_date TEXT,
    artifact_type TEXT NOT NULL,      -- daily_report / daily_csv / chart / metric_definitions / index
    relative_path TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    UNIQUE (run_id, artifact_type, relative_path)
);

CREATE INDEX IF NOT EXISTS idx_s03_artifacts_run ON s03_artifacts(run_id, artifact_type);

-- 每个 (device_id, observed_date) 的最新结果；历史 run 不删除、不覆盖。
CREATE VIEW IF NOT EXISTS v_latest_daily_statistics AS
SELECT d.*
FROM daily_statistics d
JOIN (
    SELECT device_id, observed_date, MAX(stat_id) AS latest_id
    FROM daily_statistics
    GROUP BY device_id, observed_date
) x ON d.stat_id = x.latest_id;
