# -*- coding: utf-8 -*-
"""S03 测试用合成 CSV（不属于正式数据，仅验证统计逻辑）。"""
from __future__ import annotations

from pathlib import Path

POINTS = 1000


def signal_values(*, event: bool = True, low: float = 10.0, high: float = 255.0) -> list[int]:
    """前 17 格为发射余脉（非零），第 17 格首零 → 行内盲区结束；第 18—22 格为候选事件。"""
    values = [int(high)] * 17 + [0] + [int(low)] * 100
    if event:
        for i in range(18, 23):
            values[i] = 210
    values.extend([0] * (POINTS - len(values)))
    return values[:POINTS]


def write_custom_csv(path: Path, device_id: str, observed_date: str,
                     signals: list[list[int]], *, hours: tuple[int, ...] = (0, 1, 3)) -> Path:
    """用逐行自定义信号写合成 CSV（用于越界幅度不变性测试）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["序号,日期,水深(m),水温(°C),量程(m),数据(信号强度)\n"]
    for seq, (hour, signal) in enumerate(zip(hours, signals), start=1):
        stamp = (f"{observed_date} {hour:02d}:00:00" if device_id != "2001"
                 else f"{observed_date} {hour}:00")
        lines.append(f"{seq},{stamp},1.5,22.0,37.5,{':'.join(str(v) for v in signal)}:\n")
    path.write_text("".join(lines), encoding="utf-8-sig")
    return path


def write_fishfinder_csv(path: Path, device_id: str, observed_date: str, *,
                         hours: tuple[int, ...] = (0, 1, 3),
                         event: bool = True,
                         water_temp: str = "22.0",
                         trailing_token: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "序号,日期,水深(m),水温(°C),量程(m),数据(信号强度)\n"
    lines = [header]
    for seq, hour in enumerate(hours, start=1):
        stamp = (f"{observed_date} {hour:02d}:00:00" if device_id != "2001"
                 else f"{observed_date} {hour}:00")
        signal = ":".join(str(v) for v in signal_values(event=event))
        if trailing_token:
            signal += ":"
        lines.append(f"{seq},{stamp},1.5,{water_temp},37.5,{signal}\n")
    path.write_text("".join(lines), encoding="utf-8-sig")
    return path
