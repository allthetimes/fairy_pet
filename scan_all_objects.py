# -*- coding: utf-8 -*-
# 扫描 BV1CkcbzgEkC 0-15s 画面里所有"蓝眼睛状"物体，确认是否只有一个
import os
from PIL import Image

BASE = r'D:\work\fairy-pet'
D = os.path.join(BASE, 'frames_hifps2')
files = sorted(f for f in os.listdir(D) if f.endswith('.png'))

# 取 3 帧采样
for f in [files[10], files[300], files[700]]:
    img = Image.open(os.path.join(D, f)).convert('RGB')
    W, H = img.size
    px = img.load()
    # 蓝环像素聚类（扫描全画面，粗粒度）
    step = 8
    hits = []
    for y in range(0, H, step):
        for x in range(0, W, step):
            r, g, b = px[x, y]
            if b > 140 and b - r > 100 and b - g > 60 and g < 140:
                hits.append((x, y))
    # 简单网格聚类
    grid = {}
    for x, y in hits:
        key = (x // 200, y // 200)
        grid.setdefault(key, []).append((x, y))
    clusters = []
    for k, pts in grid.items():
        if len(pts) < 15: continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        clusters.append((len(pts), min(xs), max(xs), min(ys), max(ys)))
    clusters.sort(reverse=True)
    print(f'\n=== {f} ({W}x{H}) 蓝块 {len(hits)} 个 ===')
    for n, x0, x1, y0, y1 in clusters[:8]:
        print(f'  块: {n:4d} px  x {x0:4d}-{x1:4d} (w={x1-x0:4d})  y {y0:4d}-{y1:4d} (h={y1-y0:4d})  中心 ({(x0+x1)//2},{(y0+y1)//2})')
    # 整体颜色分布统计：主色调
    from collections import Counter
    c = Counter()
    for y in range(0, H, 16):
        for x in range(0, W, 16):
            r, g, b = px[x, y]
            c[(r//40*40, g//40*40, b//40*40)] += 1
    print('  主色调 top5:', c.most_common(5))