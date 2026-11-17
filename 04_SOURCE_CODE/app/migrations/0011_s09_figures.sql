-- S09：16 类科研图登记、Origin 桥接任务与动态导出留痕
CREATE TABLE IF NOT EXISTS figure_registry (
    figure_id TEXT PRIMARY KEY,
    figure_class TEXT NOT NULL,
    priority TEXT NOT NULL,
    title TEXT NOT NULL,
    engine TEXT NOT NULL,
    status TEXT NOT NULL,
    run_id TEXT,
    dataset_id TEXT,
    source_csv TEXT,
    output_png TEXT,
    caption TEXT,
    units_json TEXT,
    metric_definition TEXT,
    quality_note TEXT,
    data_condition TEXT,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS figure_exports (
    export_id TEXT PRIMARY KEY,
    figure_id TEXT NOT NULL,
    export_format TEXT NOT NULL,
    file_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS origin_tasks (
    task_id TEXT PRIMARY KEY,
    figure_id TEXT,
    status TEXT NOT NULL,
    task_package TEXT NOT NULL,
    worker_log TEXT,
    opju_path TEXT,
    reopen_check TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    actor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS animation_exports (
    export_id TEXT PRIMARY KEY,
    source_frames TEXT NOT NULL,
    export_format TEXT NOT NULL,
    file_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    frame_count INTEGER NOT NULL,
    consistency_check TEXT NOT NULL,
    created_at TEXT NOT NULL
);
