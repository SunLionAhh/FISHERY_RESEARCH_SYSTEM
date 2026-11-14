# 10_TEST_REPORTS 文件用途与优先级

> 2026-11-14 整理，**19:04 按用户范围确认、19:17 按 V4 基准裁定修订**：21 个 CSV 是第一阶段双站数据的**完整导出**，不再是「部分到位 / 缺 17 个文件」。本目录目前**只有预检记录，没有阶段报告**；`stage_reports/STAGE_S00.md` 仍待编码 Agent 实测后生成。
> 所有文件均为 WorkBuddy 辅助盘点，**不构成 S00 PASS，也不替代 S02 数据质量审计**。

## 原始 CSV 清单：哪一份是现行路径

| 优先级 | 文件 | 用途 | 状态 |
| --- | --- | --- | --- |
| **1（现行）** | `RAW_CSV_PRECHECK_INVENTORY_CURRENT.csv` | 21 个 CSV 的**现行相对路径** + SHA-256、字节数、编码、BOM、换行、时间格式、首末时间戳、信号点数、文本行数 | 归档后复跑，与归档前 21/21 哈希一致 |
| **1（现行）** | `RAW_CSV_ARCHIVE_MANIFEST.csv` | 21 行**归档映射**：原路径 → 现行路径、移动前后 SHA-256、哈希/字节数/mtime 三项校验（全 PASS） | 追溯归档动作的唯一依据 |
| 2（基准） | `RAW_CSV_PRECHECK_INVENTORY.csv` | **归档前快照**，21 行，作为归档校验的哈希基准 | 刻意不改写；其 `note` 列「文件仍在项目根目录，未按 02 指南 4.1 归档」描述的是当时状态，**现已失效**，不要据此判断文件位置 |

**原始 CSV 现行位置**：`01_ORIGINAL_DATA/FISHFINDER/2000/`（13 个）、`01_ORIGINAL_DATA/FISHFINDER/2001/`（8 个），共 8,380,445,292 字节。
符合 02 执行指南 4.1；属于 `01_ORIGINAL_DATA/` 只读保护范围，不得覆盖、改名或回写。
**归档 ≠ 导入**：未生成 `import_batch_id`，未入数据库，未做 S02 审计。

## 其余文件

| 文件 | 用途 |
| --- | --- |
| `RAW_CSV_ARRIVAL_NOTE.md` | 原始数据到位时间线、归档记录、差异表（**19:04 已撤销「缺 17 个」误判**、新增 D6 同期窗口口径）、结构预检结论、明确未做的 S02 项 |
| `ENVIRONMENT_PRECHECK.md` | 本机环境实测（Windows / Python / Git / PyCharm / Origin / 数据盘）、8 份归档资料 SHA-256、风速与潮汐资料预检 |
| `stage_reports/` | 空；S00—S11 阶段报告目录，须由编码 Agent 实测后写入 |

## 复现命令（在项目根目录执行）

```text
python3 12_DOCUMENTATION/precheck_raw_csv.py      # 扫描归档位置，输出 CURRENT 清单并与归档前快照比对
python3 12_DOCUMENTATION/archive_raw_csv.py       # 归档动作；源目录已不存在时会安全退出，不会重复移动
python3 12_DOCUMENTATION/preprocess_environment.py # 风速/潮汐格式预处理副本
python3 12_DOCUMENTATION/generate_demo.py         # 重生成只读演示原型
```

日志在 `14_TEMP/`：`archive_raw_csv_log.txt`、`precheck_after_archive_log.txt`、`raw_csv_precheck_log.txt`。

## 相关范围与版本记录（在 12_DOCUMENTATION/）

| 文件 | 用途 |
| --- | --- |
| `SCOPE_CONFIRMATION_DUAL_STATION.md` | 用户 19:04 确认 `SCOPE_DUAL_STATION_V1`：双站先行、完整导出、2000/2001 覆盖期、五站功能继续开发、持续增量上传、撤销旧误判、同期窗口口径 |
| `V4_PACKAGE_ARRIVAL_NOTE.md` | V4 规范包到位盘点（17 个文件 / 清单 16/16 PASS）、与 FINAL 1.5 的 V-1—V-8 差异；原待裁定项已于 19:17 关闭（以 V4 为准） |
| `V4_REQUIREMENTS_INDEX.md` / `SPEC_VERSION_MATRIX.md`（12_DOCUMENTATION/） | V4 要求全集索引（含路径解析规则）与版本 / 路径 / 冲突处置矩阵 |
