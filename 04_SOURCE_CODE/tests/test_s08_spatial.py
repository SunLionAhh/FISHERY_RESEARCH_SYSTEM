# -*- coding: utf-8 -*-
"""S08：GPS 管理、坐标审计、站距、空间比较、动态帧与 Web 入口。"""
from __future__ import annotations

import itertools
import json
import math

import pytest

from app.services import spatial
from s04_helpers import seed_stat
from s07_helpers import seed_grid
from s08_helpers import seed_environment


def test_sync_from_positions_keeps_unknown_station_codes(conn):
    assert spatial.sync_from_positions(conn) == 2
    points = spatial.locations(conn, "2026-10-31")
    assert len(points) == 2
    assert all(p["station_id"] is None for p in points)
    result = spatial.compute_distances(conn, "2026-10-31")
    assert len(result["distances"]) == 1
    pair = result["distances"][0]
    assert pair["status"] == "PROVISIONAL"
    assert pair["method"] == "HAVERSINE_WGS84_ASSUMED_UNDECLARED"
    assert 140 < pair["distance_m"] < 200
    payload = spatial.map_payload(conn, "2026-10-31")
    assert set(payload["unknown_devices"]) == {"2002", "2003", "2005"}
    assert all("P 码未提供" in s["label"] for s in payload["stations"])
    coverages = [s["coverage"] for s in payload["stations"]]
    assert any(c["status"] == "CIRCLE_ONLY" for c in coverages)
    assert any(c["status"] == "UNKNOWN" for c in coverages)
    assert all((c.get("directional_footprint") or {}).get("status", "UNKNOWN") == "UNKNOWN"
               for c in coverages)
    assert payload["map_mode"] == "OFFLINE_LOCAL_COORDINATE_SKETCH"


def test_station_history_and_cross_crs_refusal(conn):
    spatial.upsert_station(conn, "2000", station_id="P1", longitude=121.21, latitude=27.99,
                           coordinate_reference_system="WGS84", effective_from="2026-10-31",
                           heading_deg=90)
    spatial.upsert_station(conn, "2000", station_id="P1", longitude=121.22, latitude=27.98,
                           coordinate_reference_system="WGS84", effective_from="2026-11-02",
                           heading_deg=120)
    history = spatial.station_history(conn, "2000")
    assert len(history) == 2
    assert spatial.locations(conn, "2026-10-31")[0]["heading_deg"] == 90
    assert spatial.locations(conn, "2026-11-02")[0]["heading_deg"] == 120

    spatial.upsert_station(conn, "2001", station_id="P2", longitude=121.23, latitude=27.97,
                           coordinate_reference_system="EPSG:3857", effective_from="2026-11-02")
    result = spatial.compute_distances(conn, "2026-11-02")
    assert result["distances"] == []
    assert len(result["excluded"]) == 1
    assert "坐标系不同" in result["excluded"][0]["reason"]

    with pytest.raises(spatial.SpatialValidationError):
        spatial.upsert_station(conn, "2002", station_id="P3", longitude=200, latitude=27.9)
    with pytest.raises(spatial.SpatialValidationError):
        spatial.upsert_station(conn, "2002", station_id="P3", longitude=121, latitude=None)


def test_coordinate_audit_flags_duplicate_and_suspected_swap(conn):
    spatial.upsert_station(conn, "2000", station_id="P1", longitude=121.21, latitude=27.99,
                           coordinate_reference_system="WGS84", effective_from="2026-10-31")
    spatial.upsert_station(conn, "2001", station_id="P2", longitude=121.21, latitude=27.99,
                           coordinate_reference_system="WGS84", effective_from="2026-10-31")
    payload = spatial.map_payload(conn, "2026-10-31")
    assert all("DUPLICATE_COORDINATE" in s["coordinate_audit"]["flags"] for s in payload["stations"])

    peers = [{"device_id": "A", "longitude_deg": 10.0, "latitude_deg": 50.0},
             {"device_id": "B", "longitude_deg": 11.0, "latitude_deg": 51.0}]
    swapped = spatial.coordinate_audit(
        {"device_id": "C", "longitude_deg": 50.5, "latitude_deg": 10.5,
         "coordinate_reference_system": "WGS84"}, peers)
    assert swapped["suspected_latlon_swap"] is True
    assert "SUSPECTED_LATLON_SWAP" in swapped["flags"]
    assert swapped["status"] == "BLOCKED"


def test_spatial_activity_statistics_heatmaps_and_environment(conn):
    devices = ("2000", "2001")
    for device, base in zip(devices, (4, 9)):
        for index, day in enumerate(("2026-10-31", "2026-11-01", "2026-11-02")):
            events = base + index * 2
            seed_stat(conn, device, day, events=events)
            seed_grid(conn, device, day, [events // 4] * 12 + [1] * 12)
    seed_environment(conn, "WIND_SPEED", [("2026-10-31T01:00:00", 3.2)])
    daily = spatial.daily_activity(conn, devices, "2026-10-31", "2026-11-02")
    assert daily["2000"]["2026-10-31"]["rate_per_hour"] > 0
    stats = spatial.spatial_statistics(conn, devices, "2026-10-31", "2026-11-02")
    assert stats["pairs"][0]["n_common"] == 3
    assert stats["pairs"][0]["status"] == "OK"
    assert stats["device_differences"]["2000"]["valid_hours_total"] > 0
    heatmaps = spatial.heatmaps(conn, devices, "2026-10-31", "2026-11-02")
    assert len(heatmaps["date_station"]) == 6
    assert heatmaps["note"].find("不填 0") >= 0
    env = spatial.environment_joint(conn, devices, "2026-10-31", "2026-11-02")
    by_var = {item["variable"]: item for item in env["results"]}
    assert by_var["WIND_SPEED"]["status"] == "PROVISIONAL"
    assert by_var["WIND_SPEED"]["station_comparison"]["status"] == "BLOCKED"
    assert by_var["TIDE_HEIGHT"]["status"] == "BLOCKED"


def test_dynamic_frames_are_discrete_and_missing_is_na(conn):
    seed_grid(conn, "2000", "2026-10-31", [0, 3, 0] + [0] * 21)
    conn.execute("DELETE FROM s06_time_grid WHERE device_id='2000' AND slot_start='2026-10-31T02:00:00'")
    conn.commit()
    seed_environment(conn, "WIND_SPEED", [("2026-10-31T01:00:00", 3.2)])
    result = spatial.dynamic_frames(conn, ("2000",), "2026-10-31", "2026-10-31")
    assert len(result["frames"]) == 24
    assert result["legend"]["missing"] == "NA"
    assert result["frames"][1]["values"][0]["candidate_events"] == 3
    assert result["frames"][1]["values"][0]["environment"]["WIND_SPEED"]["value"] == 3.2
    missing = result["frames"][2]["values"][0]
    assert missing["candidate_events"] is None and missing["status"] == "NA"
    assert "trajectory" not in result and "interpolated_density" not in result


def test_web_s08_routes_and_outputs(client, tmp_path):
    assert client.get("/s08").status_code == 200
    assert client.post("/s08", data={"action": "sync", "observed_date": "2026-10-31"}).status_code == 200
    response = client.post("/s08", data={
        "action": "analyze", "devices": "2000", "start_date": "2026-10-31",
        "end_date": "2026-10-31", "observed_date": "2026-10-31", "step_hours": "1"})
    assert response.status_code == 200
    assert "离散动态帧".encode("utf-8") in response.data
    assert "无轨迹".encode("utf-8") in response.data
    bad = client.post("/s08", data={"action": "save_station", "device_id": "2002",
                                    "longitude": "200", "latitude": "27"})
    assert bad.status_code == 200
    assert b"[-180,180]" in bad.data


def test_write_outputs_creates_evidence_files(tmp_path, conn):
    spatial.sync_from_positions(conn)
    result = {
        "map": spatial.map_payload(conn, "2026-10-31"),
        "activity": spatial.daily_activity(conn, ("2000",), "2026-10-31", "2026-10-31"),
        "dynamics": spatial.dynamic_frames(conn, ("2000",), "2026-10-31", "2026-10-31"),
    }
    written = spatial.write_outputs(result, tmp_path / "s08")
    assert "station_locations.csv" in written
    assert "dynamic_frames.csv" in written
    assert (tmp_path / "s08" / "spatial_summary.json").exists()
    assert len((tmp_path / "s08" / "dynamic_frames.csv").read_text(encoding="utf-8-sig").splitlines()) == 25


def test_haversine_symmetric():
    left = spatial.haversine_m(121.2117505073547, 27.99346353124773,
                               121.2130272388458, 27.99260143251764)
    right = spatial.haversine_m(121.2130272388458, 27.99260143251764,
                                121.2117505073547, 27.99346353124773)
    assert math.isclose(left, right, abs_tol=1e-9)


def _seed_five_station_context(conn):
    positions = (
        ("2000", 121.2117505, 27.9934635, 110),
        ("2001", 121.2130272, 27.9926014, 260),
        ("2002", 121.2150000, 27.9910000, 270),
        ("2003", 121.2170000, 27.9900000, 234),
        ("2005", 121.2190000, 27.9890000, 165),
    )
    for device_id, lon, lat, heading in positions:
        spatial.upsert_station(
            conn, device_id, station_id=f"P{device_id[-1]}", longitude=lon, latitude=lat,
            coordinate_reference_system="WGS84", effective_from="2026-10-31",
            heading_deg=heading, heading_reference="TEST_COMPASS", actor="pytest")
    days_by_device = {
        "2000": ["2026-10-31", "2026-11-01", "2026-11-02"],
        "2001": ["2026-10-31", "2026-11-01"],
        "2002": ["2026-10-31", "2026-11-01"],
        "2003": ["2026-10-31"],
        "2005": ["2026-10-31", "2026-11-02"],
    }
    for device_id, days in days_by_device.items():
        for index, day in enumerate(days):
            seed_stat(conn, device_id, day, events=10 + int(device_id) % 7 + index)
            seed_grid(conn, device_id, day, [1 + index] * 24)
    return days_by_device


def test_parse_devices_accepts_any_subset_and_rejects_unknown():
    assert spatial.parse_devices("2005,2000") == ["2000", "2005"]
    assert spatial.parse_devices(["2003", "2001", "2003"]) == ["2001", "2003"]
    with pytest.raises(spatial.SpatialValidationError):
        spatial.parse_devices([])
    with pytest.raises(spatial.SpatialValidationError):
        spatial.parse_devices(["2004"])


def test_arbitrary_combinations_switch_and_recompute(conn):
    days_by_device = _seed_five_station_context(conn)
    start, end, observed = "2026-10-31", "2026-11-02", "2026-10-31"
    checked = 0
    for size in (2, 3, 4, 5):
        for subset in itertools.combinations(spatial.DEVICE_IDS, size):
            combo = list(subset)
            result = spatial.analyze_combination(
                conn, combo, start, end, observed,
                dataset_id="DATASET_02_FIVE_STATION", actor="pytest")
            assert result["selected_devices"] == combo
            assert [s["device_id"] for s in result["map"]["stations"]] == combo
            assert set(result["activity"]) == set(combo)
            assert set(result["time_curves"]) == set(combo)
            assert {h["device_id"] for h in result["heatmaps"]["date_station"]} == set(combo)
            assert result["common_valid_periods"]["devices"] == combo
            expected_days = sorted(set.intersection(
                *(set(days_by_device[device]) for device in combo)))
            assert result["common_valid_periods"]["common_dates"] == expected_days
            assert result["common_valid_periods"]["n_common_hours"] == 24 * len(expected_days)
            assert len(result["pairwise"]["pairs"]) == len(list(itertools.combinations(combo, 2)))
            assert len(result["statistics"]["modes"]["common_valid"]["pairs"]) == len(
                result["pairwise"]["pairs"])
            assert result["statistics"]["modes"]["independent"]["status"] == "OK"
            assert all(item["device_id"] in combo for item in
                       result["statistics"]["modes"]["independent"]["devices"])
            row = conn.execute(
                "SELECT * FROM spatial_combination_runs WHERE run_id=?",
                (result["run_id"],)).fetchone()
            assert row is not None
            assert row["device_list"] == ",".join(combo)
            assert json.loads(row["devices_json"]) == combo
            assert set(json.loads(row["parameter_versions_json"])) == set(combo)
            assert row["dataset_id"] == "DATASET_02_FIVE_STATION"
            assert row["n_devices"] == size
            checked += 1
    assert checked == 26


def test_dual_pair_geometry_missing_na_and_independent_parameters(conn):
    _seed_five_station_context(conn)
    result = spatial.pairwise_analysis(
        conn, ("2000", "2001"), "2026-10-31", "2026-11-02", "2026-10-31")
    pair = result["pairs"][0]
    assert pair["distance"]["status"] in ("OK", "PROVISIONAL")
    assert pair["distance"]["distance_m"] > 100
    coverage_a = pair["theoretical_coverage"]["device_a"]
    coverage_b = pair["theoretical_coverage"]["device_b"]
    assert coverage_a["coverage_radius_m"] is not None
    assert coverage_a["parameter_version"] == 1
    assert coverage_b["coverage_radius_m"] is None
    assert coverage_b["parameter_version"] is None
    assert pair["conditional_overlap"]["status"] == "UNKNOWN"
    assert pair["conditional_overlap"]["area_m2"] is None
    by_date = {row["observed_date"]: row
               for row in pair["activity_difference"]["by_date"]}
    assert by_date["2026-11-02"]["rate_b"] is None
    assert by_date["2026-11-02"]["difference_a_minus_b"] is None

    stub = {"inputs": {"internal_half_angle_deg": 30},
            "water_projection_max_forward_m": 20}
    left = {"longitude_deg": 121.2117505, "latitude_deg": 27.9934635}
    right = {"longitude_deg": 121.2118505, "latitude_deg": 27.9934635}
    overlap = spatial._conditional_overlap(
        {"directional_footprint": spatial.directional_footprint(90, stub)},
        {"directional_footprint": spatial.directional_footprint(90, stub)}, left, right)
    assert overlap["status"] == "CONDITIONAL_OVERLAP"
    assert overlap["area_m2"] > 0


def test_web_s08_multiselect_and_combination_export(client, conn):
    _seed_five_station_context(conn)
    response = client.post("/s08", data={
        "action": "analyze", "devices": ["2000", "2002", "2005"],
        "start_date": "2026-10-31", "end_date": "2026-11-02",
        "observed_date": "2026-10-31", "step_hours": "1",
        "dataset_id": "DATASET_02_FIVE_STATION"})
    assert response.status_code == 200
    assert "组合分析完成".encode("utf-8") in response.data
    assert "模式二：共同有效时段比较".encode("utf-8") in response.data

    export = client.post("/s08", data={
        "action": "export_animation", "devices": ["2000", "2002"],
        "formats": ["GIF"], "start_date": "2026-10-31",
        "end_date": "2026-11-02", "observed_date": "2026-10-31",
        "step_hours": "1", "dataset_id": "DATASET_02_FIVE_STATION"})
    assert export.status_code == 200
    assert "动画导出".encode("utf-8") in export.data
    rows = list(conn.execute("SELECT * FROM animation_exports"))
    assert rows
    assert any("run_id=" in row["source_frames"]
               and "devices=2000,2002" in row["source_frames"] for row in rows)
