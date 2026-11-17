# -*- coding: utf-8 -*-
"""S07 三水层/近底 QC、长期规律证据等级与数据集冻结。"""
from __future__ import annotations

import pytest

from app.services import incremental as incremental_svc
from app.services import s07_datasets as datasets
from app.services import s07_depth as depth
from app.services import s07_patterns as patterns
from s04_helpers import seed_stat
from s06_helpers import seed_stat_and_file
from s07_helpers import register_imported_file, seed_grid, seed_s06_result


def _seed_day(s03_conn, tmp_path, device, date, *, slots=None):
    path = seed_stat_and_file(s03_conn, tmp_path, device, date, active_slots=slots or set())
    register_imported_file(s03_conn, device, date, path, tmp_path)
    return path


def test_layers_and_bottom_qc_never_restore_cutoff_samples(s03_conn, tmp_path):
    active = set(range(24, 36))
    _seed_day(s03_conn, tmp_path, "2000", "2026-10-31", slots=active)
    result = depth.analyze_device_day(s03_conn, "2000", "2026-10-31", project_root=tmp_path)
    layers = {row["layer"]: row for row in result["layers"]}
    assert set(layers) == {"UPPER", "MIDDLE", "LOWER"}
    assert sum(row["kept_samples"] for row in layers.values()) == 96 * 108
    assert layers["UPPER"]["candidate_events"] == len(active)
    assert layers["LOWER"]["candidate_events"] == 0
    assert result["qc"]["status"] == "PENDING_REVIEW"
    assert result["qc"]["excluded_samples"] == 0
    assert result["cutoff_m"] == 5.2
    assert result["geometry"]["center_axis_bottom_m"] > 5.2
    assert result["geometry"]["theory_does_not_override_cutoff"]
    assert s03_conn.execute("SELECT COUNT(*) n FROM s07_bottom_qc").fetchone()["n"] == 1
    assert s03_conn.execute("SELECT COUNT(*) n FROM s07_layer_stats").fetchone()["n"] == 3


def test_no_independent_bottom_detection_means_no_extra_exclusion(s03_conn, tmp_path):
    _seed_day(s03_conn, tmp_path, "2000", "2026-11-01")
    result = depth.analyze_device_day(s03_conn, "2000", "2026-11-01", project_root=tmp_path)
    assert result["qc"]["near_bottom_candidates"] >= 0
    assert result["qc"]["excluded_samples"] == 0
    assert "未实测" in result["qc"]["status"] or result["qc"]["status"] == "PENDING_REVIEW"


def test_pattern_evidence_levels_not_auto_upgraded(conn):
    devices = ("2000",)
    profile = [3, 2, 1] * 8
    for day in ("2026-12-01",):
        seed_stat(conn, "2000", day)
        seed_grid(conn, "2000", day, profile)
    zero = patterns.analyze(conn, devices, "2026-12-01", "2026-12-01", dataset_id="DATASET_01_DUAL_STATION")
    assert zero["evidence_level"] == "L0"

    for day in ("2026-12-02", "2026-12-03"):
        seed_stat(conn, "2000", day)
        seed_grid(conn, "2000", day, profile)
    one_day_short = patterns.analyze(conn, devices, "2026-12-01", "2026-12-03")
    assert one_day_short["evidence_level"] == "L1"
    assert "天数本身不能升级" in "".join(one_day_short["level_reasons"])


def test_l3_requires_frozen_dataset_and_two_devices(conn):
    profile = [4, 2, 1, 3] * 6
    devices = ("2000", "2001")
    dates = [f"2027-01-{day:02d}" for day in range(1, 8)]
    for device in devices:
        for day in dates:
            seed_stat(conn, device, day)
            seed_grid(conn, device, day, profile)
    seed_s06_result(conn, "S06-S07-TEST", list(devices), dates, [1] * 14)
    unfrozen = patterns.analyze(conn, devices, dates[0], dates[-1],
                                dataset_id="DATASET_01_DUAL_STATION")
    assert unfrozen["evidence_level"] == "L2"
    datasets.freeze(conn, "DATASET_01_DUAL_STATION", actor="pytest", reason="S07 测试冻结")
    frozen = patterns.analyze(conn, devices, dates[0], dates[-1],
                              dataset_id="DATASET_01_DUAL_STATION")
    assert frozen["evidence_level"] == "L3"
    first = patterns.save_pattern(conn, unfrozen, pattern_key="TEST_PATTERN")
    second = patterns.reevaluate(conn, "TEST_PATTERN", devices=devices,
                                 start=dates[0], end=dates[-1],
                                 dataset_id="DATASET_01_DUAL_STATION", actor="pytest")
    assert second["supersedes_id"] == first and second["pattern_id"] != first
    assert conn.execute("SELECT COUNT(*) n FROM s07_pattern_versions").fetchone()["n"] == 2


def test_web_s07_routes(client):
    assert client.get("/s07").status_code == 200
    response = client.post("/s07", data={"action": "geometry", "device_id": "2000",
                                         "observed_date": "2026-10-31"})
    assert response.status_code == 200
    assert b"5.204306" in response.data
    assert b"5.2" in response.data
    assert client.post("/s07", data={"action": "pattern", "devices": "2000",
                                     "start_date": "2026-12-01",
                                     "end_date": "2026-12-03"}).status_code == 200


def test_dataset_boundaries_freeze_and_reopen_keep_versions(s03_conn, tmp_path):
    report = datasets.set_boundaries(
        s03_conn, "DATASET_01_DUAL_STATION",
        start_time="2028-01-01T00:00:00+08:00", end_time="2028-01-31T23:59:59+08:00",
        formal_sync_time="2028-02-01T00:00:00+08:00",
        installation_status="BOTH_STATIONS_INSTALLED", actor="pytest")
    assert report["phase_boundaries"]["formal_sync_time"].startswith("2028-02-01")
    assert len(report["versions"]) >= 2
    with pytest.raises(datasets.DatasetBoundaryError):
        datasets.set_boundaries(s03_conn, "DATASET_01_DUAL_STATION",
                                start_time="2026-11-05", end_time="2026-11-01")

    datasets.freeze(s03_conn, "DATASET_01_DUAL_STATION", actor="pytest", reason="阶段截止")
    frozen = datasets.report(s03_conn, "DATASET_01_DUAL_STATION")
    assert frozen["dataset"]["status"] == "FROZEN"
    assert frozen["dataset"]["freeze_reason"] == "阶段截止"
    from s03_helpers import write_fishfinder_csv
    path = write_fishfinder_csv(tmp_path / "探鱼-2000_2028-01-15.csv", "2000", "2028-01-15")
    with pytest.raises(incremental_svc.FrozenDatasetBlocked):
        incremental_svc.register_upload(s03_conn, "2000", path, project_root=tmp_path,
                                        dataset_id="DATASET_01_DUAL_STATION")
    reopened = datasets.reopen(s03_conn, "DATASET_01_DUAL_STATION", actor="pytest",
                               reason="新阶段开始")
    assert reopened["dataset"]["status"] == "PLANNED"
    assert len(reopened["versions"]) >= 4
    assert [v["version"] for v in reopened["versions"]] == sorted(v["version"] for v in reopened["versions"])
