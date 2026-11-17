# -*- coding: utf-8 -*-
"""S03 每日统计：口径、分子分母、0/NA、越界不变性与单台阻断。"""
from __future__ import annotations

import json
import statistics
from dataclasses import replace

import pytest

from app.services import daily_stats as ds
from app.services import distance_mapping as dm
from s03_helpers import POINTS, signal_values, write_custom_csv, write_fishfinder_csv


def _synthetic_values() -> list[int]:
    values = signal_values()
    # 盲区内首零前 17 格不进入统计；区内 17—124 格：0×8、210×5、10×95。
    return values


def test_metric_definitions_have_numerator_denominator_unit(tmp_path):
    assert len(ds.METRIC_DEFINITIONS) >= 20
    for metric in ds.METRIC_DEFINITIONS:
        assert metric.numerator and metric.denominator and metric.unit and metric.na_rule
    out = ds.write_metric_definitions_csv(tmp_path / "metric_definitions.csv")
    text = out.read_text(encoding="utf-8-sig")
    assert "metric_name,numerator,denominator,unit,na_rule,source" in text
    assert "coverage_ratio" in text and "NA" in text


def test_value_accumulator_exact_quantiles_and_population_stddev():
    acc = ds.ValueAccumulator()
    data = [0] * 8 + [210] * 5 + [10] * 95
    for value in data:
        acc.add(value)
    assert acc.n == 108
    assert acc.quantile_method == "EXACT_LINEAR_INTERPOLATION"
    assert acc.quantile(0.5) == 10.0
    assert acc.quantile(0.99) == 210.0
    assert acc.snapshot()["signal_mean"] == pytest.approx(statistics.fmean(data))
    assert acc.snapshot()["signal_stddev"] == pytest.approx(statistics.pstdev(data))
    assert acc.snapshot()["signal_min"] == 0 and acc.snapshot()["signal_max"] == 210
    assert sum(json.loads(acc.snapshot()["signal_histogram_json"]).values()) == 108


def test_value_accumulator_binned_fallback_for_high_cardinality():
    acc = ds.ValueAccumulator()
    for i in range(ds.MAX_DISTINCT_FOR_EXACT_QUANTILE + 50):
        acc.add(float(i))
    assert acc.quantile_method == "BINNED_1UNIT_LINEAR_INTERPOLATION"
    assert acc.quantile(0.5) is not None


def test_candidate_events_requires_contiguous_masked_bins():
    indices = [17, 18, 19, 20, 21, 25, 26, 27]  # 22—24 被掩码剔除，不连续
    values = [210] * 8
    assert ds.detect_candidate_events(indices, values) == 2
    assert ds.detect_candidate_events(indices[:2], values[:2]) == 0  # 不足 3 格
    assert ds.detect_candidate_events(indices, [10] * len(indices)) == 0  # 未达阈值


def test_status_precedence():
    assert ds.determine_status(ds.STATUS_COMPLETE, ds.UPLOAD_LATE) == ds.STATUS_UPLOADED_LATE
    assert ds.determine_status(ds.STATUS_MISSING, ds.UPLOAD_REPROCESSED) == ds.STATUS_MISSING
    assert ds.determine_status(ds.STATUS_QC_FAILED, ds.UPLOAD_LATE) == ds.STATUS_QC_FAILED
    assert ds.determine_status(ds.STATUS_PARTIAL, ds.UPLOAD_NORMAL) == ds.STATUS_PARTIAL


def test_compute_daily_statistics_from_synthetic_csv(s03_conn, tmp_path):
    path = write_fishfinder_csv(tmp_path / "探鱼-2000_2027-01-01.csv", "2000", "2027-01-01")
    row = ds.compute_daily_statistics(s03_conn, "2000", "2027-01-01", path, run_id="RUN-SYNTH-001")
    assert row["raw_records"] == 3 and row["valid_records"] == 3
    assert row["kept_samples"] == 3 * 108
    assert row["candidate_events"] == 3  # 每行一个连续 5 格事件
    assert row["candidate_event_rate_per_hour"] == pytest.approx(3600.0)  # 3 次 / 3 秒
    assert row["timestamp_resolution_s"] == 1
    assert row["coverage_ratio"] == pytest.approx(3 / 86400)
    assert row["signal_median"] == 10.0
    assert row["water_temp_mean"] == pytest.approx(22.0)
    assert row["near_field_excluded_samples"] > 0
    import json
    reasons = json.loads(row["excluded_by_reason_json"])
    assert dm.REASON_NEAR_FIELD in reasons and dm.REASON_OUT_OF_RANGE in reasons
    assert row["bottom_excluded_samples"] == 0  # S07 前预留，不冒充实测
    hourly = json.loads(row["hourly_activity_json"])
    assert hourly["valid_records"][1] == 1 and hourly["valid_records"][2] == 0
    assert row["missing_interval_count"] >= 2  # 01:00→03:00 断档 + 首尾缺口
    assert row["status"] == ds.STATUS_PARTIAL


def test_zero_event_is_zero_but_no_valid_observation_is_na(s03_conn, tmp_path):
    path = write_fishfinder_csv(tmp_path / "探鱼-2000_2027-01-02.csv", "2000", "2027-01-02",
                                event=False)
    row = ds.compute_daily_statistics(s03_conn, "2000", "2027-01-02", path, run_id="RUN-SYNTH-002")
    assert row["valid_records"] == 3
    assert row["candidate_events"] == 0  # 区内有效但无候选 → 真实 0
    assert row["signal_median"] == 10.0

    context = replace(ds.resolve_stat_context(s03_conn, "2000"), cutoff_m=0.6)
    path2 = write_fishfinder_csv(tmp_path / "探鱼-2000_2027-01-03.csv", "2000", "2027-01-03")
    row2 = ds.compute_daily_statistics(s03_conn, "2000", "2027-01-03", path2,
                                       run_id="RUN-SYNTH-003", context=context)
    assert row2["valid_records"] == 0 and row2["fully_masked_records"] == 3
    assert row2["kept_samples"] == 0
    for key in ("signal_mean", "signal_median", "candidate_events", "coverage_ratio"):
        assert row2[key] is None, f"{key} 必须为 NA，不得填 0"
    assert row2["raw_records"] == 3  # 计数量保留真实值
    assert row2["observation_status"] == ds.STATUS_UNKNOWN


def test_out_of_range_amplitude_does_not_change_in_range_stats(s03_conn, tmp_path):
    base = _synthetic_values()
    low = [list(base) for _ in range(3)]
    high = [list(base) for _ in range(3)]
    for signal in high:
        for i in range(125, POINTS):  # 全部位于人工截断之外
            signal[i] = 255
    p1 = write_custom_csv(tmp_path / "探鱼-2000_2027-02-01.csv", "2000", "2027-02-01", low)
    p2 = write_custom_csv(tmp_path / "探鱼-2000_2027-02-02.csv", "2000", "2027-02-02", high)
    a = ds.compute_daily_statistics(s03_conn, "2000", "2027-02-01", p1, run_id="RUN-A")
    b = ds.compute_daily_statistics(s03_conn, "2000", "2027-02-02", p2, run_id="RUN-B")
    for key in ("kept_samples", "signal_mean", "signal_median", "signal_stddev",
                "candidate_events", "raw_records", "valid_records", "coverage_ratio"):
        assert a[key] == b[key], f"越界幅度改变了区内指标 {key}"


def test_missing_and_blocked_rows_are_na_not_zero():
    missing = ds.missing_row("2001", "2027-03-01")
    assert missing["status"] == ds.STATUS_MISSING
    assert missing["raw_records"] is None and missing["signal_mean"] is None
    blocked = ds.blocked_row("2002", "2027-03-01", "RUN-X", ("无截断",))
    assert blocked["status"] == ds.STATUS_BLOCKED
    assert blocked["valid_records"] is None and blocked["candidate_events"] is None
    assert "无截断" in blocked["blockage_reasons"]


def test_blocked_device_is_not_scanned(s03_conn, tmp_path):
    with pytest.raises(ds.StatisticsBlocked) as exc:
        ds.compute_daily_statistics(s03_conn, "2002", "2027-04-01",
                                    tmp_path / "does-not-exist.csv", run_id="RUN-BLOCK")
    assert exc.value.device_id == "2002"
    assert any("截断" in r for r in exc.value.reasons)


def test_zero_slot_rows_are_invalid_not_abort(s03_conn, tmp_path):
    path = write_custom_csv(tmp_path / "探鱼-2000_2027-06-15.csv", "2000", "2027-06-15",
                            [signal_values(), signal_values(), [], signal_values()],
                            hours=(0, 1, 3, 5))
    row = ds.compute_daily_statistics(s03_conn, "2000", "2027-06-15", path, run_id="RUN-EMPTY-SLOT")
    assert row["raw_records"] == 4
    assert row["invalid_records"] == 1
    assert row["valid_records"] == 3
    assert row["kept_samples"] == 3 * 108
    assert "无有效槽位" in row["qc_notes"]


def test_insert_and_query_latest_stat(s03_conn, tmp_path):
    s03_conn.execute(
        "INSERT INTO analysis_runs (run_id, device_id, params_snapshot_json, status, created_at) "
        "VALUES ('RUN-INSERT','2000','{}','PENDING','2027-05-01T00:00:00+00:00')")
    s03_conn.commit()
    path = write_fishfinder_csv(tmp_path / "探鱼-2000_2027-05-01.csv", "2000", "2027-05-01")
    row = ds.compute_daily_statistics(s03_conn, "2000", "2027-05-01", path, run_id="RUN-INSERT")
    stat_id = ds.insert_stat_row(s03_conn, row)
    assert stat_id > 0
    latest = ds.latest_stat(s03_conn, "2000", "2027-05-01")
    assert latest["run_id"] == "RUN-INSERT" and latest["kept_samples"] == 324
    assert any(r["stat_id"] == stat_id for r in ds.all_latest_stats(s03_conn))
