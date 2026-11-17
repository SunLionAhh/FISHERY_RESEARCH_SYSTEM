# -*- coding: utf-8 -*-
"""S01 Web 路由：首页（设备清单+未知队列）、设备详情（参数/GPS 表单+历史）、保存与预览。"""
import sqlite3
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, redirect, render_template,
                   request, url_for)

from ..db import connect
from ..services import comparison as compare_svc
from ..services import daily_stats as daily_svc
from ..services import environment_analysis as env_analysis_svc
from ..services import environment_fetch as fetch_svc
from ..services import environment_import as env_import_svc
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
        except (ValueError, env_analysis_svc.AnalysisUnavailable) as exc:
            error = str(exc)
        finally:
            conn.close()
    return render_template("environment_analysis.html", result=result, error=error)
