# -*- coding: utf-8 -*-
# 精确测量视频右眼"内部圆"的面积随时间变化 → 找真实周期
# 位置：1280 宽下右眼中心 (890, 301)，只看半径 215 内，排除背景
import os, math
from PIL import Image

BASE = r'D:\work\fairy-pet'
D = os.path.join(BASE, 'frames_hifps2')
files = sorted(f for f in os.listdir(D) if f.endswith('.png'))
FPS = 60
CX, CY = 890, 301
RMAX = 215

# 采样：每 2 帧（30fps），900 帧 → 450 个样本
series_outer = []   # 亮蓝外环（外圈）像素数
series_inner = []   # 内部圆（浅蓝灰+中蓝+深蓝核心）
series_core = []    # 深蓝核心
etimes = []

for i in range(0, len(files), 2):
    img = Image.open(os.path.join(D, files[i])).convert('RGB')
    px = img.load()
    no = ni = nc = 0
    for y in range(max(0, CY-RMAX), min(img.size[1], CY+RMAX), 2):
        for x in range(max(0, CX-RMAX), min(img.size[0], CX+RMAX), 2):
            dx, dy = x-CX, y-CY
            if dx*dx + dy*dy > RMAX*RMAX: continue
            r, g, b = px[x, y]
            # 亮蓝外环（深蓝紫高饱和）
            if b > 170 and b - r > 110 and b - g > 80 and r < 110:
                no += 1
            # 浅蓝灰环（内部圈）
            elif 110 <= r <= 175 and 120 <= g <= 180 and 175 <= b <= 235:
                ni += 1
            # 深蓝核心
            elif r < 90 and g < 110 and 120 < b < 190:
                nc += 1
    series_outer.append(no); series_inner.append(ni); series_core.append(nc)
    etimes.append(i / FPS)

print('n =', len(series_outer), ' 采样率 30fps, 时长', round(etimes[-1], 1), 's')

def stats(name, s):
    mu = sum(s)/len(s)
    print(f'{name}: min={min(s)} max={max(s)} mean={mu:.0f}  ±{(max(s)-min(s))/2/mu*100:.1f}%')

stats('外环', series_outer)
stats('内部圆', series_inner)
stats('核心', series_core)

def ac_best(s, label):
    mu = sum(s)/len(s)
    sd = (sum((x-mu)**2 for x in s)/len(s))**0.5
    if sd == 0: return
    best = (0, 0)
    for lag in range(3, 200):
        num = 0
        for i in range(len(s)-lag):
            num += (s[i]-mu)*(s[i+lag]-mu)
        a = num/(len(s)-lag)/sd/sd
        if a > best[0]: best = (a, lag)
    print(f'{label}: 主周期 = {best[1]/30:.3f}s  (ac={best[0]:.3f}, lag={best[1]} 帧@30fps)')

print()
ac_best(series_outer, '外环')
ac_best(series_inner, '内部圆')
ac_best(series_core, '核心')

# 内部圆/外环 的比值（消除运镜缩放）
ratio = [i/o if o else 0 for i, o in zip(series_inner, series_outer)]
ac_best(ratio, '内部圆/外环 比值')
stats('内部圆/外环比值', [r*1000 for r in ratio])

# 打印前 60 个样本（2 秒）
print('\n前 60 样本（每样本 1/30 s）：')
print(' t    外环  内部圆  核心')
for k in range(min(60, len(etimes))):
    print(f'{etimes[k]:5.2f}  {series_outer[k]:5d}  {series_inner[k]:6d}  {series_core[k]:5d}')