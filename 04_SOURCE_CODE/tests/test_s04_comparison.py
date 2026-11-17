# -*- coding: utf-8 -*-
"""S04 比较、日期矩阵、历史基线与自动总结。"""
from __future__ import annotations

import math

import pytest

from app.services import comparison as cmp
from s04_helpers import seed_stat

DUR = 85000.0


def _rate(events: int) -> float:
    return events / (DUR / 3600)


def test_compare_direction_difference_and_effective_sample(s03_conn):
    seed_stat(s03_conn, "2000", "2026-05-01", events=20, duration=DUR)
    seed_stat(s03_conn, "2000", "2026-05-02", events=10, duration=DUR)
    selection = cmp.select(s03_conn, cmp.Criteria(devices=("2000",), dates=("2026-05-01", "2026-05-02")))
    a, b = selection["windows"]
    seed_a = dict(a, candidate_events=20, candidate_event_rate_per_hour=_rate(20))
    seed_b = dict(b, candidate_events=10, candidate_event_rate_per_hour=_rate(10))
    result = cmp.compare_windows(seed_a, seed_b, label="test")
    primary = result["primary"]
    assert primary["result"] == "HIGHER"
    assert math.isclose(primary["difference"], _rate(10), rel_tol=1e-9)
    assert math.isclose(primary["change_percent"], 100.0, rel_tol=1e-9)
    assert primary["effective_n"] == a["kept_samples"]
    assert primary["coverage"] == a["coverage_ratio"]
    assert "不得直接归因" in result["disclaimer"]


def test_reference_zero_gives_na_percent_with_explanation(s03_conn):
    seed_stat(s03_conn, "2000", "2026-05-01", events=10, duration=DUR)
    seed_stat(s03_conn, "2000", "2026-05-02", events=0, duration=DUR, signal_mean=0.0)
    selection = cmp.select(s03_conn, cmp.Criteria(devices=("2000",), dates=("2026-05-01", "2026-05-02")))
    result = cmp.compare_windows(selection["windows"][0], selection["windows"][1])
    primary = result["primary"]
    assert primary["reference"] == 0
    assert primary["change_percent"] is None
    assert "参考值为 0" in primary["pct_note"] and "K27" in primary["pct_note"]
    assert primary["result"] == "HIGHER"


def test_matrix_eight_cases_with_seven_synthetic_days(s03_conn):
    events = [2, 4, 6, 8, 10, 12, 14]
    for i, count in enumerate(events, start=1):
        seed_stat(s03_conn, "2000", f"2026-06-{i:02d}", events=count, duration=DUR)
    selection = cmp.select(s03_conn, cmp.Criteria(
        devices=("2000",), start_date="2026-06-01", end_date="2026-06-07"))
    matrix = cmp.date_comparison_matrix(selection)
    assert matrix["required_case_count"] == 8
    assert all(c["status"] == "OK" for c in matrix["cases"])
    by_label = {c["label"]: c for c in matrix["cases"]}
    assert math.isclose(by_label["D4_vs_D1"]["primary"]["reference"], _rate(2))
    assert math.isclose(by_label["D4_vs_prev3_mean"]["primary"]["reference"],
                        sum(_rate(e) for e in events[:3]) / 3, rel_tol=1e-9)
    assert math.isclose(by_label["D7_vs_prev6_mean"]["primary"]["reference"],
                        sum(_rate(e) for e in events[:6]) / 6, rel_tol=1e-9)
    assert by_label["D1_vs_D2"]["reference_dates"] == ["2026-06-02"]
    assert by_label["D5_vs_prev4_mean"]["reference_dates"] == [
        "2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"]


def test_matrix_insufficient_dates_never_fabricate(s03_conn):
    for i in range(1, 5):
        seed_stat(s03_conn, "2000", f"2026-07-{i:02d}")
    selection = cmp.select(s03_conn, cmp.Criteria(devices=("2000",), day_count=4,
                                                  end_date="2026-07-04"))
    matrix = cmp.date_comparison_matrix(selection)
    insufficient = [c for c in matrix["cases"] if c["status"] == "INSUFFICIENT_DATES"]
    assert {c["case"] for c in insufficient} == {"D5_vs_D3", "D5_vs_prev4_mean", "D7_vs_prev6_mean"}
    assert all("不伪造" in c["detail"] for c in insufficient)


def test_baseline_valid_excludes_missing_and_calendar_reports_shortfall(s03_conn):
    for day in ("2026-08-01", "2026-08-02", "2026-08-04", "2026-08-05"):
        seed_stat(s03_conn, "2000", day, events=6, duration=DUR)
    seed_stat(s03_conn, "2000", "2026-08-03", status="MISSING", valid_records=0,
              kept_samples=0, events=0, duration=0.0, coverage=0.0)
    criteria = cmp.Criteria(devices=("2000",))
    valid = cmp.build_baseline(s03_conn, criteria, "2026-08-05", n=3, mode="valid")
    group = valid["devices"]["2000"]
    assert [m["observed_date"] for m in group["members"]] == [
        "2026-08-01", "2026-08-02", "2026-08-04"]
    assert group["shortfall"] == 0
    assert math.isclose(group["aggregate_rate_per_hour"], 18 / (3 * DUR / 3600), rel_tol=1e-9)
    assert "Σ候选事件" in valid["denominator_table"]["aggregate_rate_per_hour"]

    calendar = cmp.build_baseline(s03_conn, criteria, "2026-08-05", n=3, mode="calendar")
    group = calendar["devices"]["2000"]
    assert [m["observed_date"] for m in group["members"]] == ["2026-08-02", "2026-08-04"]
    assert group["shortfall"] == 1
    assert any(e["reason"] == "INVALID_BASELINE_DAY" for e in calendar["excluded"])


def test_all_history_range_and_rolling_baselines(s03_conn):
    for i in (1, 2, 4, 5):
        seed_stat(s03_conn, "2000", f"2026-09-{i:02d}", events=i, duration=DUR)
    criteria = cmp.Criteria(devices=("2000",))
    all_history = cmp.build_baseline(s03_conn, criteria, "2026-09-05", mode="all")
    assert all_history["devices"]["2000"]["n_members"] == 3  # 参考日当天不计入基线
    ranged = cmp.build_baseline(s03_conn, criteria, "2026-09-05", mode="range",
                                start="2026-09-02", end="2026-09-04")
    assert [m["observed_date"] for m in ranged["devices"]["2000"]["members"]] == [
        "2026-09-02", "2026-09-04"]
    rolling = cmp.rolling_baselines(s03_conn, criteria,
                                    ["2026-09-04", "2026-09-05"], n=2)
    assert [r["baseline"]["devices"]["2000"]["n_members"] for r in rolling] == [2, 2]


def test_empty_baseline_raises_with_reason(s03_conn):
    with pytest.raises(cmp.ComparisonEmptyError, match="无有效观测日"):
        cmp.build_baseline(s03_conn, cmp.Criteria(devices=("2001",)),
                           "2026-10-01", n=3, mode="valid")


def test_histogram_stats_use_counts_not_naive_mean(s03_conn):
    seed_stat(s03_conn, "2000", "2026-10-01", histogram={"1": 2, "3": 2})
    selection = cmp.select(s03_conn, cmp.Criteria(devices=("2000",), dates=("2026-10-01",)))
    window = selection["windows"][0]
    assert window["signal_mean"] == 2.0
    assert window["signal_p95"] == 3.0


def test_summary_includes_uncertainty_and_missing_note(s03_conn):
    seed_stat(s03_conn, "2000", "2026-11-01", events=4, duration=DUR)
    seed_stat(s03_conn, "2000", "2026-11-02", events=8, duration=DUR)
    seed_stat(s03_conn, "2000", "2026-11-03", status="MISSING", valid_records=0,
              kept_samples=0, events=0, duration=0.0, coverage=0.0)
    selection = cmp.select(s03_conn, cmp.Criteria(
        devices=("2000",), start_date="2026-11-01", end_date="2026-11-03"))
    matrix = cmp.date_comparison_matrix(selection)
    summary = cmp.summarize(selection, [c for c in matrix["cases"] if c.get("status") == "OK"])
    assert "不等同于真实鱼类数量变化" in summary["markdown"]
    assert "缺测/无效说明" in summary["markdown"]
    assert summary["missing_count"] >= 1
    assert "S07" in summary["markdown"]


def test_device_comparison_same_day_and_missing_pair(s03_conn):
    seed_stat(s03_conn, "2000", "2026-10-15", events=10, duration=DUR)
    seed_stat(s03_conn, "2001", "2026-10-15", events=5, duration=DUR)
    selection = cmp.select(s03_conn, cmp.Criteria(dates=("2026-10-15",)))
    matrix = cmp.device_comparison_matrix(selection, reference_device="2000")
    ok = [c for c in matrix["cases"] if c["status"] == "OK"]
    missing = [c for c in matrix["cases"] if c["status"] == "MISSING_PAIR"]
    assert len(ok) == 1 and ok[0]["device_id"] == "2001"
    assert math.isclose(ok[0]["primary"]["difference"], -_rate(5), rel_tol=1e-9)
    assert ok[0]["primary"]["result"] == "LOWER"
    assert len(missing) >= 1  # 未上传设备不补 0


def test_timezone_bounds_and_unknown_timezone(s03_conn):
    seed_stat(s03_conn, "2000", "2026-02-01")
    selection = cmp.select(s03_conn, cmp.Criteria(
        devices=("2000",), dates=("2026-02-01",), hour_start=22, hour_end=2,
        timezone="Asia/Shanghai"))
    window = selection["windows"][0]
    assert window["local_window_start"] == "2026-02-01T22:00:00"
    assert window["local_window_end"] == "2026-02-02T02:00:00"
    assert window["utc_window_start"] == "2026-02-01T14:00:00Z"
    assert window["utc_window_end"] == "2026-02-01T18:00:00Z"
    with pytest.raises(cmp.ComparisonValidationError, match="不支持的时区"):
        cmp.select(s03_conn, cmp.Criteria(timezone="Mars/Olympus"))


def test_include_invalid_keeps_na_not_zero(s03_conn):
    seed_stat(s03_conn, "2000", "2026-12-01", status="BLOCKED", valid_records=0,
              kept_samples=0, events=0, duration=0.0, coverage=0.0)
    selection = cmp.select(s03_conn, cmp.Criteria(
        devices=("2000",), dates=("2026-12-01",), include_invalid=True))
    window = selection["windows"][0]
    assert window["candidate_events"] is None and window["kept_samples"] is None
    assert window["coverage_ratio"] is None
