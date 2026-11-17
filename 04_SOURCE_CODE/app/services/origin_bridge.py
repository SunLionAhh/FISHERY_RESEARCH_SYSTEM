# -*- coding: utf-8 -*-
"""S09：Origin 任务包、独立 Windows Worker 串行调用与环境实测留痕。"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def probe_environment() -> dict:
    return {
        "origin_installed": Path(r"C:\Program Files\OriginLab\Origin2027\Origin64.exe").exists(),
        "executable_version": "Origin64.exe 10.4.0 / ProductVersion 10.4",
        "com_progids": ["Origin.Application", "Origin.ApplicationSI"],
        "originpro_python_package": "NOT_INSTALLED" if importlib.util.find_spec("originpro") is None
                                    else "INSTALLED",
        "pywin32_python_package": "NOT_INSTALLED" if importlib.util.find_spec("win32com") is None
                                  else "INSTALLED",
        "bridge": "PowerShell COM Worker（独立于 Flask 请求，串行执行）",
        "license_observation": "TRIAL_MODE_REMAINING_3_DAYS (2026-11-17 UI 实测)",
        "learning_edition": "UNCONFIRMED_BY_COM_REGISTRY",
        "note": "COM 实测可用；originpro 包未安装，不能声称 Python 包兼容闭环 PASS",
    }


def create_task(conn: sqlite3.Connection, project_root: Path, figure_ids: list[str], *,
                formats=("png", "pdf", "svg"), actor: str = "S09") -> dict:
    root = Path(project_root)
    task_id = "ORIGIN-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
    task_dir = root / "07_FIGURES" / "s09" / "origin" / "tasks"
    output_dir = root / "07_FIGURES" / "s09" / "origin" / "exports"
    task_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    figures = []
    for figure_id in figure_ids:
        row = conn.execute("SELECT figure_id,source_csv FROM figure_registry WHERE figure_id=?",
                           (figure_id,)).fetchone()
        if not row:
            continue
        figures.append({"figure_id": row["figure_id"], "csv": row["source_csv"], "y": "value"})
    if not figures:
        raise ValueError("没有可提交给 Origin 的图类")
    package = {"task_id": task_id, "figures": figures, "formats": list(formats),
               "output_dir": str(output_dir).replace("\\", "/")}
    package_path = task_dir / f"{task_id}.json"
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT OR REPLACE INTO origin_tasks (task_id,figure_id,status,task_package,created_at,"
        "updated_at,actor) VALUES (?,?,?,?,?,?,?)",
        (task_id, ",".join(f["figure_id"] for f in figures), "QUEUED", str(package_path), now, now, actor))
    conn.commit()
    return {"task_id": task_id, "package": str(package_path), "figures": [f["figure_id"] for f in figures]}


def run_task(conn: sqlite3.Connection, task_id: str, project_root: Path, *,
             worker: Path | None = None, timeout: int = 300) -> dict:
    row = conn.execute("SELECT * FROM origin_tasks WHERE task_id=?", (task_id,)).fetchone()
    if not row:
        raise KeyError(task_id)
    root = Path(project_root)
    worker = worker or root / "04_SOURCE_CODE" / "scripts" / "origin_worker.ps1"
    package = Path(row["task_package"])
    result_path = package.with_name(package.stem + "_result.json")
    ps = shutil.which("powershell") or shutil.which("powershell.exe")
    if not ps:
        raise RuntimeError("PowerShell 不可用，不能启动 Origin Worker")
    conn.execute("UPDATE origin_tasks SET status='RUNNING',updated_at=? WHERE task_id=?",
                 (datetime.now().isoformat(timespec="seconds"), task_id))
    conn.commit()
    try:
        completed = subprocess.run(
            [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(worker),
             "-Task", str(package), "-Result", str(result_path)],
            capture_output=True, text=True, timeout=timeout, cwd=str(root))
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        else:
            result = {"status": "FAILED", "error": (completed.stderr or completed.stdout)[-2000:]}
        status = result.get("status", "FAILED")
        conn.execute(
            "UPDATE origin_tasks SET status=?,worker_log=?,opju_path=?,reopen_check=?,error=?,"
            "updated_at=? WHERE task_id=?",
            (status, str(result_path), result.get("opju_path"), result.get("reopen_check"),
             result.get("error"), datetime.now().isoformat(timespec="seconds"), task_id))
        conn.commit()
        return result
    except Exception as exc:
        conn.execute("UPDATE origin_tasks SET status='FAILED',error=?,updated_at=? WHERE task_id=?",
                     (str(exc), datetime.now().isoformat(timespec="seconds"), task_id))
        conn.commit()
        raise


def report(conn: sqlite3.Connection) -> dict:
    return {"environment": probe_environment(),
            "tasks": [dict(r) for r in conn.execute("SELECT * FROM origin_tasks ORDER BY created_at DESC LIMIT 20")]}
