# -*- coding: utf-8 -*-
"""S07 波束几何：V4/GPS_BEAM_GEOMETRY 数值验收基准与参数版本解析。"""
from __future__ import annotations

import math

import pytest

from app.services import beam_geometry as geo


def test_2000_conditional_45deg_full15_numeric_reference():
    g = geo.beam_geometry(height_m=3.68, tilt_deg=45, beam_value_deg=15,
                          beam_kind="FULL", cutoff_m=5.2)
    assert math.isclose(g["center_axis_bottom_m"], 5.204306, abs_tol=0.001)
    assert math.isclose(g["axis_vertical_distance_at_R_m"], 3.676955, abs_tol=0.001)
    assert math.isclose(g["steeper_edge_bottom_m"], 4.638538, abs_tol=0.001)
    assert math.isclose(g["flatter_edge_bottom_m"], 6.045061, abs_tol=0.001)
    ellipse = g["uncut_ellipse"]
    assert math.isclose(ellipse["center_x_m"], 3.809816, abs_tol=0.001)
    assert math.isclose(ellipse["semi_major_m"], 0.986053, abs_tol=0.001)
    assert math.isclose(ellipse["semi_minor_m"], 0.691176, abs_tol=0.001)
    assert math.isclose(ellipse["area_m2"], 2.141109, abs_tol=0.001)
    assert math.isclose(g["cutoff_disk_radius_m"], 3.673908, abs_tol=0.001)
    assert math.isclose(g["water_volume_m3"], 2.35305, rel_tol=0.005)
    assert math.isclose(g["water_projection_max_forward_m"], 4.125437, abs_tol=0.001)
    assert g["bottom_hit_status"] == "PARTIAL_BOTTOM_HIT"
    assert g["numeric"]["converged"] and g["numeric"]["volume_relative_change"] <= 0.005
    assert g["cutoff_locked_m"] == 5.2 and g["theory_does_not_override_cutoff"]
    assert "HORIZONTAL_BOTTOM_ASSUMED" in g["assumptions"]


def test_vertical_90deg_analytic_regression():
    g = geo.beam_geometry(height_m=3.68, tilt_deg=90, beam_value_deg=15,
                          beam_kind="FULL", cutoff_m=5.2)
    beta = math.radians(7.5)
    expected_volume = math.pi * 3.68 ** 3 * math.tan(beta) ** 2 / 3
    expected_area = math.pi * (3.68 * math.tan(beta)) ** 2
    assert math.isclose(g["water_volume_m3"], expected_volume, rel_tol=0.005)
    assert math.isclose(g["retained_footprint"]["area_m2"], expected_area, rel_tol=0.005)


def test_full15_and_half7_5_are_equivalent():
    full = geo.beam_geometry(height_m=3.68, tilt_deg=45, beam_value_deg=15,
                             beam_kind="FULL", cutoff_m=5.2)
    half = geo.beam_geometry(height_m=3.68, tilt_deg=45, beam_value_deg=7.5,
                             beam_kind="HALF", cutoff_m=5.2)
    assert full["inputs"]["internal_half_angle_deg"] == half["inputs"]["internal_half_angle_deg"]
    assert math.isclose(full["water_volume_m3"], half["water_volume_m3"], rel_tol=1e-9)


def test_unknown_beam_type_or_too_flat_is_not_confirmed():
    with pytest.raises(geo.GeometryUnavailable, match="未确认"):
        geo.beam_geometry(height_m=3.68, tilt_deg=45, beam_value_deg=15,
                          beam_kind="UNKNOWN", cutoff_m=5.2)
    with pytest.raises(geo.GeometryUnavailable, match="不大于半角"):
        geo.beam_geometry(height_m=3.68, tilt_deg=5, beam_value_deg=15,
                          beam_kind="FULL", cutoff_m=5.2)


def test_effective_params_by_date_not_current_pointer(conn):
    source = dict(conn.execute(
        "SELECT * FROM device_parameter_versions WHERE device_id='2000' ORDER BY version DESC LIMIT 1"
    ).fetchone())
    source.pop("parameter_id")
    source.update({"version": 2, "effective_from": "2026-11-02", "effective_to": None,
                   "analysis_cutoff_slant_m": 5.3, "source": "S07_TEST",
                   "change_reason": "按日期生效版本测试"})
    conn.execute(
        "INSERT INTO device_parameter_versions (" + ",".join(source) + ") VALUES ("
        + ",".join("?" for _ in source) + ")", tuple(source.values()))
    conn.commit()
    old = geo.effective_params(conn, "2000", "2026-11-01")
    new = geo.effective_params(conn, "2000", "2026-11-02")
    assert old["version"] == 1 and old["analysis_cutoff_slant_m"] == 5.2
    assert new["version"] == 2 and new["analysis_cutoff_slant_m"] == 5.3
    assert old["parameter_id"] != new["parameter_id"]
    assert old["bottom_reference"]["vertical_height_m"] == 3.68
