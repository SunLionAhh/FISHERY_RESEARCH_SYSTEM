# -*- coding: utf-8 -*-
"""S06 日内/昼夜/晨昏流水线（原始文件只读，结果写入 06_ANALYSIS_RESULTS/s06）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from app import create_app  # noqa: E402
from app.config import PROJECT_ROOT  # noqa: E402
from app.db import connect, ensure_database  # noqa: E402
from app.services import intraday  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="S06 日内、昼夜与晨昏分析")
    sub = parser.add_subparsers(dest="command", required=True)
    grid = sub.add_parser("build-grid")
    grid.add_argument("--device", required=True)
    grid.add_argument("--date", required=True)
    grid.add_argument("--overwrite", action="store_true")
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--devices", required=True, help="逗号分隔")
    analyze.add_argument("--start", required=True)
    analyze.add_argument("--end", required=True)
    analyze.add_argument("--timezone", default="Asia/Shanghai")
    analyze.add_argument("--name", default="S06 日内分析")
    analyze.add_argument("--out", type=Path)
    analyze.add_argument("--overwrite-grids", action="store_true")
    args = parser.parse_args()

    create_app()
    conn = connect()
    ensure_database(conn)
    try:
        if args.command == "build-grid":
            count = intraday.build_grid(conn, args.device, args.date,
                                        project_root=PROJECT_ROOT, overwrite=args.overwrite)
            print(json.dumps({"device_id": args.device, "observed_date": args.date,
                              "grid_cells": count}, ensure_ascii=False))
        else:
            devices = tuple(d.strip() for d in args.devices.split(",") if d.strip())
            result = intraday.run(conn, devices, intraday.date_range(args.start, args.end), name=args.name,
                                  timezone_name=args.timezone, project_root=PROJECT_ROOT,
                                  overwrite_grids=args.overwrite_grids)
            paths = intraday.write_outputs(result, args.out or PROJECT_ROOT)
            print(json.dumps({"analysis_id": result["analysis_id"],
                              "grid_cells": result["scope"]["n_grid_cells"],
                              "blocked_inputs": result["scope"]["blocked_inputs"],
                              "artifacts": paths}, ensure_ascii=False, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
