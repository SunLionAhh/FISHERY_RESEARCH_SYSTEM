# -*- coding: utf-8 -*-
"""S05 环境数据手动导入：字段识别/映射、时间时区、单位、预览、重复与质量检查、来源与批次归档。"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel

from . import comparison
from .csv_parser import detect_encoding, detect_delimiter
from ..config import PROJECT_ROOT
from ..identity import current_operator

VARIABLES = ("WATER_TEMP", "TIDE_HEIGHT", "WIND_SPEED", "WIND_DIRECTION")
CANONICAL_UNITS = {
    "WATER_TEMP": "CELSIUS", "TIDE_HEIGHT": "M", "WIND_SPEED": "M/S",
    "WIND_DIRECTION": "DEGREE",
}
UNIT_FACTORS = {
    "WIND_SPEED": {"M/S": 1.0, "MPS": 1.0, "KM/H": 1 / 3.6,
                   "KMH": 1 / 3.6, "MPH": 0.44704, "KNOT": 0.514444, "KT": 0.514444},
    "WATER_TEMP": {"CELSIUS": 1.0, "C": 1.0, "°C": 1.0, "DEGC": 1.0},
    "TIDE_HEIGHT": {"M": 1.0, "CM": 0.01, "MM": 0.001},
    "WIND_DIRECTION": {"DEGREE": 1.0, "DEG": 1.0, "°": 1.0},
}
_FORECAST_WORDS = ("未来预报", "forecast", "predicted", "预报")
_HISTORICAL_WORDS = ("历史存档", "historical", "reanalysis", "历史")

_TIME_KEYS = ("时间", "时刻", "日期时间", "观测时间", "datetime", "timestamp", "observed_at", "time", "hour")
_DATE_KEYS = ("日期", "date", "day")
_VALUE_KEYS = ("风速", "潮位", "潮高", "水位", "水温", "温度", "value", "风速（", "wind", "temp", "tide")
_UNIT_KEYS = ("单位", "unit")
_STATION_KEYS = ("站位", "站点", "设备", "测站", "station", "device")
_QUALITY_KEYS = ("时段", "质量", "状态", "quality", "flag", "forecast")


class ImportValidationError(ValueError):
    pass


@dataclass
class Mapping:
    variable: str
    timezone: str
    datetime_column: str | None = None
    date_column: str | None = None
    time_column: str | None = None
    value_column: str | None = None
    unit_column: str | None = None
    unit_literal: str | None = None
    station_column: str | None = None
    quality_column: str | None = None
    header_row: int | None = None
    sheet: str | None = None
    location_key: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RowResult:
    observed_at: str
    observed_at_utc: str
    variable: str
    location_key: str
    value: float
    unit: str
    value_si: float
    quality_flag: str
    raw_row: dict
    issue: str | None = None


@dataclass
class Preview:
    path: str
    file_kind: str
    sheet: str | None
    header_row: int | None
    headers: list[str]
    metadata: list[str]
    mapping: dict
    samples: list[dict]
    accepted: list[RowResult] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    row_count: int = 0

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)

    def as_dict(self, *, include_rows: bool = False) -> dict:
        out = {
            "path": self.path, "file_kind": self.file_kind, "sheet": self.sheet,
            "header_row": self.header_row, "headers": self.headers,
            "metadata": self.metadata, "mapping": self.mapping, "samples": self.samples,
            "row_count": self.row_count, "accepted_count": len(self.accepted),
            "rejected_count": len(self.rejected), "issue_summary": self.issues,
        }
        if include_rows:
            out["accepted"] = [asdict(r) for r in self.accepted]
            out["rejected"] = self.rejected
        return out


def _norm(value) -> str:
    return re.sub(r"[\s_\-（）()：:]", "", str(value or "")).lower()


def _has(text: str, keys) -> bool:
    return any(_norm(k) in text for k in keys)


def read_table(path: Path, sheet: str | None = None, header_row: int | None = None):
    """返回 (headers, rows, metadata, sheet, header_row, file_kind)；只读，不修改源文件。"""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        wb = load_workbook(path, read_only=True, data_only=True)
        sheet = sheet or wb.sheetnames[0]
        ws = wb[sheet]
        raw = [[c for c in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
        kind = "XLSX"
    elif suffix in (".csv", ".txt"):
        encoding, _, _ = detect_encoding(path.open("rb").read(1 << 20))
        first_line = path.open("r", encoding=encoding).readline()
        delimiter = detect_delimiter(first_line)
        with path.open("r", encoding=encoding, newline="") as f:
            raw = [row for row in csv.reader(f, delimiter=delimiter)]
        kind = "CSV"
    else:
        raise ImportValidationError(f"不支持的文件类型：{path.suffix}（仅 CSV/XLSX）")

    if header_row is None:
        header_row = _detect_header(raw)
    if header_row is None or header_row >= len(raw):
        raise ImportValidationError("未能识别字段表头；请显式指定 header_row")
    headers = [str(h).strip() if h is not None else "" for h in raw[header_row]]
    metadata = [str(" | ".join(str(c) for c in row if c is not None))
                for row in raw[:header_row] if any(c is not None for c in row)]
    rows = []
    for index, values in enumerate(raw[header_row + 1:], start=header_row + 2):
        if not any(v is not None and str(v).strip() for v in values):
            continue
        row = {headers[i] if i < len(headers) and headers[i] else f"col_{i}": values[i]
               for i in range(len(values))}
        row["__row__"] = index
        rows.append(row)
    return headers, rows, metadata, sheet, header_row, kind


def _detect_header(raw: list[list]) -> int | None:
    for index, row in enumerate(raw[:30]):
        cells = [_norm(c) for c in row if c is not None and str(c).strip()]
        if len(cells) < 2:
            continue
        if any(_has(c, _VALUE_KEYS) for c in cells) and any(
                _has(c, _TIME_KEYS + _DATE_KEYS) for c in cells):
            return index
    return None


def suggest_mapping(headers: list[str], *, variable: str = "WIND_SPEED",
                    timezone: str = "Asia/Shanghai", metadata: list[str] | None = None) -> Mapping:
    mapping = Mapping(variable=variable, timezone=timezone)
    for name in headers:
        key = _norm(name)
        if not key:
            continue
        if mapping.datetime_column is None and _has(key, ("datetime", "日期时间", "timestamp")):
            mapping.datetime_column = name
        elif mapping.date_column is None and _has(key, _DATE_KEYS):
            mapping.date_column = name
        elif mapping.time_column is None and _has(key, _TIME_KEYS):
            mapping.time_column = name
        elif mapping.value_column is None and _has(key, _VALUE_KEYS):
            mapping.value_column = name
        elif mapping.unit_column is None and _has(key, _UNIT_KEYS):
            mapping.unit_column = name
        elif mapping.station_column is None and _has(key, _STATION_KEYS):
            mapping.station_column = name
        elif mapping.quality_column is None and _has(key, _QUALITY_KEYS):
            mapping.quality_column = name
    text = " ".join(metadata or [])
    for var, words in (("WIND_SPEED", ("风速", "windspeed", "wind speed")),
                       ("WIND_DIRECTION", ("风向", "winddirection")),
                       ("TIDE_HEIGHT", ("潮位", "潮高", "tide", "水位")),
                       ("WATER_TEMP", ("水温", "watertemp", "temperature"))):
        if any(w in text.lower() or any(w in _norm(h) for h in headers) for w in words):
            mapping.variable = var
            break
    if "米/秒" in text or "m/s" in text.lower():
        mapping.unit_literal = "M/S"
    elif "米" in text and "潮" in text:
        mapping.unit_literal = "M"
    if any(w in text for w in _FORECAST_WORDS):
        mapping.location_key = mapping.location_key or "SOURCE_GRID"
    if mapping.value_column is None:
        raise ImportValidationError("未能识别数值列；请在字段映射中指定 value_column")
    return mapping


def parse_time(value, *, date_value=None) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, time(0, 0))
    if isinstance(value, (int, float)) and 20000 < float(value) < 80000:
        return from_excel(float(value)).replace(tzinfo=None)
    text = str(value or "").strip()
    if not text and date_value is not None:
        return parse_time(date_value).replace(tzinfo=None)
    if isinstance(value, time):
        base = parse_time(date_value).date() if date_value else date(1900, 1, 1)
        return datetime.combine(base, value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S",
                "%Y/%m/%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H时%M分", "%Y年%m月%d日 %H时%M分", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:?\d{2}", text):
        return datetime.fromisoformat(text).replace(tzinfo=None)
    raise ImportValidationError(f"无法解析时间：{value!r}")


def combine_time(row: dict, mapping: Mapping) -> datetime:
    if mapping.datetime_column and row.get(mapping.datetime_column) not in (None, ""):
        return parse_time(row[mapping.datetime_column])
    date_value = row.get(mapping.date_column) if mapping.date_column else None
    time_value = row.get(mapping.time_column) if mapping.time_column else None
    if isinstance(time_value, time):
        return parse_time(time_value, date_value=date_value)
    base = parse_time(date_value) if date_value not in (None, "") else None
    if base is None:
        raise ImportValidationError("缺少时间列")
    if time_value in (None, ""):
        return base
    text = str(time_value).strip()
    if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", text):
        parts = [int(p) for p in text.split(":")]
        return base.replace(hour=parts[0], minute=parts[1], second=parts[2] if len(parts) > 2 else 0)
    return parse_time(text, date_value=date_value)


def normalise_unit(text) -> str:
    value = str(text or "").strip().upper().replace(" ", "")
    aliases = {"米/秒": "M/S", "M/S": "M/S", "MPS": "M/S", "KM/H": "KM/H", "KMH": "KM/H",
               "℃": "CELSIUS", "°C": "CELSIUS", "C": "CELSIUS", "摄氏度": "CELSIUS",
               "CM": "CM", "MM": "MM", "M": "M", "度": "DEGREE", "DEG": "DEGREE"}
    return aliases.get(value, value)


def convert(value: float, unit: str, variable: str) -> float:
    if variable not in VARIABLES:
        raise ImportValidationError(f"未知环境变量：{variable}")
    factor = UNIT_FACTORS[variable].get(normalise_unit(unit))
    if factor is None:
        raise ImportValidationError(f"变量 {variable} 不支持单位 {unit!r}")
    return value * factor


def _location(row: dict, mapping: Mapping) -> str:
    if mapping.location_key:
        return str(mapping.location_key)
    if mapping.station_column and row.get(mapping.station_column) not in (None, ""):
        return str(row[mapping.station_column]).strip()
    return "DEFAULT"


def _quality(row: dict, mapping: Mapping, metadata: list[str]) -> str:
    flag = str(row.get(mapping.quality_column) or "") if mapping.quality_column else ""
    meta = " ".join(metadata)
    normalized = flag.strip().upper()
    if normalized in ("DERIVED", "SUSPECT", "FORECAST", "MODEL_HISTORICAL", "OK"):
        return normalized
    if any(w in flag for w in _FORECAST_WORDS):
        return "FORECAST"
    if any(w in flag for w in _HISTORICAL_WORDS):
        return "MODEL_HISTORICAL" if "模型" in meta or "model" in meta.lower() else "OK"
    return "MODEL_HISTORICAL" if "模型" in meta or "model" in meta.lower() else "OK"


def parse_rows(rows: list[dict], mapping: Mapping, metadata: list[str]) -> tuple[list[RowResult], list[dict], list[str]]:
    accepted: list[RowResult] = []
    rejected: list[dict] = []
    issues: list[str] = []
    offset = comparison.utc_offset_hours(mapping.timezone)
    seen: dict[tuple, RowResult] = {}
    duplicates = 0
    for row in rows:
        raw = {k: v for k, v in row.items() if k != "__row__"}
        try:
            local = combine_time(row, mapping)
            observed_at = local.isoformat(timespec="seconds")
            observed_at_utc = (local - timedelta(hours=offset)).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
            raw_value = row.get(mapping.value_column)
            if raw_value in (None, ""):
                raise ImportValidationError("MISSING_VALUE：数值为空")
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise ImportValidationError(f"INVALID_VALUE：{exc}") from exc
            if not math.isfinite(value):
                raise ImportValidationError("INVALID_VALUE：非有限数")
            unit = normalise_unit(row.get(mapping.unit_column) if mapping.unit_column else mapping.unit_literal)
            if not unit:
                raise ImportValidationError("MISSING_UNIT：未声明单位")
            value_si = convert(value, unit, mapping.variable)
            if mapping.variable == "WIND_SPEED" and value_si < 0:
                raise ImportValidationError("ANOMALY_VALUE：风速为负")
            if mapping.variable == "WIND_DIRECTION" and not 0 <= value_si <= 360:
                raise ImportValidationError("ANOMALY_VALUE：风向不在 0—360°")
            quality = _quality(row, mapping, metadata)
            if mapping.variable == "WATER_TEMP" and not -5 <= value_si <= 45:
                quality = "SUSPECT"
            key = (mapping.variable, _location(row, mapping), observed_at_utc)
            result = RowResult(observed_at, observed_at_utc, mapping.variable, key[1],
                               value, unit, value_si, quality, raw)
            if key in seen:
                duplicates += 1
                issues.append(f"第 {row.get('__row__')} 行重复：{key}（保留首条）")
                continue
            seen[key] = result
            accepted.append(result)
        except (ImportValidationError, ValueError, TypeError) as exc:
            rejected.append({"row": row.get("__row__"), "reason": str(exc), "raw": raw})
    if duplicates:
        issues.insert(0, f"文件内重复 {duplicates} 条，已跳过")
    return accepted, rejected, issues


def preview_file(path: Path, mapping: Mapping) -> Preview:
    headers, rows, metadata, sheet, header_row, kind = read_table(
        path, sheet=mapping.sheet, header_row=mapping.header_row)
    accepted, rejected, issues = parse_rows(rows, mapping, metadata)
    return Preview(str(path), kind, sheet, header_row, headers, metadata, mapping.as_dict(),
                   [{k: v for k, v in row.items() if k != "__row__"} for row in rows[:8]],
                   accepted, rejected, issues, len(rows))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def register_source(conn, source_id: str, *, name: str, kind: str, provider: str,
                    dataset: str = "", source_url: str = "", spatial_coverage: str = "",
                    time_resolution: str = "", units_json: dict | None = None,
                    observed_or_forecast: str = "UNKNOWN", license: str = "",
                    authorization: str = "", api_limits: str = "", quality_note: str = "") -> dict:
    payload = {
        "source_id": source_id, "name": name, "kind": kind, "provider": provider,
        "dataset": dataset, "source_url": source_url, "spatial_coverage": spatial_coverage,
        "time_resolution": time_resolution, "units_json": json.dumps(units_json or {}, ensure_ascii=False),
        "observed_or_forecast": observed_or_forecast, "license": license,
        "authorization": authorization, "api_limits": api_limits, "quality_note": quality_note,
        "created_at": datetime.now(dt_timezone.utc).isoformat(timespec="seconds"),
        "actor": current_operator(),
    }
    conn.execute(
        "INSERT OR REPLACE INTO environment_source (source_id,name,kind,provider,dataset,source_url,"
        "spatial_coverage,time_resolution,units_json,observed_or_forecast,license,authorization,"
        "api_limits,quality_note,created_at,actor) VALUES (" + ",".join("?" for _ in payload) + ")",
        tuple(payload.values()))
    conn.commit()
    return payload


def commit_import(conn, path: Path, mapping: Mapping, source_id: str, *,
                  project_root: Path = PROJECT_ROOT) -> dict:
    """单事务导入；已存在同一 (source,variable,location,utc) 的记录不覆盖，冲突单独记账。"""
    conn.execute("BEGIN IMMEDIATE")
    try:
        preview = preview_file(path, mapping)
        if not preview.accepted:
            raise ImportValidationError("无任何可导入记录")
        source = conn.execute("SELECT source_id FROM environment_source WHERE source_id=?",
                              (source_id,)).fetchone()
        if source is None:
            raise ImportValidationError(f"来源未登记：{source_id}")
        batch_id = "ENV-" + uuid.uuid4().hex[:12].upper()
        archive = (project_root / "02_IMPORTED_DATA" / "ENVIRONMENT_ARCHIVE" / batch_id
                   / path.name)
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, archive)
        created_at = datetime.now(dt_timezone.utc).isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO environment_import_batch (batch_id,source_id,file_name,file_sha256,"
            "file_size_bytes,file_kind,sheet_name,field_mapping_json,timezone,row_count,"
            "accepted_count,rejected_count,duplicate_count,issue_summary_json,status,archive_path,"
            "created_at,actor) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (batch_id, source_id, path.name, _sha(path), path.stat().st_size, preview.file_kind,
             preview.sheet, json.dumps(mapping.as_dict(), ensure_ascii=False), mapping.timezone,
             preview.row_count, 0, 0, 0, "[]", "IMPORTED", str(archive), created_at,
             current_operator()))
        inserted = duplicates = conflicts = 0
        for row in preview.accepted:
            existing = conn.execute(
                "SELECT value_si FROM environment_observation WHERE source_id=? AND variable=? "
                "AND location_key=? AND observed_at_utc=?",
                (source_id, row.variable, row.location_key, row.observed_at_utc)).fetchone()
            if existing is not None:
                if not math.isclose(existing["value_si"], row.value_si, rel_tol=1e-9, abs_tol=1e-9):
                    conflicts += 1
                    preview.issues.append(f"来源冲突：{row.observed_at_utc} 同键不同值，保留原值")
                else:
                    duplicates += 1
                continue
            conn.execute(
                "INSERT INTO environment_observation (batch_id,source_id,variable,location_key,"
                "station_id,device_id,observed_at,observed_at_utc,timezone,value,unit,value_si,"
                "quality_flag,raw_row_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (batch_id, source_id, row.variable, row.location_key,
                 mapping.station_column and row.raw_row.get(mapping.station_column),
                 row.raw_row.get("device_id"), row.observed_at, row.observed_at_utc, mapping.timezone,
                 row.value, row.unit, row.value_si, row.quality_flag,
                 json.dumps(row.raw_row, ensure_ascii=False, default=str)))
            inserted += 1
        issues = preview.issues + [f"新增重复 {duplicates} 条；来源冲突 {conflicts} 条（未覆盖原值）"]
        status = "IMPORTED" if not preview.rejected and not conflicts else "PARTIAL"
        conn.execute(
            "UPDATE environment_import_batch SET accepted_count=?, rejected_count=?, "
            "duplicate_count=?, issue_summary_json=?, status=? WHERE batch_id=?",
            (inserted, len(preview.rejected), duplicates + conflicts,
             json.dumps(issues, ensure_ascii=False), status, batch_id))
        conn.commit()
        return {"batch_id": batch_id, "source_id": source_id, "status": status,
                "inserted": inserted, "duplicates": duplicates, "conflicts": conflicts,
                "rejected": len(preview.rejected), "issues": issues, "archive": str(archive)}
    except Exception:
        conn.rollback()
        raise


def log_fetch(conn, adapter: str, status: str, parameter: dict, *,
              records: int = 0, error: str = "") -> dict:
    fetch_id = "FETCH-" + uuid.uuid4().hex[:10].upper()
    now = datetime.now(dt_timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO environment_fetch_log (fetch_id,adapter,status,requested_at,finished_at,"
        "parameter_json,records_written,error_message,actor) VALUES (?,?,?,?,?,?,?,?,?)",
        (fetch_id, adapter, status, now, now, json.dumps(parameter, ensure_ascii=False),
         records, error, current_operator()))
    conn.commit()
    return {"fetch_id": fetch_id, "adapter": adapter, "status": status, "error": error}
