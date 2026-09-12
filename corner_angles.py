# -*- coding: utf-8 -*-
# 尖角角度分布：只扫外环区域（半径 145-215），排除中心核心
import os, math, collections
from PIL import Image

BASE = r'D:\work\fairy-pet'
D = os.path.join(BASE, 'frames_hifps2')
files = sorted(f for f in os.listdir(D) if f.endswith('.png'))
CX, CY = 890, 301

for idx in [180, 500, 800]:
    img = Image.open(os.path.join(D, files[idx])).convert('RGB')
    px = img.load()
    hist = collections.Counter()
    total = 0
    for y in range(CY-215, CY+215):
        for x in range(CX-215, CX+215):
            dx, dy = x-CX, y-CY
            d = math.hypot(dx, dy)
            if not (145 <= d <= 212):   # 只在外环+尖角区
                continue
            r, g, b = px[x, y]
            # 暗蓝尖角：明显比亮蓝外环暗
            if r < 60 and g < 70 and b < 190 and b > 90:
                a = math.degrees(math.atan2(-(y-CY), x-CX))  # 数学坐标（上=+y）
                if a < 0: a += 360
                hist[int(a/10)*10] += 1
                total += 1
    print(f'\n=== 帧 {idx} (t={idx/60:.2f}s)，暗蓝像素 {total} ===')
    # 每 10° 桶，只打印非零
    for a in sorted(hist):
        bar = '#' * min(60, hist[a] // 4)
        print(f'  {a:3d}°-{a+10:3d}°  {hist[a]:4d} {bar}')
    # 找峰值角度
    if hist:
        tops = sorted(hist.items(), key=lambda kv: -kv[1])[:8]
        print('  峰值:', ', '.join(f'{a}°({n})' for a, n in sorted(tops)))
print('\n（角度：0°=正右，90°=正上，180°=正左，270°=正下）')