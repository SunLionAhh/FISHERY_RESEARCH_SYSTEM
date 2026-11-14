# -*- coding: utf-8 -*-
"""
原始鱼探 CSV 只读预检盘点（流式，不加载整文件、不修改原件、不移动文件）。

定位：
- 这是资料盘点，不是 S02 全量数据质量审计，不生成 field_dictionary.csv 等 8 项正式产物。
- 不做同秒多记录、时间断档、异常值、信号值分布等 S02 审计项。
- 2026-11-14 18:50 后改为扫描归档位置 01_ORIGINAL_DATA/FISHFINDER/<设备>/。
- 输出 10_TEST_REPORTS/RAW_CSV_PRECHECK_INVENTORY_CURRENT.csv（归档后清单），
  并自动与归档前快照 RAW_CSV_PRECHECK_INVENTORY.csv 逐文件比对 SHA-256。
  归档前快照是 archive_raw_csv.py 的校验基准，本脚本**不会覆盖它**。

运行：python3 12_DOCUMENTATION/precheck_raw_csv.py
"""
import csv
import glob
import hashlib
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FISHFINDER = os.path.join(ROOT, "01_ORIGINAL_DATA", "FISHFINDER")
BEFORE = os.path.join(ROOT, "10_TEST_REPORTS", "RAW_CSV_PRECHECK_INVENTORY.csv")
OUT = os.path.join(ROOT, "10_TEST_REPORTS", "RAW_CSV_PRECHECK_INVENTORY_CURRENT.csv")


def sniff(head):
    bom = head.startswith(b"\xef\xbb\xbf")
    try:
        head.decode("utf-8")
        enc = "UTF-8"
    except UnicodeDecodeError:
        enc = "GBK"
    nl = "CRLF" if b"\r\n" in head[:1200] else "LF"
    return enc, "BOM" if bom else "NO_BOM", nl


def first_last(path, enc):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(6000)
    lines = head.split(b"\n")
    first = ""
    for raw in lines[1:3]:
        s = raw.decode(enc, errors="replace").strip("\r")
        if "," in s:
            first = s.split(",")[1].strip()
            break
    with open(path, "rb") as f:
        f.seek(max(0, size - 12000))
        tail = f.read()
    last = ""
    for raw in tail.split(b"\n"):
        s = raw.decode(enc, errors="replace").strip("\r")
        if "," in s and s[0].isdigit():
            last = s.split(",")[1].strip()
    parts = lines[1].decode(enc, errors="replace").strip("\r").split(",")[-1].split(":")
    npts = len([x for x in parts if x != ""])
    return first, last, npts


def scan(path):
    h = hashlib.sha256()
    nl_count = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(4 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            nl_count += chunk.count(b"\n")
    return h.hexdigest(), nl_count


def main():
    files = sorted(glob.glob(os.path.join(FISHFINDER, "*", "*.csv")))
    if not files:
        print("未在 %s 下找到 CSV，请检查归档状态。" % FISHFINDER)
        return
    rows = []
    for i, p in enumerate(files, 1):
        name = os.path.basename(p)
        with open(p, "rb") as f:
            head = f.read(6000)
        enc, bom, nl = sniff(head)
        size = os.path.getsize(p)
        digest, lines = scan(p)
        first, last, npts = first_last(p, enc)
        fmt = "ISO_YYYY-MM-DD_HH:MM:SS" if "-" in first else "SLASH_YYYY/M/D_H:MM"
        dev = name.split("_")[0].replace("探鱼-", "")
        date = name.split("_")[1].replace(".csv", "")
        rows.append({
            "relative_path": os.path.relpath(p, ROOT).replace(os.sep, "/"),
            "file_name": name, "device_id_in_filename": dev, "date_in_filename": date,
            "size_bytes": size, "sha256": digest, "encoding": enc, "bom": bom,
            "newline": nl, "timestamp_format": fmt, "first_timestamp": first,
            "last_timestamp": last, "signal_points_excl_trailing_empty": npts,
            "text_line_count_incl_header": lines,
            "note": "归档后复跑的只读预检；路径符合 02 指南 4.1；非 S02 审计结论",
        })
        print("[%02d/%02d] %s  %d bytes  lines=%d  %s" %
              (i, len(files), name, size, lines, digest[:12]))

    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\n输出:", OUT)
    print("文件数:", len(rows), "合计字节:", sum(r["size_bytes"] for r in rows))
    print("总文本行数(含表头):", sum(r["text_line_count_incl_header"] for r in rows))

    # 与归档前快照独立比对
    if os.path.isfile(BEFORE):
        with open(BEFORE, encoding="utf-8-sig", newline="") as f:
            before = {r["file_name"]: r for r in csv.DictReader(f)}
        same, diff = 0, []
        for r in rows:
            b = before.get(r["file_name"])
            if b and b["sha256"] == r["sha256"] and int(b["size_bytes"]) == r["size_bytes"]:
                same += 1
            else:
                diff.append(r["file_name"])
        print("与归档前快照比对：%d/%d SHA-256 与字节数一致" % (same, len(rows)))
        if diff:
            print("  不一致文件:", diff)
    import collections
    for k in ("encoding", "bom", "newline", "timestamp_format", "signal_points_excl_trailing_empty"):
        print(k, dict(collections.Counter(str(r[k]) for r in rows)))


if __name__ == "__main__":
    main()
