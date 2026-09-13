# -*- coding: utf-8 -*-
"""高光球 v3 —— 定向径向剖面。

依据 (dev/glint_zoom_compare.png 放大核对): 高光是一颗直径≈60px 的白球, 位于深眼右下方
(方位≈54°), 中心距圆心≈67px, 其内缘压过深眼边缘。球内亮度饱和均匀, 所以:
  - 过球心的径向剖面上, 球表现为一段高亮度平台 → 平台起止即球的内/外缘, 跨度=直径
  - 深眼边缘在高光方向被球覆盖, 改在对面几个方向用梯度法测, 取中位数

使用固定方向(高光摆动只有 ±1px, 可忽略), 逐帧输出:
  r_glint(球半径) / glint_dist(球心距) / r_deep(深眼半径) / gap = dist - r_g - r_deep

用法: python scripts/_glint_radial.py --video <f> --align <json> [--ss 0] [--dur 12] [--fps 120]
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

GLINT_DEG = 53.8            # 高光方位(0°=右, 90°=下)
DEEP_DIRS = [200, 250, 300]  # 测深眼边缘的方向(避开高光)


def ray(im, L, C, deg, rmax, step=0.25):
    t = np.radians(deg)
    rs = np.arange(0, rmax, step)
    x = np.clip(C + rs * np.cos(t), 0, im.shape[1] - 1)
    y = np.clip(C + rs * np.sin(t), 0, im.shape[0] - 1)
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int)
    fx = (x - x0)[:, None]; fy = (y - y0)[:, None]
    # 双线性 (L 已是单通道, 用 2D 插值)
    v = (L[y0, x0] * (1 - fx[:, 0]) * (1 - fy[:, 0]) + L[y0, x0 + 1] * fx[:, 0] * (1 - fy[:, 0]) +
         L[y0 + 1, x0] * (1 - fx[:, 0]) * fy[:, 0] + L[y0 + 1, x0 + 1] * fx[:, 0] * fy[:, 0])
    return rs, v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--align", required=True)
    ap.add_argument("--ss", type=float, default=0.0)
    ap.add_argument("--dur", type=float, default=12.0)
    ap.add_argument("--fps", type=float, default=120.0)
    ap.add_argument("--deg", type=float, default=GLINT_DEG)
    ap.add_argument("--out", default=str(ROOT / "dev" / "glint_radial.json"))
    a = ap.parse_args()

    al = json.load(open(a.align, encoding="utf-8"))
    R = al["R_px"]
    side = int(R * 2.9)
    x0, y0 = int(round(al["cx"] - side / 2)), int(round(al["cy"] - side / 2))
    C = side / 2

    args = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", str(a.ss), "-i", a.video,
            "-t", str(a.dur), "-vf", f"crop={side}:{side}:{x0}:{y0},fps={a.fps}",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    nb = side * side * 3

    rec, n = [], 0
    dbg = None
    while True:
        buf = p.stdout.read(nb)
        if len(buf) < nb:
            break
        im = np.frombuffer(buf, np.uint8).reshape(side, side, 3).astype(np.float32)
        L = 0.299 * im[:, :, 0] + 0.587 * im[:, :, 1] + 0.114 * im[:, :, 2]

        # --- 高光球: 两条切向弧的弦长联立解 (球半径 R, 球心距 d) ---
        # 弦长(r) = 2√(R²-(d-r)²)  →  两条弧即可解出 R 与 d, 不受"球与白环相连"影响
        def chord(rq):
            th = np.radians(a.deg) + np.linspace(-0.6, 0.6, 261)
            x = np.clip(C + rq * np.cos(th), 0, side - 1)
            y = np.clip(C + rq * np.sin(th), 0, side - 1)
            xi = np.floor(x).astype(int); yi = np.floor(y).astype(int)
            fx, fy = x - xi, y - yi
            vv = (L[yi, xi] * (1 - fx) * (1 - fy) + L[yi, xi + 1] * fx * (1 - fy) +
                  L[yi + 1, xi] * (1 - fx) * fy + L[yi + 1, xi + 1] * fx * fy)
            vv = np.convolve(vv, np.ones(5) / 5, mode="same")
            s = rq * (th - th[0])
            outside = float(np.median(np.concatenate([vv[:25], vv[-25:]])))
            thr_g = (float(vv.max()) + outside) / 2
            mm = vv > thr_g
            if not mm.any():
                return None, thr_g, vv, s, th
            ipk = int(np.argmax(vv))
            i1 = ipk
            while i1 > 0 and mm[i1 - 1]:
                i1 -= 1
            i2 = ipk
            while i2 < len(mm) - 1 and mm[i2 + 1]:
                i2 += 1
            return float(s[i2] - s[i1]), thr_g, vv, s, th

        R1, R2 = 58.0, 78.0
        c1, thr1, vv1, s1, th1 = chord(R1)
        c2, thr2, _, _, _ = chord(R2)
        if c1 is None or c2 is None or c1 <= 1 or c2 <= 1:
            rec.append(None); n += 1; continue
        # c1²/4 - c2²/4 = (d-R2)² - (d-R1)² = (2d-R1-R2)(R1-R2)
        k1 = c1 * c1 / 4.0
        k2 = c2 * c2 / 4.0
        den = 2.0 * (R1 - R2)
        dist = ((k1 - k2) - (R1 * R1 - R2 * R2)) / den if abs(den) > 1e-9 else np.nan
        Rg2 = k1 + (dist - R1) ** 2
        if not np.isfinite(dist) or Rg2 <= 0:
            rec.append(None); n += 1; continue
        r_g = float(np.sqrt(Rg2))
        dist = float(dist)
        best = (c1, thr1, vv1, s1, th1, R1)        # --- 深眼边缘(其他方向, 梯度法) ---
        deps = []
        for d in DEEP_DIRS:
            rs2, v2 = ray(im, L, C, d, 0.40 * R)
            v2s = np.convolve(v2, np.ones(9) / 9, mode="same")
            g = np.gradient(v2s)
            m2 = (rs2 > 0.10 * R) & (rs2 < 0.30 * R)
            if m2.any():
                deps.append(float(rs2[m2][int(np.argmax(g[m2]))]))
        r_deep = float(np.median(deps)) if deps else np.nan

        gap = dist - r_g - r_deep
        rec.append((dist, r_g, r_deep, gap, dist - r_g, dist + r_g, best[1], best[0]))
        if dbg is None:
            dbg = (best[4], best[2], best[1], 0.0, best[0], best[5])
        n += 1
    p.stdout.close()
    p.wait()

    good = [r for r in rec if r]
    print(f"{pathlib.Path(a.video).name}  采样 {n} 帧, 有效 {len(good)}  (高光方向 {a.deg}°)")
    A = np.array(good)
    fps = a.fps
    ts = np.arange(len(good)) / fps
    dist, r_g, r_deep, gap, r_in, r_out, thr, vmax = A.T

    def stat(name, v):
        print(f"  {name:<12} 均值 {v.mean():8.3f}  std {v.std():6.3f}  "
              f"范围 {v.min():8.3f} ~ {v.max():8.3f}  峰谷 {v.max()-v.min():7.3f}"
              f" ({(v.max()-v.min())/abs(v.mean())*100:5.2f}%)")
    print("\n[序列统计] (px)")
    stat("球半径 r_g", r_g)
    stat("球心距 dist", dist)
    stat("深眼半径", r_deep)
    stat("gap", gap)
    stat("球内缘", r_in)
    stat("球外缘", r_out)
    print(f"  球半径分位: " + "  ".join(f"P{q}={np.percentile(r_g, q):.2f}" for q in (0, 5, 50, 95, 100)))
    print(f"  球内缘 vs 深眼边缘: 球内缘 {r_in.mean():.2f}  深眼 {r_deep.mean():.2f}  "
          f"→ 球内缘在深眼{'内' if r_in.mean() < r_deep.mean() else '外'}侧 "
          f"{abs(r_in.mean()-r_deep.mean()):.2f}px")
    print(f"  球压过深眼的帧: {int((gap < 0).sum())}/{len(gap)} ({(gap < 0).mean()*100:.1f}%)")

    def fitfreq(y, fmin=0.9, fmax=1.6):
        best = None
        for f in np.arange(fmin, fmax, 0.0002):
            M = np.column_stack([np.ones_like(ts), np.cos(2 * np.pi * f * ts), np.sin(2 * np.pi * f * ts)])
            c, *_ = np.linalg.lstsq(M, y, rcond=None)
            rsd = float((y - M @ c).std())
            if best is None or rsd < best[0]:
                best = (rsd, f, float(np.hypot(c[1], c[2])), float(np.arctan2(c[2], c[1])))
        return best
    print("\n[呼吸频率处拟合]")
    fr = {}
    for name, v in [("球半径", r_g), ("球心距", dist), ("深眼半径", r_deep), ("gap", gap)]:
        rsd, f, amp, ph = fitfreq(v)
        fr[name] = (f, amp, ph, rsd)
        print(f"  {name:<10} f={f:.4f}Hz  振幅 {amp:6.3f}px ({amp/abs(v.mean())*100:5.2f}%)  "
              f"相位 {np.degrees(ph):7.1f}°  残差 {rsd:6.3f}")

    out = {"video": pathlib.Path(a.video).name, "frames": len(good), "fps": fps, "R_px": R,
           "glint_deg": a.deg,
           "stats": {k: {"mean": round(float(v.mean()), 3), "std": round(float(v.std()), 3),
                         "min": round(float(v.min()), 3), "max": round(float(v.max()), 3)}
                     for k, v in [("r_glint", r_g), ("dist", dist), ("r_deep", r_deep), ("gap", gap)]},
           "overlap_ratio": round(float((gap < 0).mean()), 4),
           "fits": {k: {"f": round(v[0], 5), "amp_px": round(v[1], 3),
                        "phase_deg": round(np.degrees(v[2]), 1), "resid": round(v[3], 3)}
                    for k, v in fr.items()},
           "series": [[round(float(x), 3) for x in row[:4]] for row in A.tolist()]}
    pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {a.out}")

    # 首帧弧剖面诊断
    th_, vv_, thr_, s1_, s2_, rt_ = dbg
    print(f"\n[首帧弧剖面] 弧半径 r={rt_:.1f}  阈值 {thr_:.1f}  球跨越弧长 {s2_-s1_:.1f}px "
          f"→ 直径 {s2_-s1_:.1f} / 半径 {(s2_-s1_)/2:.1f}")
    print("  角度°: " + " ".join(f"{np.degrees(t):6.1f}" for t in th_[::20]))
    print("  L    : " + " ".join(f"{x:6.0f}" for x in vv_[::20]))


main()
