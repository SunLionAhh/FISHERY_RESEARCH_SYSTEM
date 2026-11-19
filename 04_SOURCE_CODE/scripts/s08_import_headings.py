# -*- coding: utf-8 -*-
"""S08：导入用户提供的五台设备方位角截图，作为新版本站位留痕。"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from app.config import PROJECT_ROOT  # noqa: E402
from app.db import connect, ensure_database  # noqa: E402
from app.services import spatial  # noqa: E402

ASSET_DIR = Path("C:/Users/Administrator/AppData/Local/CodeBuddyExtension/Data/"
                 "a1c09734-4641-467b-a8c3-77324755ba79/CodeBuddyIDE/"
                 "a1c09734-4641-467b-a8c3-77324755ba79/history/"
                 "af999f81dd5f872713c2515d1f7bba6d/3a7b5f14c9bd4bd4a5f70fa23b5ff5b4/assets")

RECORDS = [
    {"device_id": "2000", "heading_deg": 110, "cardinal": "东", "screenshot_time": "07:36",
     "image": "0eb6f66d-4f85-48f3-a9eb-68e995a95e1f.0e7e388e7f.jpg"},
    {"device_id": "2001", "heading_deg": 260, "cardinal": "西", "screenshot_time": "09:36",
     "image": "394d7b60-b107-4d48-8a7a-b6f7411ea99d.d1128c7846.png"},
    {"device_id": "2002", "heading_deg": 270, "cardinal": "西", "screenshot_time": "11:03",
     "image": "e90c0f82-b80f-48a0-8af6-e86baca42409.fd3c68a674.png"},
    {"device_id": "2003", "heading_deg": 234, "cardinal": "西南", "screenshot_time": "11:01",
     "image": "ff18e46d-b3b1-4112-9dc6-ea946a4e3f88.3590a59436.png"},
    {"device_id": "2005", "heading_deg": 165, "cardinal": "南", "screenshot_time": "11:52",
     "image": "0dcd5581-93c4-41b6-86d3-02521e89b8af.496b179700.jpg"},
]

EFFECTIVE_FROM = "2026-10-31"
MEASURED_AT = "2026-11-19"
REFERENCE = ("PHONE_COMPASS_MAGNETIC_SCREENSHOT_2026-11-19; "
             "ASSUMED_SAME_AS_DEPLOYMENT_HEADING_2026-10_31_TO_11_03")
SOURCE_NAME = "USER_PROVIDED_COMPASS_IMAGE_2026-11-19"


def main() -> None:
    conn = connect()
    ensure_database(conn)
    out = PROJECT_ROOT / "10_TEST_REPORTS" / "s08_verification"
    out.mkdir(parents=True, exist_ok=True)
    records = [{**r, "image_path": str(ASSET_DIR / r["image"]),
                "heading_reference": REFERENCE, "position_source": SOURCE_NAME}
               for r in RECORDS]
    try:
        imported = spatial.import_headings(
            conn, PROJECT_ROOT, records, effective_from=EFFECTIVE_FROM,
            measured_at=MEASURED_AT, actor="S08-USER-COMPASS")
        rows = [{**r, "cardinal": next(x["cardinal"] for x in RECORDS
                                       if x["device_id"] == r["device_id"]),
                 "screenshot_time": next(x["screenshot_time"] for x in RECORDS
                                         if x["device_id"] == r["device_id"])}
                for r in imported]
        csv_path = out / "heading_import.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["device_id", "heading_deg", "cardinal",
                                                    "screenshot_time", "image", "sha256",
                                                    "had_coordinates"])
            writer.writeheader()
            writer.writerows(rows)
        (out / "heading_import.json").write_text(json.dumps({
            "effective_from": EFFECTIVE_FROM, "measured_at": MEASURED_AT,
            "heading_reference": REFERENCE, "source": SOURCE_NAME,
            "assumption": "用户说明为设备方位角；按部署期固定朝向处理并回填至 2026-10-31，手机罗盘为磁北口径，未声明真北修正",
            "records": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"imported": len(rows), "csv": str(csv_path)}, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
