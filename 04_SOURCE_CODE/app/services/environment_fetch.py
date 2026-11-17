# -*- coding: utf-8 -*-
"""S05 自动获取适配器骨架与数据源评估（不联网、不冒充已核实）。

V4 要求：核实空间覆盖/时间分辨率/单位/实测预报属性/授权/API 限制；自动数据不得覆盖手动数据。
未核实项一律 BLOCKED，只写 fetch log；不生成假观测、不把模型预报标成现场实测。
"""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from . import environment_import as env

CANDIDATES = (
    {
        "adapter": "OPEN_METEO_MARINE", "provider": "Open-Meteo Marine API",
        "variables": ("WAVE_HEIGHT", "SEA_SURFACE_TEMP"),
        "spatial_coverage": "全球网格；研究水域的具体格点与近岸适用性未核实",
        "time_resolution": "逐小时（文档口径，未实测）",
        "observed_or_forecast": "MODEL_HISTORICAL/FORECAST",
        "license": "CC-BY 4.0（文档口径，需按用户实际用途复核）",
        "authorization": "公开 API，需复核署名要求",
        "api_limits": "有速率限制（文档口径，未压测）",
        "status": "BLOCKED",
        "reason": "未取得用户对数据源/授权/格点的书面确认；当前真实风速文件已来自 Open-Meteo 模型，不能重复当独立实测",
    },
    {
        "adapter": "NOAA_COOPS_TIDE", "provider": "NOAA CO-OPS",
        "variables": ("TIDE_HEIGHT",),
        "spatial_coverage": "美国站点为主；洞头附近是否有适用站点未核实",
        "time_resolution": "分钟级（文档口径）",
        "observed_or_forecast": "OBSERVED/FORECAST 混合",
        "license": "美国政府公开数据（需复核再分发条款）",
        "authorization": "公开；API key 与额度未配置",
        "api_limits": "有请求限额（未实测）",
        "status": "BLOCKED",
        "reason": "研究水域站点覆盖未核实，且用户尚未提供 API 凭证与数据源选择",
    },
    {
        "adapter": "LOCAL_CSV_POLL", "provider": "用户本地导出目录",
        "variables": ("WATER_TEMP", "TIDE_HEIGHT", "WIND_SPEED", "WIND_DIRECTION"),
        "spatial_coverage": "取决于文件元数据",
        "time_resolution": "取决于文件",
        "observed_or_forecast": "UNKNOWN",
        "license": "用户自有",
        "authorization": "需用户指定受监视目录",
        "api_limits": "无 API；文件系统轮询",
        "status": "BLOCKED",
        "reason": "未配置受监视目录；实现可插拔骨架但不启动后台任务",
    },
)


def evaluate() -> dict:
    return {
        "generated_at": datetime.now(dt_timezone.utc).isoformat(timespec="seconds") + "Z",
        "candidates": list(CANDIDATES),
        "policy": "未核实覆盖/分辨率/单位/属性/授权/API 限制前不得启用；自动数据不覆盖手动导入数据；失败只写 fetch log。",
        "enabled_adapters": [],
    }


def attempt(conn, adapter: str, parameter: dict | None = None) -> dict:
    known = {c["adapter"]: c for c in CANDIDATES}
    info = known.get(adapter)
    if info is None:
        error = f"未注册的适配器：{adapter}"
        return env.log_fetch(conn, adapter, "FAILED", parameter or {}, error=error)
    return env.log_fetch(conn, adapter, "BLOCKED", parameter or {},
                         records=0, error=info["reason"])


def adapter_skeleton() -> str:
    """供后续接线的最小接口契约说明；不实现网络请求。"""
    return ("class EnvironmentAdapter:\n"
            "    name: str\n"
            "    def validate(self, config: dict) -> None: ...\n"
            "    def fetch(self, start_utc, end_utc) -> list[dict]: ...\n"
            "    def to_observation(self, record: dict) -> dict: ...\n"
            "  # 写入前必须调用 environment_import.register_source(kind='AUTO')，\n"
            "  # 且 commit_import 的 UNIQUE 键保证手动来源不会被自动来源覆盖。")
