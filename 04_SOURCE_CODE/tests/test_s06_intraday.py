# -*- coding: utf-8 -*-
"""S06 日内 15 分钟格、聚合、昼夜锚定、峰谷形态与典型日。"""
from __future__ import annotations

import pytest

from app.services import intraday as it
from s06_helpers import seed_position, seed_stat_and_file

ACTIVE = set(range(24, 36)) | set(range(64, 76))  # 06:00—09:00、16:00—19:00 高值


def _grid(s03_conn, tmp_path, date="2026-10-31", expected=96, coverage_mode="slot", **kwargs):
    seed_stat_and_file(s03_conn, tmp_path, "2000", date, **kwargs)
    assert it.build_grid(s03_conn, "2000", date, project_root=tmp_path,
                         coverage_mode=coverage_mode) == expected
    return it.load_grid(s03_conn, ["2000"], [date])


def test_grid_uses_s03_mask_and_is_idempotent(s03_conn, tmp_path):
    grid = _grid(s03_conn, tmp_path, active_slots=ACTIVE)
    assert len(grid) == 96
    active = [c for c in grid if c["candidate_events"] > 0]
    assert {it._slot_index(c) for c in active} == ACTIVE
    assert all(c["kept_samples"] == 108 for c in grid)
    assert it.build_grid(s03_conn, "2000", "2026-10-31", project_root=tmp_path,
                         coverage_mode="slot") == 96
    assert s03_conn.execute("SELECT COUNT(*) n FROM s06_time_grid").fetchone()["n"] == 96


def test_aggregate_and_low_coverage_flag(s03_conn, tmp_path):
    grid = _grid(s03_conn, tmp_path, active_slots=ACTIVE, skip_slots={5, 6, 7},
                 expected=93, coverage_mode="timestamp")
    grid15 = it.aggregate(grid, 15)
    hourly = it.aggregate(grid, 60)
    two_hour = it.two_hour_groups(hourly)
    assert len(grid15) == 93 and len(hourly) == 24 and len(two_hour) == 12
    assert sum(c["candidate_events"] for c in grid15) == sum(c["candidate_events"] for c in grid)
    assert sum(c["candidate_events"] for c in hourly) == sum(c["candidate_events"] for c in grid15)
    assert any(c["low_coverage"] for c in grid15)
    prof = it.daily_profile(hourly)["profiles"][0]
    assert len(prof["rate_per_hour"]) == 24 and 0 in prof["low_coverage_hours"]
    assert prof["rate_per_hour"][0] is None or prof["rate_per_hour"][0] >= 0


def test_solar_day_and_night_anchor(s03_conn, tmp_path):
    seed_position(s03_conn, "2000")  # 坐标系未声明
    grid = _grid(s03_conn, tmp_path, active_slots=ACTIVE)
    result = it.day_night(s03_conn, grid, ["2000"], ["2026-10-31", "2026-11-01"],
                          "Asia/Shanghai", 8.0)["results"][0]
    assert result["status"] == "PROVISIONAL"
    assert result["crs_status"] == "UNDECLARED"
    sunrise = result["solar"]["sunrise"]
    hour = int(sunrise[11:13])
    assert 5 <= hour <= 7
    assert result["night_anchor_date"] == "2026-10-31"
    assert result["night_next_morning"]["end"].startswith("2026-11-01")
    windows = it.solar_windows(s03_conn, grid, ["2000"], ["2026-10-31"], "Asia/Shanghai", 8.0)
    assert windows["results"][0]["status"] == "PROVISIONAL"


def test_missing_coordinates_block_astronomy(s03_conn, tmp_path):
    s03_conn.execute("DELETE FROM device_positions WHERE device_id='2000'")
    s03_conn.commit()
    grid = _grid(s03_conn, tmp_path)
    grid += _grid(s03_conn, tmp_path, date="2026-11-01")
    result = it.day_night(s03_conn, grid, ["2000"], ["2026-10-31"], "Asia/Shanghai", 8.0)
    assert result["results"][0]["status"] == "BLOCKED"
    assert "禁止伪造" in result["results"][0]["reason"]


def test_peak_high_low_rebound_and_not_identifiable(s03_conn, tmp_path):
    grid = _grid(s03_conn, tmp_path, active_slots=ACTIVE)
    item = it.peaks(grid, ["2000"], ["2026-10-31"])["results"][0]
    assert item["pattern"] == "HIGH_LOW_REBOUND"
    assert item["high_window"][0] == 24 * 15 and item["rebound_window"][0] >= 64 * 15
    assert item["duration_minutes"]["high"] > 0
    flat = it.peaks(it.load_grid(s03_conn, ["2000"], ["2026-10-31"]), ["2000"], ["2026-10-31"])
    assert flat["results"][0]["pattern"] == "HIGH_LOW_REBOUND"

    for date in ("2026-11-01", "2026-11-02"):
        seed_stat_and_file(s03_conn, tmp_path, "2000", date, active_slots={40})
        it.build_grid(s03_conn, "2000", date, project_root=tmp_path, coverage_mode="slot")
    grid = it.load_grid(s03_conn, ["2000"], ["2026-11-01", "2026-11-02"])
    other = it.peaks(grid, ["2000"], ["2026-11-01"])["results"][0]
    assert other["pattern"] == "NOT_IDENTIFIABLE"
    assert "不强行给时段" in other["reason"]


def test_typical_day_min_days_and_equal_weighting(s03_conn, tmp_path):
    for date, slots in (("2026-11-03", ACTIVE), ("2026-11-04", ACTIVE),
                        ("2026-11-05", ACTIVE), ("2026-11-06", ACTIVE)):
        seed_stat_and_file(s03_conn, tmp_path, "2000", date, active_slots=slots)
        it.build_grid(s03_conn, "2000", date, project_root=tmp_path, coverage_mode="slot")
    hourly = it.aggregate(it.load_grid(s03_conn, ["2000"],
                                       ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]), 60)
    insufficient = it.typical_day(hourly[:24], min_days=3)
    enough = it.typical_day(hourly, min_days=3)
    assert all(row["status"] == "INSUFFICIENT_DAYS" for row in insufficient["hours"][:24])
    assert all(row["status"] == "OK" and row["n_effective_days"] == 4
               for row in enough["hours"] if 6 <= row["hour"] <= 8)
    assert it.period_typical(hourly, "weekday")["min_days"] == 2


def test_date_range_inclusive():
    assert it.date_range("2026-10-31", "2026-11-02") == [
        "2026-10-31", "2026-11-01", "2026-11-02"]
    with pytest.raises(ValueError):
        it.date_range("2026-11-02", "2026-10-31")


def test_web_intraday_routes(client, s03_conn, tmp_path):
    seed_stat_and_file(s03_conn, tmp_path, "2000", "2026-10-31", active_slots=ACTIVE)
    assert client.get("/intraday").status_code == 200
    response = client.post("/intraday", data={
        "devices": "2000", "start_date": "2026-10-31", "end_date": "2026-10-31",
        "timezone": "Asia/Shanghai", "coverage_mode": "slot", "name": "S06 Web 测试"})
    assert response.status_code == 302
    run_id = response.headers["Location"].rsplit("/", 1)[-1]
    detail = client.get(f"/intraday/{run_id}")
    assert detail.status_code == 200 and b"HIGH_LOW_REBOUND" in detail.data
