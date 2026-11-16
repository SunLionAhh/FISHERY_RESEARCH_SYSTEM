# -*- coding: utf-8 -*-
"""S01 验收整改测试（ACCEPTANCE_S00_S01.md D1-1/D1-2/D1-3 + P2-1/P2-2/P2-3）。

不修改既有断言、不放宽期望值；全部为新增用例。
"""
import math
import re
import sqlite3
from pathlib import Path

import pytest

import app.db as dbmod
from app import identity
from app.db import connect, split_sql_statements
from app.services import devices as svc
from app.services.devices import ValidationError

ROOT = Path(__file__).resolve().parents[1]  # 04_SOURCE_CODE
LOCK_FILE = ROOT / "requirements-lock.txt"
REQ_FILE = ROOT / "requirements.txt"

VALID_PARAM = {
    "analysis_cutoff_slant_m": "5.2",
    "clearance_input_type": "VERTICAL",
    "vertical_bottom_clearance_m": "3.5",
    "axis_slant_m": "",
    "downward_tilt_deg": "45",
    "tilt_reference": "USER_PROVIDED",
    "beam_angle_value_deg": "15",
    "beam_angle_kind": "FULL",
    "heading_deg": "",
    "heading_reference": "",
    "measurement_method": "USER_PROVIDED",
    "uncertainty": "",
    "source": "TEST_FIX",
    "change_reason": "fix test",
    "effective_from": "2026-10-31",
}


def make_form(**overrides):
    form = dict(VALID_PARAM)
    form.update(overrides)
    return form


def _param_rows(conn, device_id="2003"):
    return conn.execute(
        "SELECT COUNT(*) n FROM device_parameter_versions WHERE device_id=?", (device_id,)
    ).fetchone()["n"]


# ---------------- D1-1：截断数值必须有限、越量程拒绝 ----------------

@pytest.mark.parametrize("bad,expect_fragment", [
    ("NaN", "有限数值"),
    ("nan", "有限数值"),
    ("inf", "有限数值"),
    ("Infinity", "有限数值"),
    ("-inf", "有限数值"),
    ("1e999", "有限数值"),   # float() 溢出为 inf
    ("abc", "必须为数字"),
    ("5.2m", "必须为数字"),
    ("0", "必须 &gt; 0"),          # HTML 中 > 被转义
    ("-1", "必须 &gt; 0"),
    ("520", "量程 UNKNOWN，按上限 100 m 临时校验"),  # cm 当 m，明显越量程
    ("1e9", "量程 UNKNOWN，按上限 100 m 临时校验"),
])
def test_k13_cutoff_invalid_values_rejected_400(client, conn, bad, expect_fragment):
    before = _param_rows(conn)
    resp = client.post("/devices/2003/params",
                       data=make_form(analysis_cutoff_slant_m=bad, expected_version="0"))
    assert resp.status_code == 400, f"截断={bad!r} 应 400，实际 {resp.status_code}"
    body = resp.get_data(as_text=True)
    assert "人工分析截断斜距" in body, "错误提示必须定位到字段"
    assert expect_fragment in body
    # 非法提交不得静默入库
    assert _param_rows(conn) == before


def test_k13_vertical_nan_rejected_400(client, conn):
    before = _param_rows(conn)
    resp = client.post("/devices/2003/params", data=make_form(
        vertical_bottom_clearance_m="NaN", expected_version="0"))
    assert resp.status_code == 400
    assert "垂直离底高度" in resp.get_data(as_text=True)
    assert "有限数值" in resp.get_data(as_text=True)
    assert _param_rows(conn) == before


@pytest.mark.parametrize("field,label", [
    ("axis_slant_m", "中心轴斜距"),
    ("downward_tilt_deg", "倾角"),
    ("beam_angle_value_deg", "波束角数值"),
    ("heading_deg", "方位角"),
])
def test_k13_other_numeric_fields_nan_rejected_400(client, field, label):
    overrides = {field: "inf"}
    if field == "axis_slant_m":
        overrides["clearance_input_type"] = "AXIS_SLANT"
        overrides["vertical_bottom_clearance_m"] = ""
    resp = client.post("/devices/2003/params", data=make_form(expected_version="0", **overrides))
    assert resp.status_code == 400
    assert label in resp.get_data(as_text=True)


def test_k13_position_nan_inf_rejected_400(client):
    for bad in ("NaN", "inf", "abc"):
        resp = client.post("/devices/2003/position", data={
            "longitude_deg": bad, "latitude_deg": "27.99", "coordinate_reference_system": "",
            "position_accuracy_m": "", "heading_deg": "", "heading_reference": "",
            "position_source": "TEST_FIX", "effective_from": "2026-10-31",
            "expected_version": "0", "notes": ""})
        assert resp.status_code == 400, f"经度={bad!r} 应 400"
        assert "经度" in resp.get_data(as_text=True)


def test_k13_position_accuracy_and_lat_checked(client):
    resp = client.post("/devices/2003/position", data={
        "longitude_deg": "121.2", "latitude_deg": "inf", "coordinate_reference_system": "",
        "position_accuracy_m": "NaN", "heading_deg": "", "heading_reference": "",
        "position_source": "TEST_FIX", "effective_from": "2026-10-31",
        "expected_version": "0", "notes": ""})
    assert resp.status_code == 400
    body = resp.get_data(as_text=True)
    assert "纬度" in body and "定位精度" in body


def test_cutoff_bound_uses_device_range_when_known(conn):
    """量程已知时优先用 devices.range_m；超出即拒绝，不再走 100 m 兜底。"""
    conn.execute("UPDATE devices SET range_m=37.5 WHERE device_id='2003'")
    conn.commit()
    with pytest.raises(ValidationError) as exc:
        svc.validate_param_form(make_form(analysis_cutoff_slant_m="40"),
                                range_m=svc.device_range_m(conn, "2003"))
    assert "本台量程" in str(exc.value)
    data = svc.validate_param_form(make_form(), range_m=37.5)
    assert data["analysis_cutoff_slant_m"] == pytest.approx(5.2)


# ---------------- D1-1：expected_version 非整数不得 500 ----------------

@pytest.mark.parametrize("bad_version", ["abc", "", "1.5", "-1", "  "])
def test_expected_version_invalid_rejected_400_params(client, bad_version):
    resp = client.post("/devices/2003/params",
                       data=make_form(expected_version=bad_version))
    assert resp.status_code == 400, f"expected_version={bad_version!r} 应 400"
    assert "预期版本号非法" in resp.get_data(as_text=True)


@pytest.mark.parametrize("bad_version", ["abc", ""])
def test_expected_version_invalid_rejected_400_position(client, bad_version):
    resp = client.post("/devices/2003/position", data={
        "longitude_deg": "121.2", "latitude_deg": "27.99", "coordinate_reference_system": "",
        "position_accuracy_m": "", "heading_deg": "", "heading_reference": "",
        "position_source": "TEST_FIX", "effective_from": "2026-10-31",
        "expected_version": bad_version, "notes": ""})
    assert resp.status_code == 400
    assert "预期版本号非法" in resp.get_data(as_text=True)


# ---------------- P2-2：预览接口 ----------------

def test_preview_tolerates_empty_cutoff(client):
    """无参数设备预览：截断未填写 → 200，派生值与 β 照常，截断返回 null。"""
    resp = client.get("/devices/2002/params/preview", query_string={
        "clearance_input_type": "VERTICAL", "vertical_bottom_clearance_m": "3.5",
        "downward_tilt_deg": "45", "beam_angle_value_deg": "15", "beam_angle_kind": "FULL",
        "analysis_cutoff_slant_m": "", "source": "preview", "effective_from": "2026-10-31"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["analysis_cutoff_slant_m_will_be"] is None
    assert "截断未填写" in body["note"]
    assert body["derived_axis_slant_m"] == pytest.approx(3.5 / math.sin(math.radians(45)), abs=1e-6)
    assert body["beam_half_angle_deg"] == pytest.approx(7.5)


def test_preview_invalid_value_returns_400_json(client):
    resp = client.get("/devices/2002/params/preview", query_string={
        "clearance_input_type": "VERTICAL", "vertical_bottom_clearance_m": "3.5",
        "downward_tilt_deg": "45", "beam_angle_value_deg": "15", "beam_angle_kind": "FULL",
        "analysis_cutoff_slant_m": "NaN", "source": "preview", "effective_from": "2026-10-31"})
    assert resp.status_code == 400
    assert resp.is_json and resp.get_json()["ok"] is False
    assert any("人工分析截断斜距" in e for e in resp.get_json()["errors"])


def test_preview_link_does_not_borrow_5_2(client):
    """P2-2：2002/2003/2005 的预览链接不得出现 analysis_cutoff_slant_m=5.2。"""
    for device_id in ("2002", "2003", "2005"):
        html = client.get(f"/devices/{device_id}").get_data(as_text=True)
        assert "analysis_cutoff_slant_m=5.2" not in html, f"{device_id} 预览链接不得借用 5.2"
    html_2000 = client.get("/devices/2000").get_data(as_text=True)
    assert "analysis_cutoff_slant_m=5.2" in html_2000  # 2000 自己的值可预填


# ---------------- D1-2：依赖锁文件可用性 ----------------

def test_requirements_lock_is_parseable_multiline():
    raw = LOCK_FILE.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf", "锁文件不得带 UTF-8 BOM"
    text = raw.decode("utf-8")
    assert "\r\n" not in text, "换行必须为 LF"
    lines = [ln for ln in text.split("\n") if ln.strip()]
    assert len(lines) >= 30, f"锁文件行数应 ≥30，实际 {len(lines)}"
    pattern = re.compile(r"^[A-Za-z0-9_.\-]+==\S+$")
    bad = [ln for ln in lines if not pattern.match(ln)]
    assert not bad, f"格式非法行：{bad[:5]}"
    assert any(ln.lower().startswith("flask==") for ln in lines)


def test_runtime_requirements_file_exists():
    text = REQ_FILE.read_text(encoding="utf-8")
    names = {ln.split("==")[0].strip().lower() for ln in text.splitlines()
             if ln.strip() and not ln.strip().startswith("#")}
    assert {"flask", "python-dotenv", "requests"} <= names


# ---------------- D1-3：迁移原子性 ----------------

def test_split_sql_handles_comments_and_strings():
    sql = (
        "-- 注释里的分号; 不应切分\n"
        "CREATE TABLE t (v TEXT DEFAULT 'a;b');\n"
        "INSERT INTO t (v) VALUES ('x;y');\n"
    )
    stmts = split_sql_statements(sql)
    assert len(stmts) == 2
    assert stmts[0].startswith("--")


def test_bad_migration_rolls_back_atomically(tmp_path, monkeypatch):
    """坏迁移：先建表/插入，再执行必错语句 → 全部回滚，schema_migrations 无记录，既有数据不损。"""
    db_file = tmp_path / "bad_migration.db"
    conn = connect(db_file)
    conn.execute("CREATE TABLE preexisting (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO preexisting (v) VALUES ('keep-me')")
    conn.commit()

    mig_dir = tmp_path / "migrations_bad"
    mig_dir.mkdir()
    (mig_dir / "0001_bad.sql").write_text(
        "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL);\n"
        "CREATE TABLE half_a (x INTEGER);\n"
        "INSERT INTO half_a VALUES (1);\n"
        "CREATE TABLE half_b (y INTEGER);\n"
        "INSERT INTO no_such_table VALUES (1);\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dbmod, "MIGRATIONS_DIR", mig_dir)

    with pytest.raises(sqlite3.OperationalError):
        dbmod.migrate(conn)

    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "half_a" not in tables, "失败迁移建的表必须回滚"
    assert "half_b" not in tables
    assert "schema_migrations" not in tables, "schema_migrations 也不得残留"
    # 既有数据未受破坏
    assert conn.execute("SELECT v FROM preexisting").fetchone()["v"] == "keep-me"
    conn.close()


def test_good_migration_after_bad_one_still_applies(tmp_path, monkeypatch):
    """坏迁移回滚后，修正版迁移可正常落地（不残留半套对象阻塞后续）。"""
    db_file = tmp_path / "recover.db"
    conn = connect(db_file)
    mig_dir = tmp_path / "migrations_ok"
    mig_dir.mkdir()
    (mig_dir / "0001_ok.sql").write_text(
        "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL);\n"
        "CREATE TABLE ok_table (x INTEGER);\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dbmod, "MIGRATIONS_DIR", mig_dir)
    applied = dbmod.migrate(conn)
    assert applied == ["0001"]
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ok_table'").fetchone()
    conn.close()


# ---------------- P2-1：station_id ----------------

def test_devices_have_station_id_column_and_unassigned(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(devices)")}
    assert "station_id" in cols, "任务二要求每台独立保存 station_id"
    rows = conn.execute("SELECT device_id, station_id FROM devices ORDER BY device_id").fetchall()
    assert all(r["station_id"] is None for r in rows), "站位未提供时必须 NULL，禁止伪造"
    assert conn.execute("SELECT COUNT(*) n FROM stations").fetchone()["n"] == 0


def test_device_page_shows_station_unassigned(client):
    html = client.get("/devices/2000").get_data(as_text=True)
    assert "站位：未分配" in html


# ---------------- P2-3：操作者 ----------------

def test_operator_recorded_not_hardcoded_web(conn):
    svc.save_param(conn, "2003", make_form(), expected_version=0)
    conn.commit()
    row = conn.execute(
        "SELECT created_by FROM device_parameter_versions WHERE device_id='2003' ORDER BY version DESC"
    ).fetchone()
    operator = identity.current_operator()
    assert row["created_by"] == operator
    assert row["created_by"] != "web"
    audit = conn.execute(
        "SELECT actor FROM audit_logs WHERE action='SAVE_PARAM' AND entity_id='2003' ORDER BY audit_id DESC"
    ).fetchone()
    assert audit["actor"] == operator
    # 种子数据仍登记 seed（不伪装成网页操作）
    seed_row = conn.execute(
        "SELECT created_by FROM device_parameter_versions WHERE device_id='2000' AND version=1"
    ).fetchone()
    assert seed_row["created_by"] == "seed"


# ---------------- 回归：已通过项不被破坏 ----------------

def test_regression_2000_values_untouched(conn):
    cur = svc.current_version(conn, "2000")
    assert cur["analysis_cutoff_slant_m"] == pytest.approx(5.2)
    assert cur["vertical_bottom_clearance_m"] == pytest.approx(3.68)
    assert cur["downward_tilt_deg"] == pytest.approx(45.0)
    assert cur["beam_angle_kind"] == "FULL"
    assert cur["beam_half_angle_deg"] == pytest.approx(7.5)
    assert cur["derived_axis_slant_m"] == pytest.approx(3.68 / math.sin(math.radians(45)), abs=1e-6)
    assert cur["derived_axis_slant_m"] != cur["analysis_cutoff_slant_m"]


def test_regression_unknown_devices_stay_unknown(conn):
    for device_id in ("2002", "2003", "2005"):
        assert svc.current_version(conn, device_id) is None
        n = conn.execute(
            "SELECT COUNT(*) n FROM device_parameter_versions WHERE device_id=?", (device_id,)
        ).fetchone()["n"]
        assert n == 0
