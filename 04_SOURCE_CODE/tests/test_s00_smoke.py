# -*- coding: utf-8 -*-
"""S00 冒烟测试：目录骨架、设备清单、原始数据登记、依赖与环境基础契约。

仅验证 S00 已实际完成的事实，不声称任何分析功能已实现。
"""
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_DIRS = [
    "00_PROJECT_SPEC", "01_ORIGINAL_DATA", "02_IMPORTED_DATA", "03_DATABASE",
    "04_SOURCE_CODE", "05_CONFIG", "06_ANALYSIS_RESULTS", "07_FIGURES",
    "08_ORIGIN_PROJECTS", "09_PAPER_OUTPUT", "10_TEST_REPORTS", "11_BACKUPS",
    "12_DOCUMENTATION", "13_FROZEN_VERSIONS", "14_TEMP", "FISHERY_FULL_PLAN_V4",
]

EXPECTED_DEVICES = ["2000", "2001", "2002", "2003", "2005"]


def test_target_python_310():
    assert sys.version_info[:2] == (3, 10), f"目标解释器须为 3.10.x，实际 {sys.version}"


def test_core_dependencies_importable():
    import flask  # noqa: F401
    import numpy  # noqa: F401
    import pandas  # noqa: F401
    import matplotlib  # noqa: F401
    import openpyxl  # noqa: F401


@pytest.mark.parametrize("d", EXPECTED_DIRS)
def test_directory_skeleton(d):
    assert (ROOT / d).is_dir(), f"缺少目录 {d}"


def test_device_folders_v4_no_2004():
    ff = ROOT / "01_ORIGINAL_DATA" / "FISHFINDER"
    for dev in EXPECTED_DEVICES:
        assert (ff / dev).is_dir(), f"缺少设备目录 {dev}"
    assert not (ff / "2004").exists(), "2004 不在设备清单，不得存在设备目录"


@pytest.mark.parametrize("sub", ["WATER_TEMPERATURE", "TIDE", "WIND"])
def test_environment_subdirs(sub):
    assert (ROOT / "01_ORIGINAL_DATA" / "ENVIRONMENT" / sub).is_dir()


def test_gps_and_manufacturer_dirs():
    assert (ROOT / "01_ORIGINAL_DATA" / "GPS").is_dir()
    assert (ROOT / "01_ORIGINAL_DATA" / "MANUFACTURER_DOCS").is_dir()


def test_raw_csv_inventory_21_files():
    inv = ROOT / "10_TEST_REPORTS" / "RAW_CSV_PRECHECK_INVENTORY_CURRENT.csv"
    with open(inv, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 21, f"清单应为 21 行，实际 {len(rows)}"
    total = sum(int(r["size_bytes"]) for r in rows)
    assert total == 8380445292, f"合计字节数不符：{total}"
    dev_counts = {}
    for r in rows:
        dev_counts[r["device_id_in_filename"]] = dev_counts.get(r["device_id_in_filename"], 0) + 1
    assert dev_counts == {"2000": 13, "2001": 8}, f"设备分布不符：{dev_counts}"
    # 现行文件必须真实存在
    missing = [r["relative_path"] for r in rows
               if not (ROOT / r["relative_path"]).is_file()]
    assert not missing, f"清单中缺失的现行文件：{missing}"


def test_v4_package_manifest_pass():
    verify = ROOT / "10_TEST_REPORTS" / "s00_verification" / "V4_PACKAGE_VERIFY.csv"
    with open(verify, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 16
    assert all(r["result"] == "PASS" for r in rows)


def test_raw_csv_sha256_recheck_pass():
    verify = ROOT / "10_TEST_REPORTS" / "s00_verification" / "RAW_CSV_SHA256_RECHECK.csv"
    with open(verify, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 21
    assert all(r["result"] == "PASS" for r in rows)


def test_v4_authoritative_files_present():
    v4 = ROOT / "FISHERY_FULL_PLAN_V4"
    for name in ["01_MASTER_SPEC_FINAL.md", "02_CODEX_EXECUTION_GUIDE_FINAL.md",
                 "03_CODEX_STAGE_TASKS_FINAL.md", "08_USER_REQUIREMENTS_V4.md",
                 "09_DEVELOPER_ACCEPTANCE.md", "11_GPS_BEAM_GEOMETRY.md"]:
        assert (v4 / name).is_file(), f"V4 关键文件缺失：{name}"


def test_device_config_example_five_devices():
    cfg = json.loads((ROOT / "FISHERY_FULL_PLAN_V4" / "10_DEVICE_CONFIG_EXAMPLE.json")
                     .read_text(encoding="utf-8"))
    ids = [d["device_id"] for d in cfg["devices"]]
    assert ids == ["2000", "2001", "2002", "2003", "2005"]
    d2000 = cfg["devices"][0]
    assert d2000["analysis_cutoff_slant_m"] == 5.2
    assert d2000["vertical_bottom_clearance_m"] == 3.68
    assert d2000["beam_angle_kind"] == "UNKNOWN"
    # 其余四台不得继承 2000 的值
    for d in cfg["devices"][1:]:
        assert d["analysis_cutoff_slant_m"] is None
        assert d["vertical_bottom_clearance_m"] is None
        assert d["position"]["longitude_deg"] is None
        assert d["position"]["latitude_deg"] is None


def test_source_layout_honest_state():
    """结构守护：实现代码只允许在 app/ 下，测试只允许在 tests/ 下（S00 时仅依赖锁+冒烟测试，S01 起含 app/）。"""
    src = ROOT / "04_SOURCE_CODE"
    py_files = [p.relative_to(src).as_posix() for p in src.rglob("*.py")]
    assert py_files, "04_SOURCE_CODE 应存在 Python 文件"
    for rel in py_files:
        assert rel.startswith(("app/", "tests/")) or rel == "run.py", f"实现代码位置越界：{rel}"
