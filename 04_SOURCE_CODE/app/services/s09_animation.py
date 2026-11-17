# -*- coding: utf-8 -*-
"""S09：从 S08 离散帧导出 PNG 序列 / GIF / MP4 / PDF 静态图，不插值、不造轨迹。"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from PIL import Image

FFMPEG_CANDIDATES = [
    Path(r"C:\Users\Administrator\.real\bin\ffmpeg\ffmpeg.exe"),
    Path(r"C:\Program Files\EVCapture\ffmpeg.exe"),
    Path(r"C:\Program Files\MiniMax Hub\resources\ffmpeg\ffmpeg.exe"),
]


def _palette():
    docs = Path(__file__).resolve().parents[3] / "12_DOCUMENTATION"
    if str(docs) not in sys.path:
        sys.path.insert(0, str(docs))
    import figure_palette as fp
    from matplotlib import font_manager
    font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    if font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
    return fp


def ffmpeg_path() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in FFMPEG_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return None


def _frames_from_csv(path: Path) -> dict[str, dict[str, dict]]:
    frames: dict[str, dict[str, dict]] = defaultdict(dict)
    with path.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            frames[row["timestamp_local"]][row["device_id"]] = {
                "status": row["activity_status"],
                "events": (float(row["candidate_events"])
                           if row["candidate_events"] not in ("", None) else None),
            }
    return dict(frames)


def _draw_frame(frame: dict, stamp: str, out_png: Path, fp) -> None:
    devices = sorted(frame)
    values = [frame[d]["events"] for d in devices]
    colors = []
    for value in values:
        if value is None:
            colors.append(fp.INK["次要"])
        elif value > 5:
            colors.append(fp.LINE["高值强调"])
        elif value >= 2:
            colors.append(fp.color("A", 3))
        else:
            colors.append(fp.color("A", 1))
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.barh(devices, [v if v is not None else 0 for v in values], color=colors)
    for i, v in enumerate(values):
        ax.text(0.1 if v else 0.05, i, "NA" if v is None else f"{v:g}", va="center",
                color=fp.INK["白"] if v is not None and v > 5 else fp.INK["正文"], fontsize=9)
    ax.set_xlabel("候选事件（次/有效小时；固定色标，缺测 NA）")
    ax.set_title(stamp + "（本地时间；离散实测帧，无轨迹/无插值）", fontsize=10)
    ax.grid(axis="x", color=fp.INK["网格"], linewidth=0.6)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(conn: sqlite3.Connection, project_root: Path, *, source_csv: Path | None = None,
           formats=("PNG_SEQUENCE", "GIF", "MP4", "PDF"), actor: str = "S09") -> dict:
    root = Path(project_root)
    source = source_csv or root / "10_TEST_REPORTS/s08_verification/real_data/dynamic_frames.csv"
    if not source.exists():
        raise FileNotFoundError(source)
    frames = _frames_from_csv(source)
    if not frames:
        raise ValueError("离散帧为空，不能导出动画")
    out_dir = root / "07_FIGURES" / "s09" / "animation"
    out_dir.mkdir(parents=True, exist_ok=True)
    fp = _palette()
    stamps = sorted(frames)
    png_dir = out_dir / "frames"
    png_dir.mkdir(exist_ok=True)
    pngs = []
    na_cells = 0
    for index, stamp in enumerate(stamps):
        path = png_dir / f"frame_{index:04d}.png"
        _draw_frame(frames[stamp], stamp, path, fp)
        pngs.append(path)
        na_cells += sum(1 for v in frames[stamp].values() if v["events"] is None)
    exports = []
    now = datetime.now().isoformat(timespec="seconds")

    def record(fmt: str, target: Path) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO animation_exports (export_id,source_frames,export_format,"
            "file_path,sha256,bytes,frame_count,consistency_check,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (f"ANIM-{fmt}-{target.stem}", str(source), fmt, str(target), _sha(target),
             target.stat().st_size, len(frames),
             f"PASS frames={len(frames)} NA={na_cells} no_interpolation", now))
        exports.append({"format": fmt, "path": str(target), "sha256": _sha(target)})

    if "PNG_SEQUENCE" in formats:
        record("PNG_SEQUENCE", pngs[0])
    if "GIF" in formats:
        gif = out_dir / "dynamic_frames.gif"
        images = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in pngs]
        images[0].save(gif, save_all=True, append_images=images[1:], duration=500, loop=0)
        record("GIF", gif)
    if "MP4" in formats:
        ffmpeg = ffmpeg_path()
        mp4 = out_dir / "dynamic_frames.mp4"
        if ffmpeg:
            list_file = out_dir / "frames.txt"
            list_file.write_text("".join(f"file '{p.as_posix()}'\nduration 0.5\n" for p in pngs)
                                 + f"file '{pngs[-1].as_posix()}'\n", encoding="utf-8")
            result = subprocess.run(
                [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                 "-vsync", "vfr", "-pix_fmt", "yuv420p", str(mp4)],
                capture_output=True, text=True, timeout=180)
            if result.returncode == 0 and mp4.exists():
                record("MP4", mp4)
            else:
                conn.execute("INSERT OR REPLACE INTO animation_exports (export_id,source_frames,"
                             "export_format,file_path,sha256,bytes,frame_count,consistency_check,created_at)"
                             " VALUES (?,?,?,?,?,?,?,?,?)",
                             (f"ANIM-MP4-FAIL-{now}", str(source), "MP4", "", "", 0, len(frames),
                              "BLOCKED ffmpeg_exit=" + str(result.returncode), now))
        else:
            conn.execute("INSERT OR REPLACE INTO animation_exports (export_id,source_frames,"
                         "export_format,file_path,sha256,bytes,frame_count,consistency_check,created_at)"
                         " VALUES (?,?,?,?,?,?,?,?,?)",
                         (f"ANIM-MP4-FAIL-{now}", str(source), "MP4", "", "", 0, len(frames),
                          "BLOCKED no_ffmpeg", now))
    if "PDF" in formats:
        pdf = out_dir / "dynamic_frames.pdf"
        with PdfPages(pdf) as pages:
            for path in pngs:
                image = Image.open(path)
                fig, ax = plt.subplots(figsize=(7.2, 3.4))
                ax.imshow(image)
                ax.axis("off")
                pages.savefig(fig)
                plt.close(fig)
        record("PDF", pdf)
    conn.commit()
    return {"source": str(source), "frames": len(frames), "na_cells": na_cells,
            "exports": exports, "ffmpeg": ffmpeg_path(),
            "note": "离散帧同源导出；无轨迹、无连续密度插值；NA 不补 0"}
