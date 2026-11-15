# -*- coding: utf-8 -*-
"""S01 验收测试：K01—K03 / K13 / K15(前置) / K19 / GEO-01 / GEO-03 + 任务三/四/五/六/七/八。

测试值 P1—P5 按规范任务七：3.20 / 3.50 / 3.68 / 3.80 / 4.00（仅测试值，非正式参数）。
"""
import math
import sqlite3

import pytest

from app.db import connect
from app.services import devices as svc
from app.services.devices import ConflictError, ValidationError

EXPECTED_TABLES = {
    "devices", "stations", "device_parameters", "device_parameter_versions",
    "device_installations", "bottom_references", "file_registry", "import_batches",
    "analysis_runs", "datasets", "dataset_members", "audit_logs",
}
DEVICE_IDS = ["2000", "2001", "2002", "2003", "2005"]
P_VALUES = {"2000": 3.20, "2001": 3.50, "2002": 3.68, "2003": 3.80, "2005": 4.00}

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
    "source": "TEST",
    "change_reason": "test",
    "effective_from": "2026-10-31",
}


def make_form(**overrides):
    form = dict(VALID_PARAM)
    form.update(overrides)
    return form


# ---------- 任务一：迁移机制 ----------

def test_migration_creates_twelve_tables_and_idempotent(tmp_path):
    from app import create_app
    db = tmp_path / "rerun.db"
    create_app(db)  # 第一次：迁移 + 播种
    with connect(db) as c:
        tables = {r["name"] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= tables
    assert "schema_migrations" in tables
    # 重复迁移幂等（create 第二次不报错、不重复播种）
    create_app(db)
    with connect(db) as c:
        assert c.execute("SELECT COUNT(*) n FROM devices").fetchone()["n"] == 5
        assert c.execute("SELECT COUNT(*) n FROM device_parameter_versions").fetchone()["n"] == 2
        assert c.execute("SELECT COUNT(*) n FROM file_registry").fetchone()["n"] == 21


# ---------- 任务二 + K01：五台清单与未知队列 ----------

def test_k01_five_devices_no_2004_and_unknown_queue(client, conn):
    rows = [r["device_id"] for r in conn.execute("SELECT device_id FROM devices ORDER BY device_id")]
    assert rows == DEVICE_IDS
    assert "2004" not in rows
    html = client.get("/").get_data(as_text=True)
    assert "2002" in html and "/devices/2004" not in html  # 2004 无设备链接（页面文案可提及"无 2004"）
    # 2002/2003/2005 无参数 → 未知队列出现「全部分析参数」
    assert "全部分析参数" in html
    # 2000/2001 截断 5.2 已显示
    assert "5.2" in html


# ---------- 任务七 + K02：五台参数独立（P1—P5） ----------

def _set_param(conn, device_id, **overrides):
    form = make_form(**overrides)
    cur = svc.current_version(conn, device_id)
    expected = cur["version"] if cur else 0
    return svc.save_param(conn, device_id, form, expected)


def test_k02_five_devices_independent_p1_p5(conn):
    for device_id, p in P_VALUES.items():
        _set_param(conn, device_id, vertical_bottom_clearance_m=str(p))
    conn.commit()
    for device_id, p in P_VALUES.items():
        cur = svc.current_version(conn, device_id)
        assert cur["vertical_bottom_clearance_m"] == pytest.approx(p), device_id
    # 修改 P1 不影响其他设备
    _set_param(conn, "2000", vertical_bottom_clearance_m="4.10")
    conn.commit()
    assert svc.current_version(conn, "2000")["vertical_bottom_clearance_m"] == pytest.approx(4.10)
    for device_id, p in P_VALUES.items():
        if device_id == "2000":
            continue
        assert svc.current_version(conn, device_id)["vertical_bottom_clearance_m"] == pytest.approx(p), device_id


# ---------- K03 + GEO-03：3.68 / 5.2 / 45° 共存 ----------

def test_k03_geo03_2000_values_coexist(conn):
    cur = svc.current_version(conn, "2000")
    assert cur["analysis_cutoff_slant_m"] == pytest.approx(5.2)
    assert cur["vertical_bottom_clearance_m"] == pytest.approx(3.68)
    assert cur["downward_tilt_deg"] == pytest.approx(45.0)
    assert cur["beam_angle_value_deg"] == pytest.approx(15.0)
    assert cur["beam_angle_kind"] == "FULL"
    assert cur["beam_half_angle_deg"] == pytest.approx(7.5)
    # 派生轴斜距 ≈ 3.68/sin45° ≈ 5.2043（仅参考，不覆盖 5.2）
    assert cur["derived_axis_slant_m"] == pytest.approx(3.68 / math.sin(math.radians(45)), abs=1e-6)
    assert cur["derived_axis_slant_m"] != cur["analysis_cutoff_slant_m"]
    assert cur["is_derived"] == 1


# ---------- 任务三：独立离底高度换算 ----------

def test_task3_derived_values_both_directions(conn):
    # AXIS_SLANT 输入 5.2、倾角 30° → 派生垂直 = 5.2*sin30 = 2.6
    _set_param(conn, "2002", clearance_input_type="AXIS_SLANT",
               vertical_bottom_clearance_m="", axis_slant_m="5.2", downward_tilt_deg="30")
    conn.commit()
    cur = svc.current_version(conn, "2002")
    assert cur["derived_vertical_clearance_m"] == pytest.approx(5.2 * math.sin(math.radians(30)), abs=1e-9)
    assert cur["derived_vertical_clearance_m"] == pytest.approx(2.6, abs=1e-9)
    # 派生值不得写回用户输入位，截断独立
    assert cur["axis_slant_m"] == pytest.approx(5.2)
    assert cur["analysis_cutoff_slant_m"] == pytest.approx(5.2)
    # 缺倾角 → 无派生值，不得报错、不得自动填 3.68
    _set_param(conn, "2003", downward_tilt_deg="")
    conn.commit()
    cur = svc.current_version(conn, "2003")
    assert cur["derived_axis_slant_m"] is None
    assert cur["vertical_bottom_clearance_m"] == pytest.approx(3.5)  # 表单输入值，非 3.68


def test_task3_unknown_not_autofilled(conn):
    """UNKNOWN 不自动填默认值（不得自动填 3.68）。"""
    _set_param(conn, "2005", clearance_input_type="UNKNOWN",
               vertical_bottom_clearance_m="", axis_slant_m="", downward_tilt_deg="")
    conn.commit()
    cur = svc.current_version(conn, "2005")
    assert cur["vertical_bottom_clearance_m"] is None
    assert cur["axis_slant_m"] is None
    assert cur["clearance_input_type"] == "UNKNOWN"
    rows = conn.execute(
        "SELECT COUNT(*) n FROM device_parameter_versions WHERE device_id='2005' AND vertical_bottom_clearance_m=3.68"
    ).fetchone()
    assert rows["n"] == 0


# ---------- 任务四：参数历史版本 ----------

def test_task4_history_immutable_and_effective_chain(conn):
    v1 = _set_param(conn, "2003", vertical_bottom_clearance_m="3.20", effective_from="2026-10-31")
    conn.commit()
    v2 = _set_param(conn, "2003", vertical_bottom_clearance_m="3.80", effective_from="2026-11-05",
                    change_reason="task4 test")
    conn.commit()
    assert v1 == 1 and v2 == 2
    hist = svc.param_history(conn, "2003")
    assert [r["version"] for r in hist] == [2, 1]
    old = hist[1]
    assert old["vertical_bottom_clearance_m"] == pytest.approx(3.20)  # 旧值未变
    assert old["effective_to"] == "2026-11-05"                        # 区间被新版本关闭
    assert hist[0]["effective_to"] is None
    # 新参数不改变历史结果：v1 行仍是 v1 的值
    cur = svc.current_version(conn, "2003")
    assert cur["version"] == 2 and cur["vertical_bottom_clearance_m"] == pytest.approx(3.80)


# ---------- K13：非法输入拒绝 ----------

@pytest.mark.parametrize("overrides,fragment", [
    ({"analysis_cutoff_slant_m": "-1"}, "人工分析截断斜距"),
    ({"analysis_cutoff_slant_m": ""}, "人工分析截断斜距"),
    ({"vertical_bottom_clearance_m": "0"}, "垂直离底高度"),
    ({"downward_tilt_deg": "120"}, "倾角"),
    ({"beam_angle_value_deg": "95", "beam_angle_kind": "HALF"}, "半角"),
    ({"beam_angle_value_deg": "15", "beam_angle_kind": "UNKNOWN"}, "显式选择"),
    ({"beam_angle_value_deg": "200", "beam_angle_kind": "FULL"}, "全角"),
    ({"heading_deg": "365"}, "方位角"),
    ({"source": ""}, "参数来源"),
    ({"effective_from": ""}, "生效起始日期"),
])
def test_k13_invalid_inputs_rejected_web(client, overrides, fragment):
    resp = client.post("/devices/2002/params", data=make_form(**overrides))
    assert resp.status_code == 400
    assert fragment in resp.get_data(as_text=True)


def test_k13_lon_lat_rejected_web(client):
    resp = client.post("/devices/2002/position", data={
        "longitude_deg": "181", "latitude_deg": "27.99", "position_source": "TEST",
        "effective_from": "2026-10-31", "expected_version": "0"})
    assert resp.status_code == 400
    assert "经度" in resp.get_data(as_text=True)


# ---------- K15 前置：并发冲突 409 ----------

def test_conflict_returns_409(client, conn):
    # 先经网页保存一次 → 当前 v2（种子 v1）
    resp = client.post("/devices/2001/params", data=make_form(vertical_bottom_clearance_m="3.6",
                                                              expected_version="1"))
    assert resp.status_code == 302
    # 用过期版本号再次提交 → 409
    resp = client.post("/devices/2001/params", data=make_form(vertical_bottom_clearance_m="3.9",
                                                              expected_version="1"))
    assert resp.status_code == 409
    assert "并发冲突" in resp.get_data(as_text=True)


# ---------- 任务五：人工水底参考面 ----------

def test_task5_bottom_reference_2000_and_independent(conn):
    br = conn.execute(
        "SELECT * FROM bottom_references WHERE device_id='2000' AND reference_type='USER_DEFINED_ESTIMATED'"
    ).fetchone()
    assert br is not None
    assert br["vertical_height_m"] == pytest.approx(3.68)
    assert br["acoustic_bottom_status"] == "NOT_DETECTED"
    # 其他台初始无人参考面；可独立设置
    assert conn.execute("SELECT COUNT(*) n FROM bottom_references WHERE device_id='2001'").fetchone()["n"] == 0
    conn.execute(
        """INSERT INTO bottom_references (device_id, reference_type, vertical_height_m,
           acoustic_bottom_status, effective_from, source, created_at)
           VALUES ('2001','USER_DEFINED_ESTIMATED',3.6,'NOT_DETECTED','2026-10-31','TEST',datetime('now'))"""
    )
    conn.commit()
    assert conn.execute(
        "SELECT vertical_height_m FROM bottom_references WHERE device_id='2001'"
    ).fetchone()["vertical_height_m"] == pytest.approx(3.6)


# ---------- 任务六：两阶段数据集 ----------

def test_task6_datasets_independent(conn):
    ds = {r["dataset_id"]: r for r in conn.execute("SELECT * FROM datasets")}
    assert set(ds) == {"DATASET_01_DUAL_STATION", "DATASET_02_FIVE_STATION"}
    m1 = {r["device_id"] for r in conn.execute(
        "SELECT device_id FROM dataset_members WHERE dataset_id='DATASET_01_DUAL_STATION'")}
    m2 = {r["device_id"] for r in conn.execute(
        "SELECT dataset_id, device_id FROM dataset_members WHERE dataset_id='DATASET_02_FIVE_STATION'")}
    assert m1 == {"2000", "2001"}
    assert m2 == set(DEVICE_IDS)
    # 起止时间待确认 → 为空，不得编造
    assert ds["DATASET_01_DUAL_STATION"]["start_time"] is None
    assert ds["DATASET_01_DUAL_STATION"]["end_time"] is None


# ---------- 任务八：原始文件登记 ----------

def test_task8_file_registry_21_rows_with_sha256(conn):
    rows = conn.execute("SELECT * FROM file_registry ORDER BY relative_path").fetchall()
    assert len(rows) == 21
    by_device = {"2000": 0, "2001": 0}
    for r in rows:
        assert len(r["sha256"]) == 64
        assert r["status"] == "ARCHIVED_REGISTERED"
        assert r["observed_date"] and len(r["observed_date"]) == 10
        by_device[r["device_id"]] += 1
    assert by_device == {"2000": 13, "2001": 8}
    # 重复检查：相对路径唯一；同哈希异路径的副本在 conflict_note 中登记
    paths = [r["relative_path"] for r in rows]
    assert len(paths) == len(set(paths))


# ---------- K19 + GEO-01：经纬度网页录入回读与历史保留 ----------

def test_k19_geo01_position_entry_readback_and_history(client, conn):
    resp = client.post("/devices/2002/position", data={
        "longitude_deg": "121.2200000000000", "latitude_deg": "27.9900000000000",
        "coordinate_reference_system": "", "position_accuracy_m": "",
        "heading_deg": "", "heading_reference": "",
        "position_source": "TEST_USER", "effective_from": "2026-11-01",
        "expected_version": "0", "notes": ""})
    assert resp.status_code == 302
    # 回读：详情页显示坐标
    html = client.get("/devices/2002").get_data(as_text=True)
    assert "121.2200000000000" in html
    pos1 = svc.current_position(conn, "2002")
    assert pos1["longitude_deg"] == pytest.approx(121.22)
    assert pos1["coordinate_reference_system"] is None  # 不默认 WGS84
    # 第二次录入 → 历史 2 行，第一行保留且区间被关闭
    resp = client.post("/devices/2002/position", data={
        "longitude_deg": "121.2210000000000", "latitude_deg": "27.9910000000000",
        "coordinate_reference_system": "WGS84", "position_accuracy_m": "3",
        "heading_deg": "127.4", "heading_reference": "TRUE_NORTH_CW",
        "position_source": "TEST_USER", "effective_from": "2026-11-10",
        "expected_version": "1", "notes": "moved"})
    assert resp.status_code == 302
    hist = svc.position_history(conn, "2002")
    assert [r["version"] for r in hist] == [2, 1]
    assert hist[1]["longitude_deg"] == pytest.approx(121.22)     # 旧版本未覆盖
    assert hist[1]["effective_to"] == "2026-11-10"
    assert hist[0]["heading_deg"] == pytest.approx(127.4)
    cur = svc.current_position(conn, "2002")
    assert cur["position_accuracy_m"] == pytest.approx(3)


# ---------- 保存前影响预览 ----------

def test_params_preview_endpoint(client):
    resp = client.get("/devices/2000/params/preview", query_string={
        "clearance_input_type": "VERTICAL", "vertical_bottom_clearance_m": "3.68",
        "axis_slant_m": "", "downward_tilt_deg": "45", "beam_angle_value_deg": "15",
        "beam_angle_kind": "FULL", "analysis_cutoff_slant_m": "5.2",
        "source": "preview", "effective_from": "2026-10-31"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["derived_axis_slant_m"] == pytest.approx(3.68 / math.sin(math.radians(45)), abs=1e-6)
    assert body["cutoff_untouched_by_derivation"] is True
    assert body["beam_half_angle_deg"] == pytest.approx(7.5)
    # 校验失败返回 400 + errors
    resp = client.get("/devices/2000/params/preview", query_string={
        "clearance_input_type": "VERTICAL", "vertical_bottom_clearance_m": "-1",
        "analysis_cutoff_slant_m": "5.2", "source": "preview", "effective_from": "2026-10-31"})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False
