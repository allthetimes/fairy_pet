"""全面精测: 各环边界半径 / 每环呼吸幅度与相位 / 高光球 / 齿轮转速与相位。

在 compare_align.py 的圆心/半径基础上:
  1. 双线性亚像素径向剖面 (720角 x 0.5px步进), 平滑梯度求边缘 (无阈值偏置)
  2. 逐边缘序列 -> 均值/幅度/与模板互相关的相位差
  3. 高光球: 自适应阈值的亮斑质心+等效半径
  4. 齿轮: r=0.85u 角向亮度剖面找齿峰, 逐帧解卷绕, 线性拟合 -> 转速/初相

用法: python measure_all.py <视频> [--out dev/measure_all.json]
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
    ker = np.ones(k) / k
    return np.convolve(x, ker, mode="same")


def bilin_profile(im, cxl, cyl, rmax, n_ang=720, step=0.5):
    """双线性插值的亚像素径向剖面, 返回 (rs, prof[n_r,3])"""
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


def grad_edge(u, sig, lo, hi, mode):
    """在 u∈[lo,hi] 内找平滑梯度的极值点 (mode: +升边 -降边)"""
    m = (u >= lo) & (u <= hi)
    g = sig[m]
    return u[m][int(np.argmax(g if mode > 0 else -g))]


def phase_lag(ts, us, T, P0, half=0.45):
    """u(t) 相对模板(t+P0)的滞后 Δ: template(t+P0+Δ) 最匹配"""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default="dev/measure_all.json")
    a = ap.parse_args()

    ALIGN = json.load(open("dev/align_data.json", encoding="utf-8"))
    cx, cy, R = ALIGN["cx"], ALIGN["cy"], ALIGN["R_px"]
    T, P0 = ALIGN["T_meas"], ALIGN["P0"]

    # ---- 抽帧: 核心周边 540px 原生分辨率, 30fps x 4s ----
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

    CLX, CLY = side / 2, side / 2
    edges = {"深眼外缘": [], "蓝瞳外缘": [], "灰紫蓝外缘": [], "白环外缘": [], "靛蓝外缘": []}
    ts, glints = [], []
    gear_theta = []

    for i, fp in enumerate(files):
        im = np.asarray(Image.open(fp).convert("RGB")).astype(np.float32)
        rs, prof = bilin_profile(im, CLX, CLY, 240)
        L = 0.299 * prof[:, 0] + 0.587 * prof[:, 1] + 0.114 * prof[:, 2]
        BR = prof[:, 2] - prof[:, 0]
        u = rs / R
        Ls = smooth(L, 5); BRs = smooth(BR, 5)
        dL = np.gradient(Ls); dBR = np.gradient(BRs)

        edges["深眼外缘"].append(grad_edge(u, dL, 0.14, 0.28, +1))
        edges["蓝瞳外缘"].append(grad_edge(u, dBR, 0.24, 0.38, -1))
        edges["灰紫蓝外缘"].append(grad_edge(u, dL, 0.38, 0.52, +1))
        edges["白环外缘"].append(grad_edge(u, dL, 0.56, 0.72, -1))
        edges["靛蓝外缘"].append(grad_edge(u, dBR, 0.70, 0.85, -1))
        ts.append(i / 30.0)

        # 高光球: 亮斑质心 (中心区域内自适应阈值)
        r_grid = rs[rs < 0.72 * R]
        ys, xs = np.mgrid[0:side, 0:side]
        rr = np.hypot(ys - CLY, xs - CLX)
        Limg = 0.299 * im[:, :, 0] + 0.587 * im[:, :, 1] + 0.114 * im[:, :, 2]
        m = (rr < 0.72 * R)
        thr = max(225.0, float(Limg[m].max()) - 12)
        g = m & (Limg > thr)
        if g.sum() > 30:
            gxs, gys = xs[g], ys[g]
            gx, gy = gxs.mean(), gys.mean()
            glints.append(((gx - CLX) / R, (gy - CLY) / R, np.sqrt(g.sum() / np.pi) / R))
        else:
            glints.append(None)

        # 齿轮: r=0.85u 角向亮度
        r_gear = 0.85 * R
        ang = np.linspace(0, 2 * np.pi, 720, endpoint=False)
        xg = CLX + r_gear * np.cos(ang); yg = CLY + r_gear * np.sin(ang)
        xg2 = np.clip(np.round(xg).astype(int), 0, side - 1)
        yg2 = np.clip(np.round(yg).astype(int), 0, side - 1)
        Lg = smooth(0.299 * im[yg2, xg2, 0] + 0.587 * im[yg2, xg2, 1] + 0.114 * im[yg2, xg2, 2], 9)
        gear_theta.append(Lg)

    # ---- 边缘统计 ----
    print(f"\n{'边缘':<8} {'均值u':>8} {'SVG半径':>8} {'极差%':>7} {'相位Δs':>8} {'相关':>6}")
    out = {"R_px": R, "cx": cx, "cy": cy, "T": T, "P0": P0, "rings": {}}
    for name, arr in edges.items():
        v = np.array(arr)
        rng = (v.max() - v.min()) / v.mean() * 100
        d, c = phase_lag(np.array(ts), v, T, P0)
        svg_r = v.mean() * 100
        print(f"{name:<8} {v.mean():8.4f} {svg_r:8.2f} {rng:7.2f} {d:8.3f} {c:6.3f}")
        out["rings"][name] = {"u": round(float(v.mean()), 4), "svg_r": round(float(svg_r), 2),
                              "range_pct": round(float(rng), 2), "lag": round(d, 3), "corr": round(c, 3)}

    # ---- 高光球 ----
    gl = [g for g in glints if g]
    if gl:
        garr = np.array(gl)
        out["glint"] = {"dx_u": round(float(garr[:, 0].mean()), 4), "dy_u": round(float(garr[:, 1].mean()), 4),
                        "r_u": round(float(garr[:, 2].mean()), 4), "n": len(gl)}
        print(f"\n高光球: 偏移=({garr[:, 0].mean():+.4f}, {garr[:, 1].mean():+.4f})u "
              f"半径={garr[:, 2].mean():.4f}u  (SVG: cx={garr[:, 0].mean() * 100:.1f} cy={garr[:, 1].mean() * 100:.1f} "
              f"r={garr[:, 2].mean() * 100:.1f}, 有效帧 {len(gl)}/{len(glints)})")
    else:
        print("\n高光球: 未检出")

    # ---- 齿轮: 角向剖面解卷绕 ----
    G = np.array(gear_theta)                    # [n帧, 720角]
    Gc = G - G.mean(axis=1, keepdims=True)
    # 每帧找峰 (4个): 简单办法 — 用复数傅里叶: 4次谐波的相位即齿的角度
    n_ang = G.shape[1]
    four = (Gc * np.exp(-1j * 4 * np.arange(n_ang) * 2 * np.pi / n_ang)).sum(axis=1)
    ph = np.angle(four) / 4                     # 齿方向角 (rad, mod 90°)
    mag = np.abs(four)
    # 解卷绕 (mod 90° -> 连续), 帧间旋转 < 45°
    unw = np.unwrap(ph)                         # rad
    tt = np.array(ts)
    k = np.polyfit(tt, unw, 1)                  # rad/s
    omega_deg = np.degrees(k[0])
    period_full = 360.0 / abs(omega_deg) if abs(omega_deg) > 1e-3 else float("inf")
    phi0_deg = np.degrees(k[1])                 # t=0 时的齿角
    resid = np.degrees(unw - np.polyval(k, tt))
    print(f"\n齿轮: 角速度={omega_deg:+.2f}°/s 方向={'顺时针' if omega_deg > 0 else '逆时针'} "
          f"整圈周期={period_full:.2f}s 相位(t=0)={phi0_deg:.1f}° 拟合残差std={resid.std():.2f}° 谐波强度={mag.mean():.1f}")
    out["gear"] = {"omega_deg_s": round(float(omega_deg), 3), "period_s": round(float(period_full), 3),
                   "phase0_deg": round(float(phi0_deg % 90), 2)}
    # 我的 SMIL: 顺时针 from0->360. begin = P0 - phi0/omega (deg), 归一到 [0, dur)
    if abs(omega_deg) > 1e-3:
        if omega_deg > 0:
            dur = 360.0 / omega_deg
            begin = (P0 - phi0_deg / omega_deg) % dur
            out["gear"].update({"dir": "cw", "dur": round(dur, 3), "begin": round(float(begin), 3)})
            print(f"  -> SMIL: dur={dur:.2f}s begin={begin:.2f}s (顺时针)")
        else:
            dur = 360.0 / -omega_deg
            begin = (P0 + phi0_deg / -omega_deg) % dur
            out["gear"].update({"dir": "ccw", "dur": round(dur, 3), "begin": round(float(begin), 3)})
            print(f"  -> SMIL: dur={dur:.2f}s begin={begin:.2f}s (需逆时针 from 0 to -360)")

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n-> {a.out}")
    shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
