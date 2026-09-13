# -*- coding: utf-8 -*-
"""各环直径/振幅测量 v2 —— 自适应阈值穿越法(对低码率模糊边缘更稳)。

与 v1(梯度极值)的区别:
  每个环先用两侧"平台"实测亮度/色差得到本帧阈值, 再取从内向外**首次穿越**该阈值的半径。
  平台亮度每帧自适应 ⇒ 不受压缩造成的亮度漂移影响; 阈值穿越点比梯度峰值更抗模糊。

口径(所有视频统一): 深眼/蓝瞳/灰紫蓝/白环/外圈蓝; 靛蓝环带因尖齿旋转调制不可测, 跳过。
外圈蓝外缘的亮度方向随背景而变(旧素材: 盘→暗背景 = 下降; 新素材: 盘→亮光晕 = 上升), 用 --outer 切换。

用法:
  python scripts/_measure_v2.py --video <mp4> --align <json> --dur 9 --fps 60 [--ss 0]
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

# 名字, 内平台区间(u), 外平台区间(u), 判据, 穿越方向(True=上升)
RINGS = [
    ("深眼外缘",   (0.04, 0.11), (0.24, 0.27), "L",  True),
    ("蓝瞳外缘",   (0.21, 0.26), (0.33, 0.39), "BR", False),
    ("灰紫蓝外缘", (0.32, 0.39), (0.46, 0.51), "BR", False),
    ("白环外缘",   (0.46, 0.51), (0.68, 0.72), "L",  False),
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


def profile(im, cxl, cyl, rmax):
    H, W, _ = im.shape
    ang = np.linspace(0, 2 * np.pi, N_ANG, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    rs = np.arange(0, rmax, STEP)
    L = np.zeros(len(rs))
    BR = np.zeros(len(rs))
    for i, r in enumerate(rs):
        x = np.clip(np.round(cxl + r * ca).astype(int), 0, W - 1)
        y = np.clip(np.round(cyl + r * sa).astype(int), 0, H - 1)
        p = im[y, x].mean(axis=0)
        L[i] = 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]
        BR[i] = p[2] - p[0]
    k = 9
    ker = np.ones(k) / k
    return rs, np.convolve(L, ker, mode="same"), np.convolve(BR, ker, mode="same")


def cross(rs, sig, R, u_in, u_out, rising):
    u = rs / R
    a = (u >= u_in[0]) & (u <= u_in[1])
    b = (u >= u_out[0]) & (u <= u_out[1])
    if not a.any() or not b.any():
        return np.nan
    thr = (np.median(sig[a]) + np.median(sig[b])) / 2.0
    m = (u > u_in[0]) & (u < u_out[1])
    v, uu = sig[m], u[m]
    cond = v > thr if rising else v < thr
    if not cond.any():
        return np.nan
    return float(uu[int(np.argmax(cond))])


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
    ap.add_argument("--outer", choices=["down", "up"], default="down",
                    help="外圈蓝外缘的亮度方向: down=盘→暗背景, up=盘→亮光晕")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    align = json.load(open(a.align, encoding="utf-8"))
    cx, cy, R = align["cx"], align["cy"], align["R_px"]
    rings = list(RINGS) + [("外圈蓝外缘", (0.92, 0.96), (1.06, 1.12), "L", a.outer == "up")]
    side = int(R * 2.9)
    x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    print(f"{pathlib.Path(a.video).name}  R={R:.2f}px  {a.dur}s@{a.fps}fps  ss={a.ss}")

    series = {r[0]: [] for r in rings}
    ts = []
    for idx, im in stream_frames(a.video, (x0, y0, side, side), a.fps, a.dur, a.ss):
        rs, L, BR = profile(im, side / 2, side / 2, R * 1.16)
        for name, ui, uo, which, rising in rings:
            sig = L if which == "L" else BR
            series[name].append(cross(rs, sig, R, ui, uo, rising))
        ts.append(idx / a.fps)
    ts = np.array(ts)
    n = len(ts)
    print(f"采样 {n} 帧\n")

    # 周期: 用最亮的白环扫描
    yw = np.array(series["白环外缘"], dtype=float)
    m = ~np.isnan(yw)
    best = min(((fit_sine(ts[m], yw[m], T)[3], T) for T in np.arange(0.70, 1.20, 0.0005)))
    T = best[1]
    print(f"周期精定 T={T:.4f}s (残差 {best[0]:.5f})\n")

    out = {"video": pathlib.Path(a.video).name, "frames": n, "period_s": round(float(T), 4),
           "R_px": R, "rings": {}}
    print(f"{'环':<10}{'Ø均值':>8}{'Ø最大':>8}{'Ø最小':>8}{'±%':>7}{'残差%':>7}{'u均值':>8}{'检出':>6}")
    print("-" * 62)
    ph = {}
    for name in series:
        y = np.array(series[name], dtype=float)
        ok = ~np.isnan(y)
        if ok.sum() < n * 0.6:
            print(f"{name:<10}  检出率过低 {ok.sum()}/{n}")
            continue
        A0, amp, p, rsd = fit_sine(ts[ok], y[ok], T)
        rec = {"u_mean": round(A0, 4), "svg_diam_mean": round(A0 * 200, 2),
               "svg_diam_max": round((A0 + amp) * 200, 2), "svg_diam_min": round((A0 - amp) * 200, 2),
               "amp_pct": round(amp / A0 * 100, 2), "resid_pct": round(rsd / A0 * 100, 2),
               "phase_rad": round(p, 4), "valid": int(ok.sum())}
        out["rings"][name] = rec
        ph[name] = p
        print(f"{name:<10}{rec['svg_diam_mean']:>8.2f}{rec['svg_diam_max']:>8.2f}{rec['svg_diam_min']:>8.2f}"
              f"{rec['amp_pct']:>7.2f}{rec['resid_pct']:>7.2f}{rec['u_mean']:>8.4f}{rec['valid']:>6d}")

    if "白环外缘" in ph:
        print("\n相位差(相对白环, 负=更早):")
        for name in series:
            if name not in ph:
                continue
            d = (ph[name] - ph["白环外缘"]) / (2 * np.pi) * T * 1000
            d = (d + T * 500) % (T * 1000) - T * 500
            out["rings"][name]["phase_ms_vs_white"] = round(d, 1)
            print(f"  {name:<10}{d:+7.1f} ms")

    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n-> {a.out}")


main()
