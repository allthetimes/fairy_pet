# -*- coding: utf-8 -*-
"""高光球分析 v2 —— 周向去背景法。

问题: 泛光素材里白环内缘整圈都超阈值, 直接用"眼内最亮-12"会把整条环圈进来, 质心被拉回圆心。
做法: 极坐标采样 L[r, θ] 后, 对每个半径减去**周向中位数**(= 沿圆周均匀的环状背景),
      剩下的就是局部亮斑(高光)。再测质心/等效半径, 并与"深蓝区"求交叠。

指标:
  r_glint  高光等效半径
  dist     高光中心到圆心距离
  r_deep   深蓝区等效半径
  gap      dist - r_glint - r_deep   (≈0 贴着深眼; >0 分离)
  overlap  高光掩膜 ∩ 深蓝掩膜 的像素数 (>0 表示高光压到深眼上)

用法: python scripts/_glint_analyze.py --video <mp4> --align <json> [--ss 0] [--dur 12] [--fps 120]
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

N_ANG, STEP = 720, 0.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--align", required=True)
    ap.add_argument("--ss", type=float, default=0.0)
    ap.add_argument("--dur", type=float, default=12.0)
    ap.add_argument("--fps", type=float, default=120.0)
    ap.add_argument("--r-eye", type=float, default=0.45, help="高光搜索区半径(×R)")
    ap.add_argument("--out", default=str(ROOT / "dev" / "glint_analysis.json"))
    a = ap.parse_args()

    al = json.load(open(a.align, encoding="utf-8"))
    R = al["R_px"]
    side = int(R * 2.9)
    x0, y0 = int(round(al["cx"] - side / 2)), int(round(al["cy"] - side / 2))
    C = side / 2
    ang = np.linspace(0, 2 * np.pi, N_ANG, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    r_hi = a.r_eye * R
    rs = np.arange(0, r_hi, STEP)
    u = rs / R

    args = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", str(a.ss), "-i", a.video,
            "-t", str(a.dur), "-vf", f"crop={side}:{side}:{x0}:{y0},fps={a.fps}",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    nb = side * side * 3

    rec, n = [], 0
    while True:
        buf = p.stdout.read(nb)
        if len(buf) < nb:
            break
        im = np.frombuffer(buf, np.uint8).reshape(side, side, 3).astype(np.float32)
        L = 0.299 * im[:, :, 0] + 0.587 * im[:, :, 1] + 0.114 * im[:, :, 2]

        # 极坐标采样
        X = np.clip(np.round(C + np.outer(rs, ca)).astype(int), 0, side - 1)
        Y = np.clip(np.round(C + np.outer(rs, sa)).astype(int), 0, side - 1)
        Lp = L[Y, X]                                   # [n_r, n_ang]
        bg = np.median(Lp, axis=1, keepdims=True)      # 周向背景
        D = Lp - bg

        # 高光: D 显著为正
        thr = max(6.0, float(D.max()) * 0.55)      # 取局部对比度最高的那部分 → 只留高光核
        gm = D > thr
        area = int(gm.sum()) * (STEP * (2 * np.pi * R / N_ANG) / (R / 100) ** 0)   # 用像素权
        if gm.sum() < 8:
            rec.append(None)
            n += 1
            continue
        # 质心 (极坐标直接算)
        w = D[gm]
        rr_g = rs[np.nonzero(gm)[0]]
        th_g = ang[np.nonzero(gm)[1]]
        gx = float((w * rr_g * np.cos(th_g)).sum() / w.sum())
        gy = float((w * rr_g * np.sin(th_g)).sum() / w.sum())
        # 等效半径: 面积换算 (每像素面积 = STEP × 2πr/N_ANG)
        px_area = STEP * (2 * np.pi * rr_g / N_ANG)
        r_g = float(np.sqrt(px_area.sum() / np.pi))

        # 深蓝区(深眼): 逐角度找 L<thr_d 的最外半径, 取中位数
        l_deep = np.median(Lp[(u > 0.04) & (u < 0.11), :])
        l_iris = np.median(Lp[(u > 0.24) & (u < 0.28), :])
        thr_d = (l_deep + l_iris) / 2
        dm = Lp < thr_d
        idx = np.where(dm[::-1, :].any(axis=0),
                       len(rs) - 1 - np.argmax(dm[::-1, :], axis=0), -1)
        deep_r = np.where(idx < 0, np.nan, rs[np.clip(idx, 0, len(rs) - 1)])
        r_deep = float(np.nanmedian(deep_r))

        # 交叠: 高光掩膜落在"深蓝区"内的数量 —— 逐像素判定
        ov = 0
        gi, gj = np.nonzero(gm)
        if len(gi):
            ov = int(np.sum(Lp[gi, gj] < thr_d))

        dist = float(np.hypot(gx, gy))
        rec.append((gx, gy, r_g, float(np.max(D)), dist, r_deep, ov, float(thr_d)))
        n += 1
    p.stdout.close()
    p.wait()

    good = [r for r in rec if r]
    print(f"{pathlib.Path(a.video).name}  采样 {n} 帧, 有效 {len(good)}")
    A = np.array(good)
    fps = a.fps
    ts = np.arange(len(good)) / fps
    gx, gy, r_g, dmax, dist, r_deep, ov, thr_d = A.T
    gap = dist - r_g - r_deep
    base = np.array([np.median(gx), np.median(gy)])
    ang_g = np.degrees(np.arctan2(gy - np.median(gy), gx - np.median(gx)))

    def stat(name, v):
        print(f"  {name:<12} 均值 {v.mean():8.3f}  std {v.std():6.3f}  "
              f"范围 {v.min():8.3f} ~ {v.max():8.3f}  峰谷/均值 {(v.max() - v.min()) / abs(v.mean()) * 100:6.2f}%")
    print("\n[序列统计]  (单位 px; ÷R×100 = SVG 单位)")
    stat("高光半径", r_g)
    stat("高光中心距", dist)
    stat("深眼半径", r_deep)
    stat("间隙 gap", gap)
    print(f"  高光方位角 均值 {ang_g.mean():7.2f}°  std {ang_g.std():5.2f}°  "
          f"(0°=右, 90°=下, 即右下方向)")
    print(f"  高光压到深眼的帧: {int((ov > 0).sum())}/{len(ov)} ({(ov > 0).mean() * 100:.1f}%)")

    def fitfreq(y, fmin=0.9, fmax=1.6):
        best = None
        for f in np.arange(fmin, fmax, 0.0002):
            M = np.column_stack([np.ones_like(ts), np.cos(2 * np.pi * f * ts),
                                 np.sin(2 * np.pi * f * ts)])
            c, *_ = np.linalg.lstsq(M, y, rcond=None)
            rsd = float((y - M @ c).std())
            if best is None or rsd < best[0]:
                best = (rsd, f, float(np.hypot(c[1], c[2])), float(np.arctan2(c[2], c[1])))
        return best

    print("\n[呼吸频率处的正弦拟合]")
    fr = {}
    for name, v in [("高光半径", r_g), ("高光中心距", dist), ("深眼半径", r_deep),
                    ("gap", gap), ("gx", gx), ("gy", gy)]:
        rsd, f, amp, ph = fitfreq(v)
        fr[name] = (f, amp, ph, rsd)
        print(f"  {name:<12} f={f:.4f}Hz  振幅={amp:7.3f}px ({amp / abs(v.mean()) * 100:5.2f}%)  "
              f"相位={np.degrees(ph):7.1f}°  残差={rsd:6.3f}")

    print("\n[间隙分布]")
    for q in (0, 1, 5, 25, 50, 75, 95, 99, 100):
        print(f"  P{q:<3} {np.percentile(gap, q):8.3f}")
    print(f"  高光半径分位: " + "  ".join(
        f"P{q}={np.percentile(r_g, q):.2f}" for q in (0, 5, 50, 95, 100)))

    means = {k: abs(v.mean()) for k, v in [("高光半径", r_g), ("高光中心距", dist), ("深眼半径", r_deep),
                                           ("gap", gap), ("gx", gx), ("gy", gy)]}
    out = {"video": pathlib.Path(a.video).name, "frames": len(good), "fps": fps, "R_px": R,
           "ring_deg_mean": round(float(ang_g.mean()), 2),
           "touch_ratio": round(float((ov > 0).mean()), 4),
           "stats": {k: {"mean": round(float(v.mean()), 3), "std": round(float(v.std()), 3),
                         "min": round(float(v.min()), 3), "max": round(float(v.max()), 3)}
                     for k, v in [("r_glint", r_g), ("dist", dist), ("r_deep", r_deep), ("gap", gap)]},
           "fits": {k: {"f": round(v[0], 5), "amp_px": round(v[1], 3),
                        "amp_pct": round(v[1] / means[k] * 100, 2),
                        "phase_deg": round(np.degrees(v[2]), 1), "resid": round(v[3], 3)}
                    for k, v in fr.items()},
           "gap_percentiles": {f"P{q}": round(float(np.percentile(gap, q)), 3)
                               for q in (0, 1, 5, 25, 50, 75, 95, 99, 100)},
           "series": [[round(float(x), 3) for x in row] for row in A.tolist()]}
    pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {a.out}")


main()
