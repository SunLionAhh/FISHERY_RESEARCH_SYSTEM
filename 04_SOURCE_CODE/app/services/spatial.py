# -*- coding: utf-8 -*-
"""S08 五站 GPS 空间与动态分析：缺站缺测 NA，不虚构轨迹或密度插值。"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import shutil
import sqlite3
import statistics
import uuid
from collections import Counter
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from . import beam_geometry as geo
from . import comparison as cmp
from . import daily_stats as ds
from . import query_context as qc
from . import s07_patterns as patterns
from . import spatial_grouping as grouping
from . import v41_contracts as v41

METHOD_VERSION = "S08_SPATIAL_V1"
COMBINATION_METHOD_VERSION = "S08_ANY_COMBINATION_V1"
DEVICE_IDS = ("2000", "2001", "2002", "2003", "2005")
UNDECLARED_CRS = "UNDECLARED"
KNOWN_CRS = {"WGS84", "EPSG:4326", "CGCS2000", "EPSG:4490"}
MIN_COVERAGE_RATIO = 0.5
LOCAL_TIMEZONE = "Asia/Shanghai"
ENV_VARIABLES = ("WATER_TEMP", "TIDE_HEIGHT", "WIND_SPEED", "WIND_DIRECTION")
DEFAULT_DATASET_ID = "DATASET_01_DUAL_STATION"
COMPARISON_MODES = ("independent", "common_valid", "baseline_change")


class SpatialValidationError(ValueError):
    pass


def parse_devices(value) -> list[str]:
    """解析表单/CLI 中的设备选择；支持 1—5 台任意组合，顺序按五站固定次序。"""
    if value is None:
        raise SpatialValidationError("至少选择一台设备")
    if isinstance(value, str):
        tokens = [part.strip() for part in value.split(",") if part.strip()]
    else:
        try:
            tokens = [str(part).strip() for part in value if str(part).strip()]
        except TypeError as exc:
            raise SpatialValidationError("设备选择格式不合法") from exc
    return validate_devices(tokens)


def validate_devices(devices) -> list[str]:
    if devices is None:
        raise SpatialValidationError("至少选择一台设备")
    selected = list(dict.fromkeys(str(device).strip() for device in devices if str(device).strip()))
    if not selected:
        raise SpatialValidationError("至少选择一台设备")
    unknown = [d for d in selected if d not in DEVICE_IDS]
    if unknown:
        raise SpatialValidationError("不支持的设备：" + "、".join(unknown))
    return [d for d in DEVICE_IDS if d in selected]


def _now() -> str:
    return datetime.now(dt_timezone.utc).isoformat(timespec="seconds")


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(min(1.0, a)))


def sync_from_positions(conn: sqlite3.Connection, *, actor: str = "S08") -> int:
    """把 S01 已填 GPS 接入站位表；station_id 不自动分配 P 码。"""
    inserted = 0
    for row in conn.execute("SELECT * FROM device_positions ORDER BY device_id, version"):
        effective = row["effective_from"] or "1970-01-01"
        exists = conn.execute(
            "SELECT 1 FROM station_location WHERE device_id=? AND effective_from=? "
            "AND position_source='S01_DEVICE_POSITIONS'", (row["device_id"], effective)).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO station_location (station_id,device_id,longitude_deg,latitude_deg,"
            "coordinate_reference_system,gps_accuracy_m,water_depth_m,position_source,"
            "measured_at,heading_deg,heading_reference,effective_from,effective_to,"
            "created_at,created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (None, row["device_id"], row["longitude_deg"], row["latitude_deg"],
             row["coordinate_reference_system"], None, None, "S01_DEVICE_POSITIONS",
             effective, row["heading_deg"], None, effective, row["effective_to"],
             _now(), actor))
        inserted += 1
    conn.commit()
    return inserted


def import_headings(conn: sqlite3.Connection, project_root: Path, records: list[dict], *,
                    effective_from: str, measured_at: str, actor: str = "S08") -> list[dict]:
    """把用户提供的方位角截图登记为新站位版本；坐标沿用当前生效记录，没有则不补。"""
    root = Path(project_root)
    image_dir = root / "10_TEST_REPORTS" / "s08_verification" / "heading_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    existing = {point["device_id"]: point for point in locations(conn, effective_from)}
    imported = []
    for record in records:
        device_id = record["device_id"]
        source_path = Path(record["image_path"])
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        target = image_dir / source_path.name
        shutil.copy2(source_path, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        point = existing.get(device_id, {})
        upsert_station(
            conn, device_id, station_id=point.get("station_id"),
            longitude=point.get("longitude_deg"), latitude=point.get("latitude_deg"),
            coordinate_reference_system=point.get("coordinate_reference_system"),
            gps_accuracy_m=point.get("gps_accuracy_m"), water_depth_m=point.get("water_depth_m"),
            heading_deg=float(record["heading_deg"]),
            heading_reference=record.get("heading_reference") or "PHONE_COMPASS_MAGNETIC_SCREENSHOT",
            position_source=record.get("position_source") or "USER_PROVIDED_COMPASS_IMAGE",
            measured_at=measured_at, effective_from=effective_from, actor=actor)
        imported.append({"device_id": device_id, "heading_deg": float(record["heading_deg"]),
                         "image": target.as_posix(), "sha256": digest,
                         "had_coordinates": point.get("longitude_deg") is not None})
    return imported


def upsert_station(conn: sqlite3.Connection, device_id: str, *, station_id: str | None,
                   longitude: float | None, latitude: float | None,
                   coordinate_reference_system: str | None = None,
                   gps_accuracy_m: float | None = None, water_depth_m: float | None = None,
                   heading_deg: float | None = None, heading_reference: str | None = None,
                   position_source: str = "USER_WEB", measured_at: str | None = None,
                   effective_from: str | None = None, actor: str = "web") -> int:
    effective = effective_from or measured_at or datetime.now(dt_timezone.utc).date().isoformat()
    if (longitude is None) != (latitude is None):
        raise SpatialValidationError("经纬度必须同时提供或同时为空")
    if longitude is not None and not (-180 <= longitude <= 180):
        raise SpatialValidationError("经度必须落在 [-180,180]")
    if latitude is not None and not (-90 <= latitude <= 90):
        raise SpatialValidationError("纬度必须落在 [-90,90]")
    if gps_accuracy_m is not None and gps_accuracy_m < 0:
        raise SpatialValidationError("GPS 精度不得为负")
    if water_depth_m is not None and water_depth_m <= 0:
        raise SpatialValidationError("水深必须为正值")
    if heading_deg is not None and not (0 <= heading_deg < 360):
        raise SpatialValidationError("探头水平朝向须落在 [0,360)°")
    conn.execute(
        "UPDATE station_location SET effective_to=? WHERE device_id=? AND effective_to IS NULL",
        (effective, device_id))
    cursor = conn.execute(
        "INSERT INTO station_location (station_id,device_id,longitude_deg,latitude_deg,"
        "coordinate_reference_system,gps_accuracy_m,water_depth_m,position_source,measured_at,"
        "heading_deg,heading_reference,effective_from,effective_to,created_at,created_by) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?)",
        (station_id or None, device_id, longitude, latitude, coordinate_reference_system,
         gps_accuracy_m, water_depth_m, position_source, measured_at, heading_deg,
         heading_reference, effective, _now(), actor))
    conn.commit()
    return int(cursor.lastrowid)


def locations(conn: sqlite3.Connection, observed_date: str | None = None) -> list[dict]:
    """按日期取生效站位；区间为 [effective_from, effective_to)，与 S01 口径一致。"""
    day = observed_date or datetime.now(dt_timezone.utc).date().isoformat()
    rows = conn.execute(
        "SELECT * FROM station_location WHERE effective_from<=? "
        "AND (effective_to IS NULL OR effective_to>?) ORDER BY device_id,effective_from DESC",
        (day, day)).fetchall()
    latest = {}
    for row in rows:
        latest.setdefault(row["device_id"], dict(row))
    return [latest[device] for device in DEVICE_IDS if device in latest]


def station_history(conn: sqlite3.Connection, device_id: str) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "SELECT * FROM station_location WHERE device_id=? ORDER BY effective_from DESC",
        (device_id,))]


def coordinate_audit(point: dict, peers: list[dict]) -> dict:
    """坐标审计：范围、坐标系声明、疑似颠倒、同点重复；只提示不自动改写。"""
    lon, lat = point.get("longitude_deg"), point.get("latitude_deg")
    crs = (point.get("coordinate_reference_system") or "").strip()
    range_ok = lon is not None and lat is not None and -180 <= lon <= 180 and -90 <= lat <= 90
    suspected_swap = False
    if range_ok and len(peers) >= 1:
        peer_lons = [p["longitude_deg"] for p in peers if p.get("longitude_deg") is not None]
        peer_lats = [p["latitude_deg"] for p in peers if p.get("latitude_deg") is not None]
        if peer_lons and peer_lats:
            suspected_swap = (min(peer_lats) <= lon <= max(peer_lats)
                              and min(peer_lons) <= lat <= max(peer_lons))
    duplicates = [p.get("station_id") or p["device_id"] for p in peers
                  if p["device_id"] != point["device_id"]
                  and p.get("longitude_deg") == lon and p.get("latitude_deg") == lat
                  and lon is not None]
    flags = []
    if lon is None or lat is None:
        flags.append("MISSING_COORDINATE")
    if not range_ok and lon is not None:
        flags.append("OUT_OF_RANGE")
    if not crs:
        flags.append("CRS_UNDECLARED")
    if suspected_swap:
        flags.append("SUSPECTED_LATLON_SWAP")
    if duplicates:
        flags.append("DUPLICATE_COORDINATE")
    return {"range_ok": bool(range_ok), "crs": crs or UNDECLARED_CRS,
            "crs_declared": bool(crs), "suspected_latlon_swap": suspected_swap,
            "duplicate_with": duplicates, "flags": flags,
            "status": "BLOCKED" if not range_ok or suspected_swap or duplicates else
                      ("PROVISIONAL" if not crs else "OK")}


def compute_distances(conn: sqlite3.Connection, observed_date: str | None = None,
                      *, actor: str = "S08") -> dict:
    """只在同一坐标系组内计算站距；坐标系未声明的组给 PROVISIONAL 近似，跨组拒绝混算。"""
    all_points = locations(conn, observed_date)
    points = [p for p in all_points if p["longitude_deg"] is not None
              and p["latitude_deg"] is not None]
    result, excluded = [], []
    for i, left in enumerate(points):
        left_crs = (left["coordinate_reference_system"] or "").strip().upper()
        for right in points[i + 1:]:
            right_crs = (right["coordinate_reference_system"] or "").strip().upper()
            name_a = left["station_id"] or left["device_id"]
            name_b = right["station_id"] or right["device_id"]
            if left_crs and right_crs and left_crs != right_crs:
                excluded.append({"station_a": name_a, "station_b": name_b,
                                 "reason": "坐标系不同且未转换，拒绝混算距离"})
                continue
            undeclared = not (left_crs or right_crs)
            method = "HAVERSINE_WGS84_ASSUMED_UNDECLARED" if undeclared else "HAVERSINE_WGS84"
            status = "PROVISIONAL" if undeclared else "OK"
            note = ("双方坐标系均未声明；按经纬度数值以 WGS84 近似，仅作相对位置示意，不作正式站距"
                    if undeclared else "同一声明坐标系内的球面距离近似")
            distance = haversine_m(left["longitude_deg"], left["latitude_deg"],
                                   right["longitude_deg"], right["latitude_deg"])
            conn.execute(
                "INSERT OR REPLACE INTO station_distance (station_a,station_b,device_a,device_b,"
                "distance_m,method,computed_at,crs_pair,status,note) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (name_a, name_b, left["device_id"], right["device_id"], distance, method,
                 _now(), left_crs or UNDECLARED_CRS, status, note))
            result.append({"station_a": name_a, "station_b": name_b,
                           "device_a": left["device_id"], "device_b": right["device_id"],
                           "distance_m": distance, "method": method, "crs_pair": left_crs or UNDECLARED_CRS,
                           "status": status, "note": note})
    conn.commit()
    return {"distances": result, "excluded": excluded,
            "note": "跨坐标系不混算；未声明坐标系的站距为 PROVISIONAL，不代表实测站距"}


def directional_footprint(heading_deg, geometry: dict, *, heading_reference: str | None = None) -> dict:
    """ heading 已提供时的条件方向足迹包络；不是实测足迹，不绑定坐标系。"""
    if heading_deg is None:
        return {"status": "UNKNOWN", "reason": "未提供探头水平朝向，不画方向足迹"}
    half = float(geometry["inputs"]["internal_half_angle_deg"])
    radius = float(geometry["water_projection_max_forward_m"])
    heading = float(heading_deg) % 360
    steps = max(8, int(half * 2))
    points = [[0.0, 0.0]]
    for index in range(steps + 1):
        bearing = heading - half + 2 * half * index / steps
        math_angle = math.radians((90.0 - bearing) % 360)
        points.append([round(radius * math.cos(math_angle), 4),
                       round(radius * math.sin(math_angle), 4)])
    return {"status": "CONDITIONAL_SECTOR", "heading_deg": heading,
            "heading_reference": heading_reference or "UNDECLARED",
            "half_angle_deg": half, "max_forward_m": round(radius, 4),
            "polygon_local_m": points,
            "note": ("以 heading=0° 朝北、顺时针为正的条件扇形包络；基于当日生效波束参数与"
                     "人工斜距上限，未做坐标系转换，不是实测鱼群位置或密度")}


def _cross(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    return abs(sum(_cross(points[i], points[(i + 1) % len(points)])
                   for i in range(len(points))) / 2)


def _ensure_ccw(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    signed = sum(_cross(points[i], points[(i + 1) % len(points)])
                 for i in range(len(points)))
    return points if signed >= 0 else list(reversed(points))


def _line_intersection(p1, p2, q1, q2) -> tuple[float, float]:
    r = (p2[0] - p1[0], p2[1] - p1[1])
    s = (q2[0] - q1[0], q2[1] - q1[1])
    denominator = _cross(r, s)
    if abs(denominator) < 1e-12:
        return p2
    t = _cross((q1[0] - p1[0], q1[1] - p1[1]), s) / denominator
    return (p1[0] + t * r[0], p1[1] + t * r[1])


def _clip_convex(subject: list[tuple[float, float]],
                 clip: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Sutherland-Hodgman：计算两个凸扇形的交集；仅作条件几何示意。"""
    output = list(subject)
    for index in range(len(clip)):
        edge_start = clip[index]
        edge_end = clip[(index + 1) % len(clip)]

        def inside(point):
            return _cross((edge_end[0] - edge_start[0], edge_end[1] - edge_start[1]),
                          (point[0] - edge_start[0], point[1] - edge_start[1])) >= -1e-9

        input_list = output
        output = []
        if not input_list:
            break
        previous = input_list[-1]
        for current in input_list:
            current_in, previous_in = inside(current), inside(previous)
            if current_in:
                if not previous_in:
                    output.append(_line_intersection(previous, current, edge_start, edge_end))
                output.append(current)
            elif previous_in:
                output.append(_line_intersection(previous, current, edge_start, edge_end))
            previous = current
    return output


def _local_offset_m(left: dict, right: dict) -> tuple[float, float]:
    """以左站为原点的局部切平面近似：x 向东、y 向北；短站距下仅作几何示意。"""
    lon_a, lat_a = left["longitude_deg"], left["latitude_deg"]
    lon_b, lat_b = right["longitude_deg"], right["latitude_deg"]
    dx = haversine_m(lon_a, lat_a, lon_b, lat_a) * (1 if lon_b >= lon_a else -1)
    dy = haversine_m(lon_a, lat_a, lon_a, lat_b) * (1 if lat_b >= lat_a else -1)
    return dx, dy


def _translated_sector(coverage: dict, offset: tuple[float, float]) -> list[tuple[float, float]] | None:
    direction = coverage.get("directional_footprint") or {}
    if direction.get("status") != "CONDITIONAL_SECTOR":
        return None
    points = [(float(x) + offset[0], float(y) + offset[1])
              for x, y in direction.get("polygon_local_m", [])]
    return _ensure_ccw(points) if len(points) >= 3 else None


def _conditional_overlap(left_coverage: dict, right_coverage: dict,
                         left_point: dict, right_point: dict) -> dict:
    """方向扇形的条件重叠面积；缺朝向/缺坐标返回 UNKNOWN，不把缺测写成 0。"""
    left_sector = _translated_sector(left_coverage, (0.0, 0.0))
    right_sector = _translated_sector(right_coverage,
                                      _local_offset_m(left_point, right_point))
    if not left_sector or not right_sector:
        reasons = []
        if not left_sector:
            reasons.append("A 站方向足迹不可用")
        if not right_sector:
            reasons.append("B 站方向足迹不可用")
        return {"status": "UNKNOWN", "area_m2": None, "reason": "；".join(reasons)}
    intersection = _clip_convex(left_sector, right_sector)
    area = _polygon_area(intersection) if len(intersection) >= 3 else 0.0
    return {
        "status": "NO_OVERLAP" if area <= 1e-6 else "CONDITIONAL_OVERLAP",
        "area_m2": round(area, 4),
        "method": "LOCAL_TANGENT_SECTOR_INTERSECTION",
        "heading_a_deg": (left_coverage.get("directional_footprint") or {}).get("heading_deg"),
        "heading_b_deg": (right_coverage.get("directional_footprint") or {}).get("heading_deg"),
        "heading_references": [
            (left_coverage.get("directional_footprint") or {}).get("heading_reference"),
            (right_coverage.get("directional_footprint") or {}).get("heading_reference")],
        "note": ("按当日生效参数、人工斜距上限与用户提供朝向计算的条件几何交集；"
                 "局部切平面近似，不是实测鱼群位置、密度或连通性证据"),
    }


def parameter_snapshot(conn: sqlite3.Connection, device_id: str, observed_date: str) -> dict:
    """每台设备独立取当日生效参数与人工底界，不借用其他设备或当前指针。"""
    try:
        params = geo.effective_params(conn, device_id, observed_date)
    except geo.GeometryUnavailable as exc:
        return {"device_id": device_id, "status": "UNKNOWN", "reason": str(exc),
                "analysis_cutoff_m": None, "parameter_version": None}
    bottom = params.get("bottom_reference")
    return {"device_id": device_id, "status": "OK",
            "parameter_version": params.get("version"),
            "effective_from": params.get("effective_from"),
            "analysis_cutoff_m": params.get("analysis_cutoff_slant_m"),
            "beam_angle_kind": params.get("beam_angle_kind"),
            "bottom_reference_status": (bottom or {}).get("status") or "NO_REFERENCE",
            "bottom_reference_id": (bottom or {}).get("reference_id")}


def map_payload(conn: sqlite3.Connection, observed_date: str | None = None,
                devices=None) -> dict:
    selected = validate_devices(devices) if devices is not None else list(DEVICE_IDS)
    points = [p for p in locations(conn, observed_date) if p["device_id"] in selected]
    activity = (daily_activity(conn, [p["device_id"] for p in points], observed_date, observed_date)
                if observed_date else {})
    stations = []
    for point in points:
        label = point["station_id"] or f"{point['device_id']}（P 码未提供）"
        audit = coordinate_audit(point, points)
        snapshot = parameter_snapshot(conn, point["device_id"],
                                      observed_date or point["effective_from"])
        coverage = {"status": "UNKNOWN", "reason": "缺参数、缺坐标或坐标审计阻断",
                    "parameter_snapshot": snapshot}
        if audit["range_ok"] and not audit["suspected_latlon_swap"] and snapshot["status"] == "OK":
            params_date = observed_date or point["effective_from"]
            try:
                params = geo.effective_params(conn, point["device_id"], params_date)
                geometry = geo.beam_geometry(
                    height_m=float(params["vertical_bottom_clearance_m"]),
                    tilt_deg=float(params["downward_tilt_deg"]),
                    beam_value_deg=float(params["beam_angle_value_deg"]),
                    beam_kind=params["beam_angle_kind"],
                    cutoff_m=float(params["analysis_cutoff_slant_m"]))
                radius = float(geometry["water_projection_max_forward_m"])
                half_angle = float(geometry["inputs"]["internal_half_angle_deg"])
                coverage = {"status": "CIRCLE_ONLY",
                            "coverage_model": "CONDITIONAL_SECTOR",
                            "cutoff_m": geometry["cutoff_locked_m"],
                            "coverage_radius_m": radius,
                            "half_angle_deg": half_angle,
                            "sector_area_m2": math.pi * radius * radius * half_angle / 180,
                            "retained_footprint_area_m2": geometry["retained_footprint"]["area_m2"],
                            "center_axis_bottom_m": geometry["center_axis_bottom_m"],
                            "directional_footprint": directional_footprint(
                                point["heading_deg"], geometry,
                                heading_reference=point["heading_reference"]),
                            "parameter_effective_from": params["effective_from"],
                            "parameter_version": snapshot["parameter_version"],
                            "analysis_cutoff_m": snapshot["analysis_cutoff_m"],
                            "assumption": "水平底面 + 人工斜距上限；圆/扇形为理论覆盖示意，不是鱼位置/密度"}
            except (geo.GeometryUnavailable, ValueError, TypeError, KeyError) as exc:
                coverage = {"status": "UNKNOWN", "reason": str(exc)}
        day_values = activity.get(point["device_id"], {}).get(observed_date) if observed_date else None
        stations.append({
            "label": label, "station_id": point["station_id"], "device_id": point["device_id"],
            "longitude_deg": point["longitude_deg"], "latitude_deg": point["latitude_deg"],
            "crs": audit["crs"], "coordinate_audit": audit,
            "heading_deg": point["heading_deg"], "gps_accuracy_m": point["gps_accuracy_m"],
            "water_depth_m": point["water_depth_m"], "source": point["position_source"],
            "measured_at": point["measured_at"], "effective_from": point["effective_from"],
            "coverage": coverage, "activity": day_values,
        })
    known = [s for s in stations if s["coordinate_audit"]["range_ok"]]
    bounds = ({"min_lon": min(s["longitude_deg"] for s in known),
               "max_lon": max(s["longitude_deg"] for s in known),
               "min_lat": min(s["latitude_deg"] for s in known),
               "max_lat": max(s["latitude_deg"] for s in known)} if known else None)
    distances = [dict(r) for r in conn.execute(
        "SELECT * FROM station_distance WHERE device_a IN (%s) AND device_b IN (%s) "
        "ORDER BY station_a,station_b" % (",".join("?" for _ in selected) if selected else "NULL",
                                          ",".join("?" for _ in selected) if selected else "NULL"),
        (*selected, *selected))]
    selected_set = set(selected)
    visible = {s["device_id"] for s in stations}
    return {"stations": stations, "bounds": bounds, "distances": distances,
            "unknown_devices": [d for d in selected if d not in visible],
            "map_mode": "OFFLINE_LOCAL_COORDINATE_SKETCH",
            "selected_devices": list(selected),
            "station_selection": [s["label"] for s in stations],
            "legend": {"activity_scale": "FIXED_PER_VIEW", "missing": "NA",
                       "circle": "理论斜距上限示意（非实测足迹）"},
            "note": "离线本地坐标示意图；不做在线底图、地图投影、鱼群轨迹或连续密度插值"}


def daily_activity(conn: sqlite3.Connection, devices, start: str, end: str) -> dict:
    devices = tuple(devices)
    result = {device: {} for device in devices}
    for row in ds.all_latest_stats(conn):
        if row["device_id"] not in devices or not start <= row["observed_date"] <= end:
            continue
        rate = (row["candidate_events"] / (row["valid_observation_duration_s"] / 3600)
                if row["status"] not in cmp.BASELINE_INVALID_STATUSES
                and row["valid_observation_duration_s"] else None)
        result[row["device_id"]][row["observed_date"]] = {
            "status": row["status"], "candidate_events": row["candidate_events"],
            "valid_hours": (row["valid_observation_duration_s"] or None) / 3600
            if row["valid_observation_duration_s"] else None,
            "coverage_ratio": row["coverage_ratio"], "rate_per_hour": rate,
        }
    return result


def time_curves(conn: sqlite3.Connection, devices, start: str, end: str) -> dict:
    """按选中设备返回逐小时活动与覆盖；缺测/低覆盖保留 NA，不填 0。"""
    devices = validate_devices(devices)
    result = {device: [] for device in devices}
    for row in conn.execute(
            "SELECT device_id,observed_date,SUBSTR(slot_start,12,2) AS hour,"
            "SUM(candidate_events) AS events,AVG(coverage_ratio) AS coverage,COUNT(*) AS slots "
            "FROM s06_time_grid WHERE device_id IN (%s) AND observed_date BETWEEN ? AND ? "
            "GROUP BY device_id,observed_date,hour ORDER BY device_id,observed_date,hour"
            % ",".join("?" for _ in devices), (*devices, start, end)):
        covered = row["coverage"] is not None and row["coverage"] >= MIN_COVERAGE_RATIO
        result[row["device_id"]].append({
            "timestamp_local": f"{row['observed_date']}T{row['hour']}",
            "observed_date": row["observed_date"], "hour": int(row["hour"]),
            "candidate_events": row["events"] if covered else None,
            "coverage_ratio": row["coverage"], "source_slots": row["slots"],
            "status": "OK" if covered else "NA"})
    return result


def common_valid_periods(conn: sqlite3.Connection, devices, start: str, end: str) -> dict:
    """按当前选择重新计算共同有效日与共同有效小时；单站即该站自身有效时段。"""
    devices = validate_devices(devices)
    daily = daily_activity(conn, devices, start, end)
    all_days = sorted(set().union(*(set(by_date) for by_date in daily.values())))
    valid_days = [day for day in all_days
                  if all(daily[device].get(day, {}).get("rate_per_hour") is not None
                         for device in devices)]
    curves = time_curves(conn, devices, start, end)
    hour_maps = [{r["timestamp_local"]: r for r in curves[device] if r["status"] == "OK"}
                 for device in devices]
    common_hours = sorted(set.intersection(*[set(h) for h in hour_maps])) if hour_maps else []
    return {"devices": list(devices), "common_dates": valid_days,
            "common_hours": common_hours, "n_common_days": len(valid_days),
            "n_common_hours": len(common_hours),
            "method": "按当前设备选择的逐日 rate_per_hour 与逐小时覆盖交集重算；缺测为 NA"}


def _safe_pairs(left: dict, right: dict, dates=None) -> list[tuple[float, float]]:
    keys = set(left) & set(right)
    if dates is not None:
        keys &= set(dates)
    return [(left[k]["rate_per_hour"], right[k]["rate_per_hour"]) for k in sorted(keys)
            if left[k].get("rate_per_hour") is not None and right[k].get("rate_per_hour") is not None]


def _pair_stat(device_a: str, device_b: str, daily: dict, dates=None) -> dict:
    values = _safe_pairs(daily[device_a], daily[device_b], dates)
    r = patterns._pearson([x for x, _ in values], [y for _, y in values])
    lagged = [(values[k][0], values[k + 1][1]) for k in range(len(values) - 1)]
    lag_r = patterns._pearson([x for x, _ in lagged], [y for _, y in lagged])
    return {"device_a": device_a, "device_b": device_b, "n_common": len(values),
            "pearson_r": r, "lag1_a_lead_b_r": lag_r,
            "status": "OK" if len(values) >= 3 and r is not None else "INSUFFICIENT_DATA",
            "note": "同期相关与 a 领先 1 日的相关都只称关联/时差；未校正时间自相关，不能证明迁移"}


def spatial_statistics(conn: sqlite3.Connection, devices, start: str, end: str) -> dict:
    devices = tuple(validate_devices(devices))
    daily = daily_activity(conn, devices, start, end)
    pairs = []
    for a, b in itertools.combinations(devices, 2):
        pairs.append(_pair_stat(a, b, daily))
    differences = {}
    for device in devices:
        rates = [v["rate_per_hour"] for v in daily[device].values()
                 if v.get("rate_per_hour") is not None]
        hours = [v["valid_hours"] for v in daily[device].values() if v.get("valid_hours")]
        differences[device] = {"n_days": len(rates),
                               "mean_rate": statistics.fmean(rates) if rates else None,
                               "cv": (statistics.pstdev(rates) / statistics.fmean(rates)
                                      if rates and statistics.fmean(rates) else None),
                               "valid_hours_total": sum(hours) if hours else 0,
                               "status": "OK" if len(rates) >= 3 else "INSUFFICIENT_DAYS"}
    all_dates = sorted({day for by_date in daily.values() for day in by_date})
    weekly_leaders = []
    for start_index in range(0, len(all_dates), 7):
        window = set(all_dates[start_index:start_index + 7])
        means = {}
        for device in devices:
            values = [v["rate_per_hour"] for day, v in daily[device].items()
                      if day in window and v.get("rate_per_hour") is not None]
            if values:
                means[device] = statistics.fmean(values)
        if len(means) >= 2:
            weekly_leaders.append(max(means, key=means.get))
    counts = Counter(weekly_leaders)
    top_share = max(counts.values()) / len(weekly_leaders) if weekly_leaders else None
    stability_status = ("PROVISIONAL" if len(weekly_leaders) >= 2 and top_share is not None
                        else "INSUFFICIENT_DATA")
    monthly = {}
    for device, by_date in daily.items():
        for day, value in by_date.items():
            if value.get("rate_per_hour") is not None:
                monthly.setdefault((device, day[:7]), []).append(value["rate_per_hour"])
    long_term = [{"device_id": device, "month": month,
                  "mean_rate": statistics.fmean(values), "n_days": len(values)}
                 for (device, month), values in sorted(monthly.items())]
    common = common_valid_periods(conn, devices, start, end)
    independent = []
    for device in devices:
        per_day = daily[device]
        independent.append({
            "device_id": device,
            "n_days": len(per_day),
            "valid_days": [day for day, value in per_day.items()
                           if value.get("rate_per_hour") is not None],
            "missing_days": [day for day, value in per_day.items()
                             if value.get("rate_per_hour") is None],
            "coverage_ratios": {day: value.get("coverage_ratio") for day, value in per_day.items()},
            "description": differences[device],
        })
    return {"pairs": pairs, "device_differences": differences,
            "modes": {
                "independent": {"status": "OK", "devices": independent,
                                "note": "各站独立描述；缺测站显示 NA 与覆盖率，不填 0"},
                "common_valid": {"status": "OK" if common["n_common_days"] else "INSUFFICIENT_DATA",
                                 "devices": list(devices),
                                 "common_dates": common["common_dates"],
                                 "n_common_days": common["n_common_days"],
                                 "n_common_hours": common["n_common_hours"],
                                 "pairs": [_pair_stat(a, b, daily, common["common_dates"])
                                           for a, b in itertools.combinations(devices, 2)],
                                 "note": common["method"]},
            },
            "common_valid_periods": common,
            "stability": {"status": stability_status, "windows": len(weekly_leaders),
                          "top_station_share": top_share,
                          "note": "格局稳定度仅按窗口内首位站重复出现比例；未独立验证，不升级为长期结论"},
            "long_term": long_term,
            "method_note": "Pearson/均值仅作探索；时间自相关、有效观测时长与伪重复未完全校正，不给因果或显著性结论"}


def heatmaps(conn: sqlite3.Connection, devices, start: str, end: str) -> dict:
    devices = tuple(validate_devices(devices))
    daily = daily_activity(conn, devices, start, end)
    dates = sorted({d for device in daily.values() for d in device})
    date_station = [{"observed_date": day, "device_id": device,
                     "status": daily[device].get(day, {}).get("status", "NA"),
                     "coverage_ratio": daily[device].get(day, {}).get("coverage_ratio"),
                     "rate_per_hour": daily[device].get(day, {}).get("rate_per_hour")}
                    for device in devices for day in dates]
    day_night = []
    for run in conn.execute("SELECT result_json FROM s06_analysis_run ORDER BY created_at DESC"):
        try:
            payload = json.loads(run["result_json"])
        except (TypeError, ValueError):
            continue
        for item in payload.get("day_night", {}).get("results", []):
            if item.get("device_id") in devices and start <= item.get("observed_date", "") <= end:
                pair = item.get("pair") or {}
                day_night.append({"device_id": item["device_id"],
                                  "observed_date": item["observed_date"],
                                  "status": item.get("status"),
                                  "night_rate": pair.get("night_rate_per_hour"),
                                  "day_rate": pair.get("day_rate_per_hour"),
                                  "difference": pair.get("difference")})
        break
    layers = [dict(r) for r in conn.execute(
        "SELECT device_id,observed_date,layer,kept_samples,candidate_events,signal_mean "
        "FROM s07_layer_stats WHERE device_id IN (%s) AND observed_date BETWEEN ? AND ? "
        "ORDER BY observed_date,device_id,layer" % ",".join("?" for _ in devices),
        (*devices, start, end))]
    weekly = {}
    monthly = {}
    for device, by_date in daily.items():
        for day, values in by_date.items():
            period = day[:7]
            key_month = (device, period)
            if values.get("rate_per_hour") is not None:
                monthly.setdefault(key_month, []).append(values["rate_per_hour"])
        for index, day in enumerate(dates):
            key_week = (device, f"W{index // 7 + 1}")
            value = by_date.get(day, {}).get("rate_per_hour")
            if value is not None:
                weekly.setdefault(key_week, []).append(value)
    return {
        "date_station": date_station,
        "day_night_station": day_night,
        "layer_station": layers,
        "weekly": [{"device_id": k[0], "period": k[1],
                    "mean_rate": statistics.fmean(v)} for k, v in sorted(weekly.items())],
        "monthly": [{"device_id": k[0], "period": k[1],
                     "mean_rate": statistics.fmean(v)} for k, v in sorted(monthly.items())],
        "note": "缺站/缺测/NA 不填 0；周为窗口内顺序分箱，不等同自然周",
    }


def _pair_distance(left: dict, right: dict) -> dict:
    """按当前两站坐标与坐标系口径重算站距，不复用过期缓存。"""
    audit_a, audit_b = left["coordinate_audit"], right["coordinate_audit"]
    if left.get("longitude_deg") is None or right.get("longitude_deg") is None \
            or audit_a.get("status") == "BLOCKED" or audit_b.get("status") == "BLOCKED":
        return {"status": "UNKNOWN", "distance_m": None,
                "reason": "缺坐标或坐标审计阻断，不计算站距"}
    crs_a = (left.get("crs") or UNDECLARED_CRS).upper()
    crs_b = (right.get("crs") or UNDECLARED_CRS).upper()
    if crs_a != UNDECLARED_CRS and crs_b != UNDECLARED_CRS and crs_a != crs_b:
        return {"status": "BLOCKED", "distance_m": None,
                "reason": "坐标系不同且未转换，拒绝混算站距"}
    undeclared = crs_a == UNDECLARED_CRS or crs_b == UNDECLARED_CRS
    return {"status": "PROVISIONAL" if undeclared else "OK",
            "distance_m": haversine_m(left["longitude_deg"], left["latitude_deg"],
                                      right["longitude_deg"], right["latitude_deg"]),
            "crs_pair": f"{crs_a} / {crs_b}",
            "note": ("未声明坐标系，按 WGS84 近似，仅作相对位置示意"
                     if undeclared else "同一声明坐标系内的球面距离近似")}


def _coverage_summary(station: dict) -> dict:
    coverage = station.get("coverage") or {}
    direction = coverage.get("directional_footprint") or {}
    return {
        "status": coverage.get("status", "UNKNOWN"),
        "cutoff_m": coverage.get("cutoff_m"),
        "coverage_radius_m": coverage.get("coverage_radius_m"),
        "half_angle_deg": coverage.get("half_angle_deg"),
        "sector_area_m2": coverage.get("sector_area_m2"),
        "retained_footprint_area_m2": coverage.get("retained_footprint_area_m2"),
        "parameter_version": coverage.get("parameter_version"),
        "analysis_cutoff_m": coverage.get("analysis_cutoff_m"),
        "directional_status": direction.get("status", "UNKNOWN"),
        "heading_deg": direction.get("heading_deg"),
        "heading_reference": direction.get("heading_reference"),
    }


def pairwise_analysis(conn: sqlite3.Connection, devices, start: str, end: str,
                      observed_date: str) -> dict:
    """当前选择的每一对设备：站距、理论覆盖、条件重叠与活动差异；缺测不填 0。"""
    selected = validate_devices(devices)
    map_data = map_payload(conn, observed_date, selected)
    stations = {station["device_id"]: station for station in map_data["stations"]}
    daily = daily_activity(conn, selected, start, end)
    pairs = []
    for device_a, device_b in itertools.combinations(selected, 2):
        left = stations.get(device_a, {"coordinate_audit": {"status": "BLOCKED"},
                                       "coverage": {"status": "UNKNOWN"}})
        right = stations.get(device_b, {"coordinate_audit": {"status": "BLOCKED"},
                                        "coverage": {"status": "UNKNOWN"}})
        distance = _pair_distance(left, right)
        coverage_a, coverage_b = _coverage_summary(left), _coverage_summary(right)
        overlap = ({"status": "UNKNOWN", "area_m2": None, "reason": distance["reason"]}
                   if distance["status"] not in ("OK", "PROVISIONAL")
                   else _conditional_overlap(left.get("coverage") or {},
                                             right.get("coverage") or {}, left, right))
        differences = []
        for day in sorted(set(daily[device_a]) | set(daily[device_b])):
            a_values = daily[device_a].get(day) or {}
            b_values = daily[device_b].get(day) or {}
            rate_a, rate_b = a_values.get("rate_per_hour"), b_values.get("rate_per_hour")
            differences.append({
                "observed_date": day,
                "rate_a": rate_a, "rate_b": rate_b,
                "difference_a_minus_b": (rate_a - rate_b
                                         if rate_a is not None and rate_b is not None else None),
                "status_a": a_values.get("status", "NA"), "status_b": b_values.get("status", "NA"),
                "coverage_a": a_values.get("coverage_ratio"),
                "coverage_b": b_values.get("coverage_ratio"),
            })
        valid = [row["difference_a_minus_b"] for row in differences
                 if row["difference_a_minus_b"] is not None]
        pairs.append({
            "device_a": device_a, "device_b": device_b, "distance": distance,
            "theoretical_coverage": {"device_a": coverage_a, "device_b": coverage_b},
            "conditional_overlap": overlap,
            "activity_difference": {
                "by_date": differences, "n_common_days": len(valid),
                "mean_difference_a_minus_b": statistics.fmean(valid) if valid else None,
                "status": "OK" if len(valid) >= 3 else "INSUFFICIENT_DATA",
                "note": "活动差异仅为同期描述；缺测日保留 NA 与覆盖率，不填 0",
            },
        })
    return {"pairs": pairs, "devices": list(selected), "observed_date": observed_date,
            "method_version": COMBINATION_METHOD_VERSION,
            "note": ("站距与覆盖按当前两站当日生效参数重算；条件重叠是几何示意，"
                     "不是实测鱼群位置、密度或站间连通性证据")}


def environment_joint(conn: sqlite3.Connection, devices, start: str, end: str) -> dict:
    results = []
    device_set = set(devices)
    for variable in ENV_VARIABLES:
        rows = [dict(r) for r in conn.execute(
            "SELECT o.*,s.kind AS source_kind FROM environment_observation o "
            "JOIN environment_source s ON s.source_id=o.source_id "
            "WHERE o.variable=? AND o.observed_at BETWEEN ? AND ?",
            (variable, start + "T00:00:00", end + "T23:59:59"))]
        if not rows:
            results.append({"variable": variable, "status": "BLOCKED",
                            "reason": "无数值观测（潮汐截图不估读，风向缺列）",
                            "station_comparison": {"status": "BLOCKED", "reason": "无环境观测"}})
            continue
        independent = [r for r in rows if r["quality_flag"] in ("OK", "MODEL_HISTORICAL")
                       and r["source_kind"] != "DERIVED"]
        if not independent:
            results.append({"variable": variable, "status": "BLOCKED",
                            "reason": "只有派生/预报数据，不作为独立环境证据",
                            "station_comparison": {"status": "BLOCKED", "reason": "无独立环境值"}})
            continue
        per_device = {}
        for row in independent:
            if row.get("device_id") in device_set:
                per_device.setdefault(row["device_id"], []).append(row["value_si"])
        if len(per_device) >= 2:
            comparison = {"status": "PROVISIONAL", "n_stations": len(per_device),
                          "station_means": {d: statistics.fmean(v) for d, v in per_device.items()},
                          "note": "逐站独立记录仍须核对时间重叠与有效观测时长"}
        else:
            comparison = {"status": "BLOCKED", "n_stations": len(per_device),
                          "reason": "环境值为共享网格/单点来源，未逐站独立布设；不能解释站间差异"}
        results.append({"variable": variable, "status": "PROVISIONAL",
                        "n_observations": len(independent), "station_comparison": comparison,
                        "reason": "环境值为共享来源，只做探索性对照，不解释因果"})
    return {"results": results,
            "note": "空间环境响应须逐站独立观测；共享网格不能证明站间环境差异"}


def dynamic_frames(conn: sqlite3.Connection, devices, start: str, end: str,
                   *, step_hours: int = 1, run_id: str | None = None) -> dict:
    """离散时间帧：每帧只放该时刻已实测量的站位值，不插值、不连轨迹。"""
    devices = validate_devices(devices)
    frames = []
    current = datetime.strptime(start, "%Y-%m-%d")
    last = datetime.strptime(end, "%Y-%m-%d")
    acoustic = {}
    for row in conn.execute(
            "SELECT device_id,slot_start,candidate_events,coverage_ratio FROM s06_time_grid "
            "WHERE observed_date BETWEEN ? AND ?", (start, end)):
        if row["device_id"] not in devices or row["coverage_ratio"] is None \
                or row["coverage_ratio"] < MIN_COVERAGE_RATIO:
            continue
        acoustic[(row["device_id"], row["slot_start"][:13])] = \
            acoustic.get((row["device_id"], row["slot_start"][:13]), 0) + row["candidate_events"]
    env = {}
    for row in conn.execute(
            "SELECT variable,observed_at,value_si,quality_flag,source_id FROM environment_observation "
            "WHERE variable IN (%s) AND quality_flag IN ('OK','MODEL_HISTORICAL')"
            % ",".join("?" for _ in ENV_VARIABLES), ENV_VARIABLES):
        env[(row["variable"], row["observed_at"][:13])] = {
            "value": row["value_si"], "quality_flag": row["quality_flag"],
            "source_id": row["source_id"]}
    while current <= last:
        for hour in range(0, 24, max(1, step_hours)):
            stamp = f"{current.date().isoformat()}T{hour:02d}"
            values = [{"device_id": device,
                       "candidate_events": acoustic.get((device, stamp)),
                       "status": "OK" if (device, stamp) in acoustic else "NA",
                       "environment": {variable: env.get((variable, stamp))
                                       for variable in ENV_VARIABLES}}
                      for device in devices]
            frames.append({"timestamp_local": stamp, "timezone": LOCAL_TIMEZONE, "values": values})
        current = datetime.fromordinal(current.toordinal() + 1)
    return {"frames": frames, "step_hours": step_hours, "devices": list(devices),
            "selected_devices": list(devices), "run_id": run_id,
            "variables": list(ENV_VARIABLES),
            "legend": {"activity_scale": "FIXED_PER_VIEW", "missing": "NA"},
            "note": "离散站位活动与环境同屏；环境按本地 observed_at 对齐，缺测帧标 NA 而非 0；无鱼群轨迹、无连续密度插值"}


def record_combination_run(conn: sqlite3.Connection, devices, start: str, end: str,
                           observed_date: str, *, dataset_id: str | None = None,
                           comparison_modes=None, actor: str = "S08", query_context=None,
                           parameter_versions=None, grouping_mode: str = "default",
                           group_members=None, aggregation_mode: str = "pooled",
                           baseline_id: str | None = None, color_scale_id: str | None = None,
                           metric_id: str = qc.DEFAULT_METRIC_ID,
                           analysis_plan_version: str = qc.DEFAULT_ANALYSIS_PLAN_VERSION,
                           mask_version: str = qc.DEFAULT_MASK_VERSION) -> dict:
    """保存组合 run 与 V4.1 查询快照；同一查询的指纹防止新旧 run 混显。"""
    selected = validate_devices(devices)
    stamp = datetime.now(dt_timezone.utc).strftime("%Y%m%dT%H%M%S")
    run_id = f"S08C-{stamp}-{uuid.uuid4().hex[:8]}"
    snapshots = dict(parameter_versions or {})
    if not snapshots:
        snapshots = {device: parameter_snapshot(conn, device, observed_date)
                     for device in selected}
    modes = list(comparison_modes or COMPARISON_MODES)
    dataset = dataset_id or DEFAULT_DATASET_ID
    context = query_context or qc.build_query_context(
        selected_devices=selected, start_date=start, end_date=end,
        dataset_id=dataset, comparison_mode=modes[0] if modes else "independent",
        aggregation_mode=aggregation_mode, grouping_mode=grouping_mode,
        baseline_id=baseline_id, metric_id=metric_id,
        analysis_plan_version=analysis_plan_version, parameter_versions=snapshots,
        mask_version=mask_version, color_scale_id=color_scale_id)
    context.run_id = run_id
    context.parameter_versions = snapshots
    context.dataset_id = dataset
    context.aggregation_mode = aggregation_mode
    context.grouping_mode = grouping_mode
    context.comparison_mode = modes[0] if modes else "independent"
    context.baseline_id = baseline_id
    context.metric_id = metric_id
    context.analysis_plan_version = analysis_plan_version
    context.mask_version = mask_version
    if color_scale_id:
        context.color_scale_id = color_scale_id
    row = {
        "run_id": run_id,
        "device_list": ",".join(selected),
        "devices_json": json.dumps(selected, ensure_ascii=False),
        "n_devices": len(selected),
        "start_date": start, "end_date": end, "observed_date": observed_date,
        "parameter_versions_json": json.dumps(snapshots, ensure_ascii=False, default=str),
        "dataset_id": dataset,
        "comparison_modes_json": json.dumps(modes, ensure_ascii=False),
        "method_version": COMBINATION_METHOD_VERSION,
        "created_at": _now(), "actor": actor,
        "query_context_json": context.to_json(),
        "query_fingerprint": context.query_fingerprint(),
        "grouping_mode": grouping_mode,
        "group_members_json": json.dumps(group_members or [], ensure_ascii=False, default=str),
        "aggregation_mode": aggregation_mode,
        "baseline_id": baseline_id,
        "color_scale_id": context.color_scale_id,
        "metric_id": metric_id,
        "analysis_plan_version": analysis_plan_version,
        "mask_version": mask_version,
        "result_json": None,
    }
    columns = ",".join(row.keys())
    placeholders = ",".join("?" for _ in row)
    conn.execute(f"INSERT INTO spatial_combination_runs ({columns}) VALUES ({placeholders})",
                 tuple(row.values()))
    conn.commit()
    row["parameter_versions"] = snapshots
    row["devices"] = list(selected)
    row["query_context"] = context.to_dict()
    return row


def store_combination_result(conn: sqlite3.Connection, run_id: str, result: dict) -> None:
    """把同源结果写回 run，API 与页面只按 run_id 读取，避免新旧结果混显。"""
    conn.execute(
        "UPDATE spatial_combination_runs SET result_json=? WHERE run_id=?",
        (json.dumps(result, ensure_ascii=False, default=str), run_id))
    conn.commit()


def _activity_rows(activity: dict, devices, dates) -> list[dict]:
    rows = []
    for device in devices:
        for day in dates:
            value = (activity.get(device) or {}).get(day)
            if not value:
                continue
            rows.append({"date": day, "device_id": device,
                         "numerator": value.get("candidate_events"),
                         "denominator": value.get("valid_hours"),
                         "coverage": value.get("coverage_ratio"),
                         "status": value.get("status")})
    return rows


def _baseline_members(activity: dict, devices, baseline_id: str | None, end: str) -> tuple[list[str], str]:
    valid_dates = sorted({day for device in devices for day, value
                          in (activity.get(device) or {}).items()
                          if value.get("rate_per_hour") is not None and day <= end})
    baseline_id = baseline_id or "FIRST_VALID_DAY"
    if baseline_id.startswith("PREV_"):
        try:
            count = int(baseline_id.split("_", 1)[1])
        except ValueError:
            count = 1
        return valid_dates[-max(1, count):], f"前 {max(1, count)} 个有效日"
    if baseline_id.startswith("DATE:"):
        day = baseline_id.split(":", 1)[1]
        return ([day] if day in valid_dates else []), f"指定日期 {day}"
    return valid_dates[:1], "首个有效日"


def _build_v41_payload(context: qc.QueryContext, activity: dict, statistics_payload: dict,
                       *, metric_id: str, grouping_mode: str, custom_step_days: int,
                       page: int, baseline_id: str | None, color_scale_id: str | None,
                       start: str, end: str, low_coverage_threshold: float) -> dict:
    selected = list(context.selected_devices)
    contract = v41.metric_contract(metric_id)
    date_set = context.date_set or grouping.inclusive_dates(start, end)
    grouping_payload = grouping.build_groups(
        start, end, grouping_mode, date_set,
        custom_step_days=custom_step_days, page=page)
    all_rows = _activity_rows(activity, selected, date_set)
    metric_supported = metric_id == "CANDIDATE_EVENT_RATE"
    usable_rows = all_rows if metric_supported else []
    rates = [value.get("rate_per_hour") for device in selected
             for value in (activity.get(device) or {}).values()
             if value.get("rate_per_hour") is not None]
    color_scale = v41.build_color_scale(metric_id, rates, config={
        "color_scale_id": color_scale_id} if color_scale_id else None)

    overview_cells = []
    trend_dates = sorted(set(date_set))
    for device in selected:
        for day in trend_dates:
            value = (activity.get(device) or {}).get(day)
            overview_cells.append({
                "device_id": device, "observed_date": day,
                "numerator": (value or {}).get("candidate_events"),
                "denominator": (value or {}).get("valid_hours"),
                "coverage_ratio": (value or {}).get("coverage_ratio"),
                "status": (value or {}).get("status"),
                "value": (value or {}).get("rate_per_hour"),
                "cell_status": v41.classify_cell(
                    selected=True,
                    numerator=(value or {}).get("candidate_events"),
                    denominator=(value or {}).get("valid_hours"),
                    coverage=(value or {}).get("coverage_ratio"),
                    status=(value or {}).get("status"),
                    low_coverage_threshold=low_coverage_threshold),
            })
    trend = [{"date": day,
              "values": {device: (activity.get(device) or {}).get(day, {}).get("rate_per_hour")
                         for device in selected}}
             for day in trend_dates]

    group_summaries = []
    for group in grouping_payload["groups"]:
        rows = [row for row in usable_rows if row["date"] in group["dates"]]
        per_device = {}
        for device in selected:
            per_device[device] = v41.aggregate_observations(
                [row for row in rows if row["device_id"] == device],
                context.aggregation_mode, metric_id)
        common_dates = sorted({row["date"] for row in rows}
                              - {row["date"] for row in rows
                                 if row["device_id"] not in selected})
        valid_by_device = [{row["date"] for row in rows if row["device_id"] == device
                            and row["numerator"] is not None}
                           for device in selected]
        common = sorted(set.intersection(*valid_by_device)) if valid_by_device else []
        group_summaries.append({**group,
                                "per_device": per_device,
                                "common_valid_dates": common,
                                "n_common_valid_days": len(common),
                                "n_present_dates": len(common_dates)})

    members, member_note = _baseline_members(activity, selected, baseline_id, end)
    baseline_rows = [row for row in usable_rows if row["date"] in members]
    current_agg = v41.aggregate_observations(usable_rows, context.aggregation_mode, metric_id)
    baseline_agg = v41.aggregate_observations(baseline_rows, context.aggregation_mode, metric_id)
    comparison = v41.compare_with_baseline(
        current_agg["selected_value"], baseline_agg["selected_value"],
        metric_id=metric_id, baseline_id=baseline_id, baseline_members=members,
        cutoff_date=end, baseline_version=member_note)
    if not metric_supported:
        comparison = {"status": "BLOCKED_DATA_SOURCE",
                      "reason": "当前 S03/S08 日值只提供候选事件率；出现比例需帧级候选标记",
                      "baseline_members": members}

    return {
        "metric": {**contract, "data_status": "OK" if metric_supported else "BLOCKED_DATA_SOURCE"},
        "query_context": context.to_dict(),
        "color_scale": color_scale,
        "overview": {"cells": overview_cells, "trend": trend,
                     "n_cells": len(overview_cells),
                     "note": "设备×日期完整总览；未选择、缺测、低覆盖、有效零值分状态显示"},
        "spatial_groups": {**grouping_payload, "group_summaries": group_summaries},
        "compare": comparison,
        "patterns": v41.pattern_cards(
            DEVICE_IDS, selected, run_id=context.run_id,
            statistics=statistics_payload.get("device_differences", {})),
        "pattern_evidence": {**v41.evidence_summary({}),
                             "reason": "当前组合分析不自动判定规律证据；需 S07 冻结规则与独立验证"},
        "status": {"run_state": "READY", "default_map_limit": grouping.MAX_DEFAULT_GROUPS,
                   "metric_data_status": "OK" if metric_supported else "BLOCKED_DATA_SOURCE"},
    }


def analyze_combination(conn: sqlite3.Connection, devices, start: str, end: str,
                        observed_date: str, *, step_hours: int = 1,
                        dataset_id: str | None = None, actor: str = "S08",
                        query_context=None, metric_id: str = qc.DEFAULT_METRIC_ID,
                        grouping_mode: str = "default", aggregation_mode: str = "pooled",
                        baseline_id: str | None = None, color_scale_id: str | None = None,
                        custom_step_days: int = 7, page: int = 1,
                        date_set=None, daily_windows=None, environment_filters=None,
                        depth_mode: str = "ALL", layer: str | None = None,
                        comparison_mode: str | None = None,
                        analysis_plan_version: str = qc.DEFAULT_ANALYSIS_PLAN_VERSION,
                        mask_version: str = qc.DEFAULT_MASK_VERSION,
                        low_coverage_threshold: float = MIN_COVERAGE_RATIO) -> dict:
    """任意 1—5 台设备 + V4.1 同查询契约；所有视图共用同一 run 与查询快照。"""
    selected = validate_devices(devices)
    snapshots = {device: parameter_snapshot(conn, device, observed_date)
                 for device in selected}
    dataset = dataset_id or DEFAULT_DATASET_ID
    modes = ([comparison_mode] + [mode for mode in COMPARISON_MODES if mode != comparison_mode]
             if comparison_mode else list(COMPARISON_MODES))
    context = query_context or qc.build_query_context(
        selected_devices=selected, start_date=start, end_date=end,
        date_set=date_set, daily_windows=daily_windows,
        comparison_mode=modes[0], baseline_id=baseline_id,
        aggregation_mode=aggregation_mode, grouping_mode=grouping_mode,
        dataset_id=dataset, metric_id=metric_id,
        analysis_plan_version=analysis_plan_version, parameter_versions=snapshots,
        mask_version=mask_version, color_scale_id=color_scale_id,
        depth_mode=depth_mode, layer=layer, environment_filters=environment_filters)
    run = record_combination_run(
        conn, selected, start, end, observed_date, dataset_id=dataset,
        comparison_modes=modes, actor=actor, query_context=context,
        parameter_versions=snapshots, grouping_mode=grouping_mode,
        group_members=[], aggregation_mode=aggregation_mode, baseline_id=baseline_id,
        color_scale_id=color_scale_id, metric_id=metric_id,
        analysis_plan_version=analysis_plan_version, mask_version=mask_version)
    activity = daily_activity(conn, selected, start, end)
    statistics_payload = spatial_statistics(conn, selected, start, end)
    v41_payload = _build_v41_payload(
        context, activity, statistics_payload, metric_id=metric_id,
        grouping_mode=grouping_mode, custom_step_days=custom_step_days, page=page,
        baseline_id=baseline_id, color_scale_id=color_scale_id, start=start, end=end,
        low_coverage_threshold=low_coverage_threshold)
    context.color_scale_id = v41_payload["color_scale"]["color_scale_id"]
    run["color_scale_id"] = context.color_scale_id
    group_members = [{key: group[key] for key in
                      ("index", "date_start", "date_end", "planned_days", "selected_days", "dates")}
                     for group in v41_payload["spatial_groups"]["groups"]]
    run["group_members"] = group_members
    conn.execute("UPDATE spatial_combination_runs SET color_scale_id=?, query_context_json=?, "
                 "group_members_json=? WHERE run_id=?",
                 (context.color_scale_id, context.to_json(),
                  json.dumps(group_members, ensure_ascii=False, default=str), run["run_id"]))
    dynamics = dynamic_frames(conn, selected, start, end,
                              step_hours=step_hours, run_id=run["run_id"])
    result = {
        "run": run, "run_id": run["run_id"], "devices": list(selected),
        "selected_devices": list(selected),
        "query_context": context.to_dict(),
        "map": map_payload(conn, observed_date, selected),
        "activity": activity,
        "time_curves": time_curves(conn, selected, start, end),
        "statistics": statistics_payload,
        "common_valid_periods": statistics_payload["common_valid_periods"],
        "pairwise": pairwise_analysis(conn, selected, start, end, observed_date),
        "heatmaps": heatmaps(conn, selected, start, end),
        "environment": environment_joint(conn, selected, start, end),
        "dynamics": dynamics,
        "v41": v41_payload,
        "overview": v41_payload["overview"],
        "spatial_groups": v41_payload["spatial_groups"],
        "patterns": v41_payload["patterns"],
        "pattern_evidence": v41_payload["pattern_evidence"],
        "compare": v41_payload["compare"],
        "color_scale": v41_payload["color_scale"],
        "start_date": start, "end_date": end, "observed_date": observed_date,
        "dataset_id": run["dataset_id"],
        "method_version": COMBINATION_METHOD_VERSION,
    }
    store_combination_result(conn, run["run_id"], result)
    return result


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ("" if row.get(key) is None else row.get(key))
                             for key in fieldnames})


def write_outputs(result: dict, output_dir: Path) -> list[str]:
    """把 S08 结果归档为 JSON/CSV，供网页与 CLI 共用同一数值来源。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    summary = output_dir / "spatial_summary.json"
    summary.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                       encoding="utf-8")
    written.append(summary.name)
    map_data = result.get("map", {})
    _write_csv(output_dir / "station_locations.csv",
               ["station_id", "device_id", "longitude_deg", "latitude_deg", "crs",
                "gps_accuracy_m", "water_depth_m", "heading_deg", "source", "measured_at",
                "effective_from", "audit_status", "coverage_status", "activity_rate_per_hour"],
               [{**station, "audit_status": station.get("coordinate_audit", {}).get("status"),
                 "coverage_status": station.get("coverage", {}).get("status"),
                 "activity_rate_per_hour": (station.get("activity") or {}).get("rate_per_hour")}
                for station in map_data.get("stations", [])])
    written.append("station_locations.csv")
    _write_csv(output_dir / "station_distances.csv",
               ["station_a", "station_b", "device_a", "device_b", "distance_m", "method",
                "crs_pair", "status", "note"], map_data.get("distances", []))
    written.append("station_distances.csv")
    activity = result.get("activity", {})
    _write_csv(output_dir / "spatial_activity.csv",
               ["observed_date", "device_id", "status", "candidate_events", "valid_hours",
                "coverage_ratio", "rate_per_hour"],
               [{"observed_date": day, "device_id": device, **values}
                for device, by_date in activity.items()
                for day, values in by_date.items()])
    written.append("spatial_activity.csv")
    run = result.get("run")
    if run:
        _write_csv(output_dir / "combination_run.csv",
                   ["run_id", "device_list", "n_devices", "start_date", "end_date",
                    "observed_date", "parameter_versions_json", "dataset_id",
                    "comparison_modes_json", "method_version", "created_at", "actor",
                    "query_fingerprint", "grouping_mode", "group_members_json",
                    "aggregation_mode", "baseline_id", "color_scale_id", "metric_id",
                    "analysis_plan_version", "mask_version", "query_context_json"],
                   [run])
        written.append("combination_run.csv")
    curves = result.get("time_curves", {})
    if curves:
        _write_csv(output_dir / "time_curves.csv",
                   ["device_id", "timestamp_local", "candidate_events", "coverage_ratio",
                    "source_slots", "status"],
                   [{"device_id": device, **point} for device, points in curves.items()
                    for point in points])
        written.append("time_curves.csv")
    pairwise = result.get("pairwise", {}).get("pairs", [])
    if pairwise:
        _write_csv(output_dir / "pairwise_analysis.csv",
                   ["device_a", "device_b", "distance_status", "distance_m",
                    "overlap_status", "overlap_area_m2", "n_common_days",
                    "mean_difference_a_minus_b", "status"],
                   [{"device_a": pair["device_a"], "device_b": pair["device_b"],
                     "distance_status": pair["distance"]["status"],
                     "distance_m": pair["distance"]["distance_m"],
                     "overlap_status": pair["conditional_overlap"]["status"],
                     "overlap_area_m2": pair["conditional_overlap"]["area_m2"],
                     "n_common_days": pair["activity_difference"]["n_common_days"],
                     "mean_difference_a_minus_b":
                         pair["activity_difference"]["mean_difference_a_minus_b"],
                     "status": pair["activity_difference"]["status"]}
                    for pair in pairwise])
        written.append("pairwise_analysis.csv")
    v41_data = result.get("v41", {})
    if v41_data:
        (output_dir / "query_context.json").write_text(
            json.dumps(v41_data.get("query_context", {}), ensure_ascii=False, indent=2),
            encoding="utf-8")
        written.append("query_context.json")
        (output_dir / "color_scale.json").write_text(
            json.dumps(v41_data.get("color_scale", {}), ensure_ascii=False, indent=2),
            encoding="utf-8")
        written.append("color_scale.json")
        _write_csv(output_dir / "v41_overview.csv",
                   ["device_id", "observed_date", "numerator", "denominator",
                    "coverage_ratio", "status", "value", "cell_status"],
                   v41_data.get("overview", {}).get("cells", []))
        written.append("v41_overview.csv")
        _write_csv(output_dir / "spatial_groups.csv",
                   ["index", "date_start", "date_end", "planned_days", "selected_days",
                    "n_common_valid_days", "grouping_mode"],
                   [{**{key: group.get(key) for key in
                        ("index", "date_start", "date_end", "planned_days",
                         "selected_days", "n_common_valid_days")},
                     "grouping_mode": v41_data.get("spatial_groups", {}).get("grouping_mode")}
                    for group in v41_data.get("spatial_groups", {}).get("group_summaries", [])])
        written.append("spatial_groups.csv")
        _write_csv(output_dir / "pattern_cards.csv",
                   ["device_id", "status", "label", "l_level", "reason"],
                   v41_data.get("patterns", []))
        written.append("pattern_cards.csv")
    frames = result.get("dynamics", {}).get("frames", [])
    frame_rows = []
    for frame in frames:
        for value in frame["values"]:
            frame_rows.append({"timestamp_local": frame["timestamp_local"],
                               "timezone": frame["timezone"], "device_id": value["device_id"],
                               "activity_status": value["status"],
                               "candidate_events": value["candidate_events"],
                               **{f"{variable}_value": (value["environment"].get(variable) or {}).get("value")
                                  for variable in ENV_VARIABLES}})
    _write_csv(output_dir / "dynamic_frames.csv",
               ["timestamp_local", "timezone", "device_id", "activity_status", "candidate_events"]
               + [f"{variable}_value" for variable in ENV_VARIABLES], frame_rows)
    written.append("dynamic_frames.csv")
    return written
