# -*- coding: utf-8 -*-
"""S02 硬掩码手算对照（K04/K05/K06 证据工件）。

用法：
    .venv\\Scripts\\python.exe 12_DOCUMENTATION\\verify_s02_mask.py

输出：控制台对照表 + 10_TEST_REPORTS/s02_verification/boundary_cases.csv
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "04_SOURCE_CODE"))

from app.services import distance_mapping as dm  # noqa: E402

OUT = ROOT / "10_TEST_REPORTS" / "s02_verification"
OUT.mkdir(parents=True, exist_ok=True)
rows = []


def record(case, sampling, index, distance, value, cutoff, kept, reason):
    rows.append([case, sampling, index, f"{distance:g}", f"{value:g}", f"{cutoff:g}",
                 "KEEP" if kept else "EXCLUDE", "" if kept else reason])
    print(f"{case:<26} {sampling:<9} idx={index} r={distance:<8g} v={value:<7g} "
          f"→ {'KEEP' if kept else 'EXCLUDE(' + reason + ')'}")


CUTOFF = 5.2

# K04：点样本边界，5.201 不得因显示精度被保留
for i, r in enumerate((5.199, 5.200, 5.201)):
    res = dm.mask_points([r], [10 + i], CUTOFF)
    kept = res.kept_count == 1
    record("K04 点边界", "POINT", i, r, 10 + i, CUTOFF, kept,
           "" if kept else res.excluded_reasons[0][1])

# K04：无浮点容差（5.2 + 1e-12 越界）
for i, r in enumerate((5.2, 5.2 + 1e-12)):
    res = dm.mask_points([r], [1], CUTOFF)
    kept = res.kept_count == 1
    record("K04 无容差", "POINT", i, r, 1, CUTOFF, kept,
           "" if kept else res.excluded_reasons[0][1])

# K05：区间采样跨界整段排除（中心在界内也不纳入）
starts = [4.6, 4.9, 5.0, 5.2]
res = dm.mask_intervals(starts, 0.5, [1, 2, 3, 4], CUTOFF)
reasons = dict(res.excluded_reasons)
for i, s in enumerate(starts):
    kept = i in res.kept_indices
    record("K05 区间跨界", "INTERVAL", i, s, i + 1, CUTOFF, kept,
           "" if kept else reasons.get(i, res.reason_summary()))

# K04：越界强回波改变幅度 → 区内结果不变（界外用非 0 值，避免触发行内盲区规则）
inside = [11.0, 22.0, 33.0]
base = dm.mask_points([5.0, 5.1, 5.2, 5.201, 6.0], inside + [1.0, 2.0], CUTOFF)
spike = dm.mask_points([5.0, 5.1, 5.2, 5.201, 6.0], inside + [65535.0, 1e9], CUTOFF)
print(f"\nK04 越界幅度不变性：kept={base.kept_values} sum={sum(base.kept_values)} "
      f"vs kept={spike.kept_values} sum={sum(spike.kept_values)} "
      f"→ {'PASS' if base.kept_values == spike.kept_values else 'FAIL'}")

# K06：映射未核实 → 正式分析 BLOCKED
unverified = dm.DistanceMapping(
    device_id="2000", range_m=37.5, point_count=1000,
    sample_mode=dm.SAMPLE_MODE_UNKNOWN, first_sample_distance_m=None,
    sample_interval_m=None, support_status=dm.SUPPORT_UNVERIFIED, version=1,
)
try:
    dm.build_mask([1, 2, 3], unverified, CUTOFF, row_range_m=37.5, row_point_count=3)
    blocked = "NOT BLOCKED (FAIL)"
except dm.DistanceMappingBlocked as exc:
    blocked = "BLOCKED: " + "；".join(exc.reasons)
print(f"K06 未知映射：{blocked}")

with (OUT / "boundary_cases.csv").open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["case", "sampling", "index", "distance_m", "value", "cutoff_m",
                "decision", "exclusion_reason"])
    w.writerows(rows)
    w.writerow(["K04 越界幅度不变性", "POINT", "", "", "", CUTOFF,
                "PASS" if base.kept_values == spike.kept_values else "FAIL", ""])
    w.writerow(["K06 未知映射", "UNKNOWN", "", "", "", CUTOFF, "BLOCKED", blocked])
(OUT / "boundary_cases_run.txt").write_text(
    f"generated_at={datetime.now().isoformat(timespec='seconds')}\n"
    f"cutoff={CUTOFF}\nrows={len(rows)}\nK06={blocked}\n",
    encoding="utf-8")
print(f"\n已写入 {OUT / 'boundary_cases.csv'}")
