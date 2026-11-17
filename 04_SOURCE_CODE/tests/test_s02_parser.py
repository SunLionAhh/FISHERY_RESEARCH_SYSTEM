# -*- coding: utf-8 -*-
"""S02 解析与审计：逐文件编码探测、流式行保留、哈希不变、8 份工件。"""
import csv
import hashlib
from pathlib import Path

import pytest

from app.services import audit_s02
from app.services import csv_parser as cp

ROOT = Path(__file__).resolve().parents[2]
DATA_2000 = ROOT / "01_ORIGINAL_DATA" / "FISHFINDER" / "2000" / "探鱼-2000_2026-10-31.csv"
DATA_2001 = ROOT / "01_ORIGINAL_DATA" / "FISHFINDER" / "2001" / "探鱼-2001_2026-10-31.csv"
MANIFEST = ROOT / "10_TEST_REPORTS" / "RAW_CSV_ARCHIVE_MANIFEST.csv"

HEADER_2000 = "序号,日期,水深(m),水温(°C),量程(m),数据(信号强度)"


def write_utf8_bom_file(path: Path) -> Path:
    lines = [
        HEADER_2000,
        "1,2026-10-31 00:00:00,0,22.2,37.5,255:255:0:12",
        "2,2026-10-31 00:00:00,0.5,22.1,37.5,10::abc:4",
        "3,2026-10-31 00:00:02,1.25,22.1,37.5,1:2:3",
    ]
    path.write_bytes(b"\xef\xbb\xbf" + ("\n".join(lines) + "\n").encode("utf-8"))
    return path


def write_gb18030_file(path: Path) -> Path:
    lines = [
        "序号,日期,水深(m),水温(℃),量程(m),数据(信号强度)",
        "1,2026/10/31 0:00,0.8625,22.1,37.5,255:255:255",
        "2,2026/10/31 0:00:01,0.9,22.1,37.5,1:2",
    ]
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("gb18030"))
    return path


def test_inspect_detects_encoding_bom_line_ending(tmp_path):
    f2000 = write_utf8_bom_file(tmp_path / "a.csv")
    f2001 = write_gb18030_file(tmp_path / "b.csv")

    i0 = cp.inspect_file(f2000)
    assert i0.encoding == "utf-8-sig" and i0.has_bom
    assert i0.line_ending == "LF" and i0.delimiter == ","
    assert i0.header_map["signal_raw"] == "数据(信号强度)"
    assert i0.unknown_headers == ()
    assert i0.sha256 == hashlib.sha256(f2000.read_bytes()).hexdigest()

    i1 = cp.inspect_file(f2001)
    assert i1.encoding == "gb18030" and not i1.has_bom
    assert i1.line_ending == "CRLF"
    assert i1.header_map["water_temp_c"] == "水温(℃)"


def test_iter_rows_preserves_line_number_and_does_not_dedup_same_second(tmp_path):
    path = write_utf8_bom_file(tmp_path / "a.csv")
    inspection = cp.inspect_file(path)
    rows = list(cp.iter_rows(inspection))
    assert [r.line_no for r in rows] == [2, 3, 4]
    # 同秒两条记录都保留（不得仅按时间戳去重）
    assert rows[0].timestamp == rows[1].timestamp
    assert len(rows) == 3
    assert rows[0].seq == 1 and rows[2].seq == 3
    assert rows[2].timestamp_format == "%Y-%m-%d %H:%M:%S"
    # 信号数组：空项与非数值项计数，位置保留
    assert rows[1].signal_len == 4
    assert rows[1].signal_empty_tokens == 1
    assert rows[1].signal_non_numeric == 1
    assert rows[1].signal[0] == 10.0 and rows[1].signal[1] is None
    assert rows[0].signal[:2] == [255.0, 255.0]


def test_iter_rows_parses_non_padded_hour_format(tmp_path):
    path = write_gb18030_file(tmp_path / "b.csv")
    inspection = cp.inspect_file(path)
    rows = list(cp.iter_rows(inspection))
    assert rows[0].timestamp.hour == 0 and rows[0].timestamp.minute == 0
    assert rows[0].timestamp_format == "%Y/%m/%d %H:%M"
    assert rows[0].depth_m == pytest.approx(0.8625)


def test_parse_timestamp_variants():
    for raw in ("2026-10-31 00:00:00", "2026/10/31 0:00", "2026/10/31 23:59:59"):
        dt, fmt, err = cp.parse_timestamp(raw)
        assert dt is not None and err is None
    dt, fmt, err = cp.parse_timestamp("not-a-time")
    assert dt is None and err


def test_first_zero_index_marks_blind_zone_end():
    """用户口径：首个 0 = 盲区结束；无 0 返回 None。"""
    assert cp.first_zero_index([255.0, 255.0, 0.0, 12.0]) == 2
    assert cp.first_zero_index([0.0, 255.0]) == 0
    assert cp.first_zero_index([1.0, None, 2.0]) is None
    assert cp.first_zero_index([]) is None


def test_signal_parse_marks_invalid_positions():
    values, empty, nonnum, trailing, errors = cp.parse_signal("1::x:4")
    assert values == [1.0, None, None, 4.0]
    assert empty == 1 and nonnum == 1 and trailing == 0 and errors


def test_signal_parse_trailing_colon_yields_empty_token(tmp_path):
    """真实文件每行以冒号结尾：1001 token = 1000 槽位 + 尾部空项。"""
    path = tmp_path / "trailing.csv"
    path.write_bytes(b"\xef\xbb\xbf" + (
        HEADER_2000 + "\n" + "1,2026-10-31 00:00:00,1,22.2,37.5,1:2:3:\n").encode("utf-8"))
    row = next(cp.iter_rows(cp.inspect_file(path)))
    assert row.signal_len == 4
    assert row.signal_trailing_empty == 1
    assert row.effective_signal_len == 3
    assert row.signal_empty_tokens == 1


@pytest.mark.skipif(not DATA_2000.exists() or not DATA_2001.exists(),
                    reason="原始 CSV 不在本机")
def test_raw_files_hash_unchanged_by_parse_and_matches_manifest():
    manifest = {}
    with MANIFEST.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["file_name"] in (DATA_2000.name, DATA_2001.name):
                manifest[row["file_name"]] = row["sha256_after"]

    for path in (DATA_2000, DATA_2001):
        before = cp.sha256_file(path)
        inspection = cp.inspect_file(path, compute_hash=False)
        list(cp.iter_rows(inspection, limit=20))
        after = cp.sha256_file(path)
        assert before == after, f"{path.name} 在解析后被改动"
        assert before == manifest[path.name], f"{path.name} 与归档清单不一致"

    assert cp.inspect_file(DATA_2000, compute_hash=False).encoding == "utf-8-sig"
    assert cp.inspect_file(DATA_2001, compute_hash=False).encoding == "gb18030"


def test_audit_writes_eight_artifacts_with_blocked_mapping(tmp_path, conn):
    path = write_utf8_bom_file(tmp_path / "2000_sample.csv")
    out = tmp_path / "data_audit"
    out.mkdir()
    audit = audit_s02.audit_device("2000", path, conn=conn)
    assert audit.rows_total == 3
    assert audit.same_second_groups == 1
    assert audit.depth_zero == 1
    # 盲区：行1 首零在索引 2；行2/3 无 0
    assert audit.sig_first_zero == {2: 1}
    assert audit.sig_rows_no_zero == 2
    assert audit.pre_zero_min == 255.0 and audit.pre_zero_max == 255.0
    assert audit.mask_status == "BLOCKED"  # 未登记映射 → 正式距离分析 BLOCKED

    audits = [audit]
    audit_s02.write_field_dictionary(audits, out)
    audit_s02.write_signal_array_audit(audits, out)
    audit_s02.write_timestamp_audit(audits, out)
    audit_s02.write_coverage_audit(audits, out)
    audit_s02.write_device_comparability(audits, out)
    audit_s02.write_bottom_reference_audit(conn, out, {"2000": audit})
    issues = audit_s02.write_issues(audits, out)
    audit_s02.write_report(audits, issues, out, generated_at="2026-11-16T00:00:00")

    for name in audit_s02.ARTIFACTS:
        assert (out / name).exists(), f"缺少工件 {name}"
    assert any(i[2] == "P0" and i[3] == "距离映射" for i in issues)
    report = (out / "DATA_AUDIT_REPORT.md").read_text(encoding="utf-8")
    assert "BLOCKED" in report and "5.2043059095" in report
    assert "1000 点" in report
