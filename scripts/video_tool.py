"""视频逐帧抽取与拼版。

ffmpeg 二进制来自 imageio-ffmpeg（纯 Python 包，自带，无需系统安装）。

用法:
  # 下载（走 yt-dlp）
  python video_tool.py dl <URL> <输出目录> [--max-h 480]

  # 抽帧
  python video_tool.py frames <视频> <输出目录> [--fps 12] [--ss 0] [--t 6]
                             [--crop x,y,w,h] [--scale W] [--tile 8]

  # 只做拼版（对已有帧目录）
  python video_tool.py tile <帧目录> <输出.png> [--tile 8]
"""
import argparse
import glob
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw


def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def cmd_dl(url, outdir, max_h):
    os.makedirs(outdir, exist_ok=True)
    args = [sys.executable, "-m", "yt_dlp",
            "-f", f"bestvideo[height<={max_h}]+bestaudio/best[height<={max_h}]/best",
            "-o", os.path.join(outdir, "%(title).80s.%(ext)s"),
            "--merge-output-format", "mp4",
            "--no-playlist", "--retries", "3", "--no-warnings",
            url]
    print(" ".join(args))
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout[-3000:] if r.stdout else "")
    if r.returncode != 0:
        print("STDERR:", (r.stderr or "")[-2000:])
    return r.returncode


def cmd_frames(video, outdir, fps, ss, dur, crop, scale, tile):
    os.makedirs(outdir, exist_ok=True)
    for f in glob.glob(os.path.join(outdir, "f_*.png")):
        os.remove(f)
    vf = []
    if crop:
        x, y, w, h = [int(v) for v in crop.split(",")]
        vf.append(f"crop={w}:{h}:{x}:{y}")
    if scale:
        vf.append(f"scale={scale}:-2")
    args = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y"]
    if ss:
        args += ["-ss", str(ss)]
    args += ["-i", video]
    if dur:
        args += ["-t", str(dur)]
    args += ["-vf", ",".join(vf) if vf else "null", "-r", str(fps),
             os.path.join(outdir, "f_%05d.png")]
    print(" ".join(args))
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("ffmpeg 失败:", (r.stderr or "")[-1500:]); return 1
    n = len(glob.glob(os.path.join(outdir, "f_*.png")))
    print(f"抽出 {n} 帧 -> {outdir}")
    if n == 0:
        return 1
    if tile:
        contact_sheet(outdir, os.path.join(outdir, "_sheet.png"), tile,
                      fps=fps, t0=ss or 0)
    return 0


def contact_sheet(frame_dir, out, cols, fps=10, t0=0, label=True):
    files = sorted(glob.glob(os.path.join(frame_dir, "f_*.png")))
    if not files:
        print("没有帧"); return
    ims = [Image.open(f).convert("RGB") for f in files]
    W, H = ims[0].size
    # 缩到单格不超过 260px 宽
    tw = min(W, 260)
    th = max(1, int(H * tw / W))
    rows = (len(ims) + cols - 1) // cols
    out_img = Image.new("RGB", (tw * cols, th * rows), (10, 14, 24))
    d = ImageDraw.Draw(out_img)
    for i, im in enumerate(ims):
        im = im.resize((tw, th), Image.LANCZOS)
        x, y = (i % cols) * tw, (i // cols) * th
        out_img.paste(im, (x, y))
        if label:
            ts = t0 + i / fps
            d.rectangle([x, y, x + 66, y + 14], fill=(0, 0, 0))
            d.text((x + 3, y + 2), f"{ts:5.2f}s", fill=(255, 210, 110))
        d.rectangle([x, y, x + tw - 1, y + th - 1], outline=(40, 52, 78))
    out_img.save(out)
    print(f"拼版 -> {out}  {out_img.width}x{out_img.height}  ({len(ims)} 帧, {cols} 列)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["dl", "frames", "tile", "probe"])
    ap.add_argument("src")
    ap.add_argument("dst", nargs="?")
    ap.add_argument("--fps", type=float, default=10)
    ap.add_argument("--ss", type=float, default=0)
    ap.add_argument("--t", dest="dur", type=float, default=None)
    ap.add_argument("--crop", default=None)
    ap.add_argument("--scale", type=int, default=None)
    ap.add_argument("--tile", type=int, default=0)
    ap.add_argument("--max-h", type=int, default=480)
    a = ap.parse_args()

    if a.mode == "dl":
        sys.exit(cmd_dl(a.src, a.dst or "video", a.max_h))
    if a.mode == "frames":
        sys.exit(cmd_frames(a.src, a.dst or "frames", a.fps, a.ss, a.dur,
                            a.crop, a.scale, a.tile))
    if a.mode == "tile":
        contact_sheet(a.src, a.dst or "_sheet.png", a.tile or 8)
    if a.mode == "probe":
        r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", a.src],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        print((r.stderr or "")[:2500])


if __name__ == "__main__":
    main()
