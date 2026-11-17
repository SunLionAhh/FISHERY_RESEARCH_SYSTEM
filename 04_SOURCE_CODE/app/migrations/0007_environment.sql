-- S05 环境数据：来源、批次、观测、自动获取日志与声学-环境配对。
-- 所有 timestamps 以本地 ISO 与 UTC ISO 并列保存；变量统一 SI 单位存 value_si。

CREATE TABLE IF NOT EXISTS environment_source (
    source_id           TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    kind                TEXT NOT NULL CHECK (kind IN ('MANUAL','DERIVED','AUTO')),
    provider            TEXT NOT NULL,
    dataset             TEXT,
    source_url          TEXT,
    spatial_coverage    TEXT,
    time_resolution     TEXT,
    units_json          TEXT NOT NULL,
    observed_or_forecast TEXT NOT NULL CHECK (observed_or_forecast IN ('OBSERVED','MODEL_HISTORICAL','FORECAST','UNKNOWN')),
    license             TEXT,
    authorization       TEXT,
    api_limits          TEXT,
    quality_note        TEXT,
    created_at          TEXT NOT NULL,
    actor               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS environment_import_batch (
    batch_id            TEXT PRIMARY KEY,
    source_id           TEXT NOT NULL REFERENCES environment_source(source_id),
    file_name           TEXT NOT NULL,
    file_sha256         TEXT NOT NULL,
    file_size_bytes     INTEGER NOT NULL,
    file_kind           TEXT NOT NULL CHECK (file_kind IN ('CSV','XLSX')),
    sheet_name          TEXT,
    field_mapping_json  TEXT NOT NULL,
    timezone            TEXT NOT NULL,
    row_count           INTEGER NOT NULL,
    accepted_count      INTEGER NOT NULL,
    rejected_count      INTEGER NOT NULL,
    duplicate_count     INTEGER NOT NULL,
    issue_summary_json  TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('IMPORTED','PARTIAL','REJECTED')),
    archive_path        TEXT,
    created_at          TEXT NOT NULL,
    actor               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS environment_observation (
    obs_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id            TEXT NOT NULL REFERENCES environment_import_batch(batch_id),
    source_id           TEXT NOT NULL REFERENCES environment_source(source_id),
    variable            TEXT NOT NULL CHECK (variable IN ('WATER_TEMP','TIDE_HEIGHT','WIND_SPEED','WIND_DIRECTION')),
    location_key        TEXT NOT NULL,
    station_id          TEXT,
    device_id           TEXT,
    observed_at         TEXT NOT NULL,
    observed_at_utc     TEXT NOT NULL,
    timezone            TEXT NOT NULL,
    value               REAL NOT NULL,
    unit                TEXT NOT NULL,
    value_si            REAL NOT NULL,
    quality_flag        TEXT NOT NULL CHECK (quality_flag IN ('OK','MODEL_HISTORICAL','FORECAST','DERIVED','SUSPECT')),
    raw_row_json        TEXT NOT NULL,
    UNIQUE(source_id, variable, location_key, observed_at_utc)
);

CREATE INDEX IF NOT EXISTS idx_env_obs_lookup
    ON environment_observation(variable, location_key, observed_at_utc);

CREATE TABLE IF NOT EXISTS environment_fetch_log (
    fetch_id            TEXT PRIMARY KEY,
    adapter             TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('ATTEMPTED','SUCCESS','FAILED','BLOCKED')),
    requested_at        TEXT NOT NULL,
    finished_at         TEXT,
    parameter_json      TEXT NOT NULL,
    records_written     INTEGER NOT NULL DEFAULT 0,
    error_message       TEXT,
    actor               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS environment_match (
    match_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id         TEXT NOT NULL,
    device_id           TEXT NOT NULL,
    acoustic_time       TEXT NOT NULL,
    variable            TEXT NOT NULL,
    obs_id              INTEGER NOT NULL REFERENCES environment_observation(obs_id),
    lag_hours           INTEGER NOT NULL DEFAULT 0,
    delta_seconds       INTEGER NOT NULL,
    tolerance_seconds   INTEGER NOT NULL,
    method              TEXT NOT NULL CHECK (method IN ('NEAREST','NONE')),
    acoustic_metric     TEXT NOT NULL,
    acoustic_value      REAL,
    environment_value   REAL
);

CREATE INDEX IF NOT EXISTS idx_env_match_analysis ON environment_match(analysis_id, device_id, lag_hours);
