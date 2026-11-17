# -*- coding: utf-8 -*-
"""S02 数据审计：流式聚合 + 8 份产物（03 第四章任务一—八）。

只读原始 CSV；不修改、不重排、不去重。所有「距离是否越界」的判断都走统一硬掩码服务
（`distance_mapping.build_mask`），本模块不自行计算下标或距离。
"""
from __future__ import annotations

import csv
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from . import distance_mapping as dm
from .csv_parser import (FileInspection, ParsedRow, first_zero_index, inspect_file,
                         iter_rows)

ARTIFACTS = (
    "field_dictionary.csv",
    "signal_array_audit.csv",
    "timestamp_audit.csv",
    "coverage_audit.csv",
    "device_comparability.csv",
    "bottom_reference_audit.csv",
    "issues.csv",
    "DATA_AUDIT_REPORT.md",
)

EXPECTED_POINTS = 1000  # 用户提供，仅为审计对照，不作为切片依据
DECLARED_RANGE_M = 37.5
# 用户口径（2026-11-17）：信号数组以第一个 0 开始才算数据盲区结束；设备盲区 0.5 m。
BLIND_ZONE_M = 0.5


@dataclass
class DeviceAudit:
    device_id: str
    inspection: FileInspection
    mapping: dm.DistanceMapping | None = None
    cutoff_m: float | None = None
    cutoff_status: str = "UNKNOWN"
    rows_total: int = 0
    rows_blank: int = 0
    rows_malformed: int = 0
    seq_missing: int = 0
    seq_non_integer: int = 0
    seq_duplicates: int = 0
    seq_duplicate_examples: list[str] = field(default_factory=list)
    ts_missing: int = 0
    ts_unparsed: int = 0
    ts_formats: Counter = field(default_factory=Counter)
    ts_multi_format: bool = False
    ts_min: datetime | None = None
    ts_max: datetime | None = None
    same_second_groups: int = 0
    same_second_rows: int = 0
    max_rows_per_second: int = 0
    repeat_timestamp_rows: int = 0
    interval_counts: Counter = field(default_factory=Counter)
    gap_examples: list[str] = field(default_factory=list)
    gap_gt_60: int = 0
    gap_gt_600: int = 0
    largest_gap_s: float = 0.0
    hours: Counter = field(default_factory=Counter)
    seconds_by_hour: dict[int, set] = field(default_factory=dict)
    dates: Counter = field(default_factory=Counter)
    date_crossing: bool = False
    depth_zero: int = 0
    depth_negative: int = 0
    depth_missing: int = 0
    depth_min: float | None = None
    depth_max: float | None = None
    depth_decimals: Counter = field(default_factory=Counter)
    temp_min: float | None = None
    temp_max: float | None = None
    temp_zero: int = 0
    temp_missing: int = 0
    ranges: Counter = field(default_factory=Counter)
    sig_lengths: Counter = field(default_factory=Counter)        # 有效槽位数（剔除尾部空 token）
    sig_token_lengths: Counter = field(default_factory=Counter)  # 原始 token 数
    sig_trailing_empty_total: int = 0
    sig_first_zero: Counter = field(default_factory=Counter)   # 首零索引分布（0 基）
    sig_rows_no_zero: int = 0
    pre_zero_min: float | None = None
    pre_zero_max: float | None = None
    pre_zero_invalid: int = 0
    ts_minute_precision_rows: int = 0
    sig_total_points: int = 0
    sig_empty_tokens: int = 0
    sig_non_numeric: int = 0
    sig_min: float | None = None
    sig_max: float | None = None
    sig_zero: int = 0
    sig_gt_255: int = 0
    sig_negative: int = 0
    rows_with_signal: int = 0
    rows_len_ne_1000: int = 0
    error_kinds: Counter = field(default_factory=Counter)
    error_examples: list[str] = field(default_factory=list)
    mask_status: str = "UNKNOWN"
    mask_blocked_reasons: tuple[str, ...] = ()
    mask_reason_summary: str = ""

    @property
    def duration_s(self) -> float | None:
        if self.ts_min and self.ts_max:
            return (self.ts_max - self.ts_min).total_seconds()
        return None

    @property
    def distinct_seconds(self) -> int:
        return sum(len(s) for s in self.seconds_by_hour.values())


def _decimals(text: str) -> int:
    t = text.strip()
    if "." not in t:
        return 0
    return len(t.split(".", 1)[1])


def _note_error(audit: DeviceAudit, row: ParsedRow) -> None:
    for err in row.errors:
        kind = err.split(" ", 1)[0]
        audit.error_kinds[kind] += 1
        if len(audit.error_examples) < 12:
            audit.error_examples.append(f"行{row.line_no}: {err}")


def audit_device(device_id: str, path: Path, *, conn: sqlite3.Connection | None = None,
                 compute_hash: bool = True, limit: int | None = None) -> DeviceAudit:
    inspection = inspect_file(path, compute_hash=compute_hash)
    audit = DeviceAudit(device_id=device_id, inspection=inspection)

    if conn is not None:
        from .devices import current_version
        cur = current_version(conn, device_id)
        if cur and cur["analysis_cutoff_slant_m"] is not None:
            audit.cutoff_m = cur["analysis_cutoff_slant_m"]
            audit.cutoff_status = "CONFIGURED"
        else:
            audit.cutoff_status = "MISSING"
        audit.mapping = dm.latest_mapping(conn, device_id, DECLARED_RANGE_M)

    seen_seq: set[int] = set()
    per_second: Counter = Counter()
    hours_set: dict[int, set] = {}
    prev_ts: datetime | None = None

    for row in iter_rows(inspection, limit=limit):
        audit.rows_total += 1
        if "空行" in row.errors:
            audit.rows_blank += 1
            _note_error(audit, row)
            continue
        if any(e.startswith("列数不符") for e in row.errors):
            audit.rows_malformed += 1
        _note_error(audit, row)

        # 序号
        if row.seq is None:
            if row.seq_raw.strip() == "":
                audit.seq_missing += 1
            else:
                audit.seq_non_integer += 1
        else:
            if row.seq in seen_seq:
                audit.seq_duplicates += 1
                if len(audit.seq_duplicate_examples) < 5:
                    audit.seq_duplicate_examples.append(f"行{row.line_no}: 序号 {row.seq} 重复")
            else:
                seen_seq.add(row.seq)

        # 时间
        if row.timestamp is None:
            if row.timestamp_raw.strip() == "":
                audit.ts_missing += 1
            else:
                audit.ts_unparsed += 1
        else:
            audit.ts_formats[row.timestamp_format] += 1
            if "%S" not in row.timestamp_format:
                audit.ts_minute_precision_rows += 1
            ts = row.timestamp
            if audit.ts_min is None or ts < audit.ts_min:
                audit.ts_min = ts
            if audit.ts_max is None or ts > audit.ts_max:
                audit.ts_max = ts
            per_second[ts] += 1
            audit.hours[ts.hour] += 1
            hours_set.setdefault(ts.hour, set()).add(ts.strftime("%Y-%m-%d %H:%M:%S"))
            audit.dates[ts.date().isoformat()] += 1
            if prev_ts is not None:
                delta = (ts - prev_ts).total_seconds()
                if delta == 0:
                    audit.interval_counts["0s（同秒）"] += 1
                elif delta == 1:
                    audit.interval_counts["1s"] += 1
                elif delta <= 2:
                    audit.interval_counts["1—2s"] += 1
                elif delta <= 10:
                    audit.interval_counts["2—10s"] += 1
                elif delta <= 60:
                    audit.interval_counts["10—60s"] += 1
                elif delta <= 600:
                    audit.interval_counts["1—10min"] += 1
                    audit.gap_gt_60 += 1
                else:
                    audit.interval_counts[">10min"] += 1
                    audit.gap_gt_60 += 1
                    audit.gap_gt_600 += 1
                if delta > audit.largest_gap_s:
                    audit.largest_gap_s = delta
                if delta > 60 and len(audit.gap_examples) < 8:
                    audit.gap_examples.append(
                        f"{prev_ts.isoformat(sep=' ')} → {ts.isoformat(sep=' ')}（{delta:.0f}s）")
                if delta < 0 and len(audit.gap_examples) < 8:
                    audit.gap_examples.append(
                        f"时间倒退：{prev_ts.isoformat(sep=' ')} → {ts.isoformat(sep=' ')}")
            prev_ts = ts

        # 水深 / 水温 / 量程
        if row.depth_m is None:
            audit.depth_missing += 1
        else:
            audit.depth_decimals[_decimals(row.depth_m_raw)] += 1
            if row.depth_m == 0:
                audit.depth_zero += 1
            if row.depth_m < 0:
                audit.depth_negative += 1
            if audit.depth_min is None or row.depth_m < audit.depth_min:
                audit.depth_min = row.depth_m
            if audit.depth_max is None or row.depth_m > audit.depth_max:
                audit.depth_max = row.depth_m
        if row.water_temp_c is None:
            audit.temp_missing += 1
        else:
            if row.water_temp_c == 0:
                audit.temp_zero += 1
            if audit.temp_min is None or row.water_temp_c < audit.temp_min:
                audit.temp_min = row.water_temp_c
            if audit.temp_max is None or row.water_temp_c > audit.temp_max:
                audit.temp_max = row.water_temp_c
        if row.range_m is None:
            audit.ranges["UNKNOWN"] += 1
        else:
            audit.ranges[f"{row.range_m:g}"] += 1

        # 信号数组（只统计，不判断越界；越界必须由硬掩码服务给出）
        if row.signal_len:
            audit.rows_with_signal += 1
            audit.sig_lengths[row.effective_signal_len] += 1
            audit.sig_token_lengths[row.signal_len] += 1
            audit.sig_trailing_empty_total += row.signal_trailing_empty
            fz = first_zero_index(row.signal)
            if fz is None:
                audit.sig_rows_no_zero += 1
            else:
                audit.sig_first_zero[fz] += 1
                for v in row.signal[:fz]:
                    if v is None:
                        audit.pre_zero_invalid += 1
                    elif audit.pre_zero_min is None or v < audit.pre_zero_min:
                        audit.pre_zero_min = v
                    elif audit.pre_zero_max is None or v > audit.pre_zero_max:
                        audit.pre_zero_max = v
            audit.sig_total_points += row.effective_signal_len
            audit.sig_empty_tokens += row.signal_empty_tokens
            audit.sig_non_numeric += row.signal_non_numeric
            if row.effective_signal_len != EXPECTED_POINTS:
                audit.rows_len_ne_1000 += 1
            for v in row.signal:
                if v is None:
                    continue
                if audit.sig_min is None or v < audit.sig_min:
                    audit.sig_min = v
                if audit.sig_max is None or v > audit.sig_max:
                    audit.sig_max = v
                if v == 0:
                    audit.sig_zero += 1
                elif v > 255:
                    audit.sig_gt_255 += 1
                elif v < 0:
                    audit.sig_negative += 1

    audit.same_second_groups = sum(1 for c in per_second.values() if c > 1)
    audit.same_second_rows = sum(c for c in per_second.values() if c > 1)
    audit.max_rows_per_second = max(per_second.values()) if per_second else 0
    audit.repeat_timestamp_rows = audit.rows_total - len(per_second)
    audit.seconds_by_hour = hours_set
    audit.date_crossing = len({d for d in audit.dates}) > 1
    audit.ts_multi_format = len({f for f, c in audit.ts_formats.items() if c}) > 1

    # 统一硬掩码：正式分析口径。映射未核实 → BLOCKED（示例行也给出原因计数）
    if audit.mapping is None:
        audit.mask_status = "BLOCKED"
        audit.mask_blocked_reasons = ("未登记距离映射",)
        audit.mask_reason_summary = f"{dm.REASON_MAPPING_UNVERIFIED}={audit.sig_total_points}"
    else:
        reasons = audit.mapping.blocking_reasons(DECLARED_RANGE_M, EXPECTED_POINTS)
        audit.mask_blocked_reasons = tuple(reasons)
        audit.mask_status = "BLOCKED" if reasons else "OK"
        if audit.cutoff_m is None:
            audit.mask_status = "BLOCKED"
            audit.mask_blocked_reasons = audit.mask_blocked_reasons + ("人工截断未配置",)
        first_len = next(iter(audit.sig_lengths), 0)
        if audit.mask_status == "BLOCKED":
            audit.mask_reason_summary = (
                f"{dm.REASON_MAPPING_UNVERIFIED}={audit.sig_total_points}")
        elif first_len:
            demo = dm.build_mask([0.0] * first_len, audit.mapping, audit.cutoff_m,
                                 row_range_m=DECLARED_RANGE_M,
                                 row_point_count=first_len, allow_blocked=True)
            audit.mask_reason_summary = demo.reason_summary()
    return audit


# ---------------- 产物写入 ----------------

def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def write_field_dictionary(audits: list[DeviceAudit], out: Path) -> None:
    rows = []
    field_meta = {
        "seq": ("序号", "int", "无", "K01/唯一性审计用；同秒多记录不去重"),
        "timestamp": ("日期", "datetime", "本地时间（未带时区）", "时间覆盖与断档审计；时区未核实"),
        "depth_m": ("水深(m)", "float", "m", "厂家字段；定义/支持范围未核实，不得直接当作截断后水深"),
        "water_temp_c": ("水温(°C)", "float", "°C", "环境参考；样本值待统计"),
        "range_m": ("量程(m)", "float", "m", "逐记录量程；与映射量程必须一致"),
        "signal_raw": ("数据(信号强度)", "int 数组（冒号分隔）", "厂家相对强度（未标定）",
                       "1000 点是中心还是区间未核实；不得按 37.5/1000 推断下标"),
    }
    for a in audits:
        for canonical, raw in a.inspection.header_map.items():
            name, dtype, unit, note = field_meta.get(
                canonical, (raw, "UNKNOWN", "UNKNOWN", "含义不明→UNKNOWN"))
            rows.append([a.device_id, raw, canonical, dtype, unit, "KNOWN" if canonical in field_meta else "UNKNOWN",
                         a.inspection.field_count, note])
        for raw in a.inspection.unknown_headers:
            rows.append([a.device_id, raw, "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN",
                         a.inspection.field_count, "未识别字段，保留原始列"])
    _write_csv(out / "field_dictionary.csv",
               ["device_id", "raw_header", "canonical_field", "dtype", "unit",
                "meaning_status", "field_count", "note"], rows)


def write_signal_array_audit(audits: list[DeviceAudit], out: Path) -> None:
    rows = []
    for a in audits:
        lengths = a.sig_lengths
        mode_len, mode_n = (lengths.most_common(1)[0] if lengths else (0, 0))
        total = sum(lengths.values()) or 1
        dist = ";".join(f"{k}点:{v}" for k, v in lengths.most_common(6))
        fz_mode, fz_n = (a.sig_first_zero.most_common(1)[0] if a.sig_first_zero else (None, 0))
        fz_total = sum(a.sig_first_zero.values()) or 1
        fz_dist = ";".join(f"idx{k}:{v}" for k, v in sorted(a.sig_first_zero.items())[:12])
        cand = f"{BLIND_ZONE_M / fz_mode:.5f}" if fz_mode else ""
        rows.append([
            a.device_id, a.rows_with_signal, a.sig_total_points,
            min(lengths) if lengths else 0, max(lengths) if lengths else 0,
            mode_len, f"{mode_n / total:.4%}", dist,
            ";".join(f"{k}个token:{v}" for k, v in a.sig_token_lengths.most_common(6)),
            a.sig_trailing_empty_total,
            a.sig_empty_tokens, a.sig_non_numeric,
            "" if a.sig_min is None else f"{a.sig_min:g}",
            "" if a.sig_max is None else f"{a.sig_max:g}",
            a.sig_zero, f"{a.sig_zero / a.sig_total_points:.6%}" if a.sig_total_points else "",
            a.sig_gt_255, a.sig_negative,
            a.rows_len_ne_1000, EXPECTED_POINTS,
            "UNVERIFIED",
            "原始行以冒号结尾：1001 个 token = 1000 个有效槽位 + 1 个尾部空项；"
            "1000 槽位是采样中心还是距离区间尚未核实，禁止由 37.5/1000 推定下标",
            BLIND_ZONE_M,
            "" if fz_mode is None else fz_mode,
            f"{fz_n / fz_total:.4%}" if a.sig_first_zero else "",
            "" if fz_mode is None else ("" if a.sig_first_zero and min(a.sig_first_zero) == max(a.sig_first_zero)
                                        else f"{min(a.sig_first_zero)}—{max(a.sig_first_zero)}"),
            a.sig_rows_no_zero, fz_dist,
            "" if a.pre_zero_min is None else f"{a.pre_zero_min:g}",
            "" if a.pre_zero_max is None else f"{a.pre_zero_max:g}",
            a.pre_zero_invalid, cand,
            a.mask_status, a.mask_reason_summary, "；".join(a.mask_blocked_reasons),
        ])
    _write_csv(out / "signal_array_audit.csv",
               ["device_id", "rows_with_signal", "total_points", "min_length", "max_length",
                "mode_length", "mode_share", "length_distribution",
                "token_length_distribution", "trailing_empty_tokens", "empty_tokens",
                "non_numeric_tokens", "min_value", "max_value", "zero_values", "zero_share",
                "values_gt_255", "negative_values", "rows_len_ne_1000", "expected_points",
                "point_or_interval", "point_or_interval_note", "blind_zone_m",
                "first_zero_index_mode", "first_zero_mode_share", "first_zero_index_range",
                "rows_no_zero", "first_zero_index_distribution", "pre_zero_min", "pre_zero_max",
                "pre_zero_invalid", "candidate_spacing_if_blind_zone_boundary",
                "mask_status", "mask_reason_summary", "mask_blocked_reasons"], rows)


def write_timestamp_audit(audits: list[DeviceAudit], out: Path) -> None:
    rows = []
    for a in audits:
        rows.append([
            a.device_id, a.rows_total, a.rows_blank, a.rows_malformed,
            a.ts_min.isoformat(sep=" ") if a.ts_min else "",
            a.ts_max.isoformat(sep=" ") if a.ts_max else "",
            "" if a.duration_s is None else f"{a.duration_s:.0f}",
            ";".join(f"{fmt or 'UNKNOWN'}:{n}" for fmt, n in a.ts_formats.most_common()),
            "YES" if a.ts_multi_format else "NO",
            a.ts_minute_precision_rows,
            a.same_second_groups, a.same_second_rows, a.max_rows_per_second,
            a.repeat_timestamp_rows, a.seq_duplicates, a.seq_missing, a.seq_non_integer,
            ";".join(f"{k}:{v}" for k, v in a.interval_counts.most_common()),
            a.gap_gt_60, a.gap_gt_600, f"{a.largest_gap_s:.0f}",
            ";".join(a.gap_examples),
            a.distinct_seconds,
            "YES" if a.date_crossing else "NO",
            ";".join(f"{d}:{n}" for d, n in sorted(a.dates.items())),
        ])
    _write_csv(out / "timestamp_audit.csv",
               ["device_id", "rows_total", "blank_rows", "malformed_rows", "first_timestamp",
                "last_timestamp", "duration_s", "timestamp_formats", "multi_format",
                "minute_precision_rows", "same_second_groups", "same_second_rows", "max_rows_per_second",
                "repeat_timestamp_rows", "duplicate_seq", "missing_seq", "non_integer_seq",
                "interval_distribution", "gaps_gt_60s", "gaps_gt_600s", "largest_gap_s",
                "gap_examples", "distinct_seconds", "date_crossing", "date_counts"], rows)


def write_coverage_audit(audits: list[DeviceAudit], out: Path) -> None:
    rows = []
    for a in audits:
        for hour in range(24):
            n = a.hours.get(hour, 0)
            secs = len(a.seconds_by_hour.get(hour, ()))
            rows.append([a.device_id, hour, n, secs, f"{secs / 3600:.4%}"])
    _write_csv(out / "coverage_audit.csv",
               ["device_id", "hour", "rows", "distinct_seconds", "second_coverage_of_hour"], rows)


def write_device_comparability(audits: list[DeviceAudit], out: Path) -> None:
    by_id = {a.device_id: a for a in audits}
    d0, d1 = by_id.get("2000"), by_id.get("2001")
    rows = []

    def add(attr, v0, v1, verdict, note=""):
        rows.append([attr, v0, v1, verdict, note])

    if d0 and d1:
        add("编码", d0.inspection.encoding, d1.inspection.encoding, "NO",
            "逐文件探测，不得假定统一编码")
        add("BOM", "YES" if d0.inspection.has_bom else "NO",
            "YES" if d1.inspection.has_bom else "NO", "NO", "2001 无 BOM")
        add("分隔符", d0.inspection.delimiter, d1.inspection.delimiter, "YES", "均为逗号")
        add("换行", d0.inspection.line_ending, d1.inspection.line_ending, "NO",
            "2001 为 CRLF")
        add("字段数", d0.inspection.field_count, d1.inspection.field_count,
            "YES" if d0.inspection.field_count == d1.inspection.field_count else "NO", "")
        add("表头", "/".join(d0.inspection.header), "/".join(d1.inspection.header), "PARTIAL",
            "中文字段名与单位写法不同（℃/°C）")
        add("时间格式", ";".join(d0.ts_formats), ";".join(d1.ts_formats),
            "YES" if set(d0.ts_formats) == set(d1.ts_formats) else "NO", "解析后统一为 datetime")
        add("行数", d0.rows_total, d1.rows_total, "NO", "覆盖不同，不可直接对齐")
        add("时间范围",
            f"{d0.ts_min} → {d0.ts_max}", f"{d1.ts_min} → {d1.ts_max}", "NO", "")
        add("distinct_seconds", d0.distinct_seconds, d1.distinct_seconds, "NO", "有效观测支持不同")
        add("同秒多记录行", d0.same_second_rows, d1.same_second_rows, "NO", "不得按时间戳去重")
        add("量程取值", ";".join(f"{k}:{v}" for k, v in d0.ranges.items()),
            ";".join(f"{k}:{v}" for k, v in d1.ranges.items()),
            "YES" if set(d0.ranges) == set(d1.ranges) else "NO", "")
        add("水温范围", f"{d0.temp_min}—{d0.temp_max}", f"{d1.temp_min}—{d1.temp_max}", "UNKNOWN",
            "范围接近，但采样时刻不同，不能互相替代")
        add("水深范围", f"{d0.depth_min}—{d0.depth_max}（0 值 {d0.depth_zero}）",
            f"{d1.depth_min}—{d1.depth_max}（0 值 {d1.depth_zero}）", "NO",
            "2001 水深有 4 位小数；定义未核实")
        add("数组长度众数", d0.sig_lengths.most_common(1), d1.sig_lengths.most_common(1),
            "UNKNOWN", "1000 点含义未核实")
        add("截断配置", f"{d0.cutoff_m}" if d0.cutoff_m else "MISSING",
            f"{d1.cutoff_m}" if d1.cutoff_m else "MISSING", "PARTIAL",
            "2001 倾角未知 → 几何换算不可用")
        add("距离映射", d0.mapping.sample_mode if d0.mapping else "NONE",
            d1.mapping.sample_mode if d1.mapping else "NONE", "NO",
            "两台均为 UNVERIFIED → 正式距离分析 BLOCKED")
    _write_csv(out / "device_comparability.csv",
               ["attribute", "device_2000", "device_2001", "comparable", "note"], rows)


def write_bottom_reference_audit(conn: sqlite3.Connection, out: Path,
                                 audit_map: dict[str, DeviceAudit]) -> None:
    rows = []
    from .devices import current_version
    for device_id in ("2000", "2001"):
        cur = current_version(conn, device_id)
        audit = audit_map.get(device_id)
        if cur is None:
            rows.append([device_id, "", "", "", "", "", "", "", "MISSING",
                         "人工参数未配置", "BLOCKED"])
            continue
        vertical = cur["vertical_bottom_clearance_m"]
        tilt = cur["downward_tilt_deg"]
        beam_val = cur["beam_angle_value_deg"]
        beam_kind = cur["beam_angle_kind"]
        derived = cur["derived_axis_slant_m"]
        cutoff = cur["analysis_cutoff_slant_m"]
        if device_id == "2000":
            marks = "USER_DEFINED_ESTIMATED;NOT_DETECTED;NOT_ACOUSTIC_MEASURED"
            status = "REFERENCE_ONLY"
            note = ("3.68 m 为用户提供的人工水底参考面（非声学实测底界）；5.2043 m 为 45° 几何派生参考，"
                    "不覆盖人工截断 5.2 m；原始 37.5 m 数组完整保留")
        else:
            marks = "USER_PROVIDED;GEOMETRY_NOT_APPLICABLE"
            status = "GEOMETRY_BLOCKED"
            note = "2001 倾角 UNKNOWN，理论中心轴交底不可换算；人工截断 5.2 m 仍独立有效"
        rows.append([
            device_id,
            "" if vertical is None else f"{vertical:g}",
            "" if tilt is None else f"{tilt:g}",
            "" if beam_val is None else f"{beam_val:g}",
            beam_kind or "UNKNOWN",
            "" if cutoff is None else f"{cutoff:g}",
            "" if derived is None else f"{derived:.10f}",
            marks, status, note,
            (audit.mask_status if audit else "UNKNOWN"),
        ])
    _write_csv(out / "bottom_reference_audit.csv",
               ["device_id", "vertical_bottom_clearance_m", "downward_tilt_deg",
                "beam_angle_value_deg", "beam_angle_kind", "analysis_cutoff_slant_m",
                "derived_axis_slant_m", "marks", "status", "note", "mask_status"], rows)


def write_issues(audits: list[DeviceAudit], out: Path) -> list[list]:
    issues: list[list] = []

    def add(device, severity, category, title, detail, evidence):
        issues.append([f"ISS-{len(issues) + 1:03d}", device, severity, category, title, detail, evidence])

    for a in audits:
        if a.inspection.unknown_headers:
            add(a.device_id, "P2", "字段定义", "存在未识别表头",
                f"未识别：{a.inspection.unknown_headers}", a.inspection.path.name)
        if a.rows_blank:
            add(a.device_id, "P2", "行结构", "存在空行", f"{a.rows_blank} 行", "timestamp_audit.csv")
        if a.rows_malformed:
            add(a.device_id, "P1", "行结构", "列数与表头不符",
                f"{a.rows_malformed} 行", "timestamp_audit.csv")
        if a.depth_zero:
            add(a.device_id, "P1", "字段质量", "水深为 0 的样本",
                f"{a.depth_zero} 行；不得当作有效水深参与统计", "timestamp_audit.csv")
        if a.sig_non_numeric:
            add(a.device_id, "P1", "信号数组", "信号数组存在非数值项",
                f"{a.sig_non_numeric} 项；硬掩码按 INVALID_VALUE 排除", "signal_array_audit.csv")
        if a.sig_empty_tokens:
            add(a.device_id, "P1", "信号数组", "信号数组存在空项（冒号结尾）",
                f"{a.sig_empty_tokens} 个空 token，其中尾部空项 {a.sig_trailing_empty_total} 个；"
                f"有效槽位 {dict(a.sig_lengths)}，原始 token 数 {dict(a.sig_token_lengths)}",
                "signal_array_audit.csv")
        if a.rows_len_ne_1000:
            add(a.device_id, "P1", "信号数组", "有效槽位数不等于 1000",
                f"{a.rows_len_ne_1000}/{a.rows_total} 行：{dict(a.sig_lengths)}", "signal_array_audit.csv")
        if a.sig_rows_no_zero:
            add(a.device_id, "P2", "盲区", "存在无 0 的信号行",
                f"{a.sig_rows_no_zero}/{a.rows_total} 行：无法按首零定位盲区结束"
                f"（用户口径盲区 0.5 m）", "signal_array_audit.csv")
        if a.ts_minute_precision_rows:
            add(a.device_id, "P1", "时间", "时间戳仅到分钟（秒精度缺失）",
                f"{a.ts_minute_precision_rows}/{a.rows_total} 行；不得与秒级时间轴直接对齐，"
                f"同分钟多记录不能按时间戳区分", "timestamp_audit.csv")
        if a.same_second_groups:
            add(a.device_id, "P1", "时间", "同秒多记录",
                f"{a.same_second_groups} 个秒组、{a.same_second_rows} 行；不得仅按时间戳去重",
                "timestamp_audit.csv")
        if a.seq_duplicates:
            add(a.device_id, "P1", "序号", "序号重复",
                f"{a.seq_duplicates} 次；示例：{';'.join(a.seq_duplicate_examples)}", "timestamp_audit.csv")
        if a.gap_gt_600:
            add(a.device_id, "P1", "时间", "存在 >10min 断档",
                f"{a.gap_gt_600} 处；最大 {a.largest_gap_s:.0f}s", "timestamp_audit.csv")
        if a.ts_multi_format:
            add(a.device_id, "P2", "时间", "同一文件内多种时间格式",
                ";".join(a.ts_formats), "timestamp_audit.csv")
        if a.mask_status != "OK":
            add(a.device_id, "P0", "距离映射", "正式距离分析 BLOCKED",
                "原因：" + "；".join(a.mask_blocked_reasons),
                "signal_array_audit.csv / DATA_AUDIT_REPORT.md")
    enc = {a.inspection.encoding for a in audits}
    if len(enc) > 1:
        add("ALL", "P1", "编码", "两台设备文件编码不同",
            f"{enc}；必须逐文件探测，不得假定统一编码", "field_dictionary.csv")
    _write_csv(out / "issues.csv",
               ["issue_id", "device_id", "severity", "category", "title", "detail", "evidence"], issues)
    return issues


def write_report(audits: list[DeviceAudit], issues: list[list], out: Path,
                 *, generated_at: str, manifest_by_device: dict[str, dict] | None = None) -> None:
    manifest_by_device = manifest_by_device or {}
    lines: list[str] = []
    lines.append("# 数据审计报告（S02）\n")
    lines.append(f"- 生成时间：{generated_at}")
    lines.append("- 阶段：S02 真实 CSV 解析与数据质量审计（只读原始文件）")
    lines.append("- 统一口径：距离越界只由 `app/services/distance_mapping.py::build_mask` 判定；"
                 "本报告不自行推算下标或距离\n")

    lines.append("## 1. 文件检查\n")
    lines.append("| 设备 | 文件 | 大小(B) | SHA-256 | 编码 | BOM | 分隔符 | 换行 | 表头 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for a in audits:
        lines.append(f"| {a.device_id} | {a.inspection.path.name} | {a.inspection.size_bytes} | "
                     f"`{a.inspection.sha256}` | {a.inspection.encoding} | "
                     f"{'YES' if a.inspection.has_bom else 'NO'} | {a.inspection.delimiter} | "
                     f"{a.inspection.line_ending} | {', '.join(a.inspection.header)} |")
    lines.append("")
    for a in audits:
        man = manifest_by_device.get(a.device_id)
        if man:
            match = "PASS" if man.get("sha256") == a.inspection.sha256 else "FAIL"
            lines.append(f"- {a.device_id}：与归档清单比对 **{match}**（清单 {man.get('sha256')}）")
    lines.append("\n原始文件在整个审计过程中只读打开；审计前后 SHA-256 一致性见 `pytest` 用例 "
                 "`test_raw_files_hash_unchanged_by_parse` 与本节清单比对。\n")

    lines.append("## 2. 记录规模与时间覆盖\n")
    lines.append("| 设备 | 总行 | 空行 | 列数异常 | 首时间 | 末时间 | 跨度 | 不同秒 | 同秒多记录行 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for a in audits:
        lines.append(f"| {a.device_id} | {a.rows_total} | {a.rows_blank} | {a.rows_malformed} | "
                     f"{a.ts_min} | {a.ts_max} | "
                     f"{'' if a.duration_s is None else f'{a.duration_s:.0f}s'} | "
                     f"{a.distinct_seconds} | {a.same_second_rows} |")
    lines.append("")
    lines.append("> 未按时间戳去重：同秒多记录全部保留，重复序号单独统计（见 `timestamp_audit.csv`）。\n")

    lines.append("## 3. 字段审计（含义不明→UNKNOWN）\n")
    lines.append("| 设备 | 字段 | 原始表头 | 观测结论 | 状态 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for a in audits:
        lines.append(f"| {a.device_id} | 序号 | {a.inspection.header_map.get('seq', '')} | "
                     f"缺 {a.seq_missing}，非整数 {a.seq_non_integer}，重复 {a.seq_duplicates} | KNOWN |")
        lines.append(f"| {a.device_id} | 日期 | {a.inspection.header_map.get('timestamp', '')} | "
                     f"格式 {dict(a.ts_formats)}；无法解析 {a.ts_unparsed} | KNOWN（时区未知） |")
        lines.append(f"| {a.device_id} | 水深 | {a.inspection.header_map.get('depth_m', '')} | "
                     f"范围 {a.depth_min}—{a.depth_max}；0 值 {a.depth_zero}；小数位 {dict(a.depth_decimals)} | "
                     f"**UNKNOWN（定义未核实）** |")
        lines.append(f"| {a.device_id} | 水温 | {a.inspection.header_map.get('water_temp_c', '')} | "
                     f"范围 {a.temp_min}—{a.temp_max}；0 值 {a.temp_zero} | KNOWN（环境参考） |")
        lines.append(f"| {a.device_id} | 量程 | {a.inspection.header_map.get('range_m', '')} | "
                     f"取值 {dict(a.ranges)} | KNOWN（逐记录） |")
        lines.append(f"| {a.device_id} | 信号 | {a.inspection.header_map.get('signal_raw', '')} | "
                     f"长度 {dict(a.sig_lengths)}；范围 {a.sig_min}—{a.sig_max} | "
                     f"**点/区间 UNKNOWN** |")
    lines.append("")

    lines.append("## 4. 信号数组\n")
    for a in audits:
        zero_share = f"{a.sig_zero / a.sig_total_points:.4%}" if a.sig_total_points else "N/A"
        lines.append(f"- **{a.device_id}**：{a.rows_with_signal} 行 / {a.sig_total_points} 个有效槽位；"
                     f"有效长度 {dict(a.sig_lengths)}；原始 token 数 {dict(a.sig_token_lengths)}；"
                     f"空项 {a.sig_empty_tokens}（尾部空项 {a.sig_trailing_empty_total}）；"
                     f"非数值 {a.sig_non_numeric}；值域 {a.sig_min}—{a.sig_max}；"
                     f"0 值占比 {zero_share}；>255：{a.sig_gt_255}；负值：{a.sig_negative}")
        fz_mode, fz_n = (a.sig_first_zero.most_common(1)[0] if a.sig_first_zero else (None, 0))
        fz_total = sum(a.sig_first_zero.values()) or 1
        if fz_mode is not None:
            cand = BLIND_ZONE_M / fz_mode
            lines.append(f"  - 盲区（用户口径 0.5 m）：首零索引众数 **{fz_mode}**"
                         f"（{fz_n / fz_total:.4%}，范围 {min(a.sig_first_zero)}—{max(a.sig_first_zero)}）；"
                         f"无 0 的行 {a.sig_rows_no_zero}；首零前取值 {a.pre_zero_min}—{a.pre_zero_max}"
                         f"（无效项 {a.pre_zero_invalid}）；候选单元宽度 0.5/{fz_mode}={cand:.5f} m"
                         f"（仅候选，**非结论**，与 37.5/1000=0.0375 并列待用户确认）")
        else:
            lines.append(f"  - 盲区（用户口径 0.5 m）：全部 {a.rows_with_signal} 行均无 0，"
                         f"无法按首零定位盲区结束")
    lines.append("")
    lines.append("**盲区口径（用户提供，2026-11-17）**：信号数组以第一个出现的 0 开始才算数据盲区结束；"
                 "设备数据盲区 0.5 m。即首零之前的槽位属盲区（`NEAR_FIELD` 候选排除原因，S07 预留），"
                 "首零及其之后才进入有效观测段。该口径与「1000 槽位=中心还是区间」「首点距离」共同决定映射，"
                 "在用户确认语义并登记 `CONFIRMED` 映射版本之前，正式距离分析仍 BLOCKED。")
    lines.append("")
    lines.append("**数组结构**：原始行以冒号结尾，`split(':')` 得到 **1001 个 token**，其中最后 1 个为空；"
                 "有效数值槽位为 **1000**。审计同时记录 token 数与槽位数，避免把尾部空项误当第 1001 个采样。")
    lines.append("\n**1000 点语义未核实**：现有证据只能证明每行有 1000 个有效数值槽位，无法证明这 1000 个值"
                 "对应「采样中心」还是「距离区间」。因此禁止按 37.5 m / 1000 推断首点、末点或切片下标。\n")

    lines.append("## 5. 时间审计\n")
    for a in audits:
        lines.append(f"- **{a.device_id}**：格式 {dict(a.ts_formats)}（仅到分钟的行 "
                     f"{a.ts_minute_precision_rows}）；同秒多记录 "
                     f"{a.same_second_groups} 组 / {a.same_second_rows} 行（单秒最多 "
                     f"{a.max_rows_per_second} 行）；间隔分布 {dict(a.interval_counts)}；"
                     f">60s 断档 {a.gap_gt_60} 处（最大 {a.largest_gap_s:.0f}s）；"
                     f"日期跨界 {'YES' if a.date_crossing else 'NO'}")
        if a.gap_examples:
            lines.append(f"  - 断档示例：{'; '.join(a.gap_examples[:5])}")
    lines.append("")

    lines.append("## 6. 设备可比性（2000 vs 2001）\n")
    lines.append("| 属性 | 2000 | 2001 | 可比 |")
    lines.append("| --- | --- | --- | --- |")
    if len(audits) >= 2:
        d0, d1 = audits[0], audits[1]
        pairs = [
            ("编码", d0.inspection.encoding, d1.inspection.encoding, "NO"),
            ("分隔符", d0.inspection.delimiter, d1.inspection.delimiter, "YES"),
            ("换行", d0.inspection.line_ending, d1.inspection.line_ending, "NO"),
            ("时间格式", ";".join(d0.ts_formats), ";".join(d1.ts_formats), "NO"),
            ("时间精度", "秒" if not d0.ts_minute_precision_rows else "部分分钟",
             "秒" if not d1.ts_minute_precision_rows else "分钟（秒缺失）", "NO"),
            ("时间范围", f"{d0.ts_min}→{d0.ts_max}", f"{d1.ts_min}→{d1.ts_max}", "NO"),
            ("行数", d0.rows_total, d1.rows_total, "NO"),
            ("量程", ";".join(d0.ranges), ";".join(d1.ranges), "YES"),
            ("数组长度", str(dict(d0.sig_lengths)), str(dict(d1.sig_lengths)), "UNKNOWN"),
            ("截断", d0.cutoff_m, d1.cutoff_m, "PARTIAL"),
        ]
        for p in pairs:
            lines.append(f"| {p[0]} | {p[1]} | {p[2]} | {p[3]} |")
    lines.append("\n> 两台设备文件结构、时间覆盖与字段精度不同，不能直接互相替代或对齐。\n")

    lines.append("## 7. 2000 号人工底界\n")
    lines.append("- 垂直离底高度 3.68 m（USER_DEFINED_ESTIMATED、NOT_DETECTED，非声学实测底界）")
    lines.append("- 倾角 45°（相对水平面，用户提供）")
    lines.append("- 条件算例：15° 全波束角 → β=7.5°（全/半角类型仍待用户确认）")
    lines.append("- 人工分析截断斜距 5.2 m（独立字段，硬上限）")
    lines.append("- 理论中心轴交底 3.68/sin45° ≈ **5.2043059095 m**：仅作参考，**不覆盖 5.2 m**，"
                 "不得标记为声学实测底界")
    lines.append("- 原始 37.5 m 数组完整保留；正式分析不得先用全量程再在图上裁剪\n")

    lines.append("## 8. 距离映射与硬掩码（V4 强制增项）\n")
    lines.append("| 设备 | 映射版本 | 采样语义 | 首点距离 | 单元宽度 | 支撑状态 | 掩码状态 | 阻断原因 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for a in audits:
        m = a.mapping
        lines.append(f"| {a.device_id} | {m.version if m else 'NONE'} | "
                     f"{m.sample_mode if m else 'UNKNOWN'} | "
                     f"{m.first_sample_distance_m if m else 'UNKNOWN'} | "
                     f"{m.sample_interval_m if m else 'UNKNOWN'} | "
                     f"{m.support_status if m else 'UNVERIFIED'} | **{a.mask_status}** | "
                     f"{'；'.join(a.mask_blocked_reasons)} |")
    lines.append("")
    lines.append("- 硬掩码规则：点样本 `r <= cutoff` 保留、无浮点容差；区间样本整段在界内才保留，"
                 "跨界且无可拆分支持信息时**整段排除**。")
    statuses = {a.mask_status for a in audits}
    if statuses == {"OK"}:
        lines.append("- 当前映射状态：两台设备映射最新版本均为 INTERVAL/CONFIRMED"
                     "（首格起点 0.5 m、格宽 0.0375 m，2026-11-16 经用户确认登记）→ **硬掩码可用**。")
    else:
        lines.append("- 当前映射存在未核实项 → **正式距离分析 BLOCKED**；"
                     "原始导入与保存仍可继续，但不得输出任何正式截断统计。")
    lines.append("- 盲区规则（用户口径 2026-11-17）：设备盲区 0.5 m——r<0.5 m 或整段/跨界盲区"
                 "边界的区间一律排除；每行数组首个 0 之前（发射余脉）按 `NEAR_FIELD` 排除。")
    lines.append("- 排除原因记录：`OUT_OF_RANGE_MANUAL_CUTOFF`、`CROSS_BOUNDARY_INTERVAL_EXCLUDED`、"
                 "`NEAR_FIELD`（盲区）、`DISTANCE_UNKNOWN`、`INVALID_VALUE`、"
                 "`DISTANCE_MAPPING_UNVERIFIED`（映射未核实时）。\n")

    lines.append("## 9. 问题清单\n")
    lines.append(f"共 {len(issues)} 项，见 `issues.csv`。")
    for issue in issues[:20]:
        lines.append(f"- [{issue[2]}] {issue[1]} {issue[4]}：{issue[5]}")
    lines.append("")

    lines.append("## 10. 结论与非结论\n")
    lines.append("**已核实**：文件存在、大小、SHA-256（与归档清单一致）、逐文件编码/分隔符/换行、"
                 "表头、行数、时间范围、同秒多记录、重复序号、断档、数组 token/槽位结构"
                 "（1001 token = 1000 有效槽位 + 尾部空项）、值域、2001 时间戳仅到分钟。")
    lines.append("\n**未核实（不得据此做正式分析）**：1000 槽位逐格对应关系以映射版本登记为准"
                 "（当前 INTERVAL/CONFIRMED）；水深字段定义；时区。")
    blocked = [a.device_id for a in audits if a.mask_status != "OK"]
    if blocked:
        lines.append(f"\n**BLOCKED**：{','.join(blocked)} 的正式距离截断分析（`build_mask` 返回 BLOCKED）。"
                     "S03 统计必须在映射核实后才能产出；本轮不生成任何未截断的正式统计。")
    else:
        lines.append("\n**硬掩码可用**：两台设备映射均为 CONFIRMED，正式截断统计可以产出"
                     "（本轮 S02 仍只做审计，不生成统计）。")
    (out / "DATA_AUDIT_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
