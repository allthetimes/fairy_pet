# -*- coding: utf-8 -*-
"""标定新素材(1920x1080 120fps)的环形核圆心与外圈半径 —— v2。

要点: 外圈蓝盘外面是**比它更亮的光晕**, 边界方向与旧素材相反, 且渐变宽(≈4px);
      所以圆心改用对比最强的**白环外缘**(L 下降沿)迭代拟合, 外圈半径再用
      B-R 的陡降沿独立测一次, 两者交叉验证。

用法: python scripts/_calib_new.py [--t 60] [--r0 206]
"""
import argparse
import json
import pathlib
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = pathlib.Path(r"D:\work\fairy_pet")
SRC = r"D:/allthetimes/Videos/2026-09-13 20-24-36.mkv"
sys.path.insert(0, str(ROOT / "scripts"))
from video_tool import ffmpeg_exe        # noqa: E402

N_ANG, STEP = 720, 0.5
U_WHITE, U_SLATE, U_IRIS, U_DEEP, U_INDIGO = 0.6223, 0.4147, 0.2813, 0.1841, 0.7397


def grab(t, src=None):
    p = ROOT / "dev" / "_new_frame.png"
    subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", str(t), "-i", src or SRC, "-frames:v", "1", str(p)], check=True)
    return np.asarray(Image.open(p).convert("RGB")).astype(np.float32)


def chan(im, cx, cy, r_lo, r_hi, which):
    """径向剖面: which in {'L','BR'}; 返回 (rs, prof[n_r, n_ang])"""
    H, W, _ = im.shape
    ang = np.linspace(0, 2 * np.pi, N_ANG, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    rs = np.arange(r_lo, r_hi, STEP)
    out = np.zeros((len(rs), N_ANG))
    for i, r in enumerate(rs):
        x = np.clip(np.round(cx + r * ca).astype(int), 0, W - 1)
        y = np.clip(np.round(cy + r * sa).astype(int), 0, H - 1)
        p = im[y, x]
        out[i] = (0.299 * p[:, 0] + 0.587 * p[:, 1] + 0.114 * p[:, 2]) if which == "L" \
            else (p[:, 2] - p[:, 0])
    return rs, np.apply_along_axis(lambda v: np.convolve(v, np.ones(5) / 5, mode="same"), 0, out)


def edge(rs, prof, sign):
    d = np.gradient(prof, axis=0)
    k = (d if sign > 0 else -d).argmax(axis=0)
    return rs[k]


def bbox_guess(im):
    """蓝色掩膜的行/列投影 → 外圈圆盘 bbox(含光晕, 只用作圆心初值)"""
    R_, B_ = im[:, :, 0], im[:, :, 2]
    m = (B_ > 140) & (B_ - R_ > 70)
    m[:, 900:] = False                      # 只看环形核一侧
    cols, rows = m.sum(axis=0), m.sum(axis=1)

    def span(v):
        idx = np.nonzero(v >= v.max() * 0.3)[0]
        return (idx[0], idx[-1]) if len(idx) else (0, 1)
    x0, x1 = span(cols)
    y0, y1 = span(rows)
    return (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2


def refine(im, cx, cy, r_lo, r_hi, which, sign, iters=4):
    """固定搜索窗, 只更新圆心(窗口随半径漂移会导致一路跑偏)"""
    for it in range(iters):
        rs, pr = chan(im, cx, cy, r_lo, r_hi, which)
        r_th = edge(rs, pr, sign)
        th = np.linspace(0, 2 * np.pi, N_ANG, endpoint=False)
        A = np.column_stack([np.ones(N_ANG), np.cos(th), np.sin(th)])
        c, *_ = np.linalg.lstsq(A, r_th, rcond=None)
        R0, ca_, sa_ = c
        cx -= ca_
        cy -= sa_
        resid = r_th - A @ c
        print(f"    {it + 1}: R={R0:7.2f}  圆心修正=({-ca_:+6.2f},{-sa_:+6.2f})  "
              f"r(θ)残差std={resid.std():5.2f}px  圆心=({cx:.2f},{cy:.2f})")
    return cx, cy, R0, resid.std()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--t", type=float, default=60.0)
    ap.add_argument("--r0", type=float, default=206.0)
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default=str(ROOT / "dev" / "new_align.json"))
    a = ap.parse_args()

    im = grab(a.t, a.src)
    H, W, _ = im.shape
    cx0, cy0, _, _ = bbox_guess(im)   # 蓝色掩膜 bbox 中心作初值
    print(f"帧 t={a.t}s  {W}x{H}   初始圆心≈({cx0},{cy0})  R0≈{a.r0}px\n")

    # 1) 白环外缘定圆心 (窗口取剖面实测位置 r≈127 附近)
    print("[1] 白环外缘 L 下降沿 (r∈[116,140]) 迭代定圆心:")
    cx, cy, r_white, res_w = refine(im, cx0, cy0, 116.0, 140.0, "L", -1)

    # 2) 外圈蓝外缘: B-R 陡降沿, 用已定的圆心 (剖面实测边缘在 r≈206)
    print("\n[2] 外圈蓝外缘 B-R 陡降沿 (r∈[196,218]):")
    rs, pr = chan(im, cx, cy, 196.0, 218.0, "BR")
    r_blue_th = edge(rs, pr, -1)
    R_blue_med = float(np.median(r_blue_th))
    print(f"    中位数 R={R_blue_med:.2f}px  均值 R={r_blue_th.mean():.2f}px  "
          f"std={r_blue_th.std():.2f}px")

    # 2.5) 用外圈蓝边缘的一阶谐波再收紧圆心 (该边缘 std 最小, 最可信)
    th = np.linspace(0, 2 * np.pi, N_ANG, endpoint=False)
    A = np.column_stack([np.ones(N_ANG), np.cos(th), np.sin(th)])
    c, *_ = np.linalg.lstsq(A, r_blue_th, rcond=None)
    cx -= c[1]
    cy -= c[2]
    rs, pr = chan(im, cx, cy, 196.0, 218.0, "BR")
    r_blue_th = edge(rs, pr, -1)
    c2, *_ = np.linalg.lstsq(A, r_blue_th, rcond=None)
    resid_b = r_blue_th - A @ c2
    R_blue_med = float(np.median(r_blue_th))
    print(f"    一阶谐波修正圆心 → ({cx:.2f},{cy:.2f})  重测 R={R_blue_med:.2f}px  "
          f"r(θ)残差std={resid_b.std():.2f}px")

    R_from_white = r_white / U_WHITE
    print(f"\n[3] 交叉验证: 白环口径 R = {r_white:.2f}/{U_WHITE} = {R_from_white:.2f}px  "
          f"| 外圈蓝口径 R = {R_blue_med:.2f}px  | 相对差 "
          f"{(R_blue_med - R_from_white) / R_from_white * 100:+.2f}%")

    R_final = float(np.mean([R_blue_med, R_from_white]))
    print(f"\n采用 R = {R_final:.2f}px  (两口径均值)  圆心=({cx:.2f},{cy:.2f})")

    # 3) 画核对图
    vis = Image.open(ROOT / "dev" / "_new_frame.png").convert("RGB")
    d = ImageDraw.Draw(vis)
    for u, col in [(1.0, (255, 60, 60)), (U_WHITE, (60, 255, 60)), (U_SLATE, (255, 255, 60)),
                   (U_IRIS, (0, 220, 255)), (U_DEEP, (255, 0, 255)), (U_INDIGO, (255, 140, 0))]:
        rr = u * R_final
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=col, width=2)
    vis.crop((int(cx) - 300, int(cy) - 300, int(cx) + 300, int(cy) + 300)).resize((720, 720)).save(
        ROOT / "dev" / "_calib_check.png")

    out = {"src": SRC, "t": a.t, "cx": round(float(cx), 2), "cy": round(float(cy), 2),
           "R_px": round(R_final, 2), "R_from_blue_edge": round(R_blue_med, 2),
           "R_from_white_edge": round(R_from_white, 2),
           "white_edge_resid_px": round(float(res_w), 3), "frame": [W, H]}
    pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {a.out}   核对图 -> dev/_calib_check.png")


main()
