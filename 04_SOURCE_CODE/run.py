# -*- coding: utf-8 -*-
"""S01 本地启动入口：仅绑定 127.0.0.1。

运行：.venv\\Scripts\\python.exe run.py   （在 04_SOURCE_CODE 目录下）
"""
from app import create_app

if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=False)
