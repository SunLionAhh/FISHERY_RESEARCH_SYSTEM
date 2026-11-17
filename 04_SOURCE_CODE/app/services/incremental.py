# -*- coding: utf-8 -*-
"""S03 逐日增量上传、补传、冲突审查与缺测登记（K17/K18/K40）。

- 一天一文件、一台一批次；允许不连续日期、缺测、迟到与历史补传。
- 原始文件只读；登记用 SHA-256 与归档清单对账，绝不写回。
- 每次上传生成新的 analysis_runs.run_id 与完整参数/映射/算法快照；旧 run 改 SUPERSEDED，不删除。
- 单台 BLOCKED 只阻断本台，不影响其他设备。
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from ..config import PROJECT_ROOT
from ..db import _now
from ..identity import current_operator
from . import daily_stats as ds
from . import devices as device_service
from .csv_parser import inspect_file, sha256_file

DATE_IN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})")

DECISION_NEW = "NEW"
DECISION_DUPLICATE = "DUPLICATE"
DECISION_REPROCESSED = "REPROCESSED"
DECISION_BLOCKED = "BLOCKED"


class UploadConflict(Exception):
    """同日不同内容或同名异容：必须人工审查，force 才允许继续。"""

    def __init__(self, message: str, *, existing_run_id: str | None = None):
        super().__init__(message)
        self.existing_run_id = existing_run_id


class FrozenDatasetBlocked(Exception):
    """数据集已冻结，不得再写入新结果。"""


class UploadValidationError(Exception):
    """上传参数不合法。"""


@dataclass
class UploadOutcome:
    decision: str
    device_id: str
    observed_date: str
    run_id: str | None
    batch_id: str | None
    stat_id: int | None
    status: str
    blocked_reasons: tuple[str, ...]
    file_sha256: str
    artifacts: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "decision": self.decision, "device_id": self.device_id,
            "observed_date": self.observed_date, "run_id": self.run_id,
            "batch_id": self.batch_id, "stat_id": self.stat_id, "status": self.status,
            "blocked_reasons": list(self.blocked_reasons),
            "file_sha256": self.file_sha256, "artifacts": list(self.artifacts),
        }


def _new_id(prefix: str, *parts: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{'-'.join(parts)}-{stamp}-{uuid.uuid4().hex[:6]}"


def relative_path_of(path: Path, project_root: Path = PROJECT_ROOT) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def observed_date_of(path: Path, explicit: str | None = None) -> str:
    if explicit:
        try:
            datetime.strptime(explicit, "%Y-%m-%d")
        except ValueError as exc:
            raise UploadValidationError(f"observed_date 必须为 YYYY-MM-DD：{explicit}") from exc
        return explicit
    match = DATE_IN_NAME.search(path.name)
    if not match:
        raise UploadValidationError(f"文件名中没有 YYYY-MM-DD，请显式给出 observed_date：{path.name}")
    return match.group(1)


def check_not_frozen(conn: sqlite3.Connection, device_id: str, observed_date: str) -> None:
    rows = conn.execute(
        """SELECT d.dataset_id, d.name FROM datasets d
           JOIN dataset_members m ON m.dataset_id = d.dataset_id
           WHERE m.device_id = ? AND UPPER(d.status) = 'FROZEN'
             AND (d.start_time IS NULL OR d.start_time <= ?)
             AND (d.end_time IS NULL OR d.end_time >= ?)""",
        (device_id, observed_date, observed_date),
    ).fetchall()
    if rows:
        names = ", ".join(f"{r['dataset_id']}({r['name']})" for r in rows)
        raise FrozenDatasetBlocked(f"{device_id} {observed_date} 已被冻结数据集保护：{names}")


def _registry_rows(conn: sqlite3.Connection, relative_path: str,
                   device_id: str, observed_date: str) -> list[sqlite3.Row]:
    return list(conn.execute(
        """SELECT * FROM file_registry
           WHERE relative_path = ?
              OR (device_id = ? AND observed_date = ?)""",
        (relative_path, device_id, observed_date),
    ))


def _later_dates(conn: sqlite3.Connection, device_id: str, observed_date: str) -> list[str]:
    return [r["observed_date"] for r in conn.execute(
        "SELECT DISTINCT observed_date FROM daily_statistics WHERE device_id=? AND observed_date>? "
        "ORDER BY observed_date", (device_id, observed_date))]


def register_upload(conn: sqlite3.Connection, device_id: str, path: Path, *,
                    observed_date: str | None = None,
                    upload_date: str | None = None,
                    project_root: Path = PROJECT_ROOT,
                    force: bool = False,
                    operator: str | None = None,
                    dataset_id: str | None = None,
                    planned_window_s: int = ds.PLANNED_WINDOW_S,
                    event_threshold: float = ds.DEFAULT_EVENT_THRESHOLD,
                    event_min_bins: int = ds.DEFAULT_EVENT_MIN_BINS,
                    limit: int | None = None,
                    generate_outputs: bool = True,
                    output_root: Path | None = None) -> UploadOutcome:
    """登记并统计一天。返回 decision：NEW / REPROCESSED / BLOCKED / DUPLICATE。"""
    if not path.exists():
        raise UploadValidationError(f"原始文件不存在：{path}")
    operator = operator or current_operator()
    observed_date = observed_date_of(path, observed_date)
    upload_date = upload_date or datetime.now(timezone.utc).date().isoformat()
    relative_path = relative_path_of(path, project_root)
    sha256 = sha256_file(path)
    inspection = inspect_file(path, compute_hash=False)

    try:
        existing = _registry_rows(conn, relative_path, device_id, observed_date)
        for row in existing:
            same_content = row["sha256"] == sha256
            already_imported = row["status"] == "IMPORTED"
            if same_content and already_imported and not force:
                previous = ds.latest_stat(conn, device_id, observed_date)
                return UploadOutcome(
                    DECISION_DUPLICATE, device_id, observed_date,
                    previous["run_id"] if previous else None, row["import_batch_id"],
                    previous["stat_id"] if previous else None,
                    previous["status"] if previous else ds.STATUS_UNKNOWN, (), sha256, (),
                )
            if not same_content:
                if not force:
                    old_stat = ds.latest_stat(conn, device_id, observed_date)
                    raise UploadConflict(
                        f"文件冲突：{relative_path} 已登记 SHA-256 {row['sha256'][:12]}…，"
                        f"本次为 {sha256[:12]}…；须人工审查后以 force=True 重传",
                        existing_run_id=old_stat["run_id"] if old_stat else None,
                    )
                conn.execute(
                    "UPDATE file_registry SET status='CONFLICT', conflict_note=? WHERE file_id=?",
                    (f"同名异容，用户 force 重传 {sha256}", row["file_id"]),
                )

        check_not_frozen(conn, device_id, observed_date)
        later = _later_dates(conn, device_id, observed_date)
        previous = ds.latest_stat(conn, device_id, observed_date)
        if force and previous is not None:
            decision = DECISION_REPROCESSED
            upload_status = ds.UPLOAD_REPROCESSED
        elif later:
            # 历史补传：后续日期存在 → 标记为 REPROCESSED 并登记受影响日期复核任务
            decision = DECISION_REPROCESSED
            upload_status = ds.UPLOAD_REPROCESSED
        else:
            decision = DECISION_NEW
            upload_status = (ds.UPLOAD_LATE if upload_date > observed_date else ds.UPLOAD_NORMAL)

        context = ds.resolve_stat_context(
            conn, device_id, device_service.device_range_m(conn, device_id))
        batch_id = _new_id("BATCH", device_id, observed_date.replace("-", ""))
        run_id = _new_id("RUN", device_id, observed_date.replace("-", ""))
        snapshot = context.snapshot()
        snapshot.update({
            "batch_id": batch_id, "dataset_id": dataset_id, "file_sha256": sha256,
            "relative_path": relative_path, "observed_date": observed_date,
            "upload_date": upload_date, "operator": operator,
            "planned_window_s": planned_window_s, "event_threshold": event_threshold,
            "event_min_bins": event_min_bins, "limit": limit,
            "upload_status": upload_status,
        })
        conn.execute(
            """INSERT INTO analysis_runs (run_id, dataset_id, device_id, params_snapshot_json, status, created_at)
               VALUES (?,?,?,?,?,?)""",
            (run_id, dataset_id, device_id, json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
             "PENDING", _now()),
        )
        conn.execute(
            """INSERT INTO import_batches (batch_id, device_id, upload_date, file_count, status, notes)
               VALUES (?,?,?,?,?,?)""",
            (batch_id, device_id, observed_date, 1, "CLOSED",
             f"逐日上传；decision={decision}；upload_date={upload_date}"),
        )
        # file_registry 已由 S01 归档登记 21 行；这里只更新导入状态，不新建重复文件行。
        registry = [r for r in existing if r["relative_path"] == relative_path]
        if registry:
            conn.execute(
                "UPDATE file_registry SET status='IMPORTED', import_batch_id=?, conflict_note=NULL "
                "WHERE file_id=?", (batch_id, registry[0]["file_id"]),
            )
        else:
            conn.execute(
                """INSERT INTO file_registry (relative_path, file_name, device_id, observed_date,
                   size_bytes, sha256, status, import_batch_id, conflict_note, registered_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (relative_path, path.name, device_id, observed_date, path.stat().st_size,
                 sha256, "IMPORTED", batch_id, None, _now()),
            )

        if not context.usable:
            row = ds.blocked_row(device_id, observed_date, run_id, context.reasons,
                                 upload_status=ds.UPLOAD_BLOCKED)
            decision = DECISION_BLOCKED
            run_status = "BLOCKED"
        else:
            row = ds.compute_daily_statistics(
                conn, device_id, observed_date, path, run_id=run_id, context=context,
                limit=limit, planned_window_s=planned_window_s, event_threshold=event_threshold,
                event_min_bins=event_min_bins, dataset_id=dataset_id,
                upload_status=upload_status, inspection=inspection, file_sha256=sha256,
            )
            run_status = row["status"]
        row["dataset_id"] = dataset_id
        stat_id = ds.insert_stat_row(conn, row)

        # 旧 run 只标 SUPERSEDED，不删历史；补传触发后续日期复核留痕。
        conn.execute(
            """UPDATE analysis_runs SET status='SUPERSEDED'
               WHERE device_id=? AND run_id<>? AND run_id IN
                 (SELECT run_id FROM daily_statistics WHERE device_id=? AND observed_date=?)""",
            (device_id, run_id, device_id, observed_date),
        )
        conn.execute("UPDATE analysis_runs SET status=? WHERE run_id=?", (run_status, run_id))
        conn.execute(
            "INSERT INTO audit_logs (action, entity, entity_id, detail_json, actor, created_at) "
            "VALUES (?,?,?,?,?,?)",
            ("IMPORT_DAILY", "analysis_runs", run_id,
             json.dumps({"device_id": device_id, "observed_date": observed_date,
                         "decision": decision, "status": row["status"],
                         "sha256": sha256, "later_dates_checked": later}, ensure_ascii=False),
             operator, _now()),
        )

        artifacts: tuple[str, ...] = ()
        if generate_outputs:
            from .reporting import generate_daily_outputs
            artifacts = generate_daily_outputs(
                conn, row, project_root=project_root, output_root=output_root,
            )
            row["report_path"] = next((p for p in artifacts if p.endswith(".md")), None)
            conn.execute("UPDATE daily_statistics SET report_path=? WHERE stat_id=?",
                         (row["report_path"], stat_id))
            register_artifacts(conn, run_id, device_id, observed_date, artifacts, project_root)
        write_analysis_index(conn, project_root)
        conn.commit()
        ensure_missing_days_between(conn, device_id, project_root)
        return UploadOutcome(
            decision, device_id, observed_date, run_id, batch_id, stat_id, row["status"],
            tuple(context.reasons), sha256, artifacts,
        )
    except Exception:
        conn.rollback()
        raise


def mark_missing(conn: sqlite3.Connection, device_id: str, observed_date: str, *,
                 note: str = "人工登记缺测", project_root: Path = PROJECT_ROOT) -> int:
    """显式登记缺测日；指标全部 NA，绝不填 0。"""
    if not observed_date:
        raise UploadValidationError("登记缺测必须给出 observed_date")
    try:
        datetime.strptime(observed_date, "%Y-%m-%d")
    except ValueError as exc:
        raise UploadValidationError(f"observed_date 必须为 YYYY-MM-DD：{observed_date}") from exc
    check_not_frozen(conn, device_id, observed_date)
    row = ds.missing_row(device_id, observed_date)
    row["qc_notes"] = note
    stat_id = ds.insert_stat_row(conn, row)
    conn.execute(
        "INSERT INTO audit_logs (action, entity, entity_id, detail_json, actor, created_at) "
        "VALUES (?,?,?,?,?,?)",
        ("MARK_MISSING", "daily_statistics", device_id,
         json.dumps({"observed_date": observed_date, "stat_id": stat_id, "note": note},
                    ensure_ascii=False), current_operator(), _now()),
    )
    write_analysis_index(conn, project_root)
    conn.commit()
    return stat_id


def ensure_missing_days_between(conn: sqlite3.Connection, device_id: str,
                                project_root: Path = PROJECT_ROOT) -> list[str]:
    """上传后把已观测日期区间内没有文件的日子自动显示为 MISSING（不要求日期连续）。"""
    bounds = conn.execute(
        "SELECT MIN(observed_date) lo, MAX(observed_date) hi FROM daily_statistics WHERE device_id=?",
        (device_id,),
    ).fetchone()
    if not bounds or not bounds["lo"]:
        return []
    from datetime import timedelta
    current = datetime.strptime(bounds["lo"], "%Y-%m-%d")
    end = datetime.strptime(bounds["hi"], "%Y-%m-%d")
    created: list[str] = []
    while current <= end:
        date_text = current.date().isoformat()
        if ds.latest_stat(conn, device_id, date_text) is None:
            mark_missing(conn, device_id, date_text,
                         note="日期区间内未上传（自动缺测登记）", project_root=project_root)
            created.append(date_text)
        current += timedelta(days=1)
    return created


def list_conflicts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT * FROM file_registry WHERE status IN ('CONFLICT','ARCHIVED_REGISTERED') "
        "ORDER BY device_id, observed_date"
    ))


def register_artifacts(conn: sqlite3.Connection, run_id: str | None, device_id: str,
                       observed_date: str, paths: Sequence[str],
                       project_root: Path = PROJECT_ROOT) -> None:
    for artifact in paths:
        full = Path(artifact)
        if not full.is_absolute():
            full = project_root / artifact
        if not full.exists():
            continue
        rel = relative_path_of(full, project_root)
        conn.execute(
            """INSERT INTO s03_artifacts
               (run_id, device_id, observed_date, artifact_type, relative_path, sha256, created_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(run_id, artifact_type, relative_path)
               DO UPDATE SET sha256=excluded.sha256, created_at=excluded.created_at""",
            (run_id, device_id, observed_date, full.suffix.lstrip(".") or "file",
             rel, sha256_file(full), _now()),
        )


def write_analysis_index(conn: sqlite3.Connection, project_root: Path = PROJECT_ROOT) -> Path:
    rows = ds.all_latest_stats(conn)
    payload = {
        "stage": "S03",
        "generated_at": _now(),
        "latest_run_by_device_date": {
            f"{r['device_id']}/{r['observed_date']}": {
                "run_id": r["run_id"], "status": r["status"],
                "coverage_ratio": r["coverage_ratio"],
                "valid_records": r["valid_records"],
                "report_path": r["report_path"],
            }
            for r in rows
        },
        "blocked": [f"{r['device_id']}/{r['observed_date']}" for r in rows
                    if r["status"] == ds.STATUS_BLOCKED],
        "missing": [f"{r['device_id']}/{r['observed_date']}" for r in rows
                    if r["status"] == ds.STATUS_MISSING],
    }
    out = project_root / "06_ANALYSIS_RESULTS" / "s03" / "analysis_index.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
