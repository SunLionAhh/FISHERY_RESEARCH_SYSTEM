# -*- coding: utf-8 -*-
"""S06 测试夹具：15 分钟合成声学 CSV、S03 统计行与 GPS。"""
from __future__ import annotations

import csv
from pathlib import Path

from app.services import daily_stats as ds


def write_intraday_csv(path: Path, device: str, observed_date: str,
                       *, active_slots: set[int] | None = None,
                       skip_slots: set[int] | None = None,
                       event_value: float = 210.0) -> Path:
    """96 个 15 分钟行；区内保留槽位固定 108 个，事件段由 active_slots 指定。"""
    active_slots = active_slots or set()
    skip_slots = skip_slots or set()
    header = ["序号", "日期", "水深(m)", "水温(°C)", "量程(M)", "数据串"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for slot in range(96):
            if slot in skip_slots:
                continue
            minute = slot * 15
            values = [255.0] * 17 + [0.0] + [70.0] * 100 + [0.0] * 882
            if slot in active_slots:
                values[18:21] = [event_value] * 3
            signal = ":".join(f"{v:.1f}" for v in values) + ":"
            writer.writerow([slot + 1, f"{observed_date} {minute // 60:02d}:{minute % 60:02d}:00",
                             "5.0", "22.0", "37.5", signal])
    return path


def seed_stat_and_file(conn, tmp_path: Path, device: str, observed_date: str, **kwargs):
    path = write_intraday_csv(
        tmp_path / "01_ORIGINAL_DATA" / "FISHFINDER" / device / f"探鱼-{device}_{observed_date}.csv",
        device, observed_date, **kwargs)
    run_id = f"S06-TEST-{device}-{observed_date}"
    conn.execute(
        "INSERT OR IGNORE INTO analysis_runs (run_id,device_id,params_snapshot_json,status,created_at) "
        "VALUES (?,?,?,?,?)", (run_id, device, "{}", "PENDING", "2026-10-31T00:00:00+00:00"))
    conn.commit()
    stat = ds.compute_daily_statistics(conn, device, observed_date, path, run_id=run_id)
    ds.insert_stat_row(conn, stat)
    conn.commit()
    return path


def seed_position(conn, device: str, *, lat: float = 27.9934, lon: float = 121.2117,
                  crs: str | None = None):
    version = conn.execute(
        "SELECT COALESCE(MAX(version),0)+1 v FROM device_positions WHERE device_id=?",
        (device,)).fetchone()["v"]
    conn.execute(
        "INSERT INTO device_positions (device_id,version,longitude_deg,latitude_deg,"
        "coordinate_reference_system,position_source,effective_from,created_at,created_by) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (device, version, lon, lat, crs, "S06_TEST_SYNTHETIC", "2026-10-31",
         "2026-10-31T00:00:00+00:00", "pytest"))
    conn.commit()
