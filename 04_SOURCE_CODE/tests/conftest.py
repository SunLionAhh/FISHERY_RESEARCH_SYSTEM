# -*- coding: utf-8 -*-
"""S01 测试夹具：临时数据库 + Flask test_client（不污染 03_DATABASE 正式库）。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 04_SOURCE_CODE

from app import create_app  # noqa: E402
from app.db import connect  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    db_file = tmp_path / "s01_test.db"
    application = create_app(db_file)
    application.config["DB_FILE"] = db_file
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def conn(app):
    c = connect(app.config["DB_FILE"])
    yield c
    c.close()
