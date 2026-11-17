# STAGE_S04 — 任意时间、任意天数与任意设备比较

> 阶段：S04（L3）｜依据：`FISHERY_FULL_PLAN_V4/03_CODEX_STAGE_TASKS_FINAL.md` 第七章、`09_DEVELOPER_ACCEPTANCE.md` K26/K27
> 执行日期：2026-11-17｜环境：Windows 11 / 项目 `.venv` Python 3.10.11 / pytest 9.2.0
> 回滚点：S03 验收后提交 `1dfa91a` 并建 tag **`s03-accepted`**；S04 运行前备份正式库 `11_BACKUPS/s04_pre_run_20261117/fishery.db`（SHA-256 `C0CCA95C…F35CF`）。
> **状态：S04 完成待验收。所有比较输入只来自 S03 `v_latest_daily_statistics`，不重算原始 CSV、不把缺测填 0。**

---

## 0. 交付物

| 类型 | 位置 |
| --- | --- |
| 迁移 | `04_SOURCE_CODE/app/migrations/0006_comparison.sql`（`comparison_runs`，查询口径与结果同库留痕） |
| 比较引擎 | `app/services/comparison.py`（筛选、跨午夜归属、时区对账、日期/设备比较矩阵、历史基线、自动总结） |
| Web | `app/web/routes.py` 新增 `/compare`、`/compare/run`；模板 `compare.html`、`compare_result.html` |
| CLI | `scripts/s04_compare.py`（`--dates/--hour-start/--day-count/--baseline-mode` 等） |
| 测试 | `tests/s04_helpers.py`、`test_s04_filters.py`、`test_s04_comparison.py`、`test_s04_web.py`；全库 **184 passed**（S03 158 + 新增 26） |
| 真实产物 | `06_ANALYSIS_RESULTS/s04/<comparison_id>/`（结果 JSON、指标 CSV、总结 MD）；`10_TEST_REPORTS/s04_verification/` |

---

## 1. 任务一：任意时间（K26）

- **日期**：`start_date`/`end_date` 区间（**两端包含**）、显式 `dates` 集合（非连续日期）、二者可单独使用；空集返回明确原因（`ComparisonEmptyError`），不返回 500、不伪造 0。
- **小时**：`[hour_start, hour_end)` 左闭右开；`hour_end < hour_start` 表示跨午夜，窗口归属**起始日期**，消耗当日 `[start,24)` + 次日 `[0,end)`。每个日历小时在一次选择中只归属一个窗口实例；次日缺行时只计入可得小时并标 `partial=true`。
- **时区**：原始 CSV 时间戳未附时区元数据；S04 按声明口径（`Asia/Shanghai` 默认，支持 `UTC`/`±HH:MM`）给出本地与 UTC 半开区间，未知时区直接拒绝，不静默猜测。
  - 真实例：`2026-11-01 22:00 +08:00` → 本地窗口 `[2026-11-01T22:00, 2026-11-02T02:00)` → UTC `[2026-11-01T14:00Z, 2026-11-01T18:00Z)`。
  - 全天窗口也有对账：`2026-10-31` 本地 `[00:00,24:00)` → UTC `[2026-10-30T16:00Z, 2026-10-31T16:00Z)`。
- **日内窗口的诚实口径**：有效时长与覆盖率由小时有效记录占比估算，标 `estimated=true`；子窗口没有小时级直方图与水温，信号分布/水温为 NA；全天窗口使用 S03 精确值。

真实验证：`real_hour_window.txt`（06:00—18:00，`hour_range`）、`real_cross_midnight.txt`（22:00—02:00，`cross_midnight`，两日窗口 401.8711 vs 338.3250 次/有效小时，+18.78%）。

## 2. 任务二：任意天数

- `day_count` 支持 1/2/3/7/14/18/19/30/60/90 及任意自定义天数。
- `calendar` 模式：以锚点日向前推 N 个**日历日**；缺测日出现在队列里但被排除，并给出 `INVALID_OBSERVATION_DAY` 原因与 `shortfall`。
- `valid` 模式：取锚点之前最近的 N 个**有效观测日**，缺测/QC_FAILED/BLOCKED/UNKNOWN 日不进入。
- 真实库 2000 现有 4 个有效观测日（10-31、11-01、11-02、11-03），`day_count=3, mode=valid` 正确取 11-01—11-03。

## 3. 任务三：任意设备与站位

- 单设备、任意双/三/四设备、五设备整体、任意子集：`devices` 多选；未选=全部五台（无 2004）。
- 站位：`stations` 多选，按 `devices.station_id` 交集筛选；未知站位/设备直接 400，**不伪造站位**。当前 `stations` 表为空，真实库不选站位，网页明确提示“未提供站位资料”。
- 同日设备对照：`device_comparison_matrix()` 以参考设备为基准逐日比较；缺任一方记 `MISSING_PAIR`，不补 0。
  - 真实例（2001 vs 2000，2026-10-31）：候选事件率 2,892.1093 vs 590.7579 次/有效小时，差值 +2,301.3514，+389.56%。两台时间戳分辨率不同（1 s vs 60 s），数值以各自 S03 有效观测时长为分母规范化后比较，未伪造秒级对齐。

## 4. 任务四：日期比较矩阵（V4 指定 8 组）

| 用例 | 2000 实测（比较日 / 参考） | 候选事件率比较 / 变化 |
| --- | --- | --- |
| D1 vs D2 | 11-01 / 11-02 | 590.7579 / 508.3947，+82.3632，+16.20% |
| D4 vs D1 | 11-03 / 10-31 | 713.6117 / 590.7579，+122.8538，+20.80% |
| D4 vs D2 | 11-03 / 11-02 | 713.6117 / 508.3947，+205.2170，+40.37% |
| D4 vs D3 | 11-03 / 11-01 | 713.6117 / 498.1628，+215.4489，+43.25% |
| D4 vs 前3天平均 | 11-03 / 10-31、11-01、11-02 | 713.6117 / 532.4385，+181.1732，+34.03% |
| D5 vs D3 / D5 vs 前4天平均 / D7 vs 前6天平均 | 真实库仅 4 个有效日 | `INSUFFICIENT_DATES`，明确“不伪造第 5/7 日” |

合成 7 日序列（事件数 2/4/6/8/10/12/14）在 `test_matrix_eight_cases_with_seven_synthetic_days` 中逐组对账，`D4_vs_prev3_mean`、`D7_vs_prev6_mean` 的参考值等于前 N 日算术平均。**没有用模拟数据冒充真实观测日。**

## 5. 任务五：历史基线（K27）

- 模式：`valid`（前 N 个有效观测日）、`calendar`（前 N 个日历日）、`all`（全部历史）、`range`（任意区间），并支持 `rolling_baselines()` 逐参考日滚动。
- 分母表：合并事件率 = `Σ候选事件 ÷ (Σ有效观测时长/3600)`；日均事件率 = 各有效日率的算术平均；`n_members` 只数有效日，`shortfall` 明示缺额。
- 真实：`CMP-4AA00A342509`，参考日 2026-11-03、前 3 有效日基线成员 10-31/11-01/11-02，`n=3`、`shortfall=0`、合并事件率 530.9403 次/有效小时。
- 参考值为 0 时变化百分比记 **NA** 并写“参考值为 0，百分比变化为 NA（K27）”（`test_reference_zero_gives_na_percent_with_explanation`）。

## 6. 任务六、七：比较指标与自动总结

输出每项指标均含：**参考值、比较值、差值、变化百分比、有效样本量、覆盖率、结论（HIGHER/LOWER/EQUAL/NA）**。指标覆盖活动记录数、候选事件数、区内样本量、候选事件率、覆盖率、有效时长、信号均值/中位数/P95、活动峰值小时与峰值、昼—夜差、水温均值；任意日期比较额外给出 24 小时逐时数组。

自动总结（`comparison_summary.md`）输出最高/最低日、最大绝对幅度、设备均值差、基线差异、缺测说明与不确定性说明。明确写入：**“变化不等同于真实鱼类数量变化，可能由观测覆盖、海况、设备差异、昼夜与算法阈值造成”**；水层指标因 S07 门禁未通过而不输出。

## 7. 任务八：测试与证据

```
.\.venv\Scripts\python.exe -m pytest 04_SOURCE_CODE\tests -q
184 passed in 9.67s
```

覆盖：日期区间端点、非连续日期、日历日/有效日天数、小时边界、跨午夜小时归属与缺口、日内估算标记、站位与未知设备拒绝、空集原因、时区上下界与未知时区拒绝、差值方向、零参考 NA、8 组合成矩阵、样本不足不伪造、基线排除缺测/缺额、全历史/区间/滚动基线、直方图计数统计、设备对照与缺对、缺测 NA、Web 3 条路径。

真实 CLI 证据：`real_matrix_2000.txt`、`real_dual_device.txt`、`real_hour_window.txt`、`real_cross_midnight.txt`、`real_baseline_valid3.txt`、`pytest.txt`。原始 21 个 CSV 哈希复验 21/21 与归档清单一致；本阶段只读 S03 统计表。

## 8. 已知限制（不伪造）

1. `stations` 表为空，站位筛选只有机制与测试，无真实站位结果；不得据此给出五站结论。
2. 真实库 2000 只有 4 个有效观测日、2001 只有 1 个，V4 指定的第 5/7 日比较在真实数据上标 `INSUFFICIENT_DATES`；公式由合成 7 日序列验证。
3. 日内子窗口的时长/覆盖率为估算；S03 未存小时级去重时间戳，不能冒充精确值。
4. 时钟“昼夜”按可配置 06:00—18:00 约定，非天文日出日落；S06 引入晨昏后须重新对账。
5. 水层指标须通过 S07 底界 QC 门禁后才纳入，本阶段为 BLOCKED/不输出。
6. **S03 遗留测试污染已修**：`/daily/<设备>/<日期>/missing` 原调用缺测登记时未传 `project_root`，pytest 会重写真实 `06_ANALYSIS_RESULTS/s03/analysis_index.json`。S04 中给 `create_app` 增加 `config["PROJECT_ROOT"]`，网页路由显式传入，测试夹具指向 `tmp_path`；被污染的真实索引已恢复为 HEAD 内容，复跑 184 项后 `git status` 无该文件改动。

**结论：S04 八项任务均有代码、真实数据、测试与留痕证据；停在 S04 等验收，未开始 S05。**
