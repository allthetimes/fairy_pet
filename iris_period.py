# -*- coding: utf-8 -*-
# BV1CkcbzgEkC 0-15s：精确测量 iris 圈面积随时间，验证周期
import os, math
from PIL import Image

BASE = r'D:\work\fairy-pet'
D = os.path.join(BASE, 'frames_iris_pulse')
files = sorted(f for f in os.listdir(D) if f.endswith('.png'))
FPS = 12
CX, CY = 1497, 510
R = 430
SC = 240
h = SC // 2

def classify(r, g, b):
    if r > 150 and g > 145 and b > 150: return 'white'
    if 120 <= r <= 140 and 130 <= g <= 150 and 190 <= b <= 210: return 'iris_outer'
    if 40 <= r <= 80 and 90 <= g <= 110 and 180 <= b <= 200: return 'iris_mid'
    if r < 60 and g < 100 and 100 < b < 160: return 'core'
    if b > 130 and b - r > 110 and b - g > 70 and r < 80: return 'ring'
    return None

ser = {k: [] for k in ['ring', 'white', 'iris_outer', 'iris_mid', 'core']}
for f in files:
    img = Image.open(os.path.join(D, f)).convert('RGB')
    crop = img.crop((CX - R, CY - R, CX + R, CY + R)).resize((SC, SC), Image.BILINEAR)
    px = crop.load()
    counts = {k: 0 for k in ser}
    for y in range(SC):
        for x in range(SC):
            r, g, b = px[x, y]
            k = classify(r, g, b)
            if k: counts[k] += 1
    for k, v in counts.items():
        ser[k].append(v)

# 输出每帧（每 3 帧打一行 = 0.25s 一步）
print(f'{"t":>4} | {"ring":>5} {"iris_o":>6} {"iris_m":>6} {"core":>5} {"white":>5}')
for i in range(0, len(files), 3):
    t = i / FPS
    print(f'{t:4.1f} | {ser["ring"][i]:5d} {ser["iris_outer"][i]:6d} {ser["iris_mid"][i]:6d} {ser["core"][i]:5d} {ser["white"][i]:5d}')

# 自相关：找主周期
def ac_best(s, label):
    mu = sum(s) / len(s)
    sd = (sum((x - mu) ** 2 for x in s) / len(s)) ** 0.5
    if sd == 0: return
    best = (0, 0)
    for lag in range(4, 100):
        num = 0
        for i in range(len(s) - lag):
            num += (s[i] - mu) * (s[i + lag] - mu)
        ac = num / (len(s) - lag) / sd / sd
        if ac > best[0]: best = (ac, lag)
    amp_pct = round((max(s) - min(s)) / 2 / (sum(s) / len(s)) * 100, 1)
    print(f'{label:12s}  最佳周期 lag={best[1]:2d} ({best[1]/FPS:.2f}s ac={best[0]:.3f})  ±{amp_pct}%')

print()
for k in ['ring', 'white', 'iris_outer', 'iris_mid', 'core']:
    ac_best(ser[k], k)

# 跨相关：iris_outer 与 ring 是否同相？
def xcorr(a, b):
    ma = sum(a) / len(a); mb = sum(b) / len(b)
    sa = (sum((x-ma)**2 for x in a)/len(a))**0.5
    sb = (sum((x-mb)**2 for x in b)/len(b))**0.5
    best = (-9, 0)
    for lag in range(-30, 31):
        num = 0; n = 0
        for i in range(len(a)):
            j = i + lag
            if 0 <= j < len(b):
                num += (a[i]-ma)*(b[j]-mb); n += 1
        ac = num / n / sa / sb if sa*sb > 0 else 0
        if ac > best[0]: best = (ac, lag)
    return best

print()
for k in ['iris_outer', 'iris_mid', 'white', 'core']:
    ac, lag = xcorr(ser[k], ser['ring'])
    print(f'xcorr({k}, ring):  lag={lag} ({lag/FPS:.2f}s) ac={ac:.3f}')

# 蓝灰外圈面积 → 推半径
n_o = ser['iris_outer']
import math as m
r_med = m.sqrt(sum(n_o)/len(n_o)/m.pi)
r_min = m.sqrt(min(n_o)/m.pi)
r_max = m.sqrt(max(n_o)/m.pi)
print(f'\n蓝灰外圈 √(area/π): {r_min:.1f} / {r_med:.1f} / {r_max:.1f} (≈ {min(n_o)}~{max(n_o)} px)')
print('我的 SVG：r=37.5 sw=13（环宽 31-44）')