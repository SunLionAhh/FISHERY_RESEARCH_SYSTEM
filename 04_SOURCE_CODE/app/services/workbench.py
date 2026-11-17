# -*- coding: utf-8 -*-
"""S10：31 类工作台入口、全局选择、跨模块联动与健康状态汇总。"""
from __future__ import annotations

import csv
import hashlib
import sqlite3
from pathlib import Path

DEVICE_IDS = ("2000", "2001", "2002", "2003", "2005")

ENTRIES = [
    (1, "首页仪表盘", "总览", "/", "S10"),
    (2, "设备管理", "数据", "/devices/2000", "S01"),
    (3, "独立离底高度", "参数", "/devices/2000", "S01/S07"),
    (4, "参数历史版本", "参数", "/devices/2000", "S01"),
    (5, "人工水底参考面", "参数", "/devices/2000", "S01/S07"),
    (6, "理论底界和近底排除设置", "分析", "/s07", "S07"),
    (7, "GPS 站位管理", "参数", "/s08", "S01/S08"),
    (8, "每日上传", "数据", "/daily/upload", "S03"),
    (9, "数据审计", "数据", "/daily", "S02"),
    (10, "每日统计", "数据", "/daily", "S03"),
    (11, "任意日期比较", "分析", "/compare", "S04"),
    (12, "任意设备组合分析", "分析", "/compare", "S04"),
    (13, "缺测管理", "数据", "/daily", "S03"),
    (14, "双站研究阶段管理", "阶段", "/s07", "S07"),
    (15, "五站研究阶段管理", "阶段", "/s08", "S08"),
    (16, "数据集管理", "阶段", "/s07", "S07"),
    (17, "每周和每月规律", "规律", "/s07", "S07"),
    (18, "环境管理", "环境", "/environment", "S05"),
    (19, "环境联合分析", "环境", "/environment/analysis", "S05"),
    (20, "日内分析", "分析", "/intraday", "S06"),
    (21, "昼夜分析", "分析", "/intraday", "S06"),
    (22, "三水层", "分析", "/s07", "S07"),
    (23, "五站空间", "空间", "/s08", "S08"),
    (24, "动态播放", "空间", "/s08", "S08"),
    (25, "规律识别", "规律", "/s07", "S07"),
    (26, "Origin 中心", "导出", "/s09", "S09"),
    (27, "16 类科研图", "导出", "/s09", "S09"),
    (28, "报告中心", "导出", "/workbench/report.md", "S10"),
    (29, "数据冻结", "阶段", "/s07", "S07"),
    (30, "备份恢复", "运维", "/workbench/backups", "S10"),
    (31, "项目状态索引", "总览", "/workbench", "S10"),
]


def device_options(conn: sqlite3.Connection) -> list[dict]:
    known = {row["device_id"] for row in conn.execute("SELECT device_id FROM devices")}
    return [{"device_id": d, "registered": d in known} for d in DEVICE_IDS]


def date_options(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT observed_date FROM daily_statistics ORDER BY observed_date")]


def stage_options(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM datasets ORDER BY phase")]


def cutoff_banner(conn: sqlite3.Connection, devices) -> list[dict]:
    """所有分析/导出入口统一展示人工截断及其生效版本。"""
    out = []
    for device in devices:
        row = conn.execute(
            "SELECT * FROM device_parameter_versions WHERE device_id=? AND effective_to IS NULL "
            "ORDER BY effective_from DESC LIMIT 1", (device,)).fetchone()
        out.append({"device_id": device,
                    "cutoff_m": row["analysis_cutoff_slant_m"] if row else None,
                    "version": row["version"] if row else None,
                    "effective_from": row["effective_from"] if row else None,
                    "status": "OK" if row else "UNKNOWN"})
    return out


def quality_summary(conn: sqlite3.Connection) -> dict:
    def count(sql, params=()):
        return conn.execute(sql, params).fetchone()[0]
    quality = {r[0]: r[1] for r in conn.execute(
        "SELECT status, COUNT(*) FROM daily_statistics GROUP BY status")}
    blocked = count("SELECT COUNT(*) FROM environment_fetch_log WHERE status='BLOCKED'")
    blocked += count("SELECT COUNT(*) FROM figure_registry WHERE status IN ('BLOCKED','NO_DATA')")
    return {"complete_days": quality.get("COMPLETE", 0),
            "missing_days": quality.get("MISSING", 0),
            "qc_failed_days": quality.get("QC_FAILED", 0),
            "unknown_days": quality.get("UNKNOWN", 0),
            "blocked_items": blocked,
            "stations_without_gps": 5 - count(
                "SELECT COUNT(DISTINCT device_id) FROM station_location "
                "WHERE longitude_deg IS NOT NULL AND latitude_deg IS NOT NULL")}


def context(conn: sqlite3.Connection, *, device: str = "2000", start: str = "",
            end: str = "", stage: str = "") -> dict:
    devices = [d for d in DEVICE_IDS if not device or d == device]
    suffix = f"?device={device}&start={start}&end={end}&stage={stage}"
    return {"devices": device_options(conn), "dates": date_options(conn),
            "stages": stage_options(conn), "selected_device": device,
            "selected_start": start, "selected_end": end, "selected_stage": stage,
            "cutoffs": cutoff_banner(conn, devices), "quality": quality_summary(conn),
            "entries": [{"id": n, "name": name, "group": group, "url": url,
                         "url_q": url + suffix, "stage": stage_name}
                        for n, name, group, url, stage_name in ENTRIES]}


def linked_view(conn: sqlite3.Connection, devices, start: str, end: str) -> list[dict]:
    """跨模块联动：同一设备/日期下的统计质量、声学率、环境状态与图状态。"""
    rows = []
    for device in devices:
        for row in conn.execute(
                "SELECT observed_date,status,coverage_ratio,candidate_events,"
                "valid_observation_duration_s FROM daily_statistics "
                "WHERE device_id=? AND observed_date BETWEEN ? AND ? ORDER BY observed_date",
                (device, start or "0000-00-00", end or "9999-99-99")):
            env = conn.execute(
                "SELECT COUNT(*) FROM environment_observation WHERE quality_flag='MODEL_HISTORICAL'"
            ).fetchone()[0]
            figs = conn.execute("SELECT COUNT(*) FROM figure_registry WHERE status='OK'").fetchone()[0]
            hours = row["valid_observation_duration_s"] / 3600 if row["valid_observation_duration_s"] else None
            rows.append({"device_id": device, "observed_date": row["observed_date"],
                         "status": row["status"], "coverage_ratio": row["coverage_ratio"],
                         "rate_per_hour": (row["candidate_events"] / hours if hours else None),
                         "env_model_historical_rows": env, "figures_ok": figs,
                         "missing": "NA" if row["status"] != "COMPLETE" else ""})
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    fields = ["device_id", "observed_date", "status", "coverage_ratio", "rate_per_hour",
              "env_model_historical_rows", "figures_ok", "missing"]
    with Path(path).open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fields})


def write_report(ctx: dict, rows: list[dict], path: Path) -> None:
    lines = ["# S10 工作台联查报告", "",
             f"- 设备：{ctx['selected_device'] or '全部'}｜日期：{ctx['selected_start'] or '不限'}—{ctx['selected_end'] or '不限'}｜阶段：{ctx['selected_stage'] or '全部'}",
             "", "## 人工截断与版本", ""]
    for cutoff in ctx["cutoffs"]:
        lines.append(f"- {cutoff['device_id']}：{cutoff['cutoff_m'] if cutoff['cutoff_m'] is not None else 'UNKNOWN'} m，"
                     f"版本 {cutoff['version'] or 'UNKNOWN'}，生效 {cutoff['effective_from'] or 'UNKNOWN'}（{cutoff['status']}）")
    q = ctx["quality"]
    lines += ["", "## 数据质量与阻断", "",
              f"- COMPLETE 日 {q['complete_days']}；MISSING 日 {q['missing_days']}；QC_FAILED 日 {q['qc_failed_days']}；UNKNOWN 日 {q['unknown_days']}",
              f"- BLOCKED 项 {q['blocked_items']}；无 GPS 站位 {q['stations_without_gps']}",
              "", "## 联动明细", ""]
    for row in rows:
        lines.append(f"- {row['device_id']} {row['observed_date']}：{row['status']}，"
                     f"覆盖率 {row['coverage_ratio']}，活动率 {row['rate_per_hour']}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def backup_report(project_root: Path) -> list[dict]:
    root = Path(project_root)
    out = []
    for folder in sorted((root / "11_BACKUPS").glob("*_pre_run_*")):
        db = folder / "fishery.db"
        if db.exists():
            out.append({"name": folder.name, "bytes": db.stat().st_size,
                        "sha256": hashlib.sha256(db.read_bytes()).hexdigest()})
    return out
