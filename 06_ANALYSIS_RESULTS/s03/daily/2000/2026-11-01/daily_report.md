# S03 每日统计日报 — 设备 2000 / 2026-11-01

- 状态：**UPLOADED_LATE**（观测状态 COMPLETE；上传状态 UPLOADED_LATE）
- run_id：`RUN-2000-20261101-20261117T023916Z-e91986`；算法版本：`DAILY_STATS_V1`
- 数据源：`NA`；SHA-256：`59b6730404ea8d367a90f44a3da1306cb2c758948d46c2cb8d5945bd9b93a9d7`
- 参数版本：1；映射版本：2
- 阻断原因：无

## 口径声明

所有区内样本均来自统一硬掩码 `app.services.distance_mapping.build_mask(allow_blocked=False)`：
人工截断 5.2 m、无浮点容差、跨界区间整段排除、盲区 0.5 m 与行内首零之前排除。
本日报不存在全量程统计，也不存在先用全量程再裁剪的结果。缺测指标一律 NA（空），**不填 0**；
仅当区内存在有效观测且未检出候选事件时，候选事件数才记为 0。

## 指标与分子/分母/单位

| 指标 | 值 | 分子 | 分母 | 单位 | NA 规则 |
| --- | --- | --- | --- | --- | --- |
| `raw_records` | 192732 | 当日文件数据行数（含解析异常行） | —（计数量） | 条 | 文件未上传=NA；上传后为真实计数，可为 0 |
| `valid_records` | 192732 | 时间戳可解析且 build_mask 后至少保留 1 个区内样本的行数 | —（计数量） | 条 | 文件未上传=NA |
| `invalid_records` | 0 | 解析错误行（空行/列数不符/字段非数值等） | —（计数量） | 条 | 文件未上传=NA |
| `fully_masked_records` | 0 | 无解析错误但掩码后 0 个区内样本的行 | —（计数量） | 条 | 文件未上传=NA |
| `signal_slots_per_record` | 1000 | 单条记录有效信号槽位众数（尾部空 token 不计） | —（结构量） | 点/条 | 文件未上传=NA |
| `raw_signal_slots` | 192732000 | Σ 每条记录有效信号槽位 | —（计数量） | 点 | 文件未上传=NA |
| `kept_samples` | 20852959 | Σ build_mask.kept_count | —（计数量） | 点 | 文件未上传=NA；BLOCKED 设备不得统计 |
| `excluded_samples` | 171879041 | Σ build_mask.excluded_total | —（计数量） | 点 | 文件未上传=NA |
| `near_field_excluded_samples` | 3238541 | 掩码原因 NEAR_FIELD 的样本数 | —（计数量） | 点 | 文件未上传=NA |
| `bottom_excluded_samples` | 0 | 掩码原因 BOTTOM_INTERFERENCE 的样本数 | —（计数量） | 点 | S07 启用自动探底前恒为 0；文件未上传=NA |
| `valid_observation_duration_s` | 86340 | 含至少 1 条有效记录的去重时间戳格数 × 时间戳分辨率 | —（时长量） | s | 文件未上传=NA；上限截断到 planned_window_s |
| `observation_span_s` | 86400 | 首末有效记录时间跨度 + 1 个时间戳格 | —（时长量） | s | 文件未上传=NA |
| `planned_window_s` | 86400 | 日历日窗口长度 | —（常量） | s | 恒为 86400（可显式覆盖并留痕） |
| `coverage_ratio` | 0.999306 | valid_observation_duration_s | planned_window_s | 比例 0—1 | 文件未上传或无区内有效观测=NA（时长 0 不等于覆盖率 0） |
| `valid_record_ratio` | 1 | valid_records | raw_records | 比例 0—1 | raw_records=0 或文件未上传=NA |
| `signal_mean` | 1.74427 | Σ kept_values | kept_samples | 强度单位（原始 0—255） | kept_samples=0 → NA，禁止填 0 |
| `signal_stddev` | 16.7009 | Σ(kept_value−mean)² / kept_samples 的平方根（总体标准差） | kept_samples | 强度单位 | kept_samples=0 → NA |
| `signal_median` | 0 | kept_values 的经验 0.5 分位数（线性插值） | kept_samples | 强度单位 | kept_samples=0 → NA |
| `signal_p10` | 0 | kept_values 的对应经验分位数 | kept_samples | 强度单位 | kept_samples=0 → NA |
| `signal_p25` | 0 | kept_values 的对应经验分位数 | kept_samples | 强度单位 | kept_samples=0 → NA |
| `signal_p75` | 0 | kept_values 的对应经验分位数 | kept_samples | 强度单位 | kept_samples=0 → NA |
| `signal_p90` | 0 | kept_values 的对应经验分位数 | kept_samples | 强度单位 | kept_samples=0 → NA |
| `signal_p95` | 0 | kept_values 的对应经验分位数 | kept_samples | 强度单位 | kept_samples=0 → NA |
| `signal_p99` | 47 | kept_values 的对应经验分位数 | kept_samples | 强度单位 | kept_samples=0 → NA |
| `candidate_events` | 12193 | 区内相邻有效槽位连续 ≥3 且值 ≥200 的极大段数 | —（计数量） | 次 | 区内存在有效观测但无候选 → 0；无区内有效观测 → NA |
| `candidate_event_rate_per_hour` | 508.395 | candidate_events | valid_observation_duration_s / 3600 | 次/小时 | 有效观测时长=0 或候选事件=NA → NA |
| `water_temp_mean` | 22.0861 | 有效记录的水温值 | 有水温的有效记录数 | °C | 无有效水温 → NA |
| `water_temp_min` | 21.8 | 有效记录的水温值 | 有水温的有效记录数 | °C | 无有效水温 → NA |
| `water_temp_max` | 22.3 | 有效记录的水温值 | 有水温的有效记录数 | °C | 无有效水温 → NA |
| `missing_intervals_json` | [{"start": "2026-11-01T12:07:00", "end": "2026-11-01T12:08:00", "duration_s": 60.0}] | 有效记录时间戳格之间的缺口（起、止、时长） | —（诊断量） | s | 文件未上传=NA |
| `excluded_by_reason_json` | {"CROSS_BOUNDARY_INTERVAL_EXCLUDED": 192732, "NEAR_FIELD": 3238541, "OUT_OF_RANGE_MANUAL_CUTOFF": 168447768} | build_mask 逐原因排除样本数 | —（诊断量） | 点 | 文件未上传=NA |
| `hourly_activity_json` | {"valid_records": [7976, 8067, 8153, 8097, 7912, 8133, 8079, 8112, 8087, 8069, 8046, 8038, 7847, 8023, 7566, 8052, 8097, 8032, 8132, 8084, 8057, 8034, 8007, 8032], "candidate_events": [270, 224, 139, 169, 651, 1406, 1047, 262, 376, 898, 951, 687, 187, 174, 42, 310, 517, 774, 415, 574, 634, 993, 249, 244], "kept_samples": [858175, 868918, 878470, 872532, 850945, 871505, 867321, 875783, 870935, 867156, 860555, 865433, 846657, 863009, 802720, 878696, 888838, 874717, 889556, 883317, 879650, 878514, 879073, 880484]} | 按时辰统计的有效记录/候选事件/区内样本 | —（诊断量） | 条/次/点 | 文件未上传=NA |
| `status` | UPLOADED_LATE | 缺测/质检状态（8 枚举 + BLOCKED） | —（状态量） | 枚举 | 不允许用 0 代替缺测 |

## 掩码与质检说明

- 原始记录 192732；有效记录 192732；解析异常 0；全掩码 0。
- 区内保留样本 20852959；排除样本 171879041。
- 排除原因：{"CROSS_BOUNDARY_INTERVAL_EXCLUDED": 192732, "NEAR_FIELD": 3238541, "OUT_OF_RANGE_MANUAL_CUTOFF": 168447768}
- 候选事件算法：CANDIDATE_RUN_V1(threshold>=200,min_bins=3,masked_indices_contiguous)（仅为候选，非物种或鱼量结论）
- QC 备注：BOTTOM_INTERFERENCE 预留给 S07 自动探底，本阶段为 0，不代表无近底影响

## 追溯

- 参数/映射/算法快照：`{"algorithm_version": "DAILY_STATS_V1", "analysis_cutoff_slant_m": 5.2, "batch_id": "BATCH-2000-20261101-20261117T023916Z-046517", "candidate_event_algorithm": "CANDIDATE_RUN_V1(threshold>=200,min_bins=3,masked_indices_contiguous)", "dataset_id": null, "device_id": "2000", "event_min_bins": 3, "event_threshold": 200.0, "file_sha256": "59b6730404ea8d367a90f44a3da1306cb2c758948d46c2cb8d5945bd9b93a9d7", "first_sample_distance_m": 0.5, "limit": null, "mapping_support_status": "CONFIRMED", "mapping_version": 2, "observed_date": "2026-11-01", "operator": "Administrator", "parameter_id": 1, "parameter_version": 1, "planned_window_s": 86400, "relative_path": "01_ORIGINAL_DATA/FISHFINDER/2000/探鱼-2000_2026-11-01.csv", "sample_interval_m": 0.0375, "sample_mode": "INTERVAL", "upload_date": "2026-11-17", "upload_status": "UPLOADED_LATE"}`
- 图表：见 `07_FIGURES/s03/2000/2026-11-01/`
