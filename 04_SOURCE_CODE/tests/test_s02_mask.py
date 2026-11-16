# -*- coding: utf-8 -*-
"""S02 K04—K06：距离映射与统一硬掩码（不修改既有断言）。"""
import math

import pytest

from app.services import distance_mapping as dm


def point_mapping(**overrides):
    data = dict(
        device_id="2000", range_m=37.5, point_count=1000,
        sample_mode=dm.SAMPLE_MODE_POINT, first_sample_distance_m=0.0375,
        sample_interval_m=0.0375, support_status=dm.SUPPORT_CONFIRMED,
        version=1, evidence="unit test", source="TEST",
    )
    data.update(overrides)
    return dm.DistanceMapping(**data)


def interval_mapping(**overrides):
    data = dict(
        device_id="2000", range_m=37.5, point_count=100,
        sample_mode=dm.SAMPLE_MODE_INTERVAL, first_sample_distance_m=0.0,
        sample_interval_m=0.5, support_status=dm.SUPPORT_CONFIRMED,
        version=1, evidence="unit test", source="TEST",
    )
    data.update(overrides)
    return dm.DistanceMapping(**data)


# ---------------- K04：点样本边界（5.199 / 5.200 / 5.201） ----------------

def test_k04_point_boundary_5199_5200_kept_5201_excluded():
    result = dm.mask_points([5.199, 5.200, 5.201], [10, 20, 99], 5.2, device_id="2000")
    assert result.kept_indices == (0, 1)
    assert result.kept_values == (10.0, 20.0)
    assert result.excluded_counts == {dm.REASON_OUT_OF_RANGE: 1}
    assert (2, dm.REASON_OUT_OF_RANGE) in result.excluded_reasons
    # 5.201 不得因显示精度四舍五入被保留
    assert 2 not in result.kept_indices


def test_k04_no_float_epsilon_extends_cutoff():
    eps = 1e-12
    result = dm.mask_points([5.2, 5.2 + eps], [1, 2], 5.2)
    assert result.kept_indices == (0,)
    assert result.kept_values == (1.0,)


def test_k04_invalid_and_unknown_distance_reasons():
    result = dm.mask_points([5.0, None, 5.1], [1, 2, None], 5.2)
    assert result.kept_indices == (0,)
    assert result.excluded_counts[dm.REASON_DISTANCE_UNKNOWN] == 1
    assert result.excluded_counts[dm.REASON_INVALID_VALUE] == 1


def test_k04_out_of_range_amplitude_change_does_not_affect_inside_result():
    """越界强回波：改变界外幅度，区内保留值/计数/求和完全不变。"""
    distances = [5.0, 5.1, 5.2, 5.201, 6.0]
    inside = [11.0, 22.0, 33.0]
    a = dm.mask_points(distances, inside + [0.0, 0.0], 5.2)
    b = dm.mask_points(distances, inside + [65535.0, 1e9], 5.2)
    assert a.kept_indices == b.kept_indices == (0, 1, 2)
    assert a.kept_values == b.kept_values == (11.0, 22.0, 33.0)
    assert sum(a.kept_values) == sum(b.kept_values)
    assert a.excluded_counts == b.excluded_counts == {dm.REASON_OUT_OF_RANGE: 2}


# ---------------- K05：区间采样与跨界 ----------------

def test_k05_crossing_interval_excluded_whole():
    starts = [4.6, 4.9, 5.0, 5.2]
    values = [1, 2, 3, 4]
    result = dm.mask_intervals(starts, 0.5, values, 5.2)
    # [4.6,5.1) 全内 → 保留；[4.9,5.4) 跨界 → 整段排除；[5.0,5.5) 跨界 → 排除；[5.2,5.7) 起始即界外
    assert result.kept_indices == (0,)
    assert result.excluded_counts[dm.REASON_CROSS_BOUNDARY] == 2
    assert result.excluded_counts[dm.REASON_OUT_OF_RANGE] == 1
    # 中心在界内（5.15）也不得纳入
    assert 1 not in result.kept_indices


def test_k05_interval_whole_inside_kept():
    result = dm.mask_intervals([0.0, 0.5, 4.5], 0.5, [5, 6, 7], 5.2)
    assert result.kept_indices == (0, 1, 2)
    assert result.kept_values == (5.0, 6.0, 7.0)
    assert result.excluded_counts == {}


def test_k05_interval_requires_positive_width():
    with pytest.raises(ValueError):
        dm.mask_intervals([0.0], 0.0, [1], 5.2)


# ---------------- K06：映射未核实 → 正式分析 BLOCKED ----------------

def test_k06_unknown_mapping_blocks_formal_analysis():
    mapping = point_mapping(sample_mode=dm.SAMPLE_MODE_UNKNOWN,
                            first_sample_distance_m=None, sample_interval_m=None,
                            support_status=dm.SUPPORT_UNVERIFIED)
    with pytest.raises(dm.DistanceMappingBlocked) as exc:
        dm.build_mask([1, 2, 3], mapping, 5.2, row_range_m=37.5, row_point_count=3)
    assert any("采样语义未核实" in r for r in exc.value.reasons)
    assert any("首点距离未核实" in r for r in exc.value.reasons)


def test_k06_allow_blocked_returns_no_kept_samples_and_keeps_reason():
    mapping = point_mapping(sample_mode=dm.SAMPLE_MODE_UNKNOWN,
                            first_sample_distance_m=None, sample_interval_m=None,
                            support_status=dm.SUPPORT_UNVERIFIED)
    result = dm.build_mask([1, 2, 3, 4], mapping, 5.2, row_range_m=37.5,
                           row_point_count=4, allow_blocked=True)
    assert result.status == "BLOCKED"
    assert result.kept_indices == () and result.kept_values == ()
    assert result.excluded_counts == {dm.REASON_MAPPING_UNVERIFIED: 4}
    assert result.blocked_reasons


def test_k06_range_mismatch_blocks():
    mapping = point_mapping(range_m=37.5)
    reasons = mapping.blocking_reasons(row_range_m=50.0, row_point_count=1000)
    assert any("量程" in r for r in reasons)


def test_k06_point_count_mismatch_blocks():
    mapping = point_mapping(point_count=1000)
    assert any("点数" in r for r in mapping.blocking_reasons(row_range_m=37.5,
                                                              row_point_count=999))


def test_k06_no_mapping_in_db_is_blocked(conn):
    with pytest.raises(dm.DistanceMappingBlocked):
        dm.mask_row_with_mapping(conn, "2002", 5.2, [1, 2, 3],
                                 row_range_m=37.5, row_point_count=3)
    result = dm.mask_row_with_mapping(conn, "2002", 5.2, [1, 2, 3],
                                      row_range_m=37.5, row_point_count=3,
                                      allow_blocked=True)
    assert result.status == "BLOCKED"
    assert result.excluded_counts == {dm.REASON_MAPPING_UNVERIFIED: 3}


# ---------------- 版本化持久化 ----------------

def test_mapping_versions_are_appended_not_overwritten(conn):
    v1 = dm.register_mapping(conn, point_mapping(), operator="tester")
    v2 = dm.register_mapping(conn, point_mapping(evidence="second"), operator="tester")
    conn.commit()
    assert (v1, v2) == (1, 2)
    latest = dm.latest_mapping(conn, "2000", 37.5)
    assert latest.version == 2 and latest.evidence == "second"
    rows = conn.execute("SELECT COUNT(*) n FROM distance_mappings").fetchone()["n"]
    assert rows == 2  # 旧版本保留


def test_confirmed_point_mapping_builds_mask_through_mapping():
    mapping = point_mapping(point_count=200)
    values = [1] * 200
    result = dm.build_mask(values, mapping, 5.2, row_range_m=37.5, row_point_count=200)
    assert result.status == "OK"
    # r_k = 0.0375 * k (k=1..200)；k <= 5.2/0.0375 = 138.67 → 138 点
    expected_kept = int(math.floor(5.2 / 0.0375))
    assert result.kept_count == expected_kept == 138
    assert result.kept_count < len(values)
