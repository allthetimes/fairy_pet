"""精测呼吸曲线的分段时长 (谷停/上升/峰停/下降), 60fps 原生采样。

原理: 对白环外缘半径序列 w(t) 归一化后逐周期测量:
  低/高阈值 = m0 + 15%/85% * (m1-m0)
  上升 = 低阈值最后一次上穿 -> 高阈值首次上穿
  峰停 = 高阈值首次上穿 -> 高阈值最后一次下穿
  下降 = 高阈值最后一次下穿 -> 低阈值首次下穿
  谷停 = 周期剩余部分
与当前 SMIL 动画在同一阈值口径下的 plateau (13% / 30%) 对比后给出新 keyTimes。

用法: python breath_curve.py <视频> [--dur 8]
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from video_tool import ffmpeg_exe  # noqa: E402


def run(args):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("CMD 失败:", " ".join(args)); print((r.stderr or "")[-1200:]); sys.exit(1)
    return r


def bilin_profile(im, cxl, cyl, rmax, n_ang=360, step=0.5):
    H, W, _ = im.shape
    ang = np.linspace(0, 2 * np.pi, n_ang, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    rs = np.arange(0, rmax, step)
    prof = np.zeros((len(rs), 3))
    for i, r in enumerate(rs):
        x = cxl + r * ca; y = cyl + r * sa
        xi = np.clip(np.floor(x).astype(int), 0, W - 2)
        yi = np.clip(np.floor(y).astype(int), 0, H - 2)
        fx = np.clip(x - xi, 0, 1)[:, None]; fy = np.clip(y - yi, 0, 1)[:, None]
        p = (im[yi, xi] * (1 - fx) * (1 - fy) + im[yi, xi + 1] * fx * (1 - fy) +
             im[yi + 1, xi] * (1 - fx) * fy + im[yi + 1, xi + 1] * fx * fy)
        prof[i] = p.mean(axis=0)
    return rs, prof


def cross_edge(u, L, scan_lo, scan_hi, inner_u, outer_u):
    mi = (u >= inner_u[0]) & (u <= inner_u[1])
    mo = (u >= outer_u[0]) & (u <= outer_u[1])
    a = L[mi].mean(); b = L[mo].mean()
    thr = (a + b) / 2
    m = (u >= scan_lo) & (u <= scan_hi)
    idx = np.where(m)[0]
    for j in range(len(idx) - 1):
        i0, i1 = idx[j], idx[j + 1]
        if L[i0] > thr >= L[i1]:
            return float(u[i0] + (L[i0] - thr) / (L[i0] - L[i1]) * (u[i1] - u[i0]))
    return None


def smooth(x, k=5):
    return np.convolve(x, np.ones(k) / k, mode="same")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--dur", type=float, default=8.0)
    a = ap.parse_args()

    ALIGN = json.load(open("dev/align_data.json", encoding="utf-8"))
    cx, cy, R = ALIGN["cx"], ALIGN["cy"], ALIGN["R_px"]
    T = ALIGN["T_meas"]

    tmpdir = "_bc_frames"
    if os.path.exists(tmpdir):
        shutil.rmtree(tmpdir)
    os.makedirs(tmpdir)
    side = 540
    x0 = int(cx - side / 2); y0 = int(cy - side / 2)
    run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
         "-t", str(a.dur), "-i", a.video,
         "-vf", f"crop={side}:{side}:{x0}:{y0}",
         "-r", "60", os.path.join(tmpdir, "f_%05d.png")])
    files = sorted(glob.glob(os.path.join(tmpdir, "f_*.png")))
    fps = len(files) / a.dur
    print(f"帧: {len(files)} 张 ({fps:.1f}fps)")

    CL = side / 2
    ts, us = [], []
    for i, fp in enumerate(files):
        im = np.asarray(Image.open(fp).convert("RGB")).astype(np.float32)
        rs, prof = bilin_profile(im, CL, CL, 0.75 * R)
        L = smooth(0.299 * prof[:, 0] + 0.587 * prof[:, 1] + 0.114 * prof[:, 2], 7)
        u = rs / R
        e = cross_edge(u, L, 0.58, 0.70, (0.52, 0.57), (0.67, 0.73))
        if e is not None:
            ts.append(i / fps); us.append(e)
    ts = np.array(ts); us = np.array(us)
    print(f"有效点: {len(us)}")

    # 归一化 + 逐周期分段
    m0, m1 = np.percentile(us, 3), np.percentile(us, 97)
    w = (us - m0) / (m1 - m0)
    lo_t, hi_t = 0.15, 0.85
    above_hi = w > hi_t
    above_lo = w > lo_t

    # 找峰 (峰停段的中心): above_hi 的连续段
    peaks = []
    in_pk = False
    for i, v in enumerate(above_hi):
        if v and not in_pk:
            s = i; in_pk = True
        elif not v and in_pk:
            peaks.append(((s + i - 1) / 2, s, i - 1)); in_pk = False
    if in_pk:
        peaks.append(((s + len(w) - 1) / 2, s, len(w) - 1))
    print(f"检出峰段: {len(peaks)} 个")

    segs = []
    for k in range(len(peaks) - 1):
        p0s, p0e = peaks[k][1], peaks[k][2]
        p1s, p1e = peaks[k + 1][1], peaks[k + 1][2]
        # 上升: p0 峰之前的低阈值上穿点 (在 p0s 前找 w 从 <lo 到 >lo)
        rise_start = None
        for i in range(p0s, 0, -1):
            if not above_lo[i]:
                rise_start = i + 1; break
        if rise_start is None:
            continue
        # 峰停 = p0e -> 下一次低于 hi 之前的最后高电平点
        # 实际: 峰停结束 = p0e (最后一次 >hi), 下降 = p0e 之后首次 <lo
        fall_end = None
        for i in range(p0e + 1, p1s + len(w) and len(w)):
            if not above_lo[i]:
                fall_end = i; break
        if fall_end is None:
            continue
        # 上升结束 = p0s (首次 >hi)
        # 下降开始 = p0e
        Tcyc = ts[fall_end + 1] - ts[rise_start - 1] if False else None
        # 用相邻谷-谷估计周期: 取 rise_start 到 fall_end 加上剩余谷
        # 下一周期上升起点:
        nxt_rise = None
        for i in range(fall_end, len(w)):
            if above_lo[i] and not above_lo[i - 1]:
                nxt_rise = i; break
        if nxt_rise is None:
            continue
        cyc = ts[nxt_rise] - ts[rise_start]
        if not (0.6 * T < cyc < 1.4 * T):
            continue
        t_rise = ts[p0s] - ts[rise_start]
        t_peak = ts[p0e] - ts[p0s]
        t_fall = ts[fall_end] - ts[p0e]
        t_valley = cyc - t_rise - t_peak - t_fall
        segs.append((t_rise / cyc, t_peak / cyc, t_fall / cyc, t_valley / cyc, cyc))

    segs = np.array(segs)
    print(f"\n有效周期: {len(segs)} 个")
    print(f"{'段':<6} {'均值%':>8} {'std':>7}")
    names = ["上升", "峰停", "下降", "谷停"]
    for j, nm in enumerate(names):
        print(f"{nm:<6} {segs[:, j].mean() * 100:8.2f} {segs[:, j].std() * 100:7.2f}")
    print(f"平均周期: {segs[:, 4].mean():.4f}s")

    # 当前 SMIL 同口径 plateau: 谷 13%, 峰 31% (0.56->0.87)
    print(f"\n当前 SMIL (同口径 15%/85% 阈值): 谷停 13.0%, 峰停 31.0%")
    new = {
        "rise": round(float(segs[:, 0].mean()), 4),
        "peak": round(float(segs[:, 1].mean()), 4),
        "fall": round(float(segs[:, 2].mean()), 4),
        "valley": round(float(segs[:, 3].mean()), 4),
        "cycles": len(segs),
        "period": round(float(segs[:, 4].mean()), 4),
    }
    print("建议 keyTimes 分段:", new)
    with open("dev/breath_curve.json", "w", encoding="utf-8") as f:
        json.dump(new, f, ensure_ascii=False, indent=2)
    shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
