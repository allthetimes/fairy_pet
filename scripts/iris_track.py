"""精确追踪 A 状态（睁眼）下虹膜各圆圈的径向边界随时间的变化。

方法:
1. 用 Hough 找外圈圆心 + 半径
2. 每帧做 360 度径向扫描, 对每个半径 r 统计平均颜色
3. 用颜色特征 (B-R, 亮度) 识别每层边界
4. 输出每帧的各层边界 u 值, 观察呼吸脉冲

用法: python iris_track.py <帧目录> [--out out.csv]
"""
import argparse
import glob
import os
import numpy as np
from PIL import Image
import cv2


def radial_profile(im, cx, cy, rmax, n_angles=360):
    """返回 (rmax+1,) 的平均颜色 [R,G,B] 数组, 每个半径取 n_angles 个角度平均"""
    H, W, _ = im.shape
    prof = np.zeros((rmax + 1, 3), dtype=np.float32)
    for r in range(0, rmax + 1):
        ang = np.linspace(0, 2 * np.pi, n_angles, endpoint=False)
        xs = np.clip(np.round(cx + r * np.cos(ang)).astype(int), 0, W - 1)
        ys = np.clip(np.round(cy + r * np.sin(ang)).astype(int), 0, H - 1)
        prof[r] = im[ys, xs].mean(axis=0)
    return prof


def find_boundaries(prof):
    """从径向剖面找层边界 (颜色突变点)。返回边界半径列表。"""
    R = prof[:, 0]
    G = prof[:, 1]
    B = prof[:, 2]
    L = 0.299 * R + 0.587 * G + 0.114 * B
    BR = B - R  # 蓝色度

    # 用 B-R 和 L 的组合找边界
    n = len(prof)
    # 找 B-R 的局部突变（层边界）
    dBR = np.abs(np.diff(BR))
    # 平滑
    k = 3
    kernel = np.ones(k) / k
    dBR_s = np.convolve(dBR, kernel, mode='same')

    boundaries = []
    # 找 dBR_s 的峰值（> 阈值的局部极大）
    thr = dBR_s.max() * 0.25
    for r in range(5, n - 5):
        if dBR_s[r] > thr and dBR_s[r] == dBR_s[max(0, r-3):r+4].max():
            boundaries.append(r)
    # 归并相邻
    merged = []
    for b in boundaries:
        if not merged or b - merged[-1] > 8:
            merged.append(b)
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('frame_dir')
    ap.add_argument('--out', default='analysis/iris_track_result.csv')
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.frame_dir, 'f_*.png')))
    print(f'共 {len(files)} 帧')

    # 第一帧找圆心
    im0 = np.asarray(Image.open(files[0]).convert('RGB')).astype(np.float32)
    gray = cv2.cvtColor(im0.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1, minDist=400,
                                param1=80, param2=30, minRadius=300, maxRadius=500)
    circles = sorted(circles[0], key=lambda c: -c[2])
    cx, cy, R = circles[0]
    print(f'圆心=({cx:.0f}, {cy:.0f}), R={R:.0f}')

    # 先看第一帧的剖面, 识别层
    prof0 = radial_profile(im0, cx, cy, int(R * 0.75))
    L0 = 0.299 * prof0[:, 0] + 0.587 * prof0[:, 1] + 0.114 * prof0[:, 2]
    BR0 = prof0[:, 2] - prof0[:, 0]

    # 打印第一帧剖面 (每隔 20px)
    print('\n第一帧径向剖面 (u = r/R):')
    print(f"{'u':>6} {'R':>5} {'G':>5} {'B':>5} {'L':>7} {'B-R':>7}")
    for i in range(0, len(prof0), 20):
        u = i / R
        r, g, b = prof0[i]
        print(f"{u:6.3f} {int(r):5d} {int(g):5d} {int(b):5d} {L0[i]:7.1f} {BR0[i]:7.1f}")

    # 识别关键层边界（用颜色特征）
    # 层: 外圈蓝(高BR), 白环(高L), 灰紫蓝(中BR), 蓝瞳(高BR), 深眼(低L)
    print('\n关键层边界估计:')
    # 白环外缘: L 从低到高的跳变 (从圆心向外找第一个 L>180)
    white_outer = None
    for r in range(int(R * 0.2), int(R * 0.8)):
        if L0[r] > 180 and L0[r-1] <= 180:
            white_outer = r
            break
    # 白环内缘: L 从高到低的跳变
    white_inner = None
    if white_outer:
        for r in range(white_outer + 1, int(R * 0.9)):
            if L0[r] < 150:
                white_inner = r
                break
    # 深眼外缘: L 从高到低 (低 L < 60)
    pupil_outer = None
    for r in range(int(R * 0.1), int(R * 0.6)):
        if L0[r] < 60:
            pupil_outer = r
            break

    print(f'白环外缘 u = {white_outer/R if white_outer else 0:.3f}')
    print(f'白环内缘 u = {white_inner/R if white_inner else 0:.3f}')
    print(f'深眼外缘 u = {pupil_outer/R if pupil_outer else 0:.3f}')

    # 追踪每帧的这些边界
    print('\n各帧边界追踪:')
    header = ['frame', 'white_outer_u', 'white_inner_u', 'pupil_outer_u']
    rows = []
    for fp in files:
        im = np.asarray(Image.open(fp).convert('RGB')).astype(np.float32)
        prof = radial_profile(im, cx, cy, int(R * 0.75))
        L = 0.299 * prof[:, 0] + 0.587 * prof[:, 1] + 0.114 * prof[:, 2]
        BR = prof[:, 2] - prof[:, 0]

        # 白环外缘
        wo = None
        for r in range(int(R * 0.2), min(int(R * 0.8), len(L) - 1)):
            if L[r] > 180 and L[r-1] <= 180:
                wo = r
                break
        # 白环内缘
        wi = None
        if wo:
            for r in range(wo + 1, min(int(R * 0.9), len(L) - 1)):
                if L[r] < 150:
                    wi = r
                    break
        # 深眼外缘
        po = None
        for r in range(int(R * 0.1), min(int(R * 0.6), len(L) - 1)):
            if L[r] < 60:
                po = r
                break

        fn = os.path.basename(fp)
        rows.append({
            'frame': fn,
            'wo': wo / R if wo else None,
            'wi': wi / R if wi else None,
            'po': po / R if po else None,
        })
        print(f"{fn}: 白环外={wo/R if wo else 0:.3f}, 白环内={wi/R if wi else 0:.3f}, 深眼外={po/R if po else 0:.3f}")

    # 写 CSV
    with open(a.out, 'w') as f:
        f.write('frame,white_outer_u,white_inner_u,pupil_outer_u\n')
        for r in rows:
            f.write(f"{r['frame']},{r['wo'] or ''},{r['wi'] or ''},{r['po'] or ''}\n")
    print(f'\n结果 -> {a.out}')


if __name__ == '__main__':
    main()