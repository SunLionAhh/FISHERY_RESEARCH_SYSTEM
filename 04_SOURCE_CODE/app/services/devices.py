# -*- coding: utf-8 -*-
"""S01 设备参数与位置服务：校验（K13）、版本链（任务四）、并发冲突 409（K15 前置）。

原则：
- 每次保存生成新版本行；旧版本行永不更新（不可变历史）；
- 新参数只影响其生效区间之后的新任务；analysis_runs 通过 params_snapshot_json 引用版本 id，
  历史结果不随新参数漂移（缓存失效按参数版本 id 键控）；
- UNKNOWN 一律存 NULL，不自动填默认值（任务三：不得自动填 3.68）。
"""
import json
import math
import sqlite3
from datetime import datetime, timezone

from ..identity import current_operator
from ..seed import beam_angles, derive_from_tilt

# K13：截断上限。优先取本台 devices.range_m；量程 UNKNOWN 时按 100 m 临时上限校验
# （本机量程 37.5 m，任何超过 100 m 的值不可能来自本设备；阈值来源见 STAGE_S01 整改记录，
#  待用户确认量程后收紧为 range_m）。
CUTOFF_FALLBACK_MAX_M = 100.0


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class ConflictError(Exception):
    def __init__(self, expected: int, actual: int):
        self.expected, self.actual = expected, actual
        super().__init__(f"version conflict: expected {expected}, actual {actual}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# 非法数值的哨兵：与「空值 None」区分，确保非法输入不会被当作未填写而静默入库
_INVALID = object()


def _parse_number(form, key, label, errors):
    """安全数值解析（K13）。

    - 空串/缺省 → None（由调用方按必填规则处理）
    - 非数字（abc、1,2 等）→ 字段级 ValidationError 记录，返回 _INVALID（不抛 500）
    - NaN/inf/-inf/超出浮点范围（1e999）→ 记录「必须为有限数值」，返回 _INVALID
    """
    raw = (form.get(key) or "").strip()
    if raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        errors.append(f"{label}必须为数字（收到“{raw}”），已拒绝保存")
        return _INVALID
    if not math.isfinite(value):
        errors.append(f"{label}必须为有限数值（不得为 NaN/inf），已拒绝保存")
        return _INVALID
    return value


def validate_param_form(form: dict, *, range_m: float | None = None,
                        require_cutoff: bool = True) -> dict:
    """后端校验（K13）：非法值、空值、NaN/inf、越量程一律拒绝并定位字段，不静默修正。

    range_m：本台量程（devices.range_m）；为 None 时按 CUTOFF_FALLBACK_MAX_M 临时校验，
    错误文案会明确「量程 UNKNOWN，按上限 100 m 临时校验」。
    require_cutoff=False 仅供保存前预览使用（截断未填写时只回派生值，不报必填错）。
    """
    errors: list[str] = []
    data: dict = {}

    cutoff = _parse_number(form, "analysis_cutoff_slant_m", "人工分析截断斜距", errors)
    if cutoff is _INVALID:
        cutoff = None
    elif cutoff is None:
        if require_cutoff:
            errors.append("人工分析截断斜距必填（每台必须有用户人工上限）")
    elif cutoff <= 0:
        errors.append("人工分析截断斜距必须 > 0")
    else:
        upper = range_m if range_m else CUTOFF_FALLBACK_MAX_M
        if cutoff > upper:
            if range_m:
                errors.append(f"人工分析截断斜距 {cutoff:g} m 超出本台量程 {range_m:g} m，已拒绝")
            else:
                errors.append(
                    f"人工分析截断斜距 {cutoff:g} m 超出上限"
                    f"（量程 UNKNOWN，按上限 {CUTOFF_FALLBACK_MAX_M:g} m 临时校验），已拒绝"
                )
    data["analysis_cutoff_slant_m"] = cutoff

    input_type = (form.get("clearance_input_type") or "UNKNOWN").strip().upper()
    if input_type not in ("VERTICAL", "AXIS_SLANT", "UNKNOWN"):
        errors.append("离底参考输入类型必须为 VERTICAL / AXIS_SLANT / UNKNOWN")
    data["clearance_input_type"] = input_type

    vertical = _parse_number(form, "vertical_bottom_clearance_m", "垂直离底高度", errors)
    axis = _parse_number(form, "axis_slant_m", "中心轴斜距", errors)
    vertical = None if vertical is _INVALID else vertical
    axis = None if axis is _INVALID else axis
    if input_type == "VERTICAL":
        if vertical is None:
            errors.append("输入类型为 VERTICAL 时必须填垂直离底高度")
        elif vertical <= 0:
            errors.append("垂直离底高度必须 > 0")
        data["vertical_bottom_clearance_m"] = vertical
        data["axis_slant_m"] = None
    elif input_type == "AXIS_SLANT":
        if axis is None:
            errors.append("输入类型为 AXIS_SLANT 时必须填中心轴斜距")
        elif axis <= 0:
            errors.append("中心轴斜距必须 > 0")
        data["vertical_bottom_clearance_m"] = None
        data["axis_slant_m"] = axis
    else:
        if vertical is not None or axis is not None:
            errors.append("输入类型为 UNKNOWN 时不得填具体离底数值")
        data["vertical_bottom_clearance_m"] = None
        data["axis_slant_m"] = None

    tilt = _parse_number(form, "downward_tilt_deg", "倾角", errors)
    tilt = None if tilt is _INVALID else tilt
    if tilt is not None and not (-90 <= tilt <= 90):
        errors.append("倾角须在 [-90, 90]（相对水平面向下为正）")
    data["downward_tilt_deg"] = tilt
    data["tilt_reference"] = (form.get("tilt_reference") or "").strip() or None

    beam_value = _parse_number(form, "beam_angle_value_deg", "波束角数值", errors)
    beam_value = None if beam_value is _INVALID else beam_value
    beam_kind = (form.get("beam_angle_kind") or "UNKNOWN").strip().upper()
    if beam_kind not in ("FULL", "HALF", "UNKNOWN"):
        errors.append("波束角类型必须为 FULL / HALF / UNKNOWN")
    if beam_value is not None:
        if beam_kind == "FULL" and not (0 < beam_value < 180):
            errors.append("全角须在 (0, 180)")
        if beam_kind == "HALF" and not (0 < beam_value < 90):
            errors.append("半角 β 须在 (0, 90)")
        if beam_kind == "UNKNOWN":
            errors.append("填写波束角数值时必须显式选择 FULL 或 HALF")
    data["beam_angle_value_deg"] = beam_value
    data["beam_angle_kind"] = beam_kind

    heading = _parse_number(form, "heading_deg", "方位角", errors)
    heading = None if heading is _INVALID else heading
    if heading is not None and not (0 <= heading < 360):
        errors.append("方位角须在 [0, 360)（真北 0°、顺时针）")
    data["heading_deg"] = heading
    data["heading_reference"] = (form.get("heading_reference") or "").strip() or None

    data["measurement_method"] = (form.get("measurement_method") or "").strip() or None
    data["uncertainty"] = (form.get("uncertainty") or "").strip() or None
    data["source"] = (form.get("source") or "").strip()
    if not data["source"]:
        errors.append("参数来源必填（可追溯性要求）")
    data["change_reason"] = (form.get("change_reason") or "").strip() or None

    eff = (form.get("effective_from") or "").strip()
    if not eff:
        errors.append("生效起始日期必填")
    data["effective_from"] = eff

    if errors:
        raise ValidationError(errors)

    # 派生计算（标记 is_derived，不写回用户输入）
    data["derived_vertical_clearance_m"] = None
    data["derived_axis_slant_m"] = None
    data["derivation_tilt_deg"] = None
    data["is_derived"] = 0
    if data["clearance_input_type"] in ("VERTICAL", "AXIS_SLANT") and tilt:
        src_val = data["vertical_bottom_clearance_m"] or data["axis_slant_m"]
        derived = derive_from_tilt(src_val, tilt, data["clearance_input_type"])
        data["derivation_tilt_deg"] = tilt
        if data["clearance_input_type"] == "VERTICAL":
            data["derived_axis_slant_m"] = derived
        else:
            data["derived_vertical_clearance_m"] = derived
        data["is_derived"] = 1 if derived is not None else 0

    full_angle, half_angle = beam_angles(beam_value, beam_kind)
    data["beam_full_angle_deg"] = full_angle
    data["beam_half_angle_deg"] = half_angle
    return data


def current_version(conn: sqlite3.Connection, device_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT v.* FROM device_parameters p
           JOIN device_parameter_versions v ON v.parameter_id = p.current_parameter_id
           WHERE p.device_id = ?""",
        (device_id,),
    ).fetchone()


def device_range_m(conn: sqlite3.Connection, device_id: str) -> float | None:
    """本台量程（devices.range_m）；UNKNOWN 返回 None。"""
    row = conn.execute("SELECT range_m FROM devices WHERE device_id = ?", (device_id,)).fetchone()
    return row["range_m"] if row and row["range_m"] is not None else None


def save_param(conn: sqlite3.Connection, device_id: str, form: dict, expected_version: int) -> int:
    """保存为新版本；expected_version 与当前版本不符 → ConflictError（HTTP 409）。"""
    cur = current_version(conn, device_id)
    cur_num = cur["version"] if cur else 0
    if cur_num != expected_version:
        raise ConflictError(expected_version, cur_num)

    range_m = device_range_m(conn, device_id)
    data = validate_param_form(form, range_m=range_m)
    if cur and cur["effective_to"] is None and data["effective_from"] < cur["effective_from"]:
        raise ValidationError([f"新版本生效日期 {data['effective_from']} 早于当前版本生效日期 {cur['effective_from']}"])

    nxt = cur_num + 1
    cur_row = conn.execute(
        """INSERT INTO device_parameter_versions
           (device_id, version, clearance_input_type, vertical_bottom_clearance_m, axis_slant_m,
            derived_vertical_clearance_m, derived_axis_slant_m, derivation_tilt_deg, is_derived,
            analysis_cutoff_slant_m, downward_tilt_deg, tilt_reference,
            beam_angle_value_deg, beam_angle_kind, beam_full_angle_deg, beam_half_angle_deg,
            heading_deg, heading_reference, measurement_method, uncertainty, source, change_reason,
            effective_from, created_at, created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            device_id, nxt, data["clearance_input_type"],
            data["vertical_bottom_clearance_m"], data["axis_slant_m"],
            data["derived_vertical_clearance_m"], data["derived_axis_slant_m"],
            data["derivation_tilt_deg"], data["is_derived"],
            data["analysis_cutoff_slant_m"], data["downward_tilt_deg"], data["tilt_reference"],
            data["beam_angle_value_deg"], data["beam_angle_kind"],
            data["beam_full_angle_deg"], data["beam_half_angle_deg"],
            data["heading_deg"], data["heading_reference"],
            data["measurement_method"], data["uncertainty"], data["source"], data["change_reason"],
            data["effective_from"], _now(), current_operator(),
        ),
    )
    # 关闭旧版本的生效区间（不改旧版本任何数值列）
    if cur:
        conn.execute(
            "UPDATE device_parameter_versions SET effective_to = ? WHERE parameter_id = ? AND effective_to IS NULL",
            (data["effective_from"], cur["parameter_id"]),
        )
    conn.execute(
        """INSERT INTO device_parameters (device_id, current_parameter_id, updated_at) VALUES (?,?,?)
           ON CONFLICT(device_id) DO UPDATE SET current_parameter_id = excluded.current_parameter_id,
           updated_at = excluded.updated_at""",
        (device_id, cur_row.lastrowid, _now()),
    )
    conn.execute(
        "INSERT INTO audit_logs (action, entity, entity_id, detail_json, actor, created_at) "
        "VALUES (?,?,?,?,?,?)",
        ("SAVE_PARAM", "device_parameter_versions", device_id,
         json.dumps({"new_version": nxt, "expected_version": expected_version,
                     "effective_from": data["effective_from"],
                     "cutoff_limit": {"range_m": range_m, "fallback_m": None if range_m else CUTOFF_FALLBACK_MAX_M}},
                     ensure_ascii=False), current_operator(), _now()),
    )
    return nxt


def validate_position_form(form: dict) -> dict:
    errors: list[str] = []
    lon = _parse_number(form, "longitude_deg", "经度", errors)
    lat = _parse_number(form, "latitude_deg", "纬度", errors)
    lon = None if lon is _INVALID else lon
    lat = None if lat is _INVALID else lat
    if lon is None:
        errors.append("经度必填且在 [-180, 180]")
    elif not (-180 <= lon <= 180):
        errors.append("经度必填且在 [-180, 180]")
    if lat is None:
        errors.append("纬度必填且在 [-90, 90]")
    elif not (-90 <= lat <= 90):
        errors.append("纬度必填且在 [-90, 90]")
    crs = (form.get("coordinate_reference_system") or "").strip() or None  # 不默认 WGS84
    accuracy = _parse_number(form, "position_accuracy_m", "定位精度", errors)
    accuracy = None if accuracy is _INVALID else accuracy
    if accuracy is not None and accuracy <= 0:
        errors.append("定位精度必须 > 0（米）")
    heading = _parse_number(form, "heading_deg", "方位角", errors)
    heading = None if heading is _INVALID else heading
    if heading is not None and not (0 <= heading < 360):
        errors.append("方位角须在 [0, 360)")
    source = (form.get("position_source") or "").strip()
    if not source:
        errors.append("位置来源必填")
    eff = (form.get("effective_from") or "").strip()
    if not eff:
        errors.append("生效起始日期必填")
    if errors:
        raise ValidationError(errors)
    return {
        "longitude_deg": lon, "latitude_deg": lat,
        "coordinate_reference_system": crs, "position_accuracy_m": accuracy,
        "heading_deg": heading,
        "heading_reference": (form.get("heading_reference") or "").strip() or None,
        "position_source": source,
        "effective_from": eff,
        "notes": (form.get("notes") or "").strip() or None,
    }


def current_position(conn: sqlite3.Connection, device_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM device_positions WHERE device_id = ? ORDER BY version DESC LIMIT 1",
        (device_id,),
    ).fetchone()


def save_position(conn: sqlite3.Connection, device_id: str, form: dict, expected_version: int) -> int:
    cur = current_position(conn, device_id)
    cur_num = cur["version"] if cur else 0
    if cur_num != expected_version:
        raise ConflictError(expected_version, cur_num)
    data = validate_position_form(form)
    nxt = cur_num + 1
    conn.execute(
        """INSERT INTO device_positions
           (device_id, version, longitude_deg, latitude_deg, coordinate_reference_system,
            position_accuracy_m, position_source, heading_deg, heading_reference,
            effective_from, notes, created_at, created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (device_id, nxt, data["longitude_deg"], data["latitude_deg"],
         data["coordinate_reference_system"], data["position_accuracy_m"], data["position_source"],
         data["heading_deg"], data["heading_reference"], data["effective_from"],
         data["notes"], _now(), current_operator()),
    )
    if cur and cur["effective_to"] is None:
        conn.execute(
            "UPDATE device_positions SET effective_to = ? WHERE position_id = ? AND effective_to IS NULL",
            (data["effective_from"], cur["position_id"]),
        )
    conn.execute(
        "INSERT INTO audit_logs (action, entity, entity_id, detail_json, actor, created_at) "
        "VALUES (?,?,?,?,?,?)",
        ("SAVE_POSITION", "device_positions", device_id,
         json.dumps({"new_version": nxt, "expected_version": expected_version}, ensure_ascii=False),
         current_operator(), _now()),
    )
    return nxt


def list_devices_with_status(conn: sqlite3.Connection) -> list[dict]:
    """首页/K01：五台清单 + 未知设备队列（缺哪些项一目了然）。"""
    devices = conn.execute("SELECT * FROM devices ORDER BY device_id").fetchall()
    result = []
    for d in devices:
        param = current_version(conn, d["device_id"])
        pos = current_position(conn, d["device_id"])
        missing = []
        if param is None:
            missing = ["全部分析参数"]
        else:
            if param["analysis_cutoff_slant_m"] is None:
                missing.append("分析截断斜距")
            if param["clearance_input_type"] == "UNKNOWN":
                missing.append("离底参考")
            if param["downward_tilt_deg"] is None:
                missing.append("倾角")
            if param["beam_angle_kind"] == "UNKNOWN":
                missing.append("波束角类型")
            if param["heading_deg"] is None:
                missing.append("方位角")
        if pos is None:
            missing.append("经纬度")
        else:
            if pos["coordinate_reference_system"] is None:
                missing.append("坐标系")
            if pos["position_accuracy_m"] is None:
                missing.append("定位精度")
            if pos["heading_deg"] is None:
                missing.append("方位角(位置)")
        result.append({
            "device_id": d["device_id"],
            "status": d["status"],
            "station_id": d["station_id"],  # P2-1：NULL = 未分配（禁止伪造站位名称/坐标）
            "param": dict(param) if param else None,
            "position": dict(pos) if pos else None,
            "missing": missing,
            "complete": not missing,
        })
    return result


def param_history(conn: sqlite3.Connection, device_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM device_parameter_versions WHERE device_id = ? ORDER BY version DESC",
        (device_id,),
    ).fetchall()


def position_history(conn: sqlite3.Connection, device_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM device_positions WHERE device_id = ? ORDER BY version DESC",
        (device_id,),
    ).fetchall()
