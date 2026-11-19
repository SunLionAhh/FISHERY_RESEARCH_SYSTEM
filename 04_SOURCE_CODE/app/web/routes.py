# -*- coding: utf-8 -*-
"""S01 Web 路由：首页（设备清单+未知队列）、设备详情（参数/GPS 表单+历史）、保存与预览。"""
import json
import sqlite3
import threading
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, flash, redirect, render_template,
                   request, url_for)

from ..db import connect
from ..services import comparison as compare_svc
from ..services import daily_stats as daily_svc
from ..services import environment_analysis as env_analysis_svc
from ..services import environment_fetch as fetch_svc
from ..services import environment_import as env_import_svc
from ..services import s07_datasets as dataset_svc
from ..services import s07_depth as depth_svc
from ..services import s07_patterns as pattern_svc
from ..services import spatial as spatial_svc
from ..services import s09_animation as animation_svc
from ..services import s09_figures as figure_svc
from ..services import origin_bridge as origin_svc
from ..services import query_context as query_ctx
from ..services import workbench as workbench_svc
from ..services import beam_geometry as geometry_svc
from ..services import intraday as intraday_svc
from ..services import devices as svc
from ..services import incremental as upload_svc
from ..services import reporting as report_svc
from ..services import weather as weather_svc
from ..services.devices import ConflictError, ValidationError
from ..services.incremental import FrozenDatasetBlocked, UploadConflict, UploadValidationError
from ..services.weather import ValidationError as WeatherValidationError

bp = Blueprint("web", __name__)


def get_conn() -> sqlite3.Connection:
    return connect(current_app_db())


def current_app_db():
    from flask import current_app
    return current_app.config["DB_FILE"]


def parse_expected_version(form) -> int:
    """expected_version 必须为非负整数；abc / 空串不得抛 500，转为字段级 400。

    字段整体缺失（非网页表单调用，如脚本/接口）按 0 处理；字段存在但为空或非法一律 400。
    """
    if "expected_version" not in form:
        return 0
    raw = (form.get("expected_version") or "").strip()
    if raw == "":
        raise ValidationError(["预期版本号非法（expected_version 为空，必须为非负整数）"])
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError([f"预期版本号非法（expected_version=“{raw}”，必须为非负整数）"])
    if value < 0:
        raise ValidationError([f"预期版本号非法（expected_version={value}，必须为非负整数）"])
    return value


@bp.route("/")
def index():
    conn = get_conn()
    devices = svc.list_devices_with_status(conn)
    n_files = conn.execute("SELECT COUNT(*) AS n FROM file_registry").fetchone()["n"]
    datasets = conn.execute("SELECT * FROM datasets ORDER BY phase").fetchall()
    conn.close()
    return render_template("index.html", devices=devices, n_files=n_files, datasets=datasets)


@bp.route("/devices/<device_id>")
def device_detail(device_id: str):
    if device_id not in ("2000", "2001", "2002", "2003", "2005"):
        abort(404)
    conn = get_conn()
    try:
        info = [d for d in svc.list_devices_with_status(conn) if d["device_id"] == device_id][0]
        phist = svc.param_history(conn, device_id)
        poshist = svc.position_history(conn, device_id)
        br = conn.execute(
            "SELECT * FROM bottom_references WHERE device_id=? ORDER BY reference_id DESC", (device_id,)
        ).fetchall()
        weather_hist = weather_svc.weather_history(conn, device_id)
    finally:
        conn.close()
    return render_template(
        "device.html", d=info,
        param_history=phist,
        position_history=poshist,
        bottom_refs=br,
        weather_history=weather_hist,
        weather_codes=weather_svc.WEATHER_CODES,
    )


@bp.route("/devices/<device_id>/params", methods=["POST"])
def save_params(device_id: str):
    conn = get_conn()
    try:
        expected = parse_expected_version(request.form)
        new_version = svc.save_param(conn, device_id, request.form, expected)
        conn.commit()
        flash(f"参数已保存为新版本 v{new_version}（旧版本保留，未覆盖）", "ok")
        return redirect(url_for("web.device_detail", device_id=device_id))
    except ValidationError as e:
        conn.rollback()
        return render_template("error.html", title="校验失败（K13 后端拒绝）", errors=e.errors), 400
    except ConflictError as e:
        conn.rollback()
        return render_template(
            "error.html", title="并发冲突 409",
            errors=[f"提交时预期版本 v{e.expected}，当前已是 v{e.actual}；请刷新页面后基于最新版本修改。"],
        ), 409
    finally:
        conn.close()


@bp.route("/devices/<device_id>/position", methods=["POST"])
def save_position(device_id: str):
    conn = get_conn()
    try:
        expected = parse_expected_version(request.form)
        new_version = svc.save_position(conn, device_id, request.form, expected)
        conn.commit()
        flash(f"位置已保存为新版本 v{new_version}（历史保留，不覆盖）", "ok")
        return redirect(url_for("web.device_detail", device_id=device_id))
    except ValidationError as e:
        conn.rollback()
        return render_template("error.html", title="校验失败（K13 后端拒绝）", errors=e.errors), 400
    except ConflictError as e:
        conn.rollback()
        return render_template(
            "error.html", title="并发冲突 409",
            errors=[f"提交时预期版本 v{e.expected}，当前已是 v{e.actual}；请刷新页面后重试。"],
        ), 409
    finally:
        conn.close()


@bp.route("/devices/<device_id>/params/preview")
def params_preview(device_id: str):
    """保存前影响预览（JSON）：派生值、β 与截断是否受影响。

    P2-2：截断允许未填写（无参数设备预览不得借用其他台的 5.2）——只回派生值与 β，
    analysis_cutoff_slant_m_will_be 返回 null，note 注明「截断未填写」；字段非法仍 400+JSON。
    """
    form = request.args
    conn = get_conn()
    try:
        range_m = svc.device_range_m(conn, device_id)
    finally:
        conn.close()
    try:
        data = svc.validate_param_form(form, range_m=range_m, require_cutoff=False)
    except ValidationError as e:
        return {"ok": False, "errors": e.errors}, 400
    derived_axis = data["derived_axis_slant_m"]
    derived_vertical = data["derived_vertical_clearance_m"]
    cutoff = data["analysis_cutoff_slant_m"]
    notes = []
    if cutoff is None:
        notes.append("截断未填写（预览不借用其他设备数值）")
    if derived_axis or derived_vertical:
        notes.append("派生值仅作参考显示，不写回、不覆盖人工分析截断斜距")
    return {
        "ok": True,
        "device_id": device_id,
        "clearance_input_type": data["clearance_input_type"],
        "derived_axis_slant_m": derived_axis,
        "derived_vertical_clearance_m": derived_vertical,
        "derivation_tilt_deg": data["derivation_tilt_deg"],
        "note": "；".join(notes) if notes else "无派生换算",
        "analysis_cutoff_slant_m_will_be": cutoff,
        "cutoff_untouched_by_derivation": True,
        "beam_half_angle_deg": data["beam_half_angle_deg"],
    }


@bp.route("/devices/<device_id>/weather", methods=["POST"])
def save_weather(device_id: str):
    """保存某设备某天观测天气（每日一条，重复录入视为更正）。"""
    if device_id not in ("2000", "2001", "2002", "2003", "2005"):
        abort(404)
    conn = get_conn()
    try:
        date, corrected = weather_svc.save_weather(conn, device_id, request.form)
        conn.commit()
        label = weather_svc.WEATHER_CODES[request.form.get("weather_code", "").strip().upper()]
        verb = "已更正" if corrected else "已保存"
        flash(f"{date} 天气{verb}：{label}（旧值仅留审计日志，天气不进参数版本链）", "ok")
        return redirect(url_for("web.device_detail", device_id=device_id))
    except WeatherValidationError as e:
        conn.rollback()
        return render_template("error.html", title="天气校验失败（后端拒绝）", errors=e.errors), 400
    finally:
        conn.close()


# ---------------- S03：每日统计 / 增量上传 / 缺测 ----------------

def _valid_device(device_id: str) -> None:
    if device_id not in ("2000", "2001", "2002", "2003", "2005"):
        abort(404)


@bp.route("/daily")
def daily_index():
    conn = get_conn()
    try:
        rows = daily_svc.all_latest_stats(conn)
        conflicts = upload_svc.list_conflicts(conn)
        runs = conn.execute(
            "SELECT run_id, device_id, status, created_at, params_snapshot_json "
            "FROM analysis_runs ORDER BY created_at DESC LIMIT 30"
        ).fetchall()
    finally:
        conn.close()
    return render_template("daily.html", rows=rows, conflicts=conflicts, runs=runs)


@bp.route("/daily/upload", methods=["GET", "POST"])
def daily_upload():
    if request.method == "GET":
        return render_template("daily_upload.html",
                               devices=("2000", "2001", "2002", "2003", "2005"))
    device_id = request.form.get("device_id", "").strip()
    _valid_device(device_id)
    raw_path = request.form.get("file_path", "").strip()
    if not raw_path:
        return render_template("error.html", title="上传校验失败",
                               errors=["必须给出原始 CSV 的本机路径（只读上传）"]), 400
    conn = get_conn()
    try:
        outcome = upload_svc.register_upload(
            conn, device_id, Path(raw_path),
            observed_date=request.form.get("observed_date") or None,
            upload_date=request.form.get("upload_date") or None,
            force=request.form.get("force") == "1",
            project_root=Path(current_app.config["PROJECT_ROOT"]),
            output_root=Path(current_app.config["PROJECT_ROOT"]) / "06_ANALYSIS_RESULTS",
        )
        verb = {"NEW": "上传", "REPROCESSED": "补传/重算", "BLOCKED": "登记（统计 BLOCKED）",
                "DUPLICATE": "重复上传已跳过"}[outcome.decision]
        flash(f"{device_id} {outcome.observed_date} {verb}完成：{outcome.status}；run_id="
              f"`{outcome.run_id or 'NA'}`", "ok")
        return redirect(url_for("web.daily_detail", device_id=device_id,
                                observed_date=outcome.observed_date))
    except UploadConflict as e:
        return render_template("error.html", title="同日文件冲突（需人工审查）",
                               errors=[str(e),
                                       "确认后可在上传表单勾选「强制重传」，旧 run 保留为 SUPERSEDED。"]), 409
    except FrozenDatasetBlocked as e:
        return render_template("error.html", title="冻结数据集保护", errors=[str(e)]), 423
    except UploadValidationError as e:
        return render_template("error.html", title="上传校验失败", errors=[str(e)]), 400
    finally:
        conn.close()


@bp.route("/daily/<device_id>/<observed_date>")
def daily_detail(device_id: str, observed_date: str):
    _valid_device(device_id)
    conn = get_conn()
    try:
        row = daily_svc.latest_stat(conn, device_id, observed_date)
        if row is None:
            abort(404)
        snapshot = None
        if row["run_id"]:
            found = conn.execute("SELECT params_snapshot_json FROM analysis_runs WHERE run_id=?",
                                 (row["run_id"],)).fetchone()
            if found:
                import json
                snapshot = json.loads(found["params_snapshot_json"])
        artifacts = conn.execute(
            "SELECT artifact_type, relative_path FROM s03_artifacts WHERE run_id=?",
            (row["run_id"],),
        ).fetchall() if row["run_id"] else []
    finally:
        conn.close()
    metrics = report_svc.metric_rows(dict(row))
    return render_template("daily_detail.html", row=row, metrics=metrics,
                           snapshot=snapshot, artifacts=artifacts)


@bp.route("/daily/<device_id>/<observed_date>/missing", methods=["POST"])
def daily_mark_missing(device_id: str, observed_date: str):
    _valid_device(device_id)
    conn = get_conn()
    try:
        upload_svc.mark_missing(conn, device_id, observed_date,
                                note=request.form.get("note") or "人工登记缺测",
                                project_root=Path(current_app.config["PROJECT_ROOT"]))
        flash(f"{device_id} {observed_date} 已登记为 MISSING（指标 NA，不填 0）", "ok")
        return redirect(url_for("web.daily_detail", device_id=device_id,
                                observed_date=observed_date))
    except (UploadValidationError, FrozenDatasetBlocked) as e:
        return render_template("error.html", title="缺测登记失败", errors=[str(e)]), 400
    finally:
        conn.close()


def _compare_form_context(conn, form=None) -> dict:
    devices = [dict(r) for r in conn.execute(
        "SELECT device_id, station_id FROM devices ORDER BY device_id")]
    stations = [dict(r) for r in conn.execute("SELECT station_id, name FROM stations ORDER BY station_id")]
    return {"devices": devices, "stations": stations, "form": form or {},
            "timezone_note": compare_svc.SOURCE_TIME_NOTE,
            "endpoint_rule": compare_svc.ENDPOINT_RULE}


@bp.route("/compare", methods=["GET", "POST"])
def compare_index():
    conn = get_conn()
    try:
        context = _compare_form_context(conn, dict(request.form) if request.method == "POST" else {})
        context["runs"] = compare_svc.list_runs(conn)
    finally:
        conn.close()
    return render_template("compare.html", **context)


@bp.route("/compare/run", methods=["POST"])
def compare_run():
    form = request.form
    raw = {
        "devices": [v for v in form.getlist("devices") if v],
        "stations": [v for v in form.getlist("stations") if v],
        "start_date": form.get("start_date"), "end_date": form.get("end_date"),
        "dates": form.get("dates"), "hour_start": form.get("hour_start"),
        "hour_end": form.get("hour_end"), "day_count": form.get("day_count"),
        "day_count_mode": form.get("day_count_mode") or "calendar",
        "timezone": form.get("timezone") or compare_svc.DEFAULT_TIMEZONE,
        "include_invalid": form.get("include_invalid") == "on",
    }
    criteria = compare_svc.Criteria.from_dict(raw)
    conn = get_conn()
    try:
        try:
            result = compare_svc.run(conn, criteria, name=form.get("name") or "网页比较")
        except (compare_svc.ComparisonValidationError, compare_svc.ComparisonEmptyError) as e:
            context = _compare_form_context(conn, raw)
            context["runs"] = compare_svc.list_runs(conn)
            context["errors"] = [str(e)]
            return render_template("compare.html", **context), 400
        baseline = None
        if form.get("baseline_mode"):
            try:
                baseline = compare_svc.build_baseline(
                    conn, criteria, form["baseline_reference_date"],
                    n=int(form.get("baseline_n") or 7), mode=form["baseline_mode"],
                    start=form.get("baseline_start"), end=form.get("baseline_end"))
                result["baseline"] = baseline
                result["summary"] = compare_svc.summarize(
                    result["selection"],
                    [c for matrix in (result["date_comparison_matrix"], result["device_comparison_matrix"])
                     for c in matrix["cases"] if c.get("status") == "OK"],
                    baseline)
            except (compare_svc.ComparisonValidationError, compare_svc.ComparisonEmptyError) as e:
                result["baseline_error"] = str(e)
    finally:
        conn.close()
    return render_template("compare_result.html", result=result)


@bp.get("/environment")
def environment_home():
    conn = get_conn()
    try:
        sources = [dict(r) for r in conn.execute(
            "SELECT * FROM environment_source ORDER BY created_at DESC")]
        batches = [dict(r) for r in conn.execute(
            "SELECT b.*, s.name AS source_name FROM environment_import_batch b "
            "JOIN environment_source s ON s.source_id=b.source_id "
            "ORDER BY b.created_at DESC LIMIT 30")]
        counts = [dict(r) for r in conn.execute(
            "SELECT variable, quality_flag, COUNT(*) n FROM environment_observation "
            "GROUP BY variable, quality_flag ORDER BY variable")]
        fetch_log = [dict(r) for r in conn.execute(
            "SELECT * FROM environment_fetch_log ORDER BY requested_at DESC LIMIT 20")]
    finally:
        conn.close()
    return render_template("environment.html", sources=sources, batches=batches,
                           counts=counts, fetch_log=fetch_log,
                           evaluation=fetch_svc.evaluate(),
                           variables=env_import_svc.VARIABLES)


@bp.post("/environment/import")
def environment_import():
    form = request.form
    action = form.get("action") or "preview"
    path = Path(form.get("file_path") or "")
    preview, outcome, error = None, None, None
    if not path.exists() or path.suffix.lower() not in (".csv", ".xlsx", ".xlsm"):
        error = "文件不存在或不是 CSV/XLSX"
    else:
        try:
            if form.get("suggest"):
                headers, _, metadata, sheet, header_row, _ = env_import_svc.read_table(path)
                mapping = env_import_svc.suggest_mapping(
                    headers, variable=form.get("variable") or "WIND_SPEED",
                    timezone=form.get("timezone") or "Asia/Shanghai", metadata=metadata)
                mapping.sheet = form.get("sheet") or sheet
                if form.get("header_row"):
                    mapping.header_row = int(form["header_row"])
                else:
                    mapping.header_row = header_row
            else:
                mapping = env_import_svc.Mapping(
                    variable=form.get("variable") or "WIND_SPEED",
                    timezone=form.get("timezone") or "Asia/Shanghai",
                    datetime_column=form.get("datetime_col") or None,
                    date_column=form.get("date_col") or None,
                    time_column=form.get("time_col") or None,
                    value_column=form.get("value_col") or None,
                    unit_column=form.get("unit_col") or None,
                    unit_literal=form.get("unit") or None,
                    quality_column=form.get("quality_col") or None,
                    location_key=form.get("location_key") or None)
            if not mapping.value_column:
                raise env_import_svc.ImportValidationError("必须指定数值列；可勾选自动识别字段")
            if action == "preview":
                preview = env_import_svc.preview_file(path, mapping).as_dict()
            else:
                conn = get_conn()
                try:
                    outcome = env_import_svc.commit_import(
                        conn, path, mapping, form.get("source_id") or "",
                        project_root=Path(current_app.config["PROJECT_ROOT"]))
                finally:
                    conn.close()
        except (env_import_svc.ImportValidationError, ValueError, OSError) as exc:
            error = str(exc)
    conn = get_conn()
    try:
        sources = [dict(r) for r in conn.execute("SELECT * FROM environment_source ORDER BY name")]
    finally:
        conn.close()
    if error:
        flash(error)
    return render_template("environment.html", sources=sources, batches=[], counts=[],
                           fetch_log=[], evaluation=fetch_svc.evaluate(),
                           variables=env_import_svc.VARIABLES,
                           preview=preview, outcome=outcome, form=form)


@bp.post("/environment/fetch-attempt")
def environment_fetch_attempt():
    conn = get_conn()
    try:
        result = fetch_svc.attempt(conn, request.form.get("adapter") or "", {"requested_by": "web"})
        flash(f"{result['adapter']}：{result['status']} — {result.get('error') or '已尝试'}")
    finally:
        conn.close()
    return redirect(url_for("web.environment_home"))


@bp.route("/environment/analysis", methods=["GET", "POST"])
def environment_analysis():
    result = None
    error = None
    if request.method == "POST":
        form = request.form
        devices = tuple(d.strip() for d in (form.get("devices") or "2000").split(",") if d.strip())
        conn = get_conn()
        try:
            result = env_analysis_svc.run(
                conn, devices=devices, start_date=form.get("start_date") or None,
                end_date=form.get("end_date") or None,
                timezone_name=form.get("timezone") or "Asia/Shanghai",
                tolerance_s=int(form.get("tolerance") or env_analysis_svc.DEFAULT_TOLERANCE_S))
            import json
            archive = (Path(current_app.config["PROJECT_ROOT"]) / "06_ANALYSIS_RESULTS"
                       / "s05" / f"{result['analysis_id']}.json")
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        except (ValueError, env_analysis_svc.AnalysisUnavailable) as exc:
            error = str(exc)
        finally:
            conn.close()
    return render_template("environment_analysis.html", result=result, error=error)

@bp.get("/intraday")
def intraday_home():
    conn = get_conn()
    try:
        runs = [dict(r) for r in conn.execute(
            "SELECT run_id,name,created_at,method_version FROM s06_analysis_run "
            "ORDER BY created_at DESC LIMIT 20")]
    finally:
        conn.close()
    return render_template("intraday.html", runs=runs, error=None)


@bp.post("/intraday")
def intraday_run():
    form = request.form
    devices = tuple(d.strip() for d in (form.get("devices") or "2000").split(",") if d.strip())
    conn = get_conn()
    try:
        dates = intraday_svc.date_range(form["start_date"], form["end_date"])
        result = intraday_svc.run(
            conn, devices, dates, name=form.get("name") or "S06 日内分析",
            timezone_name=form.get("timezone") or "Asia/Shanghai",
            coverage_mode=form.get("coverage_mode") or "timestamp",
            project_root=Path(current_app.config["PROJECT_ROOT"]))
        intraday_svc.write_outputs(
            result, Path(current_app.config["PROJECT_ROOT"]) / "10_TEST_REPORTS" / "s06_web")
        flash(f"分析完成：{result['analysis_id']}（{len(result['grid_15min'])} 个 15 分钟格）")
        return redirect(url_for("web.intraday_result", run_id=result["analysis_id"]))
    except (KeyError, ValueError, intraday_svc.AnalysisUnavailable) as exc:
        flash(str(exc))
        return redirect(url_for("web.intraday_home"))
    finally:
        conn.close()


@bp.get("/intraday/<run_id>")
def intraday_result(run_id: str):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM s06_analysis_run WHERE run_id=?", (run_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        abort(404)
    result = json.loads(row["result_json"])
    return render_template("intraday_result.html", result=result)


@bp.route("/s07", methods=["GET", "POST"])
def s07_home():
    conn = get_conn()
    message = None
    depth_result = None
    geometry = None
    patterns_result = None
    try:
        if request.method == "POST":
            action = request.form.get("action")
            try:
                if action == "depth":
                    depth_result = depth_svc.analyze_device_day(
                        conn, request.form.get("device_id") or "2000",
                        request.form.get("observed_date") or "2026-10-31",
                        project_root=Path(current_app.config["PROJECT_ROOT"]))
                elif action == "geometry":
                    params = geometry_svc.effective_params(
                        conn, request.form.get("device_id") or "2000",
                        request.form.get("observed_date") or "2026-10-31")
                    geometry = geometry_svc.beam_geometry(
                        height_m=float(params["vertical_bottom_clearance_m"]),
                        tilt_deg=float(params["downward_tilt_deg"]),
                        beam_value_deg=float(params["beam_angle_value_deg"]),
                        beam_kind=params["beam_angle_kind"],
                        cutoff_m=float(params["analysis_cutoff_slant_m"]))
                elif action == "pattern":
                    devices = tuple(d.strip() for d in (request.form.get("devices") or "2000").split(",")
                                    if d.strip())
                    patterns_result = pattern_svc.analyze(
                        conn, devices, request.form.get("start_date"), request.form.get("end_date"),
                        dataset_id=request.form.get("dataset_id") or None)
                    if request.form.get("save"):
                        patterns_result["pattern_id"] = pattern_svc.save_pattern(
                            conn, patterns_result, actor="web")
                elif action in ("boundaries", "freeze", "reopen"):
                    dataset_id = request.form.get("dataset_id") or "DATASET_01_DUAL_STATION"
                    if action == "boundaries":
                        dataset_svc.set_boundaries(
                            conn, dataset_id,
                            start_time=request.form.get("start_time") or None,
                            end_time=request.form.get("end_time") or None,
                            formal_sync_time=request.form.get("formal_sync_time") or None,
                            installation_status=request.form.get("installation_status") or None,
                            actor="web")
                    elif action == "freeze":
                        dataset_svc.freeze(conn, dataset_id, actor="web",
                                           reason=request.form.get("reason") or "S07 阶段冻结")
                    else:
                        dataset_svc.reopen(conn, dataset_id, actor="web",
                                           reason=request.form.get("reason") or "S07 解除冻结")
                    message = f"{action} 完成：{dataset_id}"
            except (ValueError, KeyError, depth_svc.DepthAnalysisUnavailable,
                    dataset_svc.DatasetBoundaryError, geometry_svc.GeometryUnavailable) as exc:
                message = str(exc)
        datasets_report = [dataset_svc.report(conn, row["dataset_id"])
                           for row in conn.execute("SELECT dataset_id FROM datasets ORDER BY dataset_id")]
        versions = [dict(r) for r in conn.execute(
            "SELECT * FROM s07_pattern_versions ORDER BY version DESC LIMIT 10")]
        qc_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM s07_bottom_qc ORDER BY created_at DESC LIMIT 10")]
    finally:
        conn.close()
    return render_template("s07.html", message=message, depth_result=depth_result,
                           geometry=geometry, patterns_result=patterns_result,
                           datasets=datasets_report, pattern_versions=versions, qc_rows=qc_rows)


def _optional_float(form, key):
    raw = (form.get(key) or "").strip()
    if not raw:
        return None
    return float(raw)


def _v41_options(source) -> dict:
    """从表单/查询串读取 V4.1 QueryContext 选项；空值回落到契约默认值。"""
    def integer(key, default):
        try:
            return int(str(source.get(key) or default))
        except (TypeError, ValueError):
            return default

    dates = str(source.get("date_set") or source.get("dates") or "")
    date_set = [part.strip() for part in dates.split(",") if part.strip()]
    windows = []
    for raw in str(source.get("daily_windows") or "").split(","):
        if "-" not in raw:
            continue
        start_time, end_time = raw.split("-", 1)
        windows.append({"start": start_time.strip(), "end": end_time.strip()})
    return {
        "comparison_mode": source.get("comparison_mode") or "independent",
        "metric_id": source.get("metric_id") or query_ctx.DEFAULT_METRIC_ID,
        "grouping_mode": source.get("grouping_mode") or "default",
        "aggregation_mode": source.get("aggregation_mode") or "pooled",
        "baseline_id": source.get("baseline_id") or "FIRST_VALID_DAY",
        "color_scale_id": source.get("color_scale_id") or None,
        "custom_step_days": integer("custom_step_days", 7),
        "page": integer("page", 1),
        "date_set": date_set,
        "daily_windows": windows,
        "depth_mode": source.get("depth_mode") or "ALL",
        "layer": source.get("layer") or None,
        "analysis_plan_version": source.get("analysis_plan_version")
                                 or query_ctx.DEFAULT_ANALYSIS_PLAN_VERSION,
        "mask_version": source.get("mask_version") or query_ctx.DEFAULT_MASK_VERSION,
    }


@bp.route("/s08", methods=["GET", "POST"])
def s08_home():
    """S08：任意组合 + V4.1 同查询契约的空间、比较、动态帧与同源动画导出。"""
    conn = get_conn()
    message = None
    analysis = None
    dynamics = None
    animation_export = None
    selected_devices = list(spatial_svc.DEVICE_IDS)
    start = "2026-10-31"
    end = "2026-11-03"
    observed_date = start
    step_hours = 1
    comparison_mode = "independent"
    dataset_id = spatial_svc.DEFAULT_DATASET_ID
    v41_options = _v41_options({})
    curve_rows = []
    parameter_rows = []
    try:
        if request.method == "POST":
            start = request.form.get("start_date") or start
            end = request.form.get("end_date") or end
            observed_date = request.form.get("observed_date") or start
            comparison_mode = request.form.get("comparison_mode") or comparison_mode
            dataset_id = request.form.get("dataset_id") or dataset_id
            step_hours = int(request.form.get("step_hours") or 1)
            v41_options = _v41_options(request.form)
        try:
            if request.method == "POST":
                raw_devices = request.form.getlist("devices")
                if raw_devices:
                    selected_devices = spatial_svc.parse_devices(raw_devices)
                action = request.form.get("action")
                root = Path(current_app.config["PROJECT_ROOT"])
                if action == "sync":
                    count = spatial_svc.sync_from_positions(conn, actor="web")
                    spatial_svc.compute_distances(conn, observed_date, actor="web")
                    message = f"已从 S01 接入 {count} 条位置记录；未提供的 P 码不自动分配"
                elif action == "save_station":
                    device_id = request.form.get("device_id")
                    spatial_svc.upsert_station(
                        conn, device_id, station_id=request.form.get("station_id") or None,
                        longitude=_optional_float(request.form, "longitude"),
                        latitude=_optional_float(request.form, "latitude"),
                        coordinate_reference_system=request.form.get("coordinate_reference_system") or None,
                        gps_accuracy_m=_optional_float(request.form, "gps_accuracy_m"),
                        water_depth_m=_optional_float(request.form, "water_depth_m"),
                        heading_deg=_optional_float(request.form, "heading_deg"),
                        heading_reference=request.form.get("heading_reference") or None,
                        position_source=request.form.get("position_source") or "USER_WEB",
                        measured_at=request.form.get("measured_at") or None,
                        effective_from=request.form.get("effective_from") or None,
                        actor="web")
                    spatial_svc.compute_distances(conn, observed_date, actor="web")
                    message = f"{device_id} 站位已保存为新版本；历史记录保留"
                elif action == "distances":
                    result = spatial_svc.compute_distances(conn, observed_date, actor="web")
                    message = (f"站距重算完成：{len(result['distances'])} 对"
                               f"，拒绝混算 {len(result['excluded'])} 对")
                elif action in ("analyze", "export_animation"):
                    analysis = spatial_svc.analyze_combination(
                        conn, selected_devices, start, end, observed_date,
                        step_hours=step_hours, dataset_id=dataset_id, actor="web",
                        metric_id=v41_options["metric_id"],
                        grouping_mode=v41_options["grouping_mode"],
                        aggregation_mode=v41_options["aggregation_mode"],
                        baseline_id=v41_options["baseline_id"],
                        color_scale_id=v41_options["color_scale_id"],
                        custom_step_days=v41_options["custom_step_days"],
                        page=v41_options["page"], date_set=v41_options["date_set"],
                        daily_windows=v41_options["daily_windows"],
                        depth_mode=v41_options["depth_mode"], layer=v41_options["layer"],
                        comparison_mode=v41_options["comparison_mode"],
                        analysis_plan_version=v41_options["analysis_plan_version"],
                        mask_version=v41_options["mask_version"])
                    dynamics = analysis["dynamics"]
                    if request.form.get("save"):
                        written = spatial_svc.write_outputs(
                            analysis, root / "10_TEST_REPORTS" / "s08_web")
                        message = "分析完成并归档：" + "、".join(written)
                    else:
                        message = (f"组合分析完成：{analysis['run_id']}，{len(selected_devices)} 站，"
                                   f"{len(dynamics['frames'])} 个离散帧")
                    if action == "export_animation":
                        formats = tuple(x.upper() for x in request.form.getlist("formats")
                                        if x.upper() in ("GIF", "MP4"))
                        animation_export = animation_svc.export_dynamic_frames(
                            conn, root, dynamics, run_id=analysis["run_id"],
                            formats=formats or ("GIF", "MP4"), devices=selected_devices)
                        archived = spatial_svc.write_outputs(
                            analysis, root / "10_TEST_REPORTS" / "s08_verification" /
                            "combinations" / analysis["run_id"])
                        exported = [x["format"] for x in animation_export["exports"]]
                        message = (f"{analysis['run_id']} 动画导出：{'、'.join(exported) or '无可用格式'}；"
                                   f"归档 {len(archived)} 个证据文件")
                elif action == "frames":
                    dynamics = spatial_svc.dynamic_frames(
                        conn, selected_devices, start, end, step_hours=step_hours)
                    message = f"动态帧重建：{len(dynamics['frames'])} 帧（{len(selected_devices)} 站，无轨迹、无插值）"
                else:
                    message = f"未知操作：{action}"
        except (spatial_svc.SpatialValidationError, ValueError, KeyError, OSError) as exc:
            message = str(exc)

        map_data = spatial_svc.map_payload(conn, observed_date, selected_devices)
        bounds = map_data.get("bounds")
        known = [s for s in map_data["stations"]
                 if s["longitude_deg"] is not None and s["latitude_deg"] is not None]
        map_points = []
        for station in map_data["stations"]:
            x = y = None
            if station in known and bounds:
                width = bounds["max_lon"] - bounds["min_lon"]
                height = bounds["max_lat"] - bounds["min_lat"]
                x = (10 + 80 * (station["longitude_deg"] - bounds["min_lon"]) / width
                     if width > 0 else 50)
                y = (85 - 80 * (station["latitude_deg"] - bounds["min_lat"]) / height
                     if height > 0 else 50)
            map_points.append({"station": station, "x": x, "y": y})
        station_rows = [dict(row) for row in conn.execute(
            "SELECT * FROM station_location ORDER BY device_id,effective_from DESC LIMIT 30")]
        if analysis:
            curves = analysis.get("time_curves", {})
            stamps = sorted({point["timestamp_local"] for points in curves.values()
                             for point in points})
            curve_rows = [{"timestamp": stamp,
                           "values": {device: next((point for point in curves.get(device, [])
                                                    if point["timestamp_local"] == stamp), None)
                                      for device in selected_devices}}
                          for stamp in stamps]
            snapshots = (analysis.get("run") or {}).get("parameter_versions", {})
        else:
            snapshots = {device: spatial_svc.parameter_snapshot(conn, device, observed_date)
                         for device in selected_devices}
        parameter_rows = [{"device_id": device, **snapshots.get(device, {})}
                          for device in selected_devices]
    finally:
        conn.close()
    return render_template(
        "s08.html", message=message, map_data=map_data, map_points=map_points,
        station_rows=station_rows, analysis=analysis, dynamics=dynamics,
        animation_export=animation_export, all_devices=spatial_svc.DEVICE_IDS,
        selected_devices=selected_devices, devices=",".join(selected_devices),
        start=start, end=end, observed_date=observed_date, step_hours=step_hours,
        comparison_mode=comparison_mode, dataset_id=dataset_id,
        curve_rows=curve_rows, parameter_rows=parameter_rows,
        v41_options=v41_options)


def _load_s08_run(conn):
    """V4.1 I2：按 run_id 或查询指纹读取同一快照，禁止新旧 run 混显。"""
    run_id = request.args.get("run_id")
    if run_id:
        row = conn.execute(
            "SELECT * FROM spatial_combination_runs WHERE run_id=?", (run_id,)).fetchone()
    else:
        options = _v41_options(request.args)
        devices = spatial_svc.parse_devices(
            request.args.get("devices") or ",".join(spatial_svc.DEVICE_IDS))
        start = request.args.get("start_date") or "2026-10-31"
        end = request.args.get("end_date") or "2026-11-03"
        observed = request.args.get("observed_date") or start
        snapshots = {device: spatial_svc.parameter_snapshot(conn, device, observed)
                     for device in devices}
        context = query_ctx.build_query_context(
            selected_devices=devices, start_date=start, end_date=end,
            date_set=options["date_set"], comparison_mode=options["comparison_mode"],
            baseline_id=options["baseline_id"], aggregation_mode=options["aggregation_mode"],
            grouping_mode=options["grouping_mode"], metric_id=options["metric_id"],
            dataset_id=request.args.get("dataset_id") or spatial_svc.DEFAULT_DATASET_ID,
            analysis_plan_version=options["analysis_plan_version"],
            mask_version=options["mask_version"], color_scale_id=options["color_scale_id"],
            parameter_versions=snapshots,
            daily_windows=options["daily_windows"], depth_mode=options["depth_mode"],
            layer=options["layer"])
        row = conn.execute(
            "SELECT * FROM spatial_combination_runs WHERE query_fingerprint=? "
            "ORDER BY created_at DESC LIMIT 1", (context.query_fingerprint(),)).fetchone()
    if row is None:
        return None, {"status": "NO_RUN", "reason": "没有匹配的组合分析 run；请先运行分析"}
    result = None
    if row["result_json"]:
        try:
            result = json.loads(row["result_json"])
        except (TypeError, ValueError):
            result = None
    meta = {"run_id": row["run_id"], "query_fingerprint": row["query_fingerprint"],
            "status": "READY" if result else "STALE",
            "created_at": row["created_at"]}
    if result is None:
        meta["reason"] = "run 存在但结果快照未生成，禁止显示旧结果冒充本次查询"
    return result, meta


def _s08_api_response(section: str):
    conn = get_conn()
    try:
        result, meta = _load_s08_run(conn)
    finally:
        conn.close()
    payload = {"status": meta["status"], "run_meta": meta,
               "query_context": (result or {}).get("query_context")}
    if result:
        payload[section] = (result.get("v41") or {}).get(section)
    return payload


@bp.get("/s08/api/overview")
def s08_api_overview():
    return _s08_api_response("overview")


@bp.get("/s08/api/spatial-groups")
def s08_api_spatial_groups():
    return _s08_api_response("spatial_groups")


@bp.get("/s08/api/patterns")
def s08_api_patterns():
    return _s08_api_response("patterns")


@bp.get("/s08/api/pattern-evidence")
def s08_api_pattern_evidence():
    return _s08_api_response("pattern_evidence")


@bp.get("/s08/api/day-detail")
def s08_api_day_detail():
    conn = get_conn()
    try:
        result, meta = _load_s08_run(conn)
    finally:
        conn.close()
    device = request.args.get("device_id")
    day = request.args.get("observed_date")
    detail = {"status": meta["status"], "run_meta": meta,
              "device_id": device, "observed_date": day}
    if result:
        detail["cell"] = next((cell for cell in result["v41"]["overview"]["cells"]
                               if cell["device_id"] == device
                               and cell["observed_date"] == day), None)
        detail["time_curve"] = [point for point in result.get("time_curves", {}).get(device, [])
                                if point.get("observed_date") == day]
        detail["frames"] = [frame for frame in result.get("dynamics", {}).get("frames", [])
                            if frame.get("timestamp_local", "").startswith(day)]
        detail["source"] = {"dataset_id": result.get("dataset_id"),
                            "run_id": result["run_id"],
                            "note": "只返回本查询快照内的日值/时段；原始回波按权限另行定位，不自动下载"}
    return detail


@bp.get("/s08/api/compare")
def s08_api_compare():
    return _s08_api_response("compare")


@bp.get("/s08/api/figure-export")
def s08_api_figure_export():
    conn = get_conn()
    try:
        result, meta = _load_s08_run(conn)
    finally:
        conn.close()
    payload = {"status": meta["status"], "run_meta": meta,
               "query_context": (result or {}).get("query_context"),
               "export_contract": {
                   "default_scope": "当前查询快照",
                   "full_scope": "全部选中日期；用户主动选择后后台生成",
                   "routes": {"page": "/s08", "animation": "POST /s08 action=export_animation"},
               }}
    if result:
        payload["export_contract"].update({
            "dataset_id": result.get("dataset_id"),
            "n_dates": len(result["v41"]["overview"]["trend"]),
            "default_groups": result["v41"]["spatial_groups"]["n_groups"],
            "color_scale_id": result["v41"]["color_scale"]["color_scale_id"],
            "dynamics_frames": len(result.get("dynamics", {}).get("frames", [])),
        })
    return payload


def _origin_worker_thread(task_id: str, db_file: str, project_root: Path) -> None:
    from ..db import connect as connect_worker
    conn = connect_worker(db_file)
    try:
        origin_svc.run_task(conn, task_id, project_root)
    finally:
        conn.close()


@bp.route("/s09", methods=["GET", "POST"])
def s09_home():
    """S09：16 类图、动画导出与 Origin 独立 Worker 任务状态。"""
    conn = get_conn()
    message = None
    app_obj = current_app._get_current_object()
    try:
        if request.method == "POST":
            action = request.form.get("action")
            if action == "figures":
                result = figure_svc.build_all(
                    conn, Path(app_obj.config["PROJECT_ROOT"]),
                    run_id=request.form.get("run_id") or "S09-RUN",
                    dataset_id=request.form.get("dataset_id") or "DATASET_01_DUAL_STATION")
                message = f"16 类图登记完成：{result['ok']} 项有数据，{result['blocked']} 项 BLOCKED/NO_DATA"
            elif action == "animation":
                formats = tuple(x for x in request.form.get("formats", "PNG_SEQUENCE,GIF,MP4,PDF").split(",") if x)
                result = animation_svc.export(conn, Path(app_obj.config["PROJECT_ROOT"]), formats=formats)
                message = f"动画导出完成：{result['frames']} 帧，{len(result['exports'])} 种格式"
            elif action == "origin":
                figure_ids = [x.strip() for x in request.form.get("figures", "").split(",") if x.strip()]
                task = origin_svc.create_task(conn, Path(app_obj.config["PROJECT_ROOT"]), figure_ids)
                threading.Thread(
                    target=_origin_worker_thread,
                    args=(task["task_id"], app_obj.config["DB_FILE"],
                          Path(app_obj.config["PROJECT_ROOT"])),
                    daemon=True).start()
                message = f"Origin 任务 {task['task_id']} 已入队，独立 Worker 串行执行；刷新查看状态"
            else:
                message = f"未知操作：{action}"
        figures = figure_svc.report(conn)
        origin = origin_svc.report(conn)
        animation = [dict(r) for r in conn.execute(
            "SELECT * FROM animation_exports ORDER BY created_at DESC LIMIT 12")]
    finally:
        conn.close()
    return render_template("s09.html", message=message, figures=figures,
                           origin=origin, animation=animation,
                           environment=origin_svc.probe_environment())


def _workbench_selection():
    device = request.args.get("device", "2000")
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    stage = request.args.get("stage", "")
    devices = [d for d in workbench_svc.DEVICE_IDS if not device or d == device]
    return device, start, end, stage, devices


@bp.route("/workbench")
def workbench_home():
    """S10：31 类入口总览 + 全局选择 + 跨模块联动，不替代既有阶段页。"""
    device, start, end, stage, devices = _workbench_selection()
    conn = get_conn()
    try:
        ctx = workbench_svc.context(conn, device=device, start=start, end=end, stage=stage)
        rows = workbench_svc.linked_view(conn, devices, start, end)
    finally:
        conn.close()
    return render_template("workbench.html", ctx=ctx, rows=rows)


@bp.route("/workbench/export.csv")
def workbench_export_csv():
    device, start, end, _stage, devices = _workbench_selection()
    conn = get_conn()
    try:
        rows = workbench_svc.linked_view(conn, devices, start, end)
    finally:
        conn.close()
    out = Path(current_app.config["PROJECT_ROOT"]) / "10_TEST_REPORTS" / "s10_verification" / "workbench_linked.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    workbench_svc.write_csv(rows, out)
    return Response(out.read_text(encoding="utf-8-sig"), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=workbench_linked.csv"})


@bp.route("/workbench/report.md")
def workbench_report():
    device, start, end, stage, devices = _workbench_selection()
    conn = get_conn()
    try:
        ctx = workbench_svc.context(conn, device=device, start=start, end=end, stage=stage)
        rows = workbench_svc.linked_view(conn, devices, start, end)
    finally:
        conn.close()
    out = Path(current_app.config["PROJECT_ROOT"]) / "10_TEST_REPORTS" / "s10_verification" / "workbench_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    workbench_svc.write_report(ctx, rows, out)
    return Response(out.read_text(encoding="utf-8"), mimetype="text/markdown; charset=utf-8")


@bp.route("/workbench/backups")
def workbench_backups():
    conn = get_conn()
    try:
        current = conn.execute("PRAGMA database_list").fetchall()
        db_path = next((r[2] for r in current if r[1] == "main"), "")
    finally:
        conn.close()
    backups = workbench_svc.backup_report(Path(current_app.config["PROJECT_ROOT"]))
    return render_template("workbench_backups.html", backups=backups, db_path=db_path)
