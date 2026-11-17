# -*- coding: utf-8 -*-
"""S03 增量上传：8 步场景、重复/冲突/迟到/补传、冻结保护、run_id 与网页入口。"""
from __future__ import annotations

import json

import pytest

from app.services import daily_stats as ds
from app.services import incremental as inc
from app.services.csv_parser import sha256_file
from s03_helpers import write_fishfinder_csv


def _upload(conn, tmp_path, device, date, *, name=None, **kwargs):
    path = write_fishfinder_csv(tmp_path / (name or f"探鱼-{device}_{date}.csv"), device, date)
    return path, inc.register_upload(conn, device, path, project_root=tmp_path,
                                     output_root=tmp_path / "outputs", **kwargs)


def test_eight_step_incremental_validation(s03_conn, tmp_path):
    # 1—2：只上传第 1 天，生成日报
    p1, out1 = _upload(s03_conn, tmp_path, "2000", "2027-06-01")
    assert out1.decision == inc.DECISION_NEW
    report = tmp_path / "outputs" / "06_ANALYSIS_RESULTS" / "s03" / "daily" / "2000" / "2027-06-01" / "daily_report.md"
    assert report.exists() and "分子" in report.read_text(encoding="utf-8")
    assert sha256_file(p1) == out1.file_sha256

    # 3—5：跳过第 2 天，上传第 3 天，系统仍正常
    _, out3 = _upload(s03_conn, tmp_path, "2000", "2027-06-03")
    assert out3.decision == inc.DECISION_NEW

    # 6：第 2 天自动显示 MISSING（指标 NA，不填 0）
    day2 = ds.latest_stat(s03_conn, "2000", "2027-06-02")
    assert day2 is not None and day2["status"] == ds.STATUS_MISSING
    assert day2["raw_records"] is None and day2["signal_mean"] is None

    # 7—8：补传第 2 天，受影响结果正确更新；原始文件哈希不变
    _, out2 = _upload(s03_conn, tmp_path, "2000", "2027-06-02")
    assert out2.decision == inc.DECISION_REPROCESSED
    day2_new = ds.latest_stat(s03_conn, "2000", "2027-06-02")
    assert day2_new["status"] == ds.STATUS_REPROCESSED
    assert day2_new["valid_records"] == 3 and day2_new["kept_samples"] == 324
    assert day2_new["stat_id"] != day2["stat_id"]  # 历史 MISSING 行保留
    assert ds.latest_stat(s03_conn, "2000", "2027-06-03")["stat_id"] == ds.latest_stat(
        s03_conn, "2000", "2027-06-03")["stat_id"]
    assert sha256_file(p1) == out1.file_sha256  # 原始文件全程未改


def test_duplicate_upload_and_force_reprocess(s03_conn, tmp_path):
    path = write_fishfinder_csv(tmp_path / "探鱼-2000_2027-07-01.csv", "2000", "2027-07-01")
    first = inc.register_upload(conn=s03_conn, device_id="2000", path=path,
                                project_root=tmp_path, output_root=tmp_path / "outputs")
    second = inc.register_upload(conn=s03_conn, device_id="2000", path=path,
                                 project_root=tmp_path, output_root=tmp_path / "outputs")
    assert second.decision == inc.DECISION_DUPLICATE and second.run_id == first.run_id
    forced = inc.register_upload(conn=s03_conn, device_id="2000", path=path,
                                 project_root=tmp_path, output_root=tmp_path / "outputs", force=True)
    assert forced.decision == inc.DECISION_REPROCESSED
    old = s03_conn.execute("SELECT status FROM analysis_runs WHERE run_id=?", (first.run_id,)).fetchone()
    assert old["status"] == "SUPERSEDED"
    n = s03_conn.execute("SELECT COUNT(*) n FROM daily_statistics WHERE device_id='2000' "
                         "AND observed_date='2027-07-01'").fetchone()["n"]
    assert n == 2  # 历史结果不删除


def test_conflict_same_day_different_content_requires_review(s03_conn, tmp_path):
    p1 = write_fishfinder_csv(tmp_path / "探鱼-2000_2027-08-01.csv", "2000", "2027-08-01",
                              event=True)
    inc.register_upload(s03_conn, "2000", p1, project_root=tmp_path, output_root=tmp_path / "out")
    p2 = tmp_path / "other" / "探鱼-2000_2027-08-01.csv"
    write_fishfinder_csv(p2, "2000", "2027-08-01", event=False)
    with pytest.raises(inc.UploadConflict) as exc:
        inc.register_upload(s03_conn, "2000", p2, project_root=tmp_path, output_root=tmp_path / "out")
    assert "人工审查" in str(exc.value)
    forced = inc.register_upload(s03_conn, "2000", p2, project_root=tmp_path,
                                 output_root=tmp_path / "out", force=True)
    assert forced.decision == inc.DECISION_REPROCESSED
    assert any(r["status"] == "CONFLICT" for r in s03_conn.execute(
        "SELECT status FROM file_registry WHERE observed_date='2027-08-01'"))


def test_late_upload_and_run_snapshot(s03_conn, tmp_path):
    _, out = _upload(s03_conn, tmp_path, "2000", "2027-09-01",
                     upload_date="2027-09-05")
    assert out.status == ds.STATUS_UPLOADED_LATE
    snapshot = json.loads(s03_conn.execute(
        "SELECT params_snapshot_json FROM analysis_runs WHERE run_id=?", (out.run_id,)
    ).fetchone()["params_snapshot_json"])
    assert snapshot["analysis_cutoff_slant_m"] == 5.2
    assert snapshot["parameter_version"] == 1
    assert snapshot["mapping_version"] == 1
    assert snapshot["algorithm_version"] == ds.ALGORITHM_VERSION
    assert snapshot["file_sha256"] == out.file_sha256
    assert ds.latest_stat(s03_conn, "2000", "2027-09-01")["file_sha256"] == out.file_sha256
    assert snapshot["upload_status"] == ds.UPLOAD_LATE


def test_frozen_dataset_blocks_upload(s03_conn, tmp_path):
    s03_conn.execute(
        "INSERT INTO datasets (dataset_id,name,phase,status) VALUES ('FROZEN_TEST','冻结集',1,'FROZEN')")
    s03_conn.execute("INSERT INTO dataset_members (dataset_id,device_id) VALUES ('FROZEN_TEST','2000')")
    s03_conn.commit()
    path = write_fishfinder_csv(tmp_path / "探鱼-2000_2027-10-01.csv", "2000", "2027-10-01")
    with pytest.raises(inc.FrozenDatasetBlocked):
        inc.register_upload(s03_conn, "2000", path, project_root=tmp_path,
                            output_root=tmp_path / "out")


def test_blocked_device_does_not_affect_others(s03_conn, tmp_path):
    blocked_path = write_fishfinder_csv(tmp_path / "探鱼-2002_2027-11-01.csv", "2002", "2027-11-01")
    blocked = inc.register_upload(s03_conn, "2002", blocked_path, project_root=tmp_path,
                                  output_root=tmp_path / "out")
    assert blocked.decision == inc.DECISION_BLOCKED and blocked.status == ds.STATUS_BLOCKED
    row = ds.latest_stat(s03_conn, "2002", "2027-11-01")
    assert row["valid_records"] is None and row["coverage_ratio"] is None
    assert row["blockage_reasons"]

    _, ok = _upload(s03_conn, tmp_path, "2000", "2027-11-01")
    assert ok.decision == inc.DECISION_NEW and ok.status != ds.STATUS_BLOCKED
    assert ds.latest_stat(s03_conn, "2000", "2027-11-01")["kept_samples"] == 324


def test_web_daily_routes(client, s03_conn, tmp_path):
    path = write_fishfinder_csv(tmp_path / "探鱼-2000_2027-12-01.csv", "2000", "2027-12-01")
    inc.register_upload(s03_conn, "2000", path, project_root=tmp_path, output_root=tmp_path / "out")
    assert client.get("/daily").status_code == 200
    assert client.get("/daily/upload").status_code == 200
    detail = client.get("/daily/2000/2027-12-01")
    assert detail.status_code == 200 and b"NA" in detail.data
    response = client.post("/daily/2000/2027-12-02/missing", data={"note": "测试缺测"})
    assert response.status_code == 302
    assert client.get("/daily/2000/2027-12-02").status_code == 200
