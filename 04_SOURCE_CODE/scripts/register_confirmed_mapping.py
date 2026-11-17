# -*- coding: utf-8 -*-
"""S03 前置：登记 CONFIRMED 距离映射新版本（v2），解除 2000/2001 距离分析 BLOCKED。

依据（2026-11-16 微信“百岁山”确认 + 用户首点确认）：
- sample_mode = INTERVAL（“一段距离区间”）
- sample_interval_m = 0.0375（“一格是 3.75cm”“1000 个点一个点就是 3.75cm”）
- first_sample_distance_m = 0.5（用户确认，与盲区 0.5m 一致）
- range_m = 37.5、point_count = 1000（CSV 逐记录）
- 末格终点 = 0.5 + 1000 × 0.0375 = 38.0m（解释“末点不是 37.5”）
- 2001 适用依据：五台登记为“同型号探鱼仪”，且 2000/2001 信号数组结构完全一致。

旧版本（v1，UNVERIFIED）只读保留，不覆盖；本脚本幂等留痕，重复执行会再生成新版本。

用法（项目根目录）：
    .venv\\Scripts\\python.exe 04_SOURCE_CODE\\scripts\\register_confirmed_mapping.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]      # 04_SOURCE_CODE
sys.path.insert(0, str(SOURCE))

from app.db import connect  # noqa: E402
from app.identity import current_operator  # noqa: E402
from app.services.distance_mapping import (  # noqa: E402
    DistanceMapping,
    SAMPLE_MODE_INTERVAL,
    SUPPORT_CONFIRMED,
    build_mask,
    latest_mapping,
    register_mapping,
)

# ---- 已确认的物理参数（两台同型号，参数一致）----
RANGE_M = 37.5
POINT_COUNT = 1000
SAMPLE_MODE = SAMPLE_MODE_INTERVAL
FIRST_SAMPLE_DISTANCE_M = 0.5
SAMPLE_INTERVAL_M = 0.0375
CUTOFF_M = 5.2

EVIDENCE_2000 = (
    "采样语义=INTERVAL（微信“百岁山”确认“一段距离区间”）；"
    "单元宽度=0.0375m（“一格是3.75cm”“1000个点一个点就是3.75cm”）；"
    "首点距离=0.5m（用户2026-11-16确认，与盲区0.5m一致）；"
    "量程37.5m、1000槽（CSV逐记录）；末格终点=0.5+1000*0.0375=38.0m。"
)
EVIDENCE_2001 = EVIDENCE_2000 + (
    "2001适用依据：五台种子数据登记为“同型号探鱼仪”，且2000/2001信号数组结构完全一致"
    "（每行1000槽、量程37.5、值域0-255、1001token含尾部空项）；"
    "采样参数为同型号固件级硬件特性，按同型号外推。"
)
SOURCE_TAG = "WECHAT_BAISUISHAN_2026-11-16 + USER_CONFIRMED_FIRST_POINT"
DEVICES = ("2000", "2001")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def verify_before_register(mapping: DistanceMapping) -> None:
    """正式登记前的硬验证：阻断原因为空 + build_mask 正式模式 OK/125 格。"""
    reasons = mapping.blocking_reasons(row_range_m=RANGE_M, row_point_count=POINT_COUNT)
    assert not reasons, f"映射仍存在阻断原因，拒绝登记：{reasons}"

    values = list(range(POINT_COUNT))           # 0..999 构造信号，仅验证掩码结构
    result = build_mask(
        values, mapping, CUTOFF_M,
        row_range_m=RANGE_M, row_point_count=POINT_COUNT, allow_blocked=False,
    )
    assert result.status == "OK", f"正式掩码应为 OK，实际 {result.status}"
    assert result.kept_count == 125, f"5.2m 截断应保留 125 格，实际 {result.kept_count}"
    assert result.kept_indices == tuple(range(125)), "保留下标应为 0..124"
    # 第 125 格 [5.1875, 5.225) 跨界 5.2 → 整段排除；其后为人工越界
    cross = [i for (i, r) in result.excluded_reasons if r == "CROSS_BOUNDARY_INTERVAL_EXCLUDED"]
    assert cross == [125], f"跨界区间应为第125格，实际 {cross}"
    out = [i for (i, r) in result.excluded_reasons if r == "OUT_OF_RANGE_MANUAL_CUTOFF"]
    assert out == list(range(126, 1000)), "第126格起应为人工越界"


def main() -> None:
    operator = current_operator()
    conn = connect()
    try:
        for device_id in DEVICES:
            evidence = EVIDENCE_2000 if device_id == "2000" else EVIDENCE_2001
            mapping = DistanceMapping(
                device_id=device_id,
                range_m=RANGE_M,
                point_count=POINT_COUNT,
                sample_mode=SAMPLE_MODE,
                first_sample_distance_m=FIRST_SAMPLE_DISTANCE_M,
                sample_interval_m=SAMPLE_INTERVAL_M,
                support_status=SUPPORT_CONFIRMED,
                evidence=evidence,
                source=SOURCE_TAG,
            )
            verify_before_register(mapping)
            version = register_mapping(conn, mapping, operator=operator)
            conn.execute(
                "INSERT INTO audit_logs (action, entity, entity_id, detail_json, actor, created_at) "
                "VALUES ('CONFIRM_MAPPING','distance_mappings',?,?,?,?)",
                (
                    device_id,
                    f'{{"version":{version},"sample_mode":"INTERVAL",'
                    f'"first_sample_distance_m":0.5,"sample_interval_m":0.0375,'
                    f'"range_m":37.5,"point_count":1000}}',
                    operator,
                    _now(),
                ),
            )
            persisted = latest_mapping(conn, device_id, RANGE_M)
            print(
                f"[{device_id}] 已登记 CONFIRMED v{version}；"
                f"复核 support={persisted.support_status} mode={persisted.sample_mode} "
                f"first={persisted.first_sample_distance_m} interval={persisted.sample_interval_m}"
            )
        conn.commit()
        print("全部提交完成：2000/2001 距离映射 CONFIRMED，build_mask 正式解阻（5.2m 保留 125 格）。")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
