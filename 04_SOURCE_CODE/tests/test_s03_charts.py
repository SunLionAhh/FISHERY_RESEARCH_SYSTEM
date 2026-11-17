# -*- coding: utf-8 -*-
"""S03 基础图表与日报工件：数量、文件头、配色、缺测不伪造。"""
from __future__ import annotations

import json
from pathlib import Path

from app.services import daily_stats as ds
from app.services import incremental as inc
from app.services import reporting
from s03_helpers import write_fishfinder_csv

PNG_HEADER = b"\x89PNG\r\n\x1a\n"
EXPECTED_CHARTS = ("daily_activity.png", "signal_distribution.png", "coverage.png",
                   "missing_status.png", "bottom_exclusion.png", "daily_stats_table.png")


def test_palette_comes_from_approved_spec():
    repo = Path(__file__).resolve().parents[2]
    colors = reporting._palette(repo)
    spec = json.loads((repo / "05_CONFIG" / "figure_palette.json").read_text(encoding="utf-8"))
    expected = [c["hex"] for c in spec["palettes"]["A_SCIENTIFIC_PRIMARY"]["colors"]]
    assert colors == expected
    assert colors[3] == "#0271AC"


def test_generate_all_outputs(s03_conn, tmp_path):
    path = write_fishfinder_csv(tmp_path / "探鱼-2000_2027-12-11.csv", "2000", "2027-12-11")
    out = inc.register_upload(s03_conn, "2000", path,
                              project_root=tmp_path, output_root=tmp_path / "out")
    assert len(out.artifacts) == 8
    figure_dir = tmp_path / "out" / "07_FIGURES" / "s03" / "2000" / "2027-12-11"
    for name in EXPECTED_CHARTS:
        p = figure_dir / name
        assert p.exists() and p.stat().st_size > 1000
        assert p.read_bytes()[:8] == PNG_HEADER
    result_dir = tmp_path / "out" / "06_ANALYSIS_RESULTS" / "s03" / "daily" / "2000" / "2027-12-11"
    csv_text = (result_dir / "daily_statistics.csv").read_text(encoding="utf-8-sig")
    assert "numerator" in csv_text and "NA" in csv_text
    report = (result_dir / "daily_report.md").read_text(encoding="utf-8")
    assert "硬掩码" in report and "build_mask" in report and "不填 0" in report
    artifacts = [a["relative_path"] for a in s03_conn.execute(
        "SELECT relative_path FROM s03_artifacts WHERE run_id=?", (out.run_id,))]
    assert len(artifacts) == 8


def test_missing_day_chart_does_not_fabricate_values(s03_conn, tmp_path):
    stat_id = inc.mark_missing(s03_conn, "2000", "2027-12-12", project_root=tmp_path)
    row = dict(s03_conn.execute("SELECT * FROM daily_statistics WHERE stat_id=?", (stat_id,)).fetchone())
    paths = reporting.generate_daily_outputs(
        s03_conn, row, project_root=Path(__file__).resolve().parents[2], output_root=tmp_path / "na_out")
    assert len(paths) == 8
    table_csv = [p for p in paths if p.endswith("daily_statistics.csv")][0]
    text = Path(table_csv).read_text(encoding="utf-8-sig")
    assert "raw_records,NA" in text
    assert "candidate_events,NA" in text
