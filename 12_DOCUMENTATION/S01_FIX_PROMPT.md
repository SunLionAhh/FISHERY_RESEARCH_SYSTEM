# S01 整改指令（发送给编码 Agent）· 2026-11-16 验收退回

> **用途**：把下方代码块整段复制给 CodeBuddy / 编码 Agent，执行 S01 整改。
> **依据**：`10_TEST_REPORTS/stage_reports/ACCEPTANCE_S00_S01.md`（2026-11-16 独立验收：S00 有条件通过、S01 退回整改）。
> **状态**：`S01_ACCEPTANCE_FAILED_PENDING_FIX`，整改后为 `S01_FIXED_PENDING_RECHECK`。
> **边界**：本轮只整改，**不得开始 S02**，不得改动已验收的数据、参数数值与科研口径。

## 验收人已实测的事实（Agent 不必重新证明，直接修）

| 编号 | 缺陷 | 实测证据 |
| --- | --- | --- |
| D1-1 | 截断斜距可写入 `NaN`/`inf` | `POST /devices/2003/params` 传 `analysis_cutoff_slant_m=inf` → 302，库中 `inf`；传 `NaN` → 302，SQLite 落库为 `NULL`；传 `abc` → 500 |
| D1-2 | 依赖锁文件不可解析 | `requirements-lock.txt` 583 字节、0 换行、带 BOM，`pip install -r` 报 `No matching distribution found for blinker==1.9.0certifi==…` |
| D1-3 | 迁移非原子 | `BEGIN` + `executescript` 中途报错，`rollback()` 后表与已插入行仍存在 |
| P2-1 | `devices` 无 `station_id` | 表结构确认；`device_installations` 0 行 |
| P2-2 | 预览预填 2000 的 5.2 | `app/templates/device.html:69` `analysis_cutoff_slant_m=… if d.param else 5.2` |
| P2-3 | 操作者恒为 `web` | `created_by`/`actor` 默认值 |

---

## 可直接复制的指令

```text
请执行 FISHERY_RESEARCH_SYSTEM 的 S01 整改。本轮只整改，不得开始 S02。

项目根目录：C:\Users\Administrator\WorkBuddy\渔业声学监测科研分析系统\FISHERY_RESEARCH_SYSTEM
请先切换到该目录。

【必读】在进行任何修改前，完整阅读：
10_TEST_REPORTS/stage_reports/ACCEPTANCE_S00_S01.md（本次验收报告，缺陷有复现步骤）
FISHERY_FULL_PLAN_V4/09_DEVELOPER_ACCEPTANCE.md 第三节 K03/K13/K15、第五节缺陷分级
FISHERY_FULL_PLAN_V4/03_CODEX_STAGE_TASKS_FINAL.md 第四章（S01 十二项任务）
04_SOURCE_CODE/app/services/devices.py、app/db.py、app/web/routes.py、app/templates/device.html
04_SOURCE_CODE/tests/test_s01_devices.py
PROJECT_MASTER_INDEX.md「下一步」一节

【总原则】
1. 三项 D1 必改，改完必须有可复现证据；五项 P2 必须处理或如实登记，不得沉默。
2. 不得改动、不得削弱任何已通过的验收项：五台设备清单（无 2004）、2000 的 5.2 m 截断与 3.68 m 垂直参考必须原值保留、派生 5.2043059 不得覆盖 5.2、2002/2003/2005 保持 UNKNOWN 不得填造、21 个原始 CSV 与 V4 包不得改一个字节。
3. 不得为了让测试变绿而删断言、放宽断言或改测试期望值。现有 53 项必须继续全部通过，新缺陷要新增用例。
4. 不得使用破坏性 Git 命令；完成后新建提交，不 amend。阶段报告与索引同步更新。

【D1-1 修复：K13 参数校验，必须封死 NaN / inf / 非数字 / 越量程】
位置：app/services/devices.py 的 _num() 与 validate_param_form()/validate_position_form()。
改为统一的安全数值解析：
- 非数字（如 abc、空串已另判）不得抛 500，必须转为字段级 ValidationError，错误文案要指明是哪一个字段（K13 要求"拒绝非法值并定位字段"）。
- 解析后必须判 math.isfinite()：NaN、inf、-inf 一律拒绝，错误文案示例："人工分析截断斜距必须为有限数值（不得为 NaN/inf）"。
- 对 analysis_cutoff_slant_m 增加有限上界：优先取 devices.range_m；range_m 为空时用 100 m 兜底（本机量程 37.5 m，任何超过 100 m 的值不可能来自本设备）。拒绝文案必须说明"量程 UNKNOWN，按上限 100 m 临时校验"，并在阶段报告登记该阈值来源与"待用户确认量程后收紧"。
- 同一套有限性校验要覆盖：vertical_bottom_clearance_m、axis_slant_m、downward_tilt_deg、beam_angle_value_deg、heading_deg、latitude_deg、longitude_deg、position_accuracy_m。
- app/web/routes.py 的 expected_version 解析：int(request.form.get(...)) 目前遇到 abc 直接 500，改为捕获后返回 400，文案"预期版本号非法"。参数表单与位置表单两处都要改。
- 预览接口 /devices/<id>/params/preview 不得因为字段非法而整页 500，保持 400 + JSON errors。
新增测试（app/tests 下，数量不限），至少覆盖：
- analysis_cutoff_slant_m 传 NaN、inf、-inf、abc、0、-1、520、1e9 → 全部 400；
- vertical_bottom_clearance_m 传 NaN；
- expected_version 传 abc、空串 → 400；
- 断言"非法提交后 device_parameter_versions 不新增任何行"（防止静默入库）。
自检命令（必须贴出真实输出）：
.\.venv\Scripts\python.exe -m pytest 04_SOURCE_CODE\tests -q
然后起服务用 curl 逐条复现：NaN/inf/abc/520 均须 400，且库里该设备参数行数不变。

【D1-2 修复：依赖锁文件】
04_SOURCE_CODE/requirements-lock.txt 现在是单行 + BOM，pip 完全无法解析。请重新生成：
- 每行一个包，UTF-8 无 BOM，换行用 LF；
- 建议用 Python 直接写，避免 PowerShell 重定向把数组拼成单行：
  .\.venv\Scripts\python.exe -c "import subprocess,sys; open('04_SOURCE_CODE/requirements-lock.txt','w',encoding='utf-8',newline='\n').write(subprocess.run([sys.executable,'-m','pip','freeze','--all'],capture_output=True,text=True).stdout)"
- 校验一：文件行数 ≥ 30，每行匹配 ^[A-Za-z0-9_.\-]+==\S+$
- 校验二：.\.venv\Scripts\python.exe -m pip install --no-deps --dry-run -r 04_SOURCE_CODE\requirements-lock.txt 必须能正常解析（不得出现 "No matching distribution found for <一长串>"）。把两条校验输出贴进报告。
- 新增一条测试：断言锁文件行数 ≥30、无 BOM、每行格式合法。
- 顺带补一份只含运行期依赖的 requirements.txt（flask、python-dotenv、requests 即可），与 lock 文件分开，报告里说明用途。

【D1-3 修复：迁移原子性】
app/db.py 现在先 execute("BEGIN") 再 executescript()，而 executescript 会隐式提交前面的 BEGIN，导致失败后残留半套表——注释和阶段报告里"每个迁移文件在独立事务中执行"这句是不成立的，必须让实现配得上这句话。
- 迁移连接使用 isolation_level=None（autocommit），自己显式 BEGIN IMMEDIATE / COMMIT / ROLLBACK；
- 不要用 split(";")，用 sqlite3.complete_statement 逐行累积切分，保证注释、字符串里的分号不误切；
- 每个迁移文件执行完才写入 schema_migrations，失败整体回滚；
- 把 db.py 顶部注释改成与实现一致的表述（如果做不到原子，就写明实际行为，不许再声称没有的能力）。
新增测试：在 tmp 目录造一份故意失败的迁移（先 CREATE TABLE，再执行一条必错语句），断言：
- 抛异常后该迁移创建的表不存在；
- schema_migrations 未记录该版本；
- 已有表与数据未被破坏。
把该测试的 pytest 输出贴进报告。

【P2-1 站位】
S01 任务二要求每台设备独立保存 station_id，当前 devices 表没有这一列，stations 表为空、device_installations 也为空。
推荐做法：新增迁移 0002，为 devices 增加 station_id TEXT REFERENCES stations(station_id)（可空），种子数据保持 NULL，设备详情页显示"站位：未分配"。
禁止伪造站位名称或坐标。若你认为本期不该改结构，则必须在 STAGE_S01.md 的未完成事项表中登记：缺 station_id、站位由 device_installations 承载、S08 前补齐录入入口，并说明对 K19/K21 的影响。

【P2-2 预览预填】
app/templates/device.html 的预览链接对无参数设备写死 analysis_cutoff_slant_m=5.2，等于把 2000 的值借给 2002/2003/2005，违反"禁止复制其他台数值"。
改为空值；同时让预览接口容忍空截断：只回派生值与 β，analysis_cutoff_slant_m_will_be 返回 null，并在 note 里写"截断未填写"，不要因此报 400 必填错。加一条测试断言无参数设备的预览链接不含 5.2。

【P2-3 操作者】
created_by / audit_logs.actor 现在恒为 'web'/'seed'。改为写入真实操作者：取 getpass.getuser() 或环境变量 USERNAME，seed 仍写 'seed'。在报告登记：本机单用户、无登录鉴权，操作者身份属弱标识，S10 若引入多用户需替换为账号。

【P2-4 / P2-5 文档同步】
- 12_DOCUMENTATION/REQUIREMENTS_TRACEABILITY_MATRIX.md：K13 已由验收人标为 FAIL，你修复并复验通过后改为 PASS 并写出测试 ID；K01 改为"S01 部分实现（设备清单），未知设备待映射队列属导入期，S02 复验"。
- 10_TEST_REPORTS/stage_reports/STAGE_S01.md：新增"验收整改记录"一节，按 09 第二节要求逐条写：用例 ID、需求条款、执行版本/提交号、环境、输入文件及 SHA-256（无文件输入的写 N/A）、设备与参数版本、操作步骤、预期、实际、PASS/FAIL、运行时间、日志与工件位置、执行者。
- PROJECT_MASTER_INDEX.md：状态改为 S01_FIXED_PENDING_RECHECK，更新"下一步"为本轮整改摘要与复验口径。
- CHANGELOG.md：追加本轮条目。

【完成标准（缺一不签收）】
1. pytest 全绿，总数 ≥58（原 53 + 新增），贴出完整末尾输出；
2. curl 复现：NaN、inf、abc、520、expected_version=abc 全部 400，且非法提交后设备参数行数不变；
3. pip install --dry-run -r 正常解析，贴输出；
4. 坏迁移回滚测试通过，贴输出；
5. 五台设备、5.2/3.68/5.2043、2002/2003/2005 全 UNKNOWN 三项回归未被破坏，贴数据库读回值；
6. 21 个 CSV 与 V4 包零改动（git status 中不得出现 01_ORIGINAL_DATA 与 FISHERY_FULL_PLAN_V4 的变更）；
7. 上述五项 P2 逐条有处理结论或登记，不得遗漏。

完成后停止，等待复验。复验通过前不得开始 S02，尤其不得先动 S02 的距离映射与统一硬掩码——本轮 D1-1 就是那条链的上游。
```

---

## 发送时附带的会话提示（可选）

如果 Agent 试图顺手把 S02 一起做了，直接回：「只做本轮整改，S02 等复验通过。」如果它声称"测试通过所以 K13 没问题"，要求它贴出 `analysis_cutoff_slant_m=inf` 的 curl 返回码和数据库读回值——这是本次验收唯一无法用测试数量掩盖的一条。
