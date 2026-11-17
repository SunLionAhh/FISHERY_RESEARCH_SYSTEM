# -*- coding: utf-8 -*-
"""S07 长期规律与证据等级：等级按证据判定，不按天数自动升级。"""
from __future__ import annotations

import json
import math
import sqlite3
import statistics
from datetime import datetime, timezone as dt_timezone

from . import comparison as cmp
from . import daily_stats as ds

METHOD_VERSION = "S07_PATTERN_V1"
LEVELS = ("L0", "L1", "L2", "L3")


def _now() -> str:
    return datetime.now(dt_timezone.utc).isoformat(timespec="seconds")


def _pearson(xs, ys):
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs)
    dy = sum((y - my) ** 2 for y in ys)
    return num / math.sqrt(dx * dy) if dx > 0 and dy > 0 else None


def _hourly_profiles(conn, devices, start, end):
    rows = conn.execute(
        "SELECT device_id,observed_date,hour,candidate_events,low_coverage "
        "FROM (SELECT device_id,observed_date,CAST(substr(slot_start,12,2) AS INTEGER) hour,"
        "SUM(candidate_events) candidate_events,"
        "MAX(CASE WHEN coverage_ratio<0.5 THEN 1 ELSE 0 END) low_coverage "
        "FROM s06_time_grid GROUP BY device_id,observed_date,hour) "
        "WHERE observed_date BETWEEN ? AND ?", (start, end)).fetchall()
    profiles = {}
    for row in rows:
        if row["device_id"] not in devices or row["low_coverage"]:
            continue
        profiles.setdefault((row["device_id"], row["observed_date"]), {})[row["hour"]] = row["candidate_events"]
    return profiles


def analyze(conn: sqlite3.Connection, devices, start: str, end: str, *,
            window_days: int | None = None, dataset_id: str | None = None) -> dict:
    devices = tuple(devices)
    rows = [r for r in ds.all_latest_stats(conn)
            if r["device_id"] in devices and start <= r["observed_date"] <= end
            and r["status"] not in cmp.BASELINE_INVALID_STATUSES]
    by_device = {}
    for row in rows:
        by_device.setdefault(row["device_id"], []).append(row)
    for values in by_device.values():
        values.sort(key=lambda r: r["observed_date"])
    n_days = len({r["observed_date"] for r in rows})
    rates = [r["candidate_events"] / (r["valid_observation_duration_s"] / 3600)
             for r in rows if r["valid_observation_duration_s"]]
    profiles = _hourly_profiles(conn, devices, start, end)
    peak_hours = {}
    for key, values in profiles.items():
        if values:
            peak_hours[key] = max(values, key=values.get)
    peak_by_device = {}
    for device_id in devices:
        hours = [hour for (dev, _), hour in peak_hours.items() if dev == device_id]
        if hours:
            mode = statistics.mode(hours)
            peak_by_device[device_id] = {
                "modal_peak_hour": mode, "n_days": len(hours),
                "stability": sum(h == mode for h in hours) / len(hours)}
    similarities = []
    grouped = {}
    for (device_id, _), values in profiles.items():
        grouped.setdefault(device_id, []).append([values.get(h, 0) for h in range(24)])
    for series in grouped.values():
        for i in range(len(series)):
            for j in range(i + 1, len(series)):
                value = _pearson(series[i], series[j])
                if value is not None:
                    similarities.append(value)
    day_night_signs = []
    for run in conn.execute(
            "SELECT result_json FROM s06_analysis_run ORDER BY created_at DESC"):
        try:
            payload = json.loads(run["result_json"])
        except (TypeError, ValueError):
            continue
        for item in payload.get("day_night", {}).get("results", []):
            if item.get("device_id") in devices and start <= item.get("observed_date", "") <= end:
                diff = (item.get("pair") or {}).get("difference")
                if diff is not None:
                    day_night_signs.append(1 if diff >= 0 else -1)
        break
    dn_consistency = (sum(s == day_night_signs[0] for s in day_night_signs) / len(day_night_signs)
                      if day_night_signs else None)
    trend = None
    if len(rates) >= 3:
        xs = list(range(len(rates)))
        slope_r = _pearson(xs, rates)
        trend = {"slope_per_day": (rates[-1] - rates[0]) / max(len(rates) - 1, 1),
                 "rank_correlation": slope_r,
                 "direction": ("UP" if slope_r > 0.2 else
                               ("DOWN" if slope_r < -0.2 else "FLAT")) if slope_r is not None else "NA"}
    mean_similarity = statistics.fmean(similarities) if similarities else None
    stability_days = [v["stability"] for v in peak_by_device.values() if v["n_days"] >= 3]
    max_stability = max(stability_days) if stability_days else None
    supporting, contradicting, reasons = [], [], []
    if n_days >= 3:
        supporting.append(f"窗口内 {n_days} 个有效观测日")
    else:
        contradicting.append(f"仅 {n_days} 个有效观测日（需≥3）")
    if max_stability is not None and max_stability >= 0.6:
        supporting.append(f"小时峰值稳定度 {max_stability:.2f}")
    elif max_stability is not None:
        contradicting.append(f"小时峰值稳定度仅 {max_stability:.2f}")
    if mean_similarity is not None and mean_similarity >= 0.6:
        supporting.append(f"日间曲线平均相关 {mean_similarity:.2f}")
    elif mean_similarity is not None:
        contradicting.append(f"日间曲线平均相关仅 {mean_similarity:.2f}")
    if dn_consistency is not None and dn_consistency >= 0.7:
        supporting.append(f"昼夜方向一致度 {dn_consistency:.2f}")
    elif dn_consistency is not None:
        contradicting.append(f"昼夜方向一致度仅 {dn_consistency:.2f}")
    if n_days < 3:
        level = "L0"
    elif n_days >= 7 and max_stability and max_stability >= 0.6 and \
            mean_similarity and mean_similarity >= 0.6 and \
            dn_consistency is not None and dn_consistency >= 0.7:
        level = "L2"
    else:
        level = "L1"
    if level == "L2":
        frozen = conn.execute(
            "SELECT 1 FROM datasets WHERE dataset_id=? AND status='FROZEN'",
            (dataset_id or "",)).fetchone()
        independent = len(devices) >= 2 and frozen is not None
        if independent:
            level = "L3"
            supporting.append("冻结数据集 + 多设备独立交叉验证")
        else:
            reasons.append("缺冻结数据集或多设备独立验证，停在 L2，不自动升 L3")
    else:
        reasons.append("等级由证据判定，天数本身不能升级")
    return {
        "analysis_id": "PAT-" + datetime.now(dt_timezone.utc).strftime("%Y%m%d%H%M%S"),
        "method_version": METHOD_VERSION, "devices": list(devices),
        "window": {"start": start, "end": end, "window_days": window_days,
                   "n_effective_days": n_days},
        "dataset_id": dataset_id,
        "metrics": {"daily_rates": rates, "mean_daily_rate": statistics.fmean(rates) if rates else None,
                    "day_to_day_cv": (statistics.pstdev(rates) / statistics.fmean(rates)
                                      if rates and statistics.fmean(rates) else None),
                    "peak_hour_stability": peak_by_device,
                    "mean_curve_similarity": mean_similarity,
                    "day_night_consistency": dn_consistency, "trend": trend},
        "evidence_level": level, "supporting": supporting,
        "contradicting": contradicting, "level_reasons": reasons,
    }


def save_pattern(conn: sqlite3.Connection, result: dict, *, pattern_key: str | None = None,
                 supersedes_id: int | None = None, actor: str = "S07") -> int:
    key = pattern_key or f"DIURNAL_{'_'.join(result['devices'])}"
    version = conn.execute(
        "SELECT COALESCE(MAX(version),0)+1 v FROM s07_pattern_versions WHERE pattern_key=?",
        (key,)).fetchone()["v"]
    cursor = conn.execute(
        "INSERT INTO s07_pattern_versions (pattern_key,version,dataset_id,devices_json,"
        "window_json,evidence_level,status,supporting_json,contradicting_json,metrics_json,"
        "note,supersedes_id,created_at,created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (key, version, result.get("dataset_id"),
         json.dumps(result["devices"], ensure_ascii=False),
         json.dumps(result["window"], ensure_ascii=False), result["evidence_level"], "ACTIVE",
         json.dumps(result["supporting"], ensure_ascii=False),
         json.dumps(result["contradicting"], ensure_ascii=False),
         json.dumps(result["metrics"], ensure_ascii=False, default=str),
         "；".join(result.get("level_reasons", [])), supersedes_id, _now(), actor))
    conn.commit()
    return int(cursor.lastrowid)


def reevaluate(conn: sqlite3.Connection, pattern_key: str, *, devices, start, end,
               dataset_id=None, actor="S07") -> dict:
    """新数据到达：另存新版本并引用旧版本，绝不静默改旧报告。"""
    previous = conn.execute(
        "SELECT pattern_id,version FROM s07_pattern_versions WHERE pattern_key=? "
        "ORDER BY version DESC LIMIT 1", (pattern_key,)).fetchone()
    result = analyze(conn, devices, start, end, dataset_id=dataset_id)
    result["supersedes_id"] = previous["pattern_id"] if previous else None
    result["previous_version"] = previous["version"] if previous else None
    result["pattern_id"] = save_pattern(conn, result, pattern_key=pattern_key,
                                        supersedes_id=previous["pattern_id"] if previous else None,
                                        actor=actor)
    return result
