-- S05 整改：自动获取框架（适配器注册、定时、重试、缓存、历史补取）
CREATE TABLE IF NOT EXISTS environment_adapter_registry (
    adapter_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    module_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('BLOCKED','ENABLED','DISABLED')),
    config_json TEXT,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS environment_fetch_schedule (
    schedule_id TEXT PRIMARY KEY,
    adapter_id TEXT NOT NULL REFERENCES environment_adapter_registry(adapter_id),
    parameter_json TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL CHECK (interval_minutes > 0),
    enabled INTEGER NOT NULL DEFAULT 1,
    next_run_at TEXT,
    last_run_at TEXT,
    last_status TEXT,
    failure_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS environment_fetch_cache (
    cache_key TEXT PRIMARY KEY,
    adapter_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    expires_at TEXT,
    actor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS environment_fetch_retry (
    retry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    adapter_id TEXT NOT NULL,
    attempt_no INTEGER NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_env_fetch_due ON environment_fetch_schedule(enabled,next_run_at);
