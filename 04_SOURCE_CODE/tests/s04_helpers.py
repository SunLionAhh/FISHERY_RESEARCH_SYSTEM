# -*- coding: utf-8 -*-
"""S04 测试夹具：向临时库写入可控的 S03 统计行（不触碰原始 CSV）。"""
from __future__ import annotations

import json
from typing import Iterable


def hourly(valid: Iterable[int] | None = None, events: Iterable[int] | None = None,
           kept: Iterable[int] | None = None) -> str:
    def arr(values, default=0):
        out = list(values or [])
        return (out + [default] * 24)[:24]
    return json.dumps({
        "valid_records": arr(valid, 10),
        "candidate_events": arr(events, 0),
        "kept_samples": arr(kept, 100),
    })


def seed_stat(conn, device_id: str, observed_date: str, *,
              status: str = "COMPLETE", valid_records: int = 240,
              kept_samples: int = 2400, events: int = 12,
              duration: float = 85000.0, coverage: float = 0.984,
              signal_mean: float = 5.0, signal_median: float = 0.0,
              histogram: dict | None = None,
              hourly_valid=None, hourly_events=None, hourly_kept=None,
              water_temp_mean: float = 22.0, stat_id: int | None = None):
    columns = (
        "device_id", "observed_date", "status", "observation_status", "upload_status",
        "algorithm_version", "raw_records", "valid_records", "invalid_records",
        "fully_masked_records", "timestamp_resolution_s", "valid_observation_duration_s",
        "planned_window_s", "coverage_ratio", "valid_record_ratio", "signal_slots_per_record",
        "raw_signal_slots", "kept_samples", "excluded_samples", "signal_mean", "signal_median",
        "signal_stddev", "hourly_activity_json", "missing_intervals_json",
        "signal_histogram_json", "excluded_by_reason_json", "candidate_events",
        "candidate_event_rate_per_hour", "water_temp_mean", "water_temp_records",
        "missing_interval_count", "created_at",
    )
    observation_status = ("MISSING" if status == "MISSING" else
                          "QC_FAILED" if status == "QC_FAILED" else
                          "UNKNOWN" if status == "UNKNOWN" else "COMPLETE")
    rate = events / (duration / 3600) if duration else None
    if hourly_valid is None:
        hourly_valid = [valid_records // 24 + (1 if i < valid_records % 24 else 0) for i in range(24)]
    if hourly_kept is None:
        hourly_kept = [kept_samples // 24 + (1 if i < kept_samples % 24 else 0) for i in range(24)]
    if hourly_events is None:
        hourly_events = [0] * 12 + [events] + [0] * (24 - 13)
    values = (
        device_id, observed_date, status, observation_status, "NORMAL", "DAILY_STATS_V1",
        valid_records, valid_records, 0, 0, 60, duration, 86400, coverage, 0.98,
        1000, 1000000, kept_samples, 0, signal_mean, signal_median, 10.0,
        hourly(hourly_valid, hourly_events, hourly_kept), "[]",
        json.dumps(histogram or {"0": 60, "10": 40}), "{}", events, rate,
        water_temp_mean, valid_records, 0, "2026-11-17T00:00:00+00:00",
    )
    if stat_id is not None:
        columns = ("stat_id",) + columns
        values = (stat_id,) + values
    placeholders = ",".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO daily_statistics ({','.join(columns)}) VALUES ({placeholders})", values)
    conn.commit()
