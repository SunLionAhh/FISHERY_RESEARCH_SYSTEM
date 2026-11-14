# -*- coding: utf-8 -*-
"""S00 任务七：把可恢复资产备份到 11_BACKUPS/S00_baseline_backup_20261114/。

不复制 8.38 GB 原始 CSV（只读保护，且由 21/21 SHA-256 清单与 Git 排除规则覆盖）；
备份对象：根目录管理文件、V4 包关键校验信息、05_CONFIG 配色规格、
12_DOCUMENTATION 脚本与文档、10_TEST_REPORTS 清单。每份备份文件记录 SHA-256。
"""
import csv
import hashlib
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\WorkBuddy\渔业声学监测科研分析系统\FISHERY_RESEARCH_SYSTEM")
DEST = ROOT / "11_BACKUPS" / "S00_baseline_backup_20261114"

COPY_LIST = [
    "PROJECT_MASTER_INDEX.md",
    "PROJECT_STRUCTURE.md",
    "CHANGELOG.md",
    ".gitignore",
    ".gitattributes",
    "05_CONFIG/FIGURE_COLOR_SPEC.md",
    "05_CONFIG/figure_palette.json",
    "12_DOCUMENTATION/V4_REQUIREMENTS_INDEX.md",
    "12_DOCUMENTATION/SPEC_VERSION_MATRIX.md",
    "12_DOCUMENTATION/SCOPE_CONFIRMATION_DUAL_STATION.md",
    "12_DOCUMENTATION/WORKBUDDY_SCOPE_AND_GAPS.md",
    "12_DOCUMENTATION/S00_START_PROMPT.md",
    "12_DOCUMENTATION/figure_palette.py",
    "12_DOCUMENTATION/check_figure_colors.py",
    "12_DOCUMENTATION/precheck_raw_csv.py",
    "12_DOCUMENTATION/archive_raw_csv.py",
    "12_DOCUMENTATION/preprocess_environment.py",
    "12_DOCUMENTATION/s00_verify_integrity.py",
    "10_TEST_REPORTS/ENVIRONMENT_PRECHECK.md",
    "10_TEST_REPORTS/RAW_CSV_ARRIVAL_NOTE.md",
    "10_TEST_REPORTS/RAW_CSV_ARCHIVE_MANIFEST.csv",
    "10_TEST_REPORTS/RAW_CSV_PRECHECK_INVENTORY_CURRENT.csv",
    "10_TEST_REPORTS/RAW_CSV_PRECHECK_INVENTORY.csv",
    "10_TEST_REPORTS/README.md",
    "01_ORIGINAL_DATA/FISHFINDER/README.md",
    "00_PROJECT_SPEC/README.md",
    "FISHERY_FULL_PLAN_V4/MANIFEST_SHA256.json",
    "FISHERY_FULL_PLAN_V4/10_DEVICE_CONFIG_EXAMPLE.json",
    "04_SOURCE_CODE/tests/test_s00_smoke.py",
    "04_SOURCE_CODE/requirements-lock.txt",
]


def sha256_file(path: Path, chunk: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


if DEST.exists():
    raise SystemExit(f"备份目录已存在，中止：{DEST}")

rows = []
for rel in COPY_LIST:
    src = ROOT / rel
    if not src.is_file():
        rows.append({"source": rel, "result": "MISSING"})
        continue
    dst = DEST / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    rows.append({
        "source": rel,
        "backup_path": str(dst.relative_to(ROOT)),
        "size_bytes": dst.stat().st_size,
        "sha256": sha256_file(dst),
        "result": "COPIED",
    })

with open(DEST / "BACKUP_MANIFEST.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["source", "backup_path", "size_bytes", "sha256", "result"])
    w.writeheader()
    w.writerows(rows)

missing = [r["source"] for r in rows if r["result"] != "COPIED"]
readme = f"""# S00 基线备份（{datetime.now().isoformat(timespec='seconds')}）

- 备份来源：项目根目录 FISHERY_RESEARCH_SYSTEM
- 文件清单：BACKUP_MANIFEST.csv（{len(rows)} 条，含 SHA-256）
- 缺失条目：{missing if missing else '无'}
- 8.38 GB 原始 CSV 不入备份：属 01_ORIGINAL_DATA 只读保护，
  完整性由 10_TEST_REPORTS/s00_verification/RAW_CSV_SHA256_RECHECK.csv（21/21 PASS）
  与 Git .gitignore 排除规则覆盖；恢复策略为「登记 + 哈希校验」而非物理复制。
- Git 回滚点：初始提交 183e469e5ff62b39adda2e2fde693995879b3e2e（代码与文档）。
- 恢复方法：把本目录内文件复制回项目对应路径，并逐条比对 BACKUP_MANIFEST.csv 的 SHA-256。
"""
(DEST / "BACKUP_README.md").write_text(readme, encoding="utf-8")
print(f"备份完成：{len(rows) - len(missing)} 文件复制到 {DEST}")
if missing:
    print("缺失：", missing)
