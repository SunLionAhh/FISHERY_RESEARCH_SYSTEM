# -*- coding: utf-8 -*-
"""V4.1 B1：长期范围的确定性阶段分组。

默认分组只改变显示，不改逐日指标、规律规则或发现/验证划分。
N 为筛选首末日的日历跨度（含首尾），不是有效观测天数。
"""
from __future__ import annotations

import calendar
import math
from datetime import date, timedelta
from typing import Iterable

MAX_DEFAULT_GROUPS = 9
LARGE_SPAN_CANDIDATES = (14, 30, 60, 90, 180, 365)


def _day(value: str) -> date:
    return date.fromisoformat(value)


def span_days(start_date: str, end_date: str) -> int:
    return (_day(end_date) - _day(start_date)).days + 1


def inclusive_dates(start_date: str, end_date: str) -> list[str]:
    total = span_days(start_date, end_date)
    if total <= 0:
        return []
    first = _day(start_date)
    return [(first + timedelta(days=index)).isoformat() for index in range(total)]


def choose_step_days(n_days: int) -> int:
    if n_days <= 0:
        return 1
    if n_days <= 7:
        return 1
    if n_days <= 31:
        return 7
    if n_days <= 90:
        return 10
    for step in LARGE_SPAN_CANDIDATES:
        if math.ceil(n_days / step) <= MAX_DEFAULT_GROUPS:
            return step
    return 365 * math.ceil(n_days / (MAX_DEFAULT_GROUPS * 365))


def _selected_in(start_date: date, end_date: date,
                 selected_dates: Iterable[str]) -> tuple[list[str], list[str]]:
    window = [(start_date + timedelta(days=index)).isoformat()
              for index in range((end_date - start_date).days + 1)]
    chosen = set(selected_dates)
    return [day for day in window if day in chosen], [day for day in window if day not in chosen]


def _group(start_index: int, end_index: int, first: date,
           selected_dates: Iterable[str]) -> dict:
    start = first + timedelta(days=start_index - 1)
    end = first + timedelta(days=end_index - 1)
    chosen, unselected = _selected_in(start, end, selected_dates)
    return {
        "index": 0,
        "offset_start": start_index,
        "offset_end": end_index,
        "date_start": start.isoformat(),
        "date_end": end.isoformat(),
        "label": (start.isoformat() if start == end
                  else f"{start.isoformat()}—{end.isoformat()}"),
        "planned_days": (end - start).days + 1,
        "selected_days": len(chosen),
        "dates": chosen,
        "unselected_dates": unselected,
        "complete_default_span": len(chosen) == (end - start).days + 1,
    }


def default_groups(start_date: str, end_date: str,
                   selected_dates: Iterable[str] | None = None) -> dict:
    n_days = span_days(start_date, end_date)
    step = choose_step_days(n_days)
    first = _day(start_date)
    chosen = list(selected_dates or inclusive_dates(start_date, end_date))
    groups = []
    for offset in range(1, n_days + 1, step):
        last = min(offset + step - 1, n_days)
        groups.append(_group(offset, last, first, chosen))
    for index, group in enumerate(groups, 1):
        group["index"] = index
    return {
        "grouping_mode": "default", "span_days": n_days, "step_days": step,
        "n_groups": len(groups), "within_default_limit": len(groups) <= MAX_DEFAULT_GROUPS,
        "groups": groups,
        "note": ("从筛选起点起算的固定天数阶段；不是自然周或自然月。"
                 "未选择日期与缺测分开标记，分组只改变显示。"),
    }


def natural_week_groups(start_date: str, end_date: str,
                        selected_dates: Iterable[str] | None = None) -> dict:
    first, last = _day(start_date), _day(end_date)
    chosen = list(selected_dates or inclusive_dates(start_date, end_date))
    monday = first - timedelta(days=first.weekday())
    groups = []
    cursor = monday
    while cursor <= last:
        week_end = cursor + timedelta(days=6)
        start_index = max(1, (cursor - first).days + 1)
        end_index = min(span_days(start_date, end_date), (week_end - first).days + 1)
        if end_index >= start_index:
            groups.append(_group(start_index, end_index, first, chosen))
        cursor = week_end + timedelta(days=1)
    for index, group in enumerate(groups, 1):
        group["index"] = index
    return {
        "grouping_mode": "natural_week", "span_days": span_days(start_date, end_date),
        "step_days": 7, "calendar_anchor": "MONDAY", "n_groups": len(groups),
        "within_default_limit": len(groups) <= MAX_DEFAULT_GROUPS, "groups": groups,
        "note": "自然周以周一至周日锚定；首尾不完整周标注实际日期与选中天数。",
    }


def natural_month_groups(start_date: str, end_date: str,
                         selected_dates: Iterable[str] | None = None) -> dict:
    first, last = _day(start_date), _day(end_date)
    chosen = list(selected_dates or inclusive_dates(start_date, end_date))
    n_days = span_days(start_date, end_date)
    groups = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        start_index = max(1, (month_start - first).days + 1)
        end_index = min(n_days, (month_end - first).days + 1)
        if end_index >= start_index:
            groups.append(_group(start_index, end_index, first, chosen))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    for index, group in enumerate(groups, 1):
        group["index"] = index
    return {
        "grouping_mode": "natural_month", "span_days": n_days,
        "step_days": None, "n_groups": len(groups),
        "within_default_limit": len(groups) <= MAX_DEFAULT_GROUPS, "groups": groups,
        "note": "自然月按实际日历月份；跨月长度不强行统一。",
    }


def custom_groups(start_date: str, end_date: str, step_days: int,
                  selected_dates: Iterable[str] | None = None,
                  *, page: int = 1, page_size: int = 9) -> dict:
    if step_days < 1:
        raise ValueError("自定义组长必须为正整数")
    n_days = span_days(start_date, end_date)
    first = _day(start_date)
    chosen = list(selected_dates or inclusive_dates(start_date, end_date))
    groups = []
    for offset in range(1, n_days + 1, step_days):
        last = min(offset + step_days - 1, n_days)
        groups.append(_group(offset, last, first, chosen))
    for index, group in enumerate(groups, 1):
        group["index"] = index
    total_pages = max(1, math.ceil(len(groups) / page_size))
    page = min(max(1, page), total_pages)
    visible = groups[(page - 1) * page_size: page * page_size]
    return {
        "grouping_mode": "custom", "span_days": n_days, "step_days": step_days,
        "n_groups": len(groups), "within_default_limit": len(groups) <= MAX_DEFAULT_GROUPS,
        "page": page, "page_size": page_size, "total_pages": total_pages,
        "groups": groups, "visible_groups": visible,
        "note": "用户自定义分组超过 9 组时分页浏览，不删组、不静默扩大组长。",
    }


def build_groups(start_date: str, end_date: str, grouping_mode: str = "default",
                 selected_dates: Iterable[str] | None = None,
                 *, custom_step_days: int = 7, page: int = 1, page_size: int = 9) -> dict:
    if grouping_mode == "default":
        return default_groups(start_date, end_date, selected_dates)
    if grouping_mode == "natural_week":
        return natural_week_groups(start_date, end_date, selected_dates)
    if grouping_mode == "natural_month":
        return natural_month_groups(start_date, end_date, selected_dates)
    if grouping_mode == "custom":
        return custom_groups(start_date, end_date, custom_step_days, selected_dates,
                             page=page, page_size=page_size)
    raise ValueError("不支持的分组模式：" + str(grouping_mode))
