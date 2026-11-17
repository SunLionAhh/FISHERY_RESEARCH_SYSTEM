# -*- coding: utf-8 -*-
"""S07 波束几何：条件算例、底面足迹、水体体积与理论底界参考。

全部为“均匀圆锥声束 + 直线传播 + 水平底面”条件下的几何估算；不替代厂家实测波束，
不改变用户人工分析截断 R，也不把理论中心轴底距当作声学实测底界。
"""
from __future__ import annotations

import math
import sqlite3
from datetime import date, datetime

ALGORITHM_VERSION = "BEAM_GEOM_V1"
HORIZONTAL_BOTTOM = "HORIZONTAL_BOTTOM_ASSUMED"
BEAM_KINDS = ("FULL", "HALF", "UNKNOWN")


class GeometryUnavailable(ValueError):
    pass


def effective_params(conn: sqlite3.Connection, device_id: str, observed_date: str) -> dict:
    """按观测日期解析生效参数版本（不是当前指针），并取同日生效的人工底界参考。"""
    row = conn.execute(
        "SELECT * FROM device_parameter_versions WHERE device_id=? "
        "AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?) "
        "ORDER BY effective_from DESC, version DESC LIMIT 1",
        (device_id, observed_date, observed_date)).fetchone()
    if row is None:
        raise GeometryUnavailable(f"{device_id}/{observed_date} 无生效参数版本")
    params = dict(row)
    bottom = conn.execute(
        "SELECT * FROM bottom_references WHERE device_id=? "
        "AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?) "
        "ORDER BY effective_from DESC, reference_id DESC LIMIT 1",
        (device_id, observed_date, observed_date)).fetchone()
    params["bottom_reference"] = dict(bottom) if bottom else None
    return params


def _beta_deg(beam_value_deg: float | None, beam_kind: str) -> float:
    if beam_value_deg is None or beam_kind not in BEAM_KINDS or beam_kind == "UNKNOWN":
        raise GeometryUnavailable("波束角值或全/半角类型未确认，只给条件算例")
    beta = beam_value_deg / 2 if beam_kind == "FULL" else beam_value_deg
    if not 0 < beta < 90:
        raise GeometryUnavailable("内部半角必须落在 (0,90)°")
    return beta


def _ellipse_radius(phi: float, xc: float, a: float, b: float) -> float:
    """从探头正下方原点沿底面方位 phi 到椭圆边界的距离。"""
    ca, sa = math.cos(phi), math.sin(phi)
    qa = (ca / a) ** 2 + (sa / b) ** 2
    qb = -2 * xc * ca / (a * a)
    qc = (xc / a) ** 2 - 1
    disc = qb * qb - 4 * qa * qc
    if disc <= 0:
        return 0.0
    root = math.sqrt(disc)
    return max(((-qb + root) / (2 * qa), (-qb - root) / (2 * qa)))


def _footprint_area(cutoff: float, h: float, xc: float, a: float, b: float,
                    steps: int) -> tuple[float, tuple[float, float]]:
    disk = math.sqrt(max(cutoff * cutoff - h * h, 0.0))
    if disk <= 0:
        return 0.0, (0.0, 0.0)
    dphi = 2 * math.pi / steps
    area = cx = cy = 0.0
    for index in range(steps):
        phi = (index + 0.5) * dphi
        limit = min(disk, _ellipse_radius(phi, xc, a, b))
        if limit <= 0:
            continue
        area += 0.5 * limit * limit * dphi
        cx += limit ** 3 * math.cos(phi) * dphi / 3
        cy += limit ** 3 * math.sin(phi) * dphi / 3
    if area <= 0:
        return 0.0, (0.0, 0.0)
    return area, (cx / area, cy / area)


def _integrate_volume(cutoff: float, h: float, alpha: float, beta: float,
                      r0: float, t_steps: int, phi_steps: int) -> tuple[float, float]:
    t0 = math.cos(beta)
    dt = (1.0 - t0) / t_steps
    dphi = 2 * math.pi / phi_steps
    volume = 0.0
    max_forward = -math.inf
    sa, ca = math.sin(alpha), math.cos(alpha)
    for ti in range(t_steps):
        t = t0 + (ti + 0.5) * dt
        sin_theta = math.sqrt(max(0.0, 1 - t * t))
        for pi in range(phi_steps):
            phi = (pi + 0.5) * dphi
            cphi, sphi = math.cos(phi), math.sin(phi)
            vx = t * ca - sin_theta * cphi * sa
            vy = sin_theta * sphi
            vz = t * sa + sin_theta * cphi * ca
            if vz <= 1e-12:
                continue
            r_bottom = h / vz
            rmax = min(cutoff, r_bottom)
            if rmax > r0:
                volume += (rmax ** 3 - r0 ** 3) * dt * dphi / 3
                max_forward = max(max_forward, rmax * vx)
    return volume, (max_forward if max_forward > -math.inf else 0.0)


def beam_geometry(*, height_m: float, tilt_deg: float, beam_value_deg: float,
                  beam_kind: str, cutoff_m: float, r0_m: float = 0.0,
                  t_steps: int = 400, phi_steps: int = 800,
                  beam_type_confirmed: bool = True) -> dict:
    """给定离底高度/倾角/波束/人工截断，给出条件几何量；R 永不被理论底距替换。"""
    if not height_m > 0 or not cutoff_m > 0 or r0_m < 0:
        raise GeometryUnavailable("离底高度、截断与近场必须为合法正数")
    beta = _beta_deg(beam_value_deg, beam_kind)
    alpha = math.radians(tilt_deg)
    if not 0 < alpha <= 90:
        raise GeometryUnavailable("倾角需在 (0,90]°")
    if alpha <= math.radians(beta):
        raise GeometryUnavailable("中心轴倾角不大于半角：需一般射线—水层求交，本条件算例不适用")
    sa, ca = math.sin(alpha), math.cos(alpha)
    sb, cb = math.sin(math.radians(beta)), math.cos(math.radians(beta))
    A = sa * sa - sb * sb
    center_bottom = height_m / sa
    axis_vertical_at_R = cutoff_m * sa
    steep = (height_m / math.sin(alpha + math.radians(beta))
             if alpha + math.radians(beta) < math.pi else None)
    shallow = (height_m / math.sin(alpha - math.radians(beta))
               if alpha > math.radians(beta) else None)
    xc = height_m * sa * ca / A
    a = height_m * sb * cb / A
    b = height_m * sb / math.sqrt(A)
    untruncated_area = math.pi * a * b
    footprint_area, centroid = _footprint_area(cutoff_m, height_m, xc, a, b, 2048)
    volume, max_forward = _integrate_volume(cutoff_m, height_m, alpha,
                                            math.radians(beta), r0_m, t_steps, phi_steps)
    half_volume, _ = _integrate_volume(cutoff_m, height_m, alpha,
                                       math.radians(beta), r0_m,
                                       max(100, t_steps // 2), max(200, phi_steps // 2))
    rel_error = abs(volume - half_volume) / volume if volume else 0.0
    if rel_error > 0.005:
        raise GeometryUnavailable(f"网格未收敛（体积相对差 {rel_error:.4f}>0.005）")
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "assumptions": [HORIZONTAL_BOTTOM, "均匀圆锥声束", "直线传播", "仅声程斜距轴"],
        "inputs": {"height_m": height_m, "tilt_deg": tilt_deg,
                   "beam_value_deg": beam_value_deg, "beam_kind": beam_kind,
                   "internal_half_angle_deg": beta, "cutoff_m": cutoff_m,
                   "near_field_m": r0_m, "beam_type_confirmed": beam_type_confirmed},
        "center_axis_bottom_m": center_bottom,
        "axis_vertical_distance_at_R_m": axis_vertical_at_R,
        "steeper_edge_bottom_m": steep,
        "flatter_edge_bottom_m": shallow,
        "bottom_hit_status": ("PARTIAL_BOTTOM_HIT" if steep is not None and shallow is not None
                              and steep < cutoff_m < shallow else "CHECK_POSTURE"),
        "uncut_ellipse": {"center_x_m": xc, "semi_major_m": a, "semi_minor_m": b,
                          "area_m2": untruncated_area},
        "cutoff_disk_radius_m": math.sqrt(max(cutoff_m ** 2 - height_m ** 2, 0.0)),
        "retained_footprint": {"area_m2": footprint_area,
                               "centroid_x_m": centroid[0], "centroid_y_m": centroid[1],
                               "note": "椭圆∩R 圆盘，非椭圆；未截断面积不得当最终足迹"},
        "water_volume_m3": volume,
        "water_projection_max_forward_m": max_forward,
        "numeric": {"t_steps": t_steps, "phi_steps": phi_steps,
                    "volume_relative_change": rel_error, "converged": True,
                    "display_precision_m": 0.01},
        "uncertainty": "几何参考值，非声学实测；波束全/半角类型与底面平坦度未实测时只作条件预览",
        "cutoff_locked_m": cutoff_m,
        "theory_does_not_override_cutoff": True,
    }
