# -*- coding: utf-8 -*-
"""FISHERY_RESEARCH_SYSTEM Flask 工作台（S01 最小可用：设备/参数/GPS）。"""
from pathlib import Path

from flask import Flask

from .config import db_path
from .db import connect, ensure_database


def create_app(db_file: Path | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DB_FILE"] = db_file or db_path()
    app.config["SECRET_KEY"] = "fishery-research-local-only"

    with connect(app.config["DB_FILE"]) as conn:
        ensure_database(conn)

    from .web.routes import bp
    app.register_blueprint(bp)
    return app
