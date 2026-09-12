# -*- coding: utf-8 -*-
# 综合分析 BV1CkcbzgEkC 0-15s 60fps：
#   1) 帧差分（|frame_n - frame_n-1|）→ 找出"哪里在动"
#   2) 每帧的多项指标：眼整体亮度、各层像素数、颜色均值
#   3) 自相关找各指标的主周期
#   4) 帧差分热力图（数值导出）→ 看哪些像素位置变化最频繁
import os, math
from PIL import Image

BASE = r'D:\work\fairy-pet'
D = os.path.join(BASE, 'frames_hifps2')
files = sorted(f for f in os.listdir(D) if f.endswith('.png'))
FPS = 60
CX, CY = 998, 340    # 1280 宽下的眼睛中心
R = 280
SC = 240

# === 第 1 步：每帧眼部 crop 与上一帧的差分 ===
ser_diff = []
prev_crop = None
for f in files:
    img = Image.open(os.path.join(D, f)).convert('RGB')
    crop = img.crop((CX - R, CY - R, CX + R, CY + R)).resize((SC, SC), Image.BILINEAR)
    if prev_crop is not None:
        a = prev_crop.load(); b = crop.load()
        s = 0
        for y in range(SC):
            for x in range(SC):
                ar, ag, ab = a[x, y]; br, bg, bb = b[x, y]
                s += abs(ar-br) + abs(ag-bg) + abs(ab-bb)
        ser_diff.append(s / (SC*SC*3))   # 平均每像素每通道的差
    prev_crop = crop

print('=== 帧差分（运动强度）峰值时刻 ===')
peaks = []
for i, v in enumerate(ser_diff):
    if v > 5:  # 阈值
        peaks.append((i / FPS, v))
print(f'共 {len(peaks)} 帧差分 > 5，前 20：')
for t, v in peaks[:20]:
    print(f'  t={t:.3f}s  diff={v:.2f}')
print('  ...')
print(f'后 5 个：')
for t, v in peaks[-5:]:
    print(f'  t={t:.3f}s  diff={v:.2f}')

# 帧差分峰值间隔 = 主周期
if len(peaks) > 5:
    gaps = [peaks[i+1][0] - peaks[i][0] for i in range(len(peaks)-1)]
    from collections import Counter
    print('\n帧差分峰值间隔分布：')
    for gap, n in sorted(Counter(round(g, 2) for g in gaps).items())[:10]:
        print(f'  {gap:.2f}s × {n}')

# === 第 2 步：每帧的细分指标（每 4 帧采一次，省时间） ===
def classify(r, g, b):
    if r > 150 and g > 145 and b > 150: return 'W'           # 白
    if 120 <= r <= 140 and 130 <= g <= 150 and 190 <= b <= 210: return 'O'   # 蓝灰外圈
    if 40 <= r <= 80 and 90 <= g <= 110 and 180 <= b <= 200: return 'M'        # 中蓝
    if r < 60 and g < 100 and 100 < b < 160: return 'C'        # 核心
    if r > 200 and g > 200 and b > 200: return 'G'             # 高光
    if b > 130 and b - r > 110 and b - g > 70 and r < 80: return 'R'  # 亮蓝外环
    return None

metrics = []
for i in range(0, len(files), 4):  # 15 fps 采样，足够看清周期
    img = Image.open(os.path.join(D, files[i])).convert('RGB')
    crop = img.crop((CX - R, CY - R, CX + R, CY + R)).resize((SC, SC), Image.BILINEAR)
    px = crop.load()
    cnt = {k: 0 for k in 'WOMCGR'}
    bsum = {k: 0 for k in 'WOMCGR'}
    gsum = {k: 0 for k in 'WOMCGR'}
    rsum = {k: 0 for k in 'WOMCGR'}
    totR = totG = totB = 0
    n = 0
    for y in range(SC):
        for x in range(SC):
            r, g, b = px[x, y]
            totR += r; totG += g; totB += b; n += 1
            k = classify(r, g, b)
            if k:
                cnt[k] += 1; bsum[k] += b; gsum[k] += g; rsum[k] += r
    m = {'t': i / FPS}
    m['meanB'] = totB / n
    m['meanR'] = totR / n
    for k in 'WOMCGR':
        m[f'{k}_n'] = cnt[k]
        if cnt[k] > 0:
            m[f'{k}_bmean'] = bsum[k] / cnt[k]
            m[f'{k}_rmean'] = rsum[k] / cnt[k]
    metrics.append(m)

# === 第 3 步：自相关找各指标的主周期 ===
def ac(s, label):
    mu = sum(s) / len(s)
    sd = (sum((x-mu)**2 for x in s) / len(s)) ** 0.5
    if sd < 0.01: return
    best = (0, 0)
    for lag in range(2, min(120, len(s)//3)):
        num = 0
        for i in range(len(s) - lag):
            num += (s[i]-mu) * (s[i+lag]-mu)
        ac_v = num / (len(s)-lag) / sd / sd
        if ac_v > best[0]: best = (ac_v, lag)
    amp = (max(s)-min(s))/2 / (sum(s)/len(s)) * 100
    print(f'  {label:10s}  周期={best[1]/15:.3f}s ac={best[0]:.3f}  ±{amp:.1f}%')

print('\n=== 各指标主周期 ===')
for key in ['meanB', 'meanR', 'W_n', 'O_n', 'M_n', 'C_n', 'G_n', 'R_n',
            'M_bmean', 'O_bmean', 'C_bmean', 'R_bmean']:
    s = [m.get(key) for m in metrics if key in m]
    if len(s) > 20 and max(s) - min(s) > 0.5:
        ac(s, key)

# === 第 4 步：导出帧差分热力图（数值，不出图）===
# 在 SCxSC 上累计每像素的总变动强度
print('\n=== 哪块区域在动 ===')
hot = [0] * (SC * SC)
for i in range(1, len(files)):
    img = Image.open(os.path.join(D, files[i])).convert('RGB')
    crop = img.crop((CX - R, CY - R, CX + R, CY + R)).resize((SC, SC), Image.BILINEAR)
    prev = Image.open(os.path.join(D, files[i-1])).convert('RGB').crop((CX - R, CY - R, CX + R, CY + R)).resize((SC, SC), Image.BILINEAR)
    a = prev.load(); b = crop.load()
    for y in range(SC):
        for x in range(SC):
            ar, ag, ab = a[x, y]; br, bg, bb = b[x, y]
            hot[y*SC + x] += abs(ar-br) + abs(ag-bg) + abs(ab-bb)

# 把 hot 矩阵投影到 1D：按半径（距中心距离）统计
import statistics
radial = {}
for y in range(SC):
    for x in range(SC):
        d = int(((x - SC//2)**2 + (y - SC//2)**2) ** 0.5)
        if d < SC // 2:
            radial.setdefault(d, []).append(hot[y*SC + x])
print('按半径统计变动强度（外圈→中心）：')
for d in sorted(radial.keys())[::10]:
    avg = sum(radial[d]) / len(radial[d])
    print(f'  半径 r={d:3d}: 平均变动 {avg:.1f}  (像素数 {len(radial[d])})')