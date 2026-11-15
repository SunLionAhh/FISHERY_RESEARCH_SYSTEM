# -*- coding: utf-8 -*-
"""S01 数据库连接与迁移机制。

迁移规则（V4 02 第六章纪律）：
- 已应用版本记录在 schema_migrations，重复执行幂等；
- 迁移前检查现状：库不存在则新建；库存在则只追加未应用迁移，不覆盖任何数据；
- 每个迁移文件在独立事务中执行。
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import db_path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def migrate(conn: sqlite3.Connection) -> list[str]:
    """按文件名顺序应用未执行的迁移，返回本次应用的版本列表。幂等。"""
    has_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    applied = set()
    if has_table:
        applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}

    newly_applied = []
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = sql_file.stem.split("_", 1)[0]
        if version in applied:
            continue
        sql = sql_file.read_text(encoding="utf-8")
        try:
            conn.execute("BEGIN")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (version, sql_file.stem, _now()),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        newly_applied.append(version)
    return newly_applied


def ensure_database(conn: sqlite3.Connection) -> list[str]:
    """迁移前置检查 + 迁移 + 种子数据（幂等）。"""
    pre_state = {
        "db_existed_before": bool(
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='devices'"
            ).fetchone()
        )
    }
    applied = migrate(conn)
    if applied:
        # 种子数据只在设备表为空或缺失时插入，绝不覆盖既有行
        from .seed import run_seed
        run_seed(conn)
        conn.commit()
    # 前置状态写入审计，证明迁移未覆盖用户数据
    if applied:
        conn.execute(
            "INSERT INTO audit_logs (action, entity, entity_id, detail_json, created_at) VALUES (?,?,?,?,?)",
            ("MIGRATE", "database", "0001_init",
             f'{{"applied": {applied!r}, "pre_state": {pre_state!r}}}'.replace("'", '"'),
             _now()),
        )
        conn.commit()
    return applied
