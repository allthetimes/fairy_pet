# -*- coding: utf-8 -*-
# 对 160x160 归一化眼部裁剪帧计算逐帧指标：
#   open   = 亮蓝环 bbox 高/宽（<1 说明纵向压缩 = 眨眼/眯眼）
#   blue   = 亮蓝环像素数（环可见面积）
#   white  = 白盘像素数（内部 55% 半径）
#   gx,gy  = 深色核心质心相对眼心偏移（视线方向，单位=眼半径）
#   brt    = 亮蓝环平均亮度（脉冲/发光）
import os
from PIL import Image

BASE = r'D:\work\fairy-pet'
D = os.path.join(BASE, 'eye_crops')
files = sorted(f for f in os.listdir(D) if f.endswith('.png'))
FPS = 12

rows = []
for f in files:
    im = Image.open(os.path.join(D, f)).convert('RGB')
    px = im.load()
    W = H = 160
    cx0 = cy0 = 80
    bx = []; by = []      # 亮蓝环
    wx = []; wy = []      # 白盘
    dark = []             # 核心暗蓝
    brt_sum = 0
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            dx, dy = x - cx0, y - cy0
            d2 = dx * dx + dy * dy
            if b > 140 and b - r > 100 and b - g > 60 and g < 135:
                bx.append(x); by.append(y); brt_sum += (r + g + b)
            elif r > 150 and g > 145 and b > 150 and d2 < (46 * 46):
                wx.append(x); wy.append(y)
                if r < 110 and b > 90:   # 白盘内的深色核心
                    dark.append((x, y))
    if not bx:
        rows.append((f, None)); continue
    x0, x1, y0, y1 = min(bx), max(bx), min(by), max(by)
    bw, bh = x1 - x0, y1 - y0
    open_ = bh / bw if bw > 0 else 0
    # 核心质心（若无则用白盘内最暗点）
    if dark:
        gx = sum(p[0] for p in dark) / len(dark) - cx0
        gy = sum(p[1] for p in dark) / len(dark) - cy0
    else:
        gx = gy = 0.0
    R_eye = (bw + bh) / 4 or 1
    rows.append((f, dict(open=open_, blue=len(bx), white=len(wx),
                         gx=round(gx / R_eye, 3), gy=round(gy / R_eye, 3),
                         brt=round(brt_sum / len(bx) / 3, 1))))

# 打印紧凑时序：每秒 1 行（12 帧聚合），并标注异常帧
import math
print('t(s) | open  blue  white  gx     gy    brt   | notes')
sec = 0
for i, (f, m) in enumerate(rows):
    t = i / FPS
    if m is None:
        print(f'{t:5.1f} | ---- 眼睛不可见 ----')
        continue
    note = ''
    if m['open'] < 0.80: note += ' 眯/眨(open=%.2f)' % m['open']
    if m['white'] < 900: note += ' 白盘缩小(%d)' % m['white']
    if abs(m['gx']) > 0.25 or abs(m['gy']) > 0.25: note += f" 核心偏移({m['gx']:.2f},{m['gy']:.2f})"
    if i % 6 == 0 or note:
        print(f"{t:5.1f} | {m['open']:.2f} {m['blue']:5d} {m['white']:5d}  {m['gx']:+.2f} {m['gy']:+.2f} {m['brt']:5.1f} |{note}")

# 汇总统计
opens = [m['open'] for _, m in rows if m]
blues = [m['blue'] for _, m in rows if m]
whites = [m['white'] for _, m in rows if m]
print()
print('open  min/med/max: %.2f / %.2f / %.2f' % (min(opens), sorted(opens)[len(opens)//2], max(opens)))
print('blue  min/med/max: %d / %d / %d' % (min(blues), sorted(blues)[len(blues)//2], max(blues)))
print('white min/med/max: %d / %d / %d' % (min(whites), sorted(whites)[len(whites)//2], max(whites)))
gxs = [m['gx'] for _, m in rows if m]; gys = [m['gy'] for _, m in rows if m]
print('gx range: %+.2f..%+.2f   gy range: %+.2f..%+.2f' % (min(gxs), max(gxs), min(gys), max(gys)))
brts = [m['brt'] for _, m in rows if m]
print('brt  min/med/max: %.1f / %.1f / %.1f' % (min(brts), sorted(brts)[len(brts)//2], max(brts)))
