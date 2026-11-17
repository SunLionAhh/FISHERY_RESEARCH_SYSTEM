# -*- coding: utf-8 -*-
"""S05 环境—声学联合分析：时间配对、滞后、效应量与 CI、多重比较、诊断。

所有关联只表述为关联/时差，不表述因果；预报、代理或缺测资料不得当作独立实测证据。
"""
from __future__ import annotations

import json
import math
import uuid
from bisect import bisect_left
from datetime import datetime, timedelta, timezone as dt_timezone
from itertools import combinations

import numpy as np

from . import comparison as cmp
from . import daily_stats as ds
from . import environment_import as env

INVALID_ACOUSTIC_STATUSES = cmp.BASELINE_INVALID_STATUSES

LAGS_HOURS = (0, 1, 2, 3, 6, 12, 24)
DEFAULT_TOLERANCE_S = 1800
ALLOWED_QUALITIES = ("OK", "MODEL_HISTORICAL", "DERIVED")
SPEED_BINS = ((0, 2), (2, 4), (4, 6), (6, 8), (8, float("inf")))
TEMP_BINS = ((-math.inf, 21), (21, 22), (22, 23), (23, math.inf))


class AnalysisUnavailable(Exception):
    pass


def _json(text, default=None):
    try:
        return json.loads(text) if text else (default if default is not None else {})
    except (TypeError, ValueError):
        return default if default is not None else {}


def _hour_key(value: str) -> datetime:
    return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")


def acoustic_hourly(conn, devices, start_date, end_date) -> dict[tuple[str, str], dict]:
    """键 (device_id, 本地小时 ISO)；只取 S03 有效统计行，缺测/阻断不生成伪 0。"""
    out = {}
    rows = ds.all_latest_stats(conn)
    for row in rows:
        if row["device_id"] not in devices or row["status"] in INVALID_ACOUSTIC_STATUSES:
            continue
        if start_date and row["observed_date"] < start_date:
            continue
        if end_date and row["observed_date"] > end_date:
            continue
        hourly = _json(row["hourly_activity_json"], {})
        events = hourly.get("candidate_events", []) or []
        valid = hourly.get("valid_records", []) or []
        for hour in range(24):
            if hour >= len(events) or hour >= len(valid):
                continue
            if valid[hour] <= 0:
                continue
            stamp = f"{row['observed_date']}T{hour:02d}:00:00"
            out[(row["device_id"], stamp)] = {
                "device_id": row["device_id"], "local_time": stamp,
                "candidate_events": events[hour], "valid_records": valid[hour],
                "observed_date": row["observed_date"],
            }
    return out


def observations(conn, variable: str, location_key: str | None = None) -> list[dict]:
    sql = ("SELECT o.*, s.kind AS source_kind FROM environment_observation o "
           "JOIN environment_source s ON s.source_id=o.source_id "
           "WHERE o.variable=?")
    params = [variable]
    if location_key is not None:
        sql += " AND o.location_key=?"
        params.append(location_key)
    sql += " ORDER BY o.observed_at_utc"
    return [dict(r) for r in conn.execute(sql, params)
            if r["quality_flag"] in ALLOWED_QUALITIES]


def _utc_from_local(stamp: str, timezone_name: str) -> datetime:
    offset = env.comparison.utc_offset_hours(timezone_name)
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S") - timedelta(hours=offset)


def pair(conn, acoustic: dict, variable: str, location_key: str, lag_hours: int,
         *, tolerance_s: int = DEFAULT_TOLERANCE_S, timezone_name: str = "Asia/Shanghai") -> list[dict]:
    series = sorted(((_utc_from_local(o["observed_at"], o["timezone"]), o["value_si"], o)
                     for o in observations(conn, variable, location_key)), key=lambda x: x[0])
    times = [x[0] for x in series]
    pairs = []
    for (device_id, stamp), record in acoustic.items():
        target = _utc_from_local(stamp, timezone_name) - timedelta(hours=lag_hours)
        pos = bisect_left(times, target)
        candidates = []
        for idx in (pos - 1, pos):
            if 0 <= idx < len(times):
                delta = abs((times[idx] - target).total_seconds())
                if delta <= tolerance_s:
                    candidates.append((delta, idx))
        if not candidates:
            continue
        delta, idx = min(candidates)
        pairs.append({
            "device_id": device_id, "acoustic_time": stamp, "lag_hours": lag_hours,
            "delta_seconds": int(delta), "tolerance_seconds": tolerance_s,
            "acoustic_value": record["candidate_events"], "environment_value": series[idx][1],
            "obs_id": series[idx][2]["obs_id"], "quality_flag": series[idx][2]["quality_flag"],
            "source_id": series[idx][2]["source_id"],
        })
    return pairs


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return None
    return max(-1.0, min(1.0, cov / math.sqrt(var_x * var_y)))


def autocorr1(values: list[float]) -> float:
    if len(values) < 3:
        return 0.0
    mean = sum(values) / len(values)
    denom = sum((v - mean) ** 2 for v in values)
    if denom <= 0:
        return 0.0
    return sum((values[i] - mean) * (values[i - 1] - mean)
               for i in range(1, len(values))) / denom


def _fisher(r: float, n_eff: int) -> dict:
    if abs(r) >= 1.0:
        return {"r": r, "ci95": [r, r], "p_two_sided": 0.0 if n_eff >= 4 else None,
                "note": "样本完全共线，Fisher z 不适用；置信区间退化为端点"}
    if n_eff < 4:
        return {"r": r, "ci95": [None, None], "p_two_sided": None,
                "note": "有效样本不足，不给置信区间与 p"}
    z = 0.5 * math.log((1 + r) / (1 - r))
    se = 1 / math.sqrt(n_eff - 3)
    lo, hi = z - 1.96 * se, z + 1.96 * se
    transform = lambda v: (math.exp(2 * v) - 1) / (math.exp(2 * v) + 1)
    p = math.erfc(abs(z) / math.sqrt(2) / se)  # Fisher z 正态近似双尾
    return {"r": round(r, 6), "ci95": [round(transform(lo), 6), round(transform(hi), 6)],
            "p_two_sided": p, "note": "Fisher z；p 为正态近似，小样本不作显著性结论"}


def holm_adjust(items: list[dict]) -> list[dict]:
    ranked = sorted((it for it in items if it.get("p_two_sided") is not None),
                    key=lambda it: it["p_two_sided"])
    running = 0.0
    for index, item in enumerate(ranked):
        count = len(ranked) - index
        running = max(running, min(1.0, item["p_two_sided"] * count))
        item["p_holm"] = running
    for item in items:
        item.setdefault("p_holm", None)
    return items


def lag_analysis(conn, acoustic: dict, variable: str, location_key: str,
                 *, tolerance_s: int = DEFAULT_TOLERANCE_S,
                 timezone_name: str = "Asia/Shanghai",
                 lags=LAGS_HOURS) -> dict:
    """滞后方向：环境变量时刻 = 声学时刻 - lag；所有预设 lag 全量输出，不挑显著。"""
    results = []
    for lag in lags:
        pairs = pair(conn, acoustic, variable, location_key, lag,
                     tolerance_s=tolerance_s, timezone_name=timezone_name)
        if len(pairs) < 5:
            results.append({"lag_hours": lag, "n_pairs": len(pairs), "status": "INSUFFICIENT_PAIRS",
                            "r": None, "ci95": [None, None], "p_two_sided": None,
                            "note": "有效配对不足 5；不据此下结论"})
            continue
        xs = [p["environment_value"] for p in pairs]
        ys = [p["acoustic_value"] for p in pairs]
        r = pearson(xs, ys)
        if r is None:
            results.append({"lag_hours": lag, "n_pairs": len(pairs), "status": "NO_VARIANCE",
                            "r": None, "ci95": [None, None], "p_two_sided": None,
                            "note": "变量无变化，相关不可估计"})
            continue
        rx, ry = autocorr1(xs), autocorr1(ys)
        denominator = 1 + rx * ry
        n_eff = (len(pairs) * (1 - rx * ry) / denominator) if denominator > 0 else len(pairs) / 3
        n_eff = max(3, min(len(pairs), int(round(n_eff))))
        stat = _fisher(r, n_eff)
        stat.update({"lag_hours": lag, "n_pairs": len(pairs), "n_eff": n_eff,
                     "autocorr_lag1": [round(rx, 4), round(ry, 4)],
                     "mean_delta_seconds": round(sum(p["delta_seconds"] for p in pairs) / len(pairs), 1),
                     "status": "OK" if n_eff >= 10 else "UNCERTAIN",
                     "direction": "ENV_LEADS_ACOUSTIC" if lag else "SYNCHRONOUS"})
        results.append(stat)
    holm_adjust(results)
    return {"variable": variable, "location_key": location_key, "timezone": timezone_name,
            "tolerance_seconds": tolerance_s, "lag_direction": "环境在前，声学在后（lag>0）",
            "search_range_hours": list(lags), "results": results,
            "note": "全部候选时滞均已列出；相关不等于因果，未做变显著挑选"}


def binned(rows: list[dict], value_key: str, bins) -> list[dict]:
    out = []
    for low, high in bins:
        selected = [r for r in rows if low <= r[value_key] < high]
        label = f"[{low:g},{high:g})" if math.isfinite(high) else f"[{low:g},+∞)"
        out.append({"bin": label, "n": len(selected),
                    "mean_acoustic": (round(sum(r["acoustic_value"] for r in selected) / len(selected), 6)
                                      if selected else None)})
    return out


def variable_report(conn, acoustic: dict, variable: str, location_key: str,
                    *, bins, timezone_name: str = "Asia/Shanghai") -> dict:
    pairs = pair(conn, acoustic, variable, location_key, 0, timezone_name=timezone_name)
    available = observations(conn, variable, location_key)
    if not available:
        return {"variable": variable, "status": "BLOCKED",
                "reason": "无已导入且非预报的该变量观测；不估读图片、不伪造数值",
                "n_observations": 0}
    flags = sorted({o["quality_flag"] for o in available})
    report = {
        "variable": variable, "location_key": location_key, "status": "OK",
        "n_observations": len(available), "quality_flags": flags,
        "n_pairs": len(pairs), "bins": binned(pairs, "environment_value", bins),
        "proxy_warning": ("数据来源于声学 CSV 派生代理，不是独立环境观测；"
                          "仅作同源描述，不能作为独立环境证据"
                          if all(o["source_kind"] == "DERIVED" for o in available) else None),
    }
    if variable == "WIND_DIRECTION":
        report["wind_direction"] = "圆周量须用 sin/cos 处理；本表仅作线性对照，方向结论以联合模型为准"
    if variable == "TIDE_HEIGHT":
        report["tide_note"] = "潮位不是流速；涨落潮只用潮位差派生，不推断水团运动"
    return report


def joint_analysis(conn, acoustic: dict, variables: list[str], location_keys: dict[str, str],
                   *, timezone_name: str = "Asia/Shanghai") -> dict:
    """多元联合： standardize 后最小二乘；样本/变量比不足或共线则给诊断而不给结论。"""
    usable, excluded = [], []
    for variable in variables:
        key = location_keys.get(variable)
        available = observations(conn, variable, key) if key else []
        if not available:
            excluded.append({"variable": variable, "reason": "无该位置观测"})
        elif all(o["source_kind"] == "DERIVED" for o in available):
            excluded.append({"variable": variable, "reason": "仅派生代理，不是独立环境观测"})
        else:
            usable.append((variable, key))
    if not usable:
        return {"status": "BLOCKED", "reason": "无可用的独立环境解释变量", "excluded": excluded}
    pairs_by_var = {}
    for variable, key in usable:
        pairs = pair(conn, acoustic, variable, key, 0, timezone_name=timezone_name)
        if pairs:
            pairs_by_var[variable] = {(p["acoustic_time"], p["device_id"]): p["environment_value"]
                                      for p in pairs}
    common = set.intersection(*(set(m) for m in pairs_by_var.values())) if pairs_by_var else set()
    if len(common) < max(10, 5 * len(usable)):
        return {"status": "INSUFFICIENT_SAMPLES", "n_common": len(common),
                "variables": [v for v, _ in usable],
                "reason": "共同有效配对不足（每变量至少 5 个有效样本且总数≥10）"}
    lookup = {(v["local_time"], k[0]): v["candidate_events"] for k, v in acoustic.items()}
    ordered = sorted(common)
    y = np.array([lookup[k] for k in ordered], dtype=float)
    matrix = np.column_stack([
        np.ones(len(ordered)),
        *[np.array([pairs_by_var[v][k] for k in ordered], dtype=float) for v, _ in usable],
    ])
    names = ["intercept", *[v for v, _ in usable]]
    Xs = matrix[:, 1:].copy()
    means, stds = Xs.mean(axis=0), Xs.std(axis=0)
    stds[stds == 0] = 1.0
    matrix[:, 1:] = (Xs - means) / stds
    y_std = (y - y.mean()) / (y.std() if y.std() else 1.0)
    try:
        beta, _, rank, _ = np.linalg.lstsq(matrix, y_std, rcond=None)
    except np.linalg.LinAlgError as exc:
        return {"status": "NUMERIC_FAILED", "reason": str(exc)}
    fitted = matrix @ beta
    ss_res = float(((y_std - fitted) ** 2).sum())
    ss_tot = float(((y_std - y_std.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot else None
    diagnostics = []
    if rank < matrix.shape[1]:
        diagnostics.append("设计矩阵秩不足：变量共线，系数不可单独解释")
    if len(common) < 30:
        diagnostics.append("共同样本少于 30：效应量不稳定")
    return {"status": "OK" if not diagnostics else "UNCERTAIN", "n_common": len(common),
            "variables": [v for v, _ in usable], "excluded": excluded,
            "standardized_beta": dict(zip(names, beta.tolist())),
            "r_squared": r2, "rank": int(rank), "diagnostics": diagnostics,
            "note": "多元回归只描述同期关联；无因果解释，预报与派生代理数据不进入解释变量"}


def run(conn, *, devices=("2000",), start_date=None, end_date=None,
        timezone_name="Asia/Shanghai", tolerance_s=DEFAULT_TOLERANCE_S,
        location_keys=None) -> dict:
    analysis_id = "ENV-" + uuid.uuid4().hex[:12].upper()
    device_list = list(devices)
    acoustic = acoustic_hourly(conn, device_list, start_date, end_date)
    keys = dict(location_keys or {})
    keys.setdefault("WIND_SPEED", "SOURCE_GRID")
    keys.setdefault("WIND_DIRECTION", "SOURCE_GRID")
    keys.setdefault("WATER_TEMP", "DEFAULT")
    keys.setdefault("TIDE_HEIGHT", "DEFAULT")
    variables = {
        "WATER_TEMP": variable_report(conn, acoustic, "WATER_TEMP", keys["WATER_TEMP"],
                                      bins=TEMP_BINS, timezone_name=timezone_name),
        "TIDE_HEIGHT": variable_report(conn, acoustic, "TIDE_HEIGHT", keys["TIDE_HEIGHT"],
                                       bins=((-math.inf, 0), (0, 1), (1, 2), (2, math.inf)),
                                       timezone_name=timezone_name),
        "WIND_SPEED": variable_report(conn, acoustic, "WIND_SPEED", keys["WIND_SPEED"],
                                      bins=SPEED_BINS, timezone_name=timezone_name),
        "WIND_DIRECTION": variable_report(conn, acoustic, "WIND_DIRECTION", keys["WIND_DIRECTION"],
                                          bins=((0, 90), (90, 180), (180, 270), (270, 360)),
                                          timezone_name=timezone_name),
    }
    lags = {}
    for variable in variables:
        if variables[variable]["status"] == "OK" and variables[variable]["n_pairs"] >= 5:
            lags[variable] = lag_analysis(conn, acoustic, variable, keys[variable],
                                          tolerance_s=tolerance_s, timezone_name=timezone_name)
        else:
            lags[variable] = {"status": "BLOCKED", "reason": variables[variable].get(
                "reason", "可用配对不足")}
    joint = joint_analysis(conn, acoustic,
                           [v for v in variables if variables[v]["status"] == "OK"
                            and v != "WIND_DIRECTION"], keys, timezone_name=timezone_name)
    all_lag_items = [item for result in lags.values() for item in result.get("results", [])
                     if isinstance(item, dict)]
    holm_adjust(all_lag_items)
    result = {
        "analysis_id": analysis_id, "generated_at": datetime.now(dt_timezone.utc).isoformat(
            timespec="seconds") + "Z",
        "scope": {"devices": device_list, "start_date": start_date, "end_date": end_date,
                  "timezone": timezone_name, "tolerance_seconds": tolerance_s,
                  "n_acoustic_hours": len(acoustic), "location_keys": keys},
        "variables": variables, "lag_analysis": lags, "joint_analysis": joint,
        "disclaimer": "关联≠因果；预报/模型/代理资料已标注，不能当作独立实测环境证据。",
    }
    return result
