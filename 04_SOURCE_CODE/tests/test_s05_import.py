# -*- coding: utf-8 -*-
"""S05 环境导入：CSV/XLSX、时区、单位、缺测异常、重复与来源冲突、自动获取失败。"""
from __future__ import annotations

import json

import pytest

from app.services import environment_analysis as analysis
from app.services import environment_fetch as fetch
from app.services import environment_import as importer
from s05_helpers import register, write_env_csv, write_env_xlsx


def _map(**kwargs):
    base = dict(variable="WIND_SPEED", timezone="Asia/Shanghai",
                datetime_column="observed_at", value_column="value",
                unit_column="unit", location_key="SOURCE_GRID")
    base.update(kwargs)
    return importer.Mapping(**base)


def test_csv_import_timezone_unit_and_preview(s03_conn, tmp_path):
    path = write_env_csv(tmp_path / "wind.csv",
                         ["observed_at", "value", "unit"],
                         [["2026-10-31 00:00:00", 3.6, "km/h"],
                          ["2026-10-31 01:00:00", 7.2, "km/h"]])
    preview = importer.preview_file(path, _map())
    assert preview.row_count == 2 and preview.accepted_count == 2
    first = preview.accepted[0]
    assert first.value_si == pytest.approx(1.0)
    assert first.observed_at_utc == "2026-10-30T16:00:00Z"
    register(s03_conn, "SRC-CSV")
    out = importer.commit_import(s03_conn, path, _map(), "SRC-CSV", project_root=tmp_path)
    assert out["inserted"] == 2 and out["status"] == "IMPORTED"
    rows = s03_conn.execute("SELECT * FROM environment_observation ORDER BY obs_id").fetchall()
    assert rows[0]["unit"] == "KM/H" and rows[0]["value_si"] == pytest.approx(1.0)


def test_xlsx_metadata_forecast_and_model_flags(s03_conn, tmp_path):
    path = write_env_xlsx(
        tmp_path / "wind.xlsx",
        ["洞头附近逐小时风速", "北京时间｜10 米高度风速：米/秒",
         "说明｜数值气象模型逐小时数据；未来数值会随预报更新"],
        ["日期", "时间", "风速（米/秒）", "时段"],
        [["2026-10-31", "00:00:00", 2.0, "历史存档"],
         ["2026-11-10", "23:00:00", 9.0, "未来预报"]])
    headers, rows, metadata, sheet, header_row, kind = importer.read_table(path)
    assert kind == "XLSX" and header_row == 3 and "风速（米/秒）" in headers
    mapping = importer.Mapping(variable="WIND_SPEED", timezone="Asia/Shanghai",
                               date_column="日期", time_column="时间",
                               value_column="风速（米/秒）", unit_literal="M/S",
                               quality_column="时段", location_key="SOURCE_GRID")
    preview = importer.preview_file(path, mapping)
    assert preview.accepted_count == 2
    assert preview.accepted[0].quality_flag == "MODEL_HISTORICAL"
    assert preview.accepted[1].quality_flag == "FORECAST"
    assert analysis.observations(s03_conn, "WIND_SPEED") == []  # 预览不写库


def test_missing_anomaly_and_direction_circular_range(tmp_path):
    path = write_env_csv(tmp_path / "bad.csv", ["observed_at", "value", "unit"],
                         [["2026-10-31 00:00:00", "", "m/s"],
                          ["2026-10-31 01:00:00", "abc", "m/s"],
                          ["2026-10-31 02:00:00", -1, "m/s"],
                          ["", 2, "m/s"]])
    preview = importer.preview_file(path, _map())
    assert preview.accepted_count == 0 and preview.rejected_count == 4
    reasons = " ".join(r["reason"] for r in preview.rejected)
    assert "MISSING_VALUE" in reasons and "INVALID_VALUE" in reasons
    assert "ANOMALY_VALUE" in reasons and ("无法解析时间" in reasons or "缺少时间" in reasons)

    direction_path = write_env_csv(tmp_path / "dir.csv", ["observed_at", "value", "unit"],
                                   [["2026-10-31 00:00:00", 361, "degree"]])
    direction_preview = importer.preview_file(
        direction_path, _map(variable="WIND_DIRECTION", value_column="value"))
    assert direction_preview.rejected[0]["reason"].startswith("ANOMALY_VALUE")


def test_duplicate_and_source_conflict_never_overwrite(s03_conn, tmp_path):
    path = write_env_csv(tmp_path / "dup.csv", ["observed_at", "value", "unit"],
                         [["2026-10-31 00:00:00", 2.0, "m/s"]])
    register(s03_conn, "SRC-DUP")
    first = importer.commit_import(s03_conn, path, _map(), "SRC-DUP", project_root=tmp_path)
    second = importer.commit_import(s03_conn, path, _map(), "SRC-DUP", project_root=tmp_path)
    assert first["inserted"] == 1 and second["duplicates"] == 1 and second["inserted"] == 0

    other = write_env_csv(tmp_path / "conflict.csv", ["observed_at", "value", "unit"],
                          [["2026-10-31T00:00:00", 9.0, "m/s"]])
    third = importer.commit_import(s03_conn, other, _map(), "SRC-DUP", project_root=tmp_path)
    assert third["conflicts"] == 1 and third["inserted"] == 0
    value = s03_conn.execute("SELECT value_si FROM environment_observation").fetchone()["value_si"]
    assert value == pytest.approx(2.0)
    batches = [dict(r) for r in s03_conn.execute("SELECT * FROM environment_import_batch")]
    assert len(batches) == 3 and all(b["archive_path"] for b in batches)


def test_fetch_evaluation_and_failure_log(s03_conn):
    evaluation = fetch.evaluate()
    assert evaluation["enabled_adapters"] == []
    assert all(c["status"] == "BLOCKED" for c in evaluation["candidates"])
    known = fetch.attempt(s03_conn, "OPEN_METEO_MARINE", {})
    unknown = fetch.attempt(s03_conn, "NOT_A_SOURCE", {})
    assert known["status"] == "BLOCKED" and unknown["status"] == "FAILED"
    logs = [dict(r) for r in s03_conn.execute("SELECT * FROM environment_fetch_log")]
    assert len(logs) == 2 and "未注册" in logs[1]["error_message"]


def test_csv_autodetect_header_and_gb18030(s03_conn, tmp_path):
    path = write_env_csv(tmp_path / "gb.csv", ["日期时间", "风速", "单位"],
                         [["2026-10-31 03:00:00", 3600, "m/h"]], encoding="gb18030")
    headers, rows, metadata, sheet, header_row, kind = importer.read_table(path)
    mapping = importer.suggest_mapping(headers, variable="WIND_SPEED")
    assert kind == "CSV" and mapping.value_column == "风速" and mapping.datetime_column == "日期时间"
    assert mapping.unit_literal is None  # 不猜单位；显式列优先
    mapping.unit_column = "单位"
    preview = importer.preview_file(path, mapping)
    assert preview.rejected_count == 1  # m/h 不是已登记单位，拒绝而非静默换算
