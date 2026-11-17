# -*- coding: utf-8 -*-
"""S03 日报、逐日指标 CSV 与 6 类基础图表。

图表一律使用 FIGURE_COLOR_SPEC_V1 的 A_SCIENTIFIC_PRIMARY 配色；数据只读取
`daily_statistics`（其来源为 build_mask 硬掩码），不重新解析原始信号。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ..config import PROJECT_ROOT
from . import daily_stats as ds


def _palette(project_root: Path) -> list[str]:
    path = project_root / "05_CONFIG" / "figure_palette.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [c["hex"] for c in data["palettes"]["A_SCIENTIFIC_PRIMARY"]["colors"]]
    except (OSError, KeyError, ValueError):
        return ["#9599C6", "#BBA0CB", "#BE71AF", "#0271AC", "#E05C4F", "#F2EF92"]


def _setup_chinese_font() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 120


def _fmt(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


_EXPANSIONS = {
    "signal_p10/p25/p75/p90/p95/p99": (
        ("signal_p10", "signal_p10"), ("signal_p25", "signal_p25"),
        ("signal_p75", "signal_p75"), ("signal_p90", "signal_p90"),
        ("signal_p95", "signal_p95"), ("signal_p99", "signal_p99"),
    ),
    "water_temp_mean/min/max": (
        ("water_temp_mean", "water_temp_mean"), ("water_temp_min", "water_temp_min"),
        ("water_temp_max", "water_temp_max"),
    ),
}


def metric_rows(row: dict) -> list[tuple[str, Any, str, str, str, str]]:
    result = []
    for definition in ds.METRIC_DEFINITIONS:
        for name, _ in _EXPANSIONS.get(definition.name, ((definition.name, definition.name),)):
            result.append((name, row.get(name), definition.numerator,
                           definition.denominator, definition.unit, definition.na_rule))
    return result


def write_daily_csv(row: dict, path: Path) -> Path:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric_name", "value", "numerator", "denominator", "unit", "na_rule",
                         "run_id", "device_id", "observed_date"])
        for name, value, numerator, denominator, unit, na_rule in metric_rows(row):
            writer.writerow([name, _fmt(value), numerator, denominator, unit, na_rule,
                             row.get("run_id") or "", row["device_id"], row["observed_date"]])
    return path


def write_daily_report(row: dict, path: Path, *, snapshot: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    reasons = row.get("blockage_reasons") or "无"
    lines = [
        f"# S03 每日统计日报 — 设备 {row['device_id']} / {row['observed_date']}",
        "",
        f"- 状态：**{row['status']}**（观测状态 {row['observation_status']}；上传状态 {row['upload_status']}）",
        f"- run_id：`{row.get('run_id') or 'NA'}`；算法版本：`{row.get('algorithm_version')}`",
        f"- 数据源：`{row.get('relative_path', 'NA')}`；SHA-256：`{row.get('file_sha256') or 'NA'}`",
        f"- 参数版本：{_fmt(row.get('parameter_version'))}；映射版本：{_fmt(row.get('mapping_version'))}",
        f"- 阻断原因：{reasons}",
        "",
        "## 口径声明",
        "",
        "所有区内样本均来自统一硬掩码 `app.services.distance_mapping.build_mask(allow_blocked=False)`：",
        "人工截断 5.2 m、无浮点容差、跨界区间整段排除、盲区 0.5 m 与行内首零之前排除。",
        "本日报不存在全量程统计，也不存在先用全量程再裁剪的结果。缺测指标一律 NA（空），**不填 0**；",
        "仅当区内存在有效观测且未检出候选事件时，候选事件数才记为 0。",
        "",
        "## 指标与分子/分母/单位",
        "",
        "| 指标 | 值 | 分子 | 分母 | 单位 | NA 规则 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, value, numerator, denominator, unit, na_rule in metric_rows(row):
        lines.append(f"| `{name}` | {_fmt(value)} | {numerator} | {denominator} | {unit} | {na_rule} |")
    lines += [
        "",
        "## 掩码与质检说明",
        "",
        f"- 原始记录 {_fmt(row.get('raw_records'))}；有效记录 {_fmt(row.get('valid_records'))}；"
        f"解析异常 {_fmt(row.get('invalid_records'))}；全掩码 {_fmt(row.get('fully_masked_records'))}。",
        f"- 区内保留样本 {_fmt(row.get('kept_samples'))}；排除样本 {_fmt(row.get('excluded_samples'))}。",
        f"- 排除原因：{row.get('excluded_by_reason_json') or '{}'}",
        f"- 候选事件算法：{row.get('candidate_event_algorithm')}（仅为候选，非物种或鱼量结论）",
        f"- QC 备注：{row.get('qc_notes') or '无'}",
        "",
        "## 追溯",
        "",
        f"- 参数/映射/算法快照：`{json.dumps(snapshot, ensure_ascii=False) if snapshot else '见 analysis_runs.params_snapshot_json'}`",
        f"- 图表：见 `07_FIGURES/s03/{row['device_id']}/{row['observed_date']}/`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _save(fig: plt.Figure, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path.as_posix()


def _chart_activity(row: dict, path: Path, colors: list[str]) -> str:
    payload = json.loads(row.get("hourly_activity_json") or "{}")
    valid = payload.get("valid_records", [0] * 24)
    events = payload.get("candidate_events", [0] * 24)
    fig, ax = plt.subplots(figsize=(8, 3.4))
    x = range(24)
    ax.bar(x, valid, color=colors[3], label="有效记录数", width=0.75)
    ax.set_ylabel("有效记录数", color=colors[3])
    ax.set_xlabel("本地时辰（0—23）")
    ax.set_xticks(list(x)[::2])
    ax2 = ax.twinx()
    ax2.plot(x, events, color=colors[4], marker="o", linewidth=1.8, label="候选事件数")
    ax2.set_ylabel("候选事件数", color=colors[4])
    ax.set_title(f"S03 日内活动指标 — {row['device_id']} {row['observed_date']}")
    if row.get("valid_records") is None:
        ax.text(0.5, 0.5, "区内无有效观测（NA）", transform=ax.transAxes, ha="center")
    return _save(fig, path)


def _chart_histogram(row: dict, path: Path, colors: list[str]) -> str:
    hist = json.loads(row.get("signal_histogram_json") or "{}")
    fig, ax = plt.subplots(figsize=(7, 3.4))
    if hist:
        keys = sorted(int(k) for k in hist)
        values = [hist[str(k)] for k in keys]
        ax.bar(keys, values, color=colors[0], edgecolor=colors[3], linewidth=0.4)
        ax.set_yscale("log")
        ax.set_xlabel("区内信号强度（原始 0—255）")
        ax.set_ylabel("样本数（对数轴）")
    else:
        ax.text(0.5, 0.5, "区内无有效观测（NA）", transform=ax.transAxes, ha="center")
    ax.set_title(f"S03 区内信号强度分布 — {row['device_id']} {row['observed_date']}")
    return _save(fig, path)


def _chart_coverage(row: dict, path: Path, colors: list[str]) -> str:
    value = row.get("coverage_ratio")
    fig, ax = plt.subplots(figsize=(6, 2.8))
    if value is None:
        ax.text(0.5, 0.5, "NA", transform=ax.transAxes, ha="center", fontsize=16)
    else:
        ax.barh(["覆盖率"], [value], color=colors[3])
        ax.axvline(0.95, color=colors[4], linestyle="--", linewidth=1.2, label="COMPLETE 阈值 0.95")
        ax.set_xlim(0, 1)
        ax.text(min(value + 0.01, 0.92), 0, _fmt(value), va="center")
        ax.legend(loc="lower right", fontsize=8)
    ax.set_title(f"S03 有效观测覆盖率 — {row['device_id']} {row['observed_date']}")
    return _save(fig, path)


def _chart_missing(rows: Sequence[dict], path: Path, colors: list[str]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    fig, ax = plt.subplots(figsize=(7, 3.2))
    names = sorted(counts)
    ax.bar(names, [counts[n] for n in names],
           color=[colors[3], colors[4], colors[0], colors[2], colors[1], colors[5]][:len(names)])
    for i, name in enumerate(names):
        ax.text(i, counts[name], str(counts[name]), ha="center", va="bottom")
    ax.set_ylabel("设备-日数")
    ax.set_title("S03 缺测/质检状态分布（全部设备-日）")
    return _save(fig, path)


def _chart_exclusion(row: dict, path: Path, colors: list[str]) -> str:
    reasons = json.loads(row.get("excluded_by_reason_json") or "{}")
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    if reasons:
        names = list(reasons)
        ax.barh(names, [reasons[n] for n in names], color=colors[0], edgecolor=colors[3], linewidth=0.5)
        ax.invert_yaxis()
        ax.set_xlabel("排除样本数（来自 build_mask）")
    else:
        ax.text(0.5, 0.5, "无可用统计（NA/BLOCKED）", transform=ax.transAxes, ha="center")
    ax.set_title(f"S03 底界/盲区排除统计 — {row['device_id']} {row['observed_date']}")
    return _save(fig, path)


def _chart_summary_table(row: dict, path: Path, colors: list[str]) -> str:
    keys = ("raw_records", "valid_records", "kept_samples", "excluded_samples",
            "valid_observation_duration_s", "coverage_ratio", "candidate_events",
            "signal_mean", "signal_median", "status")
    cell_text = [[_fmt(row.get(k)) for k in keys]]
    fig, ax = plt.subplots(figsize=(10, 1.8))
    ax.axis("off")
    table = ax.table(cellText=cell_text, colLabels=keys, cellLoc="center", loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.auto_set_column_width(col=list(range(len(keys))))
    for (r, c), cell in table.get_celld().items():
        cell.set_facecolor(colors[3] if r == 0 else "#FFFFFF")
        if r == 0:
            cell.set_text_props(color="white")
    ax.set_title(f"S03 每日统计表 — {row['device_id']} {row['observed_date']}")
    return _save(fig, path)


def generate_daily_outputs(conn: sqlite3.Connection, row: dict, *,
                           project_root: Path = PROJECT_ROOT,
                           output_root: Path | None = None) -> tuple[str, ...]:
    """写日报 + 指标 CSV + 6 类基础图；返回相对/绝对路径列表供清单登记。"""
    base = output_root or project_root
    result_dir = base / "06_ANALYSIS_RESULTS" / "s03" / "daily" / row["device_id"] / row["observed_date"]
    figure_dir = base / "07_FIGURES" / "s03" / row["device_id"] / row["observed_date"]
    _setup_chinese_font()
    colors = _palette(project_root)

    snapshot = None
    if row.get("run_id"):
        found = conn.execute(
            "SELECT params_snapshot_json FROM analysis_runs WHERE run_id=?", (row["run_id"],)
        ).fetchone()
        if found:
            snapshot = json.loads(found["params_snapshot_json"])

    csv_path = write_daily_csv(row, result_dir / "daily_statistics.csv")
    report_path = write_daily_report(row, result_dir / "daily_report.md", snapshot=snapshot)
    all_rows = [dict(r) for r in ds.all_latest_stats(conn)]
    paths = [
        csv_path.as_posix(), report_path.as_posix(),
        _chart_activity(row, figure_dir / "daily_activity.png", colors),
        _chart_histogram(row, figure_dir / "signal_distribution.png", colors),
        _chart_coverage(row, figure_dir / "coverage.png", colors),
        _chart_missing(all_rows, figure_dir / "missing_status.png", colors),
        _chart_exclusion(row, figure_dir / "bottom_exclusion.png", colors),
        _chart_summary_table(row, figure_dir / "daily_stats_table.png", colors),
    ]
    return tuple(paths)
