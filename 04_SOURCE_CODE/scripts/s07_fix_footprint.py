# -*- coding: utf-8 -*-
"""S07 整改 D1-5：以新版本追加正确的底足迹面积留痕，不改旧记录。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from app.config import PROJECT_ROOT  # noqa: E402
from app.db import connect, ensure_database  # noqa: E402
from app.services import beam_geometry as geo  # noqa: E402

ACTOR = "S07-FOOTPRINT-FIX-V2"


def main() -> None:
    conn = connect()
    ensure_database(conn)
    out = PROJECT_ROOT / "10_TEST_REPORTS" / "s07_verification" / "geometry_2000_footprint_fix_v2.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    appended = []
    try:
        rows = list(conn.execute(
            "SELECT * FROM s07_bottom_qc WHERE details_json LIKE '%retained_footprint%' "
            "ORDER BY qc_id"))
        for row in rows:
            exists = conn.execute(
                "SELECT COUNT(1) FROM s07_bottom_qc WHERE device_id=? AND observed_date=? "
                "AND parameter_id=? AND created_by=?",
                (row["device_id"], row["observed_date"], row["parameter_id"], ACTOR)).fetchone()[0]
            if exists:
                continue
            details = json.loads(row["details_json"])
            inputs = details["inputs"]
            recomputed = geo.beam_geometry(
                height_m=inputs["height_m"], tilt_deg=inputs["tilt_deg"],
                beam_value_deg=inputs["beam_value_deg"], beam_kind=inputs["beam_kind"],
                cutoff_m=inputs["cutoff_m"], r0_m=inputs.get("near_field_m", 0.0))
            corrected = dict(details)
            corrected["algorithm_version"] = "BEAM_GEOM_V2_FOOTPRINT_INTERSECTION"
            corrected["retained_footprint"] = recomputed["retained_footprint"]
            corrected["footprint_fix"] = {
                "reason": "V1 极坐标积分假定原点在椭圆内；45° 情形原点在椭圆外，面积上界被突破",
                "old_area_m2": details["retained_footprint"]["area_m2"],
                "new_area_m2": recomputed["retained_footprint"]["area_m2"],
                "method": "圆盘∩椭圆按 x 切片解析积分；原点内外均成立",
                "old_record_unchanged": True,
            }
            conn.execute(
                "INSERT INTO s07_bottom_qc (device_id,observed_date,parameter_id,bottom_reference_id,"
                "method,status,center_axis_bottom_m,near_edge_bottom_m,far_edge_bottom_m,"
                "near_bottom_candidate_samples,bottom_after_candidate_samples,excluded_samples,"
                "reason,details_json,created_at,created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (row["device_id"], row["observed_date"], row["parameter_id"],
                 row["bottom_reference_id"], "GEOMETRY_RECOMPUTE_V2", row["status"],
                 row["center_axis_bottom_m"], row["near_edge_bottom_m"], row["far_edge_bottom_m"],
                 row["near_bottom_candidate_samples"], row["bottom_after_candidate_samples"],
                 row["excluded_samples"], "旧几何留痕保留；本行为底足迹面积修正的新版本",
                 json.dumps(corrected, ensure_ascii=False, indent=2), geo._now().isoformat()
                 if hasattr(geo, "_now") else __import__("datetime").datetime.now().isoformat(),
                 ACTOR))
            appended.append({"qc_id": row["qc_id"], "device_id": row["device_id"],
                             "observed_date": row["observed_date"],
                             "old_area_m2": details["retained_footprint"]["area_m2"],
                             "new_area_m2": recomputed["retained_footprint"]["area_m2"]})
        conn.commit()
        out.write_text(json.dumps({"actor": ACTOR, "appended": appended,
                                   "note": "旧 QC 行未修改；新行为 V2 留痕"},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"appended": len(appended), "evidence": str(out)}, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
