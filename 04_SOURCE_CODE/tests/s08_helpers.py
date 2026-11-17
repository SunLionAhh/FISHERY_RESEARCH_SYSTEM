# -*- coding: utf-8 -*-
"""S08 测试助手：可控环境观测（本地时间 + UTC 时间并列）。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta


def seed_environment(conn, variable: str, rows, *, source_id: str = "S08_TEST_ENV",
                     kind: str = "AUTO", quality: str = "OK", device_id: str | None = None,
                     batch_id: str = "S08_TEST_BATCH"):
    conn.execute(
        "INSERT OR IGNORE INTO environment_source (source_id,name,kind,provider,"
        "observed_or_forecast,units_json,quality_note,created_at,actor) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (source_id, "S08 测试环境源", kind, "pytest", "OBSERVED", "{}",
         "测试数据", "2026-11-17T00:00:00+00:00", "pytest"))
    conn.execute(
        "INSERT OR IGNORE INTO environment_import_batch (batch_id,source_id,file_name,file_sha256,"
        "file_size_bytes,file_kind,field_mapping_json,timezone,row_count,accepted_count,"
        "rejected_count,duplicate_count,issue_summary_json,status,created_at,actor) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (batch_id, source_id, "s08_test.csv", "TEST", 1, "CSV", "{}", "Asia/Shanghai",
         len(rows), len(rows), 0, 0, "{}", "IMPORTED", "2026-11-17T00:00:00+00:00", "pytest"))
    for local_stamp, value in rows:
        local = datetime.strptime(local_stamp, "%Y-%m-%dT%H:%M:%S")
        utc = (local - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "INSERT OR REPLACE INTO environment_observation (batch_id,source_id,variable,"
            "location_key,device_id,observed_at,observed_at_utc,timezone,value,unit,value_si,"
            "quality_flag,raw_row_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (batch_id, source_id, variable, "TEST", device_id, local_stamp, utc,
             "Asia/Shanghai", value, "TEST", value, quality, json.dumps({"value": value})))
    conn.commit()
