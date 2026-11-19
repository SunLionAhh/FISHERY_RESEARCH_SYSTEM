# -*- coding: utf-8 -*-
"""整改 P2-5：把派生代理来源的逐行质量标记纠正为 DERIVED。"""
from __future__ import annotations

import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from app.db import connect  # noqa: E402

SOURCE_ID = "ENV-WATER-FISHFINDER-DERIVED"


def main() -> None:
    conn = connect()
    try:
        count = conn.execute(
            "UPDATE environment_observation SET quality_flag='DERIVED' WHERE source_id=?",
            (SOURCE_ID,)).rowcount
        conn.commit()
        print(f"updated={count}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
