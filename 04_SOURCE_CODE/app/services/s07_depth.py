# -*- coding: utf-8 -*-
"""S07 近底 QC 与三水层：只追加区内排除与分层，不恢复人工截断外信号。"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import statistics
import uuid
from collections import defaultdict
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from . import beam_geometry as geo
from . import csv_parser, daily_stats as ds, distance_mapping as dm

METHOD_VERSION = "S07_LAYER_QCV1"
LAYERS = ("UPPER", "MIDDLE", "LOWER", "NA")
EVENT_THRESHOLD = 200.0
EVENT_MIN_BINS = 3


class DepthAnalysisUnavailable(ValueError):
    pass


def _now() -> str:
    return datetime.now(dt_timezone.utc).isoformat(timespec="seconds")


def _source_path(conn: sqlite3.Connection, device_id: str, observed_date: str,
                 project_root: Path) -> tuple[Path, str, dict]:
    stat = ds.latest_stat(conn, device_id, observed_date)
    if stat is None or stat["status"] in ("MISSING", "QC_FAILED", "BLOCKED", "UNKNOWN"):
        raise DepthAnalysisUnavailable(f"{device_id}/{observed_date} 无可用 S03 统计行")
    registry = conn.execute(
        "SELECT * FROM file_registry WHERE device_id=? AND observed_date=? AND status='IMPORTED' "
        "ORDER BY registered_at DESC LIMIT 1", (device_id, observed_date)).fetchone()
    if registry is None:
        raise DepthAnalysisUnavailable(f"{device_id}/{observed_date} 无已导入原始文件登记")
    path = project_root / registry["relative_path"]
    if not path.exists():
        raise DepthAnalysisUnavailable(f"原始文件不存在：{path}")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if sha != registry["sha256"] or sha != stat["file_sha256"]:
        raise DepthAnalysisUnavailable("原始文件哈希与 S03 统计/登记不一致，拒绝分层")
    return path, sha, stat


def _layer_of(r_m: float, height_m: float, alpha_rad: float) -> str:
    z = height_m - r_m * math.sin(alpha_rad)
    if z < -1e-9 or z > height_m + 1e-9:
        return "NA"
    if z > 2 * height_m / 3:
        return "UPPER"
    if z > height_m / 3:
        return "MIDDLE"
    return "LOWER"


def analyze_device_day(conn: sqlite3.Connection, device_id: str, observed_date: str,
                       *, project_root: Path | None = None,
                       actor: str = "S07") -> dict:
    """单设备单日：同一遍扫描同时生成近底 QC 与三水层统计；使用同一硬掩码。"""
    root = Path(project_root or Path(__file__).resolve().parents[2])
    path, sha, stat = _source_path(conn, device_id, observed_date, root)
    params = geo.effective_params(conn, device_id, observed_date)
    bottom = params.get("bottom_reference")
    height = (bottom or {}).get("vertical_height_m") or params.get("derived_vertical_clearance_m")
    tilt = params.get("downward_tilt_deg")
    if not height or tilt is None:
        raise DepthAnalysisUnavailable(f"{device_id}/{observed_date} 缺离底高度或倾角，分层 BLOCKED")
    geom = geo.beam_geometry(
        height_m=float(height), tilt_deg=float(tilt),
        beam_value_deg=float(params["beam_angle_value_deg"]),
        beam_kind=params["beam_angle_kind"], cutoff_m=float(params["analysis_cutoff_slant_m"]),
        r0_m=0.0)
    context = ds.resolve_stat_context(conn, device_id)
    mapping = context.mapping
    if mapping is None:
        raise DepthAnalysisUnavailable(f"{device_id} 距离映射未核实")
    alpha = math.radians(float(tilt))
    first = mapping.first_sample_distance_m or 0.0
    step = mapping.sample_interval_m or 0.0
    near_edge = geom["steeper_edge_bottom_m"] or math.inf
    center_bottom = geom["center_axis_bottom_m"]
    near_count = after_count = 0
    acc = {layer: {"kept": 0, "events": 0, "values": [], "r": [], "z": []}
           for layer in LAYERS}
    inspection = csv_parser.inspect_file(path)
    for row in csv_parser.iter_rows(inspection):
        if row.timestamp is None or row.timestamp.date().isoformat() != observed_date:
            continue
        if row.effective_signal_len == 0:
            continue
        try:
            mask = dm.build_mask(row.signal[:row.effective_signal_len], mapping,
                                 context.cutoff_m, row_range_m=row.range_m,
                                 row_point_count=row.effective_signal_len,
                                 allow_blocked=False)
        except dm.DistanceMappingBlocked:
            continue
        previous_index = None
        run = 0
        for index, value in zip(mask.kept_indices, mask.kept_values):
            r = first + index * step
            if r >= center_bottom:
                after_count += 1
            if r >= near_edge:
                near_count += 1
            layer = _layer_of(r, float(height), alpha)
            bucket = acc[layer]
            bucket["kept"] += 1
            bucket["values"].append(value)
            bucket["r"].append(r)
            bucket["z"].append(float(height) - r * math.sin(alpha))
            if value >= EVENT_THRESHOLD and previous_index is not None \
                    and index == previous_index + 1 and _layer_of(first + previous_index * step,
                                                                  float(height), alpha) == layer:
                run += 1
                if run == EVENT_MIN_BINS - 1:
                    bucket["events"] += 1
            else:
                run = 0
            previous_index = index
    status = "PENDING_REVIEW"
    if (bottom or {}).get("acoustic_bottom_status") == "DETECTED":
        status = "CONFIRMED_REVIEW"
    qc_id = None
    conn.execute(
        "INSERT OR REPLACE INTO s07_bottom_qc (device_id,observed_date,parameter_id,"
        "bottom_reference_id,method,status,center_axis_bottom_m,near_edge_bottom_m,"
        "far_edge_bottom_m,near_bottom_candidate_samples,bottom_after_candidate_samples,"
        "excluded_samples,reason,details_json,created_at,created_by) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (device_id, observed_date, params["parameter_id"],
         (bottom or {}).get("reference_id"), "MANUAL_REFERENCE", status,
         center_bottom, near_edge, geom["flatter_edge_bottom_m"], near_count, after_count, 0,
         "人工底界未实测/未逐角确认：近底仅标记候选，不额外排除；截断外仍被 S02 硬掩码屏蔽",
         json.dumps(geom, ensure_ascii=False), _now(), actor))
    conn.commit()
    qc_id = conn.execute(
        "SELECT qc_id FROM s07_bottom_qc WHERE device_id=? AND observed_date=? "
        "AND method='MANUAL_REFERENCE' AND status=?",
        (device_id, observed_date, status)).fetchone()["qc_id"]
    rows = []
    for layer in LAYERS:
        bucket = acc[layer]
        if not bucket["kept"]:
            continue
        values = bucket["values"]
        conn.execute(
            "INSERT OR REPLACE INTO s07_layer_stats (device_id,observed_date,layer,parameter_id,"
            "mapping_version,method_version,file_sha256,kept_samples,candidate_events,"
            "signal_mean,signal_median,min_range_m,max_range_m,min_height_above_bottom_m,"
            "max_height_above_bottom_m,created_at,created_by) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (device_id, observed_date, layer, params["parameter_id"], mapping.version,
             METHOD_VERSION, sha, bucket["kept"], bucket["events"],
             statistics.fmean(values), statistics.median(values),
             min(bucket["r"]), max(bucket["r"]), min(bucket["z"]), max(bucket["z"]),
             _now(), actor))
        rows.append(dict(conn.execute(
            "SELECT * FROM s07_layer_stats WHERE device_id=? AND observed_date=? AND layer=?",
            (device_id, observed_date, layer)).fetchone()))
    conn.commit()
    return {
        "analysis_id": "LAY-" + uuid.uuid4().hex[:12].upper(),
        "device_id": device_id, "observed_date": observed_date,
        "file_sha256": sha, "parameter_id": params["parameter_id"],
        "parameter_version": params["version"], "bottom_reference_id": (bottom or {}).get("reference_id"),
        "height_m": float(height), "tilt_deg": float(tilt), "cutoff_m": float(params["analysis_cutoff_slant_m"]),
        "geometry": geom, "qc": {"qc_id": qc_id, "status": status,
                                 "near_bottom_candidates": near_count,
                                 "bottom_after_candidates": after_count,
                                 "excluded_samples": 0},
        "layers": rows, "method_version": METHOD_VERSION,
    }
