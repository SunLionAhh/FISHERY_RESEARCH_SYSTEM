# -*- coding: utf-8 -*-
"""S08 CLI：站位 GPS、坐标审计、站距、空间比较与离散动态帧。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from app.config import PROJECT_ROOT  # noqa: E402
from app.db import connect, ensure_database  # noqa: E402
from app.services import spatial  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="S08 五站空间与动态分析流水线")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync")
    sync.add_argument("--date", default="2026-10-31")

    station = sub.add_parser("station")
    station.add_argument("--device", required=True)
    station.add_argument("--station-id")
    station.add_argument("--longitude", type=float)
    station.add_argument("--latitude", type=float)
    station.add_argument("--crs")
    station.add_argument("--accuracy", type=float)
    station.add_argument("--depth", type=float)
    station.add_argument("--heading", type=float)
    station.add_argument("--heading-reference")
    station.add_argument("--source", default="USER_CLI")
    station.add_argument("--measured-at")
    station.add_argument("--effective-from")
    station.add_argument("--date", default="2026-10-31")

    distances = sub.add_parser("distances")
    distances.add_argument("--date", default="2026-10-31")

    map_cmd = sub.add_parser("map")
    map_cmd.add_argument("--date", default="2026-10-31")
    map_cmd.add_argument("--devices", default=",".join(spatial.DEVICE_IDS))

    analyze = sub.add_parser("analyze")
    analyze.add_argument("--devices", default=",".join(spatial.DEVICE_IDS))
    analyze.add_argument("--start", required=True)
    analyze.add_argument("--end", required=True)
    analyze.add_argument("--date", default="2026-10-31")
    analyze.add_argument("--step-hours", type=int, default=1)
    analyze.add_argument("--out", type=Path)

    frames = sub.add_parser("frames")
    frames.add_argument("--devices", default=",".join(spatial.DEVICE_IDS))
    frames.add_argument("--start", required=True)
    frames.add_argument("--end", required=True)
    frames.add_argument("--date", default="2026-10-31")
    frames.add_argument("--step-hours", type=int, default=1)

    args = parser.parse_args()
    conn = connect()
    ensure_database(conn)
    try:
        if args.command == "sync":
            count = spatial.sync_from_positions(conn, actor="cli")
            result = {"imported": count, "distances": spatial.compute_distances(
                conn, args.date, actor="cli")}
        elif args.command == "station":
            row_id = spatial.upsert_station(
                conn, args.device, station_id=args.station_id,
                longitude=args.longitude, latitude=args.latitude,
                coordinate_reference_system=args.crs, gps_accuracy_m=args.accuracy,
                water_depth_m=args.depth, heading_deg=args.heading,
                heading_reference=args.heading_reference, position_source=args.source,
                measured_at=args.measured_at, effective_from=args.effective_from, actor="cli")
            result = {"location_id": row_id,
                      "distances": spatial.compute_distances(conn, args.date, actor="cli")}
        elif args.command == "distances":
            result = spatial.compute_distances(conn, args.date, actor="cli")
        elif args.command == "map":
            result = spatial.map_payload(conn, args.date, spatial.parse_devices(args.devices))
        else:
            devices = spatial.parse_devices(args.devices)
            if args.command == "analyze":
                result = spatial.analyze_combination(
                    conn, devices, args.start, args.end, args.date,
                    step_hours=args.step_hours, actor="cli")
                if args.out:
                    args.out.parent.mkdir(parents=True, exist_ok=True)
                    result["archived_files"] = spatial.write_outputs(result, args.out)
            else:
                result = spatial.dynamic_frames(
                    conn, devices, args.start, args.end, step_hours=args.step_hours)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
