# -*- coding: utf-8 -*-
"""
科研配色方案合规校验器（FIGURE_COLOR_SPEC_V1）。

检查三件事：
  1. 05_CONFIG/figure_palette.json 内所有 HEX 与 RGB 是否一一对应；
  2. 三张参考图的 SHA-256 是否与规格登记一致（防止参考图被替换）；
  3. 生成物（默认 DEMO_PROTOTYPE.html，可追加路径）中出现的每个 HEX 颜色
     是否都在「三套色板 + 中性色」白名单内。

规则：色板外颜色数必须为 0，否则退出码 1。
用法：
  python3 12_DOCUMENTATION/check_figure_colors.py
  python3 12_DOCUMENTATION/check_figure_colors.py path/to/figure.svg path/to/page.html
"""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import figure_palette as fp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
TEXT_EXT = (".html", ".htm", ".svg", ".css", ".js", ".json", ".yaml", ".yml", ".py", ".md")


def check_spec():
    fp.self_check()
    print("[1/3] 色板 HEX/RGB 一致性：PASS（色板 %d 色 + 中性 %d 色 = 白名单 %d 色）" %
          (sum(len(p["colors"]) for p in fp.PALETTES.values()),
           len(fp.NEUTRAL), len(fp.ALLOWED_HEX)))


def check_references():
    bad = []
    for ref in fp.SPEC["source_references"]:
        p = os.path.join(ROOT, ref["file"].replace("/", os.sep))
        if not os.path.isfile(p):
            bad.append("缺失 " + ref["file"])
            continue
        b = open(p, "rb").read()
        if len(b) != ref["size_bytes"] or hashlib.sha256(b).hexdigest() != ref["sha256"]:
            bad.append("哈希/大小不符 " + ref["file"])
    print("[2/3] 参考图 SHA-256：%s（%d 张）" %
          ("PASS" if not bad else "FAIL", len(fp.SPEC["source_references"])))
    for x in bad:
        print("      ", x)
    return bad


def check_artifact(path):
    """扫描一个文本型生成物，返回 (总色值数, 违规色值集合, 全部色值集合)。"""
    s = open(path, encoding="utf-8", errors="replace").read()
    found = {}
    for raw in HEX_RE.findall(s):
        n = fp.normalize(raw)
        if n:
            found[n] = found.get(n, 0) + 1
    bad = {h: c for h, c in found.items() if h not in fp.ALLOWED_HEX}
    return sum(found.values()), bad, found


def main():
    check_spec()
    bad_refs = check_references()

    args = sys.argv[1:]
    targets = args or [os.path.join(ROOT, "12_DOCUMENTATION", "DEMO_PROTOTYPE.html")]
    total_bad = {}
    print("[3/3] 生成物配色合规扫描：")
    for t in targets:
        if not os.path.isfile(t):
            print("       FAIL 文件不存在:", t)
            total_bad["<缺失文件>"] = 1
            continue
        if not t.lower().endswith(TEXT_EXT):
            print("       SKIP 非文本型（位图请用绘图脚本自查）:", os.path.relpath(t, ROOT))
            continue
        n, bad, found = check_artifact(t)
        rel = os.path.relpath(t, ROOT)
        print("       %s：%d 处色值，%d 种唯一色，色板外 %d 种 -> %s" %
              (rel, n, len(found), len(bad), "PASS" if not bad else "FAIL"))
        for h, c in sorted(bad.items()):
            print("         违规 %s × %d" % (h, c))
            total_bad[h] = total_bad.get(h, 0) + c

    ok = not bad_refs and not total_bad
    print("\n结论：%s（色板外颜色总数 %d，参考图异常 %d）" %
          ("PASS · 符合 FIGURE_COLOR_SPEC_V1" if ok else "FAIL · 不符合规格",
           sum(total_bad.values()), len(bad_refs)))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
