# STAGE_S11 — 最终系统与预答辩验收

> 阶段：S11（LEVEL 8）｜依据：`FISHERY_FULL_PLAN_V4/03_CODEX_STAGE_TASKS_FINAL.md` 第十四章（十四项验收与最终报告要求）
> 执行日期：2026-11-17｜环境：Windows 11 / 项目 `.venv` Python 3.10.11 / pytest 9.2.0 / OriginPro 2027 10.400131
> 回滚点：S10 验收后提交 `7ec58f6` 并建 tag **`s10-accepted`**；运行前备份正式库 `11_BACKUPS/s11_pre_run_20261117/fishery.db`（SHA-256 `27AE845F11DF480CE26959F1A9E6904F0E506C88A400A27F3FD54822747660D2`）。
> **状态：S11 已最终验收并由用户签收（2026-11-17）。13/13 验收章节 PASS；238 测试全过；PRE_DEFENSE 数据集 FROZEN；开发到此停止，不再进入新阶段。**

---

## 1. 功能完成情况

| 模块 | 最终状态 |
| --- | --- |
| S01—S10 | 全部已签收（tag `s00-accepted`—`s10-accepted`）；本阶段只做回归与交付整理，不重写既有功能 |
| S11 验收服务 | `app/services/s11_acceptance.py`：14 章归并为 13 组自动验收、论文包、PRE_DEFENSE 冻结、离线测试、恢复演练 |
| S11 入口 | `scripts/s11_final.py` 一次生成 `final_acceptance.json` 与论文/冻结证据 |
| 论文交付 | `12_DOCUMENTATION/PAPER_EVIDENCE/` 六个文件：第三/四/五章数据包、方法说明、数据质量报告、预答辩索引 |
| 冻结 | 新增 `PRE_DEFENSE` 数据集，成员 2000/2001，状态 FROZEN，v2，版本快照留痕 |

## 2. 测试结果

```text
.\.venv\Scripts\python.exe -m pytest 04_SOURCE_CODE\tests -q
238 passed in 29.82s (S10 233 + S11 5)
```

S11 新增 5 项测试：最终验收证据完整性、真实库 13 章节回归、论文交付文件、PRE_DEFENSE 冻结与恢复演练、离线核心功能。全库累计 238 项通过，未跳过、未 xfail。

## 3. 真实数据验证（13/13 章节）

| 章节 | 结果 | 关键证据 |
| --- | --- | --- |
| 一 真实数据 | PASS | 21/21 原始 CSV 哈希一致；2000/2001 真实导入 |
| 二 第一阶段双站 | PASS | 仅 2000/2001 成员；实际边界 2026-10-31—11-03；FROZEN v5，不固定 14/18/19/30 天 |
| 三 第二阶段五站 | PASS | 五台成员已登记；正式同步时间 NULL、状态 PLANNED，不冒充五站数据 |
| 四 数据重叠 | PASS | 两阶段数据集独立；无重复 `relative_path`；原始文件不重复复制 |
| 五 每日增量上传 | PASS | 缺测/补传统计留痕；任意比较引擎与 run 存在 |
| 六 设备参数 | PASS | 五台独立记录；2000 截断 5.2 m、15° FULL 已确认 |
| 七 2000 人工底界 | PASS | 3.68 m 人工参考面；理论 5.204306 m 仅参考，5.2 m 硬截断不覆盖 |
| 八 环境数据 | PASS | 风速真实导入；自动获取失败 BLOCKED；水温代理不冒充独立证据 |
| 九 时间和空间 | PASS | S06 15 分钟格、S07 三水层、S08 站距/动画导出非空 |
| 十 规律识别 | PASS | S07 规律版本与 L0—L3 等级留痕，真实结果 L1，无越级 |
| 十一 Origin | PASS | COM/绘图/OPJU/重开/PNG-PDF-SVG 闭环任务均 OK |
| 十二 备份和离线 | PASS | 阶段备份 SHA-256 可见；禁用 socket 后 CSV 解析与工作台入口仍可用；恢复到隔离路径 PASS |
| 十三 论文交付 | PASS | 六个论文交付文件存在；PRE_DEFENSE FROZEN |

完整逐项 JSON：`10_TEST_REPORTS/s11_verification/final_acceptance.json`。无失败章节。

## 4. 未通过项目

无。13 组自动验收全部 PASS，238 项测试无失败。

## 5. BLOCKED / 未验证项目（如实保留）

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 五站正式同步数据 | BLOCKED（待数据） | 五台仅登记成员，正式同步时间 NULL；第四章数据包明确不能冒充五站结论 |
| 2002/2003/2005 GPS、朝向、参数 | UNKNOWN | 不复制 2000/2001 数值，不默认 (0,0) 或北向 |
| 2000/2001 坐标系与朝向 | UNKNOWN | 站距只给 PROVISIONAL 示意，方向足迹未画 |
| 水温独立观测、潮汐逐时值、风向列 | BLOCKED | 水温仅派生代理，潮汐截图不估读，风向缺列 |
| `originpro` Python 包兼容 | BLOCKED | 未安装；自动桥接通过 PowerShell COM，不冒充 Python 包 PASS |
| Origin 正式出图 | BLOCKED（授权） | 本机试用版导出含 demo 水印；正式图由 MATPLOTLIB 同源导出且色板外 0 |
| Learning Edition 12 窗口上限 | UNVERIFIED | Edition 状态未确认；仅实测 10 窗口任务 PASS |
| 真实浏览器点击全流程 | UNVERIFIED | S10 用 Flask test client 完成 31/31 入口与重启恢复；S11 未启动外部浏览器逐点击 |
| W1/W2/W3 性能负载 | UNVERIFIED | S00 预算草案存在，未做真实压力测试 |
| 覆盖运行库的破坏性恢复演练 | BLOCKED（安全） | 本阶段恢复到隔离路径并核对 SHA/完整性/记录数；运行库哈希未变，破坏性演练留用户授权后执行 |

## 6. 风险

1. 五站数据不到位是第四章与五站阶段结论的最大外部依赖；系统只能保持 PLANNED 与 BLOCKED，不能以双站数据替代。
2. 坐标系/朝向/底界确认不足会影响覆盖重叠、方向足迹和底界相关解释；所有相关结果已标 UNKNOWN/PROVISIONAL。
3. Origin 试用授权与 `originpro` 包缺失使 Python 包闭环和正式 Origin 出图不可声称通过；已有独立 COM Worker 与 MATPLOTLIB 正式图作为可控替代。
4. 备份恢复若覆盖运行库会改变当前状态；S11 采用隔离路径演练，保护了运行库。
5. 离线测试在进程内禁用 `socket.connect`，证明核心路径不依赖外网；但未模拟完整系统断网重启。

## 7. 备份恢复结果

- S11 运行前备份：`11_BACKUPS/s11_pre_run_20261117/fishery.db`，SHA-256 `27AE845F…47660D2`。
- 恢复演练：从 `s10_pre_run_20261117/fishery.db` 复制到 `10_TEST_REPORTS/s11_verification/restore_drill/restored_fishery.db`；源/恢复副本哈希一致，`PRAGMA integrity_check=ok`，devices=5、file_registry>0，PASS。
- 运行库 `03_DATABASE/fishery.db` 哈希保持不变，没有覆盖生产数据；`/workbench/backups` 页面可查看全部阶段备份与 SHA-256。

## 8. 最终文件目录（关键）

```text
03_DATABASE/fishery.db                     正式数据库（PRE_DEFENSE FROZEN）
04_SOURCE_CODE/app/                        Web 路由、服务、模板、11 个迁移
04_SOURCE_CODE/scripts/                    各阶段 CLI 与 Origin Worker
10_TEST_REPORTS/stage_reports/              STAGE_S00—STAGE_S11.md
10_TEST_REPORTS/s00—s11_verification/       各阶段原始证据
11_BACKUPS/s00—s11_pre_run_*/fishery.db     各阶段运行前备份
12_DOCUMENTATION/PAPER_EVIDENCE/            论文第三/四/五章与方法质量包
07_FIGURES/s09/                             正式 PNG/PDF/SVG + 动画 + Origin 留痕
启动工作台.bat                              Windows 一键启动（127.0.0.1:5000）
```

## 9. 论文交付物

- `CHAPTER03_DUAL_STATION.md`：第一阶段双站实际边界、成员、冻结版本与证据路径。
- `CHAPTER04_FIVE_STATION.md`：五站阶段框架与 BLOCKED 说明，不冒充五站数据。
- `CHAPTER05_ENVIRONMENT.md`：风速真实结果、环境 BLOCKED 项、规律 L1 结论。
- `METHODS.md`：硬掩码、5.2 m 截断、事件率分母、相关口径与不推断因果原则。
- `DATA_QUALITY.md`：21 CSV 哈希、质量/缺测、Origin 水印与正式图隔离。
- `PRE_DEFENSE.md`：阶段报告、图表、统计表和 PRE_DEFENSE 冻结索引。

## 10. 用户操作说明

1. 双击项目根 `启动工作台.bat`；脚本仅启动 `127.0.0.1:5000`，浏览器自动打开 `/workbench`。
2. 在 `/workbench` 选择设备、日期、研究阶段；查看人工截断版本、质量/缺测/阻断概览与联动明细；可导出联动 CSV 和报告 MD。
3. 需要录入或修改参数/GPS 时进入“设备管理”，保存后历史版本保留；缺值留空即 UNKNOWN。
4. 需要重算或分析时分别进入每日统计、任意比较、环境、日内、S07—S09 页面；所有结果都有 run/版本与证据归档。
5. 备份与恢复：在 `/workbench/backups` 核对 SHA-256；真正覆盖运行库前需停止 Flask、另做当前库备份并取得用户授权。
6. 最终验收后请确认是否接受 S11；系统停在最终验收状态，不再自动进入后续阶段。

**结论：S11 的 14 项最终验收要求均有代码、真实数据、报告或明确 BLOCKED 说明；13/13 自动章节 PASS、238 测试 PASS、PRE_DEFENSE FROZEN。用户已最终验收并签收（tag `s11-accepted`），开发到此停止。**
