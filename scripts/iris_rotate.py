"""量化 Fairy 虹膜的旋转：用相邻帧的角度亮度剖面的互相关求角位移。

思路：虹膜内部的螺旋/钩状结构在旋转。取某个半径上的角度亮度剖面 A(θ)，
相邻帧互相关即可求出这一帧转了多少度；累加得到总转角曲线。

用法: python iris_rotate.py <帧目录> [--r 0.30] [--cx N] [--cy N] [--half 58]
"""
import argparse
import glob
import os

import numpy as np
from PIL import Image


def profile(a, cx, cy, r, n=1440):
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    L = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
    H, W = L.shape
    xs = np.clip(np.round(cx + r * np.cos(th)).astype(int), 0, W - 1)
    ys = np.clip(np.round(cy + r * np.sin(th)).astype(int), 0, H - 1)
    return L[ys, xs]


def shift_deg(p0, p1):
    """p1 相对 p0 转了多少度（正 = 顺时针，与图像坐标一致）。"""
    n = len(p0)
    a = p0 - p0.mean()
    b = p1 - p1.mean()
    # 循环互相关，用 FFT
    c = np.fft.ifft(np.fft.fft(b) * np.conj(np.fft.fft(a))).real
    k = int(np.argmax(c))
    if k > n // 2:
        k -= n
    return k * 360.0 / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames")
    ap.add_argument("--r", type=float, default=0.30, help="采样半径（核心半径的倍数）")
    ap.add_argument("--cx", type=float, default=None)
    ap.add_argument("--cy", type=float, default=None)
    ap.add_argument("--R", type=float, default=None, help="核心半径（像素）")
    ap.add_argument("--fps", type=float, default=12)
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.frames, "f_*.png")))
    if not files:
        print("没有帧"); return
    im0 = np.asarray(Image.open(files[0]).convert("RGB")).astype(np.float32)
    H, W, _ = im0.shape

    cx = a.cx if a.cx is not None else W / 2
    cy = a.cy if a.cy is not None else H / 2
    if a.R is not None:
        R = a.R
    else:
        L = 0.299 * im0[:, :, 0] + 0.587 * im0[:, :, 1] + 0.114 * im0[:, :, 2]
        R = np.sqrt((L > 120).sum() / np.pi)
    r = a.r * R
    print(f"帧 {len(files)}  采样半径 r={r:.1f}px (R={R:.1f}, u={a.r})")

    prev = None
    total = 0.0
    rows = []
    for i, f in enumerate(files):
        arr = np.asarray(Image.open(f).convert("RGB")).astype(np.float32)
        p = profile(arr, cx, cy, r)
        if prev is not None:
            d = shift_deg(prev, p)
            total += d
        else:
            d = 0.0
        t = i / a.fps
        rows.append((i, t, d, total))
        prev = p

    print(f"\n{'#':>4} {'t(s)':>7} {'单帧Δ':>8} {'累计':>9}")
    for i, t, d, tot in rows:
        if i % max(1, len(rows) // 25) == 0 or i == len(rows) - 1:
            print(f"{i:4d} {t:7.3f} {d:+8.2f} {tot:+9.2f}")

    tot = np.array([x[3] for x in rows])
    span = tot[-1] - tot[0]
    print(f"\n累计总转角 {span:+.1f}°  历时 {rows[-1][1]:.3f}s")
    if abs(span) > 1e-6:
        print(f"平均转速 {span / rows[-1][1]:+.1f} °/s  →  一圈约 {abs(360/(span/rows[-1][1])):.2f}s")
    steps = np.array([x[2] for x in rows[1:]])
    print(f"单帧步进 中位 {np.median(steps):+.2f}°  "
          f"（若接近 {360/a.fps:.1f}° 的整数分之一，说明转速快到发生了混叠）")


if __name__ == "__main__":
    main()
