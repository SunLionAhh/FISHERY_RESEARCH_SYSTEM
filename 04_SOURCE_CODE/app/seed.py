# -*- coding: utf-8 -*-
"""S01 种子数据（幂等，绝不覆盖既有行）。

数值全部来自已登记的用户输入，来源字段可追溯到：
- USER_PROVIDED_PARAMETERS.md（用户 2026-11-15 提供）
- 10_TEST_REPORTS/RAW_CSV_ARCHIVE_MANIFEST.csv（21 个归档 CSV 的 SHA-256）
- 用户 2026-11-15 裁定：15° 波束角为全角（FULL）
"""
import csv
import math
from datetime import datetime, timezone

from .config import PROJECT_ROOT

DEVICE_IDS = ["2000", "2001", "2002", "2003", "2005"]  # 无 2004（用户硬约束）

# 用户已确认参数（其余设备保持 UNKNOWN，禁止复制这些值）
SEED_PARAMS = {
    "2000": {
        "analysis_cutoff_slant_m": 5.2,
        "clearance_input_type": "VERTICAL",
        "vertical_bottom_clearance_m": 3.68,
        "downward_tilt_deg": 45.0,
        "tilt_reference": "USER_PROVIDED",
        "beam_angle_value_deg": 15.0,
        "beam_angle_kind": "FULL",  # 用户 2026-11-15 确认全角
        "heading_deg": None,        # 用户后天提供，暂 UNKNOWN
        "heading_reference": None,
        "source": "USER_PROVIDED_2026-11-15（USER_PROVIDED_PARAMETERS.md）",
        "change_reason": "S01 初始化：用户此前提供 5.2/3.68/45°；2026-11-15 确认 15° 为全角",
    },
    "2001": {
        "analysis_cutoff_slant_m": 5.2,
        "clearance_input_type": "VERTICAL",
        "vertical_bottom_clearance_m": 3.6,
        "downward_tilt_deg": None,  # 不默认继承 2000 的 45°
        "tilt_reference": None,
        "beam_angle_value_deg": 15.0,
        "beam_angle_kind": "FULL",  # 同型号；用户 2026-11-15 确认全角
        "heading_deg": None,
        "heading_reference": None,
        "source": "USER_PROVIDED_2026-11-15（USER_PROVIDED_PARAMETERS.md）",
        "change_reason": "S01 初始化：用户 2026-11-15 提供 5.2/3.6/坐标",
    },
}

SEED_POSITIONS = {
    "2000": {"longitude_deg": 121.2117505073547, "latitude_deg": 27.99346353124773},
    "2001": {"longitude_deg": 121.2130272388458, "latitude_deg": 27.99260143251764},
}

EFFECTIVE_FROM = "2026-10-31"  # 双站观测起始；正式区间待 S02 按文件内时间戳复核


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def derive_from_tilt(value: float, tilt_deg: float, input_type: str):
    """任务三：根据本台倾角在垂直离底高度与中心轴斜距之间换算（标记派生值）。

    VERTICAL 输入 → 派生轴斜距 = vertical / sin(tilt)；AXIS_SLANT 输入 → 派生垂直 = axis * sin(tilt)。
    """
    if tilt_deg is None or tilt_deg == 0:
        return None
    rad = math.radians(tilt_deg)
    if input_type == "VERTICAL":
        return round(value / math.sin(rad), 10)
    if input_type == "AXIS_SLANT":
        return round(value * math.sin(rad), 10)
    return None


def beam_angles(value: float | None, kind: str):
    """FULL: 半角 = value/2；HALF: 半角 = value；UNKNOWN: 两者皆 None。"""
    if value is None or kind == "UNKNOWN":
        return None, None
    if kind == "FULL":
        return value, round(value / 2.0, 10)
    return value, value  # HALF


def run_seed(conn) -> None:
    now = _now()

    # ---- devices（INSERT OR IGNORE：不覆盖任何既有设备行）----
    for device_id in DEVICE_IDS:
        conn.execute(
            "INSERT OR IGNORE INTO devices (device_id, model, status, notes, created_at, updated_at) "
            "VALUES (?, '同型号探鱼仪', ?, ?, ?, ?)",
            (
                device_id,
                "ACTIVE" if device_id in ("2000", "2001") else "PENDING_USER_INPUT",
                "第一阶段双站" if device_id in ("2000", "2001") else "待用户提供参数与坐标；数据待上传",
                now, now,
            ),
        )

    # ---- device_parameter_versions + device_parameters 指针 ----
    for device_id, p in SEED_PARAMS.items():
        has = conn.execute(
            "SELECT 1 FROM device_parameter_versions WHERE device_id = ?", (device_id,)
        ).fetchone()
        if has:
            continue
        derived = None
        if p["clearance_input_type"] == "VERTICAL" and p["downward_tilt_deg"]:
            derived = derive_from_tilt(p["vertical_bottom_clearance_m"], p["downward_tilt_deg"], "VERTICAL")
        full_angle, half_angle = beam_angles(p["beam_angle_value_deg"], p["beam_angle_kind"])
        cur = conn.execute(
            """INSERT INTO device_parameter_versions
               (device_id, version, clearance_input_type, vertical_bottom_clearance_m, axis_slant_m,
                derived_vertical_clearance_m, derived_axis_slant_m, derivation_tilt_deg, is_derived,
                analysis_cutoff_slant_m, downward_tilt_deg, tilt_reference,
                beam_angle_value_deg, beam_angle_kind, beam_full_angle_deg, beam_half_angle_deg,
                heading_deg, heading_reference, source, change_reason,
                effective_from, created_at, created_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                device_id, 1, p["clearance_input_type"],
                p["vertical_bottom_clearance_m"], None,
                None,
                derived,                        # 派生轴斜距（如 3.68/45° → 5.2043…，仅参考，不覆盖 5.2）
                p["downward_tilt_deg"], 1 if derived is not None else 0,
                p["analysis_cutoff_slant_m"], p["downward_tilt_deg"], p["tilt_reference"],
                p["beam_angle_value_deg"], p["beam_angle_kind"], full_angle, half_angle,
                p["heading_deg"], p["heading_reference"], p["source"], p["change_reason"],
                EFFECTIVE_FROM, now, "seed",
            ),
        )
        conn.execute(
            "INSERT INTO device_parameters (device_id, current_parameter_id, updated_at) VALUES (?,?,?)",
            (device_id, cur.lastrowid, now),
        )
        conn.execute(
            "INSERT INTO audit_logs (action, entity, entity_id, detail_json, actor, created_at) "
            "VALUES ('SEED_PARAM','device_parameter_versions',?,?,'seed',?)",
            (device_id, f'{{"version":1,"source":"{p["source"]}"}}', now),
        )

    # ---- device_positions（历史保留，只追加）----
    for device_id, pos in SEED_POSITIONS.items():
        has = conn.execute(
            "SELECT 1 FROM device_positions WHERE device_id = ?", (device_id,)
        ).fetchone()
        if has:
            continue
        conn.execute(
            """INSERT INTO device_positions
               (device_id, version, longitude_deg, latitude_deg, coordinate_reference_system,
                position_accuracy_m, position_source, heading_deg, heading_reference,
                effective_from, notes, created_at, created_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                device_id, 1, pos["longitude_deg"], pos["latitude_deg"],
                None,  # CRS 未说明 → UNKNOWN，禁止默认 WGS84
                None,  # 精度未提供；末位 1e-13° 为浮点残差，不得当定位精度
                "USER_PROVIDED_2026-11-15（USER_PROVIDED_PARAMETERS.md）",
                None, None,
                EFFECTIVE_FROM,
                "坐标系/精度/方位角待用户确认（方位角后天提供）",
                now, "seed",
            ),
        )

    # ---- bottom_references：2000 人工水底参考面（任务五初始配置）----
    has_br = conn.execute(
        "SELECT 1 FROM bottom_references WHERE device_id='2000' AND reference_type='USER_DEFINED_ESTIMATED'"
    ).fetchone()
    if not has_br:
        conn.execute(
            """INSERT INTO bottom_references
               (device_id, reference_type, vertical_height_m, acoustic_bottom_status,
                effective_from, source, notes, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                "2000", "USER_DEFINED_ESTIMATED", 3.68, "NOT_DETECTED",
                EFFECTIVE_FROM,
                "USER_PROVIDED（人工设定，非厂家校准）",
                "2000 允许不启用自动探底；3.68 为人工水底参考面，5.2 为人工分析截断，二者独立",
                now,
            ),
        )

    # ---- datasets（任务六：两阶段数据集，引用原始数据不复制）----
    conn.execute(
        "INSERT OR IGNORE INTO datasets (dataset_id, name, phase, start_time, end_time, status, notes) "
        "VALUES ('DATASET_01_DUAL_STATION','第一阶段双站研究数据集',1,?,?,?,?)",
        (None, None, "PLANNED",
         "设备 2000/2001；起始待实际确认；结束待五站正式同步开始时间确定；天数不固定；同期窗口口径 2026-10-31—11-07 待 S02 复核"),
        )
    conn.execute(
        "INSERT OR IGNORE INTO datasets (dataset_id, name, phase, status, notes) "
        "VALUES ('DATASET_02_FIVE_STATION','第二阶段五站研究数据集',2,'PLANNED',?)",
        ("设备 2000/2001/2002/2003/2005；起始待五站正式同步运行确认；目标 60—90 天或更长",),
    )
    for ds, members in (("DATASET_01_DUAL_STATION", ("2000", "2001")),
                        ("DATASET_02_FIVE_STATION", DEVICE_IDS)):
        for device_id in members:
            conn.execute(
                "INSERT OR IGNORE INTO dataset_members (dataset_id, device_id) VALUES (?,?)",
                (ds, device_id),
            )

    # ---- file_registry（任务八：21 个归档 CSV 登记 + SHA-256 + 重复检查）----
    manifest = PROJECT_ROOT / "10_TEST_REPORTS" / "RAW_CSV_ARCHIVE_MANIFEST.csv"
    if manifest.is_file():
        with open(manifest, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                # observed_date 从文件名解析：探鱼-2000_2026-10-31.csv
                fname = row["file_name"]
                observed = fname.rsplit("_", 1)[-1].replace(".csv", "") if "_" in fname else None
                # 重复检查：UNIQUE(relative_path) + INSERT OR IGNORE；同哈希不同路径视为重复副本另行登记
                dup = conn.execute(
                    "SELECT file_id FROM file_registry WHERE sha256=? AND relative_path<>?",
                    (row["sha256_after"], row["archived_relative_path"]),
                ).fetchone()
                conflict_note = f"与 file_id={dup['file_id']} 内容相同（同哈希异路径）" if dup else None
                conn.execute(
                    """INSERT OR IGNORE INTO file_registry
                       (relative_path, file_name, device_id, observed_date, size_bytes, sha256,
                        status, conflict_note, registered_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        row["archived_relative_path"], fname, row["device_id"], observed,
                        int(row["size_bytes"]), row["sha256_after"],
                        "ARCHIVED_REGISTERED", conflict_note, now,
                    ),
                )
