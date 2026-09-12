# -*- coding: utf-8 -*-
# 全片扫描 egg.mp4 (fps=12, 1440宽)：逐帧眼部指标 + 事件检测 + 脉动周期自相关
import imageio_ffmpeg, subprocess, os, math
from PIL import Image

BASE = r'D:\work\fairy-pet'
ff = imageio_ffmpeg.get_ffmpeg_exe()

outdir = os.path.join(BASE, 'frames_full')
os.makedirs(outdir, exist_ok=True)
for f in os.listdir(outdir):
    if f.endswith('.png'):
        os.remove(os.path.join(outdir, f))
cmd = [ff, '-y', '-i', os.path.join(BASE, 'ref_video/egg.mp4'),
       '-vf', 'fps=12,scale=1440:-1:flags=lanczos', '-pix_fmt', 'rgb24',
       os.path.join(outdir, 'f%06d.png')]
r = subprocess.run(cmd, capture_output=True, text=True)
files = sorted(f for f in os.listdir(outdir) if f.endswith('.png'))
print('full frames:', len(files), 'rc=', r.returncode)

FPS = 12
rows = []
for f in files:
    img = Image.open(os.path.join(outdir, f))
    im = img.convert('RGB'); W, H = im.size; px = im.load()
    step = 3
    xs, ys = [], []
    for y in range(0, H, step):
        for x in range(0, W, step):
            rr, g, b = px[x, y]
            if b > 150 and b - rr > 110 and b - g > 70 and g < 130:
                xs.append(x); ys.append(y)
    if len(xs) < 30:
        rows.append(None); continue
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = x1 - x0, y1 - y0
    if bw < 15 or bh < 15 or not (0.5 < bw / bh < 2.0):
        rows.append(None); continue
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    R_eye = (bw + bh) / 4
    # 细指标：在裁剪坐标里做
    R = int(R_eye * 1.55)
    box = (cx - R, cy - R, cx + R, cy + R)
    crop = img.crop(box).resize((160, 160), Image.BILINEAR)
    cpx = crop.load()
    bx = []; by = []; wx = []; wy = []; dark = []; brt = 0
    for y in range(160):
        for x in range(160):
            rr, g, b = cpx[x, y]
            dx, dy = x - 80, y - 80
            d2 = dx * dx + dy * dy
            if b > 140 and b - rr > 100 and b - g > 60 and g < 135:
                bx.append(x); by.append(y); brt += rr + g + b
            elif rr > 150 and g > 145 and b > 150 and d2 < 46 * 46:
                wx.append(x); wy.append(y)
                if rr < 110 and b > 90:
                    dark.append((x, y))
    if not bx:
        rows.append(None); continue
    bb0, bb1, bby0, bby1 = min(bx), max(bx), min(by), max(by)
    open_ = (bby1 - bby0) / max(1, bb1 - bb0)
    if dark:
        gx = sum(p[0] for p in dark) / len(dark) - 80
        gy = sum(p[1] for p in dark) / len(dark) - 80
    else:
        gx = gy = float('nan')
    Rn = ((bb1 - bb0) + (bby1 - bby0)) / 4 or 1
    rows.append(dict(open=open_, blue=len(bx), white=len(wx), ndark=len(dark),
                     gx=gx / Rn, gy=gy / Rn, brt=brt / len(bx) / 3,
                     rr=R_eye, cx=cx, cy=cy))

# 事件检测
print()
print('== 事件（open<0.90 / white<900 / brt<100 / blue<1600 / ndark==0）==')
ev = []
for i, m in enumerate(rows):
    if m is None:
        continue
    t = i / FPS
    tags = []
    if m['open'] < 0.90: tags.append('眯%.2f' % m['open'])
    if m['white'] < 900: tags.append('白%d' % m['white'])
    if m['brt'] < 100: tags.append('暗%.0f' % m['brt'])
    if m['blue'] < 1600: tags.append('蓝%d' % m['blue'])
    if m['ndark'] == 0: tags.append('核心丢失')
    if tags:
        ev.append((t, tags))
# 压缩成时间段
if ev:
    runs = [[ev[0]]]
    for e in ev[1:]:
        if e[0] - runs[-1][-1][0] <= 0.6:
            runs[-1].append(e)
        else:
            runs.append([e])
    for run in runs:
        alltags = set()
        for _, tags in run:
            alltags.update(t[:2] for t in tags)
        print('  t=%6.1f-%6.1fs  %s' % (run[0][0], run[-1][0], ','.join(sorted(alltags))))
else:
    print('  无事件：整段眼睛保持全开、亮度稳定')

# 核心是否一直检测到
nd = [m['ndark'] for m in rows if m]
print()
print('ndark min/med/max: %d / %d / %d' % (min(nd), sorted(nd)[len(nd)//2], max(nd)))
gxs = [m['gx'] for m in rows if m and m['ndark'] > 0]
gys = [m['gy'] for m in rows if m and m['ndark'] > 0]
if gxs:
    print('gx: %+.3f..%+.3f (std %.3f)  gy: %+.3f..%+.3f (std %.3f)' % (
        min(gxs), max(gxs), (sum(x*x for x in gxs)/len(gxs))**0.5,
        min(gys), max(gys), (sum(y*y for y in gys)/len(gys))**0.5))

# 蓝环面积脉动周期（自相关）
blues = [m['blue'] for m in rows if m]
n = len(blues)
mu = sum(blues) / n
sd = (sum((b - mu) ** 2 for b in blues) / n) ** 0.5 or 1
ac_best, lag_best = 0, 0
for lag in range(6, min(180, n // 2)):
    s = 0; c = 0
    for i in range(n - lag):
        s += (blues[i] - mu) * (blues[i + lag] - mu); c += 1
    ac = s / c / (sd * sd)
    if ac > ac_best:
        ac_best, lag_best = ac, lag
print('blue 脉动自相关: 最佳 lag=%d 帧 = %.2fs (ac=%.2f)' % (lag_best, lag_best / FPS, ac_best))
# 眼半径（呼吸幅度）
rrs = [m['rr'] for m in rows if m]
print('眼半径 min/med/max: %.1f / %.1f / %.1f px (呼吸幅度 ±%.1f%%)' % (
    min(rrs), sorted(rrs)[len(rrs)//2], max(rrs),
    (max(rrs) - min(rrs)) / 2 / (sum(rrs)/len(rrs)) * 100))
