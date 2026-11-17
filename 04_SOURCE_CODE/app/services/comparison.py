# -*- coding: utf-8 -*-
"""S04 通用筛选与比较引擎。

纪律：
- 所有输入指标只来自 S03 `v_latest_daily_statistics`，不重算、不补齐、不填 0；
- 日期区间两端包含；小时区间 [start,end)，跨午夜由当日 [start,24) + 次日 [0,end) 组成，
  窗口归属起始日期，每个日历小时在一次选择中只归属一个窗口实例；
- 原始时间戳为设备本地时间，S04 只做口径声明与可追溯换算，不把推断时区写成实测；
- 日内子窗口的有效时长与覆盖率由小时样本占比估算并显式标记 estimated；
  全天窗口使用 S03 精确值；无小时分布的信号分布/水温不伪造；
- 参考值为 0 时百分比变化为 NA；缺测/QC_FAILED/BLOCKED 日不得进入有效基线。
"""
from __future__ import annotations

import csv
import json
import math
import re
import statistics
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from ..identity import current_operator
from . import daily_stats as ds

DEFAULT_TIMEZONE = "Asia/Shanghai"
SOURCE_TIME_NOTE = "原始 CSV 时间戳为设备本地时间；未附带时区元数据，按 Asia/Shanghai(UTC+08:00) 声明比对口径，不冒充实测时区。"
ENDPOINT_RULE = (
    "日期区间 [start_date, end_date] 两端包含；小时区间 [hour_start, hour_end) 左闭右开；"
    "hour_end < hour_start 表示跨午夜，窗口归属起始日期，消耗当日 [start,24) 与次日 [0,end) 的小时。"
)
DAY_NIGHT_CONVENTION = (6, 18)
DAY_NIGHT_NOTE = "昼夜按可配置约定 06:00—18:00 / 18:00—06:00 划分（非天文日出日落，S06 再引入晨昏）。"
BASELINE_INVALID_STATUSES = frozenset({
    ds.STATUS_MISSING, ds.STATUS_QC_FAILED, ds.STATUS_BLOCKED, ds.STATUS_UNKNOWN,
})
METRIC_FIELDS = (
    "valid_records", "candidate_events", "kept_samples",
    "candidate_event_rate_per_hour", "coverage_ratio", "valid_observation_duration_s",
    "signal_mean", "signal_median", "signal_p95", "activity_peak_hour",
    "activity_peak_value", "day_night_diff", "water_temp_mean",
)
METRIC_LABELS = {
    "valid_records": "有效记录数（条）",
    "candidate_events": "候选回波事件（次）",
    "kept_samples": "区内有效样本量（点）",
    "candidate_event_rate_per_hour": "候选事件率（次/有效观测小时）",
    "coverage_ratio": "有效覆盖率（0—1）",
    "valid_observation_duration_s": "有效观测时长（s）",
    "signal_mean": "区内信号均值（0—255）",
    "signal_median": "区内信号中位数（0—255）",
    "signal_p95": "区内信号 P95（0—255）",
    "activity_peak_hour": "活动峰值小时（0—23）",
    "activity_peak_value": "活动峰值（次/小时）",
    "day_night_diff": "昼—夜候选事件差（次）",
    "water_temp_mean": "平均水温（°C）",
}


class ComparisonValidationError(ValueError):
    pass


class ComparisonEmptyError(ValueError):
    pass


@dataclass(frozen=True)
class Criteria:
    devices: tuple[str, ...] = ()
    stations: tuple[str, ...] = ()
    start_date: str | None = None
    end_date: str | None = None
    dates: tuple[str, ...] = ()
    hour_start: int | None = None
    hour_end: int | None = None
    day_count: int | None = None
    day_count_mode: str = "calendar"
    timezone: str = DEFAULT_TIMEZONE
    day_hours: tuple[int, int] = DAY_NIGHT_CONVENTION
    include_invalid: bool = False

    @classmethod
    def from_dict(cls, raw: dict | None) -> "Criteria":
        raw = dict(raw or {})
        for key in ("devices", "stations", "dates"):
            if isinstance(raw.get(key), str):
                raw[key] = tuple(x.strip() for x in raw[key].split(",") if x.strip())
            elif raw.get(key) is not None:
                raw[key] = tuple(str(x) for x in raw[key])
        for key in ("hour_start", "hour_end", "day_count"):
            if raw.get(key) in ("", None):
                raw[key] = None
            elif raw.get(key) is not None:
                raw[key] = int(raw[key])
        if raw.get("day_hours") and not isinstance(raw["day_hours"], tuple):
            raw["day_hours"] = tuple(int(x) for x in raw["day_hours"])
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def as_dict(self) -> dict:
        return asdict(self)


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ComparisonValidationError(f"日期格式非法：{value!r}，应为 YYYY-MM-DD")


def _json(raw: str | None, fallback):
    if raw is None or raw == "":
        return fallback
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


def utc_offset_hours(timezone_name: str) -> float:
    """把声明时区解析为固定偏移；未知声明直接拒绝，不猜、不静默按北京时间处理。"""
    name = (timezone_name or "").strip()
    if name in ("Asia/Shanghai", "UTC+08:00", "+08:00", "CST"):
        return 8.0
    if name in ("UTC", "UTC+00:00", "+00:00", "Z"):
        return 0.0
    match = re.fullmatch(r"([+-])(\d{1,2}):?(\d{2})?", name)
    if match:
        sign = 1 if match.group(1) == "+" else -1
        return sign * (int(match.group(2)) + int(match.group(3) or 0) / 60)
    raise ComparisonValidationError(
        f"不支持的时区声明：{timezone_name!r}；可用 Asia/Shanghai / UTC / ±HH:MM")


def _window_bounds(row, criteria: Criteria, hours: list[int] | None,
                   next_date: str | None) -> tuple[str, str, str, str]:
    """返回本地起止与 UTC 起止（半开区间），用于 K26 边界与跨午夜对账。"""
    offset = utc_offset_hours(criteria.timezone)
    full = hours is None or sorted(hours) == list(range(24))
    start_hour = criteria.hour_start if not full else 0
    end_hour = criteria.hour_end if not full else 24
    start_day = row["observed_date"]
    end_day = next_date if next_date else row["observed_date"]
    local_start = datetime.strptime(f"{start_day}T{start_hour:02d}:00:00", "%Y-%m-%dT%H:%M:%S")
    if end_hour == 24:
        local_end = datetime.strptime(end_day, "%Y-%m-%d") + timedelta(days=1)
    else:
        local_end = datetime.strptime(f"{end_day}T{end_hour:02d}:00:00", "%Y-%m-%dT%H:%M:%S")
    utc_start = local_start - timedelta(hours=offset)
    utc_end = local_end - timedelta(hours=offset)
    return (local_start.isoformat(timespec="seconds"), local_end.isoformat(timespec="seconds"),
            utc_start.strftime("%Y-%m-%dT%H:%M:%SZ"), utc_end.strftime("%Y-%m-%dT%H:%M:%SZ"))


def validate(criteria: Criteria, conn=None) -> None:
    if (criteria.hour_start is None) != (criteria.hour_end is None):
        raise ComparisonValidationError("hour_start 与 hour_end 必须同时提供")
    if criteria.hour_start is not None:
        if not 0 <= criteria.hour_start <= 23 or not 1 <= criteria.hour_end <= 24:
            raise ComparisonValidationError("小时范围须满足 0<=hour_start<=23、1<=hour_end<=24")
        if criteria.hour_start == criteria.hour_end:
            raise ComparisonValidationError("hour_start 与 hour_end 不得相同")
    if criteria.day_count is not None and criteria.day_count < 1:
        raise ComparisonValidationError("day_count 必须为正整数")
    if criteria.day_count_mode not in ("calendar", "valid"):
        raise ComparisonValidationError("day_count_mode 只能是 calendar 或 valid")
    for value in criteria.dates:
        _parse_date(value)
    for key in ("start_date", "end_date"):
        value = getattr(criteria, key)
        if value:
            _parse_date(value)
    if criteria.start_date and criteria.end_date and criteria.start_date > criteria.end_date:
        raise ComparisonValidationError("start_date 不得晚于 end_date")
    if len(criteria.day_hours) != 2 or not all(0 <= h <= 24 for h in criteria.day_hours):
        raise ComparisonValidationError("day_hours 必须为 [0,24] 内两个整数")
    if not criteria.timezone:
        raise ComparisonValidationError("timezone 不得为空")
    utc_offset_hours(criteria.timezone)
    if conn is None:
        return
    known = {r[0] for r in conn.execute("SELECT device_id FROM devices")}
    unknown = [d for d in criteria.devices if d not in known]
    if unknown:
        raise ComparisonValidationError(f"未知设备：{unknown}（五台为 2000/2001/2002/2003/2005）")
    known_stations = {r[0] for r in conn.execute("SELECT station_id FROM stations")}
    unknown_stations = [s for s in criteria.stations if s not in known_stations]
    if unknown_stations:
        raise ComparisonValidationError(f"未知站位：{unknown_stations}（stations 表无该记录，禁止伪造）")


def _resolve_devices(conn, criteria: Criteria) -> list[str]:
    rows = conn.execute("SELECT device_id, station_id FROM devices ORDER BY device_id").fetchall()
    result = []
    for row in rows:
        device_id = row["device_id"]
        if criteria.devices and device_id not in criteria.devices:
            continue
        if criteria.stations and row["station_id"] not in criteria.stations:
            continue
        result.append(device_id)
    return result


def _all_dates(conn) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT observed_date FROM v_latest_daily_statistics ORDER BY observed_date")]


def _valid_dates(conn) -> list[str]:
    placeholders = ",".join("?" for _ in BASELINE_INVALID_STATUSES)
    return [r[0] for r in conn.execute(
        f"SELECT DISTINCT observed_date FROM v_latest_daily_statistics "
        f"WHERE status NOT IN ({placeholders}) ORDER BY observed_date",
        tuple(BASELINE_INVALID_STATUSES))]


def _resolve_dates(conn, criteria: Criteria) -> list[str]:
    available = _all_dates(conn)
    if not available:
        return []
    if criteria.dates:
        return sorted(set(criteria.dates))
    if criteria.day_count is not None:
        anchor = criteria.end_date or available[-1]
        anchor_day = _parse_date(anchor)
        if criteria.day_count_mode == "valid":
            pool = [d for d in _valid_dates(conn) if d <= anchor]
            return pool[-criteria.day_count:]
        return [(anchor_day - timedelta(days=i)).isoformat()
                for i in range(criteria.day_count - 1, -1, -1)]
    start = criteria.start_date or available[0]
    end = criteria.end_date or available[-1]
    start_day, end_day = _parse_date(start), _parse_date(end)
    if start_day > end_day:
        raise ComparisonValidationError("start_date 不得晚于 end_date")
    return [(start_day + timedelta(days=i)).isoformat()
            for i in range((end_day - start_day).days + 1)]


def _hour_indices(criteria: Criteria) -> list[int] | None:
    if criteria.hour_start is None:
        return None
    start, end = criteria.hour_start, criteria.hour_end
    if end > start:
        return list(range(start, end))
    return list(range(start, 24)) + list(range(0, end))


def _hist_stats(hist: dict) -> dict:
    pairs = []
    for key, count in hist.items():
        try:
            pairs.append((float(key), int(count)))
        except (TypeError, ValueError):
            continue
    if not pairs or sum(c for _, c in pairs) == 0:
        return {"mean": None, "median": None, "p95": None}
    total = sum(c for _, c in pairs)
    ordered = sorted(pairs)
    cumulative = 0
    median = p95 = None
    for value, count in ordered:
        cumulative += count
        if median is None and cumulative >= total / 2:
            median = value
        if p95 is None and cumulative >= total * 0.95:
            p95 = value
    return {
        "mean": sum(v * c for v, c in pairs) / total,
        "median": median if median is not None else ordered[-1][0],
        "p95": p95 if p95 is not None else ordered[-1][0],
    }


def _merge_hist(hists: Iterable[dict]) -> dict:
    merged: dict[str, int] = {}
    for hist in hists:
        for key, count in hist.items():
            merged[str(key)] = merged.get(str(key), 0) + int(count)
    return merged


def _peak(hourly_events: list[int] | None) -> tuple[int | None, int | None]:
    if not hourly_events or not any(hourly_events):
        return None, None
    best = max(hourly_events)
    return hourly_events.index(best), best


def _make_window(row, criteria: Criteria, hours: list[int] | None,
                 row_lookup: dict[tuple[str, str], object]) -> dict:
    if row["status"] in BASELINE_INVALID_STATUSES:
        return {
            "device_id": row["device_id"], "observed_date": row["observed_date"],
            "stat_id": row["stat_id"], "run_id": row["run_id"], "status": row["status"],
            "observation_status": row["observation_status"], "window_hours": hours or list(range(24)),
            "window_start_date": row["observed_date"], "window_next_date": None,
            "window_kind": "invalid_day", "partial": False, "estimated": False,
            "local_window_start": _window_bounds(row, criteria, None, None)[0],
            "local_window_end": _window_bounds(row, criteria, None, None)[1],
            "utc_window_start": _window_bounds(row, criteria, None, None)[2],
            "utc_window_end": _window_bounds(row, criteria, None, None)[3],
            "valid_records": None, "candidate_events": None, "kept_samples": None,
            "valid_observation_duration_s": None, "coverage_ratio": None,
            "candidate_event_rate_per_hour": None, "signal_mean": None, "signal_median": None,
            "signal_p95": None, "activity_peak_hour": None, "activity_peak_value": None,
            "day_night_diff": None, "day_night_night_events": None, "water_temp_mean": None,
            "hourly_candidate_events": None, "hourly_valid_records": None,
            "notes": [f"状态 {row['status']}：样本指标全部 NA（不填 0，不参与有效比较）"],
        }
    hourly = _json(row["hourly_activity_json"], {}) or {}
    hourly_valid = hourly.get("valid_records", []) or []
    hourly_events = hourly.get("candidate_events", []) or []
    hourly_kept = hourly.get("kept_samples", []) or []
    full_day = hours is None or sorted(hours) == list(range(24))
    wraps = hours is not None and bool(hours) and min(hours) < max(hours) and hours[-1] < hours[0]
    hours = list(range(24)) if full_day else (hours or [])
    next_date = None
    partial = False
    next_row = None
    current_hours = list(hours)
    next_hours: list[int] = []
    if wraps:
        next_date = (datetime.strptime(row["observed_date"], "%Y-%m-%d").date()
                     + timedelta(days=1)).isoformat()
        current_hours = [h for h in hours if h >= criteria.hour_start]
        next_hours = [h for h in hours if h < criteria.hour_start]
        next_row = row_lookup.get((row["device_id"], next_date))
        partial = next_row is None
        if partial:
            hours = current_hours
            next_hours = []
    next_hourly = (_json(next_row["hourly_activity_json"], {}) or {}) if next_row is not None else {}
    next_valid = next_hourly.get("valid_records", []) or []
    next_events = next_hourly.get("candidate_events", []) or []
    next_kept = next_hourly.get("kept_samples", []) or []

    def _sum(values, indices):
        return sum(values[h] for h in indices if h < len(values))

    valid_records = _sum(hourly_valid, current_hours) + _sum(next_valid, next_hours)
    events = _sum(hourly_events, current_hours) + _sum(next_events, next_hours)
    kept = _sum(hourly_kept, current_hours) + _sum(next_kept, next_hours)
    if full_day:
        duration = row["valid_observation_duration_s"]
        coverage = row["coverage_ratio"]
        estimated = False
    else:
        parts = []
        if sum(hourly_valid):
            parts.append((row["valid_observation_duration_s"] or 0)
                         * _sum(hourly_valid, current_hours) / sum(hourly_valid))
        if next_row is not None and sum(next_valid):
            parts.append((next_row["valid_observation_duration_s"] or 0)
                         * _sum(next_valid, next_hours) / sum(next_valid))
        duration = sum(parts) if parts else None
        coverage = (duration / (len(hours) * 3600)) if duration is not None and hours else None
        estimated = True
    rate = events / (duration / 3600) if duration and duration > 0 else None
    hist = _json(row["signal_histogram_json"], {}) or {}
    stats = _hist_stats(hist) if full_day else {"mean": None, "median": None, "p95": None}
    hour_labels = current_hours + next_hours
    window_events = ([hourly_events[h] if h < len(hourly_events) else 0 for h in current_hours]
                     + [next_events[h] if h < len(next_events) else 0 for h in next_hours])
    if full_day:
        peak_hour, peak_value = _peak(hourly_events)
    elif window_events and any(window_events):
        peak_value = max(window_events)
        peak_hour = hour_labels[window_events.index(peak_value)]
    else:
        peak_hour, peak_value = None, None
    day_hours = criteria.day_hours
    night_events = None
    day_night_diff = None
    if full_day and hourly_events:
        day_idx = [h for h in range(24) if day_hours[0] <= h < day_hours[1]]
        night_idx = [h for h in range(24) if h not in day_idx]
        day_events = sum(hourly_events[h] for h in day_idx)
        night_events = sum(hourly_events[h] for h in night_idx)
        day_night_diff = day_events - night_events
    notes = []
    if estimated:
        notes.append("日内子窗口有效时长/覆盖率按小时有效记录占比估算（estimated=true），非 S03 精确值")
    if wraps:
        notes.append(f"跨午夜窗口的 [0,{criteria.hour_end}) 小时取自次日 {next_date} 的统计行，归属起始日，不重复计入次日窗口")
    if partial:
        notes.append(f"跨午夜窗口次日 {next_date} 无统计行，只计入起始日可得小时（partial=true）")
    if not full_day:
        notes.append("子窗口无小时级直方图与水温，信号分布/水温指标为 NA（不伪造）")
    if peak_value is None:
        notes.append("窗口内候选事件全为 0，活动峰值与峰时为 NA（真实零，不虚构小时）")
    local_start, local_end, utc_start, utc_end = _window_bounds(row, criteria, hours, next_date)
    return {
        "device_id": row["device_id"], "observed_date": row["observed_date"],
        "stat_id": row["stat_id"], "run_id": row["run_id"], "status": row["status"],
        "observation_status": row["observation_status"], "window_hours": hours,
        "window_start_date": row["observed_date"], "window_next_date": next_date,
        "local_window_start": local_start, "local_window_end": local_end,
        "utc_window_start": utc_start, "utc_window_end": utc_end,
        "window_kind": "full_day" if full_day else ("cross_midnight" if wraps else "hour_range"),
        "partial": partial, "estimated": estimated,
        "valid_records": valid_records, "candidate_events": events, "kept_samples": kept,
        "valid_observation_duration_s": duration, "coverage_ratio": coverage,
        "candidate_event_rate_per_hour": rate,
        "signal_mean": stats["mean"], "signal_median": stats["median"], "signal_p95": stats["p95"],
        "activity_peak_hour": peak_hour, "activity_peak_value": peak_value,
        "day_night_diff": day_night_diff, "day_night_night_events": night_events,
        "water_temp_mean": row["water_temp_mean"] if full_day else None,
        "hourly_candidate_events": hourly_events if full_day else None,
        "hourly_valid_records": hourly_valid if full_day else None,
        "notes": notes,
    }


def select(conn, criteria: Criteria) -> dict:
    """按条件选择统计窗口；空集返回明确原因，不抛 500。"""
    validate(criteria, conn)
    devices = _resolve_devices(conn, criteria)
    resolved_dates = _resolve_dates(conn, criteria)
    excluded: list[dict] = []
    if not devices:
        raise ComparisonEmptyError("无符合筛选条件的设备（设备白名单、站位筛选交集为空）")
    if not resolved_dates:
        raise ComparisonEmptyError("正式库尚无 daily_statistics 统计行，无法比较")
    placeholders_d = ",".join("?" for _ in devices)
    placeholders_t = ",".join("?" for _ in resolved_dates)
    rows = conn.execute(
        f"SELECT * FROM v_latest_daily_statistics "
        f"WHERE device_id IN ({placeholders_d}) AND observed_date IN ({placeholders_t}) "
        f"ORDER BY observed_date, device_id",
        tuple(devices) + tuple(resolved_dates)).fetchall()
    present = {(r["device_id"], r["observed_date"]) for r in rows}
    for day in resolved_dates:
        for device_id in devices:
            if (device_id, day) not in present:
                excluded.append({"device_id": device_id, "observed_date": day,
                                 "reason": "NO_STAT_ROW", "detail": "该设备-日无 S03 统计行"})
    hours = _hour_indices(criteria)
    row_lookup = {(r["device_id"], r["observed_date"]): r for r in rows}
    windows = []
    for row in rows:
        if row["status"] in BASELINE_INVALID_STATUSES and not criteria.include_invalid:
            excluded.append({"device_id": row["device_id"], "observed_date": row["observed_date"],
                             "reason": "INVALID_OBSERVATION_DAY", "detail": f"status={row['status']}，不参与有效比较"})
            continue
        windows.append(_make_window(row, criteria, hours, row_lookup))
    if not windows:
        raise ComparisonEmptyError("筛选结果为空：所有设备-日均为缺测/无效或无统计行；"
                                   "可用 include_invalid=true 查看原始状态，但不得当作有效观测")
    return {
        "criteria": criteria.as_dict(),
        "resolved_devices": devices, "resolved_dates": resolved_dates,
        "hour_indices": hours, "window_count": len(windows),
        "windows": windows, "excluded": excluded,
        "endpoint_rule": ENDPOINT_RULE,
        "timezone": criteria.timezone, "timezone_note": SOURCE_TIME_NOTE,
        "day_night_note": DAY_NIGHT_NOTE,
        "source": "v_latest_daily_statistics（S03 最新统计行；缺测不填 0）",
    }


def compare_windows(subject: dict, reference: dict, *, label: str = "") -> dict:
    """单组比较：差值、变化百分比、参考值、有效样本量、覆盖率、结论。"""
    metrics = []
    for name in METRIC_FIELDS:
        a, b = subject.get(name), reference.get(name)
        diff = (a - b) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
        if diff is None:
            pct, pct_reason = None, "参考值或比较值为 NA"
        elif b == 0:
            pct, pct_reason = None, "参考值为 0，百分比变化为 NA（K27）"
        else:
            pct, pct_reason = diff / abs(b) * 100, None
        if diff is None:
            result = "NA"
        elif diff > 0:
            result = "HIGHER"
        elif diff < 0:
            result = "LOWER"
        else:
            result = "EQUAL"
        metrics.append({
            "metric": name, "label": METRIC_LABELS[name],
            "subject": a, "reference": b, "difference": diff,
            "change_percent": pct, "pct_note": pct_reason,
            "effective_n": subject.get("kept_samples"),
            "coverage": subject.get("coverage_ratio"),
            "coverage_estimated": subject.get("estimated", False),
            "result": result,
        })
    return {
        "label": label,
        "subject": {"device_id": subject["device_id"], "observed_date": subject["observed_date"],
                    "window_kind": subject["window_kind"]},
        "reference": {"device_id": reference["device_id"], "observed_date": reference["observed_date"],
                      "window_kind": reference["window_kind"]},
        "metrics": metrics,
        "primary": next(m for m in metrics if m["metric"] == "candidate_event_rate_per_hour"),
        "disclaimer": "候选事件为阈值算法结果，变化不得直接归因于真实鱼类数量变化。",
    }


def _average_reference(windows: list[dict]) -> dict:
    """由前 N 个窗口构造“前 N 天平均”参考窗口。"""
    def mean(key):
        values = [w[key] for w in windows if isinstance(w.get(key), (int, float))]
        return statistics.fmean(values) if values else None
    return {
        "device_id": windows[0]["device_id"] if windows else None,
        "observed_date": f"前{len(windows)}个有效日平均",
        "window_kind": "historical_mean",
        "valid_records": mean("valid_records"), "candidate_events": mean("candidate_events"),
        "kept_samples": mean("kept_samples"),
        "valid_observation_duration_s": mean("valid_observation_duration_s"),
        "coverage_ratio": mean("coverage_ratio"),
        "candidate_event_rate_per_hour": mean("candidate_event_rate_per_hour"),
        "signal_mean": mean("signal_mean"), "signal_median": mean("signal_median"),
        "signal_p95": mean("signal_p95"), "activity_peak_hour": None,
        "activity_peak_value": mean("activity_peak_value"),
        "day_night_diff": mean("day_night_diff"), "water_temp_mean": mean("water_temp_mean"),
        "estimated": any(w.get("estimated") for w in windows),
        "kept_samples_total": sum(w.get("kept_samples") or 0 for w in windows),
    }


def date_comparison_matrix(selection: dict, dates: list[str] | None = None) -> dict:
    """V4 任务四：固定的 8 组日期比较；不足 7 日时对应组标 INSUFFICIENT_DATES。"""
    by_device: dict[str, dict[str, dict]] = {}
    for w in selection["windows"]:
        by_device.setdefault(w["device_id"], {})[w["observed_date"]] = w
    cases = [
        ("D1_vs_D2", 1, "single", 2),
        ("D4_vs_D1", 4, "single", 1),
        ("D4_vs_D2", 4, "single", 2),
        ("D4_vs_D3", 4, "single", 3),
        ("D4_vs_prev3_mean", 4, "mean", 3),
        ("D5_vs_D3", 5, "single", 3),
        ("D5_vs_prev4_mean", 5, "mean", 4),
        ("D7_vs_prev6_mean", 7, "mean", 6),
    ]
    results = []
    for device_id, by_date in sorted(by_device.items()):
        ordered = [d for d in (dates or sorted(by_date)) if d in by_date]
        for name, subject_idx, mode, ref_n in cases:
            needed = max(subject_idx, ref_n)
            if len(ordered) < needed:
                results.append({
                    "device_id": device_id, "case": name, "status": "INSUFFICIENT_DATES",
                    "detail": f"该设备仅 {len(ordered)} 个可比较日，需 {needed} 日；不伪造第 {needed} 日",
                    "required_dates": needed,
                })
                continue
            subject = by_date[ordered[subject_idx - 1]]
            if mode == "single":
                reference = by_date[ordered[ref_n - 1]]
            else:
                reference = _average_reference([by_date[d] for d in ordered[:ref_n]])
            item = compare_windows(subject, reference, label=name)
            item["device_id"] = device_id
            item["status"] = "OK"
            item["subject_date"] = subject["observed_date"]
            item["reference_dates"] = ([reference["observed_date"]] if mode == "single"
                                       else ordered[:ref_n])
            results.append(item)
    return {"cases": results, "required_case_count": len(cases),
            "note": "第5/7日与前N日平均按前N个可比较日算术平均；不把缺测日计入平均。"}


def device_comparison_matrix(selection: dict, reference_device: str | None = None) -> dict:
    """任意设备比较：同日其他设备对照参考设备；缺一方时明确记 MISSING_PAIR，不补 0。"""
    windows = [w for w in selection["windows"] if w["status"] not in BASELINE_INVALID_STATUSES]
    devices = sorted(set(selection["resolved_devices"]) | {w["device_id"] for w in windows})
    if not devices:
        return {"cases": [], "reference_device": None, "note": "无有效窗口"}
    reference = reference_device or devices[0]
    if reference not in devices:
        raise ComparisonValidationError(f"参考设备 {reference} 不在本次筛选范围内")
    lookup = {(w["device_id"], w["observed_date"]): w for w in windows}
    cases = []
    for day in selection["resolved_dates"]:
        reference_window = lookup.get((reference, day))
        for device_id in devices:
            if device_id == reference:
                continue
            window = lookup.get((device_id, day))
            if window is None or reference_window is None:
                cases.append({
                    "device_id": device_id, "observed_date": day,
                    "case": f"{device_id}_vs_{reference}_{day}", "status": "MISSING_PAIR",
                    "detail": f"{device_id} 或参考设备 {reference} 在 {day} 无有效统计行",
                })
                continue
            item = compare_windows(window, reference_window,
                                   label=f"{device_id}_vs_{reference}_{day}")
            item.update({"device_id": device_id, "reference_device": reference,
                         "observed_date": day, "status": "OK"})
            cases.append(item)
    return {"cases": cases, "reference_device": reference,
            "note": "参考设备可指定；各设备按同日同口径窗口比较，不跨日混比。"}


def build_baseline(conn, criteria: Criteria, reference_date: str, *,
                   n: int | None = None, mode: str = "valid",
                   start: str | None = None, end: str | None = None) -> dict:
    """历史基线：前 N 有效观测日 / 前 N 日历日 / 全部历史 / 任意区间。"""
    validate(criteria, conn)
    _parse_date(reference_date)
    if mode not in ("valid", "calendar", "all", "range"):
        raise ComparisonValidationError("基线 mode 只能是 valid/calendar/all/range")
    if mode in ("valid", "calendar") and (n is None or n < 1):
        raise ComparisonValidationError("valid/calendar 基线须提供正整数 n")
    devices = _resolve_devices(conn, criteria)
    ref_day = _parse_date(reference_date)
    if mode == "calendar":
        candidates = [(ref_day - timedelta(days=i)).isoformat() for i in range(1, n + 1)]
    elif mode == "range":
        if not start or not end:
            raise ComparisonValidationError("range 基线须提供 start 与 end")
        s, e = _parse_date(start), _parse_date(end)
        candidates = [(s + timedelta(days=i)).isoformat() for i in range((e - s).days + 1)]
    else:
        candidates = _valid_dates(conn)
        candidates = [d for d in candidates if d < reference_date]
        if mode == "valid":
            candidates = candidates[-n:]
    placeholders_d = ",".join("?" for _ in devices)
    placeholders_t = ",".join("?" for _ in candidates) or "''"
    rows = conn.execute(
        f"SELECT * FROM v_latest_daily_statistics WHERE device_id IN ({placeholders_d}) "
        f"AND observed_date IN ({placeholders_t}) ORDER BY observed_date, device_id",
        tuple(devices) + tuple(candidates)).fetchall() if candidates else []
    members, excluded = [], []
    for row in rows:
        if row["status"] in BASELINE_INVALID_STATUSES:
            excluded.append({"device_id": row["device_id"], "observed_date": row["observed_date"],
                             "reason": "INVALID_BASELINE_DAY", "detail": f"status={row['status']}"})
            continue
        hourly = _json(row["hourly_activity_json"], {}) or {}
        events = sum(hourly.get("candidate_events", []))
        duration = row["valid_observation_duration_s"]
        members.append({
            "device_id": row["device_id"], "observed_date": row["observed_date"],
            "stat_id": row["stat_id"], "status": row["status"],
            "valid_records": row["valid_records"], "kept_samples": row["kept_samples"],
            "candidate_events": events, "valid_observation_duration_s": duration,
            "coverage_ratio": row["coverage_ratio"],
            "rate": events / (duration / 3600) if duration and duration > 0 else None,
        })
    by_device: dict[str, list[dict]] = {}
    for member in members:
        by_device.setdefault(member["device_id"], []).append(member)
    groups = {}
    for device_id, items in by_device.items():
        total_events = sum(i["candidate_events"] for i in items)
        total_duration = sum(i["valid_observation_duration_s"] or 0 for i in items)
        rates = [i["rate"] for i in items if i["rate"] is not None]
        groups[device_id] = {
            "members": items, "n_members": len(items),
            "sum_kept_samples": sum(i["kept_samples"] or 0 for i in items),
            "sum_valid_records": sum(i["valid_records"] or 0 for i in items),
            "sum_candidate_events": total_events,
            "sum_valid_duration_s": total_duration,
            "aggregate_rate_per_hour": total_events / (total_duration / 3600) if total_duration else None,
            "mean_daily_rate_per_hour": statistics.fmean(rates) if rates else None,
            "mean_coverage": statistics.fmean([i["coverage_ratio"] for i in items
                                               if i["coverage_ratio"] is not None]) if items else None,
            "shortfall": (n - len(items)) if mode in ("valid", "calendar") and n else 0,
        }
    if not groups:
        raise ComparisonEmptyError(
            f"基线为空：{reference_date} 之前无有效观测日（缺测/QC_FAILED/BLOCKED 已排除，未用 0 填充）")
    return {
        "reference_date": reference_date, "mode": mode, "n": n, "range": [start, end],
        "devices": groups, "excluded": excluded,
        "denominator_table": {
            "aggregate_rate_per_hour": "Σ候选事件 ÷ (Σ有效观测时长/3600)",
            "mean_daily_rate_per_hour": "各有效日 事件÷(该日有效时长/3600) 的算术平均",
            "n_members": "有效观测日行数（缺测/质检失败/阻断日不计入）",
        },
        "note": "基线只使用有效观测日；样本量不足时 shortfall>0，不补 0、不外推。",
    }


def rolling_baselines(conn, criteria: Criteria, dates: list[str], *, n: int = 3,
                      mode: str = "valid") -> list[dict]:
    return [{"reference_date": day,
             "baseline": build_baseline(conn, criteria, day, n=n, mode=mode)}
            for day in dates]


def summarize(selection: dict, comparisons: list[dict], baseline: dict | None = None) -> dict:
    """自动总结：高低日、幅度、设备差异、基线差异、缺测说明、不确定性。"""
    metric = "candidate_event_rate_per_hour"
    valid = [c for c in comparisons if c.get("status") == "OK" and c["primary"]["subject"] is not None]
    highest = max(valid, key=lambda c: c["primary"]["subject"]) if valid else None
    lowest = min(valid, key=lambda c: c["primary"]["subject"]) if valid else None
    amplitudes = [abs(c["primary"]["subject"] - c["primary"]["reference"]) for c in valid
                  if c["primary"]["reference"] is not None]
    device_values = {}
    for w in selection["windows"]:
        value = w.get(metric)
        if value is not None:
            device_values.setdefault(w["device_id"], []).append(value)
    device_means = {k: statistics.fmean(v) for k, v in device_values.items()}
    device_gap = (max(device_means.values()) - min(device_means.values())
                  if len(device_means) > 1 else None)
    missing = [e for e in selection["excluded"] if e["reason"] in
               ("NO_STAT_ROW", "INVALID_OBSERVATION_DAY")]
    notes = [
        "变化量来自 S03 硬掩码区内样本与阈值候选算法；不等同于真实鱼类数量变化，"
        "可能由观测覆盖、海况、设备差异、昼夜与算法阈值造成。",
        "时区口径：原始时间戳未附时区元数据，按声明时区比较，不把推断当作实测（K26）。",
        "日内子窗口覆盖率与有效时长为估算，全天窗口使用 S03 精确值；比较结果标注 estimated。",
        "参考值为 0 时变化百分比记 NA；缺测/质检失败/阻断日不进入有效基线（K27）。",
        "水层指标未纳入：S07 底界 QC 门禁尚未通过，禁止输出未经门禁的水层结论。",
    ]
    if baseline:
        notes.append("历史基线成员与分母见 baseline.denominator_table，可按 comparison_id 复现。")
    if not valid:
        notes.append("无有效比较组：不输出高低日与幅度结论。")
    lines = ["# S04 自动比较总结", ""]
    if highest and lowest:
        lines += [
            f"- 最高候选事件率：设备 {highest.get('device_id', '?')} / "
            f"{highest['subject']['observed_date']}，"
            f"{highest['primary']['subject']:.4f} 次/有效小时",
            f"- 最低候选事件率：设备 {lowest.get('device_id', '?')} / "
            f"{lowest['subject']['observed_date']}，"
            f"{lowest['primary']['subject']:.4f} 次/有效小时",
            f"- 最大绝对变化幅度：{max(amplitudes):.4f} 次/有效小时" if amplitudes else
            "- 最大绝对变化幅度：NA（参考值全为 NA）",
        ]
    if device_gap is not None:
        lines.append(f"- 设备间均值差（候选事件率）：{device_gap:.4f} 次/有效小时")
    if missing:
        lines.append(f"- 缺测/无效说明：{len(missing)} 个设备-日未参与比较，明细见 excluded")
    lines += ["", "## 不确定性说明", ""] + [f"- {n}" for n in notes]
    return {"highest": highest, "lowest": lowest, "max_abs_amplitude": max(amplitudes) if amplitudes else None,
            "device_mean_rate": device_means, "device_gap": device_gap,
            "missing_count": len(missing), "uncertainty_notes": notes,
            "markdown": "\n".join(lines)}


def run(conn, criteria: Criteria, *, name: str = "",
        compare_dates: tuple[str, ...] = (),
        baseline: dict | None = None,
        save: bool = True) -> dict:
    selection = select(conn, criteria)
    matrix = date_comparison_matrix(selection, list(compare_dates) or None)
    device_matrix = device_comparison_matrix(selection)
    comparisons = ([c for c in matrix["cases"] if c.get("status") == "OK"]
                   + [c for c in device_matrix["cases"] if c.get("status") == "OK"])
    summary = summarize(selection, comparisons, baseline)
    result = {
        "comparison_id": "CMP-" + uuid.uuid4().hex[:12].upper(),
        "name": name or "S04 比较",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "selection": selection, "date_comparison_matrix": matrix,
        "device_comparison_matrix": device_matrix,
        "baseline": baseline, "summary": summary,
    }
    if save:
        persist(conn, result)
    return result


def persist(conn, result: dict) -> None:
    conn.execute(
        "INSERT INTO comparison_runs (comparison_id,name,query_json,result_json,created_by,created_at) "
        "VALUES (?,?,?,?,?,?)",
        (result["comparison_id"], result["name"],
         json.dumps(result["selection"]["criteria"], ensure_ascii=False),
         json.dumps(result, ensure_ascii=False),
         current_operator(), result["generated_at"]))
    conn.commit()


def list_runs(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT comparison_id,name,created_by,created_at FROM comparison_runs ORDER BY created_at DESC")]


def write_outputs(result: dict, output_root: Path) -> list[str]:
    """导出比较结果 JSON、指标 CSV 与总结 MD。"""
    base = Path(output_root) / "06_ANALYSIS_RESULTS" / "s04" / result["comparison_id"]
    base.mkdir(parents=True, exist_ok=True)
    json_path = base / "comparison_result.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = base / "comparison_metrics.csv"
    fields = ["case", "device_id", "subject_date", "reference_dates", "metric", "label",
              "subject", "reference", "difference", "change_percent", "pct_note",
              "effective_n", "coverage", "coverage_estimated", "result"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for case in result["date_comparison_matrix"]["cases"]:
            if case.get("status") != "OK":
                writer.writerow({"case": case["case"], "device_id": case["device_id"],
                                 "result": case["status"], "pct_note": case["detail"]})
                continue
            for metric in case["metrics"]:
                writer.writerow({
                    "case": case["label"], "device_id": case["device_id"],
                    "subject_date": case["subject_date"],
                    "reference_dates": json.dumps(case["reference_dates"], ensure_ascii=False),
                    **{k: metric.get(k) for k in fields if k in metric},
                })
        for case in result.get("device_comparison_matrix", {}).get("cases", []):
            if case.get("status") == "OK":
                for metric in case["metrics"]:
                    writer.writerow({
                        "case": case["label"], "device_id": case["device_id"],
                        "subject_date": case["observed_date"],
                        "reference_dates": f"{case['reference_device']}@{case['observed_date']}",
                        **{k: metric.get(k) for k in fields if k in metric},
                    })
            else:
                writer.writerow({"case": case.get("case"), "device_id": case.get("device_id"),
                                 "result": case.get("status"), "pct_note": case.get("detail")})
    md_path = base / "comparison_summary.md"
    md_path.write_text(result["summary"]["markdown"], encoding="utf-8")
    return [str(p) for p in (json_path, csv_path, md_path)]
