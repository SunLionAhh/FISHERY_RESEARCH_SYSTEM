# STAGE_S01 — 数据库、五台设备和独立参数管理（阶段报告）

> 阶段：S01｜依据：`FISHERY_FULL_PLAN_V4/03_CODEX_STAGE_TASKS_FINAL.md` 第四章（L367—593）+ V4 强制增项（五台参数与 GPS 可操作网页不得推迟到 S10）
> 执行日期：2026-11-15（首版）／2026-11-16（验收整改）｜环境：项目 `.venv`（Python 3.10.11）｜S00 验收回滚点：tag `s00-accepted`（提交 `373add0`）
> **状态总览：S01 九项任务全部实际执行；首版 53 测试全过但被独立验收判 3 项 D1 缺陷（K13 校验、依赖锁、迁移原子性）+ 5 项 P2 观察项；2026-11-16 已完成整改，93 测试全过，等待复验（复验通过前不开始 S02）**
> 首版提交 `8deaad7` → 整改提交 `5aae0e5`｜验收报告：`10_TEST_REPORTS/stage_reports/ACCEPTANCE_S00_S01.md`

---

## 1. 阶段目标

建立 SQLite 数据库迁移机制（12 张表）、五台设备独立参数管理（含独立离底高度换算、参数历史版本、人工水底参考面、两阶段数据集）、五台设备参数与 GPS 可操作网页、原始文件登记；按任务七 P1—P5 测试值完成独立性与换算验证；输出阶段报告。

## 2. 前置检查与回滚点

- S00 验收通过（用户 2026-11-15），已建阶段回滚点 **tag `s00-accepted`**。
- 迁移前置检查：`03_DATABASE/` 为空，无既有库可覆盖；`ensure_database()` 记录 `db_existed_before` 状态到 audit_logs，迁移不覆盖任何数据。
- 数据库位置：`03_DATABASE/fishery.db`（`.gitignore` 已排除 `*.db`，可由迁移+种子幂等重建）。

## 3. 任务一：数据库与迁移机制（12 张表）

迁移框架：`04_SOURCE_CODE/app/db.py` + `app/migrations/0001_init.sql`（整改新增 `0002_devices_station_id.sql`）；`schema_migrations` 记录已应用版本；重复执行幂等（测试验证二次 create 不重复播种）。

> **整改更正（2026-11-16）**：首版声称「每个迁移文件在独立事务中执行」**当时不成立**——`BEGIN` 后调用 `executescript()` 会隐式提交，失败后残留半套表（验收报告 §4.3 复现）。现已改为：迁移连接 `isolation_level=None`（autocommit）+ 显式 `BEGIN IMMEDIATE → 逐条 execute → 写 schema_migrations → COMMIT`，失败 `ROLLBACK`；语句用 `sqlite3.complete_statement` 逐字符切分（注释/字符串内分号不误切）。该声明自 `5aae0e5` 起与实现一致，并由 `test_bad_migration_rolls_back_atomically` 证明。

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

**pytest：首版 53 passed；整改后（2026-11-16）93 passed / 0 failed / 0 skipped**（S00 冒烟 29 + S01 首版 24 + 整改新增 40）。

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
| K13：11 组非法输入（负截断/零离底/倾角120/半角95/全角200/方位365/空来源/空日期/经度181 等）全部 400 拒绝 | 首版 PASS（但未覆盖 NaN/inf/单位混用 → 验收判 D1-1，见 §16.1；整改后全量 PASS） |
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

整改新增/修改（2026-11-16，`5aae0e5`）：新增 `app/identity.py`、`app/migrations/0002_devices_station_id.sql`、`tests/test_s01_fix.py`、`requirements.txt`、`12_DOCUMENTATION/verify_s01_fix.py`；修改 `app/db.py`（原子迁移）、`app/services/devices.py`（安全数值校验/量程上限/操作者）、`app/web/routes.py`（expected_version 400、预览容错）、`app/templates/device.html`（站位显示、预览不借值）、`requirements-lock.txt`（重建 39 行）。

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
| **截断上限阈值** | 整改新增：`devices.range_m` 已知时用它，UNKNOWN 时按 **100 m 临时上限**校验（`CUTOFF_FALLBACK_MAX_M`）。阈值来源：本机量程 37.5 m、量程字段为空；**待用户确认量程后收紧为 range_m 并重跑边界测试**（登记于 `app/services/devices.py` 注释与 §16.1） |
| **站位入口** | 整改新增 `devices.station_id`（迁移 0002，可空）；`stations` 表仍为空、页面显示「站位：未分配」。**站位录入入口与坐标待用户提供，S08 前补齐**（P2-1 已从「缺列」降级为「缺数据/入口」） |
| **操作者身份强度** | `created_by`/`audit_logs.actor` 已改为系统登录名（`app/identity.py`）；本机单用户、无登录鉴权，属**弱标识**，S10 若引入多用户须替换为账号主体（P2-3） |
| **K01 未知设备待映射队列** | S01 只实现设备清单；未知编号映射属导入期能力，**S02 复验**（P2-4 已在追踪矩阵降级为「部分实现」） |

## 15. S02 前置条件

1. S01 报告经用户验收。
2. 数据库与 file_registry 已就绪；S02 将做 21 个 CSV 流式解析、编码逐文件探测、距离映射审计、统一硬掩码服务、数据审计 8 项产物。
3. 采样语义核实需用户确认原始信号数组是「点位置」还是「区间」（S02 现场核对，未核实前正式距离分析 BLOCKED）。
4. **复验通过**（`ACCEPTANCE_S00_S01.md` 第 6 节 5 条复验口径）。

## 16. 验收整改记录（2026-11-16）

> 依据：`ACCEPTANCE_S00_S01.md`（独立验收人 WorkBuddy，2026-11-16）、09 第二节证据字段、09 第五节缺陷分级。
> 执行版本：首版 `8deaad7` → 整改 `5aae0e5`（不 amend、非破坏性提交）。
> 环境：Windows 11 NT 10.0.22621｜`.venv` Python 3.10.11｜Flask 3.1.3 / pytest 9.2.0。
> 输入文件与 SHA-256：HTTP 用例无输入文件（N/A）；`requirements-lock.txt` = `2dd7b226b989fbd560cfc03622de0d824a304a01e2a66089776177310d423eb8`；`tests/test_s01_fix.py` = `93ca3de99bc058d905a61d7e4bf26918110f6b6f9980c438dd21b79df64b792d`；`app/services/devices.py` = `d0b71aaa468dca26c9709b6af110f75f5f4797d090b3a4c9c4f718986a338967`。
> 设备与参数版本：复验用 `03_DATABASE/fishery.db` 副本（`14_TEMP/fix_verify.db`），参数版本 2000 v1、2001 v1，其余三台 0 行。
> 执行者：CodeBuddy（开发）｜复核者：WorkBuddy（待复验）。
> 证据汇总：`10_TEST_REPORTS/s01_verification/fix_evidence/`（`pytest.txt`、`verify_db.txt`、`pip_dryrun.txt`、`curl_cases.txt`、`bad_migration_and_lock.txt`）。运行时间：2026-11-16。

### 16.1 D1-1 K13 校验漏洞（阻断签收 → 已修复）

**代码改动**：`app/services/devices.py`

- `_num()` 废弃，改为 `_parse_number(form, key, label, errors)`：非数字捕获为字段级错误（不再 500）；`math.isfinite()` 拒绝 NaN/inf/-inf/1e999；非法值用 `_INVALID` 哨兵与「空值」区分，**不可能静默入库**。
- 截断有限上界：优先 `devices.range_m`（已知量程），为空时 `CUTOFF_FALLBACK_MAX_M = 100 m` 兜底，错误文案明确「量程 UNKNOWN，按上限 100 m 临时校验」；**阈值来源：本机量程 37.5 m、`devices.range_m` 当前为空；待用户确认量程后收紧为 range_m 并重跑边界测试**。
- 同一有限性校验覆盖：`vertical_bottom_clearance_m`、`axis_slant_m`、`downward_tilt_deg`、`beam_angle_value_deg`、`heading_deg`、`longitude_deg`、`latitude_deg`、`position_accuracy_m`。
- `app/web/routes.py`：新增 `parse_expected_version()`，`abc`/空串/负数/非整数 → 400「预期版本号非法」，参数与位置两处均改；字段整体缺失（脚本/接口调用）保持 0。预览接口改为 `require_cutoff=False` + 传入本台 `range_m`，非法字段仍 400+JSON（不再整页 500）。

| 用例 ID | 需求条款 | 操作步骤 | 预期 | 实际（实测） | 判定 |
| --- | --- | --- | --- | --- | --- |
| TC-K13-01～06 | 09 K13 / 08 硬截断 | `POST /devices/2003/params` 截断 = `NaN`/`nan`/`inf`/`Infinity`/`-inf`/`1e999` | 400，提示「必须为有限数值」，不入库 | 全部 400，字段定位「人工分析截断斜距」，行数 0→0 | PASS |
| TC-K13-07～08 | 09 K13 | 截断 = `abc`/`5.2m` | 400，提示「必须为数字」 | 400，不再 500 | PASS |
| TC-K13-09～10 | 09 K13 | 截断 = `0`/`-1` | 400，提示「必须 > 0」 | 400（HTML 转义 `&gt;`） | PASS |
| TC-K13-11～12 | 09 K13 单位混用/超量程 | 截断 = `520`（cm 当 m）/`1e9` | 400，提示「量程 UNKNOWN，按上限 100 m 临时校验」 | 400 且文案一致；`curl_cases.txt` 记录 | PASS |
| TC-K13-13～14 | 09 K13 / K15 | `expected_version=abc` / 空串（参数与位置表单） | 400「预期版本号非法」 | 400，不再 500 | PASS |
| TC-K13-15～16 | 09 K13 | 位置表单经度/纬度 = `NaN`/`inf`/`abc` | 400 并定位字段 | 400（「经度」「纬度」） | PASS |
| TC-K13-17 | 09 K13 | 定位精度 = `NaN` | 400 并定位字段 | 400（「定位精度」） | PASS |
| TC-K13-18 | 09 K13 | 量程已知（`range_m=37.5`）截断 = `40` | 400「超出本台量程 37.5 m」 | 400；`5.2` 仍通过 | PASS |
| TC-K13-19 | 09 K13 / P2-2 | 预览：截断空 → 200 且截断为 null；截断 `NaN` → 400 JSON | 不整页 500、不借用他台值 | 200 `analysis_cutoff_slant_m_will_be=null`；400 `{"ok":false,"errors":[...]}` | PASS |

**复验命令与真实输出**（完整见 `fix_evidence/pytest.txt`、`curl_cases.txt`）：

```
> POST cutoff=NaN|inf|-inf|abc|520|1e9 -> 400；expected_version=abc|'' -> 400；
> BEFORE 2002/2003/2005 rows=0,0,0；AFTER 0,0,0（非法提交零入库）
> 合法 5.2 -> 302（未过度拦截）
```

### 16.2 D1-2 依赖锁文件（阻断 S00 依赖交付 → 已修复）

- 旧文件：583 字节、**0 个换行**、带 UTF-8 BOM，pip 报 `No matching distribution found for blinker==1.9.0certifi==…`。
- 新文件：用 `pip freeze --all` 经 Python 直接写盘（`encoding='utf-8', newline='\n'`），**39 行、每行一包、无 BOM、LF**；新增运行期最小集 `requirements.txt`（flask / python-dotenv / requests），用途在文件头注明（部署者阅读用；精确复建用 lock）。
- 校验一：行数 39 ≥ 30，逐行匹配 `^[A-Za-z0-9_.\-]+==\S+$`（测试 `test_requirements_lock_is_parseable_multiline`）。
- 校验二：`pip install --no-deps --dry-run -r 04_SOURCE_CODE\requirements-lock.txt` → 39 行全部 "Requirement already satisfied"，**无解析错误**（`fix_evidence/pip_dryrun.txt`）。

| 用例 ID | 需求条款 | 操作 | 预期 | 实际 | 判定 |
| --- | --- | --- | --- | --- | --- |
| TC-DEP-01 | 09 第 12 项 / K43 | 检查锁文件字节 | 无 BOM、LF、≥30 行、格式合法 | 39 行、无 BOM、LF、格式全合法 | PASS |
| TC-DEP-02 | K43 | `pip install --dry-run -r` | 可解析，无 "No matching distribution" | 全部 satisfied | PASS |

### 16.3 D1-3 迁移原子性（阻断迁移可信度 → 已修复）

- 旧实现 `BEGIN` + `executescript()`：`executescript` 隐式提交 → 回滚后残留 `a`/`b` 表（验收 §4.3 复现）。
- 新实现（`app/db.py`）：迁移连接 `isolation_level=None` → `BEGIN IMMEDIATE` → 逐条 `execute` → 写 `schema_migrations` → `COMMIT`，异常 `ROLLBACK` 并恢复原 isolation；语句由 `split_sql_statements()` 逐字符累积 + `sqlite3.complete_statement` 切分（注释/字符串中的分号不误切）。
- 顶部注释已改为与实现一致的表述，不再声称未做到的能力。

| 用例 ID | 需求条款 | 操作 | 预期 | 实际 | 判定 |
| --- | --- | --- | --- | --- | --- |
| TC-MIG-01 | K43 / 02 第六章 | 临时目录注入坏迁移（建 `schema_migrations`/`half_a`/`half_b` + 插入后执行必错语句） | 抛异常后三表均不存在、无版本记录、既有表与数据完好 | 三表全部回滚；`preexisting` 行 `keep-me` 保留 | PASS |
| TC-MIG-02 | K43 | 坏迁移回滚后执行修正版迁移 | 可正常落地，不被半套对象阻塞 | `applied=['0001']`，`ok_table` 存在 | PASS |
| TC-MIG-03 | 迁移切分 | 含注释/字符串分号的 SQL | 切分为 2 条完整语句 | 2 条，注释保留 | PASS |

### 16.4 P2 观察项处置（逐条，不沉默）

| 编号 | 处置 | 证据/登记位置 |
| --- | --- | --- |
| P2-1 站位 | **已改结构**：迁移 `0002_devices_station_id.sql` 为 `devices` 增加可空 `station_id`；种子保持 NULL；详情页显示「站位：未分配」；`stations` 表不伪造。站位名称/坐标与录入入口待用户提供（§14 已登记，S08 前补齐）。影响：K19「区分设备位置/站位/安装历史」的站位一侧从「缺列」降为「缺数据」 | `test_devices_have_station_id_column_and_unassigned`、`test_device_page_shows_station_unassigned`；`verify_db.txt` 显示五台 station_id 全 NULL |
| P2-2 预览预填 | **已修**：无参数设备的预览链接不再写死 `analysis_cutoff_slant_m=5.2`（改为空）；预览接口容忍空截断 → `analysis_cutoff_slant_m_will_be=null` + note「截断未填写（预览不借用其他设备数值）」，其他字段非法仍 400+JSON | `test_preview_link_does_not_borrow_5_2`、`test_preview_tolerates_empty_cutoff`、`test_preview_invalid_value_returns_400_json`；`curl_cases.txt` |
| P2-3 操作者 | **已修**：新增 `app/identity.py`（`USERNAME`/`USER`/`getpass` 兜底），`created_by` 与 `audit_logs.actor` 写真实登录名，seed 仍写 `seed`；**登记：本机单用户、无登录鉴权，属弱标识，S10 多用户须替换为账号主体** | `test_operator_recorded_not_hardcoded_web` |
| P2-4 矩阵状态 | **已修**：K13 改 PASS 并写用例 ID；K01 改「S01 部分实现（设备清单），未知设备待映射队列属导入期，S02 复验」；K43 登记迁移/依赖整改；第 20 章 Flask 工作台标注 S01 部分实现 | `12_DOCUMENTATION/REQUIREMENTS_TRACEABILITY_MATRIX.md` |
| P2-5 报告缺项 | **已修**：本 §16 与 §14 补齐；迁移事务不实声明已在 §3 更正；截断阈值、站位、操作者、K01 均单列登记，不从分母消失（K44） | 本文件 §3/§14/§16 |

### 16.5 既有验收项回归（不得被整改削弱）

- `pytest 04_SOURCE_CODE/tests -q` → **93 passed**（首版 53 项断言一字未改、未放宽；新增 40 项）。
- 正式库只读复验（`verify_s01_fix.py`，`fix_evidence/verify_db.txt`）**全 PASS**：
  - 五台设备 `2000/2001/2002/2003/2005`，无 2004；`station_id` 全 NULL；
  - 2000：截断 **5.2**、垂直 **3.68**、倾角 **45**、波束 **15 FULL**、β **7.5**、派生 **5.2043059095**（≠5.2，`is_derived=1`，未覆盖 5.2）；
  - 2001：截断 5.2、垂直 3.6、倾角保持 NULL；2002/2003/2005 参数行 **0**、无 3.68；
  - 库内截断字面量仅 `['5.2','5.2']`，无 inf/nan，无 NULL 截断版本。
- 原始数据与规范包零改动：`git status` 中不含 `01_ORIGINAL_DATA` 与 `FISHERY_FULL_PLAN_V4`（21 CSV、V4 16 文件均未触碰）。
- 配色校验不受影响（本轮无新增图表；页面 CSS 仍全部取自色板）。

### 16.6 复验口径（对应验收报告第 6 节）

| # | 复验项 | 命令/位置 |
| --- | --- | --- |
| 1 | NaN/inf/abc/520 → 400 | `fix_evidence/curl_cases.txt`；或起 5055 副本服务复跑 |
| 2 | `expected_version=abc` → 400 | 同上 |
| 3 | 锁文件可解析 | `fix_evidence/pip_dryrun.txt` |
| 4 | 坏迁移回滚 | `fix_evidence/bad_migration_and_lock.txt` |
| 5 | pytest 全绿 ≥58 | `fix_evidence/pytest.txt`（93 passed） |

---

**结论：S01 首版 3 项 D1 已修复并有可复现证据（K13 全量拒绝且零入库、锁文件 39 行可解析、迁移真原子可回滚），5 项 P2 已逐条处置或登记；93 测试全过；已提交 `5aae0e5`。本报告提交复验；复验通过前不开始 S02。**
