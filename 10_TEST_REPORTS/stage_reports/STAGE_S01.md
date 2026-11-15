# STAGE_S01 — 数据库、五台设备和独立参数管理（阶段报告）

> 阶段：S01｜依据：`FISHERY_FULL_PLAN_V4/03_CODEX_STAGE_TASKS_FINAL.md` 第四章（L367—593）+ V4 强制增项（五台参数与 GPS 可操作网页不得推迟到 S10）
> 执行日期：2026-11-15｜环境：项目 `.venv`（Python 3.10.11）｜S00 验收回滚点：tag `s00-accepted`（提交 `373add0`）
> **状态总览：S01 九项任务全部实际执行；53 个自动测试全过；真实服务界面证据已归档；待用户验收（验收前不开始 S02）**

---

## 1. 阶段目标

建立 SQLite 数据库迁移机制（12 张表）、五台设备独立参数管理（含独立离底高度换算、参数历史版本、人工水底参考面、两阶段数据集）、五台设备参数与 GPS 可操作网页、原始文件登记；按任务七 P1—P5 测试值完成独立性与换算验证；输出阶段报告。

## 2. 前置检查与回滚点

- S00 验收通过（用户 2026-11-15），已建阶段回滚点 **tag `s00-accepted`**。
- 迁移前置检查：`03_DATABASE/` 为空，无既有库可覆盖；`ensure_database()` 记录 `db_existed_before` 状态到 audit_logs，迁移不覆盖任何数据。
- 数据库位置：`03_DATABASE/fishery.db`（`.gitignore` 已排除 `*.db`，可由迁移+种子幂等重建）。

## 3. 任务一：数据库与迁移机制（12 张表）

迁移框架：`04_SOURCE_CODE/app/db.py` + `app/migrations/0001_init.sql`；`schema_migrations` 记录已应用版本；重复执行幂等（测试验证二次 create 不重复播种）。

| 表 | 用途 |
| --- | --- |
| devices | 五台设备（2000/2001/2002/2003/2005，无 2004） |
| stations | 站位（预留） |
| device_parameter_versions | 参数版本行（只追加，不可变历史） |
| device_parameters | 每台当前版本指针 |
| device_positions | 位置版本行（历史保留，K19/GEO-01） |
| device_installations | 安装记录 |
| bottom_references | 水底参考面（USER_DEFINED_ESTIMATED / AUTO_DETECTED） |
| file_registry | 原始文件登记 + SHA-256 + 重复检查 |
| import_batches | 导入批次（S02 使用） |
| analysis_runs | 分析运行（含 params_snapshot_json 配置快照） |
| datasets / dataset_members | 两阶段研究数据集 |
| audit_logs | 全部操作审计 |

## 4. 任务二/三：五台设备独立参数与独立离底高度

- 每台独立保存：截断斜距、离底参考（显式输入类型 VERTICAL/AXIS_SLANT/UNKNOWN）、倾角及基准、波束角数值与 FULL/HALF/UNKNOWN 类型、方位角及基准、经纬度、坐标系、精度、来源、生效区间。
- **独立换算（不写回）**：VERTICAL 输入 → 派生轴斜距 = 垂直/sin(倾角)；AXIS_SLANT 输入 → 派生垂直 = 轴距×sin(倾角)。派生值标记 `is_derived=1`，存 `derived_*` 列，**不覆盖**用户输入位，**不覆盖**人工分析截断 `analysis_cutoff_slant_m`（K03/GEO-03 测试断言 5.2043 ≠ 5.2）。
- 未知参数保存 UNKNOWN（NULL），**不自动填 3.68**（测试断言 2005 无任何 3.68 行）。

## 5. 任务四：参数历史版本

每次保存生成新版本行：版本号、生效起/止、参数值、来源、测量方式、不确定性、修改原因。旧版本行永不更新（只有 `effective_to` 被新版本关闭）；`analysis_runs.params_snapshot_json` 引用参数版本 id，新参数不改变历史结果。测试验证 v1 值保留、区间闭合、当前指针指向 v2。

## 6. 任务五：2000 号人工水底参考面初始配置

已按用户裁定播种（与阶段文本的两处差异均为用户后续裁定，登记于 CHANGELOG）：

| 项 | 值 | 备注 |
| --- | --- | --- |
| 垂直离底高度 | 3.68 m | USER_DEFINED_ESTIMATED，非厂家校准 |
| 倾角 | 45° | 用户此前提供 |
| 波束角 | 15° **FULL**（β=7.5°） | **用户 2026-11-15 确认全角**（阶段文本原写 UNKNOWN） |
| 分析截断 | 5.2 m | 硬上限；理论 5.2043 仅派生参考 |
| 声学探底状态 | NOT_DETECTED | 2000 允许不启用自动探底 |
| 2001 | 截断 5.2 m、离底 3.6 m、坐标 | **用户 2026-11-15 提供**，独立输入非继承；倾角/方位角 UNKNOWN |
| 2002/2003/2005 | 全部 UNKNOWN（PENDING_USER_INPUT） | 禁止复制 2000/2001 数值 |
| 两台坐标 | 已播种（12—13 位小数） | CRS/精度 UNKNOWN（不默认 WGS84）；方位角用户后天补录 |

## 7. 任务六：研究数据集

`DATASET_01_DUAL_STATION`（阶段 1，成员 2000+2001）与 `DATASET_02_FIVE_STATION`（阶段 2，五台）已建立，状态 PLANNED，起止时间为空（待实际确认，不编造）；引用 `file_registry` 登记路径，不复制大型 CSV。

## 8. 任务八：原始文件登记

`file_registry` 从 `RAW_CSV_ARCHIVE_MANIFEST.csv` 播种 **21 行**（2000：13、2001：8），逐文件 64 位 SHA-256，状态 ARCHIVED_REGISTERED；相对路径唯一约束 + 同哈希异路径冲突备注（重复检查）。原始文件未做任何修改。

## 9. 强制增项：五台参数与 GPS 可操作网页

| 页面 | 路径 | 功能 |
| --- | --- | --- |
| 设备清单 | `/` | 五台状态矩阵 + **未知参数队列**（K01）+ 数据集概览 |
| 设备详情 | `/devices/<id>` | 当前参数表、参数表单（含全字段+生效区间）、GPS 表单、参数历史表、位置历史表、水底参考面 |
| 保存参数 | `POST /devices/<id>/params` | 后端校验（K13）→ 新版本；预期版本过期 → **409 并发冲突**；错误 400 渲染 |
| 保存位置 | `POST /devices/<id>/position` | 同上；历史保留不覆盖 |
| 影响预览 | `GET /devices/<id>/params/preview` | JSON：派生值、β 换算、**截断上限不受派生影响**声明 |

- 缓存失效设计：统计类缓存一律以参数版本 id 为键；参数变更产生新版本 id，旧快照结果不失效不漂移（S03 起落实）。
- 配色：页面 CSS 全部取自 `05_CONFIG/figure_palette.json`（neutral 组 + A/B 方案色），`check_figure_colors.py` 复验 PASS（色板外 0）。

## 10. 任务七：测试结果（P1—P5 测试值）

**pytest：53 passed / 0 failed / 0 skipped**（S01 24 项 + S00 冒烟 29 项）。

| 验证点 | 结果 |
| --- | --- |
| 五台参数独立（P1=3.20/P2=3.50/P3=3.68/P4=3.80/P5=4.00） | PASS |
| 修改 P1（2000→4.10）不影响其他四台 | PASS |
| 不同倾角换算正确（45°：3.68→5.2043；30°：5.2→2.6） | PASS |
| UNKNOWN 不自动填默认值（无 3.68 自动填入） | PASS |
| 参数历史版本保留、区间闭合、不可覆盖 | PASS |
| 人工底界可独立设置（2000 初始 + 2001 可加） | PASS |
| 两阶段数据集可独立创建 | PASS |
| K03/GEO-03：3.68/5.2/45° 同行共存，5.2043≠5.2 | PASS |
| K13：11 组非法输入（负截断/零离底/倾角120/半角95/全角200/方位365/空来源/空日期/经度181 等）全部 400 拒绝 | PASS |
| 409 并发冲突（过期版本号提交） | PASS |
| K19/GEO-01：经纬度网页录入→回读→二次录入→历史 2 行且首行未覆盖 | PASS |
| 迁移幂等（二次执行不重复播种） | PASS |
| file_registry 21 行（13+8）、SHA-256、路径唯一 | PASS |

## 11. 界面证据（真实服务）

| 证据 | 位置 | 结果 |
| --- | --- | --- |
| 首页 HTML（五台矩阵+未知队列） | `10_TEST_REPORTS/s01_verification/web_evidence/index.html` | GET / → 200 |
| 2000 详情页 | `.../device_2000.html` | 200；显示 5.2/3.68/45°/15°FULL/β7.5/派生5.2043 |
| 2001 详情页 | `.../device_2001.html` | 200；显示 5.2/3.6/坐标 |
| 预览接口 JSON | `.../preview_2001.json` | 200；`derived_axis_slant_m=5.0912`（3.6/sin45）、β=7.5、cutoff 不受派生影响 |
| 证据日志 | `.../evidence_log.txt` | 4 个请求全部 200 |

## 12. 修改文件清单

新增：`app/__init__.py`、`app/config.py`、`app/db.py`、`app/seed.py`、`app/migrations/0001_init.sql`、`app/services/devices.py`、`app/web/routes.py`、`app/templates/{base,index,device,error}.html`、`run.py`、`tests/conftest.py`、`tests/test_s01_devices.py`、`10_TEST_REPORTS/s01_verification/`（5 个证据文件）。修改：`.gitignore`（排除 *.db）、`tests/test_s00_smoke.py`（「尚无实现代码」断言随 S01 过时，改为结构守护：实现只在 app/，测试只在 tests/，白名单 run.py）。

启动方式：在 `04_SOURCE_CODE` 下执行 `.venv\Scripts\python.exe run.py`，浏览器打开 `http://127.0.0.1:5000`（仅绑定本机）。

## 13. 独立数值复算

- 3.68/sin(45°) = 5.2043059…（派生参考，≠5.2，测试断言）
- 5.2×sin(30°) = 2.6；3.6/sin(45°) = 5.0911688（预览接口实测一致）
- 15° 全角 → β = 7.5°（FULL 派生规则）

## 14. 未完成事项 / 阻断

| 项 | 状态 |
| --- | --- |
| 方位角（两台 heading） | UNKNOWN，用户后天提供 → 表单补录即生成新位置版本 |
| 坐标系/定位精度 | UNKNOWN（不默认 WGS84），待用户确认 |
| 2001 倾角 | UNKNOWN（未继承 45°） |
| 2002/2003/2005 参数 | PENDING_USER_INPUT，待用户网页填写 |
| 数据集起止时间 | 空值待确认（第一阶段截止=五站同步开始前） |
| 距离采样语义 | 留待 S02 核实（本阶段不涉及距离分析） |
| 16 图/18 报告/Origin | 后续阶段 |

## 15. S02 前置条件

1. S01 报告经用户验收。
2. 数据库与 file_registry 已就绪；S02 将做 21 个 CSV 流式解析、编码逐文件探测、距离映射审计、统一硬掩码服务、数据审计 8 项产物。
3. 采样语义核实需用户确认原始信号数组是「点位置」还是「区间」（S02 现场核对，未核实前正式距离分析 BLOCKED）。

---

**结论：S01 九项任务完成并有证据工件（迁移幂等、53 测试全过、真实服务 4 请求 200、界面证据归档）；本报告提交用户验收；验收通过前不开始 S02。**
