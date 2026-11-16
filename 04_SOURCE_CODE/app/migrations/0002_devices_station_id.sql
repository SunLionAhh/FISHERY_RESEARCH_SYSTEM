-- S01 整改 P2-1：设备增加站位归属（任务二「每台独立保存 station_id」）
-- 可空：站位未分配时保持 NULL，禁止伪造站位名称或坐标（stations 表保持为空直到用户提供）。
ALTER TABLE devices ADD COLUMN station_id TEXT REFERENCES stations(station_id);
