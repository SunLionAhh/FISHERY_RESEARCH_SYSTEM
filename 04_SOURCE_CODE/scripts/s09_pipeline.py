# -*- coding: utf-8 -*-
"""S09 CLI：16 类图、动画导出与 Origin Worker 闭环。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from app.config import PROJECT_ROOT  # noqa: E402
from app.db import connect, ensure_database  # noqa: E402
from app.services import origin_bridge, s09_animation, s09_figures  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="S09 科研图与导出流水线")
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe")
    figures = sub.add_parser("figures")
    figures.add_argument("--run-id", default="S09-RUN-20261117")
    figures.add_argument("--dataset-id", default="DATASET_01_DUAL_STATION")

    anim = sub.add_parser("animation")
    anim.add_argument("--formats", default="PNG_SEQUENCE,GIF,MP4,PDF")

    origin = sub.add_parser("origin")
    origin.add_argument("--figures", required=True)
    origin.add_argument("--formats", default="png,pdf,svg")
    origin.add_argument("--run", action="store_true")

    report = sub.add_parser("report")

    args = parser.parse_args()
    conn = connect()
    ensure_database(conn)
    try:
        if args.command == "probe":
            result = origin_bridge.probe_environment()
        elif args.command == "figures":
            result = s09_figures.build_all(conn, PROJECT_ROOT, run_id=args.run_id,
                                           dataset_id=args.dataset_id)
        elif args.command == "animation":
            result = s09_animation.export(conn, PROJECT_ROOT,
                                          formats=tuple(x for x in args.formats.split(",") if x))
        elif args.command == "origin":
            ids = [x.strip() for x in args.figures.split(",") if x.strip()]
            result = origin_bridge.create_task(
                conn, PROJECT_ROOT, ids,
                formats=tuple(x for x in args.formats.split(",") if x))
            if args.run:
                result["run"] = origin_bridge.run_task(conn, result["task_id"], PROJECT_ROOT)
        else:
            result = {"figures": s09_figures.report(conn),
                      "origin": origin_bridge.report(conn),
                      "animation": [dict(r) for r in conn.execute(
                          "SELECT * FROM animation_exports ORDER BY created_at DESC LIMIT 20")]}
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
