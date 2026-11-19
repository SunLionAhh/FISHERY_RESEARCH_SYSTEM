# -*- coding: utf-8 -*-
"""S08：GPS 管理、坐标审计、站距、空间比较、动态帧与 Web 入口。"""
from __future__ import annotations

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
