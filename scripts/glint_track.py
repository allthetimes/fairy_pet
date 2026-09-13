"""高光球轨迹追踪: 60fps 全片逐帧测质心, 频谱+正弦拟合分析漂移规律。

背景: compare.html/fairy-lab.html 里的 7s 漂移路线 (0 0 -> -2.5 -3.5 -> 2 2)
是当初目测编的, 从未实测。本脚本把原版高光的真实运动测出来。

检测: 眼内 r<0.40R 窗口, 阈值 max-10, 取最大连通域质心 (cv2)。
输出: dev/glint_track.json + 轨迹图 dev/glint_track.png

用法: python glint_track.py <视频> [--out dev/glint_track.json]
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

SVG_PX = None  # R/100, 运行时算


def luma(im):
    return 0.299 * im[:, :, 0].astype(np.float32) + 0.587 * im[:, :, 1] + 0.114 * im[:, :, 2]


def detect_glint(crop, ecx, ecy, rmax):
    """返回 (gx, gy, r_area, Lpeak) 或 None。坐标为 crop 内绝对像素。"""
    L = luma(crop)
    ys, xs = np.mgrid[0:L.shape[0], 0:L.shape[1]]
    rr = np.hypot(ys - ecy, xs - ecx)
    m = rr < rmax
    if not m.any():
        return None
    thr = L[m].max() - 10
    g = (m & (L > thr)).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(g, 8)
    if n < 2:
        return None
    best = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    area = stats[best, cv2.CC_STAT_AREA]
    if area < 40:
        return None
    mx = lab == best
    gx = xs[mx].mean(); gy = ys[mx].mean()
    r_area = float(np.sqrt(area / np.pi))
    return float(gx), float(gy), r_area, float(L[m].max())


def despike(t, v, k=5, nsig=4.0):
    """中值滤波去尖刺: 偏离中值超过 nsig*MAD 的点用中值替换。"""
    med = np.array([np.median(v[max(0, i - k):i + k + 1]) for i in range(len(v))])
    mad = np.median(np.abs(v - med)) * 1.4826 + 1e-9
    out = v.copy()
    bad = np.abs(v - med) > nsig * mad
    out[bad] = med[bad]
    return out, int(bad.sum())


def sinfit(t, v, f_grid):
    """频率网格扫描 + 线性最小二乘: v ≈ a + b*sin + c*cos。返回 (freq, a, b, c, resid)。"""
    best = None
    for f in f_grid:
        A = np.column_stack([np.ones_like(t), np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t)])
        coef, res, *_ = np.linalg.lstsq(A, v, rcond=None)
        r = float(np.sqrt(((A @ coef - v) ** 2).mean()))
        if best is None or r < best[4]:
            best = (f, float(coef[0]), float(coef[1]), float(coef[2]), r)
    return best


def fft_top(t, v, fmin=0.02, fmax=2.0):
    """均匀重采样后 FFT, 返回 (top_freq, top_power)。"""
    dt = np.median(np.diff(t))
    n = len(t)
    grid = np.arange(n) * dt
    vi = np.interp(grid, t, v)
    vi -= vi.mean()
    F = np.fft.rfft(vi * np.hanning(n))
    fr = np.fft.rfftfreq(n, dt)
    m = (fr >= fmin) & (fr <= fmax)
    idx = np.argmax(np.abs(F[m]) ** 2)
    return float(fr[m][idx]), float(np.abs(F[m][idx]) ** 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default="dev/glint_track.json")
    a = ap.parse_args()

    ALIGN = json.load(open("dev/align_data.json", encoding="utf-8"))
    cx, cy, R = ALIGN["cx"], ALIGN["cy"], ALIGN["R_px"]
    T, P0 = ALIGN["T_meas"], ALIGN["P0"]

    cap = cv2.VideoCapture(a.video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    side = 540
    x0, y0 = int(cx - side / 2), int(cy - side / 2)
    ecx = ecy = side / 2
    rmax = 0.40 * R

    rows = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        crop = frame[y0:y0 + side, x0:x0 + side]
        g = detect_glint(crop, ecx, ecy, rmax)
        if g:
            gx, gy, r_area, Lp = g
            # 转 SVG 单位 (100u = R px)
            rows.append((i / fps, (gx - ecx) / R * 100, (gy - ecy) / R * 100,
                         r_area / R * 100, Lp))
        i += 1
    cap.release()
    print(f"帧: {i} 总, {len(rows)} 检出 ({fps:.0f}fps)")

    d = np.array(rows)
    t, X, Y, RA, LP = d[:, 0], d[:, 1], d[:, 2], d[:, 3], d[:, 4]
    X, bx = despike(t, X); Y, by = despike(t, Y); RA, br = despike(t, RA)
    print(f"去尖刺: x {bx}, y {by}, r {br}")

    # 基线与摆幅
    x0m, y0m = float(np.median(X)), float(np.median(Y))
    print(f"\n基线: ({x0m:+.2f}, {y0m:+.2f})u  "
          f"x范围 [{X.min():.2f},{X.max():.2f}]  y范围 [{Y.min():.2f},{Y.max():.2f}]")

    # 频谱
    fx, px = fft_top(t, X); fy, py = fft_top(t, Y)
    print(f"FFT 主频: x {fx:.4f}Hz (P{px:.1f})  y {fy:.4f}Hz (P{py:.1f})")

    # 正弦拟合 (频率网格围绕 FFT 峰 ±30%)
    grid_x = np.linspace(max(0.02, fx * 0.7), fx * 1.3, 120)
    grid_y = np.linspace(max(0.02, fy * 0.7), fy * 1.3, 120)
    fX, aX, bX, cX, rX = sinfit(t, X, grid_x)
    fY, aY, bY, cY, rY = sinfit(t, Y, grid_y)
    ampX = np.hypot(bX, cX); ampY = np.hypot(bY, cY)
    phX = np.arctan2(cX, bX); phY = np.arctan2(cY, bY)
    print(f"X 拟合: f={fX:.4f}Hz 振幅={ampX:.2f}u 相位={np.degrees(phX):+.1f}° 残差={rX:.3f}u")
    print(f"Y 拟合: f={fY:.4f}Hz 振幅={ampY:.2f}u 相位={np.degrees(phY):+.1f}° 残差={rY:.3f}u")
    dph = np.degrees(phY - phX)
    print(f"相位差 y-x = {dph:+.1f}°  (±90°=椭圆/圆轨道, 0/180°=直线往复)")

    # 半径/亮度 vs 呼吸相位
    ph_breath = ((t + P0) % T) / T
    tm = json.load(open("dev/breath_curve.json", encoding="utf-8")) if os.path.exists(
        "dev/breath_curve.json") else None
    cR = float(np.corrcoef(ph_breath, RA)[0, 1])
    cL = float(np.corrcoef(ph_breath, LP)[0, 1])
    print(f"\n高光半径: 均值 {RA.mean():.2f}u std {RA.std():.2f}u  与呼吸相位相关 {cR:+.3f}")
    print(f"峰值亮度: 均值 {LP.mean():.1f} std {LP.std():.1f}  与呼吸相位相关 {cL:+.3f}")

    out = {
        "fps": fps, "n_frames": i, "n_valid": len(rows),
        "base_u": [round(x0m, 3), round(y0m, 3)],
        "x_range_u": [round(float(X.min()), 3), round(float(X.max()), 3)],
        "y_range_u": [round(float(Y.min()), 3), round(float(Y.max()), 3)],
        "fit_x": {"f": round(fX, 4), "amp": round(ampX, 3),
                  "phase_deg": round(float(np.degrees(phX)), 1), "resid": round(rX, 3)},
        "fit_y": {"f": round(fY, 4), "amp": round(ampY, 3),
                  "phase_deg": round(float(np.degrees(phY)), 1), "resid": round(rY, 3)},
        "phase_diff_deg": round(float(dph), 1),
        "r_area_mean_u": round(float(RA.mean()), 3),
        "r_area_std_u": round(float(RA.std()), 3),
        "corr_r_breath": round(cR, 3), "corr_L_breath": round(cL, 3),
        "track": [[round(float(tt), 4), round(float(xx), 3), round(float(yy), 3),
                   round(float(rr), 3)] for tt, xx, yy, rr in zip(t, X, Y, RA)],
    }
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n-> {a.out}")

    # 轨迹图 (PIL 简易散点 + 时间序列, 全部以基线为中心)
    try:
        from PIL import Image, ImageDraw
        W, H = 960, 400
        im = Image.new("RGB", (W, H), (18, 20, 28))
        dr = ImageDraw.Draw(im)
        xr = max(X.max() - X.min(), 0.5) * 1.2
        yr = max(Y.max() - Y.min(), 0.5) * 1.2
        # 左: X-Y 轨迹 (以基线为中心)
        ox, oy, sc = 180, 200, min(140.0 / xr, 140.0 / yr)
        for k in range(1, len(X)):
            c = int(255 * k / len(X))
            dr.line([ox + (X[k - 1] - x0m) * sc, oy - (Y[k - 1] - y0m) * sc,
                     ox + (X[k] - x0m) * sc, oy - (Y[k] - y0m) * sc],
                    fill=(c, 255 - c // 2, 120), width=2)
        dr.ellipse([ox - 3, oy - 3, ox + 3, oy + 3], fill=(255, 80, 80))
        dr.text((10, 8), f"X-Y trajectory rel base ({x0m:.2f},{y0m:.2f})u  grid=0.5u", fill=(220, 224, 235))
        for g in np.arange(-2, 2.01, 0.5):
            if abs(g) * sc < 160:
                dr.line([ox + g * sc, oy - 160, ox + g * sc, oy + 160], fill=(40, 44, 58))
                dr.line([ox - 160, oy + g * sc, ox + 160, oy + g * sc], fill=(40, 44, 58))
        # 右: x(t), y(t) 时间序列 (去基线, y 向翻转)
        t0, t1 = t[0], t[-1]
        gx = lambda tt: 400 + (tt - t0) / (t1 - t0) * 540
        scT = 60.0 / max(xr, yr)
        for v, base, col, mid in ((X, x0m, (90, 200, 255), 120), (Y, y0m, (255, 170, 90), 300)):
            for k in range(1, len(t)):
                dr.line([gx(t[k - 1]), mid - (v[k - 1] - base) * scT,
                         gx(t[k]), mid - (v[k] - base) * scT], fill=col, width=1)
            dr.line([400, mid, 940, mid], fill=(60, 64, 80))
        dr.text((410, 8), "x(t)-base blue / y(t)-base orange  (u)", fill=(220, 224, 235))
        im.save(os.path.splitext(a.out)[0] + ".png")
        print(f"-> {os.path.splitext(a.out)[0]}.png")
    except Exception as e:
        print("绘图跳过:", e)


if __name__ == "__main__":
    main()
