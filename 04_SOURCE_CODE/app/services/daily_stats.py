# -*- coding: utf-8 -*-
"""S03 每日统计引擎。

硬契约（V4 03 第六章 + 09 K07—K09/K14—K18/K25/K40）：
1. 所有样本只能来自 S02 的统一硬掩码 `build_mask(..., allow_blocked=False)`；
   本模块不实现任何独立切片/距离换算，不存在「先全量程统计再修正」。
2. 每个统计任务绑定观测时刻适用的参数版本与距离映射版本（见 analysis_runs.params_snapshot_json）。
3. 0/NA 分开：区内有效观测存在但无候选事件 → 候选事件数 = 0；完全没有区内有效观测 →
   所有依赖样本的指标 = NULL(NA)，绝不填 0；记录数等计数量保持真实计数。
4. 单台缺少有效截断/映射 → 抛 StatisticsBlocked，由上层写 BLOCKED 行，不牵连其他设备。
5. 每个指标都有明确的分子、分母、单位与 NA 规则（`METRIC_DEFINITIONS` / CSV 工件）。
"""
from __future__ import annotations

import csv
import json
import math
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, Sequence

from ..db import _now
from . import devices as device_service
from . import distance_mapping as dm
from .csv_parser import FileInspection, ParsedRow, inspect_file, iter_rows

ALGORITHM_VERSION = "DAILY_STATS_V1"
CANDIDATE_EVENT_ALGORITHM = "CANDIDATE_RUN_V1(threshold>=200,min_bins=3,masked_indices_contiguous)"
DEFAULT_EVENT_THRESHOLD = 200.0
DEFAULT_EVENT_MIN_BINS = 3
PLANNED_WINDOW_S = 86400          # 日历日窗口（分母默认口径，可显式覆盖）
MAX_DISTINCT_FOR_EXACT_QUANTILE = 4096

STATUS_COMPLETE = "COMPLETE"
STATUS_PARTIAL = "PARTIAL"
STATUS_MISSING = "MISSING"
STATUS_QC_FAILED = "QC_FAILED"
STATUS_UPLOADED_LATE = "UPLOADED_LATE"
STATUS_REPROCESSED = "REPROCESSED"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_BLOCKED = "BLOCKED"
ALL_STATUSES = (STATUS_COMPLETE, STATUS_PARTIAL, STATUS_MISSING, STATUS_QC_FAILED,
                STATUS_UPLOADED_LATE, STATUS_REPROCESSED, STATUS_UNKNOWN, STATUS_BLOCKED)

UPLOAD_NORMAL = "NORMAL"
UPLOAD_LATE = "UPLOADED_LATE"
UPLOAD_REPROCESSED = "REPROCESSED"
UPLOAD_BLOCKED = "BLOCKED"


class StatisticsBlocked(Exception):
    """单台前置条件不满足；正式统计不得开始，也不得用全量程替代。"""

    def __init__(self, device_id: str, reasons: Sequence[str]):
        self.device_id = device_id
        self.reasons = list(reasons)
        super().__init__(f"{device_id} 每日统计 BLOCKED：" + "；".join(self.reasons))


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    numerator: str
    denominator: str
    unit: str
    na_rule: str
    source: str = "build_mask(allow_blocked=False)"


METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition("raw_records", "当日文件数据行数（含解析异常行）", "—（计数量）", "条",
                     "文件未上传=NA；上传后为真实计数，可为 0", "csv_parser.iter_rows"),
    MetricDefinition("valid_records", "时间戳可解析且 build_mask 后至少保留 1 个区内样本的行数", "—（计数量）", "条",
                     "文件未上传=NA", "build_mask.kept_count>0"),
    MetricDefinition("invalid_records", "解析错误行（空行/列数不符/字段非数值等）", "—（计数量）", "条",
                     "文件未上传=NA", "ParsedRow.errors"),
    MetricDefinition("fully_masked_records", "无解析错误但掩码后 0 个区内样本的行", "—（计数量）", "条",
                     "文件未上传=NA", "build_mask.kept_count==0"),
    MetricDefinition("signal_slots_per_record", "单条记录有效信号槽位众数（尾部空 token 不计）", "—（结构量）", "点/条",
                     "文件未上传=NA", "ParsedRow.effective_signal_len"),
    MetricDefinition("raw_signal_slots", "Σ 每条记录有效信号槽位", "—（计数量）", "点",
                     "文件未上传=NA", "ParsedRow.effective_signal_len"),
    MetricDefinition("kept_samples", "Σ build_mask.kept_count", "—（计数量）", "点",
                     "文件未上传=NA；BLOCKED 设备不得统计", "build_mask"),
    MetricDefinition("excluded_samples", "Σ build_mask.excluded_total", "—（计数量）", "点",
                     "文件未上传=NA", "build_mask"),
    MetricDefinition("near_field_excluded_samples", "掩码原因 NEAR_FIELD 的样本数", "—（计数量）", "点",
                     "文件未上传=NA", "build_mask.excluded_counts"),
    MetricDefinition("bottom_excluded_samples", "掩码原因 BOTTOM_INTERFERENCE 的样本数", "—（计数量）", "点",
                     "S07 启用自动探底前恒为 0；文件未上传=NA", "build_mask.excluded_counts"),
    MetricDefinition("valid_observation_duration_s", "含至少 1 条有效记录的去重时间戳格数 × 时间戳分辨率", "—（时长量）", "s",
                     "文件未上传=NA；上限截断到 planned_window_s", "ValidRow.timestamp bins"),
    MetricDefinition("observation_span_s", "首末有效记录时间跨度 + 1 个时间戳格", "—（时长量）", "s",
                     "文件未上传=NA", "min/max timestamp"),
    MetricDefinition("planned_window_s", "日历日窗口长度", "—（常量）", "s",
                     "恒为 86400（可显式覆盖并留痕）", "定义常量"),
    MetricDefinition("coverage_ratio", "valid_observation_duration_s", "planned_window_s", "比例 0—1",
                     "文件未上传或无区内有效观测=NA（时长 0 不等于覆盖率 0）", "两个时长字段"),
    MetricDefinition("valid_record_ratio", "valid_records", "raw_records", "比例 0—1",
                     "raw_records=0 或文件未上传=NA", "记录计数"),
    MetricDefinition("signal_mean", "Σ kept_values", "kept_samples", "强度单位（原始 0—255）",
                     "kept_samples=0 → NA，禁止填 0", "build_mask.kept_values"),
    MetricDefinition("signal_stddev", "Σ(kept_value−mean)² / kept_samples 的平方根（总体标准差）", "kept_samples", "强度单位",
                     "kept_samples=0 → NA", "build_mask.kept_values"),
    MetricDefinition("signal_median", "kept_values 的经验 0.5 分位数（线性插值）", "kept_samples", "强度单位",
                     "kept_samples=0 → NA", "build_mask.kept_values"),
    MetricDefinition("signal_p10/p25/p75/p90/p95/p99", "kept_values 的对应经验分位数", "kept_samples", "强度单位",
                     "kept_samples=0 → NA", "build_mask.kept_values"),
    MetricDefinition("candidate_events", "区内相邻有效槽位连续 ≥3 且值 ≥200 的极大段数", "—（计数量）", "次",
                     "区内存在有效观测但无候选 → 0；无区内有效观测 → NA", "CANDIDATE_RUN_V1"),
    MetricDefinition("candidate_event_rate_per_hour", "candidate_events", "valid_observation_duration_s / 3600", "次/小时",
                     "有效观测时长=0 或候选事件=NA → NA", "事件数与时长"),
    MetricDefinition("water_temp_mean/min/max", "有效记录的水温值", "有水温的有效记录数", "°C",
                     "无有效水温 → NA", "ParsedRow.water_temp_c"),
    MetricDefinition("missing_intervals_json", "有效记录时间戳格之间的缺口（起、止、时长）", "—（诊断量）", "s",
                     "文件未上传=NA", "去重时间戳"),
    MetricDefinition("excluded_by_reason_json", "build_mask 逐原因排除样本数", "—（诊断量）", "点",
                     "文件未上传=NA", "build_mask.excluded_counts"),
    MetricDefinition("hourly_activity_json", "按时辰统计的有效记录/候选事件/区内样本", "—（诊断量）", "条/次/点",
                     "文件未上传=NA", "有效记录时间戳"),
    MetricDefinition("status", "缺测/质检状态（8 枚举 + BLOCKED）", "—（状态量）", "枚举",
                     "不允许用 0 代替缺测", "状态判定规则"),
)


def write_metric_definitions_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric_name", "numerator", "denominator", "unit", "na_rule", "source"])
        for m in METRIC_DEFINITIONS:
            writer.writerow([m.name, m.numerator, m.denominator, m.unit, m.na_rule, m.source])
    return path


class ValueAccumulator:
    """区内信号值的流式聚合；整数/低基数数据用精确计数表算分位数，超出基数后退化为 1 单位分箱。"""

    def __init__(self) -> None:
        self.n = 0
        self.total = 0.0
        self.sumsq = 0.0
        self.min: float | None = None
        self.max: float | None = None
        self._exact: dict[float, int] = {}
        self._bins: dict[int, int] | None = None

    def add(self, value: float) -> None:
        v = float(value)
        self.n += 1
        self.total += v
        self.sumsq += v * v
        self.min = v if self.min is None else min(self.min, v)
        self.max = v if self.max is None else max(self.max, v)
        if self._bins is not None:
            self._bins[math.floor(v)] = self._bins.get(math.floor(v), 0) + 1
            return
        if v in self._exact:
            self._exact[v] += 1
            return
        if len(self._exact) < MAX_DISTINCT_FOR_EXACT_QUANTILE:
            self._exact[v] = 1
            return
        self._bins = {}
        for key, count in self._exact.items():
            b = math.floor(key)
            self._bins[b] = self._bins.get(b, 0) + count
        self._exact = {}
        b = math.floor(v)
        self._bins[b] = self._bins.get(b, 0) + 1

    @property
    def quantile_method(self) -> str:
        return "EXACT_LINEAR_INTERPOLATION" if self._bins is None else "BINNED_1UNIT_LINEAR_INTERPOLATION"

    def _ordered_counts(self) -> list[tuple[float, int]]:
        if self._bins is None:
            return sorted(self._exact.items())
        return sorted((float(k) + 0.5, v) for k, v in self._bins.items())

    def quantile(self, q: float) -> float | None:
        if self.n == 0:
            return None
        if not 0.0 <= q <= 1.0:
            raise ValueError("分位数 q 必须在 [0,1]")
        ordered = self._ordered_counts()
        # 标准 type-7（numpy 默认）线性插值：h=(n-1)q，取展开后第 floor(h) 与 floor(h)+1 个值。
        h = (self.n - 1) * q
        lower_index = int(math.floor(h))
        fraction = h - lower_index
        cumulative = 0
        lower_value: float | None = None
        upper_value: float | None = None
        for value, count in ordered:
            if lower_value is None and cumulative <= lower_index < cumulative + count:
                lower_value = value
            if upper_value is None and cumulative <= lower_index + 1 < cumulative + count:
                upper_value = value
                break
            cumulative += count
        if lower_value is None:
            lower_value = ordered[-1][0]
        if upper_value is None:
            upper_value = lower_value
        return lower_value + fraction * (upper_value - lower_value)

    def histogram(self) -> dict[str, int]:
        if self._bins is None:
            return {str(int(k)) if float(k).is_integer() else str(k): v
                    for k, v in sorted(self._exact.items())}
        return {str(k): v for k, v in sorted(self._bins.items())}

    def snapshot(self) -> dict:
        if self.n == 0:
            return {k: None for k in ("signal_mean", "signal_stddev", "signal_min", "signal_max",
                                      "signal_p10", "signal_p25", "signal_median", "signal_p75",
                                      "signal_p90", "signal_p95", "signal_p99")} | {
                "signal_histogram_json": json.dumps({}, ensure_ascii=False),
                "quantile_method": self.quantile_method,
            }
        mean = self.total / self.n
        variance = max(0.0, self.sumsq / self.n - mean * mean)
        return {
            "signal_mean": mean,
            "signal_stddev": math.sqrt(variance),
            "signal_min": self.min,
            "signal_max": self.max,
            "signal_p10": self.quantile(0.10),
            "signal_p25": self.quantile(0.25),
            "signal_median": self.quantile(0.50),
            "signal_p75": self.quantile(0.75),
            "signal_p90": self.quantile(0.90),
            "signal_p95": self.quantile(0.95),
            "signal_p99": self.quantile(0.99),
            "signal_histogram_json": json.dumps(self.histogram(), ensure_ascii=False),
            "quantile_method": self.quantile_method,
        }


@dataclass(frozen=True)
class StatContext:
    device_id: str
    cutoff_m: float | None
    mapping: dm.DistanceMapping | None
    parameter_id: int | None
    parameter_version: int | None
    reasons: tuple[str, ...]

    @property
    def usable(self) -> bool:
        return not self.reasons

    def snapshot(self) -> dict:
        return {
            "device_id": self.device_id,
            "parameter_id": self.parameter_id,
            "parameter_version": self.parameter_version,
            "analysis_cutoff_slant_m": self.cutoff_m,
            "mapping_version": self.mapping.version if self.mapping else None,
            "mapping_support_status": self.mapping.support_status if self.mapping else None,
            "sample_mode": self.mapping.sample_mode if self.mapping else None,
            "first_sample_distance_m": self.mapping.first_sample_distance_m if self.mapping else None,
            "sample_interval_m": self.mapping.sample_interval_m if self.mapping else None,
            "algorithm_version": ALGORITHM_VERSION,
            "candidate_event_algorithm": CANDIDATE_EVENT_ALGORITHM,
        }


def resolve_stat_context(conn: sqlite3.Connection, device_id: str,
                         range_m: float | None = None) -> StatContext:
    """取观测时刻适用的参数版本与已核实映射；任何缺项都只阻断本台。"""
    reasons: list[str] = []
    param = device_service.current_version(conn, device_id)
    cutoff = float(param["analysis_cutoff_slant_m"]) if param and param["analysis_cutoff_slant_m"] is not None else None
    if param is None:
        reasons.append("未登记设备参数版本")
    if cutoff is None:
        reasons.append("人工分析截断斜距未配置（禁止用全量程替代）")
    mapping = dm.latest_mapping(conn, device_id, range_m)
    if mapping is None:
        reasons.append("距离映射未登记（禁止按 37.5/1000 推定距离）")
    else:
        reasons.extend(mapping.blocking_reasons(row_range_m=range_m))
    return StatContext(
        device_id=device_id, cutoff_m=cutoff, mapping=mapping,
        parameter_id=param["parameter_id"] if param else None,
        parameter_version=param["version"] if param else None,
        reasons=tuple(reasons),
    )


def detect_candidate_events(indices: Sequence[int], values: Sequence[float], *,
                            threshold: float = DEFAULT_EVENT_THRESHOLD,
                            min_bins: int = DEFAULT_EVENT_MIN_BINS) -> int:
    """区内候选回波：连续（有效槽位下标相邻）且值达到阈值的极大段，达到最小长度记 1 次。"""
    if len(indices) != len(values):
        raise ValueError("indices 与 values 长度必须一致")
    events = 0
    run = 0
    previous: int | None = None
    for idx, value in zip(indices, values):
        if value >= threshold:
            run = run + 1 if previous is not None and idx == previous + 1 else 1
            previous = idx
            if run == min_bins:
                events += 1
        else:
            run = 0
            previous = None
    return events


def _bin_seconds(fmt: str) -> int:
    return 1 if "%S" in fmt else 60


def _missing_intervals(timestamps: Sequence[datetime], bin_s: int,
                       observed_date: str) -> list[dict]:
    if not timestamps:
        return []
    day = datetime.strptime(observed_date, "%Y-%m-%d")
    day_start = day
    day_end = day + timedelta(days=1)
    step = timedelta(seconds=bin_s)
    ordered = sorted(timestamps)
    gaps: list[dict] = []

    def add_gap(start: datetime, end: datetime) -> None:
        seconds = (end - start).total_seconds()
        if seconds > 0:
            gaps.append({"start": start.isoformat(timespec="seconds"),
                         "end": end.isoformat(timespec="seconds"),
                         "duration_s": seconds})

    if ordered[0] > day_start:
        add_gap(day_start, ordered[0])
    for previous, current in zip(ordered, ordered[1:]):
        if current - previous > step:
            add_gap(previous + step, current)
    if ordered[-1] + step < day_end:
        add_gap(ordered[-1] + step, day_end)
    return gaps


def determine_status(observation_status: str, upload_status: str) -> str:
    """状态优先级：缺测/质检/阻断 > 上传属性 > 观测完整度。"""
    if observation_status == STATUS_MISSING:
        return STATUS_MISSING
    if observation_status == STATUS_QC_FAILED:
        return STATUS_QC_FAILED
    if observation_status == STATUS_UNKNOWN:
        return STATUS_UNKNOWN
    if upload_status == UPLOAD_LATE:
        return STATUS_UPLOADED_LATE
    if upload_status == UPLOAD_REPROCESSED:
        return STATUS_REPROCESSED
    return observation_status


@dataclass
class DailyAccumulator:
    device_id: str
    observed_date: str
    context: StatContext
    run_id: str
    planned_window_s: int = PLANNED_WINDOW_S
    event_threshold: float = DEFAULT_EVENT_THRESHOLD
    event_min_bins: int = DEFAULT_EVENT_MIN_BINS
    dataset_id: str | None = None
    upload_status: str = UPLOAD_NORMAL
    raw_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    fully_masked_records: int = 0
    kept_samples: int = 0
    excluded_samples: int = 0
    excluded_by_reason: Counter = field(default_factory=Counter)
    slot_lengths: Counter = field(default_factory=Counter)
    timestamp_formats: Counter = field(default_factory=Counter)
    values: ValueAccumulator = field(default_factory=ValueAccumulator)
    candidate_events: int = 0
    water_sum: float = 0.0
    water_min: float | None = None
    water_max: float | None = None
    water_count: int = 0
    _timestamps: set[datetime] = field(default_factory=set)
    _hourly_valid: list[int] = field(default_factory=lambda: [0] * 24)
    _hourly_events: list[int] = field(default_factory=lambda: [0] * 24)
    _hourly_kept: list[int] = field(default_factory=lambda: [0] * 24)
    mapping_blocked_rows: int = 0
    mapping_blocked_examples: list[str] = field(default_factory=list)

    def add_invalid_row(self, row: ParsedRow, reason: str) -> None:
        """结构异常行（如 0 个有效槽位、逐行量程/点数与映射不符）：计入原始与异常，绝不进入统计。"""
        self.raw_records += 1
        self.slot_lengths[row.effective_signal_len] += 1
        self.invalid_records += 1
        self.mapping_blocked_rows += 1
        if reason not in self.mapping_blocked_examples and len(self.mapping_blocked_examples) < 3:
            self.mapping_blocked_examples.append(reason)

    def add_row(self, row: ParsedRow, mask: dm.MaskResult) -> None:
        self.raw_records += 1
        self.slot_lengths[row.effective_signal_len] += 1
        self.excluded_samples += mask.excluded_total
        for reason, count in mask.excluded_counts.items():
            self.excluded_by_reason[reason] += count
        if row.errors:
            self.invalid_records += 1
            return
        if mask.status != "OK" or mask.kept_count == 0:
            self.fully_masked_records += 1
            return
        self.valid_records += 1
        self.kept_samples += mask.kept_count
        for value in mask.kept_values:
            self.values.add(value)
        events = detect_candidate_events(
            mask.kept_indices, mask.kept_values,
            threshold=self.event_threshold, min_bins=self.event_min_bins,
        )
        self.candidate_events += events
        if row.timestamp is not None:
            self._timestamps.add(row.timestamp)
            self.timestamp_formats[row.timestamp_format] += 1
            hour = row.timestamp.hour
            self._hourly_valid[hour] += 1
            self._hourly_events[hour] += events
            self._hourly_kept[hour] += mask.kept_count
        if row.water_temp_c is not None:
            self.water_count += 1
            self.water_sum += row.water_temp_c
            self.water_min = row.water_temp_c if self.water_min is None else min(self.water_min, row.water_temp_c)
            self.water_max = row.water_temp_c if self.water_max is None else max(self.water_max, row.water_temp_c)

    def finish(self, file_sha256: str = "") -> dict:
        resolution = min((_bin_seconds(fmt) for fmt in self.timestamp_formats), default=60)
        duration = min(len(self._timestamps) * resolution, self.planned_window_s)
        ordered = sorted(self._timestamps)
        gaps = _missing_intervals(ordered, resolution, self.observed_date)
        span = ((ordered[-1] - ordered[0]).total_seconds() + resolution) if ordered else 0.0
        invalid_ratio = self.invalid_records / self.raw_records if self.raw_records else 1.0
        coverage = (duration / self.planned_window_s
                    if self.planned_window_s and self.valid_records else None)
        valid_record_ratio = (self.valid_records / self.raw_records) if self.raw_records else None

        if self.valid_records == 0:
            observation_status = STATUS_UNKNOWN if self.raw_records else STATUS_MISSING
        elif invalid_ratio > 0.05:
            observation_status = STATUS_QC_FAILED
        elif coverage is not None and coverage >= 0.95:
            observation_status = STATUS_COMPLETE
        else:
            observation_status = STATUS_PARTIAL

        notes: list[str] = []
        if self.valid_records == 0 and self.raw_records:
            notes.append("区内无有效观测（依赖样本的指标全部 NA，不填 0）")
        if invalid_ratio > 0.05:
            notes.append(f"解析异常行占比 {invalid_ratio:.4f} > 0.05")
        if self.mapping_blocked_rows:
            notes.append(f"逐行结构异常（无法套用已核实映射）{self.mapping_blocked_rows} 行；"
                         f"示例：{'；'.join(self.mapping_blocked_examples)}")
        if self.excluded_by_reason.get(dm.REASON_BOTTOM, 0) == 0:
            notes.append("BOTTOM_INTERFERENCE 预留给 S07 自动探底，本阶段为 0，不代表无近底影响")

        result = self.values.snapshot()
        result.update({
            "device_id": self.device_id,
            "observed_date": self.observed_date,
            "status": determine_status(observation_status, self.upload_status),
            "observation_status": observation_status,
            "upload_status": self.upload_status,
            "run_id": self.run_id,
            "parameter_version": self.context.parameter_version,
            "mapping_version": self.context.mapping.version if self.context.mapping else None,
            "algorithm_version": ALGORITHM_VERSION,
            "raw_records": self.raw_records,
            "valid_records": self.valid_records,
            "invalid_records": self.invalid_records,
            "fully_masked_records": self.fully_masked_records,
            "timestamp_formats_json": json.dumps(dict(self.timestamp_formats), ensure_ascii=False),
            "timestamp_resolution_s": resolution,
            "valid_observation_duration_s": duration,
            "observation_span_s": span,
            "planned_window_s": self.planned_window_s,
            "coverage_ratio": coverage,
            "valid_record_ratio": valid_record_ratio,
            "signal_slots_per_record": self.slot_lengths.most_common(1)[0][0] if self.slot_lengths else None,
            "raw_signal_slots": sum(k * v for k, v in self.slot_lengths.items()),
            "kept_samples": self.kept_samples,
            "excluded_samples": self.excluded_samples,
            "excluded_by_reason_json": json.dumps(dict(sorted(self.excluded_by_reason.items())), ensure_ascii=False),
            "near_field_excluded_samples": self.excluded_by_reason.get(dm.REASON_NEAR_FIELD, 0),
            "bottom_excluded_samples": self.excluded_by_reason.get(dm.REASON_BOTTOM, 0),
            "candidate_events": self.candidate_events if self.valid_records else None,
            "candidate_event_rate_per_hour": (
                self.candidate_events / (duration / 3600.0) if self.valid_records and duration > 0 else None
            ),
            "candidate_event_algorithm": CANDIDATE_EVENT_ALGORITHM,
            "water_temp_mean": self.water_sum / self.water_count if self.water_count else None,
            "water_temp_min": self.water_min,
            "water_temp_max": self.water_max,
            "water_temp_records": self.water_count,
            "hourly_activity_json": json.dumps({
                "valid_records": self._hourly_valid,
                "candidate_events": self._hourly_events,
                "kept_samples": self._hourly_kept,
            }, ensure_ascii=False),
            "missing_intervals_json": json.dumps(gaps, ensure_ascii=False),
            "missing_interval_count": len(gaps),
            "file_sha256": file_sha256,
            "dataset_id": self.dataset_id,
            "qc_notes": "；".join(notes),
            "blockage_reasons": None,
            "report_path": None,
            "created_at": _now(),
        })
        return result


def compute_daily_statistics(conn: sqlite3.Connection, device_id: str, observed_date: str,
                             path: Path, *, run_id: str, context: StatContext | None = None,
                             limit: int | None = None, planned_window_s: int = PLANNED_WINDOW_S,
                             event_threshold: float = DEFAULT_EVENT_THRESHOLD,
                             event_min_bins: int = DEFAULT_EVENT_MIN_BINS,
                             dataset_id: str | None = None,
                             upload_status: str = UPLOAD_NORMAL,
                             inspection: FileInspection | None = None,
                             file_sha256: str | None = None,
                             progress: object | None = None) -> dict:
    """流式统计一天：唯一样本入口是 build_mask；不修改原始文件。"""
    context = context or resolve_stat_context(conn, device_id)
    if not context.usable:
        raise StatisticsBlocked(device_id, context.reasons)
    if context.cutoff_m is None or context.mapping is None:  # 类型收窄，理论上已由 usable 覆盖
        raise StatisticsBlocked(device_id, ("截断或映射缺失",))

    inspection = inspection or inspect_file(path)
    acc = DailyAccumulator(
        device_id=device_id, observed_date=observed_date, context=context, run_id=run_id,
        planned_window_s=planned_window_s, event_threshold=event_threshold,
        event_min_bins=event_min_bins, dataset_id=dataset_id, upload_status=upload_status,
    )
    for row in iter_rows(inspection, limit=limit):
        if row.effective_signal_len == 0:
            acc.add_invalid_row(row, "信号数组无有效槽位（尾部空 token 不算样本，无法套用距离映射）")
            continue
        try:
            mask = dm.build_mask(
                row.signal[: row.effective_signal_len], context.mapping, context.cutoff_m,
                row_range_m=row.range_m, row_point_count=row.effective_signal_len,
                allow_blocked=False,
            )
        except dm.DistanceMappingBlocked as exc:
            acc.add_invalid_row(row, str(exc))
            continue
        acc.add_row(row, mask)
        if progress is not None and acc.raw_records % 50000 == 0:
            progress(acc.raw_records)  # type: ignore[operator]
    return acc.finish(file_sha256 if file_sha256 is not None else inspection.sha256)


def blocked_row(device_id: str, observed_date: str, run_id: str, reasons: Sequence[str],
                *, upload_status: str = UPLOAD_BLOCKED) -> dict:
    """为前置条件不满足的单台生成 BLOCKED 行：所有样本指标为 NA，绝不填 0。"""
    columns = (
        "signal_mean", "signal_stddev", "signal_min", "signal_max", "signal_p10", "signal_p25",
        "signal_median", "signal_p75", "signal_p90", "signal_p95", "signal_p99",
        "raw_records", "valid_records", "invalid_records", "fully_masked_records",
        "timestamp_resolution_s", "valid_observation_duration_s", "observation_span_s",
        "planned_window_s", "coverage_ratio", "valid_record_ratio",
        "signal_slots_per_record", "raw_signal_slots", "kept_samples", "excluded_samples",
        "near_field_excluded_samples", "bottom_excluded_samples",
        "candidate_events", "candidate_event_rate_per_hour",
        "water_temp_mean", "water_temp_min", "water_temp_max", "water_temp_records",
        "missing_interval_count", "file_sha256",
    )
    row: dict = {name: None for name in columns}
    row.update({
        "device_id": device_id,
        "observed_date": observed_date,
        "status": STATUS_BLOCKED,
        "observation_status": STATUS_UNKNOWN,
        "upload_status": upload_status,
        "run_id": run_id,
        "parameter_version": None,
        "mapping_version": None,
        "algorithm_version": ALGORITHM_VERSION,
        "timestamp_formats_json": "{}",
        "signal_histogram_json": "{}",
        "quantile_method": None,
        "candidate_event_algorithm": CANDIDATE_EVENT_ALGORITHM,
        "excluded_by_reason_json": "{}",
        "hourly_activity_json": "{}",
        "missing_intervals_json": "[]",
        "dataset_id": None,
        "qc_notes": "前置条件不满足，未读取原始文件；禁止用全量程替代",
        "blockage_reasons": "；".join(reasons),
        "report_path": None,
        "created_at": _now(),
    })
    return row


def missing_row(device_id: str, observed_date: str) -> dict:
    """显式缺测日：所有指标 NA（不是 0）。"""
    row = blocked_row(device_id, observed_date, "", ("未上传或未登记当日文件",), upload_status=UPLOAD_NORMAL)
    row.update({
        "status": STATUS_MISSING,
        "observation_status": STATUS_MISSING,
        "upload_status": UPLOAD_NORMAL,
        "run_id": None,
        "qc_notes": "缺测登记：未上传当日文件；所有指标 NA，不得填 0",
    })
    return row


def insert_stat_row(conn: sqlite3.Connection, row: dict) -> int:
    """按列名写入 daily_statistics（列名来自本模块常量，非外部输入）。"""
    allowed = set(_stat_columns(conn))
    unknown = set(row) - allowed
    if unknown:
        raise ValueError(f"daily_statistics 无这些列：{sorted(unknown)}")
    columns = [c for c in row if c != "stat_id"]
    sql = ("INSERT INTO daily_statistics (" + ",".join(columns) + ") VALUES ("
           + ",".join("?" for _ in columns) + ")")
    cursor = conn.execute(sql, tuple(row[c] for c in columns))
    return int(cursor.lastrowid)


def _stat_columns(conn: sqlite3.Connection) -> list[str]:
    return [r["name"] for r in conn.execute("PRAGMA table_info(daily_statistics)")]


def latest_stat(conn: sqlite3.Connection, device_id: str, observed_date: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM daily_statistics WHERE device_id=? AND observed_date=? "
        "ORDER BY stat_id DESC LIMIT 1", (device_id, observed_date),
    ).fetchone()


def all_latest_stats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM v_latest_daily_statistics ORDER BY observed_date, device_id"))
