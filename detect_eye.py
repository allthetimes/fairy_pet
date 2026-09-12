# -*- coding: utf-8 -*-
# 逐帧检测 Fairy 眼睛：亮蓝外环 (#2D3FE8 系) 像素聚类 + 中心白盘验证
import os
from PIL import Image

BASE = r'D:\work\fairy-pet'

def detect(img):
    """返回 (cx, cy, r_est, blue_cnt, white_ratio) 或 None"""
    im = img.convert('RGB')
    W, H = im.size
    px = im.load()
    step = max(1, min(W, H) // 240)  # 降采样
    xs, ys = [], []
    for y in range(0, H, step):
        for x in range(0, W, step):
            r, g, b = px[x, y]
            # 亮蓝：蓝显著高于红绿
            if b > 150 and b - r > 110 and b - g > 70 and g < 130:
                xs.append(x); ys.append(y)
    if len(xs) < 40:
        return None
    # 聚类：取包围盒
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = x1 - x0, y1 - y0
    if w < 30 or h < 30:      # 太小
        return None
    if w > W * 0.9 or h > H * 0.9:  # 满屏蓝（界面背景），不可用
        return None
    if not (0.5 < w / h < 2.0):     # 眼睛应近方形包围盒
        return None
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    r_est = (w + h) / 4
    # 中心区域白盘验证：内接 60% 区域
    rr = int(r_est * 0.6)
    white = tot = 0
    for y in range(max(0, cy - rr), min(H, cy + rr), max(1, step)):
        for x in range(max(0, cx - rr), min(W, cx + rr), max(1, step)):
            r, g, b = px[x, y]
            tot += 1
            if r > 150 and g > 150 and b > 150:
                white += 1
    if tot == 0:
        return None
    wr = white / tot
    if wr < 0.12:            # 中心必须有白盘
        return None
    return cx, cy, r_est, len(xs), wr

for outdir, fps in [('frames_egg', 2.0), ('frames_voice', 2.0)]:
    d = os.path.join(BASE, outdir)
    files = sorted(f for f in os.listdir(d) if f.endswith('.jpg'))
    hits = []
    for f in files:
        img = Image.open(os.path.join(d, f))
        res = detect(img)
        if res:
            t = int(f[1:6]) / fps
            hits.append((t, f) + res)
    print(f'== {outdir}: {len(hits)}/{len(files)} frames with eye ==')
    # 打印摘要：连续段
    if hits:
        runs = []
        cur = [hits[0]]
        for h in hits[1:]:
            if h[0] - cur[-1][0] <= 1.6:
                cur.append(h)
            else:
                runs.append(cur); cur = [h]
        runs.append(cur)
        for run in runs:
            if len(run) >= 3:
                rads = [x[4] for x in run]
                print(f'  t={run[0][0]:6.1f}-{run[-1][0]:6.1f}s  n={len(run):3d}  '
                      f'c=({sum(x[2] for x in run)//len(run)},{sum(x[3] for x in run)//len(run)})  '
                      f'r~{sum(rads)/len(rads):.0f}')
