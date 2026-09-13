# -*- coding: utf-8 -*-
"""环间相位 v5 —— 窄环带空间平均 + 单频 DFT 相位。

相比 v3 的单点采样: 取横跨每个边缘的一条窄环带(宽 0.06u)做径向平均,
信号来源是"边缘扫过带区", 空间平均把噪声压低 √N 倍, 且不依赖单点梯度估计。
相位用精确频率 f0 的单频 DFT 求(arg Σ x(t)·e^{-i2πf0t}), 不受 FFT bin 限制。

用法: python scripts/_band_phase.py --video <mp4> --align <json> [--ss 0] [--dur 9] [--fps 120]
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

N_ANG, STEP = 360, 0.5

# 每个边缘对应的窄环带 (u 中心, 半宽)
BANDS = [
    ("深眼边缘带",   0.180, 0.030),
    ("蓝瞳边缘带",   0.290, 0.030),
    ("灰紫蓝边缘带", 0.410, 0.030),
    ("白环边缘带",   0.630, 0.030),
    ("外圈蓝边缘带", 1.000, 0.030),
]


def frames(src, align, ss, dur, fps):
    cx, cy, R = align["cx"], align["cy"], align["R_px"]
    side = int(R * 2.9)
    x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    args = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", str(ss), "-i", src,
            "-t", str(dur), "-vf", f"crop={side}:{side}:{x0}:{y0},fps={fps}",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    nb, i = side * side * 3, 0
    ang = np.linspace(0, 2 * np.pi, N_ANG, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    rs = np.arange(0, R * 1.16, STEP)
    u = rs / R
    band_idx = {}
    for name, u0, hw in BANDS:
        band_idx[name] = np.nonzero((u >= u0 - hw) & (u <= u0 + hw))[0]
    L = {k: [] for k in band_idx}
    while True:
        buf = p.stdout.read(nb)
        if len(buf) < nb:
            break
        im = np.frombuffer(buf, np.uint8).reshape(side, side, 3).astype(np.float32)
        prof = np.zeros(len(rs))
        for j, r in enumerate(rs):
            x = np.clip(np.round(side / 2 + r * ca).astype(int), 0, side - 1)
            y = np.clip(np.round(side / 2 + r * sa).astype(int), 0, side - 1)
            q = im[y, x].mean(axis=0)
            prof[j] = 0.299 * q[0] + 0.587 * q[1] + 0.114 * q[2]
        for k, ix in band_idx.items():
            L[k].append(prof[ix].mean())
        i += 1
    p.stdout.close()
    p.wait()
    return {k: np.array(v) for k, v in L.items()}, i


def dft_phase(ts, x, f0):
    """精确频率 f0 处的单频 DFT 幅度与相位(先去均值与线性趋势)"""
    A = np.column_stack([np.ones_like(ts), ts - ts.mean()])
    c, *_ = np.linalg.lstsq(A, x, rcond=None)
    y = x - A @ c
    w = np.exp(-1j * 2 * np.pi * f0 * ts)
    X = (y * w).sum()
    return float(np.abs(X)) / len(ts) * 2, float(np.angle(X))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--align", required=True)
    ap.add_argument("--ss", type=float, default=0.0)
    ap.add_argument("--dur", type=float, default=9.0)
    ap.add_argument("--fps", type=float, default=120.0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    align = json.load(open(a.align, encoding="utf-8"))
    L, n = frames(a.video, align, a.ss, a.dur, a.fps)
    fps = n / a.dur
    ts = np.arange(n) / fps
    print(f"{pathlib.Path(a.video).name}  {len(ts)} 帧 {ts[-1]:.2f}s @{fps:.0f}fps")

    # 周期精定: 白环边缘带的时域波形做正弦扫描
    y = L["白环边缘带"]
    A0 = np.column_stack([np.ones_like(ts), ts - ts.mean()])

    def resid_at(f0):
        c, *_ = np.linalg.lstsq(np.column_stack([A0, np.cos(2 * np.pi * f0 * ts),
                                                 np.sin(2 * np.pi * f0 * ts)]), y, rcond=None)
        M = np.column_stack([np.ones_like(ts), ts - ts.mean(), np.cos(2 * np.pi * f0 * ts),
                             np.sin(2 * np.pi * f0 * ts)])
        return float((y - M @ c).std())
    fs = np.arange(1 / 0.95, 1 / 0.80, 0.00005)
    rs_ = np.array([resid_at(f) for f in fs])
    f0 = float(fs[int(np.argmin(rs_))])
    print(f"周期精定 f0={f0:.4f} Hz → T={1 / f0:.4f}s (残差 {rs_.min():.4f})\n")

    out = {"video": pathlib.Path(a.video).name, "frames": len(ts), "f0": round(f0, 5),
           "T": round(1 / f0, 5), "bands": {}}
    print(f"{'环带':<14}{'调制幅度':>10}{'信噪':>8}{'相位ms(相对白环)':>18}")
    print("-" * 52)
    ph0 = None
    vals = {}
    for name, u0, hw in BANDS:
        x = L[name]
        amp, p = dft_phase(ts, x, f0)
        # 噪声水平: 去掉 f0 分量后的残差
        M = np.column_stack([np.ones_like(ts), ts - ts.mean(), np.cos(2 * np.pi * f0 * ts),
                             np.sin(2 * np.pi * f0 * ts)])
        c, *_ = np.linalg.lstsq(M, x, rcond=None)
        noise = float((x - M @ c).std())
        snr = amp / (noise * np.sqrt(2) + 1e-9)
        vals[name] = (amp, p, snr)
        if name == "白环边缘带":
            ph0 = p
    for name, u0, hw in BANDS:
        amp, p, snr = vals[name]
        d = (p - ph0) / (2 * np.pi) / f0 * 1000
        d = (d + 500 / f0) % (1000 / f0) - 500 / f0
        out["bands"][name] = {"amp": round(amp, 3), "phase_ms_vs_white": round(d, 1),
                              "snr": round(snr, 2), "u_center": u0}
        print(f"{name:<14}{amp:>10.3f}{snr:>8.2f}{d:>18.1f}")

    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n-> {a.out}")


main()
