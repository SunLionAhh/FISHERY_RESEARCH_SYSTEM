# -*- coding: utf-8 -*-
"""V4.1 I1：版本化共享查询状态 QueryContext。

所有总览、热力、阶段图、趋势、证据抽屉和导出必须绑定同一上下文；
任何组件不得自行推断日期、参数版本或 run。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone as dt_timezone
from typing import Any

DEFAULT_TIMEZONE = "Asia/Shanghai"
COMPARISON_MODES = ("independent", "common_valid", "baseline_change")
AGGREGATION_MODES = ("pooled", "equal_day")
GROUPING_MODES = ("default", "natural_week", "natural_month", "custom")
DEFAULT_METRIC_ID = "CANDIDATE_EVENT_RATE"
DEFAULT_ANALYSIS_PLAN_VERSION = "S08_V41_PLAN_V1"
DEFAULT_MASK_VERSION = "S02_HARD_MASK_V2"


class QueryContextError(ValueError):
    pass


def _now() -> str:
    return datetime.now(dt_timezone.utc).isoformat(timespec="seconds")


@dataclass
class QueryContext:
    selected_devices: list[str]
    date_range: dict[str, str]
    date_set: list[str] = field(default_factory=list)
    daily_windows: list[dict[str, Any]] = field(default_factory=list)
    timezone: str = DEFAULT_TIMEZONE
    metric_id: str = DEFAULT_METRIC_ID
    depth_mode: str = "ALL"
    layer: str | None = None
    environment_filters: dict[str, Any] = field(default_factory=dict)
    comparison_mode: str = "independent"
    baseline_id: str | None = None
    aggregation_mode: str = "pooled"
    grouping_mode: str = "default"
    calendar_anchor: str = "MONDAY"
    dataset_id: str = "DATASET_01_DUAL_STATION"
    run_id: str | None = None
    analysis_plan_version: str = DEFAULT_ANALYSIS_PLAN_VERSION
    parameter_versions: dict[str, Any] = field(default_factory=dict)
    mask_version: str = DEFAULT_MASK_VERSION
    color_scale_id: str | None = None
    status: str = "READY"
    context_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.selected_devices = list(dict.fromkeys(str(d).strip()
                                                   for d in self.selected_devices
                                                   if str(d).strip()))
        if not self.selected_devices:
            raise QueryContextError("QueryContext 至少需要一台设备")
        start, end = self.date_range.get("start"), self.date_range.get("end")
        if not start or not end or start > end:
            raise QueryContextError("date_range 必须为合法的 start<=end")
        if self.timezone != DEFAULT_TIMEZONE:
            raise QueryContextError("V4.1 查询状态固定使用 Asia/Shanghai")
        if self.comparison_mode not in COMPARISON_MODES:
            raise QueryContextError("不支持的比较模式：" + str(self.comparison_mode))
        if self.aggregation_mode not in AGGREGATION_MODES:
            raise QueryContextError("不支持的聚合模式：" + str(self.aggregation_mode))
        if self.grouping_mode not in GROUPING_MODES:
            raise QueryContextError("不支持的分组模式：" + str(self.grouping_mode))
        self.date_set = sorted(set(str(d).strip() for d in self.date_set if str(d).strip()))

    def _fingerprint_payload(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("run_id", "status", "context_id", "created_at"):
            data.pop(key, None)
        return data

    def query_fingerprint(self) -> str:
        """不含 run_id 的查询指纹：用于识别同一查询，防止新旧 run 混显。"""
        payload = json.dumps(self._fingerprint_payload(), ensure_ascii=False,
                             sort_keys=True, separators=(",", ":"))
        return "QC-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["query_fingerprint"] = self.query_fingerprint()
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, default=str)

    def assert_same_query(self, other: "QueryContext") -> None:
        if self.query_fingerprint() != other.query_fingerprint():
            raise QueryContextError("查询状态不一致：禁止把不同 run 当作同一查询结果")


def build_query_context(*, selected_devices, start_date: str, end_date: str,
                        date_set=None, daily_windows=None, timezone: str = DEFAULT_TIMEZONE,
                        metric_id: str = DEFAULT_METRIC_ID, depth_mode: str = "ALL",
                        layer: str | None = None, environment_filters=None,
                        comparison_mode: str = "independent", baseline_id: str | None = None,
                        aggregation_mode: str = "pooled", grouping_mode: str = "default",
                        calendar_anchor: str = "MONDAY", dataset_id: str = "DATASET_01_DUAL_STATION",
                        run_id: str | None = None,
                        analysis_plan_version: str = DEFAULT_ANALYSIS_PLAN_VERSION,
                        parameter_versions=None, mask_version: str = DEFAULT_MASK_VERSION,
                        color_scale_id: str | None = None):
    return QueryContext(
        selected_devices=list(selected_devices),
        date_range={"start": start_date, "end": end_date,
                    "interval": "[start,end)"},
        date_set=list(date_set or []),
        daily_windows=list(daily_windows or []),
        timezone=timezone, metric_id=metric_id, depth_mode=depth_mode, layer=layer,
        environment_filters=dict(environment_filters or {}),
        comparison_mode=comparison_mode, baseline_id=baseline_id,
        aggregation_mode=aggregation_mode, grouping_mode=grouping_mode,
        calendar_anchor=calendar_anchor, dataset_id=dataset_id, run_id=run_id,
        analysis_plan_version=analysis_plan_version,
        parameter_versions=dict(parameter_versions or {}),
        mask_version=mask_version, color_scale_id=color_scale_id)
