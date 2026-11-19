# -*- coding: utf-8 -*-
"""V4.1 C/F/H：指标聚合、比较、色标、0/NA 与证据分母契约。

本模块只实现可精确验收的软件口径；真实规律与科学验证另按 S07/S11 证据判定。
"""
from __future__ import annotations

import math
import statistics
from typing import Iterable

METRIC_CONTRACTS = {
    "CANDIDATE_EVENT_RATE": {
        "metric_id": "CANDIDATE_EVENT_RATE",
        "name": "候选事件率",
        "unit": "次/有效观测小时",
        "numerator": "候选事件数",
        "denominator": "有效观测小时数",
        "scale": 1.0,
        "color_family": "UNBOUNDED",
        "valid_domain": "S02 硬掩码有效域 + S03 合格统计日",
    },
    "CANDIDATE_OCCURRENCE_RATIO": {
        "metric_id": "CANDIDATE_OCCURRENCE_RATIO",
        "name": "候选回波出现比例",
        "unit": "%",
        "numerator": "至少一个候选回波的有效帧数",
        "denominator": "有效帧数",
        "scale": 100.0,
        "color_family": "RATIO",
        "valid_domain": "有效帧定义与候选识别算法已核实的有效域",
    },
}

COLOR_SCALE_DEFAULTS = {
    "CANDIDATE_EVENT_RATE": {"lower": 0.0, "upper": 3000.0,
                             "color_scale_id": "EVENT_RATE_REFERENCE_V1"},
    "CANDIDATE_OCCURRENCE_RATIO": {"lower": 0.0, "upper": 100.0,
                                   "color_scale_id": "RATIO_0_100_V1"},
}


def metric_contract(metric_id: str) -> dict:
    if metric_id not in METRIC_CONTRACTS:
        raise ValueError("未登记的 metric_id：" + str(metric_id))
    return dict(METRIC_CONTRACTS[metric_id])


def aggregate_observations(rows: Iterable[dict], mode: str = "pooled",
                           metric_id: str = "CANDIDATE_EVENT_RATE") -> dict:
    """合并有效观测 vs 典型日等权；比例与事件率共用分子分母口径但单位不同。"""
    contract = metric_contract(metric_id)
    scale = contract["scale"]
    items = list(rows)
    usable = [row for row in items
              if row.get("numerator") is not None and row.get("denominator")
              and row["denominator"] > 0]
    invalid_days = [row.get("date") for row in items if row not in usable]
    pooled = (sum(row["numerator"] for row in usable)
              / sum(row["denominator"] for row in usable) * scale) if usable else None
    equal_day = (statistics.fmean(row["numerator"] / row["denominator"] * scale
                                  for row in usable)) if usable else None
    selected = pooled if mode == "pooled" else equal_day
    return {
        "metric_id": metric_id, "unit": contract["unit"],
        "aggregation_mode": mode, "n_valid_days": len(usable),
        "n_invalid_days": len(invalid_days), "invalid_days": invalid_days,
        "pooled_value": pooled, "equal_day_mean": equal_day,
        "selected_value": selected,
        "method_id": "POOLED_NUMERATOR_DENOMINATOR" if mode == "pooled"
                     else "EQUAL_DAY_MEAN",
        "note": ("合并有效观测：先分别求分子/分母，再计算指标；"
                 "典型观测日：先算合格日指标，再按日等权均值。二者不得混称。"),
    }


def compare_with_baseline(current_value: float | None, baseline_value: float | None, *,
                          metric_id: str = "CANDIDATE_EVENT_RATE",
                          baseline_id: str | None = None,
                          baseline_members: Iterable[str] = (),
                          cutoff_date: str | None = None,
                          baseline_version: str | None = None) -> dict:
    """相对基线变化：比率差值用百分点，相对变化单列；0/NA 基线为 NA。"""
    contract = metric_contract(metric_id)
    members = list(baseline_members)
    leakage = [member for member in members if cutoff_date and member > cutoff_date]
    if leakage:
        return {"status": "BLOCKED_FUTURE_LEAKAGE", "reason":
                "基线含晚于冻结截止时间的数据：" + "、".join(leakage),
                "baseline_members": members, "cutoff_date": cutoff_date}
    if current_value is None or baseline_value is None:
        return {"status": "NA", "reason": "当前值或基线缺失",
                "percentage_points": None, "absolute_difference": None,
                "relative_change_percent": None, "baseline_members": members}
    absolute = current_value - baseline_value
    relative = (absolute / baseline_value * 100
                if baseline_value not in (0, None) and math.isfinite(float(baseline_value))
                else None)
    return {
        "status": "OK", "comparison_mode": "baseline_change", "metric_id": metric_id,
        "unit": contract["unit"], "baseline_id": baseline_id,
        "baseline_version": baseline_version, "baseline_members": members,
        "cutoff_date": cutoff_date, "baseline_value": baseline_value,
        "current_value": current_value,
        "absolute_difference": absolute,
        "percentage_points": (absolute if contract["color_family"] == "RATIO" else None),
        "relative_change_percent": relative,
        "note": ("百分点仅用于比例指标；相对变化单独命名。"
                 "基线为 0 或缺测时相对变化为 NA，不得写成 0 或 100%。"),
    }


def build_color_scale(metric_id: str, values: Iterable[float | None], *,
                      comparison: bool = False, config: dict | None = None) -> dict:
    """同一组图共用一个 color_scale_id；超界显式标记，不剪裁数据。"""
    contract = metric_contract(metric_id)
    config = dict(config or {})
    numeric = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if comparison:
        magnitude = config.get("magnitude")
        if magnitude is None:
            magnitude = max((abs(v) for v in numeric), default=1.0) or 1.0
        result = {
            "color_scale_id": config.get("color_scale_id")
            or f"DIFF_SYMMETRIC_{metric_id}_V1",
            "metric_id": metric_id, "mode": "diverging", "lower": -float(magnitude),
            "upper": float(magnitude), "center": 0.0, "unit": contract["unit"] + " 差值",
            "map_min": contract["color_family"] == "RATIO",
        }
    else:
        default = COLOR_SCALE_DEFAULTS[metric_id]
        lower = config.get("lower", default["lower"])
        upper = config.get("upper", default["upper"])
        if upper <= lower:
            raise ValueError("色标上界必须大于下界")
        result = {
            "color_scale_id": config.get("color_scale_id") or default["color_scale_id"],
            "metric_id": metric_id, "mode": "sequential",
            "lower": float(lower), "upper": float(upper), "center": None,
            "unit": contract["unit"], "map_min": contract["color_family"] == "RATIO",
        }
    out_of_range = [v for v in numeric if v < result["lower"] or v > result["upper"]]
    result["out_of_range_count"] = len(out_of_range)
    result["out_of_range_values"] = out_of_range
    result["out_of_range_handling"] = "显式标记；不改数据、不静默裁剪"
    result["note"] = ("比例指标固定 0—100%；无上界指标使用冻结参考范围。"
                      "同一比较组不得逐图 min-max 归一化。")
    return result


def classify_cell(*, selected: bool, numerator: float | None, denominator: float | None,
                  coverage: float | None = None, status: str | None = None,
                  low_coverage_threshold: float = 0.5) -> str:
    """有效零值、缺测、低覆盖和未选择必须视觉可区分。"""
    if not selected:
        return "UNSELECTED"
    if status in ("MISSING", "BLOCKED", "QC_FAILED", "UNKNOWN") \
            or numerator is None or denominator is None or denominator <= 0 \
            or coverage is None:
        return "NA"
    if coverage < low_coverage_threshold:
        return "LOW_COVERAGE"
    if numerator == 0:
        return "VALID_ZERO"
    return "OK"


def evidence_summary(counts: dict) -> dict:
    """证据五状态；支持率不是置信度，可评价分母为 0 时返回 NA。"""
    keys = ("SUPPORT", "COUNTER", "INCONCLUSIVE", "UNEVALUABLE", "ERROR")
    values = {key: int(counts.get(key, counts.get(key.lower(), 0)) or 0) for key in keys}
    if any(value < 0 for value in values.values()):
        raise ValueError("证据状态计数不得为负")
    eligible = values["SUPPORT"] + values["COUNTER"] + values["INCONCLUSIVE"]
    rate = values["SUPPORT"] / eligible if eligible else None
    return {
        **values, "total_units": sum(values.values()), "eligible_units": eligible,
        "support_rate": rate,
        "status": "OK" if eligible else "INSUFFICIENT_EVIDENCE",
        "note": ("可评价数=支持+反对+不确定；无法评价与错误单列。"
                 "支持率不是置信度，也不是 L3 自动门槛。"),
    }


def pattern_cards(devices: Iterable[str], selected_devices: Iterable[str], *,
                  run_id: str | None = None, statistics: dict | None = None) -> list[dict]:
    """五台固定独立卡片；无可靠证据时如实显示空态，不生成‘几点鱼多’结论。"""
    selected = set(selected_devices)
    stats = statistics or {}
    cards = []
    for device in devices:
        if device not in selected:
            cards.append({"device_id": device, "status": "UNSELECTED",
                          "label": "未选择", "l_level": None,
                          "reason": "用户未选择该设备；不伪造结果"})
            continue
        if not run_id:
            cards.append({"device_id": device, "status": "NOT_RUN",
                          "label": "未运行", "l_level": None,
                          "reason": "尚未运行该查询；请先运行组合分析"})
            continue
        n_days = (stats.get(device) or {}).get("n_days", 0)
        if n_days < 3:
            cards.append({"device_id": device, "status": "INSUFFICIENT_SAMPLE",
                          "label": "样本不足", "l_level": "L0",
                          "reason": f"有效日 {n_days} < 3；不得给出规律结论"})
            continue
        cards.append({"device_id": device, "status": "CANDIDATE_NO_INDEPENDENT_VALIDATION",
                      "label": "候选；未完成独立验证", "l_level": "L1",
                      "reason": "仅能描述候选模式；独立验证、效应和反例证据未完成"})
    return cards
