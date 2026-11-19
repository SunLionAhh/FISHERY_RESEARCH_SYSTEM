# -*- coding: utf-8 -*-
"""S09：16 类科研图注册、数据对账与出图（数据不足明确 BLOCKED，不造图）。"""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FIGURES = [
    ("F09-01", "数据覆盖和质量审计", "P0", "MATPLOTLIB"),
    ("F09-02", "双日 24 小时曲线", "P0", "MATPLOTLIB"),
    ("F09-03", "多日日内热图", "P0", "MATPLOTLIB"),
    ("F09-04", "时间×深度热图", "P1", "MATPLOTLIB"),
    ("F09-05", "原始回波剖面和底界", "P1", "ORIGIN"),
    ("F09-06", "五站空间分布", "P2", "MATPLOTLIB"),
    ("F09-07", "声学与环境关联", "P2", "ORIGIN"),
    ("F09-08", "关键规律证据组合", "P1", "ORIGIN"),
    ("F09-09", "峰值时段和持续性", "P1", "MATPLOTLIB"),
    ("F09-10", "历史滚动基线", "P2", "ORIGIN"),
    ("F09-11", "任意 N 天阶段比较", "P2", "ORIGIN"),
    ("F09-12", "周内节律", "P2", "MATPLOTLIB"),
    ("F09-13", "2 小时×日期热图", "P0", "MATPLOTLIB"),
    ("F09-14", "日期×点位热图", "P2", "MATPLOTLIB"),
    ("F09-15", "多站同期序列与同步性", "P2", "ORIGIN"),
    ("F09-16", "昼夜晨昏和三水层组合", "P1", "ORIGIN"),
]

CONDITIONS = {
    "F09-01": "至少 1 个已建 S03 统计日",
    "F09-02": "至少 2 个不同观测日的逐小时活动",
    "F09-03": "S06 15 分钟格非空",
    "F09-04": "S07 三水层统计非空（以水层代理深度维度）",
    "F09-05": "需原始 37.5 m 回波剖面与已确认底界；当前底界 NOT_DETECTED",
    "F09-06": "至少 1 台设备有用户提供的经纬度",
    "F09-07": "至少 1 个非派生环境数值变量与声学同窗口",
    "F09-08": "至少 1 个 S07 规律版本",
    "F09-09": "S06 峰谷结果非空",
    "F09-10": "S04 历史滚动基线 run 非空",
    "F09-11": "S04 阶段比较 run 非空",
    "F09-12": "S06 周内节律结果非空",
    "F09-13": "S06 15 分钟格非空",
    "F09-14": "S08 日期×站位活动矩阵非空",
    "F09-15": "至少 2 台设备有 ≥3 个共同有效日",
    "F09-16": "S06 昼夜晨昏与 S07 三水层结果均非空",
}

UNITS = {
    "F09-01": "覆盖率（0—1）/ 日",
    "F09-02": "次/有效小时；小时 0—23",
    "F09-03": "次/15 分钟；小时 0—23；日期 YYYY-MM-DD",
    "F09-04": "次/有效小时；离底高度分层代理（m）",
    "F09-05": "回波强度 0—255；距离门 m；底界 m",
    "F09-06": "经度/纬度（度）；站距 m",
    "F09-07": "声学 次/有效小时；环境 SI 单位见 environment_source.units_json",
    "F09-08": "证据等级 L0—L3；版本号（整数）",
    "F09-09": "峰值小时 0—23；活动率 次/有效小时",
    "F09-10": "统计量原单位（见 comparison_runs.result_json）",
    "F09-11": "差值/百分比；单位随比较指标而定",
    "F09-12": "星期 0—6；环境 SI 单位",
    "F09-13": "次/2 小时；小时窗 0/2/.../22",
    "F09-14": "次/有效小时；日期 YYYY-MM-DD；设备 ID",
    "F09-15": "Pearson r（无量纲）；共同有效日（天）",
    "F09-16": "次/有效小时；水层；昼夜段",
}

METRICS = {
    "F09-01": "覆盖率 = 有效观测时长 / 计划窗口（S03 硬掩码后）；样本为每个设备-日最新统计行；缺测状态不参与均值。",
    "F09-02": "活动率 = candidate_events / 有效观测小时；逐小时按 S04 [start,end) 窗口；样本为前两个有效观测日。",
    "F09-03": "15 分钟格候选事件数；有效样本为 coverage_ratio≥0.5 的格子；低覆盖格标 NA，不插值、不填 0。",
    "F09-04": "三水层按日候选事件数；深度维度为离底高度分层代理，不是连续深度剖面；样本为 S07 三水层统计行。",
    "F09-05": "原始回波剖面的逐距离门信号值与人工底界；当前底界 NOT_DETECTED，BLOCKED，不输出图。",
    "F09-06": "五站经纬度与站距；坐标为用户提供的真实值，缺坐标设备标 UNKNOWN；坐标系未声明时站距为 PROVISIONAL 近似。",
    "F09-07": "环境变量逐时刻数值（SI）；来源见 environment_source/quality_flag；共享来源不能解释站间差异。",
    "F09-08": "规律证据等级 L0—L3 与版本；不按天数自动升级；样本为 S07 规律版本记录。",
    "F09-09": "峰值小时与峰值活动率；峰谷阈值固定为峰值×0.7/×0.35；无峰谷结果时 NO_DATA。",
    "F09-10": "S04 历史滚动基线统计量；分母与成员见 baseline.denominator_table；无基线 run 时 NO_DATA。",
    "F09-11": "S04 任意日期/设备比较结果；只读硬掩码后统计；无对应 run 时 NO_DATA。",
    "F09-12": "周内节律统计量；当前以环境数值按星期聚合作代理，不等同声学周节律，需在图中注明。",
    "F09-13": "15 分钟格按 2 小时窗口聚合的候选事件均值；缺格不填 0。",
    "F09-14": "S08 daily_activity 的 rate_per_hour = candidate_events / 有效观测小时；缺站缺测 NA。",
    "F09-15": "S08 同期 Pearson 与领先 1 日相关；共同有效日不足时 r=NA；未校正时间自相关，不证明迁移。",
    "F09-16": "三水层×昼夜条件组合；天文 COORDINATE 未声明时 PROVISIONAL，昼夜覆盖率不足时 NOT_COMPARABLE。",
}

CAPTIONS = {
    "F09-01": "数据覆盖与质量审计：展示各设备-日 S03 硬掩码后的覆盖率与状态；缺测为 NA，不填 0。",
    "F09-02": "双日 24 小时活动曲线：每个有效小时候选事件数除以有效小时数，单位为次/有效小时。",
    "F09-03": "多日日内 15 分钟热图数据：低覆盖格被排除且不插值，色标为固定分级。",
    "F09-04": "时间×三水层代理热图：深度轴为离底高度分层，不是连续深度剖面；样本来自 S07。",
    "F09-05": "原始回波剖面与底界：当前人工底界未确认，BLOCKED，不出图。",
    "F09-06": "五站离线坐标示意：仅绘制用户提供的真实经纬度；缺站标 UNKNOWN，无在线底图与投影。",
    "F09-07": "声学—环境联合数据：环境值来自 S05 来源登记，预报/派生代理不进入正式证据。",
    "F09-08": "关键规律证据组合：按 S07 版本展示 L0—L3 证据等级与指标；低等级不升级为结论。",
    "F09-09": "峰值时段与持续性：峰谷阈值固定；无峰谷检测结果时不出图。",
    "F09-10": "历史滚动基线：S04 基线成员与分母留痕；无 run 时不出图。",
    "F09-11": "任意 N 天阶段比较：S04 比较引擎输出；无 run 时不出图。",
    "F09-12": "周内节律数据：当前为环境代理，不等同声学周节律。",
    "F09-13": "2 小时×日期热图：15 分钟格按固定 2 小时窗聚合，缺格保持 NA。",
    "F09-14": "日期×点位活动率：S08 同源数据，缺站缺测 NA。",
    "F09-15": "多站同期序列与同步性：相关只称关联，共同日不足时不出结论。",
    "F09-16": "昼夜晨昏与三水层组合：坐标系未声明结果 PROVISIONAL；昼夜覆盖不足标不可比。",
}


def _palette():
    docs = Path(__file__).resolve().parents[3] / "12_DOCUMENTATION"
    if str(docs) not in sys.path:
        sys.path.insert(0, str(docs))
    import figure_palette as fp
    from matplotlib import font_manager
    font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    if font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
    plt.rcParams["text.color"] = fp.INK["正文"]
    plt.rcParams["axes.labelcolor"] = fp.INK["正文"]
    plt.rcParams["xtick.color"] = fp.INK["次级"]
    plt.rcParams["ytick.color"] = fp.INK["次级"]
    plt.rcParams["axes.edgecolor"] = fp.INK["边框"]
    return fp


def _rows_from_json(conn, table: str, column: str) -> list[dict]:
    out = []
    for row in conn.execute(f"SELECT {column} FROM {table} ORDER BY created_at DESC"):
        try:
            payload = json.loads(row[0])
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            out.extend(payload.get("results", payload.get("pairs", [])) or [])
        elif isinstance(payload, list):
            out.extend(payload)
    return out


def _hourly(conn) -> dict:
    out = {}
    for row in conn.execute("SELECT device_id,observed_date,hourly_activity_json,coverage_ratio "
                            "FROM daily_statistics WHERE hourly_activity_json IS NOT NULL"):
        try:
            payload = json.loads(row[2])
        except (TypeError, ValueError):
            continue
        events = payload.get("candidate_events", [])
        if len(events) == 24:
            hours = 24 * (row[3] or 1.0)
            out.setdefault(row[0], {})[row[1]] = [e / (hours / 24) for e in events]
    return out


def _grid(conn) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT device_id,observed_date,slot_start,candidate_events,coverage_ratio "
        "FROM s06_time_grid ORDER BY observed_date,slot_start"))


def _data(conn, figure_id: str, project_root: Path):
    """返回 (rows, x, y, title, status, note)；无真实数据时 status!=OK 且 rows 为空。"""
    if figure_id == "F09-01":
        rows = [{"device_id": r[0], "observed_date": r[1], "coverage_ratio": r[2], "status": r[3]}
                for r in conn.execute("SELECT device_id,observed_date,coverage_ratio,status "
                                      "FROM daily_statistics ORDER BY observed_date,device_id")]
        return rows, "observed_date", "coverage_ratio", "覆盖率（按设备）", "OK" if rows else "NO_DATA", "S03 硬掩码后覆盖率"
    if figure_id == "F09-02":
        hourly = _hourly(conn)
        dates = sorted({d for v in hourly.values() for d in v})[:2]
        rows = [{"device_id": dev, "observed_date": day, "hour": h, "rate": hourly[dev][day][h]}
                for dev in hourly for day in dates if day in hourly[dev] for h in range(24)]
        return rows, "hour", "rate", "双日 24 小时活动率", "OK" if len(dates) >= 2 else "INSUFFICIENT_DATES", "仅前两个有效日"
    if figure_id in ("F09-03", "F09-13"):
        grid = _grid(conn)
        rows = []
        for r in grid:
            if r["coverage_ratio"] is None or r["coverage_ratio"] < 0.5:
                continue
            hour = int(r["slot_start"][11:13])
            rows.append({"observed_date": r["observed_date"], "device_id": r["device_id"],
                         "hour": hour // 2 * 2 if figure_id == "F09-13" else hour,
                         "candidate_events": r["candidate_events"]})
        return rows, "hour", "candidate_events", "日内热图（按设备）", "OK" if rows else "NO_DATA", "15 分钟格；低覆盖标 NA"
    if figure_id == "F09-04":
        rows = [{"observed_date": r[1], "device_id": r[0], "layer": r[2],
                 "candidate_events": r[4], "height_m": r[5]}
                for r in conn.execute("SELECT device_id,observed_date,layer,kept_samples,candidate_events,"
                                      "min_height_above_bottom_m FROM s07_layer_stats ORDER BY observed_date")]
        return rows, "observed_date", "candidate_events", "水层×日期（深度代理）", "OK" if rows else "NO_DATA", "三水层代理深度，非连续深度剖面"
    if figure_id == "F09-06":
        path = project_root / "10_TEST_REPORTS/s08_verification/real_data/station_locations.csv"
        if not path.exists():
            return [], "", "", "", "NO_DATA", "缺 S08 站位归档"
        with path.open(encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        rows = [r for r in rows if r.get("longitude_deg") and r.get("latitude_deg")]
        return rows, "longitude_deg", "latitude_deg", "五站离线坐标示意", "OK" if rows else "NO_DATA", "仅真实坐标；无底图/投影"
    if figure_id == "F09-07":
        rows = list(conn.execute(
            "SELECT variable,observed_at,value_si,quality_flag FROM environment_observation "
            "WHERE quality_flag IN ('OK','MODEL_HISTORICAL') ORDER BY observed_at LIMIT 1000"))
        return [dict(r) for r in rows], "observed_at", "value_si", "环境数值序列", "OK" if rows else "BLOCKED", "共享来源，不能解释站间差异"
    if figure_id == "F09-08":
        rows = [dict(r) for r in conn.execute(
            "SELECT pattern_id,version,evidence_level,metrics_json FROM s07_pattern_versions ORDER BY version")]
        return rows, "version", "evidence_level", "规律证据等级版本", "OK" if rows else "NO_DATA", "L0—L3 由 S07 版本化"
    if figure_id == "F09-09":
        rows = _rows_from_json(conn, "s06_analysis_run", "result_json")
        peaks = [r for r in rows if isinstance(r, dict) and (r.get("peak") or r.get("peaks"))]
        return peaks, "observed_date", "peak_hour", "峰值时段与持续性", "OK" if peaks else "NO_DATA", "S06 峰谷检测"
    if figure_id in ("F09-10", "F09-11"):
        rows = _rows_from_json(conn, "comparison_runs", "result_json")
        return rows, "name", "value", "比较/基线留痕", "OK" if rows else "NO_DATA", "S04 比较引擎"
    if figure_id == "F09-12":
        rows = [dict(r) for r in conn.execute(
            "SELECT strftime('%w',observed_at) AS weekday, AVG(value_si) AS mean_value "
            "FROM environment_observation GROUP BY weekday")]
        return rows, "weekday", "mean_value", "周内节律（环境代理）", "OK" if rows else "NO_DATA", "声学周内节律需 S06 结果支持"
    if figure_id == "F09-14":
        path = project_root / "10_TEST_REPORTS/s08_verification/real_data/spatial_activity.csv"
        if not path.exists():
            return [], "", "", "", "NO_DATA", "缺 S08 空间活动归档"
        with path.open(encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        rows = [r for r in rows if r.get("rate_per_hour")]
        return rows, "observed_date", "device_id", "日期×点位活动率", "OK" if rows else "NO_DATA", "缺测不填 0"
    if figure_id == "F09-15":
        path = project_root / "10_TEST_REPORTS/s08_verification/real_data/spatial_summary.json"
        if not path.exists():
            return [], "", "", "", "NO_DATA", "缺 S08 空间统计归档"
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        pairs = payload.get("statistics", {}).get("pairs", [])
        return pairs, "device_a", "pearson_r", "多站同期相关", "OK" if pairs else "NO_DATA", "共同日不足时 r 为 NA"
    if figure_id == "F09-16":
        rows = list(conn.execute("SELECT device_id,observed_date,layer,candidate_events "
                                 "FROM s07_layer_stats ORDER BY observed_date LIMIT 200"))
        return [dict(r) for r in rows], "observed_date", "candidate_events", "三水层×昼夜（条件组合）", "OK" if rows else "NO_DATA", "天文与三水层口径均带 PROVISIONAL/条件标记"
    if figure_id == "F09-05":
        return [], "", "", "", "BLOCKED", "原始 37.5 m 回波剖面未入 S09 数据表；人工底界 NOT_DETECTED，不能确认绘底界"
    return [], "", "", "", "UNKNOWN", "未登记的图类"


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fields})


def _draw(rows, x, y, title, out_png, note, fp):
    fig, ax = plt.subplots(figsize=(8, 4.2))
    cats = sorted({str(r.get(x, "")) for r in rows})[:24]
    series = {}
    for row in rows:
        key = str(row.get("device_id") or row.get("variable") or row.get("layer") or "all")
        try:
            value = float(row.get(y))
        except (TypeError, ValueError):
            continue
        series.setdefault(key, []).append((str(row.get(x, "")), value))
    for index, (key, values) in enumerate(series.items()):
        lookup = dict(values)
        ax.plot(range(len(cats)), [lookup.get(c, float("nan")) for c in cats],
                marker="o", linewidth=1.5, label=key, color=fp.color("A", index + 1)
                if index < len(fp.colors("A")) else fp.LINE["主数据"])
    if series:
        legend = ax.legend(fontsize=8)
        legend.get_frame().set_edgecolor(fp.INK["边框"])
        legend.get_frame().set_facecolor(fp.INK["白"])
    ax.set_xticks(range(len(cats)))
    ax.set_xticklabels(cats, rotation=45, ha="right", fontsize=8)
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.set_title(title + "（" + note + "）", fontsize=10)
    ax.grid(color=fp.INK["网格"], linewidth=0.6)
    fig.tight_layout()
    fig.savefig(out_png, dpi=160)
    plt.close(fig)


def build_all(conn: sqlite3.Connection, project_root: Path, *, run_id: str,
              dataset_id: str, actor: str = "S09") -> dict:
    root = Path(project_root)
    out_dir = root / "07_FIGURES" / "s09"
    out_dir.mkdir(parents=True, exist_ok=True)
    fp = _palette()
    created = []
    now = datetime.now().isoformat(timespec="seconds")
    for figure_id, title, priority, engine in FIGURES:
        rows, x, y, chart_title, status, note = _data(conn, figure_id, root)
        fields = sorted({k for row in rows for k in row})
        fields = [x, y] + [f for f in fields if f not in (x, y)]
        csv_path = out_dir / f"{figure_id}.csv"
        png_path = out_dir / f"{figure_id}.png"
        _write_csv(csv_path, rows, fields)
        quality_note = note
        if status == "OK" and rows:
            for suffix in (".png", ".pdf", ".svg"):
                target = out_dir / f"{figure_id}{suffix}"
                _draw(rows, x, y, chart_title, target, note, fp)
                conn.execute(
                    "INSERT OR REPLACE INTO figure_exports (export_id,figure_id,export_format,"
                    "file_path,sha256,bytes,created_at) VALUES (?,?,?,?,?,?,?)",
                    (f"{figure_id}-{suffix[1:].upper()}", figure_id, suffix[1:].upper(),
                     str(target), hashlib.sha256(target.read_bytes()).hexdigest(),
                     target.stat().st_size, now))
            if engine == "ORIGIN":
                quality_note = (note + "；Origin 本机为试用版（导出含 demo 水印），正式图由 MATPLOTLIB 同源导出；"
                                "Origin OPJU/PNG/PDF/SVG 仅作桥接闭环留痕")
        else:
            png_path = None
        conn.execute(
            "INSERT OR REPLACE INTO figure_registry (figure_id,figure_class,priority,title,engine,"
            "status,run_id,dataset_id,source_csv,output_png,caption,units_json,metric_definition,"
            "quality_note,data_condition,created_at,actor) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (figure_id, title, priority, title, engine, status, run_id, dataset_id, str(csv_path),
             str(png_path) if png_path else None, CAPTIONS[figure_id],
             json.dumps({title: UNITS[figure_id]}, ensure_ascii=False),
             METRICS[figure_id],
             quality_note, CONDITIONS[figure_id], now, actor))
        created.append({"figure_id": figure_id, "status": status, "csv": str(csv_path),
                        "png": str(png_path) if png_path else None})
    conn.commit()
    return {"run_id": run_id, "dataset_id": dataset_id, "figures": created,
            "ok": sum(1 for f in created if f["status"] == "OK"),
            "blocked": sum(1 for f in created if f["status"] != "OK")}


def report(conn: sqlite3.Connection) -> dict:
    rows = [dict(r) for r in conn.execute("SELECT * FROM figure_registry ORDER BY figure_id")]
    return {"total": len(rows), "rows": rows,
            "ok": sum(1 for r in rows if r["status"] == "OK"),
            "blocked": sum(1 for r in rows if r["status"] != "OK")}
