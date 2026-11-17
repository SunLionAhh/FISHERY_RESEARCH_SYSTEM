-- S07：深度、人工底界、三水层、长期规律与数据集阶段冻结
ALTER TABLE datasets ADD COLUMN formal_sync_time TEXT;
ALTER TABLE datasets ADD COLUMN installation_status TEXT;
ALTER TABLE datasets ADD COLUMN dataset_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE datasets ADD COLUMN frozen_at TEXT;
ALTER TABLE datasets ADD COLUMN frozen_by TEXT;
ALTER TABLE datasets ADD COLUMN freeze_reason TEXT;

CREATE TABLE IF NOT EXISTS dataset_versions (
    version_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id             TEXT NOT NULL REFERENCES datasets(dataset_id),
    version                INTEGER NOT NULL,
    status                 TEXT NOT NULL,
    start_time             TEXT,
    end_time               TEXT,
    formal_sync_time       TEXT,
    phase                  INTEGER NOT NULL,
    boundaries_json        TEXT NOT NULL,
    hashes_json            TEXT NOT NULL,
    run_ids_json           TEXT NOT NULL,
    parameter_versions_json TEXT NOT NULL,
    note                   TEXT,
    created_at             TEXT NOT NULL,
    created_by             TEXT NOT NULL,
    UNIQUE (dataset_id, version)
);

CREATE TABLE IF NOT EXISTS s07_bottom_qc (
    qc_id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id                    TEXT NOT NULL REFERENCES devices(device_id),
    observed_date                TEXT NOT NULL,
    parameter_id                 TEXT,
    bottom_reference_id          INTEGER,
    method                       TEXT NOT NULL,
    status                       TEXT NOT NULL,
    center_axis_bottom_m         REAL,
    near_edge_bottom_m           REAL,
    far_edge_bottom_m            REAL,
    near_bottom_candidate_samples INTEGER NOT NULL DEFAULT 0,
    bottom_after_candidate_samples INTEGER NOT NULL DEFAULT 0,
    excluded_samples             INTEGER NOT NULL DEFAULT 0,
    reason                       TEXT,
    details_json                 TEXT NOT NULL,
    created_at                   TEXT NOT NULL,
    created_by                   TEXT NOT NULL,
    UNIQUE (device_id, observed_date, method, status)
);

CREATE TABLE IF NOT EXISTS s07_layer_stats (
    layer_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id         TEXT NOT NULL REFERENCES devices(device_id),
    observed_date     TEXT NOT NULL,
    layer             TEXT NOT NULL CHECK (layer IN ('UPPER','MIDDLE','LOWER','NA')),
    parameter_id      TEXT,
    mapping_version   INTEGER,
    method_version    TEXT NOT NULL,
    file_sha256       TEXT NOT NULL,
    kept_samples      INTEGER NOT NULL DEFAULT 0,
    candidate_events  INTEGER NOT NULL DEFAULT 0,
    signal_mean       REAL,
    signal_median     REAL,
    min_range_m       REAL,
    max_range_m       REAL,
    min_height_above_bottom_m REAL,
    max_height_above_bottom_m REAL,
    created_at        TEXT NOT NULL,
    created_by        TEXT NOT NULL,
    UNIQUE (device_id, observed_date, layer, method_version, file_sha256)
);

CREATE TABLE IF NOT EXISTS s07_pattern_versions (
    pattern_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_key       TEXT NOT NULL,
    version           INTEGER NOT NULL,
    dataset_id        TEXT REFERENCES datasets(dataset_id),
    devices_json      TEXT NOT NULL,
    window_json       TEXT NOT NULL,
    evidence_level    TEXT NOT NULL CHECK (evidence_level IN ('L0','L1','L2','L3')),
    status            TEXT NOT NULL,
    supporting_json   TEXT NOT NULL,
    contradicting_json TEXT NOT NULL,
    metrics_json      TEXT NOT NULL,
    note              TEXT,
    supersedes_id     INTEGER REFERENCES s07_pattern_versions(pattern_id),
    created_at        TEXT NOT NULL,
    created_by        TEXT NOT NULL,
    UNIQUE (pattern_key, version)
);

CREATE INDEX IF NOT EXISTS idx_s07_qc_device_date ON s07_bottom_qc(device_id, observed_date);
CREATE INDEX IF NOT EXISTS idx_s07_layer_device_date ON s07_layer_stats(device_id, observed_date);
CREATE INDEX IF NOT EXISTS idx_s07_pattern_key ON s07_pattern_versions(pattern_key, version);
