# STAGE_S09 — OriginPro 桥接、16 类科研图与动态导出

> 阶段：S09（LEVEL 8）｜依据：`FISHERY_FULL_PLAN_V4/03_CODEX_STAGE_TASKS_FINAL.md` 第十二章（任务一至六）、`01_MASTER_SPEC_FINAL.md` 第十八/十九章、`09_DEVELOPER_ACCEPTANCE.md` K35—K37
> 执行日期：2026-11-17｜环境：Windows 11 / 项目 `.venv` Python 3.10.11 / pytest 9.2.0 / OriginPro 2027（10.400131）
> 回滚点：S08 验收后提交 `80bf877` 并建 tag **`s08-accepted`**；运行前备份正式库 `11_BACKUPS/s09_pre_run_20261117/fishery.db`（SHA-256 `BF54D20464322FE360EFC947AFA95696FEBC95299D3C4ED965BC04F83B2E98D3`）。
> **状态：S09 完成待验收。Origin COM 自动桥接闭环 PASS；本机为试用授权，导出图带 demo 水印，正式科研图改由 MATPLOTLIB 同源导出；`originpro`/`pywin32` Python 包未安装，Python 包兼容性不冒充 PASS。**

---

## 0. 交付物

| 类型 | 位置 |
| --- | --- |
| 迁移 | `app/migrations/0011_s09_figures.sql`：`figure_registry`、`figure_exports`、`origin_tasks`、`animation_exports` |
| 图注册/出图 | `app/services/s09_figures.py`：16 类固定清单、数据对账、源 CSV、PNG/PDF/SVG、单位/指标/质量说明 |
| 动画 | `app/services/s09_animation.py`：从 S08 `dynamic_frames.csv` 导出 PNG 序列/GIF/MP4/PDF，无轨迹无插值 |
| Origin 桥接 | `app/services/origin_bridge.py` + `scripts/origin_worker.ps1`：任务包、独立 PowerShell COM Worker、OPJU 保存/重开/导出 |
| Web/CLI | `/s09` 页面（仅入队不阻塞请求）；`scripts/s09_pipeline.py`（probe/figures/animation/origin/report） |
| 测试 | `tests/test_s09_figures.py`（5 项）；全库 **228 passed**（S08 223 + 新增 5） |
| 证据 | `10_TEST_REPORTS/s09_verification/`、`07_FIGURES/s09/`（`figure_manifest.csv`、图 CSV/PNG/PDF/SVG、动画、Origin 任务包与导出） |

---

## 1. 任务一：Origin 环境实测（不假设接口可用）

| 项目 | 实测结果 |
| --- | --- |
| 安装 | `C:\Program Files\OriginLab\Origin2027\Origin64.exe`，FileVersion 10.4.0 / ProductVersion 10.4 |
| COM | `New-Object -ComObject Origin.Application` 首次因首次运行用户目录/许可对话框报 `0x80080005`；完成首次运行设置后 **COM_OK**，`Evaluate('system.version')=10.400131` |
| 外部 Python 连接 | `originpro` 未安装、`pywin32` 未安装；采用 PowerShell COM Worker 作为外部连接，**不声称 originpro 包兼容 PASS** |
| 许可 | UI 实测为试用模式，提示剩余 3 天；导出图含 `demo` 水印（OriginLab 官方说明试用版水印无法通过设置去除） |
| Learning Edition | 注册表/COM 均无法确认 Edition 状态，标 `UNCONFIRMED`；12 窗口上限不能声称已按 Learning Edition 实测 |

证据：`origin_env_probe.txt`、`probe.json`、首次运行与许可对话框截图。

## 2. 任务二：Origin 桥接闭环

- 任务包 JSON 记录 `task_id`、图 ID、源 CSV、导出格式、输出目录；Worker 独立 Windows PowerShell 进程串行执行，Flask 只入队（后台线程启动子进程，请求立即返回）。
- 每图流程：`newbook` → `FindWorksheet('')` → `Worksheet.SetData()` 写入由 CSV 解析的二维数组 → `plotxy` → 轴题 → `expGraph` PNG/PDF/SVG → `Save(opju)` → `Exit` → 新 COM 实例 `Load(opju)` → `FindWorksheet('[F09_01]Sheet1')` 验证重开。
- 真实闭环：任务 `ORIGIN-20261117223449` **status=OK**，3 图 × 3 格式共 9 个导出文件，`reopen_check=PASS:[F09_01]Sheet1`，OPJU 63,921 bytes；日志逐项记录导出 True。任务 `ORIGIN-20261117224750808941` 10 图 PNG，`status=OK`、`reopen_check=PASS`、10 个导出文件。
- Origin 的 `impCSV` X-Function 在本机返回 False；改为 Worker 用 PowerShell `Import-Csv` 解析后经 COM `SetData` 写入，仍以 CSV 为唯一源表，且不把失败命令伪装为成功。`expGraph` 必须用 `path:=目录 filename:=文件名`，仅给完整路径的写法未生成文件。
- Origin 导出图带试用水印，且 SVG 配色扫描仍有色板外 `#00FFFF/#515151`；因此 **Origin 导出只作桥接闭环证据，不作正式科研图**。正式图由 `s09_figures.py` 从同一 CSV 用 MATPLOTLIB 导出。

## 3. 任务三：窗口限制

- 设计目标不超过 10 个可访问窗口；真实例在单个 OPJU 中创建 10 个工作簿+图形任务成功，OPJU 208,150 bytes，重开核对 PASS，未触发 12 窗口上限。
- 因许可状态不是已确认的 Learning Edition，且试用版弹出许可/水印限制，**12 窗口硬上限没有合法实测**，按 K37 记 `BLOCKED/UNVERIFIED`，不以 10 窗口通过代替 12 窗口实测。

## 4. 任务四：16 类科研图

- 固定 16 类清单（P0 5 类、P1 5 类、P2 6 类），每类登记 `figure_id`、`run_id`、`dataset_id`、源 CSV、图注、单位、指标定义、质量说明、数据条件与实际绘图引擎。
- 真实结果：**12 类有数据**、4 类无数据/阻断：

| ID | 类别 | 状态 | 依据 |
| --- | --- | --- | --- |
| F09-05 | 原始回波剖面和底界 | BLOCKED | 原始 37.5 m 数组未入 S09 数据表；人工底界 `NOT_DETECTED` |
| F09-09 | 峰值时段和持续性 | NO_DATA | S06 `result_json` 结构在本解析路径未检出峰谷条目，不伪造时段 |
| F09-10 | 历史滚动基线 | NO_DATA | S04 结果 JSON 无可直接映射的滚动基线条目 |
| F09-11 | 任意 N 天阶段比较 | NO_DATA | S04 结果 JSON 无可直接映射的阶段比较条目 |

- 12 个有数据类别均生成 `.csv`、`.png`、`.pdf`、`.svg`；正式图配色严格取自 `FIGURE_COLOR_SPEC_V1`。`check_figure_colors.py` 对 Python 源与正式 SVG 扫描结果 **色板外 0**，参考图 SHA 3/3 PASS；Origin SVG 因试用水印不满足配色规格，已明确隔离。
- 图例与实例：`F09-01` 覆盖率（5 个 S03 统计日，两台设备）、`F09-02` 双日 24 小时曲线、`F09-03/13` 15 分钟/2 小时格、`F09-04` 三水层代理深度、`F09-06` 两站真实坐标、`F09-07` 环境数值序列、`F09-08` 规律版本、`F09-14` 日期×站位、`F09-15` 多站相关（共同日不足，r 为 NA）、`F09-16` 三水层×昼夜。

## 5. 任务五：动态导出

- 源表为 S08 `dynamic_frames.csv`（4 日 × 24 小时 = 96 帧，五站同步）。导出 PNG 序列 96 张、`dynamic_frames.gif`、`dynamic_frames.mp4`、`dynamic_frames.pdf`。
- 使用本机登记的 ffmpeg（`C:\Program Files\EVCapture\ffmpeg.exe`）编码 MP4；导出记录含 `frame_count=96`、`consistency_check=PASS frames=96 NA=... no_interpolation`、SHA-256 与文件大小。
- 色标固定、缺测 NA 不补 0；无鱼群轨迹、无连续密度插值；网页交互播放已在 S08 完成，本阶段只做导出与帧一致性对账。

## 6. 任务六：测试与数据保护

```text
.\.venv\Scripts\python.exe -m pytest 04_SOURCE_CODE\tests -q
228 passed in 25.08s
```

覆盖：16 类登记与 BLOCKED 不造图、正式图配色 PASS、动画离散帧/NA/同源导出、Origin 环境探测、任务队列隔离、Worker 成功与故障状态、Web `/s09` 入队不阻塞。

原始数据保护：21 个声学 CSV 哈希 **21/21 与归档清单一致**；S09 只读既有分析结果与 S08 归档，不改原始 CSV。

## 7. 本阶段发现与处置

| # | 发现 | 处置 |
| --- | --- | --- |
| D-01 | `originpro`/`pywin32` 未安装 | 改用 PowerShell COM Worker；Python 包兼容标 BLOCKED |
| D-02 | Origin 首次运行出现用户目录与许可对话框；COM 初始 `0x80080005` | 完成首次运行设置后 COM 实测 PASS；许可/水印状态写入证据 |
| D-03 | `impCSV` 返回 False | Worker 解析 CSV 后经 COM `SetData` 写入，源表仍为 CSV |
| D-04 | `expGraph` 完整路径写法未生成文件 | 改为 `path:=目录 filename:=文件名`，逐格式记录 True |
| D-05 | 任务 ID 用秒级时间戳，同秒两次提交冲突 | 改微秒级 `ORIGIN-YYYYmmddHHMMSSffffff` |
| D-06 | 重复导出触发 Origin“文件存在”模态框导致 Worker 超时 | 导出前删除同名目标文件；超时任务标 FAILED 并清理子进程 |
| D-07 | MATPLOTLIB 默认黑色/灰色出现在 SVG，色板外不为 0 | 从 `figure_palette` 设置 text/axis/tick/legend 颜色，正式 SVG 色板外 0 |

## 8. 已知限制（不伪造）

1. 本机 Origin 为试用授权，导出图含 `demo` 水印，不能作正式科研图；正式图用 MATPLOTLIB 同源导出。
2. `originpro` Python 包与 Learning Edition 12 窗口上限均未实测通过，分别保持 BLOCKED/UNVERIFIED。
3. F09-05 因底界未确认保持 BLOCKED；F09-09/10/11 因现有结果 JSON 无可直接映射条目保持 NO_DATA，不补造图。
4. 动画只来自 S08 离散帧；倍速/播放不改变数据，不生成轨迹或连续密度。
5. Web 提交只入队并启动独立 Worker；刷新页面不会重复执行同一任务，项目隔离由任务 ID 与独立 OPJU 保证。

**结论：S09 的 6 项任务均有代码、真实环境实测、网页/CLI 与测试证据；停在 S09 等验收，未开始 S10。**
