"""为 compare.html 生成自动对齐参数。

输出:
  1. 视频中 Fairy 核心的圆心 (cx, cy) 与最外白描边半径 R_px (对应 SVG r=100)
  2. 白环呼吸的实际周期 T_meas (自相关)
  3. 呼吸相位偏移 P0 —— 让动画时间轴 = 视频时间 + P0 时白环谷峰对齐

方法:
  A. 单帧: 亮度阈值找最大连通域质心 -> 360° 射线找最外亮环(白描边) -> 最小二乘圆拟合 (两次, 剔除离群点)
  B. 序列: 以核心为中心裁剪缩放抽帧 30fps x 6s -> 逐帧径向剖面找白环外缘 u(t)
  C. w(t) 与动画模板 (不对称曲线, 谷0.13/慢升0.43/峰停0.30/快降0.13) 互相关 -> P0

用法: python compare_align.py <视频> [--out dev/align_data.json]
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

# 动画呼吸曲线参数 (2026-09-13 60fps 实测重拟合: 无平顶, 峰驻留来自缓动形状)
KEY_TIMES = [0.0, 0.155, 0.688, 1.0]
KEY_VALUES = [0.0, 0.0, 1.0, 0.0]               # 归一化: 谷=0 峰=1
KEY_SPLINES = [None, (0.3, 0.0, 0.3, 1.0), (0.5, 0.0, 1.0, 1.0), None]
T_BREATH = 0.857


def run(args):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("CMD 失败:", " ".join(args))
        print((r.stderr or "")[-1200:])
        sys.exit(1)
    return r


def extract_frame(video, t, out, crop=None, scale=None):
    vf = []
    if crop:
        x, y, w, h = crop
        vf.append(f"crop={w}:{h}:{x}:{y}")
    if scale:
        vf.append(f"scale={scale}:-2")
    args = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            "-ss", str(t), "-i", video, "-frames:v", "1"]
    if vf:
        args += ["-vf", ",".join(vf)]
    args += [out]
    run(args)
    return out


def kasa_fit(pts):
    """最小二乘圆拟合: x^2+y^2 + a x + b y + c = 0"""
    x = pts[:, 0]; y = pts[:, 1]
    A = np.column_stack([x, y, np.ones(len(x))])
    b = -(x ** 2 + y ** 2)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    a, bb, c = sol
    cx, cy = -a / 2, -bb / 2
    R = np.sqrt(cx ** 2 + cy ** 2 - c)
    return cx, cy, R


def detect_core(video, t=2.0, tmp="_align_f0.png"):
    extract_frame(video, t, tmp)
    im = np.asarray(Image.open(tmp).convert("RGB")).astype(np.float32)
    L = 0.299 * im[:, :, 0] + 0.587 * im[:, :, 1] + 0.114 * im[:, :, 2]
    H, W = L.shape

    import cv2
    mask = (L > 165).astype(np.uint8)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n < 2:
        print("亮度阈值找不到连通域"); sys.exit(1)
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    bx, by, bw, bh, area = stats[idx]
    cx0, cy0 = cents[idx]
    R_est = max(bw, bh) / 2 * 1.05          # 若最大域是白描边环, bbox 即直径
    print(f"初始: 质心=({cx0:.1f},{cy0:.1f}) bbox={bw}x{bh} R_est={R_est:.1f}")

    def ray_points(cx, cy, r_lo, r_hi):
        pts = []
        for deg in range(0, 360, 2):
            a = np.deg2rad(deg)
            rs = np.arange(r_lo, r_hi, 1.0)
            xs = np.clip(np.round(cx + rs * np.cos(a)).astype(int), 0, W - 1)
            ys = np.clip(np.round(cy + rs * np.sin(a)).astype(int), 0, H - 1)
            lv = L[ys, xs]
            hit = np.where((lv > 165) & (np.roll(lv, 1) > 165))[0]
            if len(hit):
                pts.append((cx + rs[hit[-1]] * np.cos(a), cy + rs[hit[-1]] * np.sin(a)))
        return np.array(pts)

    def fit_at(cx, cy, R0):
        cx, cy, R = cx, cy, R0
        for it in range(2):
            pts = ray_points(cx, cy, R * 0.94, R * 1.06)
            if len(pts) < 90:
                return None
            cx, cy, R = kasa_fit(pts)
            d = np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - R
            keep = np.abs(d) < max(3.0, 2.5 * d.std())
            pts2 = pts[keep]
            if len(pts2) < 90:
                return None
            cx, cy, R = kasa_fit(pts2)
            print(f"  拟合: 圆心=({cx:.2f},{cy:.2f}) R={R:.2f}px  点数={len(pts2)} 残差std={d[keep].std():.2f}")
        return cx, cy, R

    # 第一环: 可能是白环外缘等内环, 逐层向外找真正的最外亮环(白描边 r=100)
    res = fit_at(cx0, cy0, R_est)
    if res is None:
        print("第一环拟合失败"); sys.exit(1)
    cx, cy, R = res
    for layer in range(4):
        r_lo, r_hi = R * 1.10, min(R * 1.75, min(cx, cy, W - cx, H - cy) - 2)
        pts = ray_points(cx, cy, r_lo, r_hi)
        if len(pts) < 120:
            print(f"第{layer + 1}层向外: 只有 {len(pts)} 个点, 停止 -> 最外环 R={R:.2f}px")
            break
        cx2, cy2, R2 = kasa_fit(pts)
        d = np.hypot(pts[:, 0] - cx2, pts[:, 1] - cy2) - R2
        keep = np.abs(d) < max(3.0, 2.5 * d.std())
        if keep.sum() < 120:
            print(f"第{layer + 1}层向外: 离群点过多, 停止 -> 最外环 R={R:.2f}px")
            break
        cx2, cy2, R2 = kasa_fit(pts[keep])
        if R2 < R * 1.08 or d[keep].std() > 4.0:
            print(f"第{layer + 1}层向外: R2={R2:.2f} 非可靠外环, 停止 -> 最外环 R={R:.2f}px")
            break
        cx, cy, R = cx2, cy2, R2
        print(f"第{layer + 1}层向外: 圆心=({cx:.2f},{cy:.2f}) R={R:.2f}px")
    os.remove(tmp)
    return cx, cy, R


def radial_profile(im, cx, cy, rmax, n_angles=360):
    H, W, _ = im.shape
    prof = np.zeros((rmax + 1, 3), dtype=np.float32)
    ang = np.linspace(0, 2 * np.pi, n_angles, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    for r in range(rmax + 1):
        xs = np.clip(np.round(cx + r * ca).astype(int), 0, W - 1)
        ys = np.clip(np.round(cy + r * sa).astype(int), 0, H - 1)
        prof[r] = im[ys, xs].mean(axis=0)
    return prof


def white_outer_u(im, cx, cy, Rsc):
    """白环外缘: 进入白环(L>170 武装)后第一次跌破 140, 搜索 u in [0.52, 0.78]"""
    prof = radial_profile(im, cx, cy, int(Rsc * 0.9))
    L = 0.299 * prof[:, 0] + 0.587 * prof[:, 1] + 0.114 * prof[:, 2]
    lo, hi = int(Rsc * 0.52), int(Rsc * 0.78)
    armed = False
    for r in range(lo, hi):
        if L[r] > 170:
            armed = True
        elif armed and L[r] < 140:
            return r / Rsc
    return None


def track_white(video, cx, cy, R, dur=6.0, fps=30, tmpdir="_align_frames"):
    if os.path.exists(tmpdir):
        shutil.rmtree(tmpdir)
    os.makedirs(tmpdir)
    side = int(2.4 * R) // 2 * 2
    x0 = int(cx - side / 2); y0 = int(cy - side / 2)
    args = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            "-t", str(dur), "-i", video,
            "-vf", f"crop={side}:{side}:{x0}:{y0},scale=360:-2",
            "-r", str(fps), os.path.join(tmpdir, "f_%05d.png")]
    run(args)
    files = sorted(glob.glob(os.path.join(tmpdir, "f_*.png")))
    print(f"追踪帧: {len(files)} 张 (crop {side}px @({x0},{y0}) -> 360px)")
    Rsc = R * 360 / side
    ts, us = [], []
    for i, fp in enumerate(files):
        im = np.asarray(Image.open(fp).convert("RGB")).astype(np.float32)
        u = white_outer_u(im, im.shape[1] / 2, im.shape[0] / 2, Rsc)
        if u is not None:
            ts.append(i / fps)
            us.append(u)
    if len(us) < 30:
        print(f"有效追踪点过少: {len(us)}/{len(files)}"); sys.exit(1)
    us = np.array(us); ts = np.array(ts)
    print(f"白环外缘 u: mean={us.mean():.4f} min={us.min():.4f} max={us.max():.4f} "
          f"极差={(us.max() - us.min()) / us.mean() * 100:.2f}%  有效 {len(us)}/{len(files)}")
    return ts, us


def bezier_ease(p, x):
    """cubic-bezier(p1x,p1y,p2x,p2y) 在横坐标 x 处的纵坐标"""
    x1, y1, x2, y2 = p
    lo_t, hi_t = 0.0, 1.0
    for _ in range(40):
        t = (lo_t + hi_t) / 2
        bx = 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t ** 2 * x2 + t ** 3
        if bx < x:
            lo_t = t
        else:
            hi_t = t
    t = (lo_t + hi_t) / 2
    return 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t ** 2 * y2 + t ** 3


def template(tau, T):
    """动画 scale 归一化曲线: tau in [0,T) -> 0(谷)..1(峰)"""
    k = (tau % T) / T
    for i in range(len(KEY_TIMES) - 1):
        if k <= KEY_TIMES[i + 1] or i == len(KEY_TIMES) - 2:
            span = KEY_TIMES[i + 1] - KEY_TIMES[i]
            x = (k - KEY_TIMES[i]) / span
            v0, v1 = KEY_VALUES[i], KEY_VALUES[i + 1]
            if v0 == v1:
                return v0
            sp = KEY_SPLINES[i] or (0, 0, 1, 1)
            return v0 + (v1 - v0) * bezier_ease(sp, min(max(x, 0), 1))
    return 0.0


def align_phase(ts, us):
    w = (us - us.min()) / max(us.max() - us.min(), 1e-6)
    t0, t1 = ts[0], ts[-1]
    n = len(ts)
    dt = (t1 - t0) / (n - 1)
    # 自相关测周期
    wz = w - w.mean()
    ac = np.correlate(wz, wz, "full")[n - 1:]
    lag_min = int(0.4 / dt)
    pk = lag_min + int(np.argmax(ac[lag_min:int(1.4 / dt)]))
    T_meas = pk * dt
    print(f"自相关主周期: {T_meas:.3f}s (设定 {T_BREATH}s)")

    best_P, best_c = 0.0, -2
    grid = np.linspace(0, T_meas, 129)[:-1]
    for P in grid:
        tpl = np.array([template(t + P, T_meas) for t in ts])
        c = np.corrcoef(wz, tpl - tpl.mean())[0, 1]
        if c > best_c:
            best_c, best_P = c, P
    # 抛物线细化
    i = int(np.argmin(np.abs(grid - best_P)))
    if 0 < i < len(grid) - 1:
        Ps = grid[i - 1:i + 2]
        tpl = [np.array([template(t + P, T_meas) for t in ts]) for P in Ps]
        cs = [np.corrcoef(wz, tp - tp.mean())[0, 1] for tp in tpl]
        denom = (cs[0] - 2 * cs[1] + cs[2])
        if abs(denom) > 1e-9:
            off = 0.5 * (cs[0] - cs[2]) / denom * (grid[1] - grid[0])
            best_P += off
    print(f"最佳相位偏移 P0={best_P % T_meas:.4f}s (相关系数 {best_c:.3f})")
    return T_meas, best_P % T_meas, best_c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default="dev/align_data.json")
    a = ap.parse_args()

    cx, cy, R = detect_core(a.video)
    ts, us = track_white(a.video, cx, cy, R)
    T_meas, P0, corr = align_phase(ts, us)

    data = {"cx": round(cx, 2), "cy": round(cy, 2), "R_px": round(R, 2),
            "T_meas": round(T_meas, 4), "P0": round(P0, 4), "corr": round(corr, 4),
            "video_w": 1920, "video_h": 1080}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(json.dumps(data, ensure_ascii=False))
    print(f"-> {a.out}")
    shutil.rmtree("_align_frames", ignore_errors=True)


if __name__ == "__main__":
    main()
