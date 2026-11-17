# -*- coding: utf-8 -*-
"""距离映射与统一硬掩码服务（S02，规范 6.8 / 09 K04—K06）。

唯一口径：网页、后台任务、报告与 Origin 导出都必须经由 `build_mask()` 取得「哪些样本在人工
截断以内」，不得各自实现一套。

规则（逐字对应 V4 01 §6.8 与 09 K04/K05/K06）：
1. 点样本（POINT）：按已核实物理距离判断 `r <= cutoff`，**不加任何浮点容差**；
   显示精度不得把 5.201 四舍五入成 5.200 后保留。
2. 区间样本（INTERVAL）：单元覆盖 [r_i, r_i + step)。只有整段都在 cutoff 以内才保留；
   任何跨越截断线的单元，在没有可拆分的原始支持信息时**整段排除**（保守），
   不得因为单元中心在界内就把界外贡献带入。
3. 映射未核实（sample_mode=UNKNOWN / 首点距离缺失 / 状态非 CONFIRMED / 记录量程与映射不符）：
   原始导入可继续，但正式距离分析必须 BLOCKED 并说明缺项；禁止默认 37.5 m/1000 点推断下标。
4. 掩码只做样本取舍并记录原因，不做零填充；被排除样本不得进入背景估计、平滑、事件、统计。
5. 排除原因至少包含：人工越界、距离未知、无效数值，另保留底部干扰扩展位。
6. 盲区（用户口径 2026-11-17）：设备数据盲区 0.5 m——几何上 r < 0.5 m 的样本一律排除
   （点样本按距离；区间样本整段在盲区内或跨界盲区边界的整段排除）；且每行信号数组以
   第一个出现的 0 开始才算数据盲区结束——首零之前的槽位（发射余脉）一律按盲区排除，
   不参与任何统计。排除原因记 `NEAR_FIELD`。
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Sequence

from .csv_parser import first_zero_index

SAMPLE_MODE_POINT = "POINT"
SAMPLE_MODE_INTERVAL = "INTERVAL"
SAMPLE_MODE_UNKNOWN = "UNKNOWN"

SUPPORT_CONFIRMED = "CONFIRMED"
SUPPORT_UNVERIFIED = "UNVERIFIED"
SUPPORT_BLOCKED = "BLOCKED"

# 排除原因（写入审计与质量诊断）
REASON_OUT_OF_RANGE = "OUT_OF_RANGE_MANUAL_CUTOFF"          # r > 人工截断
REASON_CROSS_BOUNDARY = "CROSS_BOUNDARY_INTERVAL_EXCLUDED"  # 无拆分支持的跨界区间
REASON_DISTANCE_UNKNOWN = "DISTANCE_UNKNOWN"                # 该样本距离不可确定
REASON_INVALID_VALUE = "INVALID_VALUE"                      # 非数值/NaN
REASON_MAPPING_UNVERIFIED = "DISTANCE_MAPPING_UNVERIFIED"    # 映射未核实，整行阻断
REASON_NEAR_FIELD = "NEAR_FIELD"                            # 盲区：r<0.5m 或行内首零之前（用户 2026-11-17）
REASON_BOTTOM = "BOTTOM_INTERFERENCE"                       # 预留：底部干扰（S07 启用）

# 用户口径（2026-11-17）：设备数据盲区 0.5 m；与映射 v2 首格起点 0.5 m 一致。
BLIND_ZONE_M = 0.5

ALL_REASONS = (
    REASON_OUT_OF_RANGE, REASON_CROSS_BOUNDARY, REASON_DISTANCE_UNKNOWN,
    REASON_INVALID_VALUE, REASON_MAPPING_UNVERIFIED, REASON_NEAR_FIELD, REASON_BOTTOM,
)


class DistanceMappingBlocked(Exception):
    """距离映射未核实：正式距离分析必须 BLOCKED，禁止用全量程替代。"""

    def __init__(self, device_id: str, reasons: list[str]):
        self.device_id = device_id
        self.reasons = reasons
        super().__init__(f"{device_id} 正式距离分析 BLOCKED：" + "；".join(reasons))


@dataclass(frozen=True)
class DistanceMapping:
    device_id: str
    range_m: float | None
    point_count: int | None
    sample_mode: str
    first_sample_distance_m: float | None
    sample_interval_m: float | None
    support_status: str
    version: int = 1
    evidence: str = ""
    source: str = ""
    mapping_id: int | None = None

    def blocking_reasons(self, row_range_m: float | None = None,
                         row_point_count: int | None = None) -> list[str]:
        """返回阻断正式距离分析的原因；空列表表示该映射可用于硬掩码。"""
        reasons: list[str] = []
        if self.sample_mode == SAMPLE_MODE_UNKNOWN:
            reasons.append("采样语义未核实（1000 点是采样中心还是距离区间未确认）")
        if self.support_status != SUPPORT_CONFIRMED:
            reasons.append(f"映射支撑状态为 {self.support_status}（未经用户确认）")
        if self.first_sample_distance_m is None:
            reasons.append("首点距离未核实（禁止按 37.5 m/1000 点推定下标）")
        if self.sample_mode == SAMPLE_MODE_INTERVAL and not self.sample_interval_m:
            reasons.append("区间采样缺少单元宽度（无法判断跨界）")
        if self.range_m is None:
            reasons.append("映射未绑定量程")
        if row_range_m is not None and self.range_m is not None and row_range_m != self.range_m:
            reasons.append(f"记录量程 {row_range_m} m 与映射量程 {self.range_m} m 不符")
        if (row_point_count is not None and self.point_count is not None
                and row_point_count != self.point_count):
            reasons.append(f"记录点数 {row_point_count} 与映射点数 {self.point_count} 不符")
        return reasons

    def is_usable(self, row_range_m: float | None = None,
                  row_point_count: int | None = None) -> bool:
        return not self.blocking_reasons(row_range_m, row_point_count)


@dataclass
class MaskResult:
    """统一硬掩码结果：只含区内样本与逐样本原因，不含任何零填充。"""
    status: str                                   # OK / BLOCKED
    device_id: str
    cutoff_m: float
    total: int
    kept_indices: tuple[int, ...] = ()
    kept_values: tuple[float, ...] = ()
    excluded_counts: dict[str, int] = field(default_factory=dict)
    excluded_reasons: tuple[tuple[int, str], ...] = ()   # (index, reason) 按索引升序
    blocked_reasons: tuple[str, ...] = ()
    mapping_version: int | None = None

    @property
    def kept_count(self) -> int:
        return len(self.kept_indices)

    @property
    def excluded_total(self) -> int:
        return self.total - self.kept_count

    def reason_summary(self) -> str:
        if not self.excluded_counts:
            return ""
        return ";".join(f"{k}={v}" for k, v in sorted(self.excluded_counts.items()))


def _is_finite_number(value) -> bool:
    import math
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def mask_points(distances: Sequence[float | None], values: Sequence[float | str | None],
                cutoff_m: float, *, device_id: str = "unknown",
                mapping_version: int | None = None,
                blind_zone_end_index: int | None = None) -> MaskResult:
    """点样本掩码：r <= cutoff 保留，绝不使用浮点容差扩展上限。

    盲区优先级最高（位置性规则）：行内首零之前的槽位、以及 r < 0.5 m 的样本，
    一律按 `NEAR_FIELD` 排除。
    """
    _validate_cutoff(cutoff_m)
    if len(distances) != len(values):
        raise ValueError("distances 与 values 长度必须一致")
    kept_idx: list[int] = []
    kept_val: list[float] = []
    reasons: list[tuple[int, str]] = []
    counts: Counter[str] = Counter()

    for i, (r, raw) in enumerate(zip(distances, values)):
        if blind_zone_end_index is not None and i < blind_zone_end_index:
            counts[REASON_NEAR_FIELD] += 1
            reasons.append((i, REASON_NEAR_FIELD))
            continue
        if not _is_finite_number(raw):
            counts[REASON_INVALID_VALUE] += 1
            reasons.append((i, REASON_INVALID_VALUE))
            continue
        if r is None or not _is_finite_number(r):
            counts[REASON_DISTANCE_UNKNOWN] += 1
            reasons.append((i, REASON_DISTANCE_UNKNOWN))
            continue
        if r < BLIND_ZONE_M:
            counts[REASON_NEAR_FIELD] += 1
            reasons.append((i, REASON_NEAR_FIELD))
            continue
        if r <= cutoff_m:
            kept_idx.append(i)
            kept_val.append(float(raw))
        else:
            counts[REASON_OUT_OF_RANGE] += 1
            reasons.append((i, REASON_OUT_OF_RANGE))

    return MaskResult(
        status="OK", device_id=device_id, cutoff_m=cutoff_m, total=len(values),
        kept_indices=tuple(kept_idx), kept_values=tuple(kept_val),
        excluded_counts=dict(counts), excluded_reasons=tuple(reasons),
        mapping_version=mapping_version,
    )


def mask_intervals(starts: Sequence[float | None], interval_m: float,
                   values: Sequence[float | str | None], cutoff_m: float, *,
                   device_id: str = "unknown",
                   mapping_version: int | None = None,
                   blind_zone_end_index: int | None = None) -> MaskResult:
    """区间样本掩码：整段在界内才保留；跨界（无拆分支持）整段排除。

    盲区优先级最高（位置性规则）：行内首零之前的槽位一律排除；几何上整段位于
    盲区内（end <= 0.5m）或跨越盲区边界（start < 0.5m < end）的单元整段排除。
    """
    _validate_cutoff(cutoff_m)
    if len(starts) != len(values):
        raise ValueError("starts 与 values 长度必须一致")
    if interval_m is None or interval_m <= 0:
        raise ValueError("区间采样必须有正的单元宽度")
    kept_idx: list[int] = []
    kept_val: list[float] = []
    reasons: list[tuple[int, str]] = []
    counts: Counter[str] = Counter()

    for i, (start, raw) in enumerate(zip(starts, values)):
        if blind_zone_end_index is not None and i < blind_zone_end_index:
            counts[REASON_NEAR_FIELD] += 1
            reasons.append((i, REASON_NEAR_FIELD))
            continue
        if not _is_finite_number(raw):
            counts[REASON_INVALID_VALUE] += 1
            reasons.append((i, REASON_INVALID_VALUE))
            continue
        if start is None or not _is_finite_number(start):
            counts[REASON_DISTANCE_UNKNOWN] += 1
            reasons.append((i, REASON_DISTANCE_UNKNOWN))
            continue
        end = start + interval_m
        if end <= BLIND_ZONE_M or start < BLIND_ZONE_M < end:
            counts[REASON_NEAR_FIELD] += 1
            reasons.append((i, REASON_NEAR_FIELD))
            continue
        if end <= cutoff_m:
            kept_idx.append(i)
            kept_val.append(float(raw))
        elif start < cutoff_m < end:
            # 中心可能在界内，但界外贡献无法拆分 → 保守整段排除
            counts[REASON_CROSS_BOUNDARY] += 1
            reasons.append((i, REASON_CROSS_BOUNDARY))
        else:
            counts[REASON_OUT_OF_RANGE] += 1
            reasons.append((i, REASON_OUT_OF_RANGE))

    return MaskResult(
        status="OK", device_id=device_id, cutoff_m=cutoff_m, total=len(values),
        kept_indices=tuple(kept_idx), kept_values=tuple(kept_val),
        excluded_counts=dict(counts), excluded_reasons=tuple(reasons),
        mapping_version=mapping_version,
    )


def _validate_cutoff(cutoff_m: float) -> None:
    if not _is_finite_number(cutoff_m) or cutoff_m <= 0:
        raise ValueError(f"人工分析截断斜距必须为有限正数，收到 {cutoff_m!r}")


def build_mask(signal_values: Sequence[float | str | None],
               mapping: DistanceMapping, cutoff_m: float, *,
               row_range_m: float | None = None,
               row_point_count: int | None = None,
               allow_blocked: bool = False) -> MaskResult:
    """唯一入口：按映射语义生成硬掩码。

    allow_blocked=False（正式分析）→ 映射未核实直接抛 DistanceMappingBlocked。
    allow_blocked=True（审计/诊断）→ 返回 status=BLOCKED 的结果，全部样本标记原因，
    绝不冒充「区内 0 个样本」参与任何统计。
    """
    reasons = mapping.blocking_reasons(row_range_m, row_point_count)
    if reasons:
        if not allow_blocked:
            raise DistanceMappingBlocked(mapping.device_id, reasons)
        return MaskResult(
            status="BLOCKED", device_id=mapping.device_id, cutoff_m=cutoff_m,
            total=len(signal_values),
            excluded_counts={REASON_MAPPING_UNVERIFIED: len(signal_values)},
            excluded_reasons=tuple((i, REASON_MAPPING_UNVERIFIED) for i in range(len(signal_values))),
            blocked_reasons=tuple(reasons), mapping_version=mapping.version,
        )

    if mapping.sample_mode == SAMPLE_MODE_POINT:
        distances = [mapping.first_sample_distance_m + i * (mapping.sample_interval_m or 0)
                     for i in range(len(signal_values))]
        return mask_points(distances, signal_values, cutoff_m,
                           device_id=mapping.device_id, mapping_version=mapping.version,
                           blind_zone_end_index=first_zero_index(signal_values))

    starts = [mapping.first_sample_distance_m + i * mapping.sample_interval_m
              for i in range(len(signal_values))]
    return mask_intervals(starts, mapping.sample_interval_m, signal_values, cutoff_m,
                          device_id=mapping.device_id, mapping_version=mapping.version,
                          blind_zone_end_index=first_zero_index(signal_values))


# ---------------- 持久化：逐设备/量程/采样定义版本化 ----------------

def register_mapping(conn: sqlite3.Connection, mapping: DistanceMapping, *,
                     operator: str = "seed") -> int:
    """写入新版本（不覆盖旧版本），返回 version。同内容重复登记也生成新版本以便留痕。"""
    row = conn.execute(
        "SELECT MAX(version) v FROM distance_mappings WHERE device_id=?", (mapping.device_id,)
    ).fetchone()
    version = (row["v"] or 0) + 1
    conn.execute(
        """INSERT INTO distance_mappings
           (device_id, version, range_m, point_count, sample_mode, first_sample_distance_m,
            sample_interval_m, support_status, evidence, source, created_by, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (mapping.device_id, version, mapping.range_m, mapping.point_count, mapping.sample_mode,
         mapping.first_sample_distance_m, mapping.sample_interval_m, mapping.support_status,
         mapping.evidence, mapping.source, operator,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    return version


def latest_mapping(conn: sqlite3.Connection, device_id: str,
                   range_m: float | None = None) -> DistanceMapping | None:
    sql = ("SELECT * FROM distance_mappings WHERE device_id=?"
           + (" AND (range_m=? OR range_m IS NULL)" if range_m is not None else "")
           + " ORDER BY version DESC LIMIT 1")
    params: tuple = (device_id,) if range_m is None else (device_id, range_m)
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    return DistanceMapping(
        device_id=row["device_id"], range_m=row["range_m"], point_count=row["point_count"],
        sample_mode=row["sample_mode"], first_sample_distance_m=row["first_sample_distance_m"],
        sample_interval_m=row["sample_interval_m"], support_status=row["support_status"],
        version=row["version"], evidence=row["evidence"] or "", source=row["source"] or "",
        mapping_id=row["mapping_id"],
    )


def mask_row_with_mapping(conn: sqlite3.Connection, device_id: str, cutoff_m: float,
                          values: Sequence[float | str | None], *,
                          row_range_m: float | None = None,
                          row_point_count: int | None = None,
                          allow_blocked: bool = False) -> MaskResult:
    """按库中最新映射生成掩码；无映射按 UNKNOWN 处理（正式分析默认 BLOCKED）。"""
    mapping = latest_mapping(conn, device_id, row_range_m)
    if mapping is None:
        mapping = DistanceMapping(
            device_id=device_id, range_m=row_range_m, point_count=row_point_count,
            sample_mode=SAMPLE_MODE_UNKNOWN, first_sample_distance_m=None,
            sample_interval_m=None, support_status=SUPPORT_UNVERIFIED,
            version=0, evidence="未登记距离映射", source="NONE",
        )
    return build_mask(values, mapping, cutoff_m, row_range_m=row_range_m,
                      row_point_count=row_point_count, allow_blocked=allow_blocked)
