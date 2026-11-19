# S03—S11 再验收缺陷整改复验报告

> 依据：`10_TEST_REPORTS/stage_reports/ACCEPTANCE_S03_S11.md`（独立复核报告）
> 整改日期：2026-11-17｜范围：全部 D1 必改项与 P2 应改项；P3 建议项择要记录
> 状态：**D1 5/5 已整改并复验；P2 8/8 已整改并复验；全量 pytest 250 passed；原始 CSV 21/21 哈希不变。**

---

## 1. D1 必改项

| 编号 | 原缺陷 | 整改实现 | 复验证据 |
| --- | --- | --- | --- |
| D1-1 | `06_ANALYSIS_RESULTS/s03/analysis_index.json` 被 pytest 污染且已入库，只含 2027 虚构日期 | 从正式库重跑 `s03_daily_pipeline.py index` 重建真实 5 个设备-日索引；`/daily/upload` 与 `/daily/<...>/missing` 均显式传 `project_root`/`output_root`；更正 STAGE_S04 §8.6 失实表述 | `analysis_index.json` 现含 `2000/2026-10-31` 等真实键、无 `2027`；`test_s03_upload_route_passes_project_root`；全量测试后索引 SHA 不再变化 |
| D1-2 | STAGE_S05 多处失实：分箱、sin/cos、多站关联、潮位≠流速不可达 | 更正 STAGE_S05 §1/§3/§5 与限制项；分箱改为 `(-∞,10)/[10,22)/[22,23)/[23,24)/[24,∞)`；新增圆周量统计、sin/cos 联合列、多站关联、潮位机制，并把“潮位不是流速”写入所有报告产物 | `test_s05_explicit_derived_quality_and_circular_statistics`、`test_s05_tide_wind_and_multi_station_mechanisms`；STAGE_S05 已按实际实现重写相关段落 |
| D1-3 | S05 潮汐/风向/多站/风速变化前后代码缺失 | `environment_analysis.py` 新增 `tide_analysis()`、`wind_change_analysis()`、`multi_station_association()`；`joint_analysis()` 将 `WIND_DIRECTION` 拆为 sin/cos 两列纳入；无真实数据的分支保持 BLOCKED/INSUFFICIENT，不用合成数据冒充真实结论 | `test_s05_tide_wind_and_multi_station_mechanisms`；`/environment/analysis` 网页新增四类结果展示；真实库分析结果归档到 `06_ANALYSIS_RESULTS/s05/` |
| D1-4 | S05 自动获取框架四项能力零实现 | 新增 `0012_s05_automation.sql` 四表；`environment_fetch.py` 实现 `register_adapter`、`configure_schedule`、`fetch_with_retry`、`run_due_schedules`、`backfill_history`、`cached_fetch`，CLI 暴露对应子命令；适配器默认 BLOCKED，无授权不联网 | `test_s05_auto_fetch_framework_success_cache_retry_and_backfill` 覆盖成功/缓存命中/定时/重试失败/历史补取；真实库仍无 ENABLED 适配器 |
| D1-5 | S07 底足迹面积 2.5252 m² 超过未截断椭圆 2.1411 m² 上界 | `_footprint_area()` 改为圆盘∩椭圆按 x 切片解析积分，45° 条件算例得 **0.854510 m²**；以 `BEAM_GEOM_V2_FOOTPRINT_INTERSECTION` 新增 QC 行和 `geometry_2000_footprint_fix_v2.txt`，旧记录保持原样 | `test_s07_footprint_area_and_new_version_evidence`；体积 2.353045 m³、5.2 m 硬截断未改；STAGE_S07 D-05 |

## 2. P2 应改项

| 编号 | 原缺陷 | 整改实现 | 复验证据 |
| --- | --- | --- | --- |
| P2-1 | 跨午夜次日只有 MISSING 行时未标 partial | `comparison._make_window()` 把次日 MISSING/BLOCKED/QC_FAILED/UNKNOWN 视为不可用，标 `partial=true` 并把具体状态写入 notes | `test_s03_cross_midnight_missing_next_day_is_partial` |
| P2-2 | Web `/daily/upload` 未传 `project_root`，同源漏修 | 路由显式传 `project_root` 与 `output_root`，与缺测登记路由一致 | `test_s03_upload_route_passes_project_root` |
| P2-3 | 夜段半截仍 `coverage_ok=true` | 计算夜/日期望秒数与覆盖率；二者均 ≥90% 且各 ≥900 s 才可比较，否则 `NOT_COMPARABLE_PARTIAL_NIGHT` + `coverage_ok=false` | `test_s06_partial_night_not_comparable_and_blocked_reason`；STAGE_S06 D-04 |
| P2-4 | BLOCKED 原因误写为缺经纬度 | `day_night()` 区分“当日无统计行/格”“次日无统计行/格”“缺经纬度/时区”三类原因 | 同上；STAGE_S06 D-05 |
| P2-5 | `environment_match` 死表、DERIVED 落库为 OK、结果未归档 | `persist_matches()` 每次 `run()` 写入下钻行；`_quality()` 尊重显式 `quality_flag`；修正脚本把现有 4 条水温代理改为 `DERIVED`；Web/CLI 分析自动写 `06_ANALYSIS_RESULTS/s05/<analysis_id>.json` | `test_s05_persist_matches_writes_drilldown_rows`、`test_s05_explicit_derived_quality_and_circular_statistics`；真实库 `WATER_TEMP=DERIVED 4` |
| P2-6 | 方向性足迹未实现 | `spatial.directional_footprint()` 在 heading 与参数齐备时输出 `CONDITIONAL_SECTOR`（heading=0° 朝北、顺时针，内部半角与前向投影上限，附本地多边形）；缺 heading 保持 UNKNOWN | `test_s08_directional_footprint_when_heading_present`；STAGE_S08 D-06 |
| P2-7 | 文件级冻结清单缺失 | `s11_acceptance.build_file_freeze_manifest()` 复制正式库/索引/正式图/动画/Origin 导出/S08 统计表/S10 导出/论文六文件/阶段报告到 `13_FROZEN_VERSIONS/PRE_DEFENSE/`，逐文件写源与副本 SHA-256 到 CSV/JSON；验收章节新增检查 | `test_s11_file_level_freeze_manifest`；`FROZEN_FILE_MANIFEST.json` 显示 `all_match=true` |
| P2-8 | 图注/指标为“见报告/源表”指针 | 为 16 类图补齐自包含 `CAPTIONS`、`METRICS`、`UNITS` 并重建 `figure_registry` | `test_s09_every_figure_has_self_contained_definition`；STAGE_S09 D-08 |

## 3. P3 建议项处理

- 保留未做的建议项，不借整改名义扩大范围：S05/S06 `SolarDay.segment()` 死代码、固定时区偏移、作废 run 标记、S07 规律上传钩子、2001 覆盖原因展示优化等仍按原限制保留。
- `09_PAPER_OUTPUT/` 与实际交付目录 `12_DOCUMENTATION/PAPER_EVIDENCE/` 不一致：本轮不改目录结构，在 `13_FROZEN_VERSIONS/PRE_DEFENSE/` 中同时冻结实际交付文件，避免路径歧义。

## 4. 全量复验

```text
.venv\Scripts\python.exe -m pytest 04_SOURCE_CODE\tests -q
250 passed in 31.94s
```

- D1/P2 新增 12 项专项测试：`tests/test_acceptance_remediation.py`，12 passed。
- 21 个原始 CSV 哈希 **21/21 与 `RAW_CSV_ARCHIVE_MANIFEST.csv` 一致**。
- `s11_final.py` 重跑：13/13 章节 PASS，离线核心 PASS，隔离恢复 PASS，`PRE_DEFENSE` FROZEN。
- 正式 SVG 配色扫描：色板外 0 种，PASS。

## 5. 仍然真实阻断的项目（未被整改“洗白”）

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 五站正式同步数据 | BLOCKED | 五台成员已登记，但正式同步时间 NULL；第四章不冒充五站结论 |
| 2002/2003/2005 GPS、朝向、参数 | UNKNOWN | 不复制 2000/2001 数值 |
| 2000/2001 坐标系与朝向 | UNKNOWN | 站距仍 PROVISIONAL；条件方向足迹只在用户录入 heading 后生成 |
| 水温独立观测、潮汐逐时值、风向列 | BLOCKED | 机制已实现但无真实数据；不生成真实结论 |
| Origin 试用版水印 / `originpro` 包 | BLOCKED | COM 闭环有效，正式图仍由 MATPLOTLIB 同源导出 |
| 破坏性覆盖恢复与整机断网 | UNVERIFIED | 隔离路径恢复与 socket 禁用测试 PASS；未覆盖生产库、未做整机断网 |

**结论：ACCEPTANCE_S03_S11.md 列出的全部 D1/P2 缺陷均已完成代码整改、真实现状修正与专项测试复验；未把数据缺失伪装成功能通过。**
