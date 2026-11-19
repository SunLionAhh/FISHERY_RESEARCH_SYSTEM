# STAGE_S00 — 项目检查、目录建立和备份（阶段报告）

> 阶段：S00｜依据：`FISHERY_FULL_PLAN_V4/03_CODEX_STAGE_TASKS_FINAL.md` 第三章 + `06_CODEX_START.txt`
> 执行日期：2026-11-14｜执行环境：Windows 11 专业版（NT 10.0.22621）、项目 `.venv`（Python 3.10.11 64-bit）
> 规范基准：`SPEC_BASELINE_V4`（用户 19:13/19:17 裁定，以 `FISHERY_FULL_PLAN_V4/` 整包为准；`00_PROJECT_SPEC/` 三份同名 .md 降级为历史基线只读对照）
> **状态总览：S00 九项任务全部实际执行；结论 = 待用户验收（本报告不自行宣布 PASS 进入 S01）**

---

## 1. 阶段目标

核对现有工程与资料、备份可恢复资产、建立完整需求追踪矩阵与 S00—S11 计划、输出环境与源数据清单、V4 与历史基线差异清单、未知资料清单、测试证据目录、工时与风险估计。本轮**只执行 S00，不开始 S01**。

## 2. 前置条件核验

| 前置 | 结果 |
| --- | --- |
| 可访问项目根目录 `C:\Users\Administrator\WorkBuddy\渔业声学监测科研分析系统\FISHERY_RESEARCH_SYSTEM` | PASS（全部读/校验操作在本机实际执行） |
| V4 全包 12 份必读文件完整阅读 | PASS（01/02/03/08/09/10/11/13/06/07/00 全文读取；04 总规划 167KB 全文提取并结构化，见第 4 节） |
| 路径解析规则 | 已执行：V4 文档内 `00_PROJECT_SPEC/01|02|03_*.md` 引用一律映射到 `FISHERY_FULL_PLAN_V4/` 同名文件；`00_PROJECT_SPEC/` 内同名文件仅作差异对照 |
| Git 仓库与初始回滚点 | PASS：分支 `master`，工作区 0 未提交修改；`183e469e5ff62b39adda2e2fde693995879b3e2e`（S00 开工前基线）与 `5ae88837…`（登记提交）均存在；未使用任何破坏性 Git 命令 |

## 3. 任务一/二：现有工程检查结果

| 检查项 | 实测结果 |
| --- | --- |
| 00—14 目录骨架 + FISHERY_FULL_PLAN_V4/ | 15+1 个目录全部存在 |
| 04_SOURCE_CODE | S00 前为空；本轮新增 `requirements-lock.txt` 与 `tests/test_s00_smoke.py` |
| 03_DATABASE | 空（无 SQLite 库，S01 任务） |
| Flask / 解析 / 统计程序 | **不存在**——如实登记，不存在历史代码可复用 |
| 测试文件 | 本轮新建冒烟测试（见第 7 节） |
| 图表 / 分析结果 / 冻结版本 | 无（07/06/13 目录空） |
| 依赖 | `.venv` 已存在且指向 Python 3.10.11，但科学计算依赖缺失 → 本轮补装并锁定 |
| 启动方式 | 尚无启动脚本（S10 任务） |
| 管理文件 | PROJECT_MASTER_INDEX.md / PROJECT_STRUCTURE.md / CHANGELOG.md 存在且为 V4 基准，本轮已更新 |

**未删除、未覆盖、未移动任何既有正式成果**；21 个原始 CSV 位置与内容未动。

## 4. 三份规范冲突检查（V4 内部一致性）

V4 01/02/03 的 V4 修订头部与 08 用户要求逐条对照，**未发现未裁定冲突**：

| 检查点 | 结论 |
| --- | --- |
| 设备清单 | 01/02/03/08/09/10/11 一致为 2000、2001、2002、2003、2005，无 2004 |
| 5.2 m 硬截断与 3.68 m 分离、5.2043 m 仅参考 | 01 §5.1/§6.2、02 §9.6、03 S01/S02/S07、08 §2、09 K03/K04、10 示例 JSON、11 §1 一致 |
| 15° 全/半角 | V4 正文一致标注 UNKNOWN；11 提供全角 15° 条件算例与 45°/90° 两组数值基准。**用户 2026-11-15 确认 15° 为全角（β=7.5°）** |
| 截断生效时点 | 01/02/03/08/09 一致：S01 配置、S02 掩码、S03 起统计全截断 |
| 31 入口 vs 29 界面能力 | 04 第 5.2 节明确为不同口径（31 入口覆盖 29 项界面能力），非冲突，无须裁定 |
| 执行指南 §2「发生冲突时主规范最高」 | 与用户效力裁定（08 同主题最高）叠加执行，无冲突 |

**V4 与历史基线差异清单**：已由 `12_DOCUMENTATION/SPEC_VERSION_MATRIX.md` D1—D12 完整登记（设备清单、5.2 m 硬截断、深度字段分离、波束角全/半角、S01 参数网页前置、几何规范升级、45 条验收、启动话术、正文体量、入口口径、E 盘路径失效、文件规模历史抽样）。本轮**独立复核确认 D1—D12 与 V4 正文一致，未发现新增差异**。

## 5. 任务三/四：目录与原始数据子目录检查

按 V4 03 第三章任务三/四逐目录核验：

- `00_PROJECT_SPEC/` … `14_TEMP/` 共 15 个一级目录：全部存在。
- `01_ORIGINAL_DATA/FISHFINDER/`：**2000（13 文件）、2001（8 文件）、2002（空）、2003（空）、2005（空）**；`2004` 目录不存在（符合用户裁定）；另有 `README.md`（V4 设备清单与只读保护声明）。
- `01_ORIGINAL_DATA/ENVIRONMENT/`：WATER_TEMPERATURE（空）、TIDE（潮汐.zip，11 张 PNG 截图）、WIND（风速 xlsx）。
- `01_ORIGINAL_DATA/GPS/`、`MANUFACTURER_DOCS/`：空。
- 规范文件未覆盖：`FISHERY_FULL_PLAN_V4/` 17 个文件原位未动（16/16 SHA-256 复核一致，见第 6 节）。

## 6. 任务五：真实资料检查（全量实测，未照抄清单）

### 6.1 原始鱼探 CSV（21 个，第一阶段双站完整导出）

本轮用 `12_DOCUMENTATION/s00_verify_integrity.py` 在 `.venv` 目标解释器内**独立重算**全部 21 个文件 SHA-256 与字节数，并与 `RAW_CSV_PRECHECK_INVENTORY_CURRENT.csv` 逐条比对：

| 项 | 实测值 |
| --- | --- |
| 文件数 | 21（2000：13 个 10-31—11-12；2001：8 个 10-31—11-07） |
| 合计字节 | **8,380,445,292**（逐文件重算求和，与清单一致） |
| SHA-256 | **21/21 复核 PASS**（逐文件独立重算，非照抄） |
| 编码/格式 | 8 个 UTF-8/BOM/LF/ISO 时间；13 个 GBK/无BOM/CRLF/斜杠时间；同设备不同日期混用 |
| 信号点数 | 去掉末尾空串后统一 1000 点（1001 切分项含末尾空串，非缺陷） |
| 证据 | `10_TEST_REPORTS/s00_verification/RAW_CSV_SHA256_RECHECK.csv`（21 行，逐文件 PASS） |

**归档 ≠ 导入**：未生成 `import_batch_id`、未入数据库、未做 S02 审计（同秒多记录、断档、信号值范围、水深 0 值、设备可比性、底界审计全部未做）。双站同期窗口 2026-10-31—11-07 为**待 S02 按文件内真实时间戳复核的口径**；2000 的 11-08—11-12 为单站延伸，不计入双站同期样本量。

### 6.2 V4 规范包完整性

`MANIFEST_SHA256.json` 16 条记录逐文件独立重算大小与 SHA-256：**16/16 PASS**（`10_TEST_REPORTS/s00_verification/V4_PACKAGE_VERIFY.csv`）。

### 6.3 其他资料可用性

| 资料 | 位置 | 状态 |
| --- | --- | --- |
| 风速 xlsx | `01_ORIGINAL_DATA/ENVIRONMENT/WIND/` | 288 行 / 12 天；**Open-Meteo 数值模型数据，非现场实测**，含 120 条未来预报；已有格式预处理 CSV（非正式导入批次） |
| 潮汐 zip | `01_ORIGINAL_DATA/ENVIRONMENT/TIDE/` | 11 张 PNG 曲线截图（10-31—11-10，单位 cm）；**无逐时数值表、无基准面标注，不满足入库条件**；未做图像估读 |
| 水温 | `ENVIRONMENT/WATER_TEMPERATURE/` | **缺**（目录空） |
| 五站 GPS | `01_ORIGINAL_DATA/GPS/` | **缺**（目录空；坐标未提供，保持 UNKNOWN） |
| 厂家资料 | `MANUFACTURER_DOCS/` | **缺**（目录空） |
| 历史风速/潮汐原始来源 SHA-256 | `ENVIRONMENT_PRECHECK.md` 第 5 节 | 已登记（本轮未重算，属既有记录） |
| `E:\鱼探仪\新软件\hydx\deeperfiles` | — | **路径不存在**（实测 `Test-Path` = False）；实际只读来源为项目内归档位置 |

## 7. 任务六：环境实测（目标解释器 `.venv` 内复测）

| 检查项 | 规范要求 | 本轮实测（真实命令输出） | 判定 |
| --- | --- | --- | --- |
| 操作系统 | Windows 11 | Microsoft Windows 11 专业版，NT 10.0.22621.0 | 符合 |
| Python 3.10 | 3.10 具体版本/位数/路径 | `3.10.11 (tags/v3.10.11:7d4cc5a) [MSC v.1929 64 bit (AMD64)]`；解释器 `C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe`（系统级），项目解释器 `.venv\Scripts\python.exe`（同版本） | 符合（用户 19:17 已批准；本机已装 3.10.11，本轮核实并复用） |
| `.venv` 独立虚拟环境 | 必须建立 | 存在，`pyvenv.cfg` version=3.10.11、include-system-site-packages=false | 符合 |
| 依赖 | Flask/NumPy/Pandas/Matplotlib/Pytest | 本轮在 `.venv` 内安装并**实测导入**：flask 3.1.3、numpy 2.2.6、pandas 2.3.3、matplotlib 3.10.9、pytest 9.2.0、openpyxl 3.1.5；锁定文件 `04_SOURCE_CODE/requirements-lock.txt`（36 项） | 符合 |
| PyCharm | 2024.1 | 实装 **PyCharm 2025.2.1.1** | **版本不符，如实登记**；不擅改规范 |
| OriginPro | 规范写 2026b Learning Edition | **用户 2026-11-15 裁定改用已装的 Origin2027**（实测：注册表 `Origin2027` 版本 10.40.131，安装路径 `C:\Program Files\OriginLab\Origin2027\`；COM ProgID `Origin.ApplicationSI`、`Origin.Application` 已注册，`OriginPro.ApplicationSI` 未注册）。Learning Edition 属性与 12 窗口上限待 S09 本机实测 | 已安装（版本与规范不同，属用户裁定，S09 实测 COM 桥接） |
| Git | 安全回滚点 | 仓库已初始化，`master` 分支干净；初始回滚点已核验 | 符合 |
| 硬件 | S00 须登记 | CPU AMD Ryzen 7 9700X（8 核）；内存 31.2 GB；磁盘空闲 C: 771.5 GB / E: 443.0 GB / F: 3,595.9 GB | 已登记（供 W1—W3 基准） |

## 8. 任务七：备份与回滚点

| 项 | 位置 | 内容 |
| --- | --- | --- |
| 资产备份 | `11_BACKUPS/S00_baseline_backup_20261114/` | 30 个可恢复资产（管理文件、配色规格、文档与脚本、CSV 清单、V4 清单/示例、测试与依赖锁），含 `BACKUP_MANIFEST.csv`（逐文件 SHA-256）与 `BACKUP_README.md`（恢复方法） |
| 8.38 GB 原始 CSV | 不做物理备份 | 只读保护；完整性由本轮 21/21 SHA-256 复核 + `.gitignore` 排除规则 + `RAW_CSV_ARCHIVE_MANIFEST.csv` 覆盖；恢复策略为「登记 + 哈希校验」 |
| Git 回滚点 | 初始 `183e469e5ff62b39adda2e2fde693995879b3e2e`；本轮新增 S00 成果提交（提交号见第 12 节） | 未清空历史、未使用破坏性命令 |
| 阶段回滚点 | **按用户要求在 S00 验收通过后另建**（tag 形式），本轮不提前创建 | 待验收 |

## 9. 性能预算拟定（09 第四节要求 S00 登记，待 S02 真实样本基准后冻结）

| 项 | 拟定值（待冻结） | 依据 |
| --- | --- | --- |
| W1 日常交互 | 任务提交 P95 ≤2 s；预计算日统计热查询 P95 ≤3 s；图表显示 P95 ≤5 s | 09 W1 |
| W2 大文件导入 | 流式处理；单文件峰值内存 ≤2 GB；登记 MB/s、行/s、总耗时 | 09 W2 + 04 L1706 |
| W3 长期对比回放 | 5 站×90 天聚合表 P95 ≤5 s；分页/抽稀规则明确 | 09 W3 |
| 磁盘粗估 | 五台约 2 GB/日；60 日约 120 GB、90 日约 180 GB（不含副本/索引/备份） | 04 L1710 |
| 本机容量核验 | C/E/F 空闲合计约 4.8 TB，可容纳 | 本轮实测 |

## 10. 需求追踪矩阵与开发计划（S00 交付物）

- `12_DOCUMENTATION/REQUIREMENTS_TRACEABILITY_MATRIX.md`：24 章 / 36 交付 / 31 入口 / 18 报告 / 16 图 / 45 条 K / GEO-01—12 逐项登记，字段含 requirement 类别、阶段、实现位置（待补）、测试 ID、状态；当前除 S00 相关 3 项外全部「未实施」，如实反映系统尚未开发。
- `12_DOCUMENTATION/DEV_PLAN_S00_S11.md`：12 阶段计划（V4 04 人日参考 57—89）、关键路径、每阶段固定流程、V4 硬契约落位检查表（防推迟）、R1—R10 风险登记。
- 测试证据目录：`10_TEST_REPORTS/s00_verification/`（本轮新建，2 份校验 CSV）。

## 11. 工时与风险估计

- 工期：按 V4 04 参考 **57—89 工程人日**；V4 增项约 +7—12 人日；2026-11-14 → 2027-01-20 约 67 日历日，单人完成全部系统与长期验证存在时间压力，风险已在 DEV_PLAN 登记。
- 主要风险 R1—R10（见 DEV_PLAN 第 5 节）：OriginPro 2027 已装但 COM 桥接与 Learning 属性待 S09 实测、四台（2001/2002/2003/2005）参数与全部坐标/方位角未知（几何正式结论 BLOCKED；15° 全角已确认，β=7.5°）、潮汐无数值表、风速非实测、双编码格式、采样语义未核实、单站延伸段、PyCharm 版本差异、五站同步时间未定、性能预算待冻结。

## 12. 修改文件与实际运行记录

**本轮修改/新增文件**：

| 文件 | 动作 |
| --- | --- |
| `04_SOURCE_CODE/requirements-lock.txt` | 新增（pip freeze，36 项锁定） |
| `04_SOURCE_CODE/tests/test_s00_smoke.py` | 新增（S00 冒烟测试，29 用例） |
| `12_DOCUMENTATION/s00_verify_integrity.py` | 新增（V4 包 + 21 CSV 全量校验，可复现） |
| `12_DOCUMENTATION/s00_backup_assets.py` | 新增（备份脚本，可复现） |
| `12_DOCUMENTATION/REQUIREMENTS_TRACEABILITY_MATRIX.md` | 新增 |
| `12_DOCUMENTATION/DEV_PLAN_S00_S11.md` | 新增 |
| `10_TEST_REPORTS/s00_verification/V4_PACKAGE_VERIFY.csv` | 新增（16 行 PASS） |
| `10_TEST_REPORTS/s00_verification/RAW_CSV_SHA256_RECHECK.csv` | 新增（21 行 PASS） |
| `11_BACKUPS/S00_baseline_backup_20261114/` | 新增（30 文件 + 清单 + README） |
| `PROJECT_MASTER_INDEX.md` / `PROJECT_STRUCTURE.md` / `CHANGELOG.md` | 更新（S00 状态） |

**实际运行命令（节选，全部真实执行）**：

```text
git log --oneline -5；git status --porcelain            # 回滚点核验，工作区干净
.\.venv\Scripts\python.exe -V                            # 3.10.11
.\.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple flask numpy pandas matplotlib pytest openpyxl python-dotenv requests
.\.venv\Scripts\python.exe -c "import flask,numpy,pandas,matplotlib,pytest,openpyxl; ..."   # 版本打印见第 7 节
.\.venv\Scripts\python.exe -m pip freeze > 04_SOURCE_CODE\requirements-lock.txt
.\.venv\Scripts\python.exe 12_DOCUMENTATION\s00_verify_integrity.py   # V4 16/16、CSV 21/21 PASS
.\.venv\Scripts\python.exe -m pytest 04_SOURCE_CODE\tests\test_s00_smoke.py -v       # 29 passed
.\.venv\Scripts\python.exe 12_DOCUMENTATION\check_figure_colors.py    # 色板外 0，PASS
.\.venv\Scripts\python.exe 12_DOCUMENTATION\s00_backup_assets.py      # 30 文件备份
[System.Environment]::OSVersionVersionString 等 Win32 查询                # 环境实测见第 7 节
```

## 13. 自动化测试结果

`python -m pytest 04_SOURCE_CODE\tests\test_s00_smoke.py -v` → **29 passed（0 failed / 0 skip / 0 blocked）**，覆盖：目标解释器 3.10、核心依赖导入、16 目录骨架、五设备目录且无 2004、环境/GPS/厂家子目录、21 CSV 清单与现行文件存在性、V4 包 16/16、原始 CSV 21/21、V4 权威文件、示例配置五台隔离（2000=5.2/3.68，其余四台 null、坐标 null）、S00 阶段无冒充实现代码。

**配色校验**（FIGURE_COLOR_SPEC_V1）：色板 17+9=26 色一致 PASS、参考图 3 张 SHA-256 PASS、生成物扫描 `DEMO_PROTOTYPE.html` 455 处色值 / 25 唯一色 / **色板外 0 种 → PASS**。

## 14. 独立数值复算

- V4 包 16 文件：大小与 SHA-256 全部与 `MANIFEST_SHA256.json` 一致。
- 21 个原始 CSV：合计 8,380,445,292 字节与逐文件 SHA-256 全部与现行清单一致（独立重算）。
- 2000 号理论参考值复核：3.68/sin(45°) = 5.2043059… m——仅作参考登记，**不覆盖 5.2 m**；5.199/5.200/5.201 边界契约已在 V4 13 核对，正式断言测试留待 S02/K04。

## 15. 未知项与缺失资料清单（不得编造）

1. ~~15° 波束角全角/半角未确认~~ **已确认：用户 2026-11-15 裁定 15° 为全角（FULL），内部半角 β=7.5°**；S01 按台录入 `beam_angle_kind=FULL`。
2. **用户 2026-11-15 已提供**：2000 经纬度（121.2117505073547, 27.99346353124773）；2001 经纬度（121.2130272388458, 27.99260143251764）+ 截断 5.2 m + 离底 3.6 m。**仍 UNKNOWN**：2002/2003/2005 全部参数与坐标、两台坐标系与定位精度、两台方位角、2001 倾角、探头入水深度 → 禁止复制其他台数值、禁止默认 (0,0) 或北向；登记见 `12_DOCUMENTATION/USER_PROVIDED_PARAMETERS.md`（待 S01 网页录入生效）。
3. 五站正式同步观测开始时间未定 → 第一阶段正式截止时间未知。
4. 双站同期窗口 10-31—11-07 须由 S02 按文件内真实时间戳复核。
5. 水温数值资料、潮汐逐时表与潮位基准面、实测风速、五站 GPS、五台安装参数、厂家资料均缺。
6. 原始信号采样点/区间语义未核实 → 正式距离截断分析在 S02 保存映射证据前 BLOCKED。
7. OriginPro 未安装 → S09 相关验收项（K36/K37、GEO 相关 Origin 闭环）BLOCKED。

## 16. 未完成事项 / 阻断

| 项 | 状态 |
| --- | --- |
| S02 全量数据审计（8 项产物） | 未开始（S02 任务，非 S00 范围） |
| SQLite 数据库与迁移框架 | 未开始（S01） |
| OriginPro 2027 COM 桥接实测（含 Learning 属性与 12 窗口上限） | 待 S09 实测（2026-11-15 已安装 Origin2027 10.40.131，ProgID 已注册） |
| W1—W3 真实样本基准 | 待验证（S02 起用真实文件测量后冻结预算） |
| 阶段回滚点 tag | 待 S00 验收通过后创建（用户明确要求） |
| PyCharm 2024.1 | 差异已登记，不阻塞开发 |

## 17. S01 前置条件

1. S00 报告经用户验收（本轮停止点）。
2. 用户在网页/S01 表单可提供 2001/2002/2003/2005 参数与坐标的，届时逐台填写；仍缺则保持 UNKNOWN 并允许 BLOCKED 状态——不阻塞 S01 数据库与表单开发。
3. OriginPro 安装非 S01 前置（S09 才需要），建议尽早办理。
4. `.venv`（3.10.11）与依赖锁已就绪，S01 直接复用。

## 18. Git 回滚点

- 初始安全回滚点：`183e469e5ff62b39adda2e2fde693995879b3e2e`（已核验存在，未改动）。
- 本轮 S00 成果提交：见提交记录（提交后以 `git log` 为准，登记于 CHANGELOG）。
- 阶段回滚点：S00 验收通过后另建 tag，不使用任何破坏性命令。

---

**结论：S00 九项任务全部实际执行并有证据工件；系统本体（数据库/网页/解析/统计）尚未开发，不宣称任何功能完成。本报告提交用户验收；验收通过前不开始 S01。**
