# -*- coding: utf-8 -*-
"""
WorkBuddy 辅助脚本：环境资料预检与格式预处理。

定位（重要）：
- 这不是 FINAL 1.5 规范中的任何阶段交付，不生成 STAGE_Sxx.md。
- 不生成 import_batch_id / run_id，不写入正式数据库。
- 产物是「供 S00 盘点、S05 手动导入参考」的预处理副本，S05 必须重新核验。
- 不对潮汐曲线截图做图像数字化（附录 A1 明确禁止生成超出图片分辨率的伪精确值）。

运行：python3 12_DOCUMENTATION/preprocess_environment.py
可重复运行，输出覆盖自身产物；不修改 01_ORIGINAL_DATA 下任何原始文件。
"""
import csv
import datetime
import hashlib
import os
import zipfile
from xml.etree import ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIND_SRC = os.path.join(ROOT, "01_ORIGINAL_DATA", "ENVIRONMENT", "WIND",
                        "洞头附近逐小时风速_2026-10-30至11-10.xlsx")
TIDE_SRC = os.path.join(ROOT, "01_ORIGINAL_DATA", "ENVIRONMENT", "TIDE", "潮汐.zip")
OUT_WIND = os.path.join(ROOT, "02_IMPORTED_DATA", "ENVIRONMENT", "WIND")
OUT_TIDE = os.path.join(ROOT, "02_IMPORTED_DATA", "ENVIRONMENT", "TIDE")
UNZIP = os.path.join(ROOT, "14_TEMP", "tide_unzip", "潮汐")
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# 由 14_TEMP/tide_titles.png 逐张识别得出；未做数值估读
TIDE_META = {
    "1d55c9a39ef4876e7e1aad5337c315df.png": ("2026-11-09", "农历十月初一", "大潮"),
    "32d52ce5045749c88ac1e3b16f801195.png": ("2026-11-04", "农历九月廿六", "小潮"),
    "4180701a293f29d984822b91f839a720.png": ("2026-11-05", "农历九月廿七", "中潮"),
    "49c611576875de14230406f24d0d3944.png": ("2026-11-08", "农历九月三十", "中潮"),
    "69df8394-65d3-4fc2-9dbc-d40159a30a8a.png": ("2026-11-07", "农历九月廿九", "中潮"),
    "6a80c0b650e823ee941b2b79b5c5c005.png": ("2026-11-10", "农历十月初二", "大潮"),
    "6dd46f6ed49b9f5c3fc7651477a236b9.png": ("2026-11-01", "农历九月廿三", "小潮"),
    "98b87721-26f7-4327-b3ad-53593ef5e618.png": ("2026-11-06", "农历九月廿八", "中潮"),
    "bcd869d8068724508f7ebb9205f291c3.png": ("2026-11-03", "农历九月廿五", "小潮"),
    "d11690ead237d7ac2f267f6b555d0b4d.png": ("2026-10-31", "农历九月廿二", "小潮"),
    "f79e5f7cf8621a982bb78736ccb58230.png": ("2026-11-02", "农历九月廿四", "小潮"),
}

PERIOD_QUALITY = {
    "历史存档": "MODEL_ARCHIVE_NOT_FIELD_MEASURED",
    "当日滚动": "MODEL_NOWCAST_NOT_FIELD_MEASURED",
    "未来预报": "FORECAST_DO_NOT_USE_AS_OBSERVATION",
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def excel_date(serial):
    return datetime.date(1899, 12, 30) + datetime.timedelta(days=int(float(serial)))


def excel_time(frac):
    sec = round(float(frac) * 86400)
    return datetime.timedelta(seconds=sec)


def read_wind_rows():
    z = zipfile.ZipFile(WIND_SRC)
    ss = ["".join(t.text or "" for t in si.iter(M + "t"))
          for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(M + "si")]
    meta = {si: ss[i] for i, si in enumerate([])}  # 保留结构，未使用
    sh = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in sh.iter(M + "row"):
        c = {}
        for cell in row.findall(M + "c"):
            ref, t, v = cell.get("r"), cell.get("t"), cell.find(M + "v")
            val = "" if v is None else v.text
            if t == "s" and val:
                val = ss[int(val)]
            c["".join(ch for ch in ref if ch.isalpha())] = val
        rows.append((int(row.get("r")), c))
    return rows, ss


def main():
    os.makedirs(OUT_WIND, exist_ok=True)
    os.makedirs(OUT_TIDE, exist_ok=True)
    rows, ss = read_wind_rows()

    header = [
        "observation_datetime_local", "observation_datetime_utc", "variable", "value", "unit",
        "latitude_deg", "longitude_deg", "station_id", "source_name", "source_url",
        "source_type", "period_flag", "quality_flag", "is_field_observation",
        "original_file", "original_row", "original_date_serial", "original_time_fraction", "note",
    ]
    out_path = os.path.join(OUT_WIND, "wind_hourly_20261030_20261110_PREPROCESSED.csv")
    stats = {"total": 0, "by_period": {}, "values": [], "dates": set()}
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for rn, c in rows:
            if rn < 8 or not c.get("A"):
                continue
            d = excel_date(c["A"])
            td = excel_time(c["B"])
            local = datetime.datetime.combine(d, datetime.time()) + td
            utc = local - datetime.timedelta(hours=8)
            period = c.get("D", "")
            stats["total"] += 1
            stats["by_period"][period] = stats["by_period"].get(period, 0) + 1
            stats["dates"].add(d.isoformat())
            stats["values"].append(float(c["C"]))
            w.writerow([
                local.strftime("%Y-%m-%d %H:%M:%S"), utc.strftime("%Y-%m-%d %H:%M:%S"),
                "wind_speed_10m", c["C"], "m/s",
                "27.87346", "121.11486", "UNKNOWN",
                "Open-Meteo (数值气象模型)", "https://open-meteo.com/en/docs",
                "NUMERICAL_WEATHER_MODEL", period, PERIOD_QUALITY.get(period, "UNKNOWN"),
                "NO",
                os.path.basename(WIND_SRC), rn, c["A"], c["B"],
                "原表自述：历史时段也不是现场实测；本行为预处理副本，非 S05 正式导入批次",
            ])
    print("WIND rows:", stats["total"])
    print("WIND period:", stats["by_period"])
    print("WIND dates:", len(stats["dates"]), min(stats["dates"]), max(stats["dates"]))
    print("WIND min/max/mean:", min(stats["values"]), max(stats["values"]),
          round(sum(stats["values"]) / len(stats["values"]), 4))
    print("WIND out:", out_path)
    print("WIND sha256:", sha256(WIND_SRC))

    inv_path = os.path.join(OUT_TIDE, "tide_image_inventory.csv")
    with open(inv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image_file", "date", "lunar", "tide_type", "unit",
                    "value_available", "datum", "station", "source", "sha256",
                    "file_size_bytes", "limitation"])
        for name in sorted(TIDE_META):
            p = os.path.join(UNZIP, name)
            d, lunar, ttype = TIDE_META[name]
            w.writerow([
                name, d, lunar, ttype, "cm（潮高）",
                "NO（仅曲线截图，无数值表）", "UNKNOWN", "洞头（站点未细化）", "UNKNOWN",
                sha256(p) if os.path.exists(p) else "UNZIP_MISSING",
                os.path.getsize(p) if os.path.exists(p) else "",
                "禁止图像估读产生伪精确值；须索取原始数值文件或可核验来源",
            ])
    print("TIDE images:", len(TIDE_META))
    print("TIDE out:", inv_path)
    print("TIDE zip sha256:", sha256(TIDE_SRC))

    print("--- 归档资料 SHA-256 ---")
    for rel in [
        "00_PROJECT_SPEC/01_MASTER_SPEC_FINAL.md",
        "00_PROJECT_SPEC/02_CODEX_EXECUTION_GUIDE_FINAL.md",
        "00_PROJECT_SPEC/03_CODEX_STAGE_TASKS_FINAL.md",
        "00_PROJECT_SPEC/_source/02_CODEX_EXECUTION_GUIDE_FINAL.md.docx",
        "00_PROJECT_SPEC/_source/03_CODEX_STAGE_TASKS_FINAL.md.docx",
        "12_DOCUMENTATION/fishery_development_plan_20261114.html.temp",
    ]:
        p = os.path.join(ROOT, rel)
        print(sha256(p), os.path.getsize(p), rel)


if __name__ == "__main__":
    main()
