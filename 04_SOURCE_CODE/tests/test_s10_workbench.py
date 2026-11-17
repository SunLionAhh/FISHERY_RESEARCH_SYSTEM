# -*- coding: utf-8 -*-
"""S10：31 类入口、全局选择、联动导出、备份页与一键启动。"""
from __future__ import annotations

from pathlib import Path

from app.services import workbench
from s04_helpers import seed_stat

ROOT = Path(__file__).resolve().parents[2]


def test_entries_are_exactly_31_and_cover_all_groups():
    assert len(workbench.ENTRIES) == 31
    ids = [row[0] for row in workbench.ENTRIES]
    assert ids == list(range(1, 32))
    urls = {row[3] for row in workbench.ENTRIES}
    assert {"/", "/devices/2000", "/s07", "/s08", "/compare", "/environment",
            "/intraday", "/s09", "/workbench", "/workbench/backups"} <= urls


def test_context_exposes_cutoff_quality_and_global_selection(conn):
    seed_stat(conn, "2000", "2026-10-31")
    ctx = workbench.context(conn, device="2000", start="2026-10-31", end="2026-10-31")
    assert len(ctx["entries"]) == 31
    assert ctx["selected_device"] == "2000"
    assert ctx["cutoffs"][0]["device_id"] == "2000"
    assert ctx["cutoffs"][0]["cutoff_m"] == 5.2
    assert ctx["quality"]["complete_days"] >= 1
    assert "device=2000" in ctx["entries"][0]["url_q"]


def test_linked_view_and_exports(conn, tmp_path):
    seed_stat(conn, "2000", "2026-10-31", events=12)
    rows = workbench.linked_view(conn, ("2000",), "2026-10-31", "2026-10-31")
    assert len(rows) == 1
    assert rows[0]["status"] == "COMPLETE"
    csv_path = tmp_path / "linked.csv"
    md_path = tmp_path / "report.md"
    workbench.write_csv(rows, csv_path)
    ctx = workbench.context(conn, device="2000", start="2026-10-31", end="2026-10-31")
    workbench.write_report(ctx, rows, md_path)
    assert "device_id" in csv_path.read_text(encoding="utf-8-sig")
    assert "人工截断" in md_path.read_text(encoding="utf-8")
    assert "5.2" in md_path.read_text(encoding="utf-8")


def test_web_workbench_pages_and_exports(client, app):
    response = client.get("/workbench?device=2000&start=2026-10-31&end=2026-10-31")
    assert response.status_code == 200
    assert "31 类工作台入口".encode("utf-8") in response.data
    assert "人工截断与版本".encode("utf-8") in response.data
    csv_response = client.get("/workbench/export.csv?device=2000&start=2026-10-31&end=2026-10-31")
    assert csv_response.status_code == 200
    assert b"device_id" in csv_response.data
    md_response = client.get("/workbench/report.md?device=2000&start=2026-10-31&end=2026-10-31")
    assert md_response.status_code == 200
    assert "人工截断".encode("utf-8") in md_response.data
    backups = client.get("/workbench/backups")
    assert backups.status_code == 200
    assert "SHA-256".encode("utf-8") in backups.data
    assert (Path(app.config["PROJECT_ROOT"]) / "10_TEST_REPORTS" / "s10_verification"
            / "workbench_linked.csv").exists()


def test_one_click_launcher_and_local_bind():
    launcher = ROOT / "启动工作台.bat"
    assert launcher.exists()
    content = launcher.read_text(encoding="utf-8")
    assert ".venv\\Scripts\\python.exe" in content
    assert "127.0.0.1:5000/workbench" in content
    run_py = (ROOT / "04_SOURCE_CODE" / "run.py").read_text(encoding="utf-8")
    assert 'host="127.0.0.1"' in run_py
    assert "debug=False" in run_py
