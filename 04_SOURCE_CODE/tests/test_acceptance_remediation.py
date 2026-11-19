# -*- coding: utf-8 -*-
"""针对 ACCEPTANCE_S03_S11.md 的 D1/P2 整改复验。"""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import create_app
from app.config import PROJECT_ROOT
from app.services import comparison as cmp
from app.services import environment_analysis as env_an
from app.services import environment_fetch as fetch
from app.services import environment_import as importer
from app.services import intraday, spatial
from app.services import beam_geometry as geo
from s04_helpers import hourly as hourly_json, seed_stat
from s05_helpers import register as register_env_source
from s06_helpers import seed_position

ROOT = Path(PROJECT_ROOT)


def _seed_env_obs(conn, variable: str, values: list[tuple[str, float]], *, source_id: str,
                  location_key: str = "SOURCE_GRID", quality: str = "MODEL_HISTORICAL"):
    register_env_source(conn, source_id)
    conn.execute(
        "INSERT OR IGNORE INTO environment_import_batch (batch_id,source_id,file_name,file_sha256,"
        "file_size_bytes,file_kind,field_mapping_json,timezone,row_count,accepted_count,"
        "rejected_count,duplicate_count,issue_summary_json,status,created_at,actor) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("REM-"+source_id, source_id, "remediation.csv", "REM", 1, "CSV", "{}",
         "Asia/Shanghai", len(values), len(values), 0, 0, "{}", "IMPORTED",
         "2026-11-17T00:00:00+00:00", "pytest"))
    for index, (local, value) in enumerate(values):
        utc = (datetime.strptime(local, "%Y-%m-%dT%H:%M:%S").timestamp() - 8 * 3600)
        utc_text = datetime.utcfromtimestamp(utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "INSERT OR REPLACE INTO environment_observation (batch_id,source_id,variable,"
            "location_key,device_id,observed_at,observed_at_utc,timezone,value,unit,value_si,"
            "quality_flag,raw_row_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("REM-"+source_id, source_id, variable, location_key, None, local, utc_text,
             "Asia/Shanghai", value, "TEST", value, quality, json.dumps({"value": value})))
    conn.commit()


def test_s03_analysis_index_rebuilt_from_real_db():
    path = ROOT / "06_ANALYSIS_RESULTS" / "s03" / "analysis_index.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    keys = list(payload["latest_run_by_device_date"])
    assert "2000/2027-12-01" not in keys
    assert "2000/10-31" not in keys
    assert any(k.startswith("2000/2026-10-31") for k in keys)
    assert len(keys) >= 5


def test_s03_cross_midnight_missing_next_day_is_partial(conn):
    seed_stat(conn, "2000", "2026-10-31", status="COMPLETE",
              hourly_valid=[1] * 24, hourly_events=[2] * 24)
    seed_stat(conn, "2000", "2026-11-01", status="MISSING")
    lookup = {(r["device_id"], r["observed_date"]): r
              for r in conn.execute("SELECT * FROM daily_statistics")}
    criteria = cmp.Criteria(devices=("2000",), start_date="2026-10-31", end_date="2026-10-31",
                            hour_start=22, hour_end=2, day_count=1)
    window = cmp._make_window(lookup[("2000", "2026-10-31")], criteria,
                              [22, 23, 0, 1], lookup)
    assert window["partial"] is True
    assert any("partial=true" in note and "MISSING" in note for note in window["notes"])


def test_s03_upload_route_passes_project_root(client, monkeypatch, app):
    captured = {}

    def fake_register(conn, device_id, path, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(decision="DUPLICATE", status="OK", observed_date="2026-10-31",
                               run_id="TEST", artifacts=(), reasons=())

    monkeypatch.setattr("app.web.routes.upload_svc.register_upload", fake_register)
    response = client.post("/daily/upload", data={"device_id": "2000",
                                                   "file_path": "dummy.csv"})
    assert response.status_code in (200, 302)
    assert captured["project_root"] == Path(app.config["PROJECT_ROOT"])
    assert captured["output_root"] == Path(app.config["PROJECT_ROOT"]) / "06_ANALYSIS_RESULTS"


def test_s05_explicit_derived_quality_and_circular_statistics():
    mapping = importer.Mapping(variable="WATER_TEMP", timezone="Asia/Shanghai",
                               quality_column="quality_flag")
    assert importer._quality({"quality_flag": "DERIVED"}, mapping, []) == "DERIVED"
    result = env_an.circular_statistics([350, 10, 0])
    assert result["status"] == "OK"
    assert abs(result["mean_direction_deg"]) < 1e-6 or result["mean_direction_deg"] > 359.9


def test_s05_tide_wind_and_multi_station_mechanisms(conn):
    tide_values = [("2026-10-31T00:00:00", 1.0), ("2026-10-31T01:00:00", 1.5),
                   ("2026-10-31T02:00:00", 1.2), ("2026-10-31T03:00:00", 0.9)]
    _seed_env_obs(conn, "TIDE_HEIGHT", tide_values, source_id="REM-TIDE",
                  location_key="DEFAULT")
    tide = env_an.tide_analysis(conn, {}, "DEFAULT", timezone_name="Asia/Shanghai")
    assert tide["status"] == "OK" and tide["phases"]
    assert tide["high_low_windows"]
    assert "潮位不是流速" in tide["tide_note"]

    seed_stat(conn, "2000", "2026-10-31", status="COMPLETE",
              hourly_valid=[10] * 24, hourly_events=[2] * 24)
    seed_stat(conn, "2001", "2026-10-31", status="COMPLETE",
              hourly_valid=[10] * 24, hourly_events=[3] * 24)
    wind = [(f"2026-10-31T{h:02d}:00:00", 1.0 + h * 0.2) for h in range(24)]
    _seed_env_obs(conn, "WIND_SPEED", wind, source_id="REM-WIND")
    acoustic = env_an.acoustic_hourly(conn, ("2000", "2001"), "2026-10-31", "2026-10-31")
    change = env_an.wind_change_analysis(conn, acoustic, "SOURCE_GRID",
                                         timezone_name="Asia/Shanghai")
    assert change["status"] == "OK" and change["n_low"] >= 5 and change["n_high"] >= 5
    multi = env_an.multi_station_association(conn, acoustic, "WIND_SPEED", "SOURCE_GRID",
                                             timezone_name="Asia/Shanghai")
    assert multi["status"] == "OK" and len(multi["pairs"]) == 1


def test_s05_persist_matches_writes_drilldown_rows(conn):
    _seed_env_obs(conn, "WIND_SPEED", [("2026-10-31T00:00:00", 3.2)],
                  source_id="REM-MATCH")
    obs_id = conn.execute("SELECT obs_id FROM environment_observation WHERE source_id='REM-MATCH'"
                          ).fetchone()[0]
    pairs = [{"device_id": "2000", "acoustic_time": "2026-10-31T00:00:00",
              "lag_hours": 0, "delta_seconds": 10, "tolerance_seconds": 1800,
              "obs_id": obs_id, "acoustic_value": 2, "environment_value": 3.2}]
    count = env_an.persist_matches(conn, "ENV-REM-TEST", {"WIND_SPEED": pairs})
    assert count == 1
    assert conn.execute("SELECT COUNT(1) FROM environment_match WHERE analysis_id='ENV-REM-TEST'"
                        ).fetchone()[0] == 1


def test_s05_auto_fetch_framework_success_cache_retry_and_backfill(conn, monkeypatch):
    class Adapter:
        def fetch(self, start_utc, end_utc):
            return [{"start": start_utc, "end": end_utc, "value": 1.0}]

    class FailingAdapter:
        def fetch(self, start_utc, end_utc):
            raise RuntimeError("SIMULATED_NETWORK_FAILURE")

    fetch.register_adapter(conn, "REM_ADAPTER", "unused:Adapter", status="ENABLED")
    monkeypatch.setattr(fetch, "_load_adapter", lambda path: Adapter())
    assert fetch.configure_schedule(conn, "REM_ADAPTER", {
        "start_utc": "2026-10-31T00:00:00Z", "end_utc": "2026-10-31T01:00:00Z"},
        enabled=True)["status"] == "OK"
    first = fetch.fetch_with_retry(conn, "REM_ADAPTER", "2026-10-31T00:00:00Z",
                                   "2026-10-31T01:00:00Z")
    second = fetch.fetch_with_retry(conn, "REM_ADAPTER", "2026-10-31T00:00:00Z",
                                    "2026-10-31T01:00:00Z")
    assert first["status"] == "SUCCESS" and second["status"] == "HIT"
    assert fetch.run_due_schedules(conn)
    backfill = fetch.backfill_history(conn, "REM_ADAPTER",
                                      "2026-10-31T00:00:00Z", "2026-10-31T03:00:00Z",
                                      chunk_hours=1)
    assert backfill["status"] == "OK" and len(backfill["chunks"]) == 3

    fetch.register_adapter(conn, "REM_FAIL", "unused:FailingAdapter", status="ENABLED")
    monkeypatch.setattr(fetch, "_load_adapter", lambda path: FailingAdapter())
    failed = fetch.fetch_with_retry(conn, "REM_FAIL", "2026-10-31T00:00:00Z",
                                    "2026-10-31T01:00:00Z", max_retries=2)
    assert failed["status"] == "FAILED"
    assert conn.execute("SELECT COUNT(1) FROM environment_fetch_retry WHERE adapter_id='REM_FAIL'"
                        ).fetchone()[0] == 2


def test_s06_partial_night_not_comparable_and_blocked_reason(conn):
    seed_position(conn, "2000")
    seed_stat(conn, "2000", "2026-10-31")
    seed_stat(conn, "2000", "2026-11-01")
    grid = []
    for slot in range(96):
        stamp = (datetime.strptime("2026-10-31", "%Y-%m-%d")
                 + __import__("datetime").timedelta(minutes=slot * 15)).isoformat(timespec="seconds")
        grid.append({"device_id": "2000", "observed_date": "2026-10-31", "slot_start": stamp,
                     "candidate_events": 2, "coverage_ratio": 1.0})
    for slot in range(8):
        stamp = (datetime.strptime("2026-11-01", "%Y-%m-%d")
                 + __import__("datetime").timedelta(minutes=slot * 15)).isoformat(timespec="seconds")
        grid.append({"device_id": "2000", "observed_date": "2026-11-01", "slot_start": stamp,
                     "candidate_events": 2, "coverage_ratio": 1.0})
    result = intraday.day_night(conn, grid, ("2000",), ("2026-10-31",),
                                "Asia/Shanghai", 8.0)
    pair = result["results"][0]["pair"]
    assert pair["coverage_ok"] is False
    assert pair["comparison_status"] == "NOT_COMPARABLE_PARTIAL_NIGHT"
    assert pair["night_coverage_ratio"] < 0.9

    blocked = intraday.day_night(conn, [], ("2002",), ("2026-10-31",),
                                 "Asia/Shanghai", 8.0)["results"][0]
    assert "S03 统计行" in blocked["reason"]
    assert "缺少该日/次日真实经纬度" not in blocked["reason"]


def test_s07_footprint_area_and_new_version_evidence():
    geometry = geo.beam_geometry(height_m=3.68, tilt_deg=45, beam_value_deg=15,
                                 beam_kind="FULL", cutoff_m=5.2)
    area = geometry["retained_footprint"]["area_m2"]
    assert 0.85 < area < 0.86
    assert area < geometry["uncut_ellipse"]["area_m2"]
    evidence = ROOT / "10_TEST_REPORTS" / "s07_verification" / "geometry_2000_footprint_fix_v2.txt"
    assert evidence.exists()
    conn = sqlite3.connect(ROOT / "03_DATABASE" / "fishery.db")
    try:
        count = conn.execute(
            "SELECT COUNT(1) FROM s07_bottom_qc WHERE created_by='S07-FOOTPRINT-FIX-V2'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert count >= 1


def test_s08_directional_footprint_when_heading_present():
    geometry = geo.beam_geometry(height_m=3.68, tilt_deg=45, beam_value_deg=15,
                                 beam_kind="FULL", cutoff_m=5.2)
    blocked = spatial.directional_footprint(None, geometry)
    assert blocked["status"] == "UNKNOWN"
    result = spatial.directional_footprint(90, geometry, heading_reference="TRUE_NORTH")
    assert result["status"] == "CONDITIONAL_SECTOR"
    assert result["heading_deg"] == 90
    assert len(result["polygon_local_m"]) >= 10
    assert "不是实测鱼群位置" in result["note"]


def test_s08_import_heading_images_creates_versioned_records(conn, tmp_path):
    image = tmp_path / "compass.jpg"
    image.write_bytes(b"HEADING-IMAGE-TEST")
    records = [{"device_id": "2000", "heading_deg": 110,
                "image_path": str(image), "heading_reference": "PHONE_COMPASS",
                "position_source": "USER_COMPASS_TEST"}]
    imported = spatial.import_headings(conn, tmp_path, records,
                                       effective_from="2026-10-31",
                                       measured_at="2026-11-19", actor="pytest")
    assert imported[0]["sha256"]
    point = spatial.locations(conn, "2026-10-31")[0]
    assert point["heading_deg"] == 110
    assert point["heading_reference"] == "PHONE_COMPASS"
    assert len(spatial.station_history(conn, "2000")) == 1


def test_s09_every_figure_has_self_contained_definition():
    conn = sqlite3.connect(ROOT / "03_DATABASE" / "fishery.db")
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM figure_registry")]
    finally:
        conn.close()
    assert len(rows) == 16
    for row in rows:
        assert row["caption"] and "见" not in row["caption"][:2]
        assert row["metric_definition"] and "见 S09 阶段报告" not in row["metric_definition"]
        units = json.loads(row["units_json"])
        assert units and "见源表" not in json.dumps(units, ensure_ascii=False)


def test_s11_file_level_freeze_manifest():
    root = ROOT / "13_FROZEN_VERSIONS" / "PRE_DEFENSE"
    manifest = root / "FROZEN_FILE_MANIFEST.json"
    assert manifest.exists()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["file_count"] > 10
    assert payload["all_match"] is True
    assert (root / "FROZEN_FILE_MANIFEST.csv").exists()
