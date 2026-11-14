# -*- coding: utf-8 -*-
"""
生成一个「只读演示原型」静态页面（单文件 HTML + 本地图片副本）。

严格边界：
- 不是 S10 Flask 科研工作台；不连数据库、不跑分析、不启动服务。
- 只使用本机真实存在的资料：288 条风速记录、11 张潮汐截图、项目状态与缺口清单。
- 不含任何声学活动指标、鱼群结论、论文图表或编造数值。
- 所有分析区块明确显示为「待真实数据」，禁止伪装成已实现功能。
- 数据全部来自本地文件，页面不请求任何外部资源，可离线双击打开。

配色（2026-11-14 起强制）：
- 规格 05_CONFIG/FIGURE_COLOR_SPEC.md（FIGURE_COLOR_SPEC_V1，用户确认）。
- 所有颜色必须从 12_DOCUMENTATION/figure_palette.py 取，禁止硬编码。
- 生成后必须运行 12_DOCUMENTATION/check_figure_colors.py，色板外颜色数为 0 才算通过。

运行：python3 12_DOCUMENTATION/generate_demo.py
"""
import csv
import html
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import figure_palette as fp

fp.self_check()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIND_CSV = os.path.join(ROOT, "02_IMPORTED_DATA", "ENVIRONMENT", "WIND",
                        "wind_hourly_20261030_20261110_PREPROCESSED.csv")
TIDE_CSV = os.path.join(ROOT, "02_IMPORTED_DATA", "ENVIRONMENT", "TIDE",
                        "tide_image_inventory.csv")
TIDE_SRC = os.path.join(ROOT, "14_TEMP", "tide_unzip", "潮汐")
ASSETS = os.path.join(ROOT, "12_DOCUMENTATION", "demo_assets")
OUT = os.path.join(ROOT, "12_DOCUMENTATION", "DEMO_PROTOTYPE.html")

C = fp.colors("C")          # 默认分组色板（G1—G6）
INK = fp.INK
FILL = fp.FILL
LINE = fp.LINE

with open(WIND_CSV, encoding="utf-8-sig", newline="") as f:
    wind = list(csv.DictReader(f))
with open(TIDE_CSV, encoding="utf-8-sig", newline="") as f:
    tide = list(csv.DictReader(f))

os.makedirs(ASSETS, exist_ok=True)
for r in tide:
    src = os.path.join(TIDE_SRC, r["image_file"])
    dst = os.path.join(ASSETS, r["image_file"])
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)

pts = [{"t": r["observation_datetime_local"], "v": float(r["value"]),
        "p": r["period_flag"]} for r in wind]
vals = [p["v"] for p in pts]
n_hist = sum(1 for p in pts if p["p"] == "历史存档")
n_now = sum(1 for p in pts if p["p"] == "当日滚动")
n_fc = sum(1 for p in pts if p["p"] == "未来预报")

# 三时段分类色：主数据→深蓝，滚动→珊瑚红，预报→灰蓝紫（弱化，避免与实测混淆）
period_colors = {
    "历史存档": LINE["主数据"],
    "当日滚动": LINE["高值强调"],
    "未来预报": LINE["弱强调"],
}

W, H, PL, PR, PT, PB = 1160, 250, 46, 16, 16, 34
vmin, vmax = 0, 14
def X(i): return PL + i * (W - PL - PR) / (len(pts) - 1)
def Y(v): return PT + (vmax - v) / (vmax - vmin) * (H - PT - PB)

grid = []
for v in (0, 3.5, 7, 10.5, 14):
    y = Y(v)
    grid.append(f'<line x1="{PL}" y1="{y:.1f}" x2="{W-PR}" y2="{y:.1f}" stroke="{INK["网格"]}" stroke-width="1"/>')
    grid.append(f'<text x="{PL-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="{INK["次要"]}">{v}</text>')
for i in range(0, len(pts), 24):
    x = X(i)
    grid.append(f'<line x1="{x:.1f}" y1="{PT}" x2="{x:.1f}" y2="{H-PB}" stroke="{INK["表头底"]}" stroke-width="1"/>')
    grid.append(f'<text x="{x:.1f}" y="{H-12}" text-anchor="middle" font-size="11" fill="{INK["次要"]}">{pts[i]["t"][5:10]}</text>')

segments = []
for i in range(len(pts) - 1):
    c = period_colors.get(pts[i]["p"], LINE["弱强调"])
    segments.append(f'<line x1="{X(i):.1f}" y1="{Y(pts[i]["v"]):.1f}" x2="{X(i+1):.1f}" y2="{Y(pts[i+1]["v"]):.1f}" stroke="{c}" stroke-width="1.6"/>')
for i, p in enumerate(pts):
    if i % 6 == 0:
        segments.append(f'<circle cx="{X(i):.1f}" cy="{Y(p["v"]):.1f}" r="1.8" fill="{period_colors.get(p["p"], LINE["弱强调"])}"/>')

chart = f'''<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="逐小时风速折线图">
<rect x="{PL}" y="{PT}" width="{W-PL-PR}" height="{H-PT-PB}" fill="{INK["白"]}" stroke="none"/>
{''.join(grid)}
{''.join(segments)}
<text x="{PL}" y="12" font-size="11" fill="{INK["次要"]}">风速 m/s</text>
</svg>'''

stage_rows = [
    ("S00", "项目检查、目录建立和备份", "目录与资料已备；21 个 CSV 已按设备归档并预检；以 V4 为准已裁定；Git 初始回滚点已建、Python 3.10 待 S00 安装；阶段报告未做"),
    ("S01", "数据库、五台设备、独立参数", "未开始"),
    ("S02", "真实 CSV 解析与质量审计", "未开始 · 21 个 CSV 为第一阶段双站完整导出、已归档；归档不等于导入；解析器须支持持续增量上传"),
    ("S03", "每日统计、增量上传、缺测", "未开始"),
    ("S04", "任意时间 / 天数 / 设备比较", "未开始"),
    ("S05", "环境数据接入与联合分析", "仅风速与潮汐资料预检，未入库"),
    ("S06", "日内、昼夜和晨昏", "未开始"),
    ("S07", "深度、底界、三水层、长期规律", "未开始 · 出图须执行科研配色规格"),
    ("S08", "五站 GPS 空间与动态分析", "未开始 · GPS 坐标未提供"),
    ("S09", "OriginPro、16 类图、动态文件", "未开始 · OriginPro 未安装；出图须执行科研配色规格"),
    ("S10", "Flask 完整科研工作台（网页）", "未开始 · 本页不是该工作台；图表须执行科研配色规格"),
    ("S11", "最终系统与预答辩验收", "未开始"),
]
stage_html = "".join(
    f'<tr><td class="sid">{html.escape(a)}</td><td>{html.escape(b)}</td>'
    f'<td class="st">{html.escape(c)}</td></tr>' for a, b, c in stage_rows)

tide_cards = "".join(
    f'<figure><img src="./demo_assets/{html.escape(r["image_file"])}" alt="{html.escape(r["date"])} 潮汐曲线" loading="lazy">'
    f'<figcaption>{html.escape(r["date"])} · {html.escape(r["lunar"])} · {html.escape(r["tide_type"])}</figcaption></figure>'
    for r in sorted(tide, key=lambda x: x["date"]))

gaps = [
    ("G1", "双站同期窗口 10-31—11-07 须按真实时间戳复核；2001 到 11-07 结束、不会补传", "影响 S07 冻结与论文第三章"),
    ("G1", "Python 3.10 已获安装授权，待 S00 安装并建 .venv", "S00 前置动作"),
    ("G1", "Git 初始回滚点已建立；S00 须核验复用并另建阶段回滚点", "S00 前置动作"),
    ("G2", "21 个 CSV 分属两套编码/换行/时间格式，须逐文件探测", "S02 解析器硬约束"),
    ("G2", "五台安装参数、五站 GPS 坐标；2002/2003/2005 数据后续上传", "阻断 S01 / S08 五站部分"),
    ("G2", "水温数值资料、潮汐逐时数值表与基准面、实测风速", "阻断 S05"),
    ("G2", "厂家资料（量程、采样机制、量纲、近场盲区）", "阻断候选回波指标"),
    ("G3", "双站 / 五站实际起止时间与调试期时间线", "阻断数据冻结与论文"),
    ("G4", "OriginPro 2026b 安装与 10 项 COM 实测", "阻断 S09"),
    ("G5", "31 类入口覆盖 29 项界面能力（非冲突）；PyCharm 版本差异待登记", "范围缩减须正式变更"),
]
gap_html = "".join(
    f'<tr><td class="gid">{html.escape(a)}</td><td>{html.escape(b)}</td>'
    f'<td class="st">{html.escape(c)}</td></tr>' for a, b, c in gaps)

# KPI 卡片顶边按默认分组色板 C 顺序轮转
kpis = [
    ("NOT_STARTED", "当前阶段状态（S00 未实施）", False),
    ("15", "已建立的一级目录", False),
    ("8", "已归档并记录 SHA-256 的资料", False),
    (str(len(pts)), "风速真实记录（12 天 × 24 条）", False),
    (str(len(tide)), "潮汐曲线截图（无数值表）", False),
    ("21", "已按设备归档的原始 CSV（8.38 GB）", False),
    ("0", "已完成 S02 审计的声学数据行", True),
    ("26", "合规色值（17 色板 + 9 中性）", False),
]
kpi_html = "".join(
    f'<div class="kpi" style="border-top:3px solid {C[i % len(C)]}">'
    f'<div class="n{" warn" if warn else ""}">{html.escape(n)}</div>'
    f'<div class="l">{html.escape(label)}</div></div>'
    for i, (n, label, warn) in enumerate(kpis))

palette_html = fp.swatches_html()

doc = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FISHERY_RESEARCH_SYSTEM · 只读演示原型</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:{INK["页面底"]};color:{INK["正文"]};font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1240px;margin:0 auto;padding:28px 24px 60px}}
h1{{font-size:22px;font-weight:600;margin:0 0 6px}}
h2{{font-size:16px;font-weight:600;margin:0 0 14px}}
.sub{{color:{INK["次要"]};font-size:13px;margin:0 0 20px}}
.banner{{background:{FILL["极淡黄"]};border:1px solid {fp.color("A",6)};border-left:4px solid {LINE["玫瑰主线"]};border-radius:8px;padding:14px 18px;margin-bottom:22px;color:{INK["正文"]};font-size:13px}}
.banner b{{color:{LINE["高值强调"]}}}
.card{{background:{INK["白"]};border:1px solid {INK["边框"]};border-radius:10px;padding:20px 22px;margin-bottom:20px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:12px;margin-bottom:20px}}
.kpi{{background:{INK["白"]};border:1px solid {INK["边框"]};border-radius:10px;padding:16px 18px}}
.kpi .n{{font-size:24px;font-weight:600;color:{LINE["主数据"]};line-height:1.2}}
.kpi .n.warn{{color:{LINE["高值强调"]}}}
.kpi .l{{font-size:12px;color:{INK["次要"]};margin-top:4px}}
.legend{{display:flex;gap:20px;flex-wrap:wrap;font-size:12px;color:{INK["次级"]};margin:6px 0 12px}}
.legend i{{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:6px;border-radius:2px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid {INK["网格"]};vertical-align:top}}
th{{color:{INK["次要"]};font-weight:500;background:{INK["表头底"]}}}
.sid,.gid{{font-family:ui-monospace,Consolas,monospace;color:{LINE["主数据"]};width:52px}}
.st{{color:{INK["次要"]}}}
.blank{{background:{FILL["极淡粉"]};border:1px dashed {C[4]};border-radius:8px;padding:26px;text-align:center;color:{INK["次要"]};font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px}}
figure{{margin:0;border:1px solid {INK["边框"]};border-radius:8px;overflow:hidden;background:{INK["白"]}}}
figure img{{width:100%;display:block}}
figcaption{{font-size:11px;color:{INK["次级"]};padding:7px 9px;border-top:1px solid {INK["网格"]}}}
.note{{font-size:12px;color:{INK["次要"]};margin-top:12px}}
code{{background:{FILL["极淡蓝"]};padding:1px 5px;border-radius:4px;font-size:12px}}
.pal{{border:1px solid {INK["边框"]};border-radius:8px;padding:14px 16px;margin-bottom:14px;background:{INK["白"]}}}
.pt{{font-size:13px;color:{INK["正文"]}}}
.pcharts{{font-size:12px;color:{INK["次要"]};margin:4px 0 12px}}
.sws{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}}
.sw{{text-align:center}}
.chip{{height:40px;border:1px solid {INK["边框"]};border-radius:8px}}
.hx{{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:{INK["正文"]};margin-top:5px}}
.rg{{font-size:11px;color:{INK["次要"]}}}
.rl{{font-size:11px;color:{INK["次要"]};margin-top:2px}}
footer{{color:{INK["次要"]};font-size:12px;text-align:center;margin-top:26px}}
</style>
</head>
<body>
<div class="wrap">
<h1>渔业声学监测科研分析系统</h1>
<p class="sub">只读演示原型 · 2026-11-14 · 数据全部来自本机文件，离线可打开 · 以 V4 为准，五台为 2000/2001/2002/2003/2005、没有 2004 · 执行科研配色规格 V1</p>

<div class="banner">
<b>这不是规范要求的 Flask 科研工作台。</b>
本页是单文件静态演示，用现有真实资料说明「网页能显示什么、还缺什么」；不连接数据库、不运行分析、不启动服务、不包含任何声学活动指标或科研结论。
FINAL 1.5 的 S10 工作台需在 S00—S09 全部通过后由编码 Agent 实现。本页不进论文、不进验收、不计入任何阶段成果。
</div>

<div class="stats">{kpi_html}</div>

<div class="card">
<h2>科研配色方案 · 用户确认规格 <code>FIGURE_COLOR_SPEC_V1</code></h2>
<p class="note" style="margin-top:0">2026-11-14 用户指示「里面出的图片要使用科研配色方案……记录这条规格，并严格执行」。色值逐字取自用户提供的三张参考图，已登记在 <code>05_CONFIG/figure_palette.json</code>；规格全文见 <code>05_CONFIG/FIGURE_COLOR_SPEC.md</code>。本页所有颜色均从加载器 <code>figure_palette.py</code> 取得，并由 <code>check_figure_colors.py</code> 校验色板外颜色为 0。方案 C 为默认分组色板（G1—G6 顺序固定），方案 A 用于折线与强调，方案 B 用于浅底与置信带。</p>
{palette_html}
<p class="note">原始资料不适用本规格：下方 11 张潮汐 PNG 是资料截图，保持原样未改色、未重绘。缺测一律留白标 NA，不使用零值色代替。</p>
</div>

<div class="card">
<h2>风速 · 真实数据（唯一已可展示的时序资料）</h2>
<div class="legend">
<span><i style="background:{period_colors["历史存档"]}"></i>历史存档 {n_hist} 条</span>
<span><i style="background:{period_colors["当日滚动"]}"></i>当日滚动 {n_now} 条</span>
<span><i style="background:{period_colors["未来预报"]}"></i>未来预报 {n_fc} 条</span>
<span>范围 {min(vals)}—{max(vals)} m/s · 均值 {sum(vals)/len(vals):.2f} m/s · 空值 0</span>
</div>
{chart}
<p class="note">来源：Open-Meteo 数值气象模型，网格 27.87346°N / 121.11486°E，北京时间，10 m 高度。<b>原表自述「历史时段也不是现场实测」</b>，且含 120 条未来预报，不能作为实测风速用于论文关联分析。此处仅作资料形态展示。折线三色取自方案 A，且以深蓝→珊瑚红→灰蓝紫的对比度递减表达可信度递减，不单靠颜色区分（图例另有文字）。</p>
</div>

<div class="card">
<h2>声学分析区 · 待真实数据</h2>
<div class="blank">
24 小时活动曲线 / 日内热图 / 昼夜晨昏 / 三水层 / 五站空间 / 规律证据卡片<br>
21 个原始 CSV（8.38 GB）已按设备归档到 01_ORIGINAL_DATA/FISHFINDER/2000/、2001/ 并完成 SHA-256 与结构预检（归档前后哈希一致），但归档不等于导入，S02 流式解析与质量审计尚未执行，且五站参数、GPS、水温仍缺，故不显示任何占位数值或模拟曲线。
</div>
<p class="note">规范要求「不得虚构观测数据」「缺测显示 NA，不显示为零」，因此这里保持空白而非填充示例值。这正是「有网页 ≠ 有分析结果」的直观例子：文件已经躺在磁盘上，但没有解析引擎，页面依然画不出一条真实活动曲线。</p>
</div>

<div class="card">
<h2>潮汐 · 11 张曲线截图（2026-10-31 — 11-10）</h2>
<div class="grid">{tide_cards}</div>
<p class="note">纵轴为潮高 cm，但<b>潮位基准面、站点、时区、实测/预报属性均缺失</b>，且没有逐时数值表。规范与开发总规划明确禁止图像估读产生超出图片分辨率的伪精确值，故本页未做任何数字化。</p>
</div>

<div class="card">
<h2>S00—S11 阶段状态</h2>
<table><thead><tr><th>阶段</th><th>任务</th><th>当前状态</th></tr></thead><tbody>{stage_html}</tbody></table>
</div>

<div class="card">
<h2>待补齐清单（摘选，完整版见 WORKBUDDY_SCOPE_AND_GAPS.md）</h2>
<table><thead><tr><th>级别</th><th>缺口</th><th>影响</th></tr></thead><tbody>{gap_html}</tbody></table>
</div>

<footer>本页由 <code>12_DOCUMENTATION/generate_demo.py</code> 从本地 CSV 生成 · 不请求任何外部资源 · 全部数据保留在本机磁盘 · 配色合规校验：<code>python3 12_DOCUMENTATION/check_figure_colors.py</code></footer>
</div>
</body>
</html>'''

with open(OUT, "w", encoding="utf-8") as f:
    f.write(doc)
print("生成:", OUT, os.path.getsize(OUT), "字节")
print("图片副本:", len([x for x in os.listdir(ASSETS) if x.endswith(".png")]), "张 ->", ASSETS)
print("风速点数:", len(pts), "潮汐截图:", len(tide))
print("取色来源:", os.path.relpath(fp.CONFIG, ROOT))
