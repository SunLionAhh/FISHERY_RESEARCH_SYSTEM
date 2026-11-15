# PROJECT_MASTER_INDEX — 项目总索引

> 本文件是项目唯一状态入口。任何新会话必须先读取本文件和最新阶段报告。
> 状态如实记录：目录已建立不等于功能已实现，资料已归档不等于已审计。

## 基本信息

| 项 | 值 |
| --- | --- |
| 项目名称 | FISHERY_RESEARCH_SYSTEM |
| 规范版本 | **V4.0 — `FISHERY_FULL_PLAN_V4/` 整个包**（用户 19:13 确认「这是全部要求」、19:17 裁定「以 V4 为准」） |
| 历史基线 | `00_PROJECT_SPEC/` 三份 FINAL 1.5 同名 `.md` + `_source/` docx，**降级为只读对照，不作开发依据** |
| 规范优先级 | 08 用户要求（同主题最高）→ 11 几何 / 09 验收 → 01 主规范 > 02 执行指南 > 03 阶段任务 → 04 总规划（实施深化，不是新主规范）；叠加 `FIGURE_COLOR_SPEC_V1`、`SCOPE_DUAL_STATION_V1` |
| 正式设备 | **2000、2001、2002、2003、2005 共五台；没有 2004**（用户 19:17 强调不得混淆） |
| 当前阶段 | S00（**九项任务已实际执行，阶段报告已生成，待用户验收；验收通过前不开始 S01**） |
| 当前状态 | S00_DONE_PENDING_ACCEPTANCE |
| 预答辩目标 | 2027-01-20 |
| 更新时间 | 2026-11-14（S00 执行完成登记） |
| Git 初始回滚点 | 见本文件「运行标识」与 `CHANGELOG.md`（用户 19:17 明确需要安全回滚点） |

## 规范与文档

**现行要求全集（V4 包，原位完整保留，17 个文件 / 包内 SHA-256 清单 16/16 通过）**

- `FISHERY_FULL_PLAN_V4/01_MASTER_SPEC_FINAL.md` — 主规范 V4 修订全文（24 章）
- `FISHERY_FULL_PLAN_V4/02_CODEX_EXECUTION_GUIDE_FINAL.md` — 执行指南（13 章）
- `FISHERY_FULL_PLAN_V4/03_CODEX_STAGE_TASKS_FINAL.md` — 阶段任务（18 章、S00—S11、修订版 22 条启动话术）
- `FISHERY_FULL_PLAN_V4/04_FULL_PLAN_V4.html` / `.txt` — 总规划（36 交付 / 31 入口 / 18 报告 / 16 图 / 工期）
- `FISHERY_FULL_PLAN_V4/06_CODEX_START.txt` — 可直接发送的开发启动要求
- `FISHERY_FULL_PLAN_V4/08_USER_REQUIREMENTS_V4.md` — **同主题最高效力**：五设备、5.2 m 硬截断、字段权威名、接口与错误状态
- `FISHERY_FULL_PLAN_V4/09_DEVELOPER_ACCEPTANCE.md` — 45 条 K 验收、W1—W3、D0—D2、用户十步验收
- `FISHERY_FULL_PLAN_V4/11_GPS_BEAM_GEOMETRY.md` — 几何算法与 GEO-01—12
- `FISHERY_FULL_PLAN_V4/00_README.txt`、`05`、`07`、`10`、`12`、`13`、`MANIFEST_SHA256.json` — 包说明、规律说明、来源效力、参数示例（草稿）、示意图（条件算例）、修订记录、完整性清单

**S00 阶段交付（2026-11-14 实际执行）**

- `10_TEST_REPORTS/stage_reports/STAGE_S00.md` — **S00 阶段报告**（环境实测、21 CSV 全量复核、V4 包 16/16、备份、风险、S01 前置；待验收）
- `12_DOCUMENTATION/REQUIREMENTS_TRACEABILITY_MATRIX.md` — **需求追踪矩阵**（24 章 / 36 交付 / 31 入口 / 18 报告 / 16 图 / 45 条 K / GEO-01—12 逐项登记，随每阶段更新）
- `12_DOCUMENTATION/DEV_PLAN_S00_S11.md` — **S00—S11 开发计划**（阶段总表、关键路径、V4 硬契约落位检查表、R1—R10 风险）
- `10_TEST_REPORTS/s00_verification/` — V4 包与原始 CSV 完整性校验证据（V4 16/16 PASS、CSV 21/21 PASS）
- `11_BACKUPS/S00_baseline_backup_20261114/` — 可恢复资产备份（30 文件 + SHA-256 清单）
- `04_SOURCE_CODE/requirements-lock.txt`、`04_SOURCE_CODE/tests/test_s00_smoke.py` — 依赖锁定（36 项）与 S00 冒烟测试（29 用例 PASS）
- `12_DOCUMENTATION/s00_verify_integrity.py`、`s00_backup_assets.py` — 可复现校验/备份脚本

**整理与执行入口**

- `12_DOCUMENTATION/V4_REQUIREMENTS_INDEX.md` — **V4 要求全集索引**：17 文件导览、效力层级、**路径解析规则**、24 章/36 交付/31 入口/18 报告/16 图/45 验收清单、与项目现状对照
- `12_DOCUMENTATION/SPEC_VERSION_MATRIX.md` — **版本矩阵**：V4 vs FINAL 1.5 的 D1—D12 差异、四项用户裁定落地、仍待处置项
- `12_DOCUMENTATION/S00_START_PROMPT.md` — **首次发送给编码 Agent 的启动指令（V4 基准）**，修订版 22 条 + 路径解析规则 + 本项目实测事实
- `00_PROJECT_SPEC/README.md` — 历史基线只读声明与版本差异摘要
- `01_ORIGINAL_DATA/FISHFINDER/README.md` — V4 设备目录、只读保护、持续上传规则、双站口径
- `.gitignore` — 排除 8.38 GB 原始 CSV 与临时文件；仓库已初始化

**其他既有记录**

- `12_DOCUMENTATION/SCOPE_CONFIRMATION_DUAL_STATION.md` — 用户 19:04 范围确认 `SCOPE_DUAL_STATION_V1`（已按 19:17 裁定补充 2001 不补传）
- `12_DOCUMENTATION/V4_PACKAGE_ARRIVAL_NOTE.md` — V4 包到位盘点与差异登记（历史时间线）
- `12_DOCUMENTATION/WORKBUDDY_SCOPE_AND_GAPS.md` — 能力边界、规范冲突与分级缺口清单
- `10_TEST_REPORTS/ENVIRONMENT_PRECHECK.md` — 本机环境与资料预检（含真实 SHA-256），非阶段报告
- `10_TEST_REPORTS/README.md` — 清单优先级与现行路径入口
- `10_TEST_REPORTS/RAW_CSV_ARRIVAL_NOTE.md` — 原始 CSV 到位、归档与结构预检
- `10_TEST_REPORTS/RAW_CSV_PRECHECK_INVENTORY_CURRENT.csv` — **现行清单**（21 行，含 SHA-256 / 编码 / 时间格式 / 首末时间戳）
- `10_TEST_REPORTS/RAW_CSV_ARCHIVE_MANIFEST.csv` — 归档映射与 21/21 三项校验
- `10_TEST_REPORTS/RAW_CSV_PRECHECK_INVENTORY.csv` — 归档前快照，仅作校验基准
- `12_DOCUMENTATION/archive_raw_csv.py`、`precheck_raw_csv.py`、`preprocess_environment.py` — 可复现脚本
- `12_DOCUMENTATION/DEMO_PROTOTYPE.html` — 只读演示原型（非 S10 工作台、不进验收），已按配色规格重绘
- `05_CONFIG/FIGURE_COLOR_SPEC.md` / `figure_palette.json` / `COLOR_REFERENCE/` — 配色规格、唯一色值源、三张参考图原件
- `12_DOCUMENTATION/figure_palette.py` / `check_figure_colors.py` — 取色加载器与合规校验器
- `12_DOCUMENTATION/fishery_development_plan_20261114.html.temp` — 早期开发总规划，历史资料

## 用户确认的补充规格

| 规格 | 确认时间 | 内容 | 强制范围 |
| --- | --- | --- | --- |
| `SPEC_BASELINE_V4` | 2026-11-14 19:13 / 19:17 | 「这是全部要求」「以 V4 为准」「没有 2004」 | 全项目现行开发依据；`12_DOCUMENTATION/V4_REQUIREMENTS_INDEX.md` |
| `FIGURE_COLOR_SPEC_V1` 科研配色方案 | 2026-11-14 18:55 | 三套色板共 17 色 + 9 个中性色，唯一色值源 `figure_palette.json` | 07_FIGURES、S07/S09/S10 全部图表、论文插图、报告与 PPT 中的图、演示页 |
| `SCOPE_DUAL_STATION_V1` 双站先行与持续上传 | 2026-11-14 19:04 / 19:17 补充 | 21 个 CSV 为第一阶段完整导出；2001 到 11-07 结束**不补传**；2002/2003/2005 后续上传 | S00—S11 全部阶段；增量上传须从早期阶段实现；五站功能不得删减 |

- 所有绘图代码不得硬编码颜色；校验命令 `python3 12_DOCUMENTATION/check_figure_colors.py`，**色板外颜色数必须为 0**。
- 当前落地：`DEMO_PROTOTYPE.html`（455 处色值 / 25 种唯一色 / 色板外 0 种，PASS）。11 张潮汐 PNG 与 V4 12 几何示意图属不适用项，未改色未重绘。

## 目录状态

`00_PROJECT_SPEC` 至 `14_TEMP` 共 15 个一级目录；`01_ORIGINAL_DATA/FISHFINDER/` 已按 V4 归位为 **2000 / 2001 / 2002 / 2003 / 2005**（空的 `2004/` 已删除）。目前仅含归档资料与文档，无代码、无数据库、无分析结果。

## 环境信息（S00 任务六须在目标解释器内复测）

> 下表为 **2026-11-14 WorkBuddy 本机预检结果**，不是正式核验。

| 项 | 预检结果 | 与 V4 差异 / 处置 |
| --- | --- | --- |
| 操作系统 | Windows NT 10.0.22621（Win11 22H2） | 符合 |
| Python | 未装 3.10；实有 3.11.15 / 3.13 / 3.14 | **用户 19:17 已批准安装 3.10**；S00 安装并建 `.venv`、锁定依赖、目标解释器内复测 |
| 独立虚拟环境 `.venv` | 未建立 | S00 任务 |
| PyCharm | 实装 2025.2.1.1 | 版本不符（V4 写 2024.1），S00 如实登记 |
| OriginPro 2026b | 未发现安装；COM 未实测 | **S09 硬阻断**，未装时相关验收项标 BLOCKED |
| Git | 2.55.0.windows.3 可用；**仓库已初始化、初始回滚点已建立** | 用户 19:17 要求；S00 须核验复用并另建阶段回滚点 |
| 科学计算库 | pandas / numpy / matplotlib / openpyxl 缺失；Pillow 13.0.0 可用 | 依赖待锁定 |
| 原始数据 | `E:\鱼探仪` 不存在；21 个 / 8.38 GB CSV 已归档至 `FISHFINDER/2000/`、`2001/` | V4 `00_README.txt` 第 45 行仍写 E 盘路径（历史口径），S00 以项目内现行清单为准 |

## 原始数据

| 资料 | 位置 | 状态 |
| --- | --- | --- |
| 鱼探 CSV（**第一阶段双站完整导出**） | `01_ORIGINAL_DATA/FISHFINDER/2000/`（13 个，10-31—11-12）、`2001/`（8 个，10-31—11-07） | **21 个 / 8,380,445,292 字节 / 4,025,012 行**；21/21 SHA-256、字节数、mtime 全 PASS；用户 19:17 确认 **2001 不补传、数据已完整**；2002/2003/2005 后续持续上传；**归档不等于导入，未做 S02 审计** |
| 双站同期窗口 | — | **2026-10-31—11-07**，须由 S02/S07 按文件内真实时间戳复核；2000 的 11-08—11-12 为单站延伸，不计入双站同期样本量 |
| CSV 清单 | `RAW_CSV_PRECHECK_INVENTORY_CURRENT.csv`（现行）、`RAW_CSV_ARCHIVE_MANIFEST.csv`（映射与校验）、`RAW_CSV_PRECHECK_INVENTORY.csv`（归档前基准） | 各 21 行；8 个 UTF-8/BOM/LF/ISO + 13 个 GBK/CRLF/斜杠，信号统一 1000 点 |
| 风速 xlsx | `01_ORIGINAL_DATA/ENVIRONMENT/WIND/` | 288 行 / 12 天；来源为 Open-Meteo 数值模型、含 120 条未来预报，非实测；已生成格式预处理 CSV（非正式导入批次） |
| 潮汐.zip | `01_ORIGINAL_DATA/ENVIRONMENT/TIDE/` | 11 张 PNG 曲线截图（10-31—11-10，单位 cm）；无数值表、无基准面，**不满足入库条件**；未做图像估读 |
| 水温 / 五站 GPS / 厂家资料 | 对应 `01_ORIGINAL_DATA/` 子目录 | 目录为空，资料未见 |

## 运行标识

| 项 | 值 |
| --- | --- |
| import_batch_id | 无（尚未导入；归档 ≠ 导入） |
| run_id | 无（尚未分析） |
| origin_job_id | 无 |
| dataset_id | 无（DATASET_01~04 待建立） |
| 最新 Git 提交 | 初始安全回滚点 `183e469e5ff62b39adda2e2fde693995879b3e2e`；S00 成果提交见 `CHANGELOG.md` 顶部；阶段回滚点 tag 待 S00 验收通过后创建 |
| 最新测试结果 | pytest 29 passed（S00 冒烟）；V4 包 16/16 SHA-256 PASS；21 CSV 全量复核 PASS；配色校验色板外 0 PASS |
| 最新阶段报告 | `10_TEST_REPORTS/stage_reports/STAGE_S00.md`（已生成，待验收） |
| 冻结版本 | 无（DUAL_STATION / FIVE_STATION / PRE_DEFENSE / BLIND_REVIEW 均未建立） |

## 已关闭与仍待处置

**用户 19:17 已裁定的四项（争议关闭）**：① 以 V4 为准；② 五台为 2000/2001/2002/2003/2005、无 2004；③ 批准安装 Python 3.10；④ 要求 Git 安全回滚点；另确认 2001 到 11-07 结束、不会补传。

**仍须在 S00 如实登记或后续处置**：

1. OriginPro 2026b 未安装、COM 与 Learning Edition 窗口上限未实测（S09 阻断，相关验收项标 BLOCKED）。
2. PyCharm 版本差异（V4 写 2024.1，实装 2025.2.1.1）。
3. **波束角已确认（用户 2026-11-15）**：15° 为**全角**（FULL），内部半角 β = 7.5°；该值为五台同型号共用，S01 网页按台录入 `beam_angle_kind=FULL`。其余仍需网页填写：2001/2002/2003/2005 的截断值、离底高度、全部设备坐标与方位角，**保持 UNKNOWN，禁止复制 2000 的 5.2 m / 3.68 m 或默认 (0,0)**。
4. 五站正式同步开始时间、第一阶段正式截止时间、安装调试期时间线未确认。
5. 双站同期窗口须按真实时间戳核验；2000 的 11-08—11-12 为单站延伸。
6. 水温数值、潮汐逐时表与潮位基准面、实测风速、五站 GPS、五台安装参数、厂家资料仍缺。
7. 21 个 CSV 只做了只读结构预检与哈希，**S02 正式审计与导入未做**；后续上传须逐文件探测编码。
8. 性能预算 W1—W3 须在 S00 用真实样本冻结。
9. 范围：36 交付 / 31 入口 / 18 报告 / 16 图 / 45 验收全部保留；任何缩减须作正式范围变更确认。

## 下一步

四项裁定已定，直接把 `12_DOCUMENTATION/S00_START_PROMPT.md` 代码块整段发给 CodeBuddy 即可开工：S00 安装 Python 3.10 并建 `.venv`、核验已有 Git 初始回滚点、在目标解释器内复测环境、核对 21 个原始 CSV 现行路径、建立需求追踪矩阵（24 章 / 36 交付 / 31 入口 / 18 报告 / 16 图 / 45 验收）与 S00—S11 计划、列出 V4 与历史基线差异，生成 `STAGE_S00.md` 后**停止等待用户验收**。S01 前置条件满足前不得开始。

五站功能继续开发，2002/2003/2005 数据后续持续上传；涉及五站真实数据的验收项在数据到位前标 `BLOCKED / 待数据`，不得用双站数据冒充五站结论。
