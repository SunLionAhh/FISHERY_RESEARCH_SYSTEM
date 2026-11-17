# -*- coding: utf-8 -*-
"""S08 五站 GPS 空间与动态分析：缺站缺测 NA，不虚构轨迹或密度插值。"""
from __future__ import annotations

import csv
import json
from collections import Counter
import math
import sqlite3
import statistics
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from . import beam_geometry as geo
from . import comparison as cmp
from . import daily_stats as ds
from . import s07_patterns as patterns

METHOD_VERSION = "S08_SPATIAL_V1"
DEVICE_IDS = ("2000", "2001", "2002", "2003", "2005")
UNDECLARED_CRS = "UNDECLARED"
KNOWN_CRS = {"WGS84", "EPSG:4326", "CGCS2000", "EPSG:4490"}
MIN_COVERAGE_RATIO = 0.5
LOCAL_TIMEZONE = "Asia/Shanghai"
ENV_VARIABLES = ("WATER_TEMP", "TIDE_HEIGHT", "WIND_SPEED", "WIND_DIRECTION")


class SpatialValidationError(ValueError):
    pass


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


def map_payload(conn: sqlite3.Connection, observed_date: str | None = None) -> dict:
    points = locations(conn, observed_date)
    activity = (daily_activity(conn, [p["device_id"] for p in points], observed_date, observed_date)
                if observed_date else {})
    stations = []
    for point in points:
        label = point["station_id"] or f"{point['device_id']}（P 码未提供）"
        audit = coordinate_audit(point, points)
        coverage = {"status": "UNKNOWN", "reason": "缺参数、缺坐标或坐标审计阻断"}
        if audit["range_ok"] and not audit["suspected_latlon_swap"]:
            params_date = observed_date or point["effective_from"]
            try:
                params = geo.effective_params(conn, point["device_id"], params_date)
                geometry = geo.beam_geometry(
                    height_m=float(params["vertical_bottom_clearance_m"]),
                    tilt_deg=float(params["downward_tilt_deg"]),
                    beam_value_deg=float(params["beam_angle_value_deg"]),
                    beam_kind=params["beam_angle_kind"],
                    cutoff_m=float(params["analysis_cutoff_slant_m"]))
                coverage = {"status": "CIRCLE_ONLY",
                            "cutoff_m": geometry["cutoff_locked_m"],
                            "center_axis_bottom_m": geometry["center_axis_bottom_m"],
                            "directional_footprint": "UNKNOWN" if point["heading_deg"] is None
                                                     else "HEADING_DECLARED_NO_MEASURED_FOOTPRINT",
                            "parameter_effective_from": params["effective_from"],
                            "assumption": "水平底面 + 人工斜距上限；圆为理论覆盖示意，不是鱼位置/密度"}
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
        "SELECT * FROM station_distance ORDER BY station_a,station_b")]
    return {"stations": stations, "bounds": bounds, "distances": distances,
            "unknown_devices": [d for d in DEVICE_IDS if d not in {s["device_id"] for s in stations}],
            "map_mode": "OFFLINE_LOCAL_COORDINATE_SKETCH",
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


def _safe_pairs(left: dict, right: dict) -> list[tuple[float, float]]:
    keys = sorted(set(left) & set(right))
    return [(left[k]["rate_per_hour"], right[k]["rate_per_hour"]) for k in keys
            if left[k].get("rate_per_hour") is not None and right[k].get("rate_per_hour") is not None]


def spatial_statistics(conn: sqlite3.Connection, devices, start: str, end: str) -> dict:
    devices = tuple(devices)
    daily = daily_activity(conn, devices, start, end)
    pairs = []
    for i, a in enumerate(devices):
        for b in devices[i + 1:]:
            values = _safe_pairs(daily[a], daily[b])
            r = patterns._pearson([x for x, _ in values], [y for _, y in values])
            lagged = [(values[k][0], values[k + 1][1]) for k in range(len(values) - 1)]
            lag_r = patterns._pearson([x for x, _ in lagged], [y for _, y in lagged])
            pairs.append({"device_a": a, "device_b": b, "n_common": len(values),
                          "pearson_r": r, "lag1_a_lead_b_r": lag_r,
                          "status": "OK" if len(values) >= 3 and r is not None else "INSUFFICIENT_DATA",
                          "note": "同期相关与 a 领先 1 日的相关都只称关联/时差；未校正时间自相关，不能证明迁移"})
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
    return {"pairs": pairs, "device_differences": differences,
            "stability": {"status": stability_status, "windows": len(weekly_leaders),
                          "top_station_share": top_share,
                          "note": "格局稳定度仅按窗口内首位站重复出现比例；未独立验证，不升级为长期结论"},
            "long_term": long_term,
            "method_note": "Pearson/均值仅作探索；时间自相关、有效观测时长与伪重复未完全校正，不给因果或显著性结论"}


def heatmaps(conn: sqlite3.Connection, devices, start: str, end: str) -> dict:
    daily = daily_activity(conn, devices, start, end)
    dates = sorted({d for device in daily.values() for d in device})
    date_station = [{"observed_date": day, "device_id": device,
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
                   *, step_hours: int = 1) -> dict:
    """离散时间帧：每帧只放该时刻已实测量的站位值，不插值、不连轨迹。"""
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
            "variables": list(ENV_VARIABLES),
            "legend": {"activity_scale": "FIXED_PER_VIEW", "missing": "NA"},
            "note": "离散站位活动与环境同屏；环境按本地 observed_at 对齐，缺测帧标 NA 而非 0；无鱼群轨迹、无连续密度插值"}


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
