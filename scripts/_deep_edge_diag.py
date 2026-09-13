# -*- coding: utf-8 -*-
"""深眼外缘多口径诊断: 深眼与蓝瞳之间夹着一条模糊白描边过渡带,
不同判据给出的"外缘"相差 2~3 个 SVG 单位。这里并列 4 种口径, 供选基准。

口径:
  A 深蓝填充外缘   —— 逐角度 L<thr 的最外半径(中位数)
  B 最陡过渡沿     —— 径向平均剖面 dL 正峰(区间 0.16~0.24), 与旧测量同口径
  C 白描边峰      —— 径向平均剖面 L 的局部极大(区间 0.17~0.25)
  D 白描边外缘    —— 从 C 向外, L 回落到"蓝瞳本体亮度"处

用法: python scripts/_deep_edge_diag.py [--dur 5]
"""
import argparse
import json
import pathlib
import sys

import numpy as np

SCRIPTS = pathlib.Path(__file__).parent
sys.path.insert(0, str(SCRIPTS))
from _measure_diameters import (ALIGN, VIDEO, fit_sine, profile2d,  # noqa: E402
                                smooth, stream_frames)

OUT = pathlib.Path(r"D:\work\fairy_pet\dev\deep_edge_diag.json")


def thr_of(L2, u):
    l_deep = np.median(L2[(u > 0.04) & (u < 0.12), :])
    l_iris = np.median(L2[(u > 0.24) & (u < 0.27), :])
    return l_deep, l_iris, (l_deep + l_iris) / 2.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dur", type=float, default=5.0)
    ap.add_argument("--fps", type=float, default=60.0)
    a = ap.parse_args()

    cx, cy, R = ALIGN["cx"], ALIGN["cy"], ALIGN["R_px"]
    side = 620
    x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    print(f"深眼外缘多口径诊断  {VIDEO.name}  {a.dur}s @ {a.fps}fps\n")

    series = {"A_深蓝填充外缘": [], "B_最陡过渡沿": [], "C_白描边峰": [], "D_白描边外缘": []}
    ts = []
    for idx, im in stream_frames(VIDEO, (x0, y0, side, side), a.fps, a.dur):
        rs, prof = profile2d(im, side / 2, side / 2, R * 1.06)
        L2 = 0.299 * prof[:, :, 0] + 0.587 * prof[:, :, 1] + 0.114 * prof[:, :, 2]
        u = rs / R
        l_deep, l_iris, thr = thr_of(L2, u)
        Lm = smooth(L2.mean(axis=1), 5)
        dL = np.gradient(Lm)

        # A 掩膜
        m = (u > 0.08) & (u < 0.34)
        sub, us = (L2 < thr)[m, :], u[m]
        idx_rev = np.argmax(sub[::-1, :], axis=0)
        any_rev = sub[::-1, :].any(axis=0)
        vals = np.where(any_rev, us[np.clip(len(us) - 1 - idx_rev, 0, len(us) - 1)], np.nan)
        series["A_深蓝填充外缘"].append(float(np.nanmedian(vals)))

        # B 最陡过渡沿
        mb = (u >= 0.16) & (u <= 0.24)
        series["B_最陡过渡沿"].append(float(u[mb][int(np.argmax(dL[mb]))]))

        # C 亮带峰值
        mc = (u >= 0.17) & (u <= 0.25)
        uc = u[mc]
        kc = int(np.argmax(Lm[mc]))
        r_c = uc[kc]
        series["C_白描边峰"].append(float(r_c))

        # D 从 C 向外回落到蓝瞳本体亮度
        r_d = np.nan
        for r in rs[rs > r_c * R]:
            if Lm[int(r / 0.5)] <= l_iris * 1.01:
                r_d = r / R
                break
        series["D_白描边外缘"].append(float(r_d))

        ts.append(idx / a.fps)

    ts = np.array(ts)
    n = len(ts)
    T = 0.8584                      # 上一步精定
    print(f"{'口径':<16}{'均值u':>9}{'SVG半径':>9}{'Ø均值':>8}{'Ø最大':>8}{'Ø最小':>8}{'±%':>7}{'残差%':>7}")
    print("-" * 74)
    out = {"video": VIDEO.name, "frames": n, "period_s": T, "edge_defs": {}}
    for name, arr in series.items():
        y = np.array(arr, dtype=float)
        ok = ~np.isnan(y)
        if ok.sum() < n * 0.5:
            print(f"{name:<16} 检出率过低 ({ok.sum()}/{n})")
            continue
        A0, amp, ph, rsd = fit_sine(ts[ok], y[ok], T)
        sv = lambda v: v * 100
        rec = {"u_mean": round(float(A0), 4), "svg_r_mean": round(sv(A0), 2),
               "svg_diam_mean": round(sv(A0) * 2, 2),
               "svg_diam_max": round(sv(A0 + amp) * 2, 2),
               "svg_diam_min": round(sv(A0 - amp) * 2, 2),
               "svg_r_max": round(sv(A0 + amp), 2), "svg_r_min": round(sv(A0 - amp), 2),
               "amp_pct": round(amp / A0 * 100, 2), "resid_pct": round(rsd / A0 * 100, 2),
               "valid": int(ok.sum())}
        out["edge_defs"][name] = rec
        print(f"{name:<16}{rec['u_mean']:>9.4f}{rec['svg_r_mean']:>9.2f}{rec['svg_diam_mean']:>8.2f}"
              f"{rec['svg_diam_max']:>8.2f}{rec['svg_diam_min']:>8.2f}{rec['amp_pct']:>7.2f}{rec['resid_pct']:>7.2f}")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {OUT}")


main()
