# -*- coding: utf-8 -*-
# BV1CkcbzgEkC 0-15s 眼部逐帧分析 —— 重点：核心 / iris 各圈是否变化
import os, math
from PIL import Image

BASE = r'D\work\fairy-pet' if False else r'D:\work\fairy-pet'
D = os.path.join(BASE, 'frames_iris_pulse')
files = sorted(f for f in os.listdir(D) if f.endswith('.png'))
FPS = 12

# 固定眼睛中心（采样均值）
CX, CY = 1497, 510
# 在 1920 宽下眼 r~390，裁剪半径 = 1.1×r
R = 430
SC = 240   # 裁剪后 resize 到 240×240（与我的 SVG 视口一致）

# 各颜色阈值（RGB）
COLORS = {
    'blue_ring':   dict(r_max=80, g_max=120, b_min=130, b_minus_r_min=110, b_minus_g_min=70),  # 亮蓝 #2D3FE8
    'white_disc':  dict(r_min=150, g_min=145, b_min=150),                                       # 白
    'iris_outer':  dict(r_in=(120,140), g_in=(130,150), b_in=(190,210)),                        # #808CC5 蓝灰
    'iris_mid':    dict(r_in=(40,80), g_in=(90,110), b_in=(180,200)),                          # #3164C0 中蓝
    'core_dark':   dict(r_max=60, g_max=100, b_in=(100,160)),                                   # 深蓝核心
    'glint':       dict(r_min=200, g_min=200, b_min=200),                                       # 白高光
}

def classify(r, g, b):
    """返回这一像素最可能的层（按优先级），或 None"""
    # 1. 白盘
    if r > 150 and g > 145 and b > 150:
        return 'white_disc'
    # 2. iris_outer 蓝灰圈
    if 120 <= r <= 140 and 130 <= g <= 150 and 190 <= b <= 210:
        return 'iris_outer'
    # 3. iris_mid 中蓝圈
    if 40 <= r <= 80 and 90 <= g <= 110 and 180 <= b <= 200:
        return 'iris_mid'
    # 4. 核心深蓝
    if r < 60 and g < 100 and 100 < b < 160:
        return 'core_dark'
    # 5. 高光
    if r > 200 and g > 200 and b > 200:
        return 'glint'
    # 6. 亮蓝环
    if b > 130 and b - r > 110 and b - g > 70 and r < 80:
        return 'blue_ring'
    return None

# 逐帧：分类 + 统计每层像素数 + 中心 + bbox
rows = []
for f in files:
    img = Image.open(os.path.join(D, f)).convert('RGB')
    crop = img.crop((CX - R, CY - R, CX + R, CY + R)).resize((SC, SC), Image.BILINEAR)
    px = crop.load()
    h = SC // 2
    layer_pixels = {k: [] for k in COLORS}    # [(x,y)...]
    for y in range(SC):
        for x in range(SC):
            r, g, b = px[x, y]
            k = classify(r, g, b)
            if k:
                layer_pixels[k].append((x, y))
    m = {}
    for k, pts in layer_pixels.items():
        if not pts:
            m[k] = None; continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        m[k] = dict(
            n=len(pts),
            cx=sum(xs)/len(xs), cy=sum(ys)/len(ys),
            x0=min(xs), x1=max(xs), y0=min(ys), y1=max(ys),
            w=max(xs)-min(xs), h=max(ys)-min(ys),
        )
    rows.append((f, m))

# 打印：每 6 帧一行（0.5s 一步）
print(f'{"t":>5} | '
      f'{"ring_n":>7} {"ring_w":>6} | '
      f'{"white_n":>7} {"white_r":>6} | '
      f'{"irOut_n":>7} {"irOut_r":>6} | '
      f'{"irMid_n":>7} {"irMid_r":>6} | '
      f'{"core_n":>6} {"core_cx":>6} {"core_cy":>6} | '
      f'{"glint_n":>6}')
for i, (f, m) in enumerate(rows):
    if i % 6: continue
    t = i / FPS
    def get(k):
        v = m.get(k)
        if v is None: return ('    -', '    -')
        if k == 'blue_ring' or k == 'white_disc' or k == 'iris_outer' or k == 'iris_mid':
            return (v['n'], round((v['w']+v['h'])/4, 0))
        if k == 'core_dark':
            return (v['n'], round(v['cx']-h, 1), round(v['cy']-h, 1))
        if k == 'glint':
            return (v['n'],)
        return (v['n'],)
    ring = m['blue_ring'] or {'n': 0, 'w': 0, 'h': 0}
    white = m['white_disc'] or {'n': 0, 'w': 0, 'h': 0}
    iout = m['iris_outer'] or {'n': 0, 'w': 0, 'h': 0}
    imid = m['iris_mid'] or {'n': 0, 'w': 0, 'h': 0}
    core = m['core_dark'] or {'n': 0, 'cx': 0, 'cy': 0}
    glint = m['glint'] or {'n': 0}
    print(f'{t:5.1f} | {ring["n"]:7d} {int((ring["w"]+ring["h"])/4):6d} | '
          f'{white["n"]:7d} {int((white["w"]+white["h"])/4):6d} | '
          f'{iout["n"]:7d} {int((iout["w"]+iout["h"])/4):6d} | '
          f'{imid["n"]:7d} {int((imid["w"]+imid["h"])/4):6d} | '
          f'{core["n"]:6d} {core["cx"]-h:+6.1f} {core["cy"]-h:+6.1f} | '
          f'{glint["n"]:6d}')

# 统计每层 bbox 直径的最小/中/最大
import statistics
def stats(key):
    vals = []
    for _, m in rows:
        v = m.get(key)
        if v: vals.append((v['w']+v['h'])/4)
    if not vals: return None
    return (min(vals), statistics.median(vals), max(vals),
            round((max(vals)-min(vals))/2/(sum(vals)/len(vals))*100, 1))

print('\n各层 bbox 直径 min/med/max (±%)：')
for k in COLORS:
    s = stats(k)
    if s: print(f'  {k:12s}: {s[0]:.1f} / {s[1]:.1f} / {s[2]:.1f} (±{s[3]}%)')

# 核心位置范围（找白盘内深蓝区域）
cx_all = []; cy_all = []
for _, m in rows:
    v = m.get('core_dark')
    if v and v['n'] > 10:
        cx_all.append(v['cx']-h); cy_all.append(v['cy']-h)
if cx_all:
    print(f'\n核心中心偏移 cx {min(cx_all):+.2f}..{max(cx_all):+.2f} (σ {(sum(x*x for x in cx_all)/len(cx_all))**0.5:.2f})  '
          f'cy {min(cy_all):+.2f}..{max(cy_all):+.2f} (σ {(sum(x*x for x in cy_all)/len(cy_all))**0.5:.2f})')