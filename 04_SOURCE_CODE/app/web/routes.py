# -*- coding: utf-8 -*-
"""S01 Web 路由：首页（设备清单+未知队列）、设备详情（参数/GPS 表单+历史）、保存与预览。"""
import sqlite3

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..db import connect
from ..services import devices as svc
from ..services.devices import ConflictError, ValidationError

bp = Blueprint("web", __name__)


def get_conn() -> sqlite3.Connection:
    return connect(current_app_db())


def current_app_db():
    from flask import current_app
    return current_app.config["DB_FILE"]


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
    finally:
        conn.close()
    return render_template(
        "device.html", d=info,
        param_history=phist,
        position_history=poshist,
        bottom_refs=br,
    )


@bp.route("/devices/<device_id>/params", methods=["POST"])
def save_params(device_id: str):
    conn = get_conn()
    try:
        expected = int(request.form.get("expected_version", "0"))
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
        expected = int(request.form.get("expected_version", "0"))
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
    """保存前影响预览（JSON）：显示派生值与 5.2 截断是否受影响。"""
    form = request.args
    try:
        data = svc.validate_param_form(form)
    except ValidationError as e:
        return {"ok": False, "errors": e.errors}, 400
    derived_axis = data["derived_axis_slant_m"]
    derived_vertical = data["derived_vertical_clearance_m"]
    return {
        "ok": True,
        "device_id": device_id,
        "clearance_input_type": data["clearance_input_type"],
        "derived_axis_slant_m": derived_axis,
        "derived_vertical_clearance_m": derived_vertical,
        "derivation_tilt_deg": data["derivation_tilt_deg"],
        "note": "派生值仅作参考显示，不写回、不覆盖人工分析截断斜距" if (derived_axis or derived_vertical) else "无派生换算",
        "analysis_cutoff_slant_m_will_be": data["analysis_cutoff_slant_m"],
        "cutoff_untouched_by_derivation": True,
        "beam_half_angle_deg": data["beam_half_angle_deg"],
    }
