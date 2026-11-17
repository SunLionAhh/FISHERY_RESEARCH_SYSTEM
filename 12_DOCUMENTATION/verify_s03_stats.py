# -*- coding: utf-8 -*-
"""S03 独立数值复算（不复用被测掩码/统计实现）。

纯标准库按已确认映射 v2（INTERVAL，首格 0.5 m，格宽 0.0375 m，人工截断 5.2 m，
盲区 0.5 m + 行内首个 0 之前排除）独立重算前 N 行，与 S03 服务的 limit 运行结果对账。

用法（项目根目录）：
  .venv\\Scripts\\python.exe 12_DOCUMENTATION\\verify_s03_stats.py --device 2000 --date 2026-10-31 --limit 2000
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "04_SOURCE_CODE"))

FIRST_M = 0.5
STEP_M = 0.0375
CUTOFF_M = 5.2
BLIND_M = 0.5
EVENT_THRESHOLD = 200.0
EVENT_MIN_BINS = 3


def detect(path: Path) -> str:
    sample = path.open("rb").read(1 << 20)
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        sample.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "gb18030"


def independent_recompute(path: Path, limit: int) -> dict:
    """只使用标准库；不 import app.services.distance_mapping / daily_stats。"""
    kept: list[float] = []
    excluded: dict[str, int] = {}
    raw = valid = 0
    events = 0
    slot_lengths: set[int] = set()
    temps: list[float] = []
    with path.open("r", encoding=detect(path), newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            raw += 1
            values = []
            for token in row[5].split(":"):
                token = token.strip()
                if token == "":
                    continue
                values.append(float(token))
            slot_lengths.add(len(values))
            first_zero = next((i for i, v in enumerate(values) if v == 0.0), None)
            row_kept_idx: list[int] = []
            row_kept_values: list[float] = []
            for i, value in enumerate(values):
                if first_zero is not None and i < first_zero:
                    reason = "NEAR_FIELD"
                elif not math.isfinite(value):
                    reason = "INVALID_VALUE"
                else:
                    start = FIRST_M + i * STEP_M
                    end = start + STEP_M
                    if end <= BLIND_M or start < BLIND_M < end:
                        reason = "NEAR_FIELD"
                    elif end <= CUTOFF_M:
                        reason = None
                        row_kept_idx.append(i)
                        row_kept_values.append(value)
                    elif start < CUTOFF_M < end:
                        reason = "CROSS_BOUNDARY_INTERVAL_EXCLUDED"
                    else:
                        reason = "OUT_OF_RANGE_MANUAL_CUTOFF"
                if reason:
                    excluded[reason] = excluded.get(reason, 0) + 1
            if row_kept_idx:
                valid += 1
                kept.extend(row_kept_values)
                run = 0
                previous = None
                for idx, value in zip(row_kept_idx, row_kept_values):
                    if value >= EVENT_THRESHOLD:
                        run = run + 1 if previous is not None and idx == previous + 1 else 1
                        previous = idx
                        if run == EVENT_MIN_BINS:
                            events += 1
                    else:
                        run = 0
                        previous = None
                temps.append(float(row[3]) if row[3] else 22.0)
            if raw >= limit:
                break
    return {
        "raw_records": raw,
        "valid_records": valid,
        "kept_samples": len(kept),
        "kept_sum": round(sum(kept), 9),
        "kept_mean": round(statistics.fmean(kept), 9) if kept else None,
        "kept_median": statistics.median(kept) if kept else None,
        "candidate_events": events,
        "excluded_by_reason": dict(sorted(excluded.items())),
        "signal_slots_per_record": sorted(slot_lengths)[0] if len(slot_lengths) == 1 else None,
        "water_temp_records": len(temps),
    }


def service_recompute(device_id: str, date: str, path: Path, limit: int) -> dict:
    from app import create_app
    from app.db import connect
    from app.services import daily_stats as ds
    from app.services import distance_mapping as dm

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "verify.db"
        create_app(db)
        conn = connect(db)
        dm.register_mapping(conn, dm.DistanceMapping(
            device_id=device_id, range_m=37.5, point_count=1000,
            sample_mode=dm.SAMPLE_MODE_INTERVAL, first_sample_distance_m=FIRST_M,
            sample_interval_m=STEP_M, support_status=dm.SUPPORT_CONFIRMED,
            evidence="独立复算临时映射", source="VERIFY"), operator="verify")
        conn.commit()
        stat = ds.compute_daily_statistics(conn, device_id, date, path,
                                           run_id="VERIFY-TEMP", limit=limit)
        conn.close()
    return stat


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--file", type=Path)
    parser.add_argument("--limit", type=int, default=2000)
    args = parser.parse_args()
    path = args.file or (ROOT / "01_ORIGINAL_DATA" / "FISHFINDER" / args.device
                         / f"探鱼-{args.device}_{args.date}.csv")
    independent = independent_recompute(path, args.limit)
    service = service_recompute(args.device, args.date, path, args.limit)
    histogram = json.loads(service["signal_histogram_json"])
    actual = {
        "raw_records": service["raw_records"],
        "valid_records": service["valid_records"],
        "kept_samples": service["kept_samples"],
        "kept_sum": round(sum(float(k) * v for k, v in histogram.items()), 6),
        "kept_mean": round(service["signal_mean"], 9),
        "kept_median": service["signal_median"],
        "candidate_events": service["candidate_events"],
        "excluded_by_reason": json.loads(service["excluded_by_reason_json"]),
        "signal_slots_per_record": service["signal_slots_per_record"],
        "water_temp_records": service["water_temp_records"],
    }
    independent["kept_sum"] = round(independent["kept_sum"], 6)
    failed = []
    print(f"独立复算 vs S03 服务：{args.device} {args.date} 前 {args.limit} 行")
    for key in independent:
        left, right = independent[key], actual[key]
        ok = left == right if not isinstance(left, float) else math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-6)
        if isinstance(left, dict):
            ok = left == right
        print(f"  {key}: 独立={left} 服务={right} {'PASS' if ok else 'FAIL'}")
        if not ok:
            failed.append(key)
    print("RESULT:", "PASS" if not failed else "FAIL:" + ",".join(failed))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
