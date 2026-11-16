-- S01 扩展：每日观测天气（按 device_id + observation_date 一条，保留历史可查）
-- 天气是随日期/站位变化的人工观测环境描述，不随声学 CSV 导入（规范未定义，属界面自定义扩展项）。
-- 天气码封闭枚举：SUNNY=晴天 / CLOUDY=阴天 / RAINY=阴雨天。
-- 不做版本链：同一天同一设备重复录入视为更正，覆盖当天值并写审计日志（与设备参数的不可变版本链区分）。
CREATE TABLE IF NOT EXISTS daily_weather (
    weather_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT NOT NULL REFERENCES devices(device_id),
    observation_date TEXT NOT NULL,                 -- 观测日期 YYYY-MM-DD（当地日）
    weather_code    TEXT NOT NULL CHECK (weather_code IN ('SUNNY','CLOUDY','RAINY')),
    source          TEXT NOT NULL,                  -- 来源必填，可追溯（如 USER_FIELD_OBSERVATION）
    notes           TEXT,
    created_at      TEXT NOT NULL,
    created_by      TEXT NOT NULL DEFAULT 'web',
    updated_at      TEXT NOT NULL,
    UNIQUE (device_id, observation_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_weather_device_date
    ON daily_weather (device_id, observation_date DESC);
