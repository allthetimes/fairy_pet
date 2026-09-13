"""全面精测 v2: 平台中点穿越法测边缘 + 差分互相关跟踪齿轮。

v1 (梯度argmax) 的教训: 视频边缘软(压缩+辉光), 梯度峰宽而平, argmax 噪声极大
(白环极差虚增到 15%)。平台中点穿越法: 取边界两侧清晰平台的均值电平,
扫描穿越点并线性插值 —— 对软边缘和辉光晕都无偏。

用法: python measure_all2.py <视频> [--out dev/measure_all.json]
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
from compare_align import template  # noqa: E402


def run(args):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("CMD 失败:", " ".join(args)); print((r.stderr or "")[-1200:]); sys.exit(1)
    return r


def smooth(x, k=5):
    return np.convolve(x, np.ones(k) / k, mode="same")


def bilin_profile(im, cxl, cyl, rmax, n_ang=720, step=0.5):
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


def cross_edge(u, sig, scan_lo, scan_hi, inner_u, outer_u):
    """平台中点穿越: inner_u/outer_u = (lo,hi) 平台窗口, 返回穿越半径(u)"""
    mi = (u >= inner_u[0]) & (u <= inner_u[1])
    mo = (u >= outer_u[0]) & (u <= outer_u[1])
    a = sig[mi].mean(); b = sig[mo].mean()
    thr = (a + b) / 2
    m = (u >= scan_lo) & (u <= scan_hi)
    idx = np.where(m)[0]
    rising = b > a
    for j in range(len(idx) - 1):
        i0, i1 = idx[j], idx[j + 1]
        if rising and sig[i0] < thr <= sig[i1]:
            return float(u[i0] + (thr - sig[i0]) / (sig[i1] - sig[i0]) * (u[i1] - u[i0]))
        if not rising and sig[i0] > thr >= sig[i1]:
            return float(u[i0] + (sig[i0] - thr) / (sig[i0] - sig[i1]) * (u[i1] - u[i0]))
    return None


def phase_lag(ts, us, T, P0, half=0.45):
    w = (us - us.min()) / max(us.max() - us.min(), 1e-6)
    wz = w - w.mean()
    grid = np.arange(-half, half, 0.005)
    cs = []
    for d in grid:
        tpl = np.array([template(t + P0 + d, T) for t in ts])
        cs.append(np.corrcoef(wz, tpl - tpl.mean())[0, 1])
    i = int(np.argmax(cs))
    if 0 < i < len(grid) - 1:
        d0, d1, d2 = cs[i - 1], cs[i], cs[i + 1]
        den = d0 - 2 * d1 + d2
        if abs(den) > 1e-9:
            grid = grid.astype(float)
            grid[i] += 0.5 * (d0 - d2) / den * (grid[1] - grid[0])
    return float(grid[i]), float(cs[i])


# 边缘定义: 名称 -> (信号, 扫描窗, 内平台, 外平台)  —— 单位 u
EDGE_DEFS = {
    "深眼外缘":  ("L",  (0.16, 0.30), (0.10, 0.15), (0.26, 0.295)),
    "蓝瞳外缘":  ("BR", (0.24, 0.36), (0.235, 0.26), (0.30, 0.335)),
    "灰紫蓝外缘": ("L",  (0.36, 0.50), (0.335, 0.36), (0.45, 0.52)),
    "白环外缘":  ("L",  (0.58, 0.70), (0.52, 0.57), (0.67, 0.73)),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default="dev/measure_all.json")
    a = ap.parse_args()

    ALIGN = json.load(open("dev/align_data.json", encoding="utf-8"))
    cx, cy, R = ALIGN["cx"], ALIGN["cy"], ALIGN["R_px"]
    T, P0 = ALIGN["T_meas"], ALIGN["P0"]

    tmpdir = "_ma_frames"
    if os.path.exists(tmpdir):
        shutil.rmtree(tmpdir)
    os.makedirs(tmpdir)
    side = 540
    x0 = int(cx - side / 2); y0 = int(cy - side / 2)
    run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
         "-t", "4", "-i", a.video,
         "-vf", f"crop={side}:{side}:{x0}:{y0}",
         "-r", "30", os.path.join(tmpdir, "f_%05d.png")])
    files = sorted(glob.glob(os.path.join(tmpdir, "f_*.png")))
    print(f"帧: {len(files)} 张 (540px 原生分辨率)")

    CLX = CLY = side / 2
    edges = {k: [] for k in EDGE_DEFS}
    ts = []
    glints = []
    gear_prof = []

    for i, fp in enumerate(files):
        im = np.asarray(Image.open(fp).convert("RGB")).astype(np.float32)
        rs, prof = bilin_profile(im, CLX, CLY, 240)
        L = smooth(0.299 * prof[:, 0] + 0.587 * prof[:, 1] + 0.114 * prof[:, 2], 7)
        BR = smooth(prof[:, 2] - prof[:, 0], 7)
        u = rs / R
        SIG = {"L": L, "BR": BR}
        for name, (sig, scan, inn, outw) in EDGE_DEFS.items():
            e = cross_edge(u, SIG[sig], *scan, inn, outw)
            edges[name].append(e)
        ts.append(i / 30.0)

        # 高光球: r<0.40u 内找亮斑 (白环内缘 ~0.41u 以内, 避开白环)
        Limg = 0.299 * im[:, :, 0] + 0.587 * im[:, :, 1] + 0.114 * im[:, :, 2]
        ys, xs = np.mgrid[0:side, 0:side]
        rr = np.hypot(ys - CLY, xs - CLX)
        m = rr < 0.40 * R
        reg = Limg[m]
        thr = reg.max() - 10
        g = m & (Limg > thr)
        if g.sum() > 40:
            gx, gy = xs[g].mean(), ys[g].mean()
            glints.append(((gx - CLX) / R, (gy - CLY) / R, np.sqrt(g.sum() / np.pi) / R))
        else:
            glints.append(None)

        # 齿轮: r=0.85u 的角向 B-R 剖面 (靛蓝齿 B-R~97 vs 外圈蓝 B-R~163, 对比度比 L 大)
        r_gear = 0.85 * R
        ang = np.linspace(0, 2 * np.pi, 720, endpoint=False)
        xg = np.clip(np.round(CLX + r_gear * np.cos(ang)).astype(int), 0, side - 1)
        yg = np.clip(np.round(CLY + r_gear * np.sin(ang)).astype(int), 0, side - 1)
        brg = smooth(im[yg, xg, 2] - im[yg, xg, 0], 9)
        gear_prof.append(brg - brg.mean())

    # ---- 边缘统计 (丢 None, 用中位数 + p2/p98) ----
    print(f"\n{'边缘':<8} {'中位u':>8} {'SVG半径':>8} {'我方':>6} {'p2~p98极差%':>10} {'相位Δs':>8} {'相关':>6}")
    MINE = {"深眼外缘": 21.5, "蓝瞳外缘": 30.6, "灰紫蓝外缘": 44.7, "白环外缘": 64.5}
    out = {"R_px": R, "cx": cx, "cy": cy, "T": T, "P0": P0, "rings": {}}
    for name, arr in edges.items():
        v = np.array([x for x in arr if x is not None])
        ok = f"{len(v)}/{len(arr)}"
        med = float(np.median(v))
        p2, p98 = np.percentile(v, 2), np.percentile(v, 98)
        rng = (p98 - p2) / med * 100
        tv = np.array([t for t, x in zip(ts, arr) if x is not None])
        d, c = phase_lag(tv, v, T, P0)
        print(f"{name:<8} {med:8.4f} {med * 100:8.2f} {MINE[name]:6.1f} {rng:10.2f} {d:8.3f} {c:6.3f}  ({ok})")
        out["rings"][name] = {"u": round(med, 4), "svg_r": round(med * 100, 2),
                              "mine": MINE[name], "range_pct": round(float(rng), 2),
                              "lag": round(d, 3), "corr": round(c, 3), "valid": len(v)}

    # ---- 高光球 ----
    gl = [g for g in glints if g]
    if len(gl) > 10:
        garr = np.array(gl)
        out["glint"] = {"dx_u": round(float(np.median(garr[:, 0])), 4),
                        "dy_u": round(float(np.median(garr[:, 1])), 4),
                        "r_u": round(float(np.median(garr[:, 2])), 4), "n": len(gl)}
        print(f"\n高光球: 偏移=({np.median(garr[:, 0]):+.4f}, {np.median(garr[:, 1]):+.4f})u "
              f"半径={np.median(garr[:, 2]):.4f}u  -> SVG cx={np.median(garr[:, 0]) * 100:.1f} "
              f"cy={np.median(garr[:, 1]) * 100:.1f} r={np.median(garr[:, 2]) * 100:.1f} ({len(gl)}帧)")
    else:
        print(f"\n高光球: 检出帧不足 ({len(gl)})")

    # ---- 齿轮: 帧间差分互相关 ----
    GP = np.array(gear_prof)
    n = len(GP)
    shifts = [0.0]
    angs = np.arange(720) * 360.0 / 720.0
    for i in range(1, n):
        prev = GP[i - 1]; cur = GP[i]
        best, bs = None, -2
        for sh in np.arange(-3.0, 3.01, 0.1):
            s = np.interp(angs + sh, angs, cur, period=360)
            c = np.corrcoef(prev, s)[0, 1]
            if c > bs:
                bs, best = c, sh
        shifts.append(shifts[-1] + best)
    shifts = np.array(shifts)
    tt = np.array(ts)
    k = np.polyfit(tt, shifts, 1)
    resid = shifts - np.polyval(k, tt)
    omega = k[0]
    print(f"\n齿轮(差分互相关): 角速度={omega:+.3f}°/s 方向={'顺时针' if omega > 0 else '逆时针'} "
          f"整圈周期={360 / abs(omega):.2f}s 残差std={resid.std():.3f}° "
          f"末帧累计={shifts[-1]:.2f}°")
    out["gear"] = {"omega_deg_s": round(float(omega), 3),
                   "period_s": round(float(360 / abs(omega)), 2),
                   "resid_std_deg": round(float(resid.std()), 3),
                   "total_deg": round(float(shifts[-1]), 2)}

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n-> {a.out}")
    shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
