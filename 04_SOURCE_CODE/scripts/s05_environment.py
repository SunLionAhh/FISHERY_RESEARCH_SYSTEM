# -*- coding: utf-8 -*-
"""S05 环境数据入口：来源登记、预览/导入、评估/自动获取失败留痕、联合分析。"""
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
from app.services import environment_analysis as analysis  # noqa: E402
from app.services import environment_fetch as fetch  # noqa: E402
from app.services import environment_import as importer  # noqa: E402


def mapping_from_args(args) -> importer.Mapping:
    return importer.Mapping(
        variable=args.variable, timezone=args.timezone,
        datetime_column=args.datetime_col, date_column=args.date_col,
        time_column=args.time_col, value_column=args.value_col,
        unit_column=args.unit_col, unit_literal=args.unit,
        station_column=args.station_col, quality_column=args.quality_col,
        header_row=args.header_row, sheet=args.sheet, location_key=args.location_key,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="S05 环境数据导入与联合分析")
    sub = parser.add_subparsers(dest="command", required=True)

    p_source = sub.add_parser("register-source")
    p_source.add_argument("--source-id", required=True)
    p_source.add_argument("--name", required=True)
    p_source.add_argument("--kind", default="MANUAL", choices=("MANUAL", "DERIVED", "AUTO"))
    p_source.add_argument("--provider", required=True)
    p_source.add_argument("--dataset", default="")
    p_source.add_argument("--url", default="")
    p_source.add_argument("--spatial", default="")
    p_source.add_argument("--resolution", default="")
    p_source.add_argument("--observed-or-forecast", default="UNKNOWN")
    p_source.add_argument("--license", default="")
    p_source.add_argument("--authorization", default="")
    p_source.add_argument("--api-limits", default="")
    p_source.add_argument("--note", default="")

    p_preview = sub.add_parser("preview")
    p_import = sub.add_parser("import")
    for p in (p_preview, p_import):
        p.add_argument("--file", type=Path, required=True)
        p.add_argument("--source-id", required=True)
        p.add_argument("--variable", default="WIND_SPEED", choices=importer.VARIABLES)
        p.add_argument("--timezone", default="Asia/Shanghai")
        p.add_argument("--datetime-col")
        p.add_argument("--date-col")
        p.add_argument("--time-col")
        p.add_argument("--value-col")
        p.add_argument("--unit-col")
        p.add_argument("--unit")
        p.add_argument("--station-col")
        p.add_argument("--quality-col")
        p.add_argument("--location-key")
        p.add_argument("--header-row", type=int)
        p.add_argument("--sheet")
        p.add_argument("--suggest", action="store_true", help="从文件自动建议字段映射")
    p_import.add_argument("--project-root", type=Path, default=PROJECT_ROOT)

    p_fetch = sub.add_parser("fetch-evaluate")
    p_attempt = sub.add_parser("fetch-attempt")
    p_attempt.add_argument("--adapter", required=True)

    p_analysis = sub.add_parser("analyze")
    p_analysis.add_argument("--devices", default="2000")
    p_analysis.add_argument("--start")
    p_analysis.add_argument("--end")
    p_analysis.add_argument("--timezone", default="Asia/Shanghai")
    p_analysis.add_argument("--tolerance", type=int, default=analysis.DEFAULT_TOLERANCE_S)
    p_analysis.add_argument("--out", type=Path)

    args = parser.parse_args()
    conn = connect()
    ensure_database(conn)
    try:
        if args.command == "register-source":
            out = importer.register_source(
                conn, args.source_id, name=args.name, kind=args.kind, provider=args.provider,
                dataset=args.dataset, source_url=args.url, spatial_coverage=args.spatial,
                time_resolution=args.resolution, observed_or_forecast=args.observed_or_forecast,
                license=args.license, authorization=args.authorization,
                api_limits=args.api_limits, quality_note=args.note)
        elif args.command in ("preview", "import"):
            if args.suggest:
                headers, _, metadata, sheet, header_row, kind = importer.read_table(args.file)
                mapping = importer.suggest_mapping(headers, variable=args.variable,
                                                   timezone=args.timezone, metadata=metadata)
                mapping.sheet, mapping.header_row = args.sheet or sheet, args.header_row if args.header_row is not None else header_row
            else:
                mapping = mapping_from_args(args)
            if not mapping.value_column:
                raise SystemExit("缺少 --value-col；或加 --suggest 自动识别")
            if args.command == "preview":
                out = importer.preview_file(args.file, mapping).as_dict()
            else:
                out = importer.commit_import(conn, args.file, mapping, args.source_id,
                                             project_root=args.project_root)
        elif args.command == "fetch-evaluate":
            out = fetch.evaluate()
        elif args.command == "fetch-attempt":
            out = fetch.attempt(conn, args.adapter, {"requested_by": "cli"})
        elif args.command == "analyze":
            result = analysis.run(conn, devices=tuple(args.devices.split(",")),
                                  start_date=args.start, end_date=args.end,
                                  timezone_name=args.timezone, tolerance_s=args.tolerance)
            out = {"analysis_id": result["analysis_id"],
                   "scope": result["scope"],
                   "status": {k: v["status"] for k, v in result["variables"].items()},
                   "joint_status": result["joint_analysis"]["status"]}
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                out["result_path"] = str(args.out)
        else:
            parser.error("未知命令")
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
