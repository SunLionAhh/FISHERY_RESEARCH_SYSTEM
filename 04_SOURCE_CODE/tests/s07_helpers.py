# -*- coding: utf-8 -*-
"""S07 测试助手：已导入登记、合成 15 分钟格与 S06 结果留痕。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def register_imported_file(conn, device_id: str, observed_date: str,
                           path: Path, project_root: Path):
    relative = path.relative_to(project_root).as_posix()
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    conn.execute(
        "INSERT OR REPLACE INTO file_registry (relative_path,file_name,device_id,observed_date,"
        "size_bytes,sha256,status,registered_at) VALUES (?,?,?,?,?,?,?,?)",
        (relative, path.name, device_id, observed_date, path.stat().st_size, sha,
         "IMPORTED", "2026-11-17T00:00:00+00:00"))
    conn.commit()
    return relative


def seed_grid(conn, device_id: str, observed_date: str, hourly_counts: list[int]):
    for hour, count in enumerate(hourly_counts):
        conn.execute(
            "INSERT OR REPLACE INTO s06_time_grid (device_id,observed_date,slot_start,slot_end,"
            "valid_records,candidate_events,kept_samples,distinct_seconds,coverage_ratio,"
            "source_file_sha,method_version,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (device_id, observed_date, f"{observed_date}T{hour:02d}:00:00",
             f"{observed_date}T{hour:02d}:59:59", 60, count, 1000, 900, 1.0,
             "TEST", "S07_TEST", "2026-11-17T00:00:00+00:00"))
    conn.commit()


def seed_s06_result(conn, run_id: str, devices, dates, differences):
    payload = {"scope": {"devices": devices, "dates": dates},
               "day_night": {"results": [
                   {"device_id": device, "observed_date": day,
                    "pair": {"difference": difference}}
                   for device, day, difference in zip(devices, dates, differences)]}}
    conn.execute(
        "INSERT OR REPLACE INTO s06_analysis_run (run_id,name,criteria_json,result_json,"
        "method_version,created_at,actor) VALUES (?,?,?,?,?,?,?)",
        (run_id, "S07 测试", "{}", json.dumps(payload), "S07_TEST",
         "2026-11-17T00:00:00+00:00", "pytest"))
    conn.commit()
