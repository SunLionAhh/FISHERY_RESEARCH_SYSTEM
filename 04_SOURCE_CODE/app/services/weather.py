# -*- coding: utf-8 -*-
"""每日观测天气服务：按 (device_id, observation_date) 一条，可更正、留审计。

- 天气为界面自定义扩展项（规范未定义），是人工观测的环境描述，不随声学 CSV 导入；
- 同一天同一设备重复录入视为更正：覆盖当天天气值并写审计日志，不生成版本链
  （与设备参数的不可变版本链区分，天气更正不改变历史声学统计结果）；
- 天气码封闭枚举，非法值/非法日期一律字段级 ValidationError，不抛 500、不静默入库。
"""
import json
import re
import sqlite3
from datetime import datetime, timezone

from ..identity import current_operator

# 天气码 → 中文显示。界面下拉与后端校验共用，避免前后端枚举漂移。
WEATHER_CODES = {
    "SUNNY": "晴天",
    "CLOUDY": "阴天",
    "RAINY": "阴雨天",
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_weather_form(form: dict) -> dict:
    """校验天气录入表单，返回规范化数据；非法值字段级报错，不抛 500。"""
    errors: list[str] = []

    date = (form.get("observation_date") or "").strip()
    if not _DATE_RE.match(date):
        errors.append("观测日期格式必须为 YYYY-MM-DD（如 2026-11-01）")
    else:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            errors.append(f"观测日期不是有效日历日期（收到“{date}”）")

    code = (form.get("weather_code") or "").strip().upper()
    if code not in WEATHER_CODES:
        allowed = "/".join(WEATHER_CODES)
        errors.append(f"天气必须为 {allowed}（收到“{code or '空'}”）")

    source = (form.get("source") or "").strip()
    if not source:
        errors.append("天气来源必填（可追溯性要求）")

    if errors:
        raise ValidationError(errors)

    return {
        "observation_date": date,
        "weather_code": code,
        "source": source,
        "notes": (form.get("notes") or "").strip() or None,
    }


def save_weather(conn: sqlite3.Connection, device_id: str, form: dict) -> tuple[str, bool]:
    """保存某设备某天的天气；返回 (观测日期, 是否覆盖更正)。

    同一天同设备重复录入 → 覆盖天气码/来源/备注/更新时间，写 CORRECT_WEATHER 审计；
    首次录入 → INSERT，写 SAVE_WEATHER 审计。两者都在同一事务内（由调用方 commit）。
    """
    data = validate_weather_form(form)
    date, code = data["observation_date"], data["weather_code"]

    existing = conn.execute(
        "SELECT weather_id FROM daily_weather WHERE device_id = ? AND observation_date = ?",
        (device_id, date),
    ).fetchone()
    is_correction = existing is not None
    now = _now()

    if is_correction:
        conn.execute(
            """UPDATE daily_weather
               SET weather_code = ?, source = ?, notes = ?, updated_at = ?, created_by = ?
               WHERE weather_id = ?""",
            (code, data["source"], data["notes"], now, current_operator(), existing["weather_id"]),
        )
    else:
        conn.execute(
            """INSERT INTO daily_weather
               (device_id, observation_date, weather_code, source, notes, created_at, created_by, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (device_id, date, code, data["source"], data["notes"],
             now, current_operator(), now),
        )

    conn.execute(
        "INSERT INTO audit_logs (action, entity, entity_id, detail_json, actor, created_at) "
        "VALUES (?,?,?,?,?,?)",
        ("CORRECT_WEATHER" if is_correction else "SAVE_WEATHER", "daily_weather", device_id,
         json.dumps({"observation_date": date, "weather_code": code,
                     "label": WEATHER_CODES[code], "source": data["source"]},
                    ensure_ascii=False),
         current_operator(), now),
    )
    return date, is_correction


def weather_history(conn: sqlite3.Connection, device_id: str) -> list[sqlite3.Row]:
    """某设备的天气历史，按日期倒序。"""
    return conn.execute(
        "SELECT * FROM daily_weather WHERE device_id = ? ORDER BY observation_date DESC",
        (device_id,),
    ).fetchall()
