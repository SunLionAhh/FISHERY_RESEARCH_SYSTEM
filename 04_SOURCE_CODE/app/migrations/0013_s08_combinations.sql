-- S08 增强：任意设备组合空间分析留痕
CREATE TABLE IF NOT EXISTS spatial_combination_runs (
    run_id TEXT PRIMARY KEY,
    device_list TEXT NOT NULL,
    devices_json TEXT NOT NULL,
    n_devices INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    observed_date TEXT NOT NULL,
    parameter_versions_json TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    comparison_modes_json TEXT NOT NULL,
    method_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL
);
