# -*- coding: utf-8 -*-
"""S10：31 类入口与完整操作链冒烟，证据写入 s10_verification。"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from app import create_app  # noqa: E402
from app.config import PROJECT_ROOT  # noqa: E402
from app.db import connect  # noqa: E402
from app.services import workbench  # noqa: E402


def main() -> None:
    out = PROJECT_ROOT / "10_TEST_REPORTS" / "s10_verification"
    out.mkdir(parents=True, exist_ok=True)
    app = create_app()
    app.config["PROJECT_ROOT"] = PROJECT_ROOT
    client = app.test_client()
    conn = connect()
    try:
        ctx = workbench.context(conn, device="", start="2026-10-31", end="2026-11-03")
        rows = workbench.linked_view(conn, workbench.DEVICE_IDS, "2026-10-31", "2026-11-03")
        workbench.write_csv(rows, out / "workbench_linked.csv")
        workbench.write_report(ctx, rows, out / "workbench_report.md")
        checks = []
        for entry in ctx["entries"]:
            response = client.get(entry["url_q"])
            checks.append({"id": entry["id"], "name": entry["name"], "url": entry["url"],
                           "status": response.status_code,
                           "pass": response.status_code == 200})
        manifest = list(__import__("csv").DictReader(
            (PROJECT_ROOT / "10_TEST_REPORTS" / "RAW_CSV_ARCHIVE_MANIFEST.csv").open(
                encoding="utf-8-sig")))
        bad = [r["file_name"] for r in manifest if not (
            (PROJECT_ROOT / r["archived_relative_path"]).exists()
            and hashlib.sha256((PROJECT_ROOT / r["archived_relative_path"]).read_bytes()).hexdigest()
            == r["sha256_after"])]
        launcher = PROJECT_ROOT / "启动工作台.bat"
        app_restarted = create_app()
        client_restarted = app_restarted.test_client()
        restart_page = client_restarted.get("/workbench?device=2000")
        result = {
            "checked_at": datetime.now().isoformat(timespec="seconds"),
            "entries_total": len(checks),
            "entries_pass": sum(1 for c in checks if c["pass"]),
            "entries": checks,
            "linked_rows": len(rows),
            "raw_csv_manifest": len(manifest),
            "raw_csv_match": len(manifest) - len(bad),
            "launcher_exists": launcher.exists(),
            "local_bind": 'host="127.0.0.1"' in (SOURCE / "run.py").read_text(encoding="utf-8"),
            "restart_recovery": restart_page.status_code == 200
                                and "31 类工作台入口".encode("utf-8") in restart_page.data,
        }
        (out / "smoke.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
        print(json.dumps({k: result[k] for k in ("entries_total", "entries_pass", "linked_rows",
                                                "raw_csv_match", "launcher_exists", "local_bind",
                                                "restart_recovery")},
                         ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
