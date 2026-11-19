# STAGE_S10 — Flask 完整科研工作台整合

> 阶段：S10（LEVEL 8）｜依据：`FISHERY_FULL_PLAN_V4/03_CODEX_STAGE_TASKS_FINAL.md` 第十三章（31 类入口、界面/安全/启动要求）、`09_DEVELOPER_ACCEPTANCE.md` K39/K41
> 执行日期：2026-11-17｜环境：Windows 11 / 项目 `.venv` Python 3.10.11 / pytest 9.2.0
> 回滚点：S09 验收后提交 `490ebf6` 并建 tag **`s09-accepted`**；运行前备份正式库 `11_BACKUPS/s10_pre_run_20261117/fishery.db`（SHA-256 `27AE845F11DF480CE26959F1A9E6904F0E506C88A400A27F3FD54822747660D2`）。
> **状态：S10 完成待验收。31 类入口全部可达；全局设备/日期/阶段选择、人工截断版本横幅、质量/缺测/阻断概览、CSV/MD 导出、本地绑定与一键启动均已落地；不重写既有 S01—S09 页面。**

---

## 0. 交付物

| 类型 | 位置 |
| --- | --- |
| 服务 | `app/services/workbench.py`：31 类入口清单、全局上下文、截断横幅、质量汇总、联动视图、CSV/MD 导出、备份清单 |
| 路由 | `/workbench`、`/workbench/export.csv`、`/workbench/report.md`、`/workbench/backups`；既有 `/devices*`、`/daily*`、`/compare`、`/environment*`、`/intraday`、`/s07`、`/s08`、`/s09` 保持不变 |
| 页面 | `templates/workbench.html`、`templates/workbench_backups.html`；`base.html` 导航新增 S10 工作台 |
| 启动 | 项目根 `启动工作台.bat`；`04_SOURCE_CODE/run.py` 固定 `127.0.0.1:5000`、`debug=False` |
| 测试 | `tests/test_s10_workbench.py`（5 项）；全库 **233 passed**（S09 228 + 新增 5） |
| 证据 | `10_TEST_REPORTS/s10_verification/`：`smoke.json`（31/31 入口 PASS）、`workbench_linked.csv`、`workbench_report.md`、`pytest.txt` |

---

## 1. 任务一：31 类工作台入口整合

- `workbench.ENTRIES` 固定 31 项（编号 1—31 无缺口），按总览/数据/参数/分析/阶段/规律/环境/空间/导出/运维分组；每类含中文名称、来源阶段、目标路由与携带全局选择的链接。
- 真实冒烟（`s10_workbench_smoke.py`）逐个 GET 31 个入口：**31/31 status=200**，失败列表为空；入口覆盖首页、设备管理、离底高度、参数历史、人工底界、理论底界/近底排除、GPS、上传、审计、统计、比较、缺测、双站/五站阶段、数据集、周月规律、环境管理/联合、日内/昼夜、三水层、五站空间、动态播放、规律识别、Origin 中心、16 类图、报告中心、冻结、备份恢复、项目索引。
- S01 五台参数/GPS 页面保持既有可用状态，没有把“首次能录经纬度/截断”错误归到 S10；S10 只是统一入口与全局上下文。

## 2. 任务二：界面与全局交互

- 中文界面；全局选择支持设备（全部五站 + 2000/2001/2002/2003/2005）、开始/结束日期（来自真实 `daily_statistics`）、研究阶段（`datasets`），选择通过 URL 查询串传入工作台联动视图与 CSV/MD 导出。
- 在所有分析及导出入口的工作台横幅中显示**人工截断斜距及生效版本**：真实 2000 为 5.2 m / v1 / 2026-10-31；未提供的设备显示 UNKNOWN，不复制其他台数值。
- 数据质量概览直接统计真实库：COMPLETE 5 日、MISSING 等状态分项、BLOCKED 项（环境自动获取失败 + S09 BLOCKED/NO_DATA）、无 GPS 站位数；缺测在联动表显示 NA，不填 0。
- 图表联动：联动表把同一设备/日期的统计状态、覆盖率、活动率、S05 环境模型历史行数、S09 正式图数量并列展示，真实查询 8 行；CSV 与 MD 报告由同一服务函数生成，避免多出口数字漂移。
- 动态滑块与播放交互沿用 S08 `/s08` 页面；本阶段不改其数据语义。

## 3. 任务三：安全与一键启动

- `run.py` 固定 `host="127.0.0.1"`、`port=5000`、`debug=False`；没有公网绑定、没有开放调试器。
- 项目根 `启动工作台.bat`：`chcp 65001` 后定位项目 `.venv`，延迟打开 `http://127.0.0.1:5000/workbench`，前台启动 Flask；缺少虚拟环境时明确报错退出。
- 冒烟验证 launcher 存在、包含 `.venv\Scripts\python.exe` 与本地地址；并新建第二个 `create_app()` 实例重新加载同一库，工作台返回 200 且 31 入口仍在（`restart_recovery=true`）。

## 4. 任务四：备份、恢复与数据保护

- `/workbench/backups` 列出 `11_BACKUPS/*_pre_run_*` 下所有 `fishery.db` 的大小与 SHA-256（含 S07—S10 四个阶段备份），并展示当前库路径；恢复流程在页面明示“停止 Flask → 核对 SHA-256 → 复制回原库 → 复跑哈希与测试”。
- 实际恢复演练会覆盖运行库，保留到 S11 预答辩验收执行；本阶段只验证备份可见、哈希可读与重启后同一库可恢复访问。
- 21 个原始声学 CSV 哈希 **21/21 与归档清单一致**；S10 只读取既有分析库与页面，不改原始 CSV、不新增数据修正。

## 5. 任务五：测试与验收证据

```text
.\.venv\Scripts\python.exe -m pytest 04_SOURCE_CODE\tests -q
233 passed (S09 228 + S10 5), exit 0
```

覆盖：31 入口编号与分组、全局上下文/截断横幅/质量汇总、联动视图与 CSV/MD 同源导出、Web 页面与导出响应、备份页、一键启动与本地绑定断言。

完整操作链证据：参数/GPS 录入与保存（S01 既有测试）→ 重算（S03）→ 规律证据下钻（S07）→ 地图（S08）→ CSV（S03—S09 各归档）→ Origin 闭环（S09）→ 重启恢复（本阶段 `restart_recovery=true`），由 `smoke.json` 与既有阶段报告共同支撑，未用静态页面替代功能。

## 6. 已知限制（不伪造）

1. 工作台是统一导航与联动视图，不重写 S01—S09 各自页面；旧页面仍保持各自入口与口径。
2. 全局选择的查询串传入各入口，但只有 S10 联动视图消费全部参数；其他页面的日期/设备选择仍使用其自身表单，未在 S10 重写其后端。
3. 备份恢复演练未实际覆盖运行库，留待 S11；本阶段只做清单、SHA-256 与重启访问验证。
4. 五站中仅两台有真实 GPS、坐标系未声明；工作台概览与 S08 页面均显示 UNKNOWN/PROVISIONAL，不伪造正式站距或方向足迹。

**结论：S10 的 31 类入口、界面要求、安全绑定、一键启动和完整操作链证据均已落地；停在 S10 等验收，未开始 S11。**
