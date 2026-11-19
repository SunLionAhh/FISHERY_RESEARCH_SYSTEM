# -*- coding: utf-8 -*-
"""S01 本地启动入口：仅绑定 127.0.0.1。

运行：.venv\\Scripts\\python.exe run.py   （在 04_SOURCE_CODE 目录下）
"""
from flask import request

from app import create_app


def configure_dev_preview(app):
    """本地即时预览：模板与静态资源改动后刷新浏览器即生效，无需重启进程。

    仅作用于直接运行 run.py 启动的实例；验收测试通过 create_app() 创建的
    app 不受影响，因此后端数据契约与测试结果保持不变。
    """
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.jinja_env.auto_reload = True

    @app.after_request
    def _no_cache_dev_assets(resp):
        if request.path.startswith("/static/"):
            resp.headers["Cache-Control"] = "no-store, max-age=0"
        return resp

    return app


if __name__ == "__main__":
    app = configure_dev_preview(create_app())
    app.run(host="127.0.0.1", port=5000, debug=False)
