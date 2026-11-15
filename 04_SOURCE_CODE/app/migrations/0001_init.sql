-- S01 迁移 0001：核心表结构（V4 03 第四章任务一：12 张表）
-- 约定：所有时间戳 UTC ISO-8601；生效区间 [effective_from, effective_to)；旧版本行只追加、不更新数值列。

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    device_id          TEXT PRIMARY KEY,           -- '2000','2001','2002','2003','2005'；无 2004
    model              TEXT,
    serial_number      TEXT,
    frequency_khz      REAL,
    range_m            REAL,
    gain_db            REAL,
    firmware           TEXT,
    calibration_status TEXT,
    install_date       TEXT,
    status             TEXT NOT NULL DEFAULT 'PENDING_USER_INPUT',  -- ACTIVE / PENDING_USER_INPUT
    notes              TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stations (
    station_id                 TEXT PRIMARY KEY,
    name                       TEXT NOT NULL,
    longitude_deg              REAL,
    latitude_deg               REAL,
    coordinate_reference_system TEXT,
    notes                      TEXT,
    created_at                 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device_parameter_versions (
    parameter_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id               TEXT NOT NULL REFERENCES devices(device_id),
    version                 INTEGER NOT NULL,
    -- 离底参考：显式输入类型，另一侧为派生值（不写回用户输入）
    clearance_input_type    TEXT CHECK (clearance_input_type IN ('VERTICAL','AXIS_SLANT','UNKNOWN')),
    vertical_bottom_clearance_m REAL,           -- 用户输入（VERTICAL）或 NULL
    axis_slant_m                REAL,           -- 用户输入（AXIS_SLANT）或 NULL
    derived_vertical_clearance_m REAL,          -- 派生值，标记 is_derived
    derived_axis_slant_m         REAL,          -- 派生值
    derivation_tilt_deg     REAL,               -- 派生时使用的倾角
    is_derived              INTEGER NOT NULL DEFAULT 0,
    -- 人工分析截断（硬上限，独立于派生值，永不覆盖）
    analysis_cutoff_slant_m REAL,
    downward_tilt_deg       REAL,               -- 相对水平面向下为正
    tilt_reference          TEXT,
    beam_angle_value_deg    REAL,
    beam_angle_kind         TEXT CHECK (beam_angle_kind IN ('FULL','HALF','UNKNOWN')),
    beam_full_angle_deg     REAL,
    beam_half_angle_deg     REAL,               -- FULL: value/2；HALF: value
    heading_deg             REAL,               -- 真北 0°、顺时针；NULL=UNKNOWN
    heading_reference       TEXT,
    measurement_method      TEXT,
    uncertainty             TEXT,
    source                  TEXT NOT NULL,
    change_reason           TEXT,
    effective_from          TEXT NOT NULL,
    effective_to            TEXT,
    created_at              TEXT NOT NULL,
    created_by              TEXT NOT NULL DEFAULT 'web',
    UNIQUE (device_id, version)
);

CREATE TABLE IF NOT EXISTS device_parameters (
    device_id             TEXT PRIMARY KEY REFERENCES devices(device_id),
    current_parameter_id  INTEGER REFERENCES device_parameter_versions(parameter_id),
    updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device_positions (
    position_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id                   TEXT NOT NULL REFERENCES devices(device_id),
    version                     INTEGER NOT NULL,
    longitude_deg               REAL NOT NULL,
    latitude_deg                REAL NOT NULL,
    coordinate_reference_system TEXT,           -- NULL=UNKNOWN，禁止默认 WGS84
    position_accuracy_m         REAL,
    position_source             TEXT NOT NULL,
    heading_deg                 REAL,
    heading_reference           TEXT,
    effective_from              TEXT NOT NULL,
    effective_to                TEXT,
    notes                       TEXT,
    created_at                  TEXT NOT NULL,
    created_by                  TEXT NOT NULL DEFAULT 'web',
    UNIQUE (device_id, version)
);

CREATE TABLE IF NOT EXISTS device_installations (
    installation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT NOT NULL REFERENCES devices(device_id),
    station_id      TEXT REFERENCES stations(station_id),
    install_date    TEXT,
    removed_date    TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bottom_references (
    reference_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id             TEXT NOT NULL REFERENCES devices(device_id),
    reference_type        TEXT NOT NULL CHECK (reference_type IN ('USER_DEFINED_ESTIMATED','AUTO_DETECTED')),
    vertical_height_m     REAL,
    acoustic_bottom_status TEXT CHECK (acoustic_bottom_status IN ('NOT_DETECTED','DETECTED','PENDING')),
    effective_from        TEXT NOT NULL,
    effective_to          TEXT,
    source                TEXT NOT NULL,
    notes                 TEXT,
    created_at            TEXT NOT NULL,
    UNIQUE (device_id, reference_type, effective_from)
);

CREATE TABLE IF NOT EXISTS file_registry (
    file_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    relative_path   TEXT NOT NULL UNIQUE,
    file_name       TEXT NOT NULL,
    device_id       TEXT REFERENCES devices(device_id),
    observed_date   TEXT,
    size_bytes      INTEGER NOT NULL,
    sha256          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'ARCHIVED_REGISTERED',  -- ARCHIVED_REGISTERED / IMPORTED / CONFLICT
    import_batch_id TEXT,
    conflict_note   TEXT,
    registered_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_batches (
    batch_id    TEXT PRIMARY KEY,
    device_id   TEXT NOT NULL REFERENCES devices(device_id),
    upload_date TEXT NOT NULL,
    file_count  INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'OPEN',
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id               TEXT PRIMARY KEY,
    dataset_id           TEXT REFERENCES datasets(dataset_id),
    device_id            TEXT REFERENCES devices(device_id),
    params_snapshot_json TEXT,                 -- 新任务配置快照：含参数版本 id，历史结果不随新参数漂移
    status               TEXT NOT NULL DEFAULT 'PENDING',
    created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id  TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    phase       INTEGER NOT NULL,
    start_time  TEXT,
    end_time    TEXT,
    status      TEXT NOT NULL DEFAULT 'PLANNED',
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS dataset_members (
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    device_id  TEXT NOT NULL REFERENCES devices(device_id),
    PRIMARY KEY (dataset_id, device_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT NOT NULL,
    entity      TEXT NOT NULL,
    entity_id   TEXT,
    detail_json TEXT,
    actor       TEXT NOT NULL DEFAULT 'web',
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_param_versions_device ON device_parameter_versions(device_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_positions_device ON device_positions(device_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_file_registry_device ON file_registry(device_id);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_logs(entity, entity_id);
