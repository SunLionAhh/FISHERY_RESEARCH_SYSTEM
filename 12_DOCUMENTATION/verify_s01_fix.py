# -*- coding: utf-8 -*-
"""S01 整改复验脚本（只读正式库，不写入任何数据）。

用法：
    .venv\\Scripts\\python.exe 12_DOCUMENTATION\\verify_s01_fix.py [db_path]

输出：迁移版本、五台 station_id、2000/2001 关键值、2002/2003/2005 未知状态、5.2 行数。
退出码：0 = 全部符合；1 = 有不符项。
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "03_DATABASE" / "fishery.db"

ok = True


def check(label, actual, expected):
    global ok
    passed = actual == expected
    ok = ok and passed
    print(f"[{'PASS' if passed else 'FAIL'}] {label}: {actual!r} (期望 {expected!r})")


conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

versions = [r["version"] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
print(f"DB = {DB}")
print(f"schema_migrations = {versions}")
check("迁移含 0001/0002（后续阶段可追加）", versions[:2], ["0001", "0002"])

device_ids = [r["device_id"] for r in conn.execute("SELECT device_id FROM devices ORDER BY device_id")]
check("五台设备且无 2004", device_ids, ["2000", "2001", "2002", "2003", "2005"])

stations = [(r["device_id"], r["station_id"]) for r in
            conn.execute("SELECT device_id, station_id FROM devices ORDER BY device_id")]
check("station_id 全部未分配(NULL)", stations,
      [("2000", None), ("2001", None), ("2002", None), ("2003", None), ("2005", None)])

p2000 = conn.execute(
    """SELECT v.* FROM device_parameter_versions v
       JOIN device_parameters p ON p.current_parameter_id = v.parameter_id
       WHERE p.device_id = '2000'"""
).fetchone()
print("2000 当前参数 =", dict(p2000))
check("2000 截断 5.2", p2000["analysis_cutoff_slant_m"], 5.2)
check("2000 垂直离底 3.68", p2000["vertical_bottom_clearance_m"], 3.68)
check("2000 倾角 45", p2000["downward_tilt_deg"], 45.0)
check("2000 波束角 15 FULL", (p2000["beam_angle_value_deg"], p2000["beam_angle_kind"]), (15.0, "FULL"))
check("2000 半角 7.5", p2000["beam_half_angle_deg"], 7.5)
print(f"2000 派生轴斜距 = {p2000['derived_axis_slant_m']:.10f}（仅参考，不得覆盖 5.2）")
check("派生值≠截断(5.2043≠5.2)", round(p2000["derived_axis_slant_m"], 7), 5.2043059)

p2001 = conn.execute(
    """SELECT v.* FROM device_parameter_versions v
       JOIN device_parameters p ON p.current_parameter_id = v.parameter_id
       WHERE p.device_id = '2001'"""
).fetchone()
print("2001 当前参数 =", {k: p2001[k] for k in
                          ("analysis_cutoff_slant_m", "vertical_bottom_clearance_m", "downward_tilt_deg")})
check("2001 截断 5.2", p2001["analysis_cutoff_slant_m"], 5.2)
check("2001 垂直离底 3.6", p2001["vertical_bottom_clearance_m"], 3.6)
check("2001 倾角保持 UNKNOWN", p2001["downward_tilt_deg"], None)

for device_id in ("2002", "2003", "2005"):
    n = conn.execute("SELECT COUNT(*) n FROM device_parameter_versions WHERE device_id=?",
                     (device_id,)).fetchone()["n"]
    n368 = conn.execute(
        "SELECT COUNT(*) n FROM device_parameter_versions WHERE device_id=? AND vertical_bottom_clearance_m=3.68",
        (device_id,)).fetchone()["n"]
    check(f"{device_id} 无参数行（UNKNOWN）", n, 0)
    check(f"{device_id} 未被填 3.68", n368, 0)

cutoff_rows = conn.execute("SELECT COUNT(*) n FROM device_parameter_versions").fetchone()["n"]
inf_rows = conn.execute(
    "SELECT COUNT(*) n FROM device_parameter_versions WHERE analysis_cutoff_slant_m IS NULL").fetchone()["n"]
print(f"参数版本总行数 = {cutoff_rows}，截断为 NULL 的行数 = {inf_rows}")
check("无截断为 NULL 的已保存版本", inf_rows, 0)

# 有限性兜底：库里不得出现 inf/nan 字面量
raw = conn.execute("SELECT quote(analysis_cutoff_slant_m) q FROM device_parameter_versions").fetchall()
print("截断存储字面量 =", [r["q"] for r in raw])
check("截断存储无 inf/nan 字面量",
      [r["q"] for r in raw if r["q"] and ("inf" in r["q"].lower() or "nan" in r["q"].lower())], [])

conn.close()
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
