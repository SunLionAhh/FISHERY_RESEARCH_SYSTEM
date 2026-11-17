# -*- coding: utf-8 -*-
"""S04 Web 入口：比较表单、执行结果与输入校验。"""
from __future__ import annotations

from s04_helpers import seed_stat


def test_compare_index(client, s03_conn):
    response = client.get("/compare")
    assert response.status_code == 200
    assert b"S04" in response.data and "任意比较".encode() in response.data


def test_compare_run_renders_result_and_persists(client, s03_conn):
    seed_stat(s03_conn, "2000", "2026-10-01", events=4)
    seed_stat(s03_conn, "2000", "2026-10-02", events=8)
    response = client.post("/compare/run", data={
        "devices": "2000", "dates": "2026-10-01,2026-10-02", "name": "网页冒烟",
    })
    assert response.status_code == 200
    assert b"CMP-" in response.data and b"D1_vs_D2" in response.data
    runs = s03_conn.execute("SELECT COUNT(*) FROM comparison_runs").fetchone()[0]
    assert runs == 1


def test_compare_run_invalid_hour_returns_400(client, s03_conn):
    seed_stat(s03_conn, "2000", "2026-10-01")
    response = client.post("/compare/run", data={
        "devices": "2000", "dates": "2026-10-01", "hour_start": "6", "hour_end": "6",
    })
    assert response.status_code == 400
    assert "无法执行".encode() in response.data


def test_compare_run_with_baseline(client, s03_conn):
    for day in ("2026-10-01", "2026-10-02", "2026-10-03"):
        seed_stat(s03_conn, "2000", day, events=6)
    response = client.post("/compare/run", data={
        "devices": "2000", "dates": "2026-10-01,2026-10-02,2026-10-03",
        "baseline_mode": "valid", "baseline_reference_date": "2026-10-03", "baseline_n": "2",
    })
    assert response.status_code == 200
    assert "历史基线".encode() in response.data
