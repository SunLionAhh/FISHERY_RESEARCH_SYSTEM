# -*- coding: utf-8 -*-
"""
科研配色方案加载器 —— 项目所有绘图脚本的统一取色入口。

规格：05_CONFIG/FIGURE_COLOR_SPEC.md（FIGURE_COLOR_SPEC_V1，用户 2026-11-14 确认）
唯一色值源：05_CONFIG/figure_palette.json
校验器：12_DOCUMENTATION/check_figure_colors.py

用法：
    import figure_palette as fp
    fp.categorical(6)          # 默认分组色板 C 的前 6 色
    fp.color("A", 4)           # 方案 A 第 4 色 #0271AC
    fp.LINE["主数据"]          # 语义色
    fp.is_allowed("#0271AC")  # True
    fp.self_check()            # 校验 HEX/RGB 一致性，失败抛 AssertionError

严格约束：绘图脚本不得硬编码颜色；需要新颜色须用户确认并升版规格。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "05_CONFIG", "figure_palette.json")

with open(CONFIG, encoding="utf-8") as _f:
    SPEC = json.load(_f)

PALETTES = SPEC["palettes"]
NEUTRAL = {c["hex"].upper(): c["role"] for c in SPEC["neutral"]["colors"]}

# 全部允许的颜色（三套色板 + 中性色），统一大写 6 位
ALLOWED_HEX = set(NEUTRAL)
for _p in PALETTES.values():
    for _c in _p["colors"]:
        ALLOWED_HEX.add(_c["hex"].upper())

SHORT = {"A": "A_SCIENTIFIC_PRIMARY", "B": "B_SOFT_PALE", "C": "C_PASTEL_SIX"}

# 语义色：折线/强调取方案 A 较深色，浅底取方案 B，分组取方案 C
LINE = {
    "主数据": "#0271AC",
    "高值强调": "#E05C4F",
    "弱强调": "#9599C6",
    "显著性": "#BE71AF",
    "玫瑰主线": "#DA7A9B",
}
FILL = {
    "极淡粉": "#FEEFF2",
    "极淡黄": "#FEFBE9",
    "极淡蓝": "#EFF5FF",
    "极淡紫": "#F6DDF8",
}
INK = {
    "正文": "#2B2B2B",
    "次级": "#4A4A4A",
    "次要": "#8A8A8A",
    "网格": "#EDEDED",
    "边框": "#E8E8E8",
    "虚线": "#D8D8D8",
    "表头底": "#F7F7F7",
    "页面底": "#FBFBFB",
    "白": "#FFFFFF",
}


def palette(key):
    """按 'A'/'B'/'C' 或全称返回色板定义。"""
    return PALETTES[SHORT.get(key, key)]


def colors(key):
    """返回该色板的 HEX 列表，顺序固定。"""
    return [c["hex"] for c in palette(key)["colors"]]


def color(key, index):
    """取色板第 index 色（1 起算）。"""
    return colors(key)[index - 1]


def categorical(n):
    """默认分类色：方案 C 前 n 色；超过 6 组须用户确认扩展色板。"""
    cs = colors("C")
    if n > len(cs):
        raise ValueError(
            "默认分组色板只有 %d 色，请求 %d 组；须用户确认后升版规格" % (len(cs), n))
    return cs[:n]


def normalize(h):
    """把 #RGB / #RRGGBB 统一成大写 6 位；无效返回 None。"""
    if not isinstance(h, str):
        return None
    s = h.strip().lstrip("#")
    if len(s) == 3 and all(ch in "0123456789abcdefABCDEF" for ch in s):
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6 or not all(ch in "0123456789abcdefABCDEF" for ch in s):
        return None
    return "#" + s.upper()


def is_allowed(h):
    n = normalize(h)
    return n is not None and n in ALLOWED_HEX


def self_check():
    """校验所有色板 HEX 与 RGB 一一对应，语义色也在白名单内。"""
    for name, p in PALETTES.items():
        for c in p["colors"]:
            h = normalize(c["hex"])
            assert h == c["hex"].upper(), (name, c["hex"])
            rgb = tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
            assert rgb == tuple(c["rgb"]), (name, c["hex"], rgb, c["rgb"])
    for group in (LINE, FILL, INK):
        for k, v in group.items():
            assert is_allowed(v), ("语义色不在色板/中性色白名单内", k, v)
    for c in SPEC["neutral"]["colors"]:
        assert normalize(c["hex"]) in ALLOWED_HEX, c["hex"]
    return True


def swatches_html():
    """生成三套色卡的 HTML 片段，供演示页与配置说明复用。"""
    import html as _html
    out = []
    for key in ("A", "B", "C"):
        p = palette(key)
        cells = []
        for c in p["colors"]:
            h = c["hex"].upper()
            rgb = "(%d, %d, %d)" % tuple(c["rgb"])
            cells.append(
                '<div class="sw"><div class="chip" style="background:%s"></div>'
                '<div class="hx">%s</div><div class="rg">%s</div>'
                '<div class="rl">%s</div></div>'
                % (h, h, rgb, _html.escape(c["role"])))
        out.append(
            '<div class="pal"><div class="pt"><b>%s</b> · %s</div>'
            '<div class="pcharts">适用：%s</div><div class="sws">%s</div></div>'
            % (_html.escape(key), _html.escape(p["label"]),
               _html.escape("、".join(p["typical_charts"])), "".join(cells)))
    return "".join(out)


if __name__ == "__main__":
    self_check()
    print("规格:", SPEC["spec_id"])
    print("允许颜色数:", len(ALLOWED_HEX), "（色板 17 + 中性 9）")
    for k in ("A", "B", "C"):
        print(" ", k, " ".join(colors(k)))
    print("HEX/RGB 一致性与语义色白名单：PASS")
