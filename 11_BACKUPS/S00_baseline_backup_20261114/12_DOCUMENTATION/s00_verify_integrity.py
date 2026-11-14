# -*- coding: utf-8 -*-
"""S00 任务五：V4 包完整性校验 + 21 个原始 CSV SHA-256 全量复核（只读，不修改任何文件）。"""
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\WorkBuddy\渔业声学监测科研分析系统\FISHERY_RESEARCH_SYSTEM")
OUT_DIR = ROOT / "10_TEST_REPORTS" / "s00_verification"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path, chunk: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# ---- 1. V4 包 MANIFEST 校验 ----
manifest_path = ROOT / "FISHERY_FULL_PLAN_V4" / "MANIFEST_SHA256.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
items = manifest["files"]  # 结构：[{"name":..,"size_bytes":..,"sha256":..}]

v4_rows, v4_fail = [], 0
for it in items:
    rel = it["name"]
    expect = it["sha256"]
    expect_size = int(it["size_bytes"])
    f = ROOT / "FISHERY_FULL_PLAN_V4" / rel
    row = {"path": rel, "expected_sha256": expect, "expected_size": expect_size}
    if not f.exists():
        row.update(result="FAIL_MISSING")
        v4_fail += 1
    else:
        actual_size = f.stat().st_size
        actual = sha256_file(f)
        ok = (actual == expect) and (actual_size == expect_size)
        row.update(actual_sha256=actual, actual_size=actual_size,
                   result="PASS" if ok else "FAIL")
        if not ok:
            v4_fail += 1
    v4_rows.append(row)

with open(OUT_DIR / "V4_PACKAGE_VERIFY.csv", "w", newline="", encoding="utf-8-sig") as fo:
    w = csv.DictWriter(fo, fieldnames=["path", "expected_sha256", "expected_size",
                                       "actual_sha256", "actual_size", "result"])
    w.writeheader()
    w.writerows(v4_rows)

# ---- 2. 21 个原始 CSV 全量复核 ----
inv_path = ROOT / "10_TEST_REPORTS" / "RAW_CSV_PRECHECK_INVENTORY_CURRENT.csv"
csv_rows, csv_fail = [], 0
with open(inv_path, newline="", encoding="utf-8-sig") as fi:
    for r in csv.DictReader(fi):
        rel = r["relative_path"]
        expect = r["sha256"]
        expect_size = int(r["size_bytes"])
        f = ROOT / rel
        row = {"relative_path": rel, "expected_size": expect_size}
        if not f.exists():
            row.update(result="FAIL_MISSING")
            csv_fail += 1
        else:
            actual_size = f.stat().st_size
            actual = sha256_file(f)
            ok = (actual == expect) and (actual_size == expect_size)
            row.update(actual_size=actual_size, sha256_match=ok, result="PASS" if ok else "FAIL")
            if not ok:
                csv_fail += 1
        csv_rows.append(row)

total_bytes = sum(x.get("actual_size", 0) or 0 for x in csv_rows)
with open(OUT_DIR / "RAW_CSV_SHA256_RECHECK.csv", "w", newline="", encoding="utf-8-sig") as fo:
    w = csv.DictWriter(fo, fieldnames=["relative_path", "expected_size", "actual_size",
                                       "sha256_match", "result"])
    w.writeheader()
    w.writerows(csv_rows)

print(f"V4_PACKAGE: {len(v4_rows)} files checked, failures={v4_fail}")
print(f"RAW_CSV: {len(csv_rows)} files checked, failures={csv_fail}, total_bytes={total_bytes}")
sys.exit(0 if (v4_fail == 0 and csv_fail == 0) else 1)
