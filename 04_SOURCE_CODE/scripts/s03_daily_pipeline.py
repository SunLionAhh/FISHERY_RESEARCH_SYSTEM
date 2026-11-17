# -*- coding: utf-8 -*-
"""S03 真实数据逐日流水线入口（只读原始 CSV）。

用法（项目根目录）：
  .venv\\Scripts\\python.exe 04_SOURCE_CODE\\scripts\\s03_daily_pipeline.py upload --device 2000 --date 2026-10-31
  .venv\\Scripts\\python.exe 04_SOURCE_CODE\\scripts\\s03_daily_pipeline.py missing --device 2000 --date 2026-11-02
  .venv\\Scripts\\python.exe 04_SOURCE_CODE\\scripts\\s03_daily_pipeline.py report --device 2000 --date 2026-10-31
  .venv\\Scripts\\python.exe 04_SOURCE_CODE\\scripts\\s03_daily_pipeline.py index
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from app.config import PROJECT_ROOT  # noqa: E402
from app.db import connect, ensure_database  # noqa: E402
from app.services import daily_stats as ds  # noqa: E402
from app.services import incremental as inc  # noqa: E402
from app.services import reporting  # noqa: E402


def default_file(device_id: str, observed_date: str) -> Path:
    return (PROJECT_ROOT / "01_ORIGINAL_DATA" / "FISHFINDER" / device_id
            / f"探鱼-{device_id}_{observed_date}.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="S03 每日统计/增量上传流水线")
    sub = parser.add_subparsers(dest="command", required=True)
    upload = sub.add_parser("upload")
    upload.add_argument("--device", required=True)
    upload.add_argument("--date", required=True)
    upload.add_argument("--file", type=Path)
    upload.add_argument("--upload-date")
    upload.add_argument("--force", action="store_true")
    upload.add_argument("--limit", type=int)
    upload.add_argument("--no-outputs", action="store_true")
    missing = sub.add_parser("missing")
    missing.add_argument("--device", required=True)
    missing.add_argument("--date", required=True)
    missing.add_argument("--note", default="人工登记缺测")
    report = sub.add_parser("report")
    report.add_argument("--device", required=True)
    report.add_argument("--date", required=True)
    sub.add_parser("index")
    args = parser.parse_args()

    conn = connect()
    ensure_database(conn)
    try:
        if args.command == "upload":
            path = args.file or default_file(args.device, args.date)
            outcome = inc.register_upload(
                conn, args.device, path, observed_date=args.date,
                upload_date=args.upload_date, force=args.force, limit=args.limit,
                generate_outputs=not args.no_outputs,
            )
            print(json.dumps(outcome.as_dict(), ensure_ascii=False, indent=2))
        elif args.command == "missing":
            stat_id = inc.mark_missing(conn, args.device, args.date, note=args.note)
            print(json.dumps({"stat_id": stat_id, "device_id": args.device,
                              "observed_date": args.date, "status": ds.STATUS_MISSING},
                             ensure_ascii=False))
        elif args.command == "report":
            row = ds.latest_stat(conn, args.device, args.date)
            if row is None:
                raise SystemExit(f"无统计行：{args.device}/{args.date}")
            paths = reporting.generate_daily_outputs(conn, dict(row))
            inc.register_artifacts(conn, row["run_id"], args.device, args.date, paths)
            conn.commit()
            print(json.dumps({"artifacts": paths}, ensure_ascii=False, indent=2))
        elif args.command == "index":
            print(inc.write_analysis_index(conn).as_posix())
    finally:
        conn.close()


if __name__ == "__main__":
    main()
