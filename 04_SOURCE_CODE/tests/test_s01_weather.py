# -*- coding: utf-8 -*-
"""每日观测天气测试：迁移建表 / 合法保存回读 / 非法输入拒绝 / 同日更正 / 审计。"""
import pytest

from app.services import weather as wx
from app.services.weather import ValidationError

VALID = {
    "observation_date": "2026-11-01",
    "weather_code": "SUNNY",
    "source": "USER_FIELD_OBSERVATION",
    "notes": "现场记录",
}


def make_form(**overrides):
    form = dict(VALID)
    form.update(overrides)
    return form


# ---------- 迁移建表 ----------

def test_migration_creates_daily_weather(conn):
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "daily_weather" in tables
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(daily_weather)")}
    assert {"weather_id", "device_id", "observation_date", "weather_code",
            "source", "notes", "created_at", "created_by", "updated_at"} <= cols


# ---------- 枚举与中文映射 ----------

def test_weather_codes_three_options():
    assert wx.WEATHER_CODES == {"SUNNY": "晴天", "CLOUDY": "阴天", "RAINY": "阴雨天"}


# ---------- 合法保存与回读 ----------

def test_save_and_readback(conn):
    date, corrected = wx.save_weather(conn, "2000", make_form())
    conn.commit()
    assert date == "2026-11-01" and corrected is False
    hist = wx.weather_history(conn, "2000")
    assert len(hist) == 1
    assert hist[0]["weather_code"] == "SUNNY"
    assert hist[0]["source"] == "USER_FIELD_OBSERVATION"
    assert hist[0]["notes"] == "现场记录"


def test_case_insensitive_code(conn):
    wx.save_weather(conn, "2001", make_form(weather_code="rainy"))
    conn.commit()
    row = wx.weather_history(conn, "2001")[0]
    assert row["weather_code"] == "RAINY"


# ---------- 同日更正：覆盖不新增，写 CORRECT 审计 ----------

def test_same_day_correction_overwrites(conn):
    wx.save_weather(conn, "2000", make_form(weather_code="SUNNY"))
    conn.commit()
    date, corrected = wx.save_weather(conn, "2000", make_form(weather_code="RAINY", notes="改阴雨"))
    conn.commit()
    assert corrected is True
    hist = wx.weather_history(conn, "2000")
    assert len(hist) == 1  # 不新增行
    assert hist[0]["weather_code"] == "RAINY"
    assert hist[0]["notes"] == "改阴雨"
    actions = [r["action"] for r in conn.execute(
        "SELECT action FROM audit_logs WHERE entity='daily_weather' ORDER BY audit_id")]
    assert actions == ["SAVE_WEATHER", "CORRECT_WEATHER"]


def test_different_days_coexist(conn):
    wx.save_weather(conn, "2000", make_form(observation_date="2026-11-01"))
    wx.save_weather(conn, "2000", make_form(observation_date="2026-11-02", weather_code="CLOUDY"))
    conn.commit()
    hist = wx.weather_history(conn, "2000")
    assert [w["observation_date"] for w in hist] == ["2026-11-02", "2026-11-01"]  # 倒序


# ---------- 设备隔离 ----------

def test_devices_isolated(conn):
    wx.save_weather(conn, "2000", make_form(weather_code="SUNNY"))
    wx.save_weather(conn, "2001", make_form(weather_code="CLOUDY"))
    conn.commit()
    assert wx.weather_history(conn, "2000")[0]["weather_code"] == "SUNNY"
    assert wx.weather_history(conn, "2001")[0]["weather_code"] == "CLOUDY"
    assert wx.weather_history(conn, "2002") == []


# ---------- 非法输入字段级拒绝 ----------

@pytest.mark.parametrize("overrides,fragment", [
    ({"weather_code": "SNOW"}, "天气必须为"),
    ({"weather_code": ""}, "天气必须为"),
    ({"observation_date": "2026/11/01"}, "YYYY-MM-DD"),
    ({"observation_date": "2026-02-30"}, "有效日历日期"),
    ({"observation_date": ""}, "YYYY-MM-DD"),
    ({"source": ""}, "天气来源必填"),
])
def test_invalid_form_rejected(overrides, fragment):
    with pytest.raises(ValidationError) as e:
        wx.validate_weather_form(make_form(**overrides))
    assert any(fragment in msg for msg in e.value.errors)


def test_web_invalid_returns_400(client):
    resp = client.post("/devices/2000/weather", data=make_form(weather_code="SNOW"))
    assert resp.status_code == 400
    assert "天气必须为" in resp.get_data(as_text=True)


# ---------- Web 端到端：保存后回显 ----------

def test_web_save_and_page_shows_label(client, conn):
    resp = client.post("/devices/2000/weather", data=make_form(weather_code="CLOUDY"))
    assert resp.status_code == 302
    html = client.get("/devices/2000").get_data(as_text=True)
    assert "2026-11-01" in html
    assert "阴天" in html
    assert "每日观测天气" in html


def test_web_unknown_device_404(client):
    assert client.post("/devices/2004/weather", data=make_form()).status_code == 404
