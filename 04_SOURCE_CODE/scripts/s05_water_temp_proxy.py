# -*- coding: utf-8 -*-
"""从 S03 每日统计派生水温代理 CSV（非独立环境观测，仅作同源描述）。"""
from __future__ import annotations

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from app.db import connect, ensure_database  # noqa: E402
from app.services import comparison as cmp  # noqa: E402
from app.services import daily_stats as ds  # noqa: E402


def main() -> None:
    conn = connect()
    ensure_database(conn)
    rows = [r for r in ds.all_latest_stats(conn)
            if r["status"] not in cmp.BASELINE_INVALID_STATUSES
            and r["water_temp_mean"] is not None]
    conn.close()
    out = Path(__file__).resolve().parents[2] / "10_TEST_REPORTS" / "s05_verification" / "water_temp_proxy.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    by_date = defaultdict(list)
    for row in rows:
        by_date[row["observed_date"]].append(row["water_temp_mean"])
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["observed_at", "water_temp_c", "unit", "quality_flag", "source_note"])
        for observed_date in sorted(by_date):
            writer.writerow([f"{observed_date}T12:00:00",
                             f"{statistics.fmean(by_date[observed_date]):.6f}",
                             "CELSIUS", "DERIVED",
                             "由同一声学 CSV 的水温列按日跨设备平均派生，不是独立环境观测"])
    print(out)


if __name__ == "__main__":
    main()
