# -*- coding: utf-8 -*-
"""各环呼吸 v3 —— "过零点采样 + 梯度换算"(对低码率/模糊边缘最稳)。

原理: 环边缘呼吸位移 Δr 会让固定在边缘最陡处的像素亮度变化 ΔI = |dI/dr|·Δr。
      所以不需要找边缘, 只需:
        1. 在时间平均剖面上, 于每个环预期边缘附近自动取 |梯度| 最大点 (自动适配不同素材)
        2. 逐帧记录该点亮度 → 正弦拟合 → ΔI 振幅与相位
        3. Δr = ΔI / |dI/dr|,  振幅% = Δr/r_edge
      模糊只会让 |dI/dr| 变小, ΔI 与 |dI/dr| 同步变化, 比值 Δr 基本不受影响。

先用旧素材(高码率)验证该方法能否重现 v1 结果(±10.11/6.29/5.99/4.63%), 再看新素材。

用法: python scripts/_measure_v3.py --video <mp4> --align <json> [--dur 9] [--fps 60] [--ss 0]
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

# 环, 预期边缘 u, 搜索半宽
RINGS = [
    ("深眼外缘",   0.150, 0.100),
    ("蓝瞳外缘",   0.315, 0.065),
    ("灰紫蓝外缘", 0.465, 0.085),
    ("白环外缘",   0.650, 0.100),
    ("靛蓝外缘",   0.815, 0.065),
    ("外圈蓝外缘", 0.965, 0.085),
]


def stream_frames(video, crop, fps, dur, start=0.0):
    x, y, w, h = crop
    args = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error"]
    if start:
        args += ["-ss", str(start)]
    args += ["-i", str(video)]
    if dur:
        args += ["-t", str(dur)]
    args += ["-vf", f"crop={w}:{h}:{x}:{y},fps={fps}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    nb, i = w * h * 3, 0
    while True:
        buf = p.stdout.read(nb)
        if len(buf) < nb:
            break
        yield i, np.frombuffer(buf, np.uint8).reshape(h, w, 3).astype(np.float32)
        i += 1
    p.stdout.close()
    err = p.stderr.read().decode("utf-8", "replace")
    p.wait()
    if i == 0 and err:
        print("ffmpeg 错误:", err[-600:])


def prof2(im, cxl, cyl, rmax, n_ang=N_ANG):
    """径向平均的 L 与 B-R 剖面"""
    H, W, _ = im.shape
    ang = np.linspace(0, 2 * np.pi, n_ang, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    rs = np.arange(0, rmax, STEP)
    L = np.zeros(len(rs))
    BR = np.zeros(len(rs))
    for i, r in enumerate(rs):
        x = np.clip(np.round(cxl + r * ca).astype(int), 0, W - 1)
        y = np.clip(np.round(cyl + r * sa).astype(int), 0, H - 1)
        q = im[y, x].mean(axis=0)
        L[i] = 0.299 * q[0] + 0.587 * q[1] + 0.114 * q[2]
        BR[i] = q[2] - q[0]
    return rs, L, BR


def smooth(x, k):
    return np.convolve(x, np.ones(k) / k, mode="same")


def fit_sine(ts, y, T):
    w = 2 * np.pi / T
    M = np.column_stack([np.ones_like(ts), np.cos(w * ts), np.sin(w * ts)])
    c, *_ = np.linalg.lstsq(M, y, rcond=None)
    resid = y - M @ c
    return float(c[0]), float(np.hypot(c[1], c[2])), float(np.arctan2(c[2], c[1])), float(resid.std())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--align", required=True)
    ap.add_argument("--dur", type=float, default=9.0)
    ap.add_argument("--fps", type=float, default=60.0)
    ap.add_argument("--ss", type=float, default=0.0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    align = json.load(open(a.align, encoding="utf-8"))
    cx, cy, R = align["cx"], align["cy"], align["R_px"]
    side = int(R * 2.9)
    x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    print(f"{pathlib.Path(a.video).name}  R={R:.2f}px  {a.dur}s@{a.fps}fps ss={a.ss}")

    # 第一遍: 累积时间平均剖面 + 逐帧保存全剖面(内存足够: 540帧×560点×2)
    frames = []
    ts = []
    acc_L = acc_BR = None
    for idx, im in stream_frames(a.video, (x0, y0, side, side), a.fps, a.dur, a.ss):
        rs, L, BR = prof2(im, side / 2, side / 2, R * 1.16)
        frames.append((L, BR))
        acc_L = L if acc_L is None else acc_L + L
        acc_BR = BR if acc_BR is None else acc_BR + BR
        ts.append(idx / a.fps)
    ts = np.array(ts)
    n = len(ts)
    mL, mBR = acc_L / n, acc_BR / n
    u = rs / R
    print(f"采样 {n} 帧, 剖面 {len(rs)} 点\n")

    # 自动选点: 每个环在预期边缘 ±半宽 内取 |梯度| 最大处, 通道取 L/BR 梯度更大者
    gL, gBR = np.gradient(smooth(mL, 9)), np.gradient(smooth(mBR, 9))
    picks = {}
    print(f"{'环':<10}{'采样u':>8}{'通道':>6}{'|dI/dr|':>9}{'边缘r(px)':>10}")
    print("-" * 44)
    for name, u0, half in RINGS:
        m = (u >= u0 - half) & (u <= u0 + half)
        iL = np.argmax(np.abs(gL[m]))
        iB = np.argmax(np.abs(gBR[m]))
        use_L = abs(gL[m][iL]) >= abs(gBR[m][iB])
        i = np.where(m)[0][iL if use_L else iB]
        grad = gL[i] if use_L else gBR[i]
        picks[name] = {"i": int(i), "ch": "L" if use_L else "BR", "grad": float(grad), "u": float(u[i])}
        print(f"{name:<10}{u[i]:>8.4f}{('L' if use_L else 'BR'):>6}{abs(grad):>9.3f}{rs[i]:>10.1f}")

    # 周期精定: 用信号最强(信噪比最高)的环
    def series_of(rec, ch_i=0):
        return np.array([f[ch_i][rec["i"]] for f in frames])

    cands = []
    for name in picks:
        y = series_of(picks[name], 0 if picks[name]["ch"] == "L" else 1)
        for T in np.arange(0.70, 1.20, 0.001):
            rsd = fit_sine(ts, y, T)[3] / (y.std() + 1e-9)
            cands.append((rsd, T, name))
    cands.sort()
    T = cands[0][1]
    print(f"\n周期精定 T={T:.4f}s  (由 {cands[0][2]} 选出, 归一化残差 {cands[0][0]:.4f})\n")

    out = {"video": pathlib.Path(a.video).name, "frames": n, "period_s": round(float(T), 4),
           "R_px": R, "rings": {}}
    hdr = (f"{'环':<10}{'振幅±%':>9}{'Δr(px)':>9}{'边沿r':>9}{'ΔI':>8}{'信噪':>7}")
    print(hdr)
    print("-" * 62)
    ph = {}
    for name, u0, half in RINGS:
        rec = picks[name]
        y = series_of(rec, 0 if rec["ch"] == "L" else 1)
        A0, amp, p, rsd = fit_sine(ts, y, T)
        grad = abs(rec["grad"])
        if grad < 0.02:
            print(f"{name:<10}  梯度太小({grad:.3f}), 跳过")
            continue
        dr = amp / grad                       # 亮度振幅 / 梯度 = 半径振幅(px)
        r_edge = rs[rec["i"]]
        amp_pct = dr / r_edge * 100
        snr = amp / (rsd + 1e-9)
        out["rings"][name] = {
            "sample_u": round(rec["u"], 4), "channel": rec["ch"],
            "r_edge_px": round(float(r_edge), 1), "grad": round(float(grad), 4),
            "dr_px": round(float(dr), 3), "amp_pct": round(float(amp_pct), 2),
            "snr": round(float(snr), 1), "phase_rad": round(p, 4),
            "svg_diam_mean": round(rec["u"] * 200, 2),
        }
        ph[name] = p
        print(f"{name:<10}{amp_pct:>9.2f}{dr:>9.3f}{r_edge:>9.1f}{amp:>8.3f}{snr:>7.1f}")

    if "白环外缘" in ph:
        print("\n相位差(相对白环, 负=更早):")
        for name in ph:
            d = (ph[name] - ph["白环外缘"]) / (2 * np.pi) * T * 1000
            d = (d + T * 500) % (T * 1000) - T * 500
            out["rings"][name]["phase_ms_vs_white"] = round(d, 1)
            print(f"  {name:<10}{d:+7.1f} ms")

    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n-> {a.out}")


main()
