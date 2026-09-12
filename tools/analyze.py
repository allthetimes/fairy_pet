# -*- coding: utf-8 -*-
"""
tools.analyze — 帧分析（numpy/PIL，无 Playwright）

子命令：
  detect-eye      egg.mp4 帧逐帧定位 Fairy 眼睛 + 中心白盘验证
  locate-eye      精确框出右眼亮蓝环（f0180 = t=3s）
  scan-objects    扫描 BV1CkcbzgEkC 整画面所有"蓝眼睛状"物体
  full-scan       egg.mp4 全片抽帧 + 逐帧指标 + 事件 + 自相关周期
  fixed-scan      egg.mp4 固定位置裁剪 + 暗核心检测 + 分块时序
  frame-diff      BV1CkcbzgEkC 60fps 帧差分 + 多指标 + 主周期 + 径向热力
  eye-metrics     eye_crops/ 160x160 归一化指标
  iris-metrics    frames_iris_pulse/ 12fps 逐层 bbox
  iris-period     frames_iris_pulse/ 各层面积 + 自相关找主周期 + 跨相关
  disc-pulse      frames_hifps2/ 60fps 白盘 + 虹膜核心 + 外环内缘三组时间序列 + FFT
  corner-angles   frames_hifps2/ 尖角角度分析 v2（取代 v1 corner_angles.py）
  corners-grid    frames_hifps2/ 0-15s 每 0.5s 一帧右眼尖角拼图
  measure-corners frames_hifps2/ 四尖角暗蓝像素时序 + 周期
  measure-period  frames_hifps2/ 内部圆面积精确周期（30fps 采样）
"""
import argparse
import math
import os
import statistics
import sys
from pathlib import Path

# 让 `python tools/analyze.py` 与 `python -m tools.analyze` 两种调用都能 import tools.*
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from PIL import Image

from tools.common import (
    ROOT,
    is_blue_ring, is_white, is_dark_navy, is_deep_blue,
    list_frames, load_frame, load_indexed,
    ray_walk,
    fft_top_peaks, autocorr_top,
)


# ============== 复用：色彩分类与检测 ==============

def _blue_outer_pred(r, g, b):
    """用于「蓝环聚类」类检测的宽松阈值（detect_eye / full_scan / fixed_scan / scan_all_objects）"""
    return b > 150 and b - r > 110 and b - g > 70 and g < 130


def _blue_ring_strict(r, g, b):
    """locate_eye 用的更严阈值"""
    return b > 190 and b - r > 130 and b - g > 90 and r < 110


def _classify_iris_layer(r, g, b):
    """与 iris_metrics.py / iris_period.py / frame_diff_analysis.py 的 classify 对齐"""
    if r > 150 and g > 145 and b > 150:
        return 'white'
    if 120 <= r <= 140 and 130 <= g <= 150 and 190 <= b <= 210:
        return 'iris_outer'
    if 40 <= r <= 80 and 90 <= g <= 110 and 180 <= b <= 200:
        return 'iris_mid'
    if r < 60 and g < 100 and 100 < b < 160:
        return 'core'
    if r > 200 and g > 200 and b > 200:
        return 'glint'
    if b > 130 and b - r > 110 and b - g > 70 and r < 80:
        return 'ring'
    return None


def _classify_fd(r, g, b):
    """frame_diff_analysis.py 的 6 类分类"""
    if r > 150 and g > 145 and b > 150: return 'W'
    if 120 <= r <= 140 and 130 <= g <= 150 and 190 <= b <= 210: return 'O'
    if 40 <= r <= 80 and 90 <= g <= 110 and 180 <= b <= 200: return 'M'
    if r < 60 and g < 100 and 100 < b < 160: return 'C'
    if r > 200 and g > 200 and b > 200: return 'G'
    if b > 130 and b - r > 110 and b - g > 70 and r < 80: return 'R'
    return None


# ============== 子命令函数 ==============

def detect_eye():
    """逐帧检测 Fairy 眼睛：亮蓝外环聚类 + 中心白盘验证"""
    def detect(img):
        im = img.convert('RGB'); W, H = im.size; px = im.load()
        step = max(1, min(W, H) // 240)
        xs, ys = [], []
        for y in range(0, H, step):
            for x in range(0, W, step):
                if _blue_outer_pred(*px[x, y]):
                    xs.append(x); ys.append(y)
        if len(xs) < 40:
            return None
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        w, h = x1 - x0, y1 - y0
        if w < 30 or h < 30 or w > W * 0.9 or h > H * 0.9 or not (0.5 < w / h < 2.0):
            return None
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        r_est = (w + h) / 4
        rr = int(r_est * 0.6)
        white = tot = 0
        for y in range(max(0, cy - rr), min(H, cy + rr), max(1, step)):
            for x in range(max(0, cx - rr), min(W, cx + rr), max(1, step)):
                rr2, g, b = px[x, y]
                tot += 1
                if rr2 > 150 and g > 150 and b > 150:
                    white += 1
        if tot == 0 or white / tot < 0.12:
            return None
        return cx, cy, r_est, len(xs), white / tot

    for outdir, fps in [('frames_egg', 2.0), ('frames_voice', 2.0)]:
        d = ROOT / outdir
        files = sorted([f for f in d.iterdir() if f.suffix.lower() == '.jpg'])
        hits = []
        for f in files:
            res = detect(Image.open(f))
            if res:
                t = int(f.stem[1:]) / fps
                hits.append((t, f.name) + res)
        print(f'== {outdir}: {len(hits)}/{len(files)} frames with eye ==')
        if hits:
            runs = []
            cur = [hits[0]]
            for h in hits[1:]:
                if h[0] - cur[-1][0] <= 1.6:
                    cur.append(h)
                else:
                    runs.append(cur); cur = [h]
            runs.append(cur)
            for run in runs:
                if len(run) >= 3:
                    rads = [x[4] for x in run]
                    print(f'  t={run[0][0]:6.1f}-{run[-1][0]:6.1f}s  n={len(run):3d}  '
                          f'c=({sum(x[2] for x in run)//len(run)},{sum(x[3] for x in run)//len(run)})  '
                          f'r~{sum(rads)/len(rads):.0f}')


def locate_eye():
    """精确框出右眼亮蓝环（f0180 = t=3s）"""
    from PIL import ImageDraw
    D = ROOT / 'frames_hifps2'
    files = list_frames(D)
    img = Image.open(files[180]).convert('RGB')
    W, H = img.size; px = img.load()

    xs, ys = [], []
    for y in range(H):
        for x in range(W // 2, W):  # 右半边
            if _blue_ring_strict(*px[x, y]):
                xs.append(x); ys.append(y)

    print(f'亮蓝像素数: {len(xs)}')
    if xs:
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        print(f'包围盒 x {x0}-{x1} (w={x1-x0})  y {y0}-{y1} (h={y1-y0})')
        print(f'中心 ({(x0+x1)//2}, {(y0+y1)//2})  半径 ~{(x1-x0+y1-y0)//4}')

    vis = img.copy()
    d = ImageDraw.Draw(vis)
    if xs:
        d.rectangle([x0, y0, x1, y1], outline=(255, 0, 0), width=4)
        d.line([x0, (y0+y1)//2, x1, (y0+y1)//2], fill=(255, 255, 0), width=2)
        d.line([(x0+x1)//2, y0, (x0+x1)//2, y1], fill=(255, 255, 0), width=2)
    out = ROOT / 'full_frames' / '_locate.png'
    out.parent.mkdir(parents=True, exist_ok=True)
    vis.save(out)
    print('saved', out)


def scan_objects():
    """扫描 BV1CkcbzgEkC 整画面所有"蓝眼睛状"物体"""
    from collections import Counter
    D = ROOT / 'frames_hifps2'
    files = list_frames(D)
    for f in [files[10], files[300], files[700]]:
        img = Image.open(f).convert('RGB')
        W, H = img.size; px = img.load()
        step = 8
        hits = []
        for y in range(0, H, step):
            for x in range(0, W, step):
                if b_strong := (b := px[x, y][2]) > 140 and b - px[x, y][0] > 100 and b - px[x, y][1] > 60 and px[x, y][1] < 140:
                    hits.append((x, y))
        grid = {}
        for x, y in hits:
            key = (x // 200, y // 200)
            grid.setdefault(key, []).append((x, y))
        clusters = []
        for k, pts in grid.items():
            if len(pts) < 15: continue
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            clusters.append((len(pts), min(xs), max(xs), min(ys), max(ys)))
        clusters.sort(reverse=True)
        print(f'\n=== {f.name} ({W}x{H}) 蓝块 {len(hits)} 个 ===')
        for n, x0, x1, y0, y1 in clusters[:8]:
            print(f'  块: {n:4d} px  x {x0:4d}-{x1:4d} (w={x1-x0:4d})  '
                  f'y {y0:4d}-{y1:4d} (h={y1-y0:4d})  中心 ({(x0+x1)//2},{(y0+y1)//2})')
        c = Counter()
        for y in range(0, H, 16):
            for x in range(0, W, 16):
                r, g, b = px[x, y]
                c[(r // 40 * 40, g // 40 * 40, b // 40 * 40)] += 1
        print('  主色调 top5:', c.most_common(5))


def full_scan():
    """egg.mp4 全片 12fps 抽帧 + 逐帧指标 + 事件检测 + 周期自相关"""
    from .extract import ffmpeg_extract
    outdir = ROOT / 'frames_full'
    outdir.mkdir(parents=True, exist_ok=True)
    for f in outdir.iterdir():
        if f.suffix == '.png':
            f.unlink()
    ffmpeg_extract(
        ROOT / 'ref_video' / 'egg.mp4', outdir,
        fps=12, scale=1440,
    )
    files = list_frames(outdir)
    print('full frames:', len(files))

    FPS = 12
    rows = []
    for f in files:
        img = Image.open(f)
        im = img.convert('RGB'); W, H = im.size; px = im.load()
        step = 3
        xs, ys = [], []
        for y in range(0, H, step):
            for x in range(0, W, step):
                if _blue_outer_pred(*px[x, y]):
                    xs.append(x); ys.append(y)
        if len(xs) < 30:
            rows.append(None); continue
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        bw, bh = x1 - x0, y1 - y0
        if bw < 15 or bh < 15 or not (0.5 < bw / bh < 2.0):
            rows.append(None); continue
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        R_eye = (bw + bh) / 4
        R = int(R_eye * 1.55)
        crop = img.crop((cx - R, cy - R, cx + R, cy + R)).resize((160, 160), Image.BILINEAR)
        cpx = crop.load()
        bx = []; by = []; wx = []; wy = []; dark = []; brt = 0
        for y in range(160):
            for x in range(160):
                r, g, b = cpx[x, y]
                if _blue_outer_pred(r, g, b) and r < 175 and b - r > 100:
                    bx.append(x); by.append(y); brt += r + g + b
                elif r > 150 and g > 145 and b > 150 and (x - 80) ** 2 + (y - 80) ** 2 < 46 * 46:
                    wx.append(x); wy.append(y)
                    if r < 110 and b > 90:
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

    print('\n== 事件 ==')
    ev = []
    for i, m in enumerate(rows):
        if m is None: continue
        t = i / FPS
        tags = []
        if m['open'] < 0.90: tags.append('眯%.2f' % m['open'])
        if m['white'] < 900: tags.append('白%d' % m['white'])
        if m['brt'] < 100: tags.append('暗%.0f' % m['brt'])
        if m['blue'] < 1600: tags.append('蓝%d' % m['blue'])
        if m['ndark'] == 0: tags.append('核心丢失')
        if tags:
            ev.append((t, tags))
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
            print(f'  t={run[0][0]:6.1f}-{run[-1][0]:6.1f}s  {",".join(sorted(alltags))}')
    else:
        print('  无事件')

    nd = [m['ndark'] for m in rows if m]
    if nd:
        print(f'\nndark min/med/max: {min(nd)} / {sorted(nd)[len(nd)//2]} / {max(nd)}')
    gxs = [m['gx'] for m in rows if m and m['ndark'] > 0]
    gys = [m['gy'] for m in rows if m and m['ndark'] > 0]
    if gxs:
        print(f'gx: {min(gxs):+.3f}..{max(gxs):+.3f}  '
              f'gy: {min(gys):+.3f}..{max(gys):+.3f}')

    blues = [m['blue'] for m in rows if m]
    if blues:
        n = len(blues)
        mu = sum(blues) / n
        sd = (sum((b - mu) ** 2 for b in blues) / n) ** 0.5 or 1
        best_ac = autocorr_top(blues, FPS, top=1)
        if best_ac:
            lag, period, ac = best_ac[0]
            print(f'\nblue 脉动自相关: lag={lag} 帧 = {period:.2f}s (ac={ac:.2f})')


def fixed_scan():
    """修正版扫描：固定位置裁剪 + 暗核心检测 + 分块时序"""
    D = ROOT / 'frames_full'
    files = list_frames(D)
    FPS = 12

    def find_near(img, cx, cy, win=120):
        px = img.convert('RGB').load()
        xs, ys = [], []
        for y in range(max(0, cy - win), cy + win, 2):
            for x in range(max(0, cx - win), cx + win, 2):
                if _blue_outer_pred(*px[x, y]):
                    xs.append(x); ys.append(y)
        if len(xs) < 10:
            return None
        return (sum(xs) / len(xs), sum(ys) / len(ys),
                (max(xs) - min(xs) + max(ys) - min(ys)) / 4)

    CXS = []
    for idx in [60, 300, 700, 1100, 1500]:
        img = Image.open(files[idx])
        res = find_near(img, 196, 670)
        print(idx, '->', None if res is None else ('(%.0f,%.0f) r=%.1f' % res))
        if res: CXS.append(res)
    if not CXS:
        print('no CXS — bail')
        return
    CX = int(sum(c[0] for c in CXS) / len(CXS))
    CY = int(sum(c[1] for c in CXS) / len(CXS))
    RR = sum(c[2] for c in CXS) / len(CXS)
    print(f'fixed center=({CX},{CY}) r={RR:.1f}')

    R = int(RR * 1.5)
    rows = []
    for f in files:
        img = Image.open(f)
        crop = img.crop((CX - R, CY - R, CX + R, CY + R)).resize((180, 180), Image.BILINEAR)
        px = crop.load()
        bx = []; by = []; wx = []; wy = []; dark = []; brt = 0
        for y in range(180):
            for x in range(180):
                r, g, b = px[x, y]
                if r < 175 and b - r > 100 and b - g > 60 and g < 135 and (x - 90) ** 2 + (y - 90) ** 2 < 180 * 180:
                    bx.append(x); by.append(y); brt += r + g + b
                elif (x - 90) ** 2 + (y - 90) ** 2 < 52 * 52:
                    if r > 150 and g > 145 and b > 150:
                        wx.append(x); wy.append(y)
                    elif r < 110 and g < 120 and 60 < b < 200 and b > r:
                        dark.append((x, y))
        if not bx:
            rows.append(None); continue
        bb_w = max(bx) - min(bx); bb_h = max(by) - min(by)
        Rn = (bb_w + bb_h) / 4 or 1
        if dark:
            gx = (sum(p[0] for p in dark) / len(dark) - 90) / Rn
            gy = (sum(p[1] for p in dark) / len(dark) - 90) / Rn
        else:
            gx = gy = float('nan')
        rows.append(dict(open=bb_h / max(1, bb_w), blue=len(bx), white=len(wx),
                         ndark=len(dark), gx=gx, gy=gy,
                         brt=brt / len(bx) / 3, scale=(bb_w + bb_h) / 2))

    print('\nt(s) | open  scale  blue  white ndark  gx     gy    brt')
    for i in range(0, len(rows), 12):
        chunk = [m for m in rows[i:i + 12] if m]
        if not chunk: continue
        t = i / FPS
        def med(k):
            v = sorted(m[k] for m in chunk if not math.isnan(m[k])) or [float('nan')]
            return v[len(v) // 2]
        def std(k):
            v = [m[k] for m in chunk if not math.isnan(m[k])]
            if not v: return float('nan')
            mu = sum(v) / len(v)
            return (sum((x - mu) ** 2 for x in v) / len(v)) ** 0.5
        print(f'{t:5.0f} | {med("open"):.2f} {med("scale"):6.1f} {med("blue"):5d} '
              f'{med("white"):5d} {med("ndark"):5d}  {med("gx"):+.2f} {med("gy"):+.2f} '
              f'{med("brt"):5.1f}   (blue sd {std("blue"):.0f})')

    ok = [m for m in rows if m]
    if ok:
        nd = [m['ndark'] for m in ok]
        print(f'\nndark min/med/max: {min(nd)} / {sorted(nd)[len(nd)//2]} / {max(nd)}')
        sc = [m['scale'] for m in ok]; sc_s = sorted(sc)
        print(f'scale p2/med/p98: {sc_s[int(.02*len(sc))]:.1f} / {sc_s[len(sc)//2]:.1f} / {sc_s[int(.98*len(sc))]:.1f}')
        op = [m['open'] for m in ok]; op_s = sorted(op)
        print(f'open p2/med/p98: {op_s[int(.02*len(op))]:.2f} / {op_s[len(op)//2]:.2f} / {op_s[int(.98*len(op))]:.2f}  min={min(op):.2f}')
        gxv = [m['gx'] for m in ok if m['ndark'] > 5]
        gyv = [m['gy'] for m in ok if m['ndark'] > 5]
        if gxv:
            print(f'gx {min(gxv):+.2f}..{max(gxv):+.2f}  gy {min(gyv):+.2f}..{max(gyv):+.2f} (n={len(gxv)})')
        blinks = [(i / FPS, m['open'], m['white']) for i, m in enumerate(rows) if m and m['open'] < 0.85]
        print(f'open<0.85 帧数: {len(blinks)} {blinks[:30]}')


def frame_diff():
    """BV1CkcbzgEkC 0-15s 60fps 综合分析：帧差分 + 多指标 + 自相关 + 径向热力"""
    D = ROOT / 'frames_hifps2'
    files = list_frames(D)
    FPS = 60
    CX, CY = 998, 340
    R = 280; SC = 240

    ser_diff = []; prev_crop = None
    for f in files:
        img = Image.open(f).convert('RGB')
        crop = img.crop((CX - R, CY - R, CX + R, CY + R)).resize((SC, SC), Image.BILINEAR)
        if prev_crop is not None:
            a = prev_crop.load(); b = crop.load()
            s = 0
            for y in range(SC):
                for x in range(SC):
                    ar, ag, ab = a[x, y]; br, bg, bb = b[x, y]
                    s += abs(ar - br) + abs(ag - bg) + abs(ab - bb)
            ser_diff.append(s / (SC * SC * 3))
        prev_crop = crop

    print('=== 帧差分（运动强度）峰值时刻 ===')
    peaks = [(i / FPS, v) for i, v in enumerate(ser_diff) if v > 5]
    print(f'共 {len(peaks)} 帧差分 > 5，前 20：')
    for t, v in peaks[:20]:
        print(f'  t={t:.3f}s  diff={v:.2f}')
    print('  ...')
    print(f'后 5 个：')
    for t, v in peaks[-5:]:
        print(f'  t={t:.3f}s  diff={v:.2f}')
    if len(peaks) > 5:
        from collections import Counter
        gaps = [peaks[i + 1][0] - peaks[i][0] for i in range(len(peaks) - 1)]
        print('\n帧差分峰值间隔分布：')
        for gap, n in sorted(Counter(round(g, 2) for g in gaps).items())[:10]:
            print(f'  {gap:.2f}s × {n}')

    metrics = []
    for i in range(0, len(files), 4):
        img = Image.open(files[i]).convert('RGB')
        crop = img.crop((CX - R, CY - R, CX + R, CY + R)).resize((SC, SC), Image.BILINEAR)
        px = crop.load()
        cnt = {k: 0 for k in 'WOMCGR'}; bsum = cnt.copy(); gsum = cnt.copy(); rsum = cnt.copy()
        totR = totG = totB = 0; n = 0
        for y in range(SC):
            for x in range(SC):
                r, g, b = px[x, y]
                totR += r; totG += g; totB += b; n += 1
                k = _classify_fd(r, g, b)
                if k:
                    cnt[k] += 1; bsum[k] += b; gsum[k] += g; rsum[k] += r
        m = {'t': i / FPS, 'meanB': totB / n, 'meanR': totR / n}
        for k in 'WOMCGR':
            m[f'{k}_n'] = cnt[k]
            if cnt[k] > 0:
                m[f'{k}_bmean'] = bsum[k] / cnt[k]
                m[f'{k}_rmean'] = rsum[k] / cnt[k]
        metrics.append(m)

    def ac(s, label):
        if len(s) < 5: return
        mu = sum(s) / len(s); sd = (sum((x - mu) ** 2 for x in s) / len(s)) ** 0.5
        if sd < 0.01: return
        best = (0, 0)
        for lag in range(2, min(120, len(s) // 3)):
            num = 0
            for i in range(len(s) - lag):
                num += (s[i] - mu) * (s[i + lag] - mu)
            ac_v = num / (len(s) - lag) / sd / sd
            if ac_v > best[0]: best = (ac_v, lag)
        amp = (max(s) - min(s)) / 2 / (sum(s) / len(s)) * 100
        print(f'  {label:10s}  周期={best[1] / 15:.3f}s ac={best[0]:.3f}  ±{amp:.1f}%')

    print('\n=== 各指标主周期（采样 15fps） ===')
    for key in ['meanB', 'meanR', 'W_n', 'O_n', 'M_n', 'C_n', 'G_n', 'R_n',
                'M_bmean', 'O_bmean', 'C_bmean', 'R_bmean']:
        s = [m.get(key) for m in metrics if key in m]
        if len(s) > 20 and max(s) - min(s) > 0.5:
            ac(s, key)


def eye_metrics():
    """eye_crops/ 160x160 归一化眼部逐帧指标"""
    D = ROOT / 'eye_crops'
    files = list_frames(D)
    FPS = 12
    rows = []
    for f in files:
        px = Image.open(f).convert('RGB').load()
        W = H = 160; cx0 = cy0 = 80
        bx = []; by = []; wx = []; wy = []; dark = []; brt_sum = 0
        for y in range(H):
            for x in range(W):
                r, g, b = px[x, y]
                if r < 175 and b - r > 100 and b - g > 60 and g < 135:
                    bx.append(x); by.append(y); brt_sum += (r + g + b)
                elif r > 150 and g > 145 and b > 150 and (x - 80) ** 2 + (y - 80) ** 2 < 46 * 46:
                    wx.append(x); wy.append(y)
                    if r < 110 and b > 90:
                        dark.append((x, y))
        if not bx:
            rows.append((f.name, None)); continue
        bw, bh = max(bx) - min(bx), max(by) - min(by)
        if dark:
            gx = sum(p[0] for p in dark) / len(dark) - cx0
            gy = sum(p[1] for p in dark) / len(dark) - cy0
        else:
            gx = gy = 0.0
        R_eye = (bw + bh) / 4 or 1
        rows.append((f.name, dict(open=bh / bw if bw > 0 else 0, blue=len(bx), white=len(wx),
                                  gx=round(gx / R_eye, 3), gy=round(gy / R_eye, 3),
                                  brt=round(brt_sum / len(bx) / 3, 1))))

    print('t(s) | open  blue  white  gx     gy    brt   | notes')
    for i, (f, m) in enumerate(rows):
        t = i / FPS
        if m is None:
            print(f'{t:5.1f} | ---- 眼睛不可见 ----')
            continue
        note = ''
        if m['open'] < 0.80: note += f'  眯/眨(open={m["open"]:.2f})'
        if m['white'] < 900: note += f'  白盘缩小({m["white"]})'
        if abs(m['gx']) > 0.25 or abs(m['gy']) > 0.25:
            note += f'  核心偏移({m["gx"]:.2f},{m["gy"]:.2f})'
        if i % 6 == 0 or note:
            print(f'{t:5.1f} | {m["open"]:.2f} {m["blue"]:5d} {m["white"]:5d}  '
                  f'{m["gx"]:+.2f} {m["gy"]:+.2f} {m["brt"]:5.1f} |{note}')

    ok = [m for _, m in rows if m]
    if ok:
        print()
        print(f'open  min/med/max: {min(m["open"] for m in ok):.2f} / '
              f'{sorted(m["open"] for m in ok)[len(ok)//2]:.2f} / {max(m["open"] for m in ok):.2f}')
        print(f'blue  min/med/max: {min(m["blue"] for m in ok)} / '
              f'{sorted(m["blue"] for m in ok)[len(ok)//2]} / {max(m["blue"] for m in ok)}')
        print(f'white min/med/max: {min(m["white"] for m in ok)} / '
              f'{sorted(m["white"] for m in ok)[len(ok)//2]} / {max(m["white"] for m in ok)}')
        print(f'gx range: {min(m["gx"] for m in ok):+.2f}..{max(m["gx"] for m in ok):+.2f}   '
              f'gy range: {min(m["gy"] for m in ok):+.2f}..{max(m["gy"] for m in ok):+.2f}')


def iris_metrics():
    """BV1CkcbzgEkC 0-15s 眼部逐帧逐层 bbox（CX,CY 硬编码沿用 iris_metrics.py）"""
    D = ROOT / 'frames_iris_pulse'
    files = list_frames(D)
    FPS = 12
    CX, CY = 1497, 510; R = 430; SC = 240
    rows = []
    for f in files:
        img = Image.open(f).convert('RGB')
        crop = img.crop((CX - R, CY - R, CX + R, CY + R)).resize((SC, SC), Image.BILINEAR)
        px = crop.load()
        layer = {k: [] for k in ['white', 'iris_outer', 'iris_mid', 'core', 'glint', 'ring']}
        for y in range(SC):
            for x in range(SC):
                k = _classify_iris_layer(*px[x, y])
                if k:
                    layer[k].append((x, y))
        m = {}
        for k, pts in layer.items():
            if not pts: m[k] = None; continue
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            m[k] = dict(n=len(pts), cx=sum(xs) / len(xs), cy=sum(ys) / len(ys),
                        x0=min(xs), x1=max(xs), y0=min(ys), y1=max(ys),
                        w=max(xs) - min(xs), h=max(ys) - min(ys))
        rows.append((f.name, m))

    h = SC // 2
    print(f'{"t":>5} | {"ring_n":>7} {"ring_w":>6} | {"white_n":>7} {"white_r":>6} | '
          f'{"irOut_n":>7} {"irOut_r":>6} | {"irMid_n":>7} {"irMid_r":>6} | '
          f'{"core_n":>6} {"core_cx":>6} {"core_cy":>6} | {"glint_n":>6}')
    for i, (f, m) in enumerate(rows):
        if i % 6: continue
        t = i / FPS
        ring = m.get('ring') or {'n': 0, 'w': 0, 'h': 0}
        white = m.get('white') or {'n': 0, 'w': 0, 'h': 0}
        iout = m.get('iris_outer') or {'n': 0, 'w': 0, 'h': 0}
        imid = m.get('iris_mid') or {'n': 0, 'w': 0, 'h': 0}
        core = m.get('core') or {'n': 0, 'cx': 0, 'cy': 0}
        glint = m.get('glint') or {'n': 0}
        print(f'{t:5.1f} | {ring["n"]:7d} {int((ring["w"]+ring["h"])/4):6d} | '
              f'{white["n"]:7d} {int((white["w"]+white["h"])/4):6d} | '
              f'{iout["n"]:7d} {int((iout["w"]+iout["h"])/4):6d} | '
              f'{imid["n"]:7d} {int((imid["w"]+imid["h"])/4):6d} | '
              f'{core["n"]:6d} {core["cx"]-h:+6.1f} {core["cy"]-h:+6.1f} | {glint["n"]:6d}')

    print('\n各层 bbox 直径 min/med/max (±%)：')
    for k in ['ring', 'white', 'iris_outer', 'iris_mid', 'core']:
        vals = []
        for _, m in rows:
            v = m.get(k)
            if v: vals.append((v['w'] + v['h']) / 4)
        if vals:
            print(f'  {k:12s}: {min(vals):.1f} / {statistics.median(vals):.1f} / '
                  f'{max(vals):.1f} (±{(max(vals)-min(vals))/2/(sum(vals)/len(vals))*100:.1f}%)')
    cx_all = []; cy_all = []
    for _, m in rows:
        v = m.get('core')
        if v and v['n'] > 10:
            cx_all.append(v['cx'] - h); cy_all.append(v['cy'] - h)
    if cx_all:
        print(f'\n核心中心偏移 cx {min(cx_all):+.2f}..{max(cx_all):+.2f} '
              f'cy {min(cy_all):+.2f}..{max(cy_all):+.2f}')


def iris_period():
    """iris 圈面积精确周期 + 跨相关"""
    D = ROOT / 'frames_iris_pulse'
    files = list_frames(D)
    FPS = 12
    CX, CY = 1497, 510; R = 430; SC = 240
    ser = {k: [] for k in ['ring', 'white', 'iris_outer', 'iris_mid', 'core']}
    for f in files:
        img = Image.open(f).convert('RGB')
        crop = img.crop((CX - R, CY - R, CX + R, CY + R)).resize((SC, SC), Image.BILINEAR)
        px = crop.load()
        counts = {k: 0 for k in ser}
        for y in range(SC):
            for x in range(SC):
                k = _classify_iris_layer(*px[x, y])
                if k: counts[k] += 1
        for k, v in counts.items():
            ser[k].append(v)

    print(f'{"t":>4} | {"ring":>5} {"iris_o":>6} {"iris_m":>6} {"core":>5} {"white":>5}')
    for i in range(0, len(files), 3):
        t = i / FPS
        print(f'{t:4.1f} | {ser["ring"][i]:5d} {ser["iris_outer"][i]:6d} '
              f'{ser["iris_mid"][i]:6d} {ser["core"][i]:5d} {ser["white"][i]:5d}')

    print()
    for k in ['ring', 'white', 'iris_outer', 'iris_mid', 'core']:
        best = autocorr_top(ser[k], FPS, top=1)
        if best:
            lag, period, ac = best[0]
            amp = round((max(ser[k]) - min(ser[k])) / 2 / (sum(ser[k]) / len(ser[k])) * 100, 1)
            print(f'{k:12s}  最佳周期 lag={lag:2d} ({period:.2f}s ac={ac:.3f})  ±{amp}%')

    print()
    for k in ['iris_outer', 'iris_mid', 'white', 'core']:
        a, b = ser[k], ser['ring']
        ma = sum(a) / len(a); mb = sum(b) / len(b)
        sa = (sum((x - ma) ** 2 for x in a) / len(a)) ** 0.5
        sb = (sum((x - mb) ** 2 for x in b) / len(b)) ** 0.5
        best = (-9, 0)
        for lag in range(-30, 31):
            num = n = 0
            for i in range(len(a)):
                j = i + lag
                if 0 <= j < len(b):
                    num += (a[i] - ma) * (b[j] - mb); n += 1
            ac = num / n / sa / sb if sa * sb > 0 else 0
            if ac > best[0]: best = (ac, lag)
        print(f'xcorr({k}, ring):  lag={best[1]} ({best[1]/FPS:.2f}s) ac={best[0]:.3f}')

    n_o = ser['iris_outer']
    r_med = math.sqrt(sum(n_o) / len(n_o) / math.pi)
    r_min = math.sqrt(min(n_o) / math.pi)
    r_max = math.sqrt(max(n_o) / math.pi)
    print(f'\n蓝灰外圈 √(area/π): {r_min:.1f} / {r_med:.1f} / {r_max:.1f} '
          f'(≈ {min(n_o)}~{max(n_o)} px)')


def disc_pulse():
    """frames_hifps2/ 白盘 + 虹膜核心 + 外环内缘三组时序 + FFT（0.86s 验证）"""
    D = ROOT / 'frames_hifps2'
    files = list_frames(D)
    N_FRAMES = len(files)
    EVERY = 3
    idxs = list(range(0, N_FRAMES, EVERY))
    CENTER = (1011.9, 364.7)
    R_OUTER_PX = 105.0
    ANGLES = [0, 45, 90, 135, 180, 225, 270, 315]

    def first_white_outer_disc(arr, cx, cy, ang):
        return ray_walk(arr, cx, cy, ang, 20, R_OUTER_PX, is_white, run_len=3)

    def iris_core_edge(arr, cx, cy, ang):
        # 沿径向找「最后」深蓝像素 r（向外走直到离开深蓝）
        last_dark = None
        for s in range(2, 60):
            x = int(round(cx + math.cos(math.radians(ang)) * s))
            y = int(round(cy + math.sin(math.radians(ang)) * s))
            if not (0 <= x < arr.shape[1] and 0 <= y < arr.shape[0]):
                break
            r, g, b = int(arr[y, x, 0]), int(arr[y, x, 1]), int(arr[y, x, 2])
            if b >= 120 and r < 130 and b > r + 20:
                last_dark = s
            else:
                if last_dark is not None:
                    break
        return float(last_dark) if last_dark else float('nan')

    def bright_ring_inner(arr, cx, cy, ang):
        # 从外向内找第一个亮蓝像素
        for s in range(int(R_OUTER_PX) - 1, 30, -1):
            x = int(round(cx + math.cos(math.radians(ang)) * s))
            y = int(round(cy + math.sin(math.radians(ang)) * s))
            if not (0 <= x < arr.shape[1] and 0 <= y < arr.shape[0]):
                continue
            r, g, b = int(arr[y, x, 0]), int(arr[y, x, 1]), int(arr[y, x, 2])
            if b > 130 and b - r > 110 and b - g > 70 and r < 130:
                return float(s)
            if r < 95 and g < 105 and 120 < b < 220:
                continue
        return float('nan')

    data_disc = {a: [] for a in ANGLES}
    data_core = {a: [] for a in ANGLES}
    data_bring = {a: [] for a in ANGLES}
    for i in idxs:
        arr = load_frame(files[i])
        for a in ANGLES:
            data_disc[a].append(first_white_outer_disc(arr, *CENTER, a))
            data_core[a].append(iris_core_edge(arr, *CENTER, a))
            data_bring[a].append(bright_ring_inner(arr, *CENTER, a))

    fs = len(idxs) / (idxs[-1] - idxs[0]) * (N_FRAMES / 60.0) * (60.0 / len(idxs))
    fs = len(idxs) / ((idxs[-1] - idxs[0]) / 60.0) / len(idxs)  # 简化
    fs = 60 / EVERY
    dt = 1 / fs

    def report(name, series):
        print(f'\n--- {name} ---')
        print(f'{"ang":>5}  {"med":>6}  {"std":>6}  {"top1":>22}  {"top2":>22}  {"top3":>22}')
        for a in ANGLES:
            x = np.asarray(series[a], dtype=float)
            x = x[~np.isnan(x)]
            if len(x) < 30:
                print(f'{a:>5}  too few ({len(x)})')
                continue
            med = float(np.median(x)); std = float(np.std(x))
            peaks = fft_top_peaks(x, dt, top=3)
            out = [f'{f:.2f}Hz({T:.2f}s,p={p})' for f, T, p in peaks]
            print(f'{a:>5}  {med:6.2f}  {std:6.2f}  ' + '  '.join(f'{o:>22}' for o in out))

    report('WHITE DISC outer edge', data_disc)
    report('IRIS CORE  outer edge', data_core)
    report('BRIGHT RING inner edge', data_bring)


def corner_angles():
    """尖角角度分析 v2"""
    import collections
    D = ROOT / 'frames_hifps2'
    files = list_frames(D)
    CX, CY = 890, 301

    def angle_hist(idx, rmin=80, rmax=150, verbose=True):
        px = Image.open(files[idx]).convert('RGB').load()
        hist = collections.Counter()
        total = 0
        for y in range(CY - rmax, CY + rmax):
            for x in range(CX - rmax, CX + rmax):
                dx, dy = x - CX, y - CY
                d = math.hypot(dx, dy)
                if not (rmin <= d <= rmax):
                    continue
                r, g, b = px[x, y]
                if r < 95 and g < 105 and 120 < b < 220:
                    a = math.degrees(math.atan2(-(y - CY), x - CX))
                    if a < 0: a += 360
                    hist[int(a / 5) * 5] += 1
                    total += 1
        if verbose:
            print(f'\n=== 帧 {idx} (t={idx/60:.2f}s) 尖角像素 {total}，半径 {rmin}-{rmax} ===')
            smooth = {}
            for a in range(0, 360, 5):
                smooth[a] = sum(hist.get((a + o) % 360, 0) for o in [-10, -5, 0, 5, 10])
            peaks = []
            for a in range(0, 360, 5):
                v = smooth[a]
                if v >= 60 and v >= max(smooth.get((a + o) % 360, 0) for o in [-15, -10, -5, 0, 5, 10, 15]):
                    peaks.append((a, v))
            merged = []
            for a, v in peaks:
                if merged and (a - merged[-1][0]) % 360 <= 20:
                    if v > merged[-1][1]: merged[-1] = (a, v)
                else:
                    merged.append((a, v))
            print('  尖角方向（度，0=右 90=上 180=左 270=下）:', ', '.join(f'{a}°(强度{v})' for a, v in merged))
            print('  尖角数量:', len(merged))
            if len(merged) > 1:
                gaps = [(merged[(i + 1) % len(merged)][0] - merged[i][0]) % 360 for i in range(len(merged))]
                print('  相邻间隔:', gaps)
        return total

    for idx in [60, 180, 300, 420, 540, 660, 780, 870]:
        angle_hist(idx)


def corners_grid():
    """0-15s 每 0.5s 一帧右眼尖角 → 6x5 网格图"""
    D = ROOT / 'frames_hifps2'
    files = list_frames(D)
    times = list(range(0, 900, 30))  # 0..870 共 30 个
    crops = []
    for i in times:
        img = Image.open(files[i]).convert('RGB')
        crop = img.crop((890 - 230, 301 - 230, 890 + 230, 301 + 230)).resize((260, 260), Image.LANCZOS)
        crops.append(crop)
    COLS, ROWS = 6, 5
    grid = Image.new('RGB', (COLS * 260, ROWS * 260), (0, 0, 0))
    for i, c in enumerate(crops):
        grid.paste(c, ((i % COLS) * 260, (i // COLS) * 260))
    out = ROOT / 'compare_events' / 'corners_seq.png'
    out.parent.mkdir(parents=True, exist_ok=True)
    grid.save(out)
    print('saved', out, grid.size, 'frames =', len(times))


def measure_corners():
    """四尖角暗蓝像素时序 + 周期自相关"""
    import collections
    D = ROOT / 'frames_hifps2'
    files = list_frames(D)
    FPS = 60
    CX, CY = 890, 301; RMAX = 215

    positions = []
    for i in range(0, len(files), 5):
        px = Image.open(files[i]).convert('RGB').load()
        pts = []
        for y in range(max(0, CY - RMAX), min(px.__self__.size[1] if hasattr(px, '__self__') else 800, CY + RMAX), 2):
            for x in range(max(0, CX - RMAX), min(800, CX + RMAX), 2):
                dx, dy = x - CX, y - CY
                if dx * dx + dy * dy > RMAX * RMAX: continue
                r, g, b = px[x, y]
                if r < 50 and g < 60 and 100 < b < 180:
                    pts.append((x, y))
        if not pts:
            positions.append({'t': i / FPS, 'n': 0})
            continue
        angles = []
        for x, y in pts:
            a = math.degrees(math.atan2(y - CY, x - CX))
            if a < 0: a += 360
            angles.append(a)
        hist = collections.Counter(int(a / 20) * 20 for a in angles)
        top4 = hist.most_common(4)
        positions.append({'t': i / FPS, 'n': len(pts), 'top4': sorted(top4)})

    print('t(s)   n   top4 角度（度）— 暗蓝尖角')
    for p in positions[::3]:
        s = ', '.join(f'{a}°:{n}' for a, n in p['top4']) if p.get('top4') else '-'
        print(f'{p["t"]:5.2f}  {p["n"]:4d}  {s}')

    n_series = [p['n'] for p in positions]
    print(f'\n尖角总像素: min={min(n_series)} max={max(n_series)} '
          f'mean={sum(n_series)/len(n_series):.0f} '
          f'±{(max(n_series)-min(n_series))/2/(sum(n_series)/len(n_series))*100:.1f}%')
    best = autocorr_top(n_series, 12, top=1)
    if best:
        lag, period, ac = best[0]
        print(f'尖角像素数周期: lag={lag} ({period:.3f}s ac={ac:.3f})')


def measure_period():
    """内部圆面积精确周期（30fps 采样）"""
    D = ROOT / 'frames_hifps2'
    files = list_frames(D)
    FPS = 60
    CX, CY = 890, 301; RMAX = 215

    series_outer = []; series_inner = []; series_core = []; etimes = []
    for i in range(0, len(files), 2):
        px = Image.open(files[i]).convert('RGB').load()
        no = ni = nc = 0
        for y in range(max(0, CY - RMAX), min(800, CY + RMAX), 2):
            for x in range(max(0, CX - RMAX), min(800, CX + RMAX), 2):
                dx, dy = x - CX, y - CY
                if dx * dx + dy * dy > RMAX * RMAX: continue
                r, g, b = px[x, y]
                if b > 170 and b - r > 110 and b - g > 80 and r < 110: no += 1
                elif 110 <= r <= 175 and 120 <= g <= 180 and 175 <= b <= 235: ni += 1
                elif r < 90 and g < 110 and 120 < b < 190: nc += 1
        series_outer.append(no); series_inner.append(ni); series_core.append(nc)
        etimes.append(i / FPS)

    print(f'n = {len(series_outer)}  采样率 30fps, 时长 {round(etimes[-1], 1)}s')

    def stats(name, s):
        mu = sum(s) / len(s)
        print(f'{name}: min={min(s)} max={max(s)} mean={mu:.0f} '
              f'±{(max(s) - min(s)) / 2 / mu * 100:.1f}%')

    stats('外环', series_outer); stats('内部圆', series_inner); stats('核心', series_core)
    print()
    for name, s in [('外环', series_outer), ('内部圆', series_inner), ('核心', series_core)]:
        best = autocorr_top(s, 30, top=1)
        if best:
            lag, period, ac = best[0]
            print(f'{name}: 主周期 = {period:.3f}s  (ac={ac:.3f}, lag={lag} 帧@30fps)')

    ratio = [i / o if o else 0 for i, o in zip(series_inner, series_outer)]
    best = autocorr_top(ratio, 30, top=1)
    if best:
        lag, period, ac = best[0]
        print(f'内部圆/外环 比值: 主周期 = {period:.3f}s  ac={ac:.3f}')
    stats('内部圆/外环比值', [r * 1000 for r in ratio])

    print('\n前 60 样本（每样本 1/30 s）：')
    print(' t    外环  内部圆  核心')
    for k in range(min(60, len(etimes))):
        print(f'{etimes[k]:5.2f}  {series_outer[k]:5d}  {series_inner[k]:6d}  {series_core[k]:5d}')


# ============== argparse ==============

DISPATCH = {
    'detect-eye': detect_eye,
    'locate-eye': locate_eye,
    'scan-objects': scan_objects,
    'full-scan': full_scan,
    'fixed-scan': fixed_scan,
    'frame-diff': frame_diff,
    'eye-metrics': eye_metrics,
    'iris-metrics': iris_metrics,
    'iris-period': iris_period,
    'disc-pulse': disc_pulse,
    'corner-angles': corner_angles,
    'corners-grid': corners_grid,
    'measure-corners': measure_corners,
    'measure-period': measure_period,
}


def main():
    p = argparse.ArgumentParser(description='fairy-pet 帧分析工具')
    p.add_argument('cmd', choices=sorted(DISPATCH.keys()))
    args = p.parse_args()
    DISPATCH[args.cmd]()


if __name__ == '__main__':
    main()