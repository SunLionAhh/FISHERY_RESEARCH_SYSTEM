# PROJECT_STRUCTURE — 项目目录结构说明

> 依据：**V4 现行** `FISHERY_FULL_PLAN_V4/01_MASTER_SPEC_FINAL.md` 第四章、`02_CODEX_EXECUTION_GUIDE_FINAL.md` 第三章。
> 项目根目录：`FISHERY_RESEARCH_SYSTEM/`。用户 2026-11-14 19:17 裁定「以 V4 为准」。
> 本文件随每阶段更新；目录职责不得擅自变更。

## 一级目录职责

| 目录 | 职责 | 当前内容 |
| --- | --- | --- |
| `00_PROJECT_SPEC/` | **历史基线（只读对照）** + `README.md` 版本声明 | 三份 FINAL 1.5 `.md`、`_source/` 原始 docx；不作开发依据，现行规范见 `FISHERY_FULL_PLAN_V4/` |
| `01_ORIGINAL_DATA/` | 原始 CSV、环境原文件、GPS、厂家资料；**只读保护** | 风速 xlsx、潮汐 zip；`FISHFINDER/2000/` 13 个 + `2001/` 8 个原始 CSV（8.38 GB，**第一阶段双站完整导出**，21/21 哈希复核通过）；`FISHFINDER/README.md`；**2002/2003/2005 空（第二阶段后续上传），无 2004** |
| `02_IMPORTED_DATA/` | 标准化数据、解析结果、字段映射、导入批次 | `ENVIRONMENT/WIND/` 风速预处理 CSV、`ENVIRONMENT/TIDE/` 潮汐截图清单 CSV（**格式预处理副本，无 import_batch_id**） |
| `03_DATABASE/` | SQLite 数据库、迁移文件、备份 | 空 |
| `04_SOURCE_CODE/` | Python、Flask、解析、统计、环境、空间、动态、Origin 桥接代码 | `requirements-lock.txt`（36 项依赖锁）、`tests/test_s00_smoke.py`（S00 冒烟 29 用例）；**尚无 Flask/解析/统计实现** |
| `05_CONFIG/` | 设备、站位、安装参数、底界、环境来源、分析参数、时区、图形样式 | `FIGURE_COLOR_SPEC.md`、`figure_palette.json`、`COLOR_REFERENCE/`；**V4 10 参数示例是草稿，未生效**；其余设备/站位参数为空 |
| `06_ANALYSIS_RESULTS/` | 各数据集统计结果、CSV、报告、运行清单 | 空 |
| `07_FIGURES/` | PNG、PDF、SVG、GIF、MP4、动态帧、组合图 | 空 |
| `08_ORIGIN_PROJECTS/` | OPJU、Origin 模板、任务包、导出与回传记录 | 空 |
| `09_PAPER_OUTPUT/` | 论文各章节、图表、表格、图注、证据包 | 空 |
| `10_TEST_REPORTS/` | S00—S11 阶段报告、数据审计、测试与验收记录 | `README.md`、`ENVIRONMENT_PRECHECK.md`、`RAW_CSV_ARRIVAL_NOTE.md`、三份 CSV 清单（预检）；**`stage_reports/STAGE_S00.md`（已生成，待验收）**、**`s00_verification/`（V4 包 16/16 + 21 CSV 全量复核证据）** |
| `11_BACKUPS/` | 代码、数据库、配置的可恢复备份 | **`S00_baseline_backup_20261114/`（30 文件 + SHA-256 清单 + 恢复说明）** |
| `12_DOCUMENTATION/` | 安装手册、用户手册、开发说明 | **`V4_REQUIREMENTS_INDEX.md`、`SPEC_VERSION_MATRIX.md`、`REQUIREMENTS_TRACEABILITY_MATRIX.md`（S00 新建追踪矩阵）、`DEV_PLAN_S00_S11.md`（S00 新建开发计划）**、`S00_START_PROMPT.md`、`SCOPE_CONFIRMATION_DUAL_STATION.md`、`V4_PACKAGE_ARRIVAL_NOTE.md`、`WORKBUDDY_SCOPE_AND_GAPS.md`、早期开发总规划；脚本 `preprocess_environment.py`、`precheck_raw_csv.py`、`archive_raw_csv.py`、`figure_palette.py`、`check_figure_colors.py`、`generate_demo.py`、**`s00_verify_integrity.py`、`s00_backup_assets.py`（S00 新增）**；`DEMO_PROTOTYPE.html`、`demo_assets/` |
| `13_FROZEN_VERSIONS/` | 双站、五站、预答辩、盲审冻结结果 | 空 |
| `14_TEMP/` | 可重新生成的临时文件 | 潮汐解压副本、日志、标题拼接图、批量同步脚本（已被 `.gitignore` 排除） |

## 原始数据子目录（V4 五台，无 2004）

```
01_ORIGINAL_DATA/
├── FISHFINDER/
│   ├── README.md
│   ├── 2000/   ← 13 个 CSV（2026-10-31 — 11-12）
│   ├── 2001/   ← 8 个 CSV（2026-10-31 — 11-07，用户确认不补传）
│   ├── 2002/   ← 空（后续上传）
│   ├── 2003/   ← 空（后续上传）
│   └── 2005/   ← 空（后续上传）
├── ENVIRONMENT/
│   ├── WATER_TEMPERATURE/
│   ├── TIDE/
│   └── WIND/
├── GPS/
└── MANUFACTURER_DOCS/
```

> V4 02 第三章与 `08_USER_REQUIREMENTS_V4.md` 明确五台为 **2000、2001、2002、2003、2005**，**没有 2004**。用户 19:17 再次强调不得混淆；原空的 `2004/` 目录已删除、`2005/` 已补建。`00_PROJECT_SPEC/` 历史基线里的 2004 字样属旧版误写，只读保留供差异对照，**不得据此开发**。
> 21 个原始 CSV 原位于项目根目录 `探鱼-2001_2026-11-07/`，用户 19:04 确认是第一阶段双站完整导出；18:48 用户指示整理后按设备归位，21/21 SHA-256、字节数、mtime 校验通过。来源路径见 `10_TEST_REPORTS/RAW_CSV_ARCHIVE_MANIFEST.csv`。后续数据按 V4 01 第八章**持续增量上传**；2001 已确认不补传。

## 根目录非编号资料（不改变 00—14 骨架）

| 目录 / 文件 | 说明 |
| --- | --- |
| `FISHERY_FULL_PLAN_V4/` | 2026-11-14 19:02 到位的 **V4 完整开发规范包**：17 个文件，包内 SHA-256 清单 16/16 通过。用户 19:13 确认「这是全部要求」、19:17 裁定「**以 V4 为准**」。**原位完整保留，不拆散、不改名、不覆盖**（`00_README.txt` 第 6 行要求整包交给开发者）。 |
| `.gitignore` | 排除 `01_ORIGINAL_DATA/FISHFINDER/**/*.csv`（8.38 GB）、`14_TEMP/`、`.venv/`、缓存。 |
| `.git/` | 用户 19:17 要求的 Git 安全回滚点；初始提交 `183e469`（完整 hash 见 `PROJECT_MASTER_INDEX.md`）；`.gitattributes` 保证按字节保真。 |

> `FISHERY_FULL_PLAN_V4/` 不属于 00—14 编号体系。V4 文档内部引用的 `00_PROJECT_SPEC/01|02|03_*.md` 须按 `12_DOCUMENTATION/V4_REQUIREMENTS_INDEX.md` 第 3 节**路径解析规则**映射到包内同名文件，不得误读历史基线。

## 配色规格文件（05_CONFIG，`FIGURE_COLOR_SPEC_V1`，用户确认，强制执行）

```
05_CONFIG/
├── FIGURE_COLOR_SPEC.md        # 规格全文：三套色板 / 版式规则 / 执行与校验
├── figure_palette.json         # 唯一机器可读色值源
└── COLOR_REFERENCE/
    ├── 1b06751c-...jpg         # 方案 A 参考图
    ├── 9e514186-...jpg         # 方案 B 参考图
    └── 4c301704-...jpg         # 方案 C 参考图
```

> 绘图脚本一律 `import figure_palette`，不得硬编码颜色；交付前运行 `check_figure_colors.py`，色板外颜色数必须为 0。
> 原始资料截图（潮汐 PNG）与 V4 12 几何条件示意图属不适用项，不得改色或重绘。

## 根目录管理文件

| 文件 | 用途 |
| --- | --- |
| `PROJECT_MASTER_INDEX.md` | 唯一状态入口：版本基准、阶段、标识、资料、已关闭/待处置项、下一步 |
| `PROJECT_STRUCTURE.md` | 本文件：目录职责与当前内容 |
| `CHANGELOG.md` | 变更记录（含初始 Git 回滚点提交号） |

## 运行标识规则（V4 04 第 7.1 节、规范 4.6）

- 每次导入生成 `import_batch_id`；每次分析生成 `run_id` 并输出 `manifest.json`；每个 Origin 任务生成 `origin_job_id`。
- `manifest.json` 记录 run_id、dataset_id、数据源 SHA-256、设备/底界/环境/分析计划/代码/依赖/QC 版本、时间范围、时区、方法、输出文件、生成时间、质量状态。
- 每条要求建立需求追踪台账：`requirement_id` → 规范章节 → 实现位置 → 测试 ID → 真实样本 → 工件 → 状态；SKIP / BLOCKED 不是 PASS。

## 文件类型约定

`.py` 程序 · `.md` 规范与报告 · `.yaml` 配置 · `.json` 任务与清单 · `.csv` 原始及分析数据 · `.xlsx` 环境资料 · `.db` 数据库 · `.parquet` 大型标准化数据 · `test_*.py` 测试 · `.opju` Origin 项目 · `.png/.pdf/.svg` 图 · `.gif/.mp4` 动画 · `.log` 日志 · `.bat` Windows 启动 · `.lock/.txt` 依赖锁定。

**不得把唯一成果留在桌面、下载目录或临时目录。**
