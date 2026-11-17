# -*- coding: utf-8 -*-
"""S05 测试夹具：合成环境文件与来源登记（标注为验收合成数据）。"""
from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook

from app.services import environment_import as importer


def write_env_csv(path: Path, headers, rows, *, encoding="utf-8-sig"):
    with path.open("w", encoding=encoding, newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return path


def write_env_xlsx(path: Path, metadata, headers, rows, *, sheet="逐小时风速"):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for line in metadata:
        ws.append([line])
    ws.append(headers)
    for row in rows:
        ws.append(list(row))
    wb.save(path)
    return path


def register(conn, source_id: str, *, kind="MANUAL", provider="验收合成数据",
             observed="OBSERVED", note="验收合成数据，不进入真实研究结论"):
    return importer.register_source(
        conn, source_id, name=source_id, kind=kind, provider=provider,
        observed_or_forecast=observed, quality_note=note,
        spatial_coverage="合成", time_resolution="逐小时",
        units_json={"WIND_SPEED": "M/S", "WATER_TEMP": "CELSIUS"})
