# -*- coding: utf-8 -*-
# 精确定位右眼（新版 2.6）外圈亮蓝环 —— 导出叠加图供确认
import os
from PIL import Image, ImageDraw

BASE = r'D:\work\fairy-pet'
D = os.path.join(BASE, 'frames_hifps2')
files = sorted(f for f in os.listdir(D) if f.endswith('.png'))

img = Image.open(os.path.join(D, files[180])).convert('RGB')  # t=3.0s
W, H = img.size
px = img.load()

# 严格亮蓝：新版外圈
xs, ys = [], []
for y in range(H):
    for x in range(W // 2, W):   # 右半边
        r, g, b = px[x, y]
        if b > 190 and b - r > 130 and b - g > 90 and r < 110:
            xs.append(x); ys.append(y)

print(f'亮蓝像素数: {len(xs)}')
if xs:
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    print(f'包围盒 x {x0}-{x1} (w={x1-x0})  y {y0}-{y1} (h={y1-y0})')
    print(f'中心 ({(x0+x1)//2}, {(y0+y1)//2})  半径 ~{(x1-x0+y1-y0)//4}')

# 画框叠加保存
vis = img.copy()
d = ImageDraw.Draw(vis)
if xs:
    d.rectangle([x0, y0, x1, y1], outline=(255, 0, 0), width=4)
    d.line([x0, (y0+y1)//2, x1, (y0+y1)//2], fill=(255, 255, 0), width=2)
    d.line([(x0+x1)//2, y0, (x0+x1)//2, y1], fill=(255, 255, 0), width=2)
outp = os.path.join(BASE, 'full_frames', '_locate.png')
vis.save(outp)
print('saved', outp)