# S00 / S01 独立验收报告

> 验收人：WorkBuddy（独立复核，**不采信阶段报告自述**，全部结论由本机重算/重跑得出）
> 验收日期：2026-11-16｜被验版本：Git `8deaad7`（S01）、`ac2e763`（S00）
> 规范依据：`FISHERY_FULL_PLAN_V4/09_DEVELOPER_ACCEPTANCE.md`、`03_CODEX_STAGE_TASKS_FINAL.md` 第三章/第四章、`08_USER_REQUIREMENTS_V4.md`
> 环境：Windows 11 NT 10.0.22621｜`.venv` Python 3.10.11｜Flask 3.1.3 / numpy 2.2.6 / pandas 2.3.3 / matplotlib 3.10.9 / pytest 9.2.0 / openpyxl 3.1.5

---

## 0. 结论摘要

| 阶段 | 结论 | 说明 |
| --- | --- | --- |
| **S00** | **有条件通过（1 项必改）** | 九项任务实体交付全部核实为真（V4 16/16、CSV 21/21、备份 30/30、29 冒烟测试），唯一缺陷是 `requirements-lock.txt` 损坏、pip 无法解析 → 依赖锁定这份交付物实际不可用 |
| **S01** | **不通过，暂缓签收（3 项必改）** | 数据库、五台设备、版本链、409 冲突、经纬度录入均实测可用；但 **K13 参数校验存在可写入 `NaN`/`inf` 的硬截断漏洞**，且迁移"事务"声明不成立 → 属于核心验收项未过 |

> S00 已打 tag `s00-accepted` 属于既成事实，本次不改标签；建议随 S01 整改一并修订锁文件。**S01 不得进入 S02**，先修 D1-1～D1-3 后复验。

---

## 1. 验收方法

1. 读规范原文（09 K 清单、03 第四章 S01 十二项任务、08 用户要求），不看报告结论先行。
2. **独立重算**：自写 `14_TEMP/acceptance_recheck.py`，直接以 `MANIFEST_SHA256.json` 与 `RAW_CSV_ARCHIVE_MANIFEST.csv` 为基准重算 SHA-256，不复用被测脚本 `s00_verify_integrity.py`。
3. **独立重跑**：`pytest 04_SOURCE_CODE/tests -q`；配色校验脚本。
4. **真实服务实测**：把 `03_DATABASE/fishery.db` 复制为 `14_TEMP/acceptance.db`，以 `FISHERY_DB_PATH` 指向副本另起 5055 端口，用 curl 逐条打接口做破坏性输入；验完确认正式库 `audit_logs` 仍为 3 条、`SAVE_PARAM` 为 0、Git 工作区干净。
5. 只读核对源码（`app/db.py`、`app/services/devices.py`、`app/web/routes.py`、`migrations/0001_init.sql`、`templates/*.html`）。

---

## 2. S00 逐项验收

| # | 验收点 | 规范/任务 | 我的复算结果 | 判定 |
| --- | --- | --- | --- | --- |
| 1 | 目标解释器 | 任务六 | `.venv\Scripts\python.exe -V` → `3.10.11` | PASS |
| 2 | 核心依赖实测导入 | 任务六 | flask 3.1.3 / numpy 2.2.6 / pandas 2.3.3 / matplotlib 3.10.9 / pytest 9.2.0 / openpyxl 3.1.5，与报告一致 | PASS |
| 3 | **依赖锁定可用性** | 任务六交付物 | `requirements-lock.txt` 共 583 字节、**换行数 0**、带 UTF-8 BOM；`pip install -r` 报 `No matching distribution found for blinker==1.9.0certifi==2026.10.23…`（37 个包被拼成一行） | **FAIL** |
| 4 | V4 包完整性 16/16 | 任务五 | 逐文件重算 SHA-256 + 字节数，**16/16 全等** | PASS |
| 5 | 原始 CSV 21/21 | 任务五 | 逐文件重算，**21/21 哈希与字节数全等，合计 8,380,445,292 字节** | PASS |
| 6 | 基线备份可恢复 | 任务七 | `BACKUP_MANIFEST.csv` 30 条，逐文件重算哈希 **30/30 PASS，无缺失** | PASS |
| 7 | 需求追踪矩阵 | 任务八 | 24 章/36 交付/31 入口/18 报告/16 图/**45 条 K 全覆盖**（双栏排版，K01—K23 + K24—K45）；状态如实标注 162 项"未实施" | PASS（内容真实性见 4.5） |
| 8 | S00—S11 开发计划 | 任务八 | `DEV_PLAN_S00_S11.md` 7,136 字节，含阶段表/关键路径/硬契约检查表/R1—R10 风险 | PASS |
| 9 | 冒烟测试 29 项 | 任务八 | `pytest` 实测 **53 passed**（= S00 冒烟 29 + S01 24），4.04s，0 skip | PASS |
| 10 | Git 安全回滚点 | 用户裁定 | tag `s00-accepted` 存在，历史 7 个提交完整，工作区干净 | PASS |
| 11 | 配色合规 | FIGURE_COLOR_SPEC_V1 | 色板 26 色一致、3 张参考图 SHA-256、`DEMO_PROTOTYPE.html` 455 处色值/25 唯一色/**色板外 0** | PASS |

**S00 唯一缺陷（必改）**

- **D1-2 依赖锁文件损坏**：`04_SOURCE_CODE/requirements-lock.txt` 无换行、含 BOM，`pip install -r` 100% 失败。影响 09 第 12 项"依赖与环境可复建"与 K43；换机器/换人无法重建环境。整改：用 `pip freeze` 重定向到文件时避免 PowerShell 单行拼接，或直接 `.venv\Scripts\python.exe -m pip freeze --all | Out-File -Encoding utf8`，修完需附 `pip install --dry-run -r` 成功输出。

---

## 3. S01 逐项验收

### 3.1 数据库与任务一～六（结构与数据）

| # | 验收点 | 实测结果 | 判定 |
| --- | --- | --- | --- |
| 1 | 12 张规范表齐全 | `devices / stations / device_parameters / device_parameter_versions / device_installations / bottom_references / file_registry / import_batches / analysis_runs / datasets / dataset_members / audit_logs` 全部存在；另加 `schema_migrations`、`device_positions`（强制增项）共 14 张 | PASS |
| 2 | 迁移幂等 | `schema_migrations` 1 行（0001），二次 `create_app` 不重复播种（测试覆盖） | PASS |
| 3 | **迁移事务原子性** | 实测：`BEGIN` + `executescript` 中途报错 → `rollback()` 后 **表 `a`、`b` 与已插入行仍在**（`executescript` 隐式提交 BEGIN）。`app/db.py` 注释与 S01 报告"每个迁移文件在独立事务中执行"**不成立** | **FAIL** |
| 4 | 五台设备、无 2004 | `devices` 5 行：2000/2001 ACTIVE、2002/2003/2005 PENDING_USER_INPUT；`/devices/2004` → **404** | PASS |
| 5 | 2000 参数 | 截断 5.2 / 垂直 3.68 / 倾角 45 / 波束 15 **FULL** → β 7.5 / 派生轴斜距 5.2043059095 且 `is_derived=1`；**5.2 原值未被覆盖** | PASS |
| 6 | 2001 参数 | 截断 5.2 / 垂直 3.6 / 倾角 NULL / 坐标已存；**未继承 2000 的 45°** | PASS |
| 7 | 2002/2003/2005 不自动填值 | 三台无参数行、无 3.68；详情页表单输入值为空 | PASS |
| 8 | 人工水底参考面 | 2000：`USER_DEFINED_ESTIMATED` 3.68 / `NOT_DETECTED`；其余台 0 行 | PASS |
| 9 | 两阶段数据集 | 2 数据集（PLANNED，起止为空未编造）+ 7 条成员（2 + 5） | PASS |
| 10 | 文件登记 | `file_registry` 21 行（2000×13 + 2001×8），合计 8,380,445,292 字节，SHA-256 齐全，状态 `ARCHIVED_REGISTERED`，原始文件未动 | PASS |
| 11 | 版本链不可变 | 实测 2000 连续两次改值：v1 5.2→`effective_to=2026-11-10`、v2 4.8→`2026-11-12`、v3 5.2→NULL；**旧行数值列未被改写**；当前指针跟随；审计 2 条 `SAVE_PARAM` | PASS |
| 12 | 设备独立性 | 改 2000 全程，2001 参数行完全未变 | PASS |
| 13 | 站位归属（任务二字面要求） | `devices` **无 `station_id` 列**；站位仅由 `device_installations.station_id` 承载，而该表 0 行且无网页录入入口 | **部分未落实** |

### 3.2 网页与交互（真实服务实测，端口 5055，数据库副本）

| # | 用例 | 预期 | 实测 | 判定 |
| --- | --- | --- | --- | --- |
| 1 | `GET /` | 200，五台 + 未知队列 | 200；出现 2000/2001/2002/2003/2005；"无 2004"仅为说明文字 | PASS |
| 2 | `GET /devices/2000` | 200，5.2/3.68/45/15/7.5/5.2043 | 200，六项数值齐全 | PASS |
| 3 | `GET /devices/2002` | 200，全 UNKNOWN | 200，7 处 UNKNOWN，表单值为空 | PASS |
| 4 | `GET /devices/2004` | 404 | 404 | PASS |
| 5 | 预览接口（2001，3.6/45°） | 5.0911688245，β7.5，截断不受派生影响 | 全部一致，`cutoff_untouched_by_derivation=true` | PASS |
| 6 | 并发冲突 | 过期版本 → 409 | 2002 先 v1 成功后，用 `expected_version=0` 再提交 → **409**，页面提示冲突 | PASS |
| 7 | 位置录入 + 回读 | 可录入、可回读 | 2005 录入 121.2140/27.9930 → 302，页面回读一致 | PASS |
| 8 | 经纬颠倒 | 拒绝并定位字段 | lon=27.99 / lat=121.21 → **400**，"纬度必填且在 [-90, 90]" | PASS |
| 9 | 空截断 / 负截断 / 零离底 / 倾角 120 / 半角 95 / 全角 200 / 方位 365 / 空来源 / 空日期 / 经度 181 | 400 | 全部 400 且提示定位到字段 | PASS |
| 10 | **截断填 `NaN`** | 400 拒绝 | **302 保存成功**；SQLite 把 NaN 落库为 **NULL**，该台静默变成"截断缺失"状态 | **FAIL** |
| 11 | **截断填 `inf`** | 400 拒绝 | **302 保存成功**；库中 `analysis_cutoff_slant_m = inf`（`typeof=real`） | **FAIL** |
| 12 | **截断填 `abc`（非数字）** | 400 并定位字段 | **HTTP 500**（`float()` 抛 ValueError 未捕获） | **FAIL** |
| 13 | **截断填 `520`（单位混用/明显越量程）** | 拒绝或明确警告 | **302 静默接受 520 m**（该量程下显系把 cm 当 m） | **FAIL** |
| 14 | **`expected_version=abc`** | 400 | **HTTP 500** | **FAIL** |

---

## 4. 缺陷清单

### 4.1 D1-1（阻断签收）K13 校验可写入 NaN / inf，硬截断存在被"关闭"的路径

- **复现**：起服务后 `POST /devices/2003/params`，`analysis_cutoff_slant_m=inf`（其余字段合法）→ 302，回读库值 `inf`；换 `NaN` → 302，库值 `NULL`。
- **根因**：`app/services/devices.py: _num()` 直接用 `float()`；`validate_param_form()` 只判 `cutoff is None` 与 `cutoff <= 0`，`nan <= 0`、`inf <= 0` 均为 False，于是放行；`float("abc")` 抛出的 ValueError 无捕获。
- **为什么是硬伤**：截断斜距是本项目的核心安全契约（08、09 K03/K04、11）。`inf` 一旦进入参数版本，S02/S03 的 `r > cutoff` 掩码将**全部为假**，界外回波会整体进入正式统计——正是 09 判 D0 的"界外数据进入正式结果"；`NaN` 落成 NULL 则让设备静默变成"无截断"，同样绕开"缺少截断的设备不能产生正式分析"。
- **与报告不符**：STAGE_S01 §10 称"K13：11 组非法输入全部 400 拒绝"，追踪矩阵称"K13 11 组非法输入 400 PASS"。实测这 11 组里**没有** 09 K13 明文要求的 `NaN`、`无穷大`、`单位混用`，只有负值/空值/越界角度。`tests/test_s01_devices.py` 的 parametrize 也确认如此（10 条 + 经纬 1 条）。
- **整改**：`_num()` 改为 `v=float(raw); if not math.isfinite(v): raise ValidationError`，非数字捕获为字段级 400；对截断增加有限上界（如 > 100 m 拒绝，或与 `devices.range_m` 齐步校验并标注"量程 UNKNOWN 未经校验"）；`expected_version` 同样包 400。补 4 条断言测试。

### 4.2 D1-2（阻断 S00 依赖交付）`requirements-lock.txt` 不可用

见 §2。583 字节单行 + BOM，pip 解析失败。

### 4.3 D1-3（阻断迁移可信度）迁移"独立事务"声明不成立

- **复现**：`14_TEMP` 内建临时库，执行 `BEGIN` → `executescript("CREATE TABLE a; INSERT…; CREATE TABLE b; …INSERT INTO nonexistent…")` → 异常后 `rollback()` → 表 `a`、`b` 与 `a` 的 1 行数据**仍在**。
- **影响**：`app/db.py` 注释与报告第 3 节都写着"每个迁移文件在独立事务中执行"。当前 0001 一次成功所以没暴露；S02 起每加一个迁移，中途失败就会留下半套表 + `schema_migrations` 无记录，重跑时 `CREATE TABLE IF NOT EXISTS` 会掩盖问题、`ALTER` 类迁移则直接卡死。直接影响 K43"升级失败不损坏已验收数据"。
- **整改**：改用 `conn.executescript` 前不开显式事务（接受单语句提交），或把脚本按 `;` 拆分逐句 `execute` 包在 `BEGIN…COMMIT` 内；并补一条"注入坏迁移 → 回滚后表集合不变"的测试。同时修正 `db.py` 注释措辞，不再声称当前不具备的原子性。

### 4.4 P2 观察项（不阻断，须登记）

| 编号 | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| P2-1 | `devices` 无 `station_id`；`device_installations` 0 行、无录入入口 | 与 S01 任务二"每台独立保存 station_id"有字面差距；K19"区分设备位置、站位和安装历史"缺站位一侧 | 在 STAGE_S01 §14 登记为未完成项；S08 前补站位录入或明确"站位由安装记录承载"的口径 |
| P2-2 | `device.html:69` 对无参数设备把 `analysis_cutoff_slant_m` 预填 `5.2` 拼进预览链接 | 点 2002/2003/2005 的"预览"会拿 2000 的 5.2 当自己值，触碰"禁止复制其他台数值"红线 | 改为空值，预览接口对空截断只回派生值、不报必填错 |
| P2-3 | `created_by` 恒为 `'web'`，`actor` 恒为 seed/web | 09 §二 要求证据记录"执行者与复核者"；本机单用户可接受，但审计链无法区分是谁改的 | S02 前定口径（本机登录名 / 显式操作人字段） |
| P2-4 | 追踪矩阵 K01 记"已实现"、K13 记"400 PASS" | K01 的"未知设备待映射队列"是导入期能力，S01 无导入；K13 见 4.1 | 矩阵改为"S01 部分 / 待 S02 复验"，K13 标 FAIL 待整改 |
| P2-5 | S01 报告未登记 4.3 与 P2-1 | 违反 K44"缺项、延期和阻断独立列示，不从分母中消失" | 补齐未完成事项表 |

---

## 5. 与阶段报告的差异汇总（报告声明 → 实测）

| 报告声明 | 实测 |
| --- | --- |
| "53 测试全过" | ✅ 53 passed，4.04s |
| "V4 16/16、CSV 21/21" | ✅ 独立重算全等 |
| "备份 30 文件" | ✅ 30/30 哈希一致 |
| "迁移每个文件在独立事务中执行" | ❌ 回滚后残留表与数据 |
| "K13 11 组非法输入全部 400 拒绝" | ❌ NaN/inf 被接受入库、abc 返回 500、520 m 静默接受 |
| "依赖锁定 36 项" | ❌ 文件损坏不可解析（实为 37 个包拼一行） |
| "12 张表" | ✅ 规范 12 张齐全（另加 2 张） |
| "4 个请求 200 + 预览 JSON" | ✅ 复现（另测 5 页 + 2004→404） |
| 未提及 station_id 缺位 | ⚠️ 未登记 |

---

## 6. 放行判断

- **S00**：九项任务实体交付真实、证据可复算，**除依赖锁文件外全部 PASS**。建议：先修锁文件，再把 §2 的 PASS 结果并入 `STAGE_S00.md` 作为验收附页。
- **S01**：**不予签收**。按 09 第五节"所有适用的强制项必须 PASS；BLOCKED、未执行、仅代码审查、仅合成数据通过不等于真实流程通过"，K13 是核心验收项（硬截断与独立参数），当前 FAIL。
- 复验口径（只需重跑这 5 条，不必重做全量）：
  1. `POST /devices/<id>/params` 传 `NaN` / `inf` / `abc` / `520` → 均 400 且提示定位字段；
  2. `expected_version=abc` → 400；
  3. 修好的 `requirements-lock.txt` → `pip install --dry-run -r` 无解析错误；
  4. 坏迁移注入 → 回滚后表集合与数据不变；
  5. `pytest` 仍全绿（预计 ≥58 项）。
- 通过后可建 S01 阶段回滚点 tag，再开 S02。S02 的距离映射审计与统一硬掩码服务必须建立在"截断值有限且已校验"的前提上，否则 4.1 会把 D0 风险带到统计层。

---

## 7. 本次验收未覆盖 / 不可验项

| 项 | 原因 |
| --- | --- |
| K04 5.199/5.200/5.201 边界 | S02/S03 范围，S01 无距离映射 |
| K14 改截断后重算与缓存失效 | 无分析 run，S03 才有重算 |
| K15 快照哈希 | `params_snapshot_json` 仅建列，无写入代码 |
| K41 W1—W3 性能 | 仅有预算草案，无真实样本基准 |
| 2002/2003/2005 真实参数、方位角、坐标系 | 用户数据未提供，保持 UNKNOWN 属正确行为 |
| 16 图 / 18 报告 / Origin 闭环 | 后续阶段 |

---

**验收人结论：S00 有条件通过（修依赖锁）；S01 退回整改（3 项必改 + 5 项登记），整改后按第 6 节口径复验再签收。**
