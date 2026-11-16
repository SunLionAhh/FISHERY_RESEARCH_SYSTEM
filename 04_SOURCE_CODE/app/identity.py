# -*- coding: utf-8 -*-
"""操作者身份（P2-3）。

本机单用户、无登录鉴权 → 取操作系统登录名作为**弱标识**，写入 created_by / audit_logs.actor，
避免审计链恒为 'web' 无法区分操作者。S10 若引入多用户登录，应替换为账号主体。
"""
import getpass
import os


def current_operator() -> str:
    """优先 USERNAME（Windows）→ USER → getpass；兜底 unknown_operator。"""
    for candidate in (os.environ.get("USERNAME"), os.environ.get("USER"), os.environ.get("LOGNAME")):
        if candidate and candidate.strip():
            return candidate.strip()
    try:
        name = getpass.getuser()
    except Exception:  # 无登录会话时（如服务账户）不得因此中断保存
        name = ""
    return name.strip() or "unknown_operator"
