# -*- coding: utf-8 -*-
"""
按设备归档原始鱼探 CSV，并做移动前后全量 SHA-256 核对。

授权依据：用户 2026-11-14 18:48 指令「你看看探鱼-2001_2026-11-07文件夹。
这里面是设备2000和设备2001的数据。你整理一下文件夹。」
规范依据：02_CODEX_EXECUTION_GUIDE_FINAL.md 4.1（按设备分目录、只读保护）、
          3.2（未经用户允许不得擅自移动；移动前后须核对 SHA-256）。

保证：
  * 只做同盘 os.rename，不复制、不改写内容、不改文件名、不改时间戳；
  * 目标若已存在同名文件则整体中止，绝不覆盖；
  * 移动后逐文件重算 SHA-256 与字节数，与移动前清单一一比对；
  * 任何一项不一致即返回非零退出码，并在标准输出中明确报出；
  * 全部通过后才删除已空的源目录（os.rmdir 仅能删空目录）。

用法：python3 12_DOCUMENTATION/archive_raw_csv.py
产物：10_TEST_REPORTS/RAW_CSV_ARCHIVE_MANIFEST.csv
"""
import csv
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "探鱼-2001_2026-11-07")
FISHFINDER = os.path.join(ROOT, "01_ORIGINAL_DATA", "FISHFINDER")
INVENTORY = os.path.join(ROOT, "10_TEST_REPORTS", "RAW_CSV_PRECHECK_INVENTORY.csv")
MANIFEST = os.path.join(ROOT, "10_TEST_REPORTS", "RAW_CSV_ARCHIVE_MANIFEST.csv")

DEV_RE = re.compile(r"^探鱼-(\d{4})_\d{4}-\d{2}-\d{2}\.csv$")


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    if not os.path.isdir(SRC):
        print("源目录不存在，可能已归档过：%s" % SRC)
        return 2
    if not os.path.isfile(INVENTORY):
        print("缺少移动前哈希清单：%s" % INVENTORY)
        return 2

    with open(INVENTORY, encoding="utf-8-sig", newline="") as fh:
        before = list(csv.DictReader(fh))
    before_map = {r["file_name"]: r for r in before}

    src_files = sorted(f for f in os.listdir(SRC) if f.lower().endswith(".csv"))
    print("源目录 CSV 数：%d；移动前清单条数：%d" % (len(src_files), len(before)))

    if set(src_files) != set(before_map):
        print("源文件与清单不一致，中止。")
        print("  仅在源目录：", sorted(set(src_files) - set(before_map)))
        print("  仅在清单：", sorted(set(before_map) - set(src_files)))
        return 2

    plan = []
    for name in src_files:
        m = DEV_RE.match(name)
        if not m:
            print("文件名不符合 探鱼-<设备>_<日期>.csv 规则，中止：%s" % name)
            return 2
        dev = m.group(1)
        dst_dir = os.path.join(FISHFINDER, dev)
        dst = os.path.join(dst_dir, name)
        if os.path.exists(dst):
            print("目标已存在同名文件，拒绝覆盖，整体中止：%s" % dst)
            return 2
        plan.append((name, dev, os.path.join(SRC, name), dst, dst_dir,
                     os.path.getsize(os.path.join(SRC, name)),
                     os.path.getmtime(os.path.join(SRC, name))))

    devs = sorted({p[1] for p in plan})
    print("待归档设备：%s" % ", ".join(devs))
    for d in devs:
        n = sum(1 for p in plan if p[1] == d)
        b = sum(p[5] for p in plan if p[1] == d)
        print("  设备 %s：%2d 个文件，%d 字节" % (d, n, b))

    # 预建目标目录
    for d in devs:
        os.makedirs(os.path.join(FISHFINDER, d), exist_ok=True)

    # 同盘原子重命名
    for name, dev, src, dst, _dir, size, mtime in plan:
        os.rename(src, dst)
    print("已完成 %d 次同盘重命名（未复制、未改写内容）。" % len(plan))

    # 移动后全量复核
    rows = []
    ok = True
    for name, dev, src, dst, _dir, size_before, mtime_before in plan:
        size_after = os.path.getsize(dst)
        mtime_after = os.path.getmtime(dst)
        sha_before = before_map[name]["sha256"]
        sha_after = sha256_of(dst)
        hm = (sha_before == sha_after)
        sm = (size_before == size_after)
        tm = (abs(mtime_before - mtime_after) < 1e-6)
        src_rel = "探鱼-2001_2026-11-07/" + name
        dst_rel = "01_ORIGINAL_DATA/FISHFINDER/%s/%s" % (dev, name)
        rows.append({
            "file_name": name,
            "device_id": dev,
            "source_relative_path": src_rel,
            "archived_relative_path": dst_rel,
            "size_bytes": size_after,
            "sha256_before": sha_before,
            "sha256_after": sha_after,
            "hash_match": "PASS" if hm else "FAIL",
            "size_match": "PASS" if sm else "FAIL",
            "mtime_preserved": "PASS" if tm else "FAIL",
            "note": "用户 2026-11-14 18:48 指示整理后按设备归档；文件名与内容未改动；非 S02 审计结论",
        })
        if not (hm and sm and tm):
            ok = False
            print("校验失败：%s hash=%s size=%s mtime=%s" % (
                name, "PASS" if hm else "FAIL", "PASS" if sm else "FAIL",
                "PASS" if tm else "FAIL"))

    fields = ["file_name", "device_id", "source_relative_path",
              "archived_relative_path", "size_bytes", "sha256_before",
              "sha256_after", "hash_match", "size_match",
              "mtime_preserved", "note"]
    with open(MANIFEST, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print("归档清单已写出：%s" % os.path.relpath(MANIFEST, ROOT))
    print("校验汇总：%d/%d 三项全部 PASS；合计 %d 字节" %
          (sum(1 for r in rows if r["hash_match"] == "PASS" and
               r["size_match"] == "PASS" and r["mtime_preserved"] == "PASS"),
           len(rows), sum(r["size_bytes"] for r in rows)))

    if not ok:
        print("存在校验失败项，保留源目录现状，不做清理。")
        return 1

    left = os.listdir(SRC)
    if left:
        print("源目录仍有 %d 个非 CSV 条目，未删除源目录：%s" % (len(left), left[:10]))
    else:
        os.rmdir(SRC)
        print("源目录已空并移除：探鱼-2001_2026-11-07/（原目录名已记入清单）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
