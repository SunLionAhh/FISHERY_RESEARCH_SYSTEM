-- S08：站位 GPS、站间距离与空间展示留痕
CREATE TABLE IF NOT EXISTS station_location (
    location_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id               TEXT,                      -- P1—P5；未提供时保持 NULL，不自动分配
    device_id                TEXT NOT NULL REFERENCES devices(device_id),
    longitude_deg            REAL,
    latitude_deg             REAL,
    coordinate_reference_system TEXT,
    gps_accuracy_m           REAL,
    water_depth_m            REAL,
    position_source          TEXT NOT NULL,
    measured_at              TEXT,
    heading_deg              REAL,                      -- 探头水平朝向；NULL = UNKNOWN，不画方向足迹
    heading_reference        TEXT,
    effective_from           TEXT NOT NULL,
    effective_to             TEXT,
    created_at               TEXT NOT NULL,
    created_by               TEXT NOT NULL,
    UNIQUE (device_id, effective_from, position_source)
);

CREATE TABLE IF NOT EXISTS station_distance (
    distance_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    station_a     TEXT NOT NULL,
    station_b     TEXT NOT NULL,
    device_a      TEXT NOT NULL,
    device_b      TEXT NOT NULL,
    distance_m    REAL NOT NULL,
    method        TEXT NOT NULL,
    computed_at   TEXT NOT NULL,
    crs_pair      TEXT,
    status        TEXT NOT NULL DEFAULT 'OK',
    note          TEXT,
    UNIQUE (station_a, station_b, method)
);
CREATE INDEX IF NOT EXISTS idx_station_location_device ON station_location(device_id, effective_from);
