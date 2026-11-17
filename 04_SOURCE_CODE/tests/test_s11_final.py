# -*- coding: utf-8 -*-
"""S11：最终验收、论文交付、冻结、恢复与离线核心功能。"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.config import PROJECT_ROOT
from app.services import s11_acceptance as acceptance

ROOT = Path(PROJECT_ROOT)


def test_final_acceptance_evidence_is_complete():
    path = ROOT / "10_TEST_REPORTS" / "s11_verification" / "final_acceptance.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["verification"]["pass"] == 13
    assert data["verification"]["failed"] == []
    assert data["offline"]["pass"] is True
    assert data["restore"]["pass"] is True
    assert data["pre_defense"]["status"] == "FROZEN"


def test_verify_sections_against_real_database():
    conn = sqlite3.connect(ROOT / "03_DATABASE" / "fishery.db")
    try:
        report = acceptance.verify_sections(conn, ROOT)
    finally:
        conn.close()
    assert report["total"] == 13
    assert report["failed"] == []


def test_paper_deliverables_exist():
    paper = ROOT / "12_DOCUMENTATION" / "PAPER_EVIDENCE"
    required = ["CHAPTER03_DUAL_STATION.md", "CHAPTER04_FIVE_STATION.md",
                "CHAPTER05_ENVIRONMENT.md", "METHODS.md", "DATA_QUALITY.md", "PRE_DEFENSE.md"]
    assert all((paper / name).exists() for name in required)


def test_pre_defense_frozen_and_restore_drill_pass():
    conn = sqlite3.connect(ROOT / "03_DATABASE" / "fishery.db")
    try:
        row = conn.execute("SELECT status FROM datasets WHERE dataset_id='PRE_DEFENSE'").fetchone()
    finally:
        conn.close()
    assert row and row[0] == "FROZEN"
    drill = acceptance.restore_drill(ROOT)
    assert drill["pass"] is True
    assert drill["integrity"] == "ok"


def test_offline_core_test_without_network():
    result = acceptance.offline_core_test(ROOT)
    assert result["pass"] is True
    assert all(check["pass"] for check in result["checks"])
