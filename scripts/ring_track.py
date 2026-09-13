"""逐环精确测量 A 状态虹膜各环的独立呼吸运动。

方法:
1. 用第一帧的最外圈(不动)拟合圆心, 之后所有帧都用这个固定圆心
2. 每帧做 360 度径向扫描, 得到径向亮度/颜色剖面
3. 用梯度 + 颜色特征识别每个环边界:
   - 外圈蓝外缘 r=100 (应不动)
   - 白环外缘 r=64.5
   - 白环内缘=灰紫蓝外缘 r=44.7
   - 灰紫蓝内缘=蓝瞳外缘 r=30.6
   - 蓝瞳内缘=深眼外缘 r=21.5 (小白边描边附近)
4. 输出每帧每环边界 u, 看独立运动

用法: python ring_track.py <帧目录> [--out out.csv]
"""
import argparse
import glob
import os
import numpy as np
from PIL import Image
import cv2


def radial_profile(im, cx, cy, rmax, n_angles=720):
    """360 度平均径向剖面, 返回 (rmax+1, 3)"""
    H, W, _ = im.shape
    prof = np.zeros((rmax + 1, 3), dtype=np.float32)
    ang = np.linspace(0, 2 * np.pi, n_angles, endpoint=False)
    cos_a = np.cos(ang)
    sin_a = np.sin(ang)
    for r in range(0, rmax + 1):
        xs = np.clip(np.round(cx + r * cos_a).astype(int), 0, W - 1)
        ys = np.clip(np.round(cy + r * sin_a).astype(int), 0, H - 1)
        prof[r] = im[ys, xs].mean(axis=0)
    return prof


def find_ring_boundaries(prof):
    """从剖面找各环边界。返回 dict {名字: 半径}。"""
    R = prof[:, 0]
    G = prof[:, 1]
    B = prof[:, 2]
    L = 0.299 * R + 0.587 * G + 0.114 * B
    BR = B - R
    n = len(prof)

    # 平滑梯度
    dL = np.abs(np.diff(L))
    k = 5
    kernel = np.ones(k) / k
    dL_s = np.convolve(dL, kernel, mode='same')

    bounds = {}

    # 深眼外缘: L 从低到高的跳变 (深蓝 -> 蓝瞳), u 约 0.15-0.25
    for r in range(5, int(n * 0.4)):
        if L[r] > 80 and L[r - 1] <= 80:
            bounds['深眼外缘'] = r
            break

    # 蓝瞳外缘: L 从高到再高 (蓝瞳 -> 灰紫蓝), u 约 0.28-0.35
    # 找 B-R 的下降 (蓝瞳 B-R 高 ~129, 灰紫蓝 B-R 中 ~60)
    for r in range(int(n * 0.2), int(n * 0.45)):
        if BR[r] < 110 and BR[r - 1] >= 110:
            bounds['蓝瞳外缘'] = r
            break

    # 灰紫蓝外缘: L 从 150 -> 205 (灰紫蓝 -> 白环), u 约 0.39-0.42
    for r in range(int(n * 0.3), int(n * 0.55)):
        if L[r] > 195 and L[r - 1] <= 195:
            bounds['灰紫蓝外缘'] = r
            break

    # 白环外缘: L 从 205 -> 88 (白环 -> 靛蓝), u 约 0.60-0.65
    for r in range(int(n * 0.5), int(n * 0.75)):
        if L[r] < 150 and L[r - 1] >= 150:
            bounds['白环外缘'] = r
            break

    # 靛蓝外缘: B-R 从高到低 (靛蓝 -> 外圈蓝), u 约 0.78
    # 找 B-R 的峰值突变
    for r in range(int(n * 0.6), int(n * 0.9)):
        if BR[r] < 60 and BR[r - 1] >= 60:
            bounds['靛蓝外缘'] = r
            break

    # 外圈蓝外缘: L 从高到低 (外蓝 -> 背景), u 约 0.95-1.0
    for r in range(int(n * 0.8), n - 1):
        if L[r] < 100 and L[r - 1] >= 100:
            bounds['外圈蓝外缘'] = r
            break

    return bounds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('frame_dir')
    ap.add_argument('--out', default='analysis/ring_track_result.csv')
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.frame_dir, 'f_*.png')))
    print(f'共 {len(files)} 帧')

    # 第一帧找圆心 (最外圈不动)
    im0 = np.asarray(Image.open(files[0]).convert('RGB')).astype(np.float32)
    gray = cv2.cvtColor(im0.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (7, 7), 0)
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1, minDist=1000,
                                param1=80, param2=30, minRadius=600, maxRadius=1000)
    if circles is None:
        # 降级：用亮区质心
        print('Hough 失败, 用质心法')
        L = 0.299 * im0[:, :, 0] + 0.587 * im0[:, :, 1] + 0.114 * im0[:, :, 2]
        ys, xs = np.where(L > 200)
        cx, cy = xs.mean(), ys.mean()
        R = 750
    else:
        circles = sorted(circles[0], key=lambda c: -c[2])
        cx, cy, R = circles[0]
    print(f'固定圆心=({cx:.1f}, {cy:.1f}), R={R:.1f}')

    # 第一帧详细剖面
    prof0 = radial_profile(im0, cx, cy, int(R))
    L0 = 0.299 * prof0[:, 0] + 0.587 * prof0[:, 1] + 0.114 * prof0[:, 2]
    BR0 = prof0[:, 2] - prof0[:, 0]
    print(f'\n第一帧剖面 (每 40px):')
    print(f"{'u':>6} {'R':>5} {'G':>5} {'B':>5} {'L':>7} {'B-R':>7}")
    for i in range(0, int(R), 40):
        u = i / R
        r, g, b = prof0[i]
        print(f"{u:6.3f} {int(r):5d} {int(g):5d} {int(b):5d} {L0[i]:7.1f} {BR0[i]:7.1f}")

    # 第一帧边界
    bounds0 = find_ring_boundaries(prof0)
    print(f'\n第一帧边界 (u = r/R):')
    for name, r in bounds0.items():
        print(f'  {name}: u={r/R:.4f}  r={r}px')

    # 追踪所有帧
    print(f'\n逐环追踪:')
    all_keys = ['深眼外缘', '蓝瞳外缘', '灰紫蓝外缘', '白环外缘', '靛蓝外缘', '外圈蓝外缘']
    results = []
    for fp in files:
        im = np.asarray(Image.open(fp).convert('RGB')).astype(np.float32)
        prof = radial_profile(im, cx, cy, int(R))
        bounds = find_ring_boundaries(prof)
        fn = os.path.basename(fp)
        row = {'frame': fn}
        for k in all_keys:
            row[k] = bounds.get(k, None)
        results.append(row)

    # 输出表
    header = ['frame'] + all_keys
    print(f"{'frame':>10} " + " ".join(f"{k[:4]:>8}" for k in all_keys))
    for row in results:
        vals = []
        for k in all_keys:
            v = row[k]
            vals.append(f"{v/R if v is not None else 0:.3f}")
        print(f"{row['frame']:>10} " + " ".join(f"{v:>8}" for v in vals))

    # 写 CSV
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write(','.join(header) + '\n')
        for row in results:
            vals = [row['frame']] + [str(row[k] / R) if row[k] is not None else '' for k in all_keys]
            f.write(','.join(vals) + '\n')
    print(f'\n结果 -> {a.out}')


if __name__ == '__main__':
    main()