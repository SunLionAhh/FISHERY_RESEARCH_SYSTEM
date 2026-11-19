-- S08 V4.1：共享查询状态、分组/聚合/色标契约与同源结果快照
ALTER TABLE spatial_combination_runs ADD COLUMN query_context_json TEXT;
ALTER TABLE spatial_combination_runs ADD COLUMN query_fingerprint TEXT;
ALTER TABLE spatial_combination_runs ADD COLUMN grouping_mode TEXT;
ALTER TABLE spatial_combination_runs ADD COLUMN group_members_json TEXT;
ALTER TABLE spatial_combination_runs ADD COLUMN aggregation_mode TEXT;
ALTER TABLE spatial_combination_runs ADD COLUMN baseline_id TEXT;
ALTER TABLE spatial_combination_runs ADD COLUMN color_scale_id TEXT;
ALTER TABLE spatial_combination_runs ADD COLUMN metric_id TEXT;
ALTER TABLE spatial_combination_runs ADD COLUMN analysis_plan_version TEXT;
ALTER TABLE spatial_combination_runs ADD COLUMN mask_version TEXT;
ALTER TABLE spatial_combination_runs ADD COLUMN result_json TEXT;
