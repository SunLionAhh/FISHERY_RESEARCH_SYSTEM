-- S06：日内 15 分钟基础格、天文分类与典型日留痕
CREATE TABLE IF NOT EXISTS s06_time_grid (
    grid_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id           TEXT NOT NULL,
    observed_date       TEXT NOT NULL,
    slot_start          TEXT NOT NULL,          -- 本地时区 ISO，半开区间起点
    slot_end            TEXT NOT NULL,
    valid_records       INTEGER NOT NULL DEFAULT 0,
    candidate_events    INTEGER NOT NULL DEFAULT 0,
    kept_samples        INTEGER NOT NULL DEFAULT 0,
    distinct_seconds    INTEGER NOT NULL DEFAULT 0,
    coverage_ratio      REAL,                   -- distinct_seconds / 900
    source_file_sha     TEXT,
    method_version      TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    UNIQUE (device_id, observed_date, slot_start)
);
CREATE INDEX IF NOT EXISTS idx_s06_grid_device_date ON s06_time_grid(device_id, observed_date, slot_start);

CREATE TABLE IF NOT EXISTS s06_analysis_run (
    run_id              TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    criteria_json       TEXT NOT NULL,
    result_json         TEXT NOT NULL,
    method_version      TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    actor               TEXT NOT NULL DEFAULT 'web'
);
