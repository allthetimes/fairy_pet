# -*- coding: utf-8 -*-
# 尖角角度分析 v2：正确的半径范围（尖角在白盘外缘 ~85-140px 处）
import os, math, collections
from PIL import Image

BASE = r'D:\work\fairy-pet'
D = os.path.join(BASE, 'frames_hifps2')
files = sorted(f for f in os.listdir(D) if f.endswith('.png'))
CX, CY = 890, 301

def angle_hist(idx, rmin=80, rmax=150, verbose=True):
    img = Image.open(os.path.join(D, files[idx])).convert('RGB')
    px = img.load()
    hist = collections.Counter()
    total = 0
    for y in range(CY-rmax, CY+rmax):
        for x in range(CX-rmax, CX+rmax):
            dx, dy = x-CX, y-CY
            d = math.hypot(dx, dy)
            if not (rmin <= d <= rmax):
                continue
            r, g, b = px[x, y]
            # 尖角色：深蓝紫，比白盘深，比亮蓝外环暗
            if r < 95 and g < 105 and 120 < b < 220:
                a = math.degrees(math.atan2(-(y-CY), x-CX))
                if a < 0: a += 360
                hist[int(a/5)*5] += 1
                total += 1
    if verbose:
        print(f'\n=== 帧 {idx} (t={idx/60:.2f}s) 尖角像素 {total}，半径 {rmin}-{rmax} ===')
        # 找局部峰（每 5° 桶，找连续段的峰）
        smooth = {}
        for a in range(0, 360, 5):
            smooth[a] = sum(hist.get((a+o) % 360, 0) for o in [-10,-5,0,5,10])
        peaks = []
        for a in range(0, 360, 5):
            v = smooth[a]
            if v >= 60 and v >= max(smooth.get((a+o) % 360, 0) for o in [-15,-10,-5,0,5,10,15]):
                peaks.append((a, v))
        # 合并相邻
        merged = []
        for a, v in peaks:
            if merged and (a - merged[-1][0]) % 360 <= 20:
                if v > merged[-1][1]: merged[-1] = (a, v)
            else:
                merged.append((a, v))
        print('  尖角方向（度，0=右 90=上 180=左 270=下）:', ', '.join(f'{a}°(强度{v})' for a, v in merged))
        print('  尖角数量:', len(merged))
        if len(merged) > 1:
            gaps = [(merged[(i+1) % len(merged)][0] - merged[i][0]) % 360 for i in range(len(merged))]
            print('  相邻间隔:', gaps)
    return total

for idx in [60, 180, 300, 420, 540, 660, 780, 870]:
    angle_hist(idx)