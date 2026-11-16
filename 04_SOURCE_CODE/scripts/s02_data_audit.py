# -*- coding: utf-8 -*-
"""S02 数据审计入口：流式审计两份真实 CSV，产出 8 份工件。

用法（在项目根目录）：
    .venv\\Scripts\\python.exe 04_SOURCE_CODE\\scripts\\s02_data_audit.py
    .venv\\Scripts\\python.exe 04_SOURCE_CODE\\scripts\\s02_data_audit.py --limit 2000   # 冒烟

只读原始文件；正式审计会遍历全文件（约 800MB），耗时数分钟。
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]      # 04_SOURCE_CODE
ROOT = SOURCE.parent
sys.path.insert(0, str(SOURCE))

from app.db import connect, ensure_database  # noqa: E402
from app.identity import current_operator  # noqa: E402
from app.services import audit_s02  # noqa: E402
from app.services import distance_mapping as dm  # noqa: E402

DATA_ROOT = ROOT / "01_ORIGINAL_DATA" / "FISHFINDER"
DEFAULT_OUT = ROOT / "10_TEST_REPORTS" / "data_audit"
MANIFEST = ROOT / "10_TEST_REPORTS" / "RAW_CSV_ARCHIVE_MANIFEST.csv"
FILES = {
    "2000": DATA_ROOT / "2000" / "探鱼-2000_2026-10-31.csv",
    "2001": DATA_ROOT / "2001" / "探鱼-2001_2026-10-31.csv",
}


def load_manifest() -> dict[str, dict]:
    result: dict[str, dict] = {}
    if not MANIFEST.exists():
        return result
    with MANIFEST.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("file_name", "").endswith("_2026-10-31.csv"):
                device = row.get("device_id", "").strip()
                result[device] = {"sha256": row.get("sha256_after", "").strip(),
                                  "size": row.get("size_bytes", "").strip()}
    return result


def ensure_mapping_registered(conn, device_id: str) -> None:
    existing = dm.latest_mapping(conn, device_id)
    if existing is not None:
        print(f"  {device_id}: 已有映射 v{existing.version}（{existing.sample_mode}/"
              f"{existing.support_status}），不重复登记")
        return
    mapping = dm.DistanceMapping(
        device_id=device_id,
        range_m=audit_s02.DECLARED_RANGE_M,
        point_count=audit_s02.EXPECTED_POINTS,
        sample_mode=dm.SAMPLE_MODE_UNKNOWN,
        first_sample_distance_m=None,
        sample_interval_m=None,
        support_status=dm.SUPPORT_UNVERIFIED,
        evidence=("S02 文件审计：每记录量程 37.5 m、数组长度众数 1000；"
                  "点/区间语义、首点距离、量程与点数的对应关系均未提供 → UNVERIFIED"),
        source="S02_DATA_AUDIT",
    )
    version = dm.register_mapping(conn, mapping, operator=current_operator())
    conn.commit()
    print(f"  {device_id}: 登记映射 v{version}（UNKNOWN/UNVERIFIED → 正式距离分析 BLOCKED）")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "03_DATABASE" / "fishery.db"))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=None, help="仅审计前 N 行（冒烟用）")
    parser.add_argument("--skip-hash", action="store_true", help="跳过 SHA-256（仅冒烟）")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    conn = connect(Path(args.db))
    applied = ensure_database(conn)
    if applied:
        print(f"数据库迁移已应用：{applied}")
    manifest = load_manifest()
    audits = []

    print("S02 数据审计开始", datetime.now().isoformat(timespec="seconds"))
    for device_id, path in FILES.items():
        print(f"[{device_id}] 检查文件 {path.name}")
        if args.limit:
            print(f"  !! 冒烟模式：仅前 {args.limit} 行，不得作为阶段结论")
        ensure_mapping_registered(conn, device_id)
        audit = audit_s02.audit_device(
            device_id, path, conn=conn, compute_hash=not args.skip_hash, limit=args.limit)
        print(f"  行数={audit.rows_total} 编码={audit.inspection.encoding} "
              f"覆盖={audit.ts_min}→{audit.ts_max} 掩码={audit.mask_status}")
        audits.append(audit)

    audit_s02.write_field_dictionary(audits, out)
    audit_s02.write_signal_array_audit(audits, out)
    audit_s02.write_timestamp_audit(audits, out)
    audit_s02.write_coverage_audit(audits, out)
    audit_s02.write_device_comparability(audits, out)
    audit_s02.write_bottom_reference_audit(conn, out, {a.device_id: a for a in audits})
    issues = audit_s02.write_issues(audits, out)
    audit_s02.write_report(
        audits, issues, out,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        manifest_by_device=manifest,
    )
    print(f"工件已写入 {out}（{len(audit_s02.ARTIFACTS)} 份，issues={len(issues)}）")
    conn.close()
    if args.limit:
        print("注意：本次为冒烟抽样，不构成 S02 结论。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
