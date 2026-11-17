# -*- coding: utf-8 -*-
"""S07 CLI：几何、分层/近底 QC、规律证据等级、数据集边界与冻结。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from app.config import PROJECT_ROOT  # noqa: E402
from app.db import connect, ensure_database  # noqa: E402
from app.services import beam_geometry as geo  # noqa: E402
from app.services import s07_datasets as datasets  # noqa: E402
from app.services import s07_depth as depth  # noqa: E402
from app.services import s07_patterns as patterns  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="S07 水层/底界/规律流水线")
    sub = parser.add_subparsers(dest="command", required=True)
    geom = sub.add_parser("geometry")
    geom.add_argument("--device", default="2000")
    geom.add_argument("--date", default="2026-10-31")
    layers = sub.add_parser("layers")
    layers.add_argument("--device", default="2000")
    layers.add_argument("--date", required=True)
    pat = sub.add_parser("patterns")
    pat.add_argument("--devices", default="2000,2001")
    pat.add_argument("--start", required=True)
    pat.add_argument("--end", required=True)
    pat.add_argument("--dataset-id")
    pat.add_argument("--save", action="store_true")
    pat.add_argument("--out", type=Path)
    data = sub.add_parser("datasets")
    data.add_argument("--dataset-id", default="DATASET_01_DUAL_STATION")
    data.add_argument("--action", choices=("report", "boundaries", "freeze", "reopen"),
                      default="report")
    data.add_argument("--start-time")
    data.add_argument("--end-time")
    data.add_argument("--formal-sync-time")
    data.add_argument("--installation-status")
    data.add_argument("--reason", default="S07 CLI")
    args = parser.parse_args()

    conn = connect()
    ensure_database(conn)
    try:
        if args.command == "geometry":
            params = geo.effective_params(conn, args.device, args.date)
            result = geo.beam_geometry(
                height_m=float(params["vertical_bottom_clearance_m"]),
                tilt_deg=float(params["downward_tilt_deg"]),
                beam_value_deg=float(params["beam_angle_value_deg"]),
                beam_kind=params["beam_angle_kind"],
                cutoff_m=float(params["analysis_cutoff_slant_m"]))
        elif args.command == "layers":
            result = depth.analyze_device_day(conn, args.device, args.date,
                                              project_root=PROJECT_ROOT)
        elif args.command == "patterns":
            devices = tuple(d.strip() for d in args.devices.split(",") if d.strip())
            result = patterns.analyze(conn, devices, args.start, args.end,
                                      dataset_id=args.dataset_id)
            if args.save:
                result["pattern_id"] = patterns.save_pattern(conn, result)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
        else:
            if args.action == "report":
                result = datasets.report(conn, args.dataset_id)
            elif args.action == "boundaries":
                result = datasets.set_boundaries(
                    conn, args.dataset_id, start_time=args.start_time,
                    end_time=args.end_time, formal_sync_time=args.formal_sync_time,
                    installation_status=args.installation_status, actor="cli")
            elif args.action == "freeze":
                result = datasets.freeze(conn, args.dataset_id, actor="cli", reason=args.reason)
            else:
                result = datasets.reopen(conn, args.dataset_id, actor="cli", reason=args.reason)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
