-- S02：距离映射版本表（规范 6.8/09 K05）
-- 每个 (device_id, range_m, 采样定义) 的映射独立版本化；证据与来源必须记录。
-- sample_mode：POINT=采样中心点，INTERVAL=距离单元区间（无拆分支持时跨界整段排除），UNKNOWN=未核实。
-- support_status：CONFIRMED=已核实可用；UNVERIFIED=已登记但未核实（正式距离分析 BLOCKED）；BLOCKED=明确阻断。
CREATE TABLE distance_mappings (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES devices(device_id),
    version INTEGER NOT NULL,
    range_m REAL,
    point_count INTEGER,
    sample_mode TEXT NOT NULL CHECK (sample_mode IN ('POINT', 'INTERVAL', 'UNKNOWN')),
    first_sample_distance_m REAL,
    sample_interval_m REAL,
    support_status TEXT NOT NULL CHECK (support_status IN ('CONFIRMED', 'UNVERIFIED', 'BLOCKED')),
    evidence TEXT,
    source TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (device_id, version)
);

CREATE INDEX idx_distance_mappings_device_range
    ON distance_mappings (device_id, range_m, version);
