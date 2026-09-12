# -*- coding: utf-8 -*-
# 验证脉动真伪：逐帧 blue/white/scale 序列 + 与视频关键帧位置对照
import os, subprocess, math
from PIL import Image

BASE = r'D:\work\fairy-pet'
ff = ''  # 用 imageio_ffmpeg
import imageio_ffmpeg
ff = imageio_ffmpeg.get_ffmpeg_exe()

# 关键帧时间
r = subprocess.run([ff, '-i', os.path.join(BASE, 'ref_video/egg.mp4'),
                    '-vf', 'showinfo', '-f', 'null', '-'],
                   capture_output=True, text=True)
kfs = []
for line in r.stderr.splitlines():
    if 'pts_time:' in line and ('type:I' in line or 'I frame' in line):
        t = float(line.split('pts_time:')[1].split()[0])
        kfs.append(round(t, 2))
kfs = sorted(set(kfs))
print('关键帧时间(前30):', kfs[:30])

D = os.path.join(BASE, 'frames_full')
files = sorted(f for f in os.listdir(D) if f.endswith('.png'))
FPS = 12
CX, CY, R = 195, 676, 48

series = []
for f in files:
    img = Image.open(os.path.join(D, f))
    crop = img.crop((CX - R, CY - R, CX + R, CY + R)).resize((180, 180), Image.BILINEAR)
    px = crop.load()
    bx = []; wx = 0; brt = 0
    for y in range(180):
        for x in range(180):
            rr, g, b = px[x, y]
            dx, dy = x - 90, y - 80  # 任意，只统计
            if b > 140 and b - rr > 100 and b - g > 60 and g < 135:
                bx.append((x, y)); brt += rr + g + b
            elif rr > 150 and g > 145 and b > 150:
                dx2 = (x - 90) ** 2 + (y - 90) ** 2
                if dx2 < 52 * 52:
                    wx += 1
    if not bx:
        series.append(None); continue
    xs = [p[0] for p in bx]; ys = [p[1] for p in bx]
    series.append(dict(blue=len(bx), white=wx,
                       scale=(max(xs) - min(xs) + max(ys) - min(ys)) / 2,
                       brt=brt / len(bx) / 3))

# 打印 t=8..24s 逐帧
print()
print('t     blue  white scale  brt')
for i in range(8 * FPS, 24 * FPS):
    m = series[i]
    if m:
        print('%5.2f %5d %5d %5.1f %5.1f' % (i / FPS, m['blue'], m['white'], m['scale'], m['brt']))

# 自相关（去均值，帧缺失跳过）
vals = [(i, m['blue']) for i, m in enumerate(series) if m]
mu = sum(v for _, v in vals) / len(vals)
print('blue mean=%.0f' % mu)
best = []
for lag in range(4, 120):
    num = den = 0
    d = dict(vals)
    for i, v in vals:
        if i + lag in d:
            num += (v - mu) * (d[i + lag] - mu); den += 1
    ac = num / den / mu if den > 100 else 0  # 方差近似用 mean^2 归一（同量级比较）
    best.append((ac, lag))
best.sort(reverse=True)
print('blue 自相关 top5 lag:', [(l, round(a, 3)) for a, l in best[:5]])
# 与关键帧周期的关系
if len(kfs) > 3:
    gaps = [round(kfs[i+1] - kfs[i], 2) for i in range(len(kfs)-1)]
    from collections import Counter
    print('关键帧间隔分布:', Counter(gaps).most_common(5))
