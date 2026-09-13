# -*- coding: utf-8 -*-
"""素材体检: 帧率真实性 / 重复帧率 / 有效帧率 / 呼吸主频。

用法: python scripts/_check_fps.py --video <mp4|mkv> [--ss 5] [--dur 8] [--align <json>]

判据: 相邻帧全图平均绝对差(MAE, 4x 下采样) < 0.5 灰度 → 判为同一帧。
      重复帧率 ~ 视频编码的正常水平(长镜头静止背景) 参考值: 60fps 素材约 15-25%。
"""
import argparse
import json
import pathlib
import subprocess
import sys

import numpy as np

ROOT = pathlib.Path(r"D:\work\fairy_pet")
sys.path.insert(0, str(ROOT / "scripts"))
from video_tool import ffmpeg_exe        # noqa: E402


def stream(src, ss, dur, scale=4):
    args = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", str(ss), "-i", src,
            "-t", str(dur), "-vf", f"scale=iw/{scale}:ih/{scale}", "-pix_fmt", "rgb24",
            "-f", "rawvideo", "-"]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    import re
    probe = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", src], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
    m = re.search(r"(\d{3,4})x(\d{3,4})", probe.stderr or "")
    w, h = (int(m.group(1)) // scale, int(m.group(2)) // scale) if m else (480, 270)
    nb = w * h * 3
    out = []
    while True:
        buf = p.stdout.read(nb)
        if len(buf) < nb:
            break
        out.append(np.frombuffer(buf, np.uint8).reshape(h, w, 3).astype(np.float32))
    p.stdout.close()
    p.wait()
    return out, w, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--ss", type=float, default=5.0)
    ap.add_argument("--dur", type=float, default=8.0)
    ap.add_argument("--align", default=None, help="标定文件: 限定环形核区域并测呼吸主频")
    a = ap.parse_args()

    frames, w, h = stream(a.video, a.ss, a.dur)
    n = len(frames)
    fps = n / a.dur
    print(f"{pathlib.Path(a.video).name}")
    print(f"  读入 {n} 帧 / {a.dur}s → 实际交付 {fps:.1f} fps   ({w * 4}x{h * 4} 下采样分析)")

    # 只统计环形核区域(该区域始终有呼吸动画, 静止背景不会干扰判据)
    reg = np.ones((h, w), bool)
    cxr = cyr = None
    if a.align:
        al = json.load(open(a.align, encoding="utf-8"))
        ys, xs = np.mgrid[0:h, 0:w]
        rr = np.hypot(ys - al["cy"] / 4, xs - al["cx"] / 4)
        reg = rr < (al["R_px"] / 4 * 1.05)
        cxr, cyr = al["cx"] / 4, al["cy"] / 4
    maes = np.array([float(np.abs(frames[i][reg] - frames[i - 1][reg]).mean())
                     for i in range(1, n)])
    q = np.percentile(maes, [0, 5, 10, 25, 50, 75, 90, 100])
    print(f"  环形核区 MAE 分位: min {q[0]:.4f} / 5% {q[1]:.4f} / 25% {q[3]:.4f} / "
          f"中位 {q[4]:.4f} / 75% {q[5]:.4f} / max {q[7]:.3f}")
    print(f"  {'阈值':<10}{'判为重复':>12}{'比例':>9}{'→有效帧率':>12}")
    for th in (0.02, 0.1, 0.5, 1.5):
        dd = int((maes < th).sum())
        print(f"  MAE<{th:<7}{dd:>12}{dd / (n - 1) * 100:>8.1f}%{(n - dd) / a.dur:>11.1f} fps")

    # 逐帧差分的周期性: 帧生成常导致"新帧-复用帧"交替的固定节奏
    if (maes < 0.02).mean() > 0.05:
        idx = np.nonzero(maes < 0.02)[0]
        gaps = np.diff(idx)
        if len(gaps):
            vals, cnt = np.unique(gaps, return_counts=True)
            top = sorted(zip(cnt, vals), reverse=True)[:4]
            print("  重复帧出现间隔(帧): " + ", ".join(f"{v}(×{c})" for c, v in top))

    if cxr:
        m = np.zeros((h, w), bool)
        ys, xs = np.mgrid[0:h, 0:w]
        rr = np.hypot(ys - cyr, xs - cxr)
        m = (rr >= 25) & (rr < 41)
        s = np.array([0.299 * f[:, :, 0][m].mean() + 0.587 * f[:, :, 1][m].mean() +
                      0.114 * f[:, :, 2][m].mean() for f in frames])
        k = 25
        d = s - np.convolve(s, np.ones(k) / k, mode="same")
        d = d[k:-k]
        F = np.abs(np.fft.rfft(d * np.hanning(len(d))))
        fr = np.fft.rfftfreq(len(d), 1 / fps)
        keep = (fr > 0.6) & (fr < 2.5)
        pk = fr[keep][int(np.argmax(F[keep]))]
        print(f"  呼吸主频 {pk:.3f} Hz → 周期 {1 / pk:.3f}s")


main()
