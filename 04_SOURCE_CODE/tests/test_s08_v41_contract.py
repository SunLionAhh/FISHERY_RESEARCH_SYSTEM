# -*- coding: utf-8 -*-
"""V4.1 S08 契约验收：分组、聚合、比较、色标、查询状态与同源接口。"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.services import query_context, spatial, spatial_grouping, v41_contracts
from s04_helpers import seed_stat
from s07_helpers import seed_grid

FIXTURE_PATH = (Path(__file__).resolve().parents[2] / "FISHERY_V4_1_CHANGES_ONLY"
                / "18_V4_1_CONTRACT_FIXTURES.json")


def _fixtures():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_v41_fixture_default_grouping_matches_all_twelve_cases():
    fixtures = _fixtures()
    first = date(2026, 1, 1)
    for case in fixtures["grouping"]:
        end = first + timedelta(days=case["span_days"] - 1)
        result = spatial_grouping.default_groups(first.isoformat(), end.isoformat())
        assert result["step_days"] == case["step_days"]
        assert [[group["offset_start"], group["offset_end"]]
                for group in result["groups"]] == case["groups"]
        assert result["within_default_limit"] is True
        assert result["n_groups"] <= 9


def test_v41_aggregation_evidence_difference_and_color_scale_fixtures():
    fixtures = _fixtures()
    ratio = v41_contracts.aggregate_observations(
        fixtures["aggregation"]["days"], "pooled", "CANDIDATE_OCCURRENCE_RATIO")
    equal = v41_contracts.aggregate_observations(
        fixtures["aggregation"]["days"], "equal_day", "CANDIDATE_OCCURRENCE_RATIO")
    assert math.isclose(ratio["pooled_value"],
                        fixtures["aggregation"]["expected_pooled_percent"], rel_tol=1e-12)
    assert math.isclose(equal["equal_day_mean"],
                        fixtures["aggregation"]["expected_equal_day_mean_percent"],
                        rel_tol=1e-12)
    assert ratio["pooled_value"] != fixtures["aggregation"]["expected_sum_percent_is_invalid"]

    evidence = fixtures["evidence"]
    summary = v41_contracts.evidence_summary(evidence)
    assert summary["eligible_units"] == evidence["expected_eligible"]
    assert math.isclose(summary["support_rate"], evidence["expected_support_rate"],
                        rel_tol=1e-12)
    assert summary["total_units"] == evidence["total_units"]

    difference = fixtures["difference"]
    compared = v41_contracts.compare_with_baseline(
        difference["current_percent"], difference["baseline_percent"],
        metric_id="CANDIDATE_OCCURRENCE_RATIO", baseline_id="FIXTURE")
    assert compared["percentage_points"] == difference["expected_percentage_points"]
    assert compared["relative_change_percent"] == difference["expected_relative_change_percent"]

    zero = fixtures["zero_and_missing"][0]
    missing = fixtures["zero_and_missing"][1]
    assert v41_contracts.classify_cell(
        selected=True, numerator=zero["numerator"], denominator=zero["denominator"],
        coverage=1.0) == "VALID_ZERO"
    assert v41_contracts.classify_cell(
        selected=True, numerator=missing["numerator"], denominator=missing["denominator"],
        coverage=None) == "NA"
    assert v41_contracts.classify_cell(
        selected=False, numerator=1, denominator=2, coverage=1.0) == "UNSELECTED"

    ratio_scale = v41_contracts.build_color_scale(
        "CANDIDATE_OCCURRENCE_RATIO", [20, 60])
    assert ratio_scale["color_scale_id"] == "RATIO_0_100_V1"
    assert (ratio_scale["lower"], ratio_scale["upper"]) == (0, 100)
    diff_scale = v41_contracts.build_color_scale(
        "CANDIDATE_OCCURRENCE_RATIO", [-20, 0, 20, 120], comparison=True)
    assert diff_scale["center"] == 0
    assert diff_scale["lower"] == -120 and diff_scale["upper"] == 120
    assert diff_scale["out_of_range_count"] == 0


def test_query_context_query_fingerprint_blocks_old_run_mixing():
    options = dict(selected_devices=["2000", "2001"], start_date="2026-10-31",
                   end_date="2026-11-03")
    first = query_context.build_query_context(**options)
    second = query_context.build_query_context(**options)
    assert first.query_fingerprint() == second.query_fingerprint()
    first.run_id = "RUN-1"
    second.run_id = "RUN-2"
    first.assert_same_query(second)
    different = query_context.build_query_context(
        **{**options, "selected_devices": ["2000", "2002"]})
    with pytest.raises(query_context.QueryContextError):
        first.assert_same_query(different)


def _seed_devices(conn, devices, days):
    for index, device in enumerate(devices):
        spatial.upsert_station(
            conn, device, station_id=f"P{device[-1]}",
            longitude=121.21 + index * 0.002, latitude=27.99 - index * 0.001,
            coordinate_reference_system="WGS84", effective_from="2026-10-31",
            heading_deg=90 + index * 30, heading_reference="V41_TEST", actor="pytest")
        for day in days:
            seed_stat(conn, device, day, events=10 + index * 3)
            seed_grid(conn, device, day, [1 + index] * 24)


def test_v41_run_snapshot_and_seven_api_routes(client, conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(spatial_combination_runs)")}
    assert {"query_context_json", "query_fingerprint", "group_members_json",
            "aggregation_mode", "baseline_id", "color_scale_id", "metric_id",
            "analysis_plan_version", "mask_version", "result_json"} <= columns

    days = ["2026-10-31", "2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"]
    devices = ["2000", "2001", "2002"]
    _seed_devices(conn, devices, days)
    response = client.post("/s08", data={
        "action": "analyze", "devices": devices,
        "start_date": days[0], "end_date": days[-1], "observed_date": days[0],
        "comparison_mode": "baseline_change", "metric_id": "CANDIDATE_EVENT_RATE",
        "grouping_mode": "default", "aggregation_mode": "pooled",
        "baseline_id": "PREV_2", "step_hours": "24",
        "dataset_id": "DATASET_02_FIVE_STATION"})
    assert response.status_code == 200
    assert "V4.1 规律与时空总览".encode("utf-8") in response.data

    row = conn.execute("SELECT * FROM spatial_combination_runs "
                       "ORDER BY created_at DESC LIMIT 1").fetchone()
    assert row["query_fingerprint"].startswith("QC-")
    assert row["result_json"]
    result = json.loads(row["result_json"])
    assert result["v41"]["status"]["run_state"] == "READY"
    assert result["v41"]["spatial_groups"]["n_groups"] == 5
    assert result["v41"]["spatial_groups"]["within_default_limit"] is True
    assert len(result["v41"]["overview"]["trend"]) == 5
    assert len(result["v41"]["patterns"]) == 5
    by_device = {card["device_id"]: card for card in result["v41"]["patterns"]}
    assert by_device["2003"]["status"] == "UNSELECTED"
    assert by_device["2000"]["status"] in ("CANDIDATE_NO_INDEPENDENT_VALIDATION",
                                           "INSUFFICIENT_SAMPLE")

    run_id = row["run_id"]
    for endpoint in ("overview", "spatial-groups", "patterns", "pattern-evidence",
                     "compare", "figure-export"):
        payload = client.get(f"/s08/api/{endpoint}", query_string={"run_id": run_id})
        assert payload.status_code == 200
        body = payload.get_json()
        assert body["status"] == "READY"
        assert body["run_meta"]["run_id"] == run_id
    day_detail = client.get("/s08/api/day-detail", query_string={
        "run_id": run_id, "device_id": "2000", "observed_date": days[2]})
    assert day_detail.status_code == 200
    assert day_detail.get_json()["cell"]["device_id"] == "2000"

    by_query = client.get("/s08/api/overview", query_string={
        "devices": ",".join(devices), "start_date": days[0], "end_date": days[-1],
        "comparison_mode": "baseline_change", "metric_id": "CANDIDATE_EVENT_RATE",
        "grouping_mode": "default", "aggregation_mode": "pooled",
        "baseline_id": "PREV_2", "dataset_id": "DATASET_02_FIVE_STATION"})
    assert by_query.status_code == 200
    assert by_query.get_json()["status"] == "READY"


def test_sixty_day_heatmap_keeps_all_dates_and_six_default_groups(conn):
    first = date(2026, 1, 1)
    last = first + timedelta(days=59)
    day37 = (first + timedelta(days=36)).isoformat()
    seed_stat(conn, "2000", day37, events=12)
    result = spatial.analyze_combination(
        conn, ["2000"], first.isoformat(), last.isoformat(), first.isoformat(),
        step_hours=24, metric_id="CANDIDATE_EVENT_RATE", grouping_mode="default")
    v41 = result["v41"]
    assert v41["overview"]["n_cells"] == 60
    assert v41["spatial_groups"]["n_groups"] == 6
    assert v41["spatial_groups"]["step_days"] == 10
    cells = {(cell["device_id"], cell["observed_date"]): cell
             for cell in v41["overview"]["cells"]}
    assert ("2000", day37) in cells
    assert cells[("2000", day37)]["cell_status"] == "OK"
    missing_day = (first + timedelta(days=1)).isoformat()
    assert cells[("2000", missing_day)]["cell_status"] == "NA"
