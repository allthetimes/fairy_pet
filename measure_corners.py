# -*- coding: utf-8 -*-
# 测量 BV1CkcbzgEkC 右眼四个尖角的时序变化
# 尖角位置预期：45°/135°/225°/315°（对角方向）
# 颜色：暗蓝 #232A8F (r<50, g<60, b 120-180)
import os, math
from PIL import Image

BASE = r'D:\work\fairy-pet'
D = os.path.join(BASE, 'frames_hifps2')
files = sorted(f for f in os.listdir(D) if f.endswith('.png'))
FPS = 60
CX, CY = 890, 301
RMAX = 215

# 每 5 帧采样（12fps 采样），900 帧 → 180 样本
positions = []
for i in range(0, len(files), 5):
    img = Image.open(os.path.join(D, files[i])).convert('RGB')
    px = img.load()
    # 在眼睛范围内找四个尖角的暗蓝像素（对角方向）
    pts = []
    for y in range(max(0, CY-RMAX), min(img.size[1], CY+RMAX), 2):
        for x in range(max(0, CX-RMAX), min(img.size[0], CX+RMAX), 2):
            dx, dy = x-CX, y-CY
            if dx*dx + dy*dy > RMAX*RMAX: continue
            r, g, b = px[x, y]
            # 暗蓝尖角（比外环暗、比核心暗）
            if r < 50 and g < 60 and 100 < b < 180:
                pts.append((x, y))
    if not pts:
        positions.append({'t': i/FPS, 'n': 0})
        continue
    # 用角度分 4 组：每个尖角一个角度范围 ±30°
    angles = []
    for x, y in pts:
        a = math.degrees(math.atan2(y - CY, x - CX))
        # 转到 0-360，从正右方开始
        if a < 0: a += 360
        angles.append(a)
    # 找 4 个角峰（45, 135, 225, 315）
    import collections
    hist = collections.Counter(int(a / 20) * 20 for a in angles)
    top4 = hist.most_common(4)
    positions.append({'t': i/FPS, 'n': len(pts), 'top4': sorted(top4)})

print('t(s)   n   top4 角度（度）— 暗蓝尖角')
for p in positions[::3]:  # 每 3 样本打印一个
    s = ', '.join(f'{a}°:{n}' for a, n in p['top4']) if p.get('top4') else '-'
    print(f'{p["t"]:5.2f}  {p["n"]:4d}  {s}')

# 总尖角像素数随时间
n_series = [p['n'] for p in positions]
print(f'\n尖角总像素: min={min(n_series)} max={max(n_series)} mean={sum(n_series)/len(n_series):.0f}  ±{(max(n_series)-min(n_series))/2/(sum(n_series)/len(n_series))*100:.1f}%')

# 自相关找周期
def ac(s):
    mu = sum(s)/len(s); sd = (sum((x-mu)**2 for x in s)/len(s))**0.5
    if sd < 0.5: return
    best = (0, 0)
    for lag in range(3, len(s)//3):
        num = 0
        for i in range(len(s)-lag):
            num += (s[i]-mu)*(s[i+lag]-mu)
        a = num/(len(s)-lag)/sd/sd
        if a > best[0]: best = (a, lag)
    print(f'  周期={best[1]/12:.3f}s  ac={best[0]:.3f}')

print('尖角像素数周期：'); ac(n_series)