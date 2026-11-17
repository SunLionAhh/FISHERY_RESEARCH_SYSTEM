# -*- coding: utf-8 -*-
"""S04 筛选：任意日期/天数/小时窗/跨午夜/站位/空集与端点口径。"""
from __future__ import annotations

import pytest

from app.services import comparison as cmp
from s04_helpers import seed_stat


def _arr(**kwargs):
    values = [0] * 24
    for index, value in kwargs.items():
        values[int(index.lstrip("_"))] = value
    return values


def test_select_range_all_devices(s03_conn):
    for day in ("2026-01-01", "2026-01-02", "2026-01-03"):
        seed_stat(s03_conn, "2000", day)
        seed_stat(s03_conn, "2001", day)
    result = cmp.select(s03_conn, cmp.Criteria(start_date="2026-01-01", end_date="2026-01-03"))
    assert result["window_count"] == 6
    assert set(result["resolved_devices"]) == {"2000", "2001", "2002", "2003", "2005"}
    assert result["resolved_dates"] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert all(e["reason"] == "NO_STAT_ROW" for e in result["excluded"])
    assert "两端包含" in result["endpoint_rule"]


def test_explicit_non_contiguous_dates(s03_conn):
    for day in ("2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"):
        seed_stat(s03_conn, "2000", day)
    result = cmp.select(s03_conn, cmp.Criteria(
        devices=("2000",), dates=("2026-01-01", "2026-01-03")))
    assert result["resolved_dates"] == ["2026-01-01", "2026-01-03"]
    assert [w["observed_date"] for w in result["windows"]] == result["resolved_dates"]


def test_day_count_calendar_excludes_missing_but_valid_mode_skips_it(s03_conn):
    for day in ("2026-01-01", "2026-01-02", "2026-01-04", "2026-01-05"):
        seed_stat(s03_conn, "2000", day)
    seed_stat(s03_conn, "2000", "2026-01-03", status="MISSING", valid_records=0,
              kept_samples=0, events=0, duration=0.0, coverage=0.0)
    calendar = cmp.select(s03_conn, cmp.Criteria(
        devices=("2000",), day_count=3, end_date="2026-01-05", day_count_mode="calendar"))
    assert calendar["resolved_dates"] == ["2026-01-03", "2026-01-04", "2026-01-05"]
    assert calendar["window_count"] == 2
    assert any(e["reason"] == "INVALID_OBSERVATION_DAY" for e in calendar["excluded"])
    valid = cmp.select(s03_conn, cmp.Criteria(
        devices=("2000",), day_count=3, end_date="2026-01-05", day_count_mode="valid"))
    assert valid["resolved_dates"] == ["2026-01-02", "2026-01-04", "2026-01-05"]
    assert valid["window_count"] == 3
    assert all(w["status"] != "MISSING" for w in valid["windows"])


def test_cross_midnight_window_assigns_hours_once(s03_conn):
    seed_stat(s03_conn, "2000", "2026-02-01", hourly_events=_arr(_22=3, _23=4, _0=1, _1=2))
    seed_stat(s03_conn, "2000", "2026-02-02", hourly_events=_arr(_22=5, _23=6, _0=9, _1=8))
    seed_stat(s03_conn, "2000", "2026-02-03", hourly_events=_arr(_0=7, _1=8))
    result = cmp.select(s03_conn, cmp.Criteria(
        devices=("2000",), start_date="2026-02-01", end_date="2026-02-03",
        hour_start=22, hour_end=2))
    first, second = result["windows"][0], result["windows"][1]
    assert first["window_kind"] == second["window_kind"] == "cross_midnight"
    assert first["window_hours"] == [22, 23, 0, 1]
    assert first["candidate_events"] == 24  # 起始日 22/23=3+4 + 次日 0/1=9+8；0/1 不取自起始日
    assert second["candidate_events"] == 26  # 5+6（02-02 的 22/23）+7+8（02-03 的 0/1）
    assert first["window_next_date"] == "2026-02-02" and not first["partial"]
    assert not second["partial"]


def test_cross_midnight_without_next_day_is_partial(s03_conn):
    seed_stat(s03_conn, "2000", "2026-02-01", hourly_events=_arr(_22=3, _23=4, _0=1, _1=2))
    result = cmp.select(s03_conn, cmp.Criteria(
        devices=("2000",), dates=("2026-02-01",), hour_start=22, hour_end=2))
    window = result["windows"][0]
    assert window["partial"] is True and window["window_hours"] == [22, 23]
    assert window["candidate_events"] == 7
    assert any("次日" in n for n in window["notes"])


def test_full_hour_range_uses_exact_s03_coverage(s03_conn):
    seed_stat(s03_conn, "2000", "2026-03-01", duration=80000.0, coverage=0.9259)
    result = cmp.select(s03_conn, cmp.Criteria(
        devices=("2000",), dates=("2026-03-01",), hour_start=0, hour_end=24))
    window = result["windows"][0]
    assert window["window_kind"] == "full_day"
    assert window["estimated"] is False
    assert window["valid_observation_duration_s"] == 80000.0
    assert window["coverage_ratio"] == 0.9259


def test_intraday_window_marks_estimated_and_na_distribution(s03_conn):
    seed_stat(s03_conn, "2000", "2026-03-01", hourly_valid=_arr(**{str(h): 10 for h in range(24)}))
    result = cmp.select(s03_conn, cmp.Criteria(
        devices=("2000",), dates=("2026-03-01",), hour_start=6, hour_end=18))
    window = result["windows"][0]
    assert window["estimated"] is True
    assert window["signal_mean"] is None and window["water_temp_mean"] is None
    assert any("estimated=true" in n for n in window["notes"])


def test_station_filter_requires_registered_station(s03_conn):
    s03_conn.execute("INSERT INTO stations (station_id,name,created_at) VALUES ('S1','站位一','2026-01-01')")
    s03_conn.execute("UPDATE devices SET station_id='S1' WHERE device_id='2000'")
    s03_conn.commit()
    seed_stat(s03_conn, "2000", "2026-04-01")
    seed_stat(s03_conn, "2001", "2026-04-01")
    result = cmp.select(s03_conn, cmp.Criteria(stations=("S1",), dates=("2026-04-01",)))
    assert result["resolved_devices"] == ["2000"]
    with pytest.raises(cmp.ComparisonValidationError, match="未知站位"):
        cmp.select(s03_conn, cmp.Criteria(stations=("S9",), dates=("2026-04-01",)))


def test_unknown_device_and_empty_selection(s03_conn):
    with pytest.raises(cmp.ComparisonValidationError, match="未知设备"):
        cmp.select(s03_conn, cmp.Criteria(devices=("2004",), dates=("2026-04-01",)))
    with pytest.raises(cmp.ComparisonEmptyError, match="尚无 daily_statistics|筛选结果为空"):
        cmp.select(s03_conn, cmp.Criteria(devices=("2000",), dates=("2026-02-28",)))


def test_invalid_hour_and_missing_hour_boundary(s03_conn):
    with pytest.raises(cmp.ComparisonValidationError, match="同时提供"):
        cmp.select(s03_conn, cmp.Criteria(hour_start=6))
    with pytest.raises(cmp.ComparisonValidationError, match="不得相同"):
        cmp.select(s03_conn, cmp.Criteria(hour_start=6, hour_end=6))
