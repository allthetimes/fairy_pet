# -*- coding: utf-8 -*-
# 修正版：固定位置裁剪 + 正确的暗核心检测；输出分块时序
import os, math
from PIL import Image

BASE = r'D:\work\fairy-pet'
D = os.path.join(BASE, 'frames_full')
files = sorted(f for f in os.listdir(D) if f.endswith('.png'))
FPS = 12

# 先验证眼睛中心：取 5 个采样帧，在其附近找蓝环质心
from PIL import Image as I
def find_near(img, cx, cy, win=120):
    im = img.convert('RGB'); px = im.load()
    xs, ys = [], []
    for y in range(max(0, cy - win), cy + win, 2):
        for x in range(max(0, cx - win), cx + win, 2):
            r, g, b = px[x, y]
            if b > 150 and b - r > 110 and b - g > 70 and g < 130:
                xs.append(x); ys.append(y)
    if len(xs) < 10:
        return None
    return (sum(xs) / len(xs), sum(ys) / len(ys),
            (max(xs) - min(xs) + max(ys) - min(ys)) / 4)

CXS = []
for idx in [60, 300, 700, 1100, 1500]:
    img = I.open(os.path.join(D, files[idx]))
    res = find_near(img, 196, 670)
    print(idx, '->', None if res is None else ('(%.0f,%.0f) r=%.1f' % res))
    if res: CXS.append(res)
CX = int(sum(c[0] for c in CXS) / len(CXS))
CY = int(sum(c[1] for c in CXS) / len(CXS))
RR = sum(c[2] for c in CXS) / len(CXS)
print('fixed center=(%d,%d) r=%.1f' % (CX, CY, RR))

R = int(RR * 1.5)
rows = []
for f in files:
    img = I.open(os.path.join(D, f))
    crop = img.crop((CX - R, CY - R, CX + R, CY + R)).resize((180, 180), Image.BILINEAR)
    px = crop.load()
    bx = []; by = []; wx = []; wy = []; dark = []; brt = 0
    for y in range(180):
        for x in range(180):
            r, g, b = px[x, y]
            dx, dy = x - 90, y - 90
            d2 = dx * dx + dy * dy
            if b > 140 and b - r > 100 and b - g > 60 and g < 135:
                bx.append(x); by.append(y); brt += r + g + b
            elif d2 < 52 * 52:
                if r > 150 and g > 145 and b > 150:
                    wx.append(x); wy.append(y)
                elif r < 110 and g < 120 and 60 < b < 200 and b > r:
                    dark.append((x, y))
    if not bx:
        rows.append(None); continue
    bb_w = max(bx) - min(bx); bb_h = max(by) - min(by)
    open_ = bb_h / max(1, bb_w)
    Rn = (bb_w + bb_h) / 4 or 1
    if dark:
        gx = (sum(p[0] for p in dark) / len(dark) - 90) / Rn
        gy = (sum(p[1] for p in dark) / len(dark) - 90) / Rn
    else:
        gx = gy = float('nan')
    rows.append(dict(open=open_, blue=len(bx), white=len(wx), ndark=len(dark),
                     gx=gx, gy=gy, brt=brt / len(bx) / 3,
                     scale=(bb_w + bb_h) / 2))

# 分块（1 秒 = 12 帧）时序
print()
print('t(s) | open  scale  blue  white ndark  gx     gy    brt')
for i in range(0, len(rows), 12):
    chunk = [m for m in rows[i:i + 12] if m]
    if not chunk:
        continue
    t = i / FPS
    def med(k):
        v = sorted(m[k] for m in chunk if not math.isnan(m[k])) or [float('nan')]
        return v[len(v) // 2]
    def std(k):
        v = [m[k] for m in chunk if not math.isnan(m[k])]
        if not v: return float('nan')
        mu = sum(v) / len(v)
        return (sum((x - mu) ** 2 for x in v) / len(v)) ** 0.5
    print('%5.0f | %.2f %6.1f %5d %5d %5d  %+.2f  %+.2f  %5.1f   (blue sd %.0f)' % (
        t, med('open'), med('scale'), med('blue'), med('white'), med('ndark'),
        med('gx'), med('gy'), med('brt'), std('blue')))

ok = [m for m in rows if m]
nd = [m['ndark'] for m in ok]
print()
print('ndark min/med/max: %d / %d / %d' % (min(nd), sorted(nd)[len(nd)//2], max(nd)))
sc = [m['scale'] for m in ok]
sc_s = sorted(sc)
print('scale(眼径px) p2/med/p98: %.1f / %.1f / %.1f' % (sc_s[int(.02*len(sc))], sc_s[len(sc)//2], sc_s[int(.98*len(sc))]))
op = [m['open'] for m in ok]
op_s = sorted(op)
print('open p2/med/p98: %.2f / %.2f / %.2f  min=%.2f' % (op_s[int(.02*len(op))], op_s[len(op)//2], op_s[int(.98*len(op))], min(op)))
gxv = [m['gx'] for m in ok if m['ndark'] > 5]
gyv = [m['gy'] for m in ok if m['ndark'] > 5]
if gxv:
    print('gx %+.2f..%+.2f  gy %+.2f..%+.2f (n=%d)' % (min(gxv), max(gxv), min(gyv), max(gyv), len(gxv)))
# open<0.85 的帧（疑似眨眼/眯眼）
blinks = [(i / FPS, m['open'], m['white']) for i, m in enumerate(rows) if m and m['open'] < 0.85]
print('open<0.85 帧数:', len(blinks), blinks[:30])
