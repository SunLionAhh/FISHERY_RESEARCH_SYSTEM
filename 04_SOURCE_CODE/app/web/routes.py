# -*- coding: utf-8 -*-
"""S01 Web 路由：首页（设备清单+未知队列）、设备详情（参数/GPS 表单+历史）、保存与预览。"""
import sqlite3

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..db import connect
from ..services import devices as svc
from ..services import weather as weather_svc
from ..services.devices import ConflictError, ValidationError
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
