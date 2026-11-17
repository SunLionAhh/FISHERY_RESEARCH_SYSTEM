# -*- coding: utf-8 -*-
"""S05 联合分析：全候选时滞、置信区间/多重比较、有效样本、缺变量 BLOCKED、网页入口。"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from app.services import environment_analysis as analysis
from app.services import environment_import as importer
from s04_helpers import seed_stat
from s05_helpers import register, write_env_csv


def _events(day_index: int) -> list[int]:
    rng = random.Random(1000 + day_index)
    return [rng.randint(2, 14) for _ in range(24)]


def _seed_days(conn, count: int, start=1):
    for index in range(count):
        day = f"2026-11-{start + index:02d}"
        seed_stat(conn, "2000", day, hourly_events=_events(index))


def _export_hourly(conn, path, variable, location_key, *, shift_hours=0, transform=lambda v: v):
    rows = []
    acoustic = analysis.acoustic_hourly(conn, ("2000",), None, None)
    for (_, stamp), record in sorted(acoustic.items()):
        local = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S") - timedelta(hours=shift_hours)
        rows.append([local.strftime("%Y-%m-%dT%H:%M:%S"),
                     f"{transform(record['candidate_events']):.6f}",
                     "m/s" if variable == "WIND_SPEED" else "CELSIUS"])
    return write_env_csv(path, ["observed_at", "value", "unit"], rows)


def _import(conn, path, variable, location_key, source_id, project_root):
    register(conn, source_id)
    mapping = importer.Mapping(variable=variable, timezone="Asia/Shanghai",
                               datetime_column="observed_at", value_column="value",
                               unit_column="unit", location_key=location_key)
    return importer.commit_import(conn, path, mapping, source_id, project_root=project_root)


def test_all_seven_lags_reported_and_no_cherry_pick(s03_conn, tmp_path):
    _seed_days(s03_conn, 8)
    path = _export_hourly(s03_conn, tmp_path / "lag_wind.csv", "WIND_SPEED", "SOURCE_GRID",
                          shift_hours=2)
    assert _import(s03_conn, path, "WIND_SPEED", "SOURCE_GRID", "SRC-LAG", tmp_path)["inserted"] == 192
    result = analysis.run(s03_conn, devices=("2000",), start_date="2026-11-01",
                          end_date="2026-11-08")
    block = result["lag_analysis"]["WIND_SPEED"]
    assert len(block["results"]) == 7
    assert [item["lag_hours"] for item in block["results"]] == [0, 1, 2, 3, 6, 12, 24]
    assert all("p_holm" in item for item in block["results"])
    best = max(block["results"], key=lambda item: abs(item["r"] or 0))
    assert best["lag_hours"] == 2 and best["r"] > 0.99
    assert best["ci95"][0] is not None and best["ci95"][1] is not None
    assert best["n_pairs"] == 192
    assert "未做变显著挑选" in block["note"]


def test_missing_variables_are_blocked_not_fabricated(s03_conn):
    _seed_days(s03_conn, 2)
    result = analysis.run(s03_conn, devices=("2000",))
    assert result["variables"]["TIDE_HEIGHT"]["status"] == "BLOCKED"
    assert "不估读图片" in result["variables"]["TIDE_HEIGHT"]["reason"]
    assert result["variables"]["WIND_DIRECTION"]["status"] == "BLOCKED"
    assert result["joint_analysis"]["status"] == "BLOCKED"
    assert "关联≠因果" in result["disclaimer"]


def test_joint_analysis_requires_common_samples(s03_conn, tmp_path):
    _seed_days(s03_conn, 12)
    wind = _export_hourly(s03_conn, tmp_path / "joint_wind.csv", "WIND_SPEED", "SOURCE_GRID")
    temp = _export_hourly(s03_conn, tmp_path / "joint_temp.csv", "WATER_TEMP", "DEFAULT",
                          transform=lambda v: 20 + v / 10)
    _import(s03_conn, wind, "WIND_SPEED", "SOURCE_GRID", "SRC-W", tmp_path)
    _import(s03_conn, temp, "WATER_TEMP", "DEFAULT", "SRC-T", tmp_path)
    result = analysis.run(s03_conn, devices=("2000",))
    joint = result["joint_analysis"]
    assert joint["status"] in ("OK", "UNCERTAIN")
    assert joint["n_common"] == 288
    assert set(joint["variables"]) == {"WIND_SPEED", "WATER_TEMP"}
    assert "intercept" in joint["standardized_beta"]
    assert 0 <= joint["r_squared"] <= 1


def test_derived_proxy_is_flagged_and_excluded_from_joint(s03_conn, tmp_path):
    _seed_days(s03_conn, 12)
    temp = _export_hourly(s03_conn, tmp_path / "proxy.csv", "WATER_TEMP", "DEFAULT")
    register(s03_conn, "SRC-PROXY", kind="DERIVED")
    mapping = importer.Mapping(variable="WATER_TEMP", timezone="Asia/Shanghai",
                               datetime_column="observed_at", value_column="value",
                               unit_column="unit", location_key="DEFAULT")
    importer.commit_import(s03_conn, temp, mapping, "SRC-PROXY", project_root=tmp_path)
    report = analysis.variable_report(
        s03_conn, analysis.acoustic_hourly(s03_conn, ("2000",), None, None),
        "WATER_TEMP", "DEFAULT", bins=analysis.TEMP_BINS)
    assert "派生代理" in report["proxy_warning"]
    joint = analysis.joint_analysis(
        s03_conn, analysis.acoustic_hourly(s03_conn, ("2000",), None, None),
        ["WATER_TEMP"], {"WATER_TEMP": "DEFAULT"})
    assert joint["status"] == "BLOCKED" and "独立" in joint["reason"]


def test_statistical_helpers():
    assert analysis.pearson([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert analysis.pearson([1, 2, 3], [1]) is None
    assert analysis.autocorr1([1, 2, 3, 4]) > 0
    result = analysis._fisher(0.6, 50)
    assert result["ci95"][0] < 0.6 < result["ci95"][1]
    assert 0 < result["p_two_sided"] < 1
    items = [{"p_two_sided": 0.01}, {"p_two_sided": 0.04}, {"p_two_sided": 0.2}]
    adjusted = analysis.holm_adjust(items)
    assert adjusted[0]["p_holm"] == 0.03 and adjusted[2]["p_holm"] == 0.2


def test_web_environment_routes(client, s03_conn, tmp_path):
    assert client.get("/environment").status_code == 200
    assert client.get("/environment/analysis").status_code == 200
    path = write_env_csv(tmp_path / "web_wind.csv", ["observed_at", "value", "unit"],
                         [["2026-10-31T00:00:00", 2.0, "m/s"]])
    response = client.post("/environment/import", data={
        "action": "preview", "file_path": str(path), "source_id": "SRC-WEB",
        "variable": "WIND_SPEED", "timezone": "Asia/Shanghai",
        "value_col": "value", "datetime_col": "observed_at", "unit_col": "unit"})
    assert response.status_code == 200 and b"wind.csv" in response.data
    attempt = client.post("/environment/fetch-attempt", data={"adapter": "NOAA_COOPS_TIDE"})
    assert attempt.status_code == 302
