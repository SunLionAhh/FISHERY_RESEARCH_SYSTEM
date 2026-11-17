# -*- coding: utf-8 -*-
"""S09：16 类图登记、动画导出、Origin Worker 与 Web 任务队列。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import origin_bridge, s09_animation, s09_figures
from s04_helpers import seed_stat
from s07_helpers import seed_grid


def _copy_s08_evidence(root: Path) -> None:
    source = (root.parents[1] / "10_TEST_REPORTS" / "s08_verification" / "real_data")
    if not source.exists():
        source = (Path(__file__).resolve().parents[2] / "10_TEST_REPORTS"
                  / "s08_verification" / "real_data")
    target = root / "10_TEST_REPORTS" / "s08_verification" / "real_data"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("station_locations.csv", "spatial_activity.csv", "spatial_summary.json",
                 "dynamic_frames.csv"):
        if (source / name).exists():
            (target / name).write_bytes((source / name).read_bytes())


def test_figure_registry_has_16_classes_and_honest_blocks(conn, tmp_path):
    _copy_s08_evidence(tmp_path)
    seed_stat(conn, "2000", "2026-10-31", events=4)
    seed_stat(conn, "2000", "2026-11-01", events=6)
    seed_grid(conn, "2000", "2026-10-31", [1] * 96)
    result = s09_figures.build_all(conn, tmp_path, run_id="TEST-RUN", dataset_id="TEST-DATA")
    assert result["ok"] + result["blocked"] == 16
    report = s09_figures.report(conn)
    assert report["total"] == 16
    by_id = {row["figure_id"]: row for row in report["rows"]}
    assert by_id["F09-05"]["status"] == "BLOCKED"
    assert by_id["F09-05"]["output_png"] is None
    assert by_id["F09-02"]["status"] == "OK"
    assert Path(by_id["F09-01"]["source_csv"]).exists()
    assert Path(by_id["F09-01"]["output_png"]).exists()
    assert by_id["F09-01"]["run_id"] == "TEST-RUN"
    assert by_id["F09-01"]["dataset_id"] == "TEST-DATA"


def test_animation_exports_are_discrete_and_na_is_not_zero(conn, tmp_path):
    source_dir = tmp_path / "10_TEST_REPORTS" / "s08_verification" / "real_data"
    source_dir.mkdir(parents=True, exist_ok=True)
    source = source_dir / "dynamic_frames.csv"
    source.write_text(
        "timestamp_local,timezone,device_id,activity_status,candidate_events,WIND_SPEED_value\n"
        "2026-10-31T00,Asia/Shanghai,2000,OK,3,2.1\n"
        "2026-10-31T00,Asia/Shanghai,2001,NA,,\n"
        "2026-10-31T01,Asia/Shanghai,2000,OK,2,2.4\n"
        "2026-10-31T01,Asia/Shanghai,2001,OK,4,\n", encoding="utf-8")
    result = s09_animation.export(conn, tmp_path, formats=("PNG_SEQUENCE", "GIF", "PDF"))
    assert result["frames"] == 2
    assert result["na_cells"] == 1
    assert {x["format"] for x in result["exports"]} == {"PNG_SEQUENCE", "GIF", "PDF"}
    rows = list(conn.execute("SELECT * FROM animation_exports"))
    assert len(rows) == 3
    assert all("no_interpolation" in r["consistency_check"] for r in rows)
    assert all(Path(r["file_path"]).exists() for r in rows)


def test_origin_probe_records_unavailable_packages():
    probe = origin_bridge.probe_environment()
    assert probe["com_progids"]
    assert probe["originpro_python_package"] == "NOT_INSTALLED"
    assert probe["pywin32_python_package"] == "NOT_INSTALLED"
    assert "PowerShell" in probe["bridge"]


def test_origin_tasks_queue_failures_and_are_isolated(conn, tmp_path):
    csv = tmp_path / "fig.csv"
    csv.write_text("x,y\n1,2\n2,4\n", encoding="utf-8")
    for figure_id in ("F09-01", "F09-07"):
        conn.execute("INSERT OR REPLACE INTO figure_registry (figure_id,figure_class,priority,title,"
                     "engine,status,source_csv,caption,created_at,actor) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (figure_id, "test", "P0", "test", "ORIGIN", "OK", str(csv), "test", "now", "pytest"))
    conn.commit()
    a = origin_bridge.create_task(conn, tmp_path, ["F09-01"], formats=("png",))
    b = origin_bridge.create_task(conn, tmp_path, ["F09-07"], formats=("svg",))
    assert a["task_id"] != b["task_id"]
    rows = list(conn.execute("SELECT status FROM origin_tasks"))
    assert rows and all(r["status"] == "QUEUED" for r in rows)

    worker = tmp_path / "fake_worker.ps1"
    worker.write_text(
        "param([string]$Task,[string]$Result)\n"
        "$t=Get-Content -LiteralPath $Task -Raw | ConvertFrom-Json\n"
        "$p=@{task_id=$t.task_id;status='OK';opju_path='fake.opju';reopen_check='PASS:FAKE';"
        "exports=@();log=@();error='';completed_at='now'} | ConvertTo-Json\n"
        "[IO.File]::WriteAllText($Result,$p,[Text.Encoding]::UTF8)\n", encoding="utf-8")
    result = origin_bridge.run_task(conn, a["task_id"], tmp_path, worker=worker)
    assert result["status"] == "OK"
    assert conn.execute("SELECT status FROM origin_tasks WHERE task_id=?",
                        (a["task_id"],)).fetchone()["status"] == "OK"
    assert conn.execute("SELECT status FROM origin_tasks WHERE task_id=?",
                        (b["task_id"],)).fetchone()["status"] == "QUEUED"

    worker.write_text(
        "param([string]$Task,[string]$Result)\n"
        "$p=@{status='FAILED';error='SIMULATED';exports=@();log=@()} | ConvertTo-Json\n"
        "[IO.File]::WriteAllText($Result,$p,[Text.Encoding]::UTF8)\n", encoding="utf-8")
    bad = origin_bridge.run_task(conn, b["task_id"], tmp_path, worker=worker)
    assert bad["status"] == "FAILED" and bad["error"] == "SIMULATED"


def test_web_s09_pages_and_actions(client, tmp_path, monkeypatch, app):
    _copy_s08_evidence(tmp_path)
    assert client.get("/s09").status_code == 200
    response = client.post("/s09", data={"action": "figures", "run_id": "WEB-RUN"})
    assert response.status_code == 200
    assert b"16" in response.data
    response = client.post("/s09", data={"action": "animation", "formats": "GIF"})
    assert response.status_code == 200
    assert "动画导出完成".encode("utf-8") in response.data

    conn = app.db if hasattr(app, "db") else None
    del conn
    monkeypatch.setattr(origin_bridge, "run_task", lambda *args, **kwargs: {"status": "OK"})
    response = client.post("/s09", data={"action": "origin", "figures": "F09-01"})
    assert response.status_code == 200
    assert "已入队".encode("utf-8") in response.data
