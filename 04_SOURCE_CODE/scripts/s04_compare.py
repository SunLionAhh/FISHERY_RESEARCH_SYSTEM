# -*- coding: utf-8 -*-
"""S04 任意时间/天数/设备比较的独立命令行入口（只读 S03 统计，不重算原始文件）。

用法（项目根目录）：
  .venv\\Scripts\\python.exe 04_SOURCE_CODE\\scripts\\s04_compare.py --devices 2000 --dates 2026-10-31,2026-11-01
  .venv\\Scripts\\python.exe 04_SOURCE_CODE\\scripts\\s04_compare.py --devices 2000 --day-count 7 --day-count-mode valid --baseline-mode valid --baseline-n 3
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
from app.services import comparison as cmp  # noqa: E402


def split(value: str | None) -> tuple[str, ...]:
    return tuple(x.strip() for x in (value or "").split(",") if x.strip())


def main() -> None:
    p = argparse.ArgumentParser(description="S04 通用筛选与比较引擎")
    p.add_argument("--name", default="S04 命令行比较")
    p.add_argument("--devices")
    p.add_argument("--stations")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--dates")
    p.add_argument("--hour-start", type=int)
    p.add_argument("--hour-end", type=int)
    p.add_argument("--day-count", type=int)
    p.add_argument("--day-count-mode", default="calendar", choices=["calendar", "valid"])
    p.add_argument("--timezone", default=cmp.DEFAULT_TIMEZONE)
    p.add_argument("--include-invalid", action="store_true")
    p.add_argument("--baseline-mode", choices=["valid", "calendar", "all", "range"])
    p.add_argument("--baseline-n", type=int, default=7)
    p.add_argument("--baseline-reference")
    p.add_argument("--baseline-start")
    p.add_argument("--baseline-end")
    p.add_argument("--output-root", type=Path, default=PROJECT_ROOT)
    p.add_argument("--no-save", action="store_true")
    args = p.parse_args()

    criteria = cmp.Criteria(
        devices=split(args.devices), stations=split(args.stations),
        start_date=args.start, end_date=args.end, dates=split(args.dates),
        hour_start=args.hour_start, hour_end=args.hour_end,
        day_count=args.day_count, day_count_mode=args.day_count_mode,
        timezone=args.timezone, include_invalid=args.include_invalid,
    )
    conn = connect()
    ensure_database(conn)
    try:
        result = cmp.run(conn, criteria, name=args.name, save=not args.no_save)
        if args.baseline_mode:
            reference = args.baseline_reference or (criteria.dates or [])[-1] or args.end
            if not reference:
                raise SystemExit("基线模式须提供 --baseline-reference（或 --dates 最后一天 / --end）")
            baseline = cmp.build_baseline(
                conn, criteria, reference, n=args.baseline_n, mode=args.baseline_mode,
                start=args.baseline_start, end=args.baseline_end)
            result["baseline"] = baseline
            result["summary"] = cmp.summarize(
                result["selection"],
                [c for matrix in (result["date_comparison_matrix"], result["device_comparison_matrix"])
                 for c in matrix["cases"] if c.get("status") == "OK"],
                baseline)
            if not args.no_save:
                conn.execute("UPDATE comparison_runs SET result_json=? WHERE comparison_id=?",
                             (json.dumps(result, ensure_ascii=False), result["comparison_id"]))
                conn.commit()
        paths = cmp.write_outputs(result, args.output_root)
        print(json.dumps({
            "comparison_id": result["comparison_id"],
            "window_count": result["selection"]["window_count"],
            "resolved_devices": result["selection"]["resolved_devices"],
            "resolved_dates": result["selection"]["resolved_dates"],
            "excluded_count": len(result["selection"]["excluded"]),
            "matrix": [{"device_id": c.get("device_id"), "case": c.get("case", c.get("label")),
                        "status": c.get("status", "OK")}
                       for c in result["date_comparison_matrix"]["cases"]],
            "device_cases": [{"device_id": c.get("device_id"), "case": c.get("case", c.get("label")),
                              "status": c.get("status", "OK")}
                             for c in result["device_comparison_matrix"]["cases"]],
            "baseline_n": {k: v["n_members"] for k, v in (result.get("baseline") or {}).get("devices", {}).items()},
            "outputs": paths,
        }, ensure_ascii=False, indent=2))
    except (cmp.ComparisonValidationError, cmp.ComparisonEmptyError) as exc:
        raise SystemExit(f"比较失败：{exc}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
