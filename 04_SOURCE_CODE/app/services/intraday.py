# -*- coding: utf-8 -*-
"""S06 日内、昼夜与晨昏分析。

硬契约：基础格必须来自 S03 同一硬掩码与同一原始文件哈希；15 分钟格是唯一底层时间单位，
小时/2 小时/24 小时/典型日全部由它聚合。低覆盖格单独标记，绝不把缺测当低谷。
天文分段时间需要真实经纬度与声明时区；坐标系未声明的结果只标 PROVISIONAL，不冒充最终结论。
"""
from __future__ import annotations

import json
import math
import sqlite3
import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable

from ..config import PROJECT_ROOT
from ..db import _now
from . import daily_stats as ds
from . import distance_mapping as dm
from .csv_parser import inspect_file, iter_rows

METHOD_VERSION = "INTRADAY_V1"
SLOT_MINUTES = 15
SLOTS_PER_DAY = 96
DEFAULT_MIN_COVERAGE = 0.5
EVENT_THRESHOLD = ds.DEFAULT_EVENT_THRESHOLD
EVENT_MIN_BINS = ds.DEFAULT_EVENT_MIN_BINS
CIVIL_ZENITH = 96.0
SOLAR_ZENITH = 90.833
DEFAULT_ANCHOR = {"h": (6.0, 9.0), "l": (10.0, 15.0), "r": (16.0, 19.0)}


class AnalysisUnavailable(Exception):
    """前置数据/坐标/覆盖不足，明确阻断，不生成伪造结论。"""


def date_range(start: str, end: str) -> list[str]:
    """两端包含的日期序列，供 CLI/网页把起止日期展开为逐日分析。"""
    first = datetime.strptime(start, "%Y-%m-%d").date()
    last = datetime.strptime(end, "%Y-%m-%d").date()
    if last < first:
        raise ValueError("结束日期早于开始日期")
    return [(first + timedelta(days=offset)).isoformat()
            for offset in range((last - first).days + 1)]


@dataclass(frozen=True)
class SolarDay:
    observed_date: str
    sunrise: datetime
    sunset: datetime
    dawn: datetime
    dusk: datetime
    crs_status: str
    crs_note: str

    def segment(self, moment: datetime, night_anchor: "SolarDay | None" = None) -> str:
        if moment < self.dawn or moment >= self.sunrise:
            return "NIGHT_MORNING"
        if moment < self.sunrise:
            return "CIVIL_DAWN"
        if moment < self.sunset:
            return "DAY"
        if moment < self.dusk:
            return "CIVIL_DUSK"
        return "NIGHT_EVENING"


def _floor_slot(moment: datetime) -> datetime:
    return moment.replace(minute=(moment.minute // SLOT_MINUTES) * SLOT_MINUTES,
                          second=0, microsecond=0)


def _slot_span(day: str, slot_index: int) -> tuple[str, str]:
    start = datetime.strptime(day, "%Y-%m-%d") + timedelta(minutes=slot_index * SLOT_MINUTES)
    return (start.isoformat(timespec="seconds"),
            (start + timedelta(minutes=SLOT_MINUTES)).isoformat(timespec="seconds"))


def build_grid(conn: sqlite3.Connection, device_id: str, observed_date: str,
               *, project_root: Path | None = None, overwrite: bool = False,
               coverage_mode: str = "timestamp") -> int:
    """按原始 CSV + S03 掩码生成 15 分钟基础格；同一文件哈希与算法版本下幂等。"""
    root = Path(project_root or PROJECT_ROOT)
    stat = ds.latest_stat(conn, device_id, observed_date)
    if stat is None or stat["status"] in ("MISSING", "QC_FAILED", "BLOCKED", "UNKNOWN"):
        raise AnalysisUnavailable(f"{device_id}/{observed_date} 无可用 S03 统计行")
    source_sha = stat["file_sha256"]
    existing = conn.execute(
        "SELECT COUNT(*) n FROM s06_time_grid WHERE device_id=? AND observed_date=? "
        "AND method_version=? AND source_file_sha=?",
        (device_id, observed_date, METHOD_VERSION, source_sha)).fetchone()["n"]
    if existing and not overwrite:
        return existing

    path = root / "01_ORIGINAL_DATA" / "FISHFINDER" / device_id / f"探鱼-{device_id}_{observed_date}.csv"
    if not path.exists():
        raise AnalysisUnavailable(f"原始文件不存在：{path}")
    inspection = inspect_file(path, compute_hash=True)
    if source_sha and inspection.sha256 != source_sha:
        raise AnalysisUnavailable(f"原始文件哈希与 S03 统计行不一致：{path}")
    context = ds.resolve_stat_context(conn, device_id)
    if not context.usable:
        raise AnalysisUnavailable(f"{device_id} 截断或距离映射不可用：{'；'.join(context.reasons)}")

    resolution = stat["timestamp_resolution_s"] or 1
    cells: dict[int, dict] = {}
    for row in iter_rows(inspection):
        if row.timestamp is None:
            continue
        if row.timestamp.date().isoformat() != observed_date:
            continue
        if row.effective_signal_len == 0:
            continue
        try:
            mask = dm.build_mask(row.signal[:row.effective_signal_len], context.mapping,
                                 context.cutoff_m, row_range_m=row.range_m,
                                 row_point_count=row.effective_signal_len, allow_blocked=False)
        except dm.DistanceMappingBlocked:
            continue
        if not mask.kept_count:
            continue
        slot = int((row.timestamp.hour * 60 + row.timestamp.minute) // SLOT_MINUTES)
        cell = cells.setdefault(slot, {"valid": 0, "events": 0, "kept": 0, "timestamps": set()})
        cell["valid"] += 1
        cell["kept"] += mask.kept_count
        cell["timestamps"].add(row.timestamp)
        cell["events"] += ds.detect_candidate_events(mask.kept_indices, mask.kept_values)
    created = _now()
    if overwrite:
        conn.execute("DELETE FROM s06_time_grid WHERE device_id=? AND observed_date=?",
                     (device_id, observed_date))
    records = []
    for slot, cell in sorted(cells.items()):
        start, end = _slot_span(observed_date, slot)
        if coverage_mode == "slot":
            covered = SLOT_MINUTES * 60
        elif coverage_mode == "timestamp":
            covered = len(cell["timestamps"]) * resolution
        else:
            raise ValueError("coverage_mode 只能是 timestamp 或 slot")
        records.append((device_id, observed_date, start, end, cell["valid"], cell["events"],
                        cell["kept"], covered, min(1.0, covered / (SLOT_MINUTES * 60)),
                        source_sha, METHOD_VERSION, created))
    conn.executemany(
        "INSERT OR REPLACE INTO s06_time_grid (device_id,observed_date,slot_start,slot_end,"
        "valid_records,candidate_events,kept_samples,distinct_seconds,coverage_ratio,"
        "source_file_sha,method_version,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", records)
    conn.commit()
    return len(records)


def load_grid(conn: sqlite3.Connection, device_ids: Iterable[str], dates: Iterable[str]) -> list[dict]:
    devices = list(device_ids)
    days = list(dates)
    if not devices or not days:
        return []
    placeholders_d = ",".join("?" for _ in devices)
    placeholders_t = ",".join("?" for _ in days)
    rows = conn.execute(
        f"SELECT * FROM s06_time_grid WHERE device_id IN ({placeholders_d}) "
        f"AND observed_date IN ({placeholders_t}) ORDER BY observed_date, device_id, slot_start",
        devices + days).fetchall()
    return [dict(r) for r in rows]


def _slot_index(cell: dict) -> int:
    moment = datetime.fromisoformat(cell["slot_start"])
    return moment.hour * 4 + moment.minute // SLOT_MINUTES


def aggregate(grid: list[dict], size_minutes: int, *, min_coverage: float = DEFAULT_MIN_COVERAGE) -> list[dict]:
    """把 15 分钟基础格按 15/60/120 分钟聚合；覆盖不足的格保留但标 low_coverage。"""
    if size_minutes not in (15, 60, 120):
        raise ValueError("仅支持 15/60/120 分钟聚合")
    groups: dict[tuple[str, str, int], dict] = defaultdict(
        lambda: {"events": 0, "valid": 0, "kept": 0, "seconds": 0.0, "slots": 0, "low": 0})
    for cell in grid:
        bucket = _slot_index(cell) // (size_minutes // SLOT_MINUTES)
        key = (cell["device_id"], cell["observed_date"], bucket)
        group = groups[key]
        group["events"] += cell["candidate_events"]
        group["valid"] += cell["valid_records"]
        group["kept"] += cell["kept_samples"]
        group["seconds"] += (cell["coverage_ratio"] or 0) * SLOT_MINUTES * 60
        group["slots"] += 1
        if (cell["coverage_ratio"] or 0) < min_coverage:
            group["low"] += 1
    out = []
    for (device_id, observed_date, bucket), group in sorted(groups.items()):
        covered = group["seconds"]
        out.append({
            "device_id": device_id, "observed_date": observed_date, "bucket": bucket,
            "start_minute": bucket * size_minutes, "end_minute": (bucket + 1) * size_minutes,
            "candidate_events": group["events"], "valid_records": group["valid"],
            "kept_samples": group["kept"], "covered_seconds": round(covered, 3),
            "rate_per_hour": (group["events"] / (covered / 3600)) if covered > 0 else None,
            "low_coverage": group["low"] > 0,
            "source_slots": group["slots"],
        })
    return out


def daily_profile(hourly: list[dict]) -> dict:
    """逐日 24 小时曲线：低覆盖小时保留但值 NA，不跨缺口平滑。"""
    profile: dict[tuple[str, str], dict] = {}
    for cell in hourly:
        key = (cell["device_id"], cell["observed_date"])
        item = profile.setdefault(key, {
            "device_id": cell["device_id"], "observed_date": cell["observed_date"],
            "rate_per_hour": [None] * 24, "coverage": [None] * 24,
            "candidate_events": [None] * 24, "low_coverage_hours": [],
        })
        hour = cell["start_minute"] // 60
        item["rate_per_hour"][hour] = cell["rate_per_hour"]
        item["coverage"][hour] = min(1.0, cell["covered_seconds"] / 3600)
        item["candidate_events"][hour] = cell["candidate_events"]
        if cell["low_coverage"]:
            item["low_coverage_hours"].append(hour)
    return {"profiles": list(profile.values()), "note":
            "低覆盖小时标 NA 并在 low_coverage_hours 列出；曲线不跨缺口插值。"}


def heatmap_15(grid: list[dict], *, min_coverage: float = DEFAULT_MIN_COVERAGE) -> dict:
    cells = {}
    for cell in grid:
        coverage = cell["coverage_ratio"] or 0
        rate = (cell["candidate_events"] / (coverage * SLOT_MINUTES * 60 / 3600)) if coverage > 0 else None
        cells[f"{cell['device_id']}|{cell['observed_date']}|{_slot_index(cell)}"] = {
            "device_id": cell["device_id"], "observed_date": cell["observed_date"],
            "slot_index": _slot_index(cell), "rate_per_hour": rate,
            "coverage": coverage, "low_coverage": coverage < min_coverage,
            "candidate_events": cell["candidate_events"],
        }
    return {"cells": cells, "slot_minutes": SLOT_MINUTES,
            "note": "15 分钟率的分母为该格有效覆盖秒数；低覆盖格仍显示但标 low_coverage，不等同于真实低谷。"}


def two_hour_groups(hourly: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, int], dict] = defaultdict(
        lambda: {"events": 0, "seconds": 0.0, "valid": 0, "low": 0})
    for cell in hourly:
        group_index = cell["start_minute"] // 120
        key = (cell["device_id"], cell["observed_date"], group_index)
        group = groups[key]
        group["events"] += cell["candidate_events"]
        group["seconds"] += cell["covered_seconds"]
        group["valid"] += cell["valid_records"]
        group["low"] += int(cell["low_coverage"])
    out = []
    for (device_id, observed_date, index), group in sorted(groups.items()):
        out.append({
            "device_id": device_id, "observed_date": observed_date,
            "start_hour": index * 2, "end_hour": index * 2 + 2,
            "candidate_events": group["events"], "covered_seconds": round(group["seconds"], 3),
            "rate_per_hour": group["events"] / (group["seconds"] / 3600) if group["seconds"] else None,
            "low_coverage": group["low"] > 0,
        })
    return out


def typical_day(hourly: list[dict], *, min_days: int = 3) -> dict:
    """先逐日按有效暴露规范化，再跨日等权汇总；避免记录多的一天支配结果。"""
    by_key: dict[tuple[str, int], list[float]] = defaultdict(list)
    for cell in hourly:
        if cell["low_coverage"] or cell["rate_per_hour"] is None:
            continue
        by_key[(cell["device_id"], cell["start_minute"] // 60)].append(cell["rate_per_hour"])
    out = []
    for device_id in sorted({k[0] for k in by_key}):
        for hour in range(24):
            values = by_key.get((device_id, hour), [])
            enough = len(values) >= min_days
            out.append({
                "device_id": device_id, "hour": hour, "n_effective_days": len(values),
                "mean_rate_per_hour": statistics.fmean(values) if values else None,
                "median_rate_per_hour": statistics.median(values) if values else None,
                "p10_rate_per_hour": _quantile(values, 0.10),
                "p90_rate_per_hour": _quantile(values, 0.90),
                "status": "OK" if enough else "INSUFFICIENT_DAYS",
            })
    return {"hours": out, "min_days": min_days, "aggregation": "日级率等权均值（先日内后跨日）",
            "note": f"每个钟点至少 {min_days} 个有效日才给典型值；不足则 NA，不把单日峰值升级为规律。"}


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _solar_times(lat: float, lon: float, day: date, offset_hours: float,
                 zenith: float) -> tuple[datetime, datetime] | None:
    """NOAA 简化日出日落算法；极昼极夜返回 None，绝不推断一个假日落。"""
    gamma = 2 * math.pi / 365 * (day.timetuple().tm_yday - 1)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                       - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    cosine = (math.cos(math.radians(zenith))
              / (math.cos(math.radians(lat)) * math.cos(decl))
              - math.tan(math.radians(lat)) * math.tan(decl))
    if not -1 <= cosine <= 1:
        return None
    hour_angle = math.degrees(math.acos(cosine))
    base = datetime.combine(day, time(0, 0))
    sunrise_utc = base + timedelta(minutes=720 - 4 * (lon + hour_angle) - eqtime)
    sunset_utc = base + timedelta(minutes=720 - 4 * (lon - hour_angle) - eqtime)
    return sunrise_utc + timedelta(hours=offset_hours), sunset_utc + timedelta(hours=offset_hours)


def solar_for(conn: sqlite3.Connection, device_id: str, observed_date: str,
              timezone_name: str, offset_hours: float) -> SolarDay | None:
    row = conn.execute(
        "SELECT * FROM device_positions WHERE device_id=? AND effective_from<=? "
        "AND (effective_to IS NULL OR effective_to>=?) ORDER BY version DESC LIMIT 1",
        (device_id, observed_date, observed_date)).fetchone()
    if row is None:
        return None
    lat, lon = row["latitude_deg"], row["longitude_deg"]
    day = datetime.strptime(observed_date, "%Y-%m-%d").date()
    times = _solar_times(lat, lon, day, offset_hours, SOLAR_ZENITH)
    civil = _solar_times(lat, lon, day, offset_hours, CIVIL_ZENITH)
    if times is None or civil is None:
        return None
    sunrise, sunset = times
    dawn, dusk = civil
    crs = row["coordinate_reference_system"]
    undeclared = not crs or crs.upper() in ("UNKNOWN", "NULL")
    return SolarDay(
        observed_date=observed_date, sunrise=sunrise, sunset=sunset, dawn=dawn, dusk=dusk,
        crs_status="UNDECLARED" if undeclared else "DECLARED",
        crs_note=("坐标系未声明：按输入经纬度数值直接计算，未做基准转换；天文分段标 PROVISIONAL"
                  if undeclared else f"坐标系={crs}"))


def _slot_midpoint(cell: dict) -> datetime:
    return datetime.fromisoformat(cell["slot_start"]) + timedelta(minutes=SLOT_MINUTES / 2)


def _segment_summary(cells: list[dict], start: datetime, end: datetime) -> dict:
    chosen = [c for c in cells if start <= _slot_midpoint(c) < end]
    seconds = sum((c["coverage_ratio"] or 0) * SLOT_MINUTES * 60 for c in chosen)
    events = sum(c["candidate_events"] for c in chosen)
    return {
        "start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds"),
        "candidate_events": events, "covered_seconds": round(seconds, 3),
        "rate_per_hour": events / (seconds / 3600) if seconds > 0 else None,
        "source_slots": len(chosen),
        "low_coverage": any((c["coverage_ratio"] or 0) < DEFAULT_MIN_COVERAGE for c in chosen),
    }


def day_night(conn: sqlite3.Connection, grid: list[dict], device_ids: Iterable[str],
              dates: Iterable[str], timezone_name: str, offset_hours: float) -> dict:
    """夜间以夜开始日期锚定：D 日夜 = D 日落→24:00 + D+1 日 00:00→日出。"""
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for cell in grid:
        by_key[(cell["device_id"], cell["observed_date"])].append(cell)
    results = []
    for device_id in device_ids:
        for observed_date in dates:
            cells = by_key.get((device_id, observed_date), [])
            solar = solar_for(conn, device_id, observed_date, timezone_name, offset_hours)
            next_date = (datetime.strptime(observed_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            next_solar = solar_for(conn, device_id, next_date, timezone_name, offset_hours)
            if solar is None or next_solar is None or not cells:
                stat = ds.latest_stat(conn, device_id, observed_date)
                next_stat = ds.latest_stat(conn, device_id, next_date)
                next_cells = by_key.get((device_id, next_date), [])
                if not cells or stat is None:
                    reason = "无该日 S03 统计行/15 分钟格，不能做昼夜比较；不是经纬度缺失"
                elif not next_cells or next_stat is None:
                    reason = "次日无 S03 统计行/15 分钟格，不能做跨午夜昼夜比较；不是经纬度缺失"
                else:
                    reason = "缺少该日/次日真实经纬度或声明时区，禁止伪造天文昼夜"
                results.append({
                    "device_id": device_id, "observed_date": observed_date,
                    "status": "BLOCKED", "reason": reason, "segments": {},
                })
                continue
            day_start = datetime.fromisoformat(observed_date + "T00:00:00")
            day_end = day_start + timedelta(days=1)
            segments = {
                "NIGHT_MORNING": _segment_summary(cells, day_start, solar.dawn),
                "CIVIL_DAWN": _segment_summary(cells, solar.dawn, solar.sunrise),
                "DAY": _segment_summary(cells, solar.sunrise, solar.sunset),
                "CIVIL_DUSK": _segment_summary(cells, solar.sunset, solar.dusk),
                "NIGHT_EVENING": _segment_summary(cells, solar.dusk, day_end),
            }
            next_start = day_end
            next_morning = _segment_summary(
                by_key.get((device_id, next_date), []), next_start, next_solar.sunrise)
            evening = segments["NIGHT_EVENING"]
            night_events = evening["candidate_events"] + next_morning["candidate_events"]
            night_seconds = evening["covered_seconds"] + next_morning["covered_seconds"]
            day_segment = segments["DAY"]
            night_rate = night_events / (night_seconds / 3600) if night_seconds > 0 else None
            day_rate = day_segment["rate_per_hour"]
            night_expected = ((day_end - solar.dusk).total_seconds()
                              + (next_solar.sunrise - next_start).total_seconds())
            day_expected = (solar.sunset - solar.sunrise).total_seconds()
            night_ratio = night_seconds / night_expected if night_expected > 0 else None
            day_ratio = (day_segment["covered_seconds"] / day_expected
                         if day_expected > 0 else None)
            comparable = bool(night_ratio is not None and day_ratio is not None
                              and night_ratio >= 0.9 and day_ratio >= 0.9
                              and night_seconds >= 900 and day_segment["covered_seconds"] >= 900)
            results.append({
                "device_id": device_id, "observed_date": observed_date,
                "status": "PROVISIONAL" if solar.crs_status == "UNDECLARED" else "OK",
                "crs_status": solar.crs_status, "crs_note": solar.crs_note,
                "solar": {"sunrise": solar.sunrise.isoformat(timespec="seconds"),
                          "sunset": solar.sunset.isoformat(timespec="seconds"),
                          "dawn": solar.dawn.isoformat(timespec="seconds"),
                          "dusk": solar.dusk.isoformat(timespec="seconds")},
                "segments": segments,
                "night_anchor_date": observed_date,
                "night_next_morning": next_morning,
                "pair": {
                    "night_events": night_events, "night_covered_seconds": round(night_seconds, 3),
                    "night_rate_per_hour": night_rate, "day_rate_per_hour": day_rate,
                    "difference": (night_rate - day_rate) if night_rate is not None and day_rate is not None else None,
                    "night_expected_seconds": round(night_expected, 3),
                    "night_coverage_ratio": round(night_ratio, 6) if night_ratio is not None else None,
                    "day_expected_seconds": round(day_expected, 3),
                    "day_coverage_ratio": round(day_ratio, 6) if day_ratio is not None else None,
                    "coverage_ok": comparable,
                    "comparison_status": "COMPARABLE" if comparable else "NOT_COMPARABLE_PARTIAL_NIGHT",
                },
            })
    return {"results": results, "night_anchor": "夜开始日期（日落当日）",
            "note": "晨昏按民用曙暮光 96°；天文分段时间按 15 分钟格中点归类，边界格不细分子区间。"
                    "昼夜比较要求夜段与日段覆盖率均≥90% 且各≥900 s；半截夜标 NOT_COMPARABLE_PARTIAL_NIGHT，不与完整日比较。"}


def solar_windows(conn: sqlite3.Connection, grid: list[dict], device_ids: Iterable[str],
                  dates: Iterable[str], timezone_name: str, offset_hours: float,
                  minutes_before_after: int = 120) -> dict:
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for cell in grid:
        by_key[(cell["device_id"], cell["observed_date"])].append(cell)
    results = []
    for device_id in device_ids:
        for observed_date in dates:
            cells = by_key.get((device_id, observed_date), [])
            solar = solar_for(conn, device_id, observed_date, timezone_name, offset_hours)
            if solar is None or not cells:
                results.append({"device_id": device_id, "observed_date": observed_date,
                                "status": "BLOCKED", "reason": "缺经纬度/时区或当日无格"})
                continue
            delta = timedelta(minutes=minutes_before_after)
            results.append({
                "device_id": device_id, "observed_date": observed_date,
                "status": "PROVISIONAL" if solar.crs_status == "UNDECLARED" else "OK",
                "window_minutes": minutes_before_after,
                "before_sunrise": _segment_summary(cells, solar.sunrise - delta, solar.sunrise + delta),
                "after_sunset": _segment_summary(cells, solar.sunset - delta, solar.sunset + delta),
            })
    return {"results": results, "note": "日出/日落前后为对称时间窗；与晨昏（太阳高度角）定义不同，不可混用。"}


def _runs(indices: list[int]) -> list[tuple[int, int]]:
    if not indices:
        return []
    ordered = sorted(indices)
    runs = []
    start = previous = ordered[0]
    for index in ordered[1:]:
        if index == previous + 1:
            previous = index
        else:
            runs.append((start, previous))
            start = previous = index
    runs.append((start, previous))
    return runs


def peaks(grid: list[dict], device_ids: Iterable[str], dates: Iterable[str],
          *, anchors: dict | None = None) -> dict:
    """峰谷与“早高—中低—再升”形态；证据不足只写 NOT_IDENTIFIABLE，不强行给时段。"""
    anchors = anchors or DEFAULT_ANCHOR
    high_share, low_share = 0.70, 0.35
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for cell in grid:
        by_key[(cell["device_id"], cell["observed_date"])].append(cell)
    results = []
    for (device_id, observed_date), cells in sorted(by_key.items()):
        if device_id not in device_ids or observed_date not in dates:
            continue
        valid = [c for c in cells if (c["coverage_ratio"] or 0) >= DEFAULT_MIN_COVERAGE
                 and c["candidate_events"] is not None]
        if len(valid) < int(SLOTS_PER_DAY * 0.6):
            results.append({"device_id": device_id, "observed_date": observed_date,
                            "status": "NOT_IDENTIFIABLE", "reason": "有效格不足 60%，不给峰谷时间",
                            "coverage_ratio": len(valid) / SLOTS_PER_DAY})
            continue
        rates = [(cell, cell["candidate_events"] / max(0.0167, (cell["coverage_ratio"] or 0) * 0.25))
                 for cell in valid]
        peak_cell, peak_rate = max(rates, key=lambda item: item[1])
        trough_cell, trough_rate = min(rates, key=lambda item: item[1])
        item = {
            "device_id": device_id, "observed_date": observed_date, "status": "OK",
            "peak_slot": _slot_index(peak_cell), "peak_rate_per_hour": round(peak_rate, 6),
            "trough_slot": _slot_index(trough_cell), "trough_rate_per_hour": round(trough_rate, 6),
            "coverage_ratio": round(len(valid) / SLOTS_PER_DAY, 4),
        }
        if peak_rate <= 0:
            item.update({"status": "NOT_IDENTIFIABLE", "reason": "全日候选事件为 0，峰值/低谷为真实零"})
            results.append(item)
            continue
        high = [_slot_index(c) for c, value in rates if value >= high_share * peak_rate]
        low = [_slot_index(c) for c, value in rates if value <= low_share * peak_rate]
        runs_high = _runs(high)
        runs_low = _runs(low)
        morning_high = next((run for run in runs_high if run[0] < 48), None)
        mid_low = next((run for run in runs_low if morning_high and run[0] > morning_high[0]), None)
        rebound = next((run for run in runs_high if mid_low and run[0] > mid_low[0]), None)
        if morning_high and mid_low and rebound:
            item.update({
                "pattern": "HIGH_LOW_REBOUND",
                "high_window": [morning_high[0] * SLOT_MINUTES, (morning_high[1] + 1) * SLOT_MINUTES],
                "decline_window": [(morning_high[1] + 1) * SLOT_MINUTES, mid_low[0] * SLOT_MINUTES],
                "low_window": [mid_low[0] * SLOT_MINUTES, (mid_low[1] + 1) * SLOT_MINUTES],
                "rebound_window": [rebound[0] * SLOT_MINUTES, (rebound[1] + 1) * SLOT_MINUTES],
                "duration_minutes": {
                    "high": (morning_high[1] - morning_high[0] + 1) * SLOT_MINUTES,
                    "low": (mid_low[1] - mid_low[0] + 1) * SLOT_MINUTES,
                    "rebound": (rebound[1] - rebound[0] + 1) * SLOT_MINUTES,
                },
                "coverage_details": [len(valid) / SLOTS_PER_DAY, item["coverage_ratio"]],
            })
        else:
            item.update({"pattern": "NOT_IDENTIFIABLE",
                         "reason": "未同时检出早间高值、随后低值与再次回升；不强行给时段"})
        results.append(item)
    return {"results": results, "anchors": anchors,
            "note": "高值阈值=峰值×0.7，低值阈值=峰值×0.35；15 分钟格；多峰/单峰/无峰均如实输出。"}


def environment_link(conn: sqlite3.Connection, hourly: list[dict], timezone_name: str) -> dict:
    """日内尺度环境关联：只用 S05 独立来源观测， lag=0，探索性，不写因果。"""
    from . import comparison as cmp
    from . import environment_analysis as env

    results = []
    for variable, location_key in (("WIND_SPEED", "SOURCE_GRID"), ("WATER_TEMP", "DEFAULT")):
        observations = [o for o in env.observations(conn, variable, location_key)
                        if o["source_kind"] != "DERIVED"]
        if not observations:
            results.append({"variable": variable, "status": "BLOCKED",
                            "reason": "无可用独立环境观测（代理数据不进入解释变量）"})
            continue
        env_by_utc = {o["observed_at_utc"][:16]: o["value_si"] for o in observations}
        pairs = []
        for cell in hourly:
            if cell["low_coverage"] or cell["rate_per_hour"] is None:
                continue
            local = datetime.fromisoformat(cell["observed_date"] + "T00:00:00")
            utc = local + timedelta(minutes=cell["start_minute"]) - timedelta(hours=cmp.utc_offset_hours(timezone_name))
            value = env_by_utc.get(utc.strftime("%Y-%m-%dT%H:%M"))
            if value is not None:
                pairs.append((value, cell["rate_per_hour"]))
        if len(pairs) < 8:
            results.append({"variable": variable, "status": "INSUFFICIENT_PAIRS",
                            "n_pairs": len(pairs), "reason": "共同有效小时不足 8，不给相关系数"})
            continue
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        r = env.pearson(xs, ys)
        n_eff = max(4, int(len(pairs) / (1 + 2 * abs(env.autocorr1(ys) or 0))))
        fisher = env._fisher(r, n_eff)
        results.append({"variable": variable, "status": "OK", "n_pairs": len(pairs), "n_eff": n_eff,
                        "r": r, "ci95": fisher["ci95"], "p_two_sided": fisher["p_two_sided"],
                        "note": "Lag=0 探索性关联；环境在前/时滞全表见 S05；关联≠因果"})
    candidates = [item for item in results if item.get("p_two_sided") is not None]
    adjusted = env.holm_adjust(candidates)
    for item, adjusted_item in zip(candidates, adjusted):
        item["p_holm"] = adjusted_item["p_holm"]
    return {"results": results, "timezone": timezone_name,
            "disclaimer": "日内环境关联仅作探索；模型历史气象不是现场实测；关联≠因果。"}


def period_typical(hourly: list[dict], period: str, *, min_days: int = 2) -> dict:
    """周/月典型日：必须达到最小有效日数，否则只标不足，不升级为长期规律。"""
    if period not in ("weekday", "month"):
        raise ValueError("period 只能是 weekday 或 month")
    values: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    for cell in hourly:
        if cell["low_coverage"] or cell["rate_per_hour"] is None:
            continue
        day = datetime.strptime(cell["observed_date"], "%Y-%m-%d").date()
        label = str(day.weekday()) if period == "weekday" else day.strftime("%Y-%m")
        values[(cell["device_id"], label, cell["start_minute"] // 60)].append(cell["rate_per_hour"])
    out = []
    for (device_id, label, hour), series in sorted(values.items()):
        out.append({"device_id": device_id, "period": label, "hour": hour,
                    "n_effective_days": len(series),
                    "mean_rate_per_hour": statistics.fmean(series) if series else None,
                    "status": "OK" if len(series) >= min_days else "INSUFFICIENT_DAYS"})
    return {"period": period, "hours": out, "min_days": min_days,
            "note": "日历星期分类不等于生物学七日节律；样本不足只标不足。"}


def run(conn: sqlite3.Connection, devices: Iterable[str], dates: Iterable[str], *,
        name: str = "S06 日内分析", timezone_name: str = "Asia/Shanghai",
        tz_offset_hours: float | None = None, project_root: Path | None = None,
        min_days: int = 3, build: bool = True, coverage_mode: str = "timestamp",
        overwrite_grids: bool = False) -> dict:
    from . import comparison as cmp

    device_ids = list(devices)
    observed_dates = sorted(set(dates))
    offset = cmp.utc_offset_hours(timezone_name) if tz_offset_hours is None else tz_offset_hours
    blocked = []
    if build:
        for device_id in device_ids:
            for observed_date in observed_dates:
                try:
                    build_grid(conn, device_id, observed_date, project_root=project_root,
                               coverage_mode=coverage_mode, overwrite=overwrite_grids)
                except (AnalysisUnavailable, OSError) as exc:
                    blocked.append({"device_id": device_id, "observed_date": observed_date,
                                    "reason": str(exc)})
    grid = load_grid(conn, device_ids, observed_dates)
    grid15 = aggregate(grid, 15)
    hourly = aggregate(grid, 60)
    profile = daily_profile(hourly)
    result = {
        "analysis_id": "S06-" + uuid.uuid4().hex[:12].upper(),
        "name": name, "generated_at": _now(), "method_version": METHOD_VERSION,
        "scope": {
            "devices": device_ids, "dates": observed_dates, "timezone": timezone_name,
            "utc_offset_hours": offset, "slot_minutes": SLOT_MINUTES,
            "min_coverage": DEFAULT_MIN_COVERAGE, "n_grid_cells": len(grid),
            "blocked_inputs": blocked,
        },
        "grid_15min": grid15,
        "hourly": hourly,
        "daily_profile": profile,
        "two_hour_groups": two_hour_groups(hourly),
        "typical_day": typical_day(hourly, min_days=min_days),
        "weekday_typical": period_typical(hourly, "weekday"),
        "month_typical": period_typical(hourly, "month"),
        "heatmap": heatmap_15(grid),
        "day_night": day_night(conn, grid, device_ids, observed_dates, timezone_name, offset),
        "solar_windows": solar_windows(conn, grid, device_ids, observed_dates, timezone_name, offset),
        "peaks": peaks(grid, device_ids, observed_dates),
        "environment": environment_link(conn, hourly, timezone_name),
        "notes": [
            "15 分钟格由 S03 原始文件哈希绑定；小时/2 小时/典型日均由同一格聚合。",
            "低覆盖格标 NA/low_coverage，不作为真实低谷；曲线不插值。",
            "天文分段需真实经纬度；坐标系未声明的结果为 PROVISIONAL，未做基准转换。",
            "单日峰值不升级为长期规律，典型日按日等权，周/月样本不足只标不足。",
        ],
    }
    conn.execute(
        "INSERT INTO s06_analysis_run (run_id,name,criteria_json,result_json,method_version,created_at,actor) "
        "VALUES (?,?,?,?,?,?,?)",
        (result["analysis_id"], name,
         json.dumps(result["scope"], ensure_ascii=False),
         json.dumps(result, ensure_ascii=False), METHOD_VERSION, _now(), "system"))
    conn.commit()
    return result


def write_outputs(result: dict, output_root: Path | None = None) -> list[str]:
    import csv
    import json
    from pathlib import Path

    root = Path(output_root or PROJECT_ROOT) / "06_ANALYSIS_RESULTS" / "s06" / result["analysis_id"]
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    (root / "analysis_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    created.append(str(root / "analysis_result.json"))
    with (root / "grid_15min.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields = ("device_id", "observed_date", "start_minute", "end_minute", "candidate_events",
                  "valid_records", "kept_samples", "covered_seconds", "rate_per_hour", "low_coverage")
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(result["grid_15min"])
        created.append(str(root / "grid_15min.csv"))

    lines = ["# S06 日内、昼夜与晨昏分析", "",
             f"分析 ID：{result['analysis_id']}｜算法：{METHOD_VERSION}",
             f"设备：{','.join(result['scope']['devices'])}｜日期：{','.join(result['scope']['dates'])}",
             f"时区：{result['scope']['timezone']}（UTC{result['scope']['utc_offset_hours']:+.0f}）", "",
             "## 口径", *[f"- {note}" for note in result["notes"]], "",
             "## 峰谷与形态"]
    for item in result["peaks"]["results"]:
        lines.append(f"- {item['device_id']} {item['observed_date']}：{item.get('pattern', item['status'])}"
                     f"｜峰时格 {item.get('peak_slot')}｜覆盖 {item.get('coverage_ratio')}")
    lines += ["", "## 昼夜", ""]
    for item in result["day_night"]["results"]:
        pair = item.get("pair", {})
        lines.append(f"- {item['device_id']} {item['observed_date']}：{item['status']}"
                     f"｜夜率 {pair.get('night_rate_per_hour')}｜日率 {pair.get('day_rate_per_hour')}")
    lines += ["", "## 环境关联（探索性）", ""]
    for item in result["environment"]["results"]:
        lines.append(f"- {item['variable']}：{item['status']}｜r={item.get('r')}"
                     f"｜p_Holm={item.get('p_holm')}")
    lines += ["", result["environment"]["disclaimer"],
              "", "关联不等同于因果；低覆盖与缺测不填 0。"]
    report = root / "report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    created.append(str(report))
    return created

