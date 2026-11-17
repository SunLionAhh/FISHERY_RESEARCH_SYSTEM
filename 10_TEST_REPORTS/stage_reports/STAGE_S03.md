# STAGE_S03 — 每日统计、逐日增量上传、缺测管理与基础图表

> 阶段：S03（L2）｜依据：`FISHERY_FULL_PLAN_V4/03_CODEX_STAGE_TASKS_FINAL.md` 第六章、`09_DEVELOPER_ACCEPTANCE.md`（K07—K09/K14—K18/K25/K40）、V4 前置门槛条款
> 执行日期：2026-11-17｜环境：Windows 11 / 项目 `.venv` Python 3.10.11 / pytest 9.2.0 / matplotlib 3.10.9
> 回滚点：用户签收 S02 后先建 tag **`s02-accepted`**（指向 `6c04e9e`），再执行本阶段；运行前数据库备份 `11_BACKUPS/s03_pre_run_20261117/fishery.db`（SHA-256 `A7FD22FF…069141`，与运行前库逐字节一致）。
> **状态：S03 完成待验收。所有正式统计均来自 S02 唯一硬掩码 `build_mask(allow_blocked=False)`；无全量程统计、无图上裁剪。**

---

## 0. 交付物一览

| 类型 | 位置 |
| --- | --- |
| 数据库迁移 | `04_SOURCE_CODE/app/migrations/0005_daily_statistics.sql`（`daily_statistics`、`s03_artifacts`、`v_latest_daily_statistics`） |
| 统计引擎 | `app/services/daily_stats.py`（指标定义、流式聚合、0/NA、分位数、候选事件、单台 BLOCKED） |
| 增量上传 | `app/services/incremental.py`（批次/run_id/快照、重复/冲突/迟到/补传、冻结保护、缺测登记、分析索引） |
| 日报与图表 | `app/services/reporting.py`（日报 MD、指标 CSV、6 类基础图，配色取自 `FIGURE_COLOR_SPEC_V1`） |
| Web 入口 | `app/web/routes.py` 新增 `/daily`、`/daily/upload`、`/daily/<设备>/<日期>`、`.../missing`；3 个新模板 |
| 独立入口 | `scripts/s03_daily_pipeline.py`（upload / missing / report / index） |
| 独立复算 | `12_DOCUMENTATION/verify_s03_stats.py`（纯标准库，不复用被测掩码/统计实现） |
| 真实产物 | `06_ANALYSIS_RESULTS/s03/`、`07_FIGURES/s03/`、`10_TEST_REPORTS/s03_verification/`、`06_ANALYSIS_RESULTS/s03/analysis_index.json` |
| 测试 | 新增 `test_s03_daily_stats.py`、`test_s03_incremental.py`、`test_s03_charts.py`；全库 **158 passed**（S02 基线 136 + 新增 22） |

---

## 1. 前置门槛核对

| 前置 | 核对结果 |
| --- | --- |
| S01 每设备人工截断配置 | 正式库 2000=5.2 m、2001=5.2 m，参数版本 v1，绑定 `analysis_runs.params_snapshot_json` |
| S02 距离映射核实 | 两台 v2 `CONFIRMED`：INTERVAL / 首格 0.5 m / 格宽 0.0375 m / 末格终点 38.0 m；v1 只读保留 |
| 统一硬掩码 | `build_mask()` 为唯一样本入口；正式分析 `allow_blocked=False`；5.2 m 无浮点容差、跨界区间整段排除、两层盲区 NEAR_FIELD |
| 原始文件只读 | 21 个 CSV 复验 SHA-256 **21/21 与归档清单一致**；本阶段未写入原始资料 |

---

## 2. 任务一：每日统计（指标、分子、分母、单位）

`10_TEST_REPORTS/s03_verification/metric_definitions.csv` 逐指标给出分子/分母/单位/NA 规则；日报与指标 CSV 同步输出同一份定义。关键口径：

| 指标 | 分子 | 分母 | 单位 | 2000 / 2026-10-31 | 2001 / 2026-10-31 |
| --- | --- | --- | --- | --- | --- |
| raw_records | 文件数据行数 | — | 条 | 192,235 | 189,834 |
| valid_records | 时间戳可解析且掩码后 ≥1 区内样本的行 | — | 条 | 192,235 | 189,834 |
| kept_samples | Σ `build_mask.kept_count` | — | 点 | 20,805,591 | 20,720,840 |
| excluded_samples | Σ `build_mask.excluded_total` | — | 点 | 171,429,409 | 169,113,160 |
| near_field_excluded_samples | 掩码原因 `NEAR_FIELD` | — | 点 | 3,223,784 | 3,008,410 |
| bottom_excluded_samples | 掩码原因 `BOTTOM_INTERFERENCE` | — | 点 | 0（S07 预留，不冒充实测） | 0 |
| valid_observation_duration_s | 去重时间戳格数 × 分辨率（1 s / 60 s） | — | s | 79,787 | 85,620 |
| planned_window_s | 日历日窗口 | — | s | 86,400 | 86,400 |
| coverage_ratio | valid_observation_duration_s | planned_window_s | 0—1 | 0.923461 | 0.990972 |
| candidate_events | 区内相邻有效槽位连续 ≥3 且值 ≥200 的极大段 | — | 次 | 13,093 | 68,784 |
| candidate_event_rate_per_hour | candidate_events | 有效时长/3600 | 次/h | 590.758 | 2,892.109 |
| signal_mean / median | Σ kept_values / 经验 0.5 分位数 | kept_samples | 强度 0—255 | 1.8552 / 0 | 7.3817 / 0 |
| water_temp_mean | 有效记录水温之和 | 有水温记录数 | °C | 22.1101 | 22.1016 |
| missing_interval_count | 有效时间戳格之间缺口数（含首尾） | — | 处 | 1,406 | 7 |

说明：

- 2001 时间戳只到分钟（分辨率 60 s），时长按 1,427 个去重分钟 × 60 = 85,620 s；**不伪造秒级对齐**。
- 候选事件为阈值算法 `CANDIDATE_RUN_V1`，仅表示“候选回波段”，**不等于鱼数量/物种结论**；阈值与最小长度写入 run 快照。
- 分位数使用标准 type-7 线性插值；真实数据为 0—255 整数，计数表给出**精确**分位数（非直方图估算）。
- 日内活动、缺测缺口、排除原因分布写入 `hourly_activity_json` / `missing_intervals_json` / `excluded_by_reason_json`。

---

## 3. 任务二、三：逐日增量上传与缺测状态

### 3.1 真实数据 8 步验证（设备 2000）

| 步骤 | 规范动作 | 实测结果 |
| --- | --- | --- |
| 1 | 只上传第 1 天（2026-11-01） | `NEW`，`RUN-2000-20261101-…e91986`，status `UPLOADED_LATE`，日报与 6 图生成 |
| 2 | 生成第 1 天报告 | `06_ANALYSIS_RESULTS/s03/daily/2000/2026-11-01/daily_report.md` 存在，含分子/分母/单位 |
| 3 | 跳过第 2 天 | 未上传 2026-11-02 |
| 4 | 上传第 3 天（2026-11-03） | `NEW`，`RUN-2000-20261103-…802e30`，系统正常 |
| 5 | 继续分析 | 11-03 统计正常：193,491 条、20,773,973 区内样本 |
| 6 | 第 2 天显示 MISSING | `daily_statistics` 出现 `2026-11-02 / MISSING` 行，**所有指标 NA**（非 0） |
| 7 | 补传第 2 天 | `REPROCESSED`，`RUN-2000-20261102-…cb7d60`，37 行结构异常按 `invalid_records` 登记 |
| 8 | 受影响结果正确更新 | 第 2 天新统计行 stat_id=8（原 MISSING 行保留）；第 3 天 stat_id/run_id 不变；21 个原始 CSV 哈希 21/21 不变 |

证据：`10_TEST_REPORTS/s03_verification/real_step1_day1.txt`、`real_step3_day3.txt`、`real_step7_backfill_PASS.txt`。

### 3.2 重复 / 冲突 / 迟到 / 补传 / 冻结

- 重复上传同内容同日 → `DUPLICATE`，直接返回原 run，不产生新统计；
- 强制重传 → `REPROCESSED`，旧 run 仅改 `SUPERSEDED`，历史统计行不删除；
- 同日不同 SHA-256 → `UploadConflict`（409，网页显示“需人工审查”），`force=True` 后旧登记标 `CONFLICT` 并留痕；
- `upload_date > observed_date` → `UPLOADED_LATE`；
- 数据集 `status='FROZEN'` 且覆盖该设备/日期 → `FrozenDatasetBlocked`（HTTP 423），不写入；
- 状态枚举齐全：`COMPLETE / PARTIAL / MISSING / QC_FAILED / UPLOADED_LATE / REPROCESSED / UNKNOWN / BLOCKED`；优先级：缺测/质检/阻断 > 上传属性 > 完整度。

### 3.3 单台 BLOCKED 不牵连其他设备

未配置截断/映射的设备（2002/2003/2005）上传后写 `BLOCKED` 行，所有样本指标为 NA，且**不读取原始文件**；同日 2000 正常产出统计。测试 `test_blocked_device_does_not_affect_others` 覆盖。

---

## 4. 任务四：日报流程与 run_id

每次上传后顺序执行：解析 → QC → 更新当日统计 → 更新覆盖率 → 更新有效观测时长 → 更新项目分析索引 → 保存 `run_id`。

- `analysis_runs.params_snapshot_json` 绑定：parameter_id/version、截断 5.2、mapping version、采样语义、候选算法版本、文件 SHA-256、批次、上传日期、操作者、阈值、时间窗口；
- 每次重算生成新 `run_id`，旧 run 标 `SUPERSEDED` 且历史统计行保留（真实库现有 7 个 run）；
- `06_ANALYSIS_RESULTS/s03/analysis_index.json` 记录每个设备-日的最新 run/状态/覆盖率/报告路径，以及 blocked/missing 清单。

---

## 5. 任务五：基础图表（6 类）

`07_FIGURES/s03/<设备>/<日期>/` 下每张图均为 PNG，配色取自 `05_CONFIG/figure_palette.json` 的 `A_SCIENTIFIC_PRIMARY`（实测 `colors[3]=#0271AC`）：

1. `daily_activity.png` — 24 时辰有效记录柱 + 候选事件折线；
2. `signal_distribution.png` — 区内信号强度分布（对数纵轴）；
3. `coverage.png` — 覆盖率与 0.95 COMPLETE 阈值线；
4. `missing_status.png` — 全部设备-日状态分布；
5. `bottom_exclusion.png` — 按掩码原因的排除样本（含近场/跨界/越界/底界）；
6. `daily_stats_table.png` — 每日统计表。

缺测/BLOCKED 日绘图只显示 NA 提示，不生成虚构 0 值曲线（测试 `test_missing_day_chart_does_not_fabricate_values` 覆盖）。

---

## 6. 任务六：0/NA 与数值复算

### 6.1 零值与 NA 分离

| 场景 | candidate_events | 其余样本指标 | 记录计数 |
| --- | --- | --- | --- |
| 区内有效、未检出候选 | **0**（真实零） | 正常计算 | 真实计数 |
| 区内完全无有效观测 | **NA** | 全部 NA（含 coverage_ratio） | raw_records 保留真实值 |
| 未上传/缺测日 | NA | 全部 NA | 全部 NA（不写 0） |
| 截断/映射未核实 | NA | 全部 NA，写 BLOCKED 行 | 不扫描文件 |

### 6.2 独立数值复算

`12_DOCUMENTATION/verify_s03_stats.py` 不 import 被测掩码/统计实现，纯标准库按映射 v2 重算两台真实文件前 2,000 行：

| 指标 | 2000 独立 / 服务 | 2001 独立 / 服务 |
| --- | --- | --- |
| raw_records / valid_records | 2000 / 2000 | 2000 / 2000 |
| kept_samples | 219,662 / 219,662 | 221,118 / 221,118 |
| kept_sum | 105,405 / 105,405 | 2,546,448 / 2,546,448 |
| kept_mean | 0.479850862 / 0.479850862 | 11.516240198 / 11.516240198 |
| candidate_events | 34 / 34 | 1,249 / 1,249 |
| 排除原因（NEAR/跨界/越界） | 30,338 / 2,000 / 1,748,000 三项全等 | 28,882 / 2,000 / 1,748,000 三项全等 |

两次独立复算均 `RESULT: PASS`（`verify_2000.txt` / `verify_2001.txt`）。

### 6.3 越界幅度不变性

`test_out_of_range_amplitude_does_not_change_in_range_stats`：同区内样本、第 125 格之后由 0 改为 255，`kept_samples / signal_mean / signal_median / signal_stddev / candidate_events / coverage_ratio` 全部不变（S02 K04 契约在统计层延续）。

---

## 7. 测试

```
.\.venv\Scripts\python.exe -m pytest 04_SOURCE_CODE\tests -q
158 passed in 9.36s
```

S02 既有 136 项断言未改、未放宽；新增 22 项覆盖：指标定义字段、分位数与总体标准差、高基数退化、候选事件连续性、状态优先级、合成 CSV 统计、0/NA 分离、越界不变性、缺测/BLOCKED 行、单台阻断、8 步增量、重复/冲突/迟到/冻结/补传、run 快照绑定、网页路由、6 类图表与配色。

---

## 8. 本阶段发现与处置

| # | 发现 | 处置 |
| --- | --- | --- |
| D-01 | 首次真实统计行 `file_sha256` 为空（复用了未算哈希的 inspection） | 修复：`compute_daily_statistics` 显式接收 `file_sha256`；对两台原文件以 `--force` 重算生成新 run，旧 run 保留 `SUPERSEDED`，未覆盖历史结果 |
| D-02 | 2026-11-02 真实文件有 **37 行信号数组有效槽位为 0**（尾部空 token 不算样本），逐行 `build_mask` 抛阻断导致整天失败 | 修复：结构异常行计入 `invalid_records` 并写入 `qc_notes`，不中断当日统计；补传成功，37 行如实登记为异常（非 0 值填充） |
| D-03 | 11-02 补传前被后台进程中断一次 | 失败日志保留为 `real_step7_backfill_FAILED_before_fix.txt`，修复后重跑 PASS 日志单独归档 |
| R-01 | 候选事件为阈值算法 V1，阈值 200 / 连续 3 格为工程约定 | 已写入 run 快照与日报；物种判定、底界 QC 留 S07，不冒充科研结论 |
| R-02 | 2001 时间戳仅到分钟 | 按 60 s 分辨率计有效时长，不伪造秒级；与 S02 ISS-007 一致 |
| R-03 | 五站（2002/2003/2005）无真实数据 | 保持 BLOCKED/无产物，不用双站冒充五站结论 |

---

## 9. 文件改动

新增：`0005_daily_statistics.sql`、`services/daily_stats.py`、`services/incremental.py`、`services/reporting.py`、`web/templates/daily*.html`(3)、`scripts/s03_daily_pipeline.py`、`tests/s03_helpers.py`、`tests/test_s03_daily_stats.py`、`tests/test_s03_incremental.py`、`tests/test_s03_charts.py`、`12_DOCUMENTATION/verify_s03_stats.py`、`10_TEST_REPORTS/s03_verification/*`、`06_ANALYSIS_RESULTS/s03/*`、`07_FIGURES/s03/*`。

修改：`app/web/routes.py`（4 条路由）、`base.html`（导航）、`tests/conftest.py`（S03 fixtures）、`CHANGELOG.md`、`PROJECT_MASTER_INDEX.md`、`DEV_PLAN_S00_S11.md`、追踪矩阵（同步 S03 状态）。

未改动：21 个原始 CSV（哈希 21/21 PASS）、V4 规范包、S00—S02 既有代码与工件。

---

## 10. 下一阶段前置

S04（任意时间/天数/设备比较引擎）需以本阶段已验收的每日统计与缺测状态为输入；若本阶段验收退回，先修复 S03 再开 S04。**未经用户明确批准，不进入 S04。**

**结论：S03 六项任务与 V4 强制增项均有代码、真实数据、独立复算与测试证据；所有正式统计来自硬掩码源，缺测与阻断如实登记为 NA/BLOCKED，本轮停在 S03 等验收。**
