# STAGE_S05 — 环境数据接入和联合分析

> 阶段：S05（L4）｜依据：`FISHERY_FULL_PLAN_V4/03_CODEX_STAGE_TASKS_FINAL.md` 第八章、`09_DEVELOPER_ACCEPTANCE.md` K30/K31
> 执行日期：2026-11-17｜环境：Windows 11 / 项目 `.venv` Python 3.10.11 / pytest 9.2.0 / openpyxl / numpy
> 回滚点：S04 验收后提交 `1658a38` 并建 tag **`s04-accepted`**；运行前备份正式库 `11_BACKUPS/s05_pre_run_20261117/fishery.db`（SHA-256 `7EC830F0…91F1E8CF`）。
> **状态：S05 完成待验收。潮汐仅 PNG 截图、无数值表；风向列不存在；自动数据源未获确认——三项均如实 BLOCKED，未估读图片、未伪造风向、未联网抓取。**

---

## 0. 交付物

| 类型 | 位置 |
| --- | --- |
| 迁移 | `app/migrations/0007_environment.sql`：`environment_source`、`environment_import_batch`、`environment_observation`、`environment_fetch_log`、`environment_match` |
| 导入 | `app/services/environment_import.py`：字段识别/映射、时间时区、单位换算、预览、重复/冲突/缺测/异常检查、来源登记、批次与原文件归档 |
| 分析 | `app/services/environment_analysis.py`：时间配对、候选时滞、Fisher z CI、有效样本、Holm 校正、多因素联合与诊断 |
| 自动获取 | `app/services/environment_fetch.py`：数据源评估、可插拔适配器契约、失败/阻断日志 |
| Web | `/environment`、`/environment/import`、`/environment/fetch-attempt`、`/environment/analysis` + 2 个模板 |
| CLI | `scripts/s05_environment.py`（register-source / preview / import / fetch-evaluate / fetch-attempt / analyze）、`scripts/s05_water_temp_proxy.py` |
| 测试 | `tests/s05_helpers.py`、`test_s05_import.py`、`test_s05_analysis.py`；全库 **196 passed**（S04 184 + 新增 12） |
| 证据 | `10_TEST_REPORTS/s05_verification/`；归档原件 `02_IMPORTED_DATA/ENVIRONMENT_ARCHIVE/<batch>/` |

---

## 1. 任务一、二：手动导入与环境数据库

- 支持 CSV（自动探测 BOM/UTF-8/GB18030、分隔符）与 XLSX（`openpyxl` 只读）；表头自动识别并支持显式 `header_row` / `sheet`。
- 字段映射可自动建议或手工指定；时间支持日期+时间列拆分、Excel 日期/时间序列、常见字符串格式；时区按声明口径（默认 `Asia/Shanghai`）同时保存本地 ISO 与 UTC ISO。
- 单位换算登记为白名单：风速 m/s、km/h、mph、knot；潮位 m/cm/mm；温度 °C；风向度。未登记单位直接拒绝（如 `m/h`），不静默猜测。
- 预览不写库；`commit_import` 单事务：批次行先落、观测后落、最后回写计数；原文件按批次归档并记 SHA-256、大小、字段映射、时区、逐行问题。
- 质量标记：`OK / MODEL_HISTORICAL / FORECAST / DERIVED / SUSPECT`。**预报只登记不参与分析**；重复键不覆盖；同键不同值记来源冲突并保留原值。
- 五张表全部建立；`environment_match` 记录声学时刻、观测 obs_id、时滞、时间差、容差与方法，供结果下钻。

**真实导入**：`ENV-WIND-OPENMETEO`（Open-Meteo 逐小时风速 XLSX，网格 27.87346°N/121.11486°E，10 m 高度）288 行全部接受，其中 **168 行 `MODEL_HISTORICAL`、120 行 `FORECAST`（已排除）**；批次 `ENV-B373122FA489`，归档 SHA 与原文件一致。

## 2. 任务三：水温分析

- 独立水温文件目录为空。为不丢失真实水温信息，从同一批声学 CSV 的 `water_temp_mean` 按日跨设备平均派生 4 行代理（`10_TEST_REPORTS/s05_verification/water_temp_proxy.csv`），来源登记 `kind=DERIVED`、质量标记 `DERIVED`，导入批次 `ENV-D8F7C909B208`。
- 报告与网页明确写入：**“同源派生代理，不是独立环境观测；仅作同源描述，不能作为独立环境证据”**。
- 真实 4 个日均水温点只能与小时声学配出 5 对，所有时滞结果标 `UNCERTAIN` 或 `INSUFFICIENT_PAIRS`，未据此下任何水温结论。
- 10—22/22—23/23—24/>24 °C 分箱、不同站位温度关联的机制与测试已实现；无独立多站温度数据时不出结论。

## 3. 任务四、五：潮汐与风速

- 潮汐：`01_ORIGINAL_DATA/ENVIRONMENT/TIDE/潮汐.zip` 只有 11 张 PNG 曲线截图，无数值表、无潮位基准面。按 S00/S02 既有裁定**不做图像估读**，潮汐高度、涨落潮、高低潮附近变化、潮位变化速度全部 `BLOCKED`，并记录“潮位不等于流速”。
- 风速：真实风速文件没有风向列，风向分析 `BLOCKED`（圆周量处理与 sin/cos 接口已写好，但没有数据不生成方向结论）。风速分级、前后变化与滞后分析基于 168 条模型历史小时值。
- 真实结果（`ENV-B3E5F0384B42`，设备 2000/2001，2026-10-31—11-03，120 个有效声学小时）：
  - 候选时滞 0/1/2/3/6/12/24 h **全部 7 组均输出**，每组 120 对、有效样本 22—23（已按 lag-1 自相关折减）；
  - r 介于 −0.177 ~ −0.096，Fisher z 95% CI 均跨 0，Holm 校正后 p=1.0；**结论：现有资料无风速—声学关联的证据，不是“无关联证明”**；
  - 联合模型仅用独立来源的风速：标准化 β=−0.096，R²=0.0092，n=120；水温代理被显式排除。

## 4. 任务六、七：联合与滞后分析（K31）

- 分析计划先登记：时滞方向为“环境在前、声学在后”，预设搜索范围 0/1/2/3/6/12/24 h，配对容差默认 1800 s（可配置），不挑显著结果。
- 每条结果给出 n_pairs、有效样本、lag-1 自相关、Fisher z 95% CI、p 与 Holm p；缺样本、零方差、完全共线分别给 `INSUFFICIENT_PAIRS` / `NO_VARIANCE` / 退化 CI 诊断。
- 多重比较对所有已输出时滞做 Holm 校正；报告明确“关联不等同于因果；可能由覆盖、海况、设备差异、昼夜与阈值造成”。
- 多因素最小二乘使用标准化变量，给 β、R²、共同样本数、秩与共线/小样本诊断；独立来源不足时 `BLOCKED`，派生代理不进入解释变量。

## 5. 任务八：自动获取

- 评估三个候选适配器（Open-Meteo Marine、NOAA CO-OPS、本地 CSV 轮询），逐项登记空间覆盖、时间分辨率、单位、实测/预报属性、许可/授权、API 限制及未核实原因，全部 `BLOCKED`；`enabled_adapters=[]`。
- 可插拔接口契约已给出（`validate` / `fetch` / `to_observation`），未实现网络请求；`fetch-attempt` 只写 `environment_fetch_log`。真实例 `FETCH-FE91F63EA6` 状态 `BLOCKED`，原因含“当前风速文件已来自 Open-Meteo 模型，不能重复当独立实测”。
- 自动数据即使将来启用，也因 `(source_id, variable, location_key, observed_at_utc)` 唯一键与来源隔离，**不能覆盖手动导入数据**。

## 6. 任务九：测试与证据

```
.\.venv\Scripts\python.exe -m pytest 04_SOURCE_CODE\tests -q
196 passed in 10.42s
```

覆盖：CSV/XLSX 导入、表头自动识别、GB18030、时区 UTC 对账、单位换算与未知单位拒绝、缺测/异常/负风速/风向越界、文件内重复、同键冲突不覆盖、来源与批次归档、元数据“预报”关键词误标回归、自动获取评估与失败日志、7 组时滞全输出、有效样本/CI/Holm、共同样本不足、代理数据排除、潮汐/风向 BLOCKED、4 条 Web 路径。

证据文件：`register_wind.txt`、`import_wind.txt`、`water_temp_proxy.csv`、`register_water.txt`、`import_water.txt`、`analyze_real.txt`、`analysis_result.json`、`fetch_evaluation.txt`、`fetch_attempt.txt`、`pytest.txt`。

原始数据保护：21 个声学 CSV 哈希 **21/21 与归档清单一致**；测试归档已隔离到 `tmp_path`，真实归档目录只保留 2 个正式批次。

## 7. 本阶段发现与处置

| # | 发现 | 处置 |
| --- | --- | --- |
| D-01 | 首次导入把“未来数值会随预报更新”的**元数据**当成逐行预报标记，288 行全标 `FORECAST` | 改为只读逐行质量列判断预报/历史，元数据仅用于判“模型”；清空并重新导入，得到 168 历史 + 120 预报；加回归测试 |
| D-02 | 水温代理首版把两个设备同一天 12:00 写成同一位置键，产生 1 条重复 | 改为按日跨设备平均、单位置键；清空并重导 4 行；重复检查机制如实记录 |
| D-03 | 测试 `commit_import` 未传 `project_root`，会向真实归档目录写文件 | 所有 S05 测试显式传 `tmp_path`；清理测试批次归档，复跑后无新增 |

## 8. 已知限制（不伪造）

1. 潮汐无数值表、风向无列、独立水温文件缺失：三项 BLOCKED，不能用截图估读或同源代理冒充独立观测。
2. 风速来自数值气象模型，历史时段也不是现场实测；不能作为“实测风场”结论。
3. 真实有效日只有 5 个（2000 的四日 + 2001 的一日），联合模型样本量小，R² 极低；任何“无关联”都只表示现有数据不支持。
4. 自动获取未联网、未配置凭证，只有评估与阻断日志；不得写成已可用的自动数据通道。
5. 声学侧只使用 S03 硬掩码后的小时候选事件数，未重新读取原始回波；水层与底界 QC 属 S07，本阶段不输出。

**结论：S05 九项任务均已实现或按数据条件明确 BLOCKED；停在 S05 等验收，未开始 S06。**
