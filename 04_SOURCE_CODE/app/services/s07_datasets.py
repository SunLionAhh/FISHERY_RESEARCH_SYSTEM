# -*- coding: utf-8 -*-
"""S07 研究阶段数据集边界、版本与冻结（使用户上传保护可审计）。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone as dt_timezone


class DatasetBoundaryError(ValueError):
    pass


def _now() -> str:
    return datetime.now(dt_timezone.utc).isoformat(timespec="seconds")


def _snapshot(conn: sqlite3.Connection, dataset_id: str) -> dict:
    files = [dict(r) for r in conn.execute(
        "SELECT f.relative_path,f.sha256,f.observed_date,f.device_id FROM file_registry f "
        "JOIN dataset_members m ON m.device_id=f.device_id "
        "WHERE m.dataset_id=? AND f.status='IMPORTED' ORDER BY f.observed_date,f.device_id",
        (dataset_id,))]
    runs = [dict(r) for r in conn.execute(
        "SELECT run_id,device_id,status,created_at FROM analysis_runs "
        "WHERE dataset_id=? ORDER BY created_at", (dataset_id,))]
    params = [dict(r) for r in conn.execute(
        "SELECT p.device_id,p.parameter_id,p.version,p.effective_from,p.analysis_cutoff_slant_m,"
        "p.beam_angle_value_deg,p.beam_angle_kind FROM device_parameter_versions p "
        "JOIN dataset_members m ON m.device_id=p.device_id "
        "WHERE m.dataset_id=? ORDER BY p.device_id,p.version", (dataset_id,))]
    return {"files": files, "runs": runs, "parameter_versions": params}


def set_boundaries(conn: sqlite3.Connection, dataset_id: str, *, start_time: str | None,
                   end_time: str | None, formal_sync_time: str | None = None,
                   installation_status: str | None = None, actor: str = "S07") -> dict:
    """记录实际开始/截止/正式同步时间；不预设 14/18/19/30 天。"""
    row = conn.execute("SELECT * FROM datasets WHERE dataset_id=?", (dataset_id,)).fetchone()
    if row is None:
        raise DatasetBoundaryError(f"数据集不存在：{dataset_id}")
    if start_time and end_time and start_time >= end_time:
        raise DatasetBoundaryError("开始时间必须早于截止时间")
    if row["phase"] == 1 and formal_sync_time and end_time and formal_sync_time < end_time:
        raise DatasetBoundaryError("第一阶段截止不得晚于五站正式同步时间")
    if row["phase"] == 2 and formal_sync_time and start_time and formal_sync_time != start_time:
        raise DatasetBoundaryError("第二阶段开始时间应等于正式同步时间")
    if not versions(conn, dataset_id):
        create_version(conn, dataset_id, actor=actor, note="边界更新前初始快照")
    conn.execute(
        "UPDATE datasets SET start_time=?,end_time=?,formal_sync_time=?,installation_status=?,"
        "dataset_version=dataset_version+1 WHERE dataset_id=?",
        (start_time, end_time, formal_sync_time, installation_status, dataset_id))
    conn.commit()
    return create_version(conn, dataset_id, actor=actor, note="边界更新")


def create_version(conn: sqlite3.Connection, dataset_id: str, *, actor: str = "S07",
                   note: str = "") -> dict:
    dataset = conn.execute("SELECT * FROM datasets WHERE dataset_id=?", (dataset_id,)).fetchone()
    if dataset is None:
        raise DatasetBoundaryError(f"数据集不存在：{dataset_id}")
    snapshot = _snapshot(conn, dataset_id)
    version = dataset["dataset_version"]
    boundaries = {k: dataset[k] for k in ("start_time", "end_time", "formal_sync_time",
                                          "installation_status", "status")}
    conn.execute(
        "INSERT OR REPLACE INTO dataset_versions (dataset_id,version,status,start_time,end_time,"
        "formal_sync_time,phase,boundaries_json,hashes_json,run_ids_json,parameter_versions_json,"
        "note,created_at,created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (dataset_id, version, dataset["status"], dataset["start_time"], dataset["end_time"],
         dataset["formal_sync_time"], dataset["phase"],
         json.dumps(boundaries, ensure_ascii=False),
         json.dumps([{"path": f["relative_path"], "sha256": f["sha256"]} for f in snapshot["files"]],
                    ensure_ascii=False),
         json.dumps([r["run_id"] for r in snapshot["runs"]], ensure_ascii=False),
         json.dumps(snapshot["parameter_versions"], ensure_ascii=False),
         note, _now(), actor))
    conn.commit()
    return report(conn, dataset_id)


def freeze(conn: sqlite3.Connection, dataset_id: str, *, actor: str, reason: str) -> dict:
    conn.execute(
        "UPDATE datasets SET status='FROZEN',frozen_at=?,frozen_by=?,freeze_reason=?,"
        "dataset_version=dataset_version+1 WHERE dataset_id=?",
        (_now(), actor, reason, dataset_id))
    conn.commit()
    return create_version(conn, dataset_id, actor=actor, note="冻结：" + reason)


def reopen(conn: sqlite3.Connection, dataset_id: str, *, actor: str, reason: str) -> dict:
    """解冻只新增版本，不擦除冻结历史；之后才允许新上传。"""
    conn.execute(
        "UPDATE datasets SET status='PLANNED',frozen_at=NULL,frozen_by=NULL,freeze_reason=NULL,"
        "dataset_version=dataset_version+1 WHERE dataset_id=?", (dataset_id,))
    conn.commit()
    return create_version(conn, dataset_id, actor=actor, note="解冻：" + reason)


def versions(conn: sqlite3.Connection, dataset_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM dataset_versions WHERE dataset_id=? ORDER BY version", (dataset_id,))]


def report(conn: sqlite3.Connection, dataset_id: str) -> dict:
    dataset = dict(conn.execute("SELECT * FROM datasets WHERE dataset_id=?",
                                (dataset_id,)).fetchone())
    members = [dict(r) for r in conn.execute(
        "SELECT m.device_id,d.station_id FROM dataset_members m LEFT JOIN devices d "
        "ON d.device_id=m.device_id WHERE m.dataset_id=? ORDER BY m.device_id", (dataset_id,))]
    snapshot = _snapshot(conn, dataset_id)
    return {"dataset": dataset, "members": members,
            "phase_boundaries": {k: dataset[k] for k in
                                 ("start_time", "end_time", "formal_sync_time",
                                  "installation_status", "status", "dataset_version")},
            "snapshot": snapshot, "versions": versions(conn, dataset_id)}
