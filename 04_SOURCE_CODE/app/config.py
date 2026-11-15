# -*- coding: utf-8 -*-
"""S01 项目配置：路径解析与数据库位置。"""
import os
from pathlib import Path

# 04_SOURCE_CODE/app/config.py -> parents[2] = 项目根 FISHERY_RESEARCH_SYSTEM
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_DIR = PROJECT_ROOT / "03_DATABASE"


def db_path() -> Path:
    """数据库文件位置：默认 03_DATABASE/fishery.db，可用环境变量覆盖（测试用）。"""
    env = os.environ.get("FISHERY_DB_PATH")
    if env:
        return Path(env)
    return DATABASE_DIR / "fishery.db"


def original_data_root() -> Path:
    return PROJECT_ROOT / "01_ORIGINAL_DATA"
