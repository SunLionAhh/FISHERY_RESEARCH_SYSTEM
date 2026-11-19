# -*- coding: utf-8 -*-
"""S05 自动获取适配器骨架与数据源评估（不联网、不冒充已核实）。

V4 要求：核实空间覆盖/时间分辨率/单位/实测预报属性/授权/API 限制；自动数据不得覆盖手动数据。
未核实项一律 BLOCKED，只写 fetch log；不生成假观测、不把模型预报标成现场实测。
"""
from __future__ import annotations

import hashlib
import importlib
import json
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone

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


def _now_iso() -> str:
    return datetime.now(dt_timezone.utc).isoformat(timespec="seconds") + "Z"


def register_adapter(conn, name: str, module_path: str, *, status: str = "BLOCKED",
                     config: dict | None = None, actor: str = "S05") -> dict:
    """可插拔适配器注册；默认 BLOCKED，未核实数据源不得启用。"""
    if status not in ("BLOCKED", "ENABLED", "DISABLED"):
        raise ValueError(f"未知适配器状态：{status}")
    adapter_id = "ADAPTER-" + uuid.uuid4().hex[:10].upper()
    conn.execute(
        "INSERT INTO environment_adapter_registry (adapter_id,name,module_path,status,config_json,"
        "created_at,actor) VALUES (?,?,?,?,?,?,?)",
        (adapter_id, name, module_path, status,
         json.dumps(config or {}, ensure_ascii=False), _now_iso(), actor))
    conn.commit()
    return {"adapter_id": adapter_id, "name": name, "status": status}


def set_adapter_status(conn, name: str, status: str) -> None:
    if status not in ("BLOCKED", "ENABLED", "DISABLED"):
        raise ValueError(f"未知适配器状态：{status}")
    conn.execute("UPDATE environment_adapter_registry SET status=? WHERE name=?", (status, name))
    conn.commit()


def _load_adapter(module_path: str):
    module_name, _, attr = module_path.partition(":")
    module = importlib.import_module(module_name)
    target = getattr(module, attr) if attr else module
    if hasattr(target, "validate"):
        target.validate({})
    return target


def configure_schedule(conn, adapter: str, parameter: dict, *, interval_minutes: int = 60,
                       enabled: bool = True, actor: str = "S05") -> dict:
    row = conn.execute("SELECT adapter_id,status FROM environment_adapter_registry WHERE name=?",
                       (adapter,)).fetchone()
    if not row:
        raise KeyError(adapter)
    if enabled and row["status"] != "ENABLED":
        return {"status": "BLOCKED", "reason": "适配器未启用；不得启动定时获取",
                "adapter": adapter}
    schedule_id = "SCHED-" + uuid.uuid4().hex[:10].upper()
    next_run = (_now_iso() if enabled else None)
    conn.execute(
        "INSERT INTO environment_fetch_schedule (schedule_id,adapter_id,parameter_json,"
        "interval_minutes,enabled,next_run_at,created_at,actor) VALUES (?,?,?,?,?,?,?,?)",
        (schedule_id, row["adapter_id"], json.dumps(parameter, ensure_ascii=False),
         interval_minutes, int(enabled), next_run, _now_iso(), actor))
    conn.commit()
    return {"schedule_id": schedule_id, "status": "OK" if enabled else "DISABLED"}


def cached_fetch(conn, adapter: str, parameter: dict, *, ttl_minutes: int = 30,
                 actor: str = "S05") -> dict | None:
    key_raw = json.dumps({"adapter": adapter, "parameter": parameter}, ensure_ascii=False,
                         sort_keys=True)
    cache_key = hashlib.sha256(key_raw.encode("utf-8")).hexdigest()
    row = conn.execute("SELECT * FROM environment_fetch_cache WHERE cache_key=?",
                       (cache_key,)).fetchone()
    if row and (not row["expires_at"] or row["expires_at"] > _now_iso()):
        return {"status": "HIT", "payload": json.loads(row["payload_json"]),
                "fetched_at": row["fetched_at"]}
    return None


def _cache_result(conn, adapter: str, parameter: dict, records: list, *, ttl_minutes: int,
                  actor: str) -> None:
    key_raw = json.dumps({"adapter": adapter, "parameter": parameter}, ensure_ascii=False,
                         sort_keys=True)
    cache_key = hashlib.sha256(key_raw.encode("utf-8")).hexdigest()
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True)
    expires = (datetime.now(dt_timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat(
        timespec="seconds") + "Z"
    conn.execute(
        "INSERT OR REPLACE INTO environment_fetch_cache (cache_key,adapter_id,payload_json,sha256,"
        "fetched_at,expires_at,actor) VALUES (?,?,?,?,?,?,?)",
        (cache_key, adapter, payload, hashlib.sha256(payload.encode("utf-8")).hexdigest(),
         _now_iso(), expires, actor))
    conn.commit()


def fetch_with_retry(conn, adapter: str, start_utc: str, end_utc: str, *,
                     max_retries: int = 3, use_cache: bool = True,
                     actor: str = "S05") -> dict:
    """实际调用适配器：先查缓存，失败按次数重试并逐次写日志。"""
    parameter = {"start_utc": start_utc, "end_utc": end_utc}
    if use_cache:
        hit = cached_fetch(conn, adapter, parameter, actor=actor)
        if hit:
            return hit
    row = conn.execute("SELECT adapter_id,module_path,status FROM environment_adapter_registry "
                       "WHERE name=?", (adapter,)).fetchone()
    if not row:
        return env.log_fetch(conn, adapter, "FAILED", parameter, error="未注册适配器")
    if row["status"] != "ENABLED":
        return env.log_fetch(conn, adapter, "BLOCKED", parameter,
                             error="适配器状态非 ENABLED，不执行网络获取")
    last_error = None
    for attempt_no in range(1, max_retries + 1):
        try:
            target = _load_adapter(row["module_path"])
            records = target.fetch(start_utc, end_utc)
            _cache_result(conn, adapter, parameter, records, ttl_minutes=30, actor=actor)
            conn.execute("INSERT INTO environment_fetch_retry (adapter_id,attempt_no,status,"
                         "error,created_at) VALUES (?,?,?,?,?)",
                         (adapter, attempt_no, "SUCCESS", None, _now_iso()))
            conn.commit()
            return env.log_fetch(conn, adapter, "SUCCESS", parameter, records=len(records))
        except Exception as exc:
            last_error = str(exc)
            conn.execute("INSERT INTO environment_fetch_retry (adapter_id,attempt_no,status,"
                         "error,created_at) VALUES (?,?,?,?,?)",
                         (adapter, attempt_no, "FAILED", last_error, _now_iso()))
            conn.commit()
    return env.log_fetch(conn, adapter, "FAILED", parameter, error=last_error or "未知失败")


def run_due_schedules(conn, *, actor: str = "S05") -> list[dict]:
    """定时更新：扫描到期任务；无 ENABLED 适配器时保持空跑并留痕。"""
    now = _now_iso()
    due = list(conn.execute(
        "SELECT s.*,a.name FROM environment_fetch_schedule s "
        "JOIN environment_adapter_registry a ON a.adapter_id=s.adapter_id "
        "WHERE s.enabled=1 AND (s.next_run_at IS NULL OR s.next_run_at<=?)", (now,)))
    results = []
    for schedule in due:
        parameter = json.loads(schedule["parameter_json"])
        result = fetch_with_retry(conn, schedule["name"],
                                  parameter.get("start_utc", ""),
                                  parameter.get("end_utc", ""), actor=actor)
        next_run = (datetime.now(dt_timezone.utc)
                    + timedelta(minutes=schedule["interval_minutes"])).isoformat(
                        timespec="seconds") + "Z"
        conn.execute(
            "UPDATE environment_fetch_schedule SET last_run_at=?,last_status=?,next_run_at=?,"
            "failure_count=failure_count+? WHERE schedule_id=?",
            (now, result.get("status"), next_run,
             1 if result.get("status") == "FAILED" else 0, schedule["schedule_id"]))
        conn.commit()
        results.append({"schedule_id": schedule["schedule_id"], "result": result})
    return results


def backfill_history(conn, adapter: str, start_utc: str, end_utc: str, *,
                     chunk_hours: int = 24, actor: str = "S05") -> dict:
    """历史补取：按 UTC 区块顺序调用，失败不掩盖、不伪造记录。"""
    if chunk_hours <= 0:
        raise ValueError("chunk_hours 必须为正数")
    start = datetime.strptime(start_utc, "%Y-%m-%dT%H:%M:%SZ")
    end = datetime.strptime(end_utc, "%Y-%m-%dT%H:%M:%SZ")
    chunks = []
    current = start
    while current < end:
        stop = min(current + timedelta(hours=chunk_hours), end)
        result = fetch_with_retry(conn, adapter,
                                  current.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                  stop.strftime("%Y-%m-%dT%H:%M:%SZ"), actor=actor)
        chunks.append({"start_utc": current.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "end_utc": stop.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "status": result.get("status")})
        current = stop
    return {"adapter": adapter, "chunks": chunks,
            "status": "OK" if all(c["status"] == "SUCCESS" or c["status"] == "HIT"
                                  for c in chunks) else "PARTIAL"}
