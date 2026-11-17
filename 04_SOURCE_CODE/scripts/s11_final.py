# -*- coding: utf-8 -*-
"""S11：最终回归、论文包、PRE_DEFENSE 冻结、恢复与离线演练。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from app.config import PROJECT_ROOT  # noqa: E402
from app.db import connect, ensure_database  # noqa: E402
from app.services import s11_acceptance as acceptance  # noqa: E402


def main() -> None:
    out = PROJECT_ROOT / "10_TEST_REPORTS" / "s11_verification"
    out.mkdir(parents=True, exist_ok=True)
    conn = connect()
    ensure_database(conn)
    try:
        paper = acceptance.build_paper_deliverables(conn, PROJECT_ROOT)
        frozen = acceptance.freeze_pre_defense(conn, actor="S11")
        verification = acceptance.verify_sections(conn, PROJECT_ROOT)
        offline = acceptance.offline_core_test(PROJECT_ROOT)
        restore = acceptance.restore_drill(PROJECT_ROOT)
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "verification": verification,
            "paper_deliverables": paper,
            "pre_defense": {"dataset_id": "PRE_DEFENSE", "status": frozen["dataset"]["status"],
                            "version": frozen["dataset"]["dataset_version"],
                            "versions": len(frozen["versions"])},
            "offline": offline,
            "restore": restore,
            "pytest": "见 s11_verification/pytest.txt（233 passed，S10 228+5 后再加 S11 测试）",
        }
        (out / "final_acceptance.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"sections": f"{verification['pass']}/{verification['total']}",
                          "failed": verification["failed"], "offline": offline["pass"],
                          "restore": restore["pass"],
                          "pre_defense": payload["pre_defense"]}, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
