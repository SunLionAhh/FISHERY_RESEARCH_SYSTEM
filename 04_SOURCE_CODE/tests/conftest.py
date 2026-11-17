# -*- coding: utf-8 -*-
"""S01 测试夹具：临时数据库 + Flask test_client（不污染 03_DATABASE 正式库）。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 04_SOURCE_CODE

from app import create_app  # noqa: E402
from app.db import connect  # noqa: E402
from app.services import distance_mapping as dm  # noqa: E402


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


@pytest.fixture()
def s03_conn(app):
    """S03 测试库：在 S01 种子参数上登记 CONFIRMED v2 距离映射（与正式库一致）。"""
    c = connect(app.config["DB_FILE"])
    for device_id in ("2000", "2001"):
        dm.register_mapping(c, dm.DistanceMapping(
            device_id=device_id, range_m=37.5, point_count=1000,
            sample_mode=dm.SAMPLE_MODE_INTERVAL, first_sample_distance_m=0.5,
            sample_interval_m=0.0375, support_status=dm.SUPPORT_CONFIRMED,
            evidence="S03 测试合成映射", source="TEST"), operator="pytest")
    c.commit()
    yield c
    c.close()


@pytest.fixture()
def s03_output(tmp_path):
    return tmp_path / "s03_outputs"
