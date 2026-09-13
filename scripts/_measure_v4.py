# -*- coding: utf-8 -*-
"""各环呼吸 v4 —— ZNCC 亚像素位移估计(数字图像相关法)。

原理: 把每个环边缘附近的一小段径向剖面当作"图案", 与时间平均剖面(参考)做
      零均值归一化互相关(ZNCC), 峰值位置即该帧边缘的亚像素位移。
      归一化 ⇒ 对亮度增益/偏置的整体漂移免疫; 只用"图案形状"定位边缘。

先用旧素材验证能否重现 v1 的 ±10.11/6.29/5.99/4.63%。

用法: python scripts/_measure_v4.py --video <mp4> --align <json> [--dur 9] [--fps 60] [--ss 0]
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
WIN_HALF_PX = 12.0          # 相关窗口半宽(px)
MAX_SHIFT_PX = 7.0          # 位移搜索范围(px)
SHIFT_STEP = 0.25           # 位移搜索步长(px)

RINGS = [
    ("深眼外缘",   0.184, 0.050),
    ("蓝瞳外缘",   0.281, 0.045),
    ("灰紫蓝外缘", 0.415, 0.050),
    ("白环外缘",   0.622, 0.055),
    ("靛蓝外缘",   0.740, 0.045),
    ("外圈蓝外缘", 1.006, 0.040),
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


def prof(im, cxl, cyl, rmax):
    H, W, _ = im.shape
    ang = np.linspace(0, 2 * np.pi, N_ANG, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    rs = np.arange(0, rmax, STEP)
    out = np.zeros(len(rs))
    for i, r in enumerate(rs):
        x = np.clip(np.round(cxl + r * ca).astype(int), 0, W - 1)
        y = np.clip(np.round(cyl + r * sa).astype(int), 0, H - 1)
        q = im[y, x].mean(axis=0)
        out[i] = 0.299 * q[0] + 0.587 * q[1] + 0.114 * q[2]
    return rs, out


def smooth(x, k=5):
    return np.convolve(x, np.ones(k) / k, mode="same")


def zncc(a, b):
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 1e-9 else 0.0


def shift_of(ref_win, cur_win, shifts):
    """返回使 ref 平移 d 后与 cur 最匹配的 d (抛物线插值到亚像素)"""
    idx = np.arange(len(ref_win), dtype=float)
    cs = np.array([zncc(np.interp(idx, idx - d, ref_win), cur_win) for d in shifts])
    i = int(np.argmax(cs))
    if 0 < i < len(shifts) - 1:
        y0, y1, y2 = cs[i - 1], cs[i], cs[i + 1]
        den = y0 - 2 * y1 + y2
        if abs(den) > 1e-12:
            return float(shifts[i] + 0.5 * (y0 - y2) / den * SHIFT_STEP), float(cs[i])
    return float(shifts[i]), float(cs[i])


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

    profs, ts = [], []
    acc = None
    for idx, im in stream_frames(a.video, (x0, y0, side, side), a.fps, a.dur, a.ss):
        rs, p = prof(im, side / 2, side / 2, R * 1.16)
        profs.append(p)
        acc = p if acc is None else acc + p
        ts.append(idx / a.fps)
    ts = np.array(ts)
    n = len(ts)
    P = np.array(profs)
    ref = smooth(acc / n, 5)
    u = rs / R
    print(f"采样 {n} 帧, 剖面 {len(rs)} 点 (0.5px 步长)\n")

    shifts = np.arange(-MAX_SHIFT_PX, MAX_SHIFT_PX + 1e-9, SHIFT_STEP)
    series, meta = {}, {}
    for name, u0, half in RINGS:
        c = u0 * R
        lo = np.searchsorted(rs, c - WIN_HALF_PX)
        hi = np.searchsorted(rs, c + WIN_HALF_PX)
        ref_win = ref[lo:hi]
        d, cc = [], []
        for p in P:
            dd, ccc = shift_of(ref_win, smooth(p, 5)[lo:hi], shifts)
            d.append(dd)
            cc.append(ccc)
        series[name] = np.array(d)
        meta[name] = {"r_edge_px": float(c), "u": float(u0),
                      "corr_mean": float(np.mean(cc)), "corr_min": float(np.min(cc))}

    # 周期精定: 用平均相关系数最高的环
    order = sorted(meta, key=lambda k: -meta[k]["corr_mean"])
    yw = series[order[0]]
    T = min(((fit_sine(ts, yw, T_)[3], T_) for T_ in np.arange(0.70, 1.20, 0.0005)))[1]
    print(f"周期精定 T={T:.4f}s (由 {order[0]} 选出, 平均相关 {meta[order[0]]['corr_mean']:.3f})\n")

    out = {"video": pathlib.Path(a.video).name, "frames": n, "period_s": round(float(T), 4),
           "R_px": R, "method": "ZNCC subpixel shift", "rings": {}}
    hdr = f"{'环':<10}{'Δr振幅(px)':>12}{'振幅±%':>9}{'平均相关':>10}{'信噪':>8}{'相位ms':>9}"
    print(hdr)
    print("-" * 60)
    ph = {}
    for name, u0, half in RINGS:
        y = series[name]
        A0, amp, p, rsd = fit_sine(ts, y, T)
        r_edge = meta[name]["r_edge_px"]
        amp_pct = amp / r_edge * 100
        snr = amp / (rsd + 1e-9)
        out["rings"][name] = {"dr_amp_px": round(amp, 3), "amp_pct": round(float(amp_pct), 2),
                              "corr_mean": round(meta[name]["corr_mean"], 3),
                              "snr": round(float(snr), 1), "resid_px": round(rsd, 3),
                              "svg_diam_mean": round(u0 * 200, 2), "phase_rad": round(p, 4)}
        ph[name] = p
        print(f"{name:<10}{amp:>12.3f}{amp_pct:>9.2f}{meta[name]['corr_mean']:>10.3f}"
              f"{snr:>8.1f}{0.0:>9.0f}")

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
