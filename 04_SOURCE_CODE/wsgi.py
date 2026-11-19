# -*- coding: utf-8 -*-
"""生产 WSGI 入口：供 gunicorn 在服务器上加载 Flask 应用。"""
from app import create_app

application = app = create_app()
