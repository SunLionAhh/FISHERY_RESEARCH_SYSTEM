-- S04：比较查询与结果留痕。比较口径（筛选条件、时区、端点规则、基线成员）与结果同库保存，便于复现。
CREATE TABLE IF NOT EXISTS comparison_runs (
    comparison_id   TEXT PRIMARY KEY,
    name            TEXT,
    query_json      TEXT NOT NULL,
    result_json     TEXT NOT NULL,
    created_by      TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_comparison_runs_created_at ON comparison_runs(created_at DESC);
