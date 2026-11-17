# -*- coding: utf-8 -*-
"""真实探鱼 CSV 的逐文件探测与流式解析（S02 任务一/二/三/四/五）。

- 只读原始文件：打开方式为 'rb' 取样、'r' 流式读取，全程不写、不改、不重排。
- 不一次性载入 ~400MB 文件：`iter_rows()` 逐行产出，调用方可随时停止。
- 逐文件探测编码（BOM / UTF-8 严格解码 / GB18030 回退）、分隔符、换行、表头；
  两份真实文件编码不同（2000=UTF-8-SIG+LF，2001=GB18030+CRLF），不得全库假定同一编码。
- 保留原始行号、序号、时间戳原文与信号数组原文；不按时间戳去重。
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator, Sequence

SAMPLE_BYTES = 1 << 20  # 1 MiB 取样用于编码/分隔符探测

TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
)


def sha256_file(path: Path, chunk_size: int = 4 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_encoding(sample: bytes) -> tuple[str, bool, str]:
    """返回 (encoding, has_bom, evidence)。禁止沉默假定 UTF-8。"""
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", True, "文件头存在 UTF-8 BOM (EF BB BF)"
    try:
        sample.decode("utf-8")
        return "utf-8", False, "无 BOM；前 1 MiB 严格 UTF-8 解码通过"
    except UnicodeDecodeError as exc:
        try:
            sample.decode("gb18030")
        except UnicodeDecodeError:
            raise UnicodeError(f"无法识别编码（UTF-8 失败：{exc}；GB18030 亦失败）") from exc
        return "gb18030", False, f"无 BOM；UTF-8 解码失败（{exc.reason}），GB18030 解码通过"


def detect_delimiter(header_line: str) -> str:
    candidates = {",": header_line.count(","), "\t": header_line.count("\t"),
                  ";": header_line.count(";")}
    best = max(candidates, key=candidates.get)
    if candidates[best] == 0:
        raise ValueError(f"无法识别分隔符：{header_line[:200]!r}")
    return best


def detect_line_ending(sample: bytes) -> str:
    if b"\r\n" in sample:
        return "CRLF"
    if b"\n" in sample:
        return "LF"
    return "UNKNOWN"


@dataclass(frozen=True)
class FileInspection:
    path: Path
    size_bytes: int
    sha256: str
    encoding: str
    has_bom: bool
    encoding_evidence: str
    delimiter: str
    line_ending: str
    header: tuple[str, ...]
    header_map: dict[str, str]        # 规范字段 → 原始表头
    unknown_headers: tuple[str, ...]

    @property
    def field_count(self) -> int:
        return len(self.header)


CANONICAL_ORDER = ("seq", "timestamp", "depth_m", "water_temp_c", "range_m", "signal_raw")


def _canonical_field(raw: str, index: int) -> str:
    name = raw.strip().replace("（", "(").replace("）", ")")
    if name.startswith("序号"):
        return "seq"
    if name.startswith("日期") or name.lower() in ("time", "datetime"):
        return "timestamp"
    if name.startswith("水深") or name.lower().startswith("depth"):
        return "depth_m"
    if name.startswith("水温") or name.lower().startswith("temp"):
        return "water_temp_c"
    if name.startswith("量程") or name.lower().startswith("range"):
        return "range_m"
    if name.startswith("数据") or "信号" in name or name.lower().startswith("signal"):
        return "signal_raw"
    return f"col_{index}"


def inspect_file(path: Path, *, compute_hash: bool = True) -> FileInspection:
    if not path.exists():
        raise FileNotFoundError(f"原始文件不存在：{path}")
    size = path.stat().st_size
    with path.open("rb") as f:
        sample = f.read(SAMPLE_BYTES)
    if not sample:
        raise ValueError(f"文件为空：{path}")
    encoding, has_bom, evidence = detect_encoding(sample)
    first_line = sample.split(b"\n", 1)[0].rstrip(b"\r")
    text_line = first_line.decode(encoding)
    delimiter = detect_delimiter(text_line)
    header = tuple(next(csv.reader([text_line], delimiter=delimiter)))
    header_map: dict[str, str] = {}
    unknown: list[str] = []
    for i, raw in enumerate(header):
        canonical = _canonical_field(raw, i)
        if canonical.startswith("col_"):
            unknown.append(raw)
        else:
            header_map[canonical] = raw
    return FileInspection(
        path=path, size_bytes=size,
        sha256=sha256_file(path) if compute_hash else "",
        encoding=encoding, has_bom=has_bom, encoding_evidence=evidence,
        delimiter=delimiter, line_ending=detect_line_ending(sample),
        header=header, header_map=header_map, unknown_headers=tuple(unknown),
    )


def parse_timestamp(raw: str) -> tuple[datetime | None, str, str | None]:
    """支持 2026-10-31 00:00:00 与 2026/10/31 0:00（小时不补零）等格式。"""
    text = (raw or "").strip()
    if not text:
        return None, "", "空时间戳"
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt), fmt, None
        except ValueError:
            continue
    return None, "", f"无法解析时间戳 {text!r}"


def first_zero_index(values: Sequence[float | None]) -> int | None:
    """返回第一个 0 的 0 基索引；无 0 时返回 None。

    用户口径（2026-11-17）：信号数组以第一个出现的 0 开始才算数据盲区结束，
    设备盲区 0.5 m——即首零之前的部分属盲区，不作为有效数据。
    """
    for i, v in enumerate(values):
        if v == 0.0:
            return i
    return None


def parse_float(raw: str) -> tuple[float | None, str | None]:
    text = (raw or "").strip()
    if text == "":
        return None, "空值"
    try:
        value = float(text)
    except ValueError:
        return None, f"非数值 {text!r}"
    if value != value or value in (float("inf"), float("-inf")):
        return None, f"非有限数值 {text!r}"
    return value, None


def parse_signal(raw: str) -> tuple[list[float | None], int, int, int, list[str]]:
    """解析信号数组：冒号分隔；保留位置（无效项为 None），统计空项与非数值项。

    真实文件每行以冒号结尾，split 后多出 1 个尾部空 token（1001 个 token / 1000 个槽位）。
    `trailing_empty` 单独返回，供审计区分「token 数」与「有效槽位数」。
    """
    text = raw or ""
    tokens = text.split(":") if text != "" else []
    values: list[float | None] = []
    empty = 0
    non_numeric = 0
    errors: list[str] = []
    for token in tokens:
        t = token.strip()
        if t == "":
            empty += 1
            values.append(None)
            continue
        try:
            values.append(float(t))
        except ValueError:
            non_numeric += 1
            values.append(None)
            if len(errors) < 3:
                errors.append(f"信号非数值 {t!r}")
    trailing_empty = 0
    for token in reversed(tokens):
        if token.strip() == "":
            trailing_empty += 1
        else:
            break
    return values, empty, non_numeric, trailing_empty, errors


@dataclass
class ParsedRow:
    line_no: int
    seq_raw: str = ""
    seq: int | None = None
    timestamp_raw: str = ""
    timestamp: datetime | None = None
    timestamp_format: str = ""
    depth_m_raw: str = ""
    depth_m: float | None = None
    water_temp_c_raw: str = ""
    water_temp_c: float | None = None
    range_m_raw: str = ""
    range_m: float | None = None
    signal_raw: str = ""
    signal: list[float | None] = field(default_factory=list)
    signal_empty_tokens: int = 0
    signal_non_numeric: int = 0
    signal_trailing_empty: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def signal_len(self) -> int:
        """token 数（真实文件为 1001，含尾部空 token）。"""
        return len(self.signal)

    @property
    def effective_signal_len(self) -> int:
        """有效数值槽位数（剔除尾部空 token，真实文件为 1000）。"""
        return len(self.signal) - self.signal_trailing_empty


def iter_rows(inspection: FileInspection, *, limit: int | None = None,
              parse_signal_array: bool = True) -> Iterator[ParsedRow]:
    """流式逐行解析；limit 仅用于测试/抽样，正式审计应遍历全文件。"""
    with inspection.path.open("r", encoding=inspection.encoding, newline="") as f:
        reader = csv.reader(f, delimiter=inspection.delimiter)
        header = next(reader, None)
        if header is None:
            return
        if tuple(h.strip() for h in header) != tuple(h.strip() for h in inspection.header):
            raise ValueError(f"表头与探测结果不一致：{header!r} vs {inspection.header!r}")
        index = {name: inspection.header.index(raw) for name, raw in inspection.header_map.items()}

        def cell(row: list[str], key: str) -> str:
            i = index.get(key)
            if i is None or i >= len(row):
                return ""
            return row[i]

        for line_no, row in enumerate(reader, start=2):
            parsed = ParsedRow(line_no=line_no)
            if not row or all(c.strip() == "" for c in row):
                parsed.errors.append("空行")
                yield parsed
                continue
            if len(row) != len(inspection.header):
                parsed.errors.append(
                    f"列数不符：期望 {len(inspection.header)}，实际 {len(row)}")
            parsed.seq_raw = cell(row, "seq")
            if parsed.seq_raw.strip():
                try:
                    parsed.seq = int(parsed.seq_raw.strip())
                except ValueError:
                    parsed.errors.append(f"序号非整数 {parsed.seq_raw!r}")
            parsed.timestamp_raw = cell(row, "timestamp")
            parsed.timestamp, parsed.timestamp_format, ts_err = parse_timestamp(parsed.timestamp_raw)
            if ts_err:
                parsed.errors.append(ts_err)
            parsed.depth_m_raw = cell(row, "depth_m")
            parsed.depth_m, err = parse_float(parsed.depth_m_raw)
            if err:
                parsed.errors.append(f"水深{err}")
            parsed.water_temp_c_raw = cell(row, "water_temp_c")
            parsed.water_temp_c, err = parse_float(parsed.water_temp_c_raw)
            if err:
                parsed.errors.append(f"水温{err}")
            parsed.range_m_raw = cell(row, "range_m")
            parsed.range_m, err = parse_float(parsed.range_m_raw)
            if err:
                parsed.errors.append(f"量程{err}")
            parsed.signal_raw = cell(row, "signal_raw")
            if parse_signal_array:
                (parsed.signal, parsed.signal_empty_tokens, parsed.signal_non_numeric,
                 parsed.signal_trailing_empty, sig_errors) = parse_signal(parsed.signal_raw)
                parsed.errors.extend(sig_errors)
            yield parsed
            if limit is not None and line_no - 1 >= limit:
                return
