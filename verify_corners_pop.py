# -*- coding: utf-8 -*-
# 验证：四个朝外尖刺的 2.0s 伸缩
#  - 截 8 帧（跨 2.0s，每 250ms）
#  - 逐帧量「暗蓝楔形像素在 r>80 区域内的最大半径」，即尖刺凸出长度
#  - 量 4 个方向的尖刺是否同相
import os
import math
from playwright.sync_api import sync_playwright
from PIL import Image

BASE = r'D:\work\fairy-pet'
OUT = os.path.join(BASE, 'compare_corners_pop')
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.png'):
        os.remove(os.path.join(OUT, f))

N = 8
with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome')
    page = b.new_page(viewport={'width': 360, 'height': 380})
    page.goto('file:///' + (BASE + r'\renderer\index.html').replace('\\', '/'))
    page.wait_for_timeout(1400)
    page.evaluate("document.getElementById('bubble').classList.add('hidden')")
    # 只保留 #corners 的动画，冻结其他层，便于单独观察尖刺
    page.evaluate("""
      for (const id of ['brightRing','ringGlow','halo','irisPulse']) {
        document.getElementById(id).style.animation = 'none';
      }
      const c = document.getElementById('corners');
      c.style.animation = 'none';
      c.getBoundingClientRect();
      c.style.animation = '';
    """)
    for i in range(N):
        page.wait_for_timeout(250)
        page.screenshot(path=os.path.join(OUT, f'p{i}.png'))
    vals = page.evaluate("""() => {
      const out = [];
      const el = document.getElementById('corners');
      return { t: getComputedStyle(el).transform };
    }""")
    print('last transform:', vals)
    b.close()


def to_px(th, rr, cx, cy):
    a = math.radians(th)
    return cx + rr * math.cos(a), cy + rr * math.sin(a)


cx, cy = 180.0, 190.0 - 26 + 0  # #boot bottom:26 => svg 顶在 380-240-26=114? 用实测中心更稳
# 实测：stage 360x380，#boot 宽高 240、left 50% margin-left -120 → svg x:60..300；
# bottom 26 → svg y: 380-26-240=114 .. 354。viewBox 240 → 1 svg unit = 1 px；中心 = (180, 234)
cx, cy = 180.0, 234.0

prof = []
for i in range(N):
    im = Image.open(os.path.join(OUT, f'p{i}.png')).convert('RGB')
    px = im.load()
    row = []
    for th in (270, 0, 90, 180):          # 上 / 右 / 下 / 左
        best = None
        for deg in [th + d for d in range(-14, 15)]:
            for rr in [x * 0.25 for x in range(280, 420)]:   # r 70..105
                x, y = to_px(deg, rr, cx, cy)
                xi, yi = int(round(x)), int(round(y))
                if not (0 <= xi < im.width and 0 <= yi < im.height):
                    continue
                r, g, bb = px[xi, yi]
                # 楔形色 #232A8F = (35,42,143)
                if abs(r - 35) <= 12 and abs(g - 42) <= 12 and abs(bb - 143) <= 14:
                    if best is None or rr > best:
                        best = rr
        row.append(round(best, 1) if best else None)
    prof.append(row)

print('\nframe (0.25s each)  top / right / bottom / left 尖刺尖端半径  (r=80 为齐平, r=90 为峰值)')
for i, row in enumerate(prof):
    print('t=%.2fs  %s' % (i * 0.25, '  '.join('%6s' % (v if v is not None else '--') for v in row)))

# 拼图
crops = [Image.open(os.path.join(OUT, f'p{i}.png')).convert('RGB') for i in range(N)]
w, h = crops[0].size
grid = Image.new('RGB', (w * 4, h * 2), (255, 255, 255))
for i, c in enumerate(crops):
    grid.paste(c, ((i % 4) * w, (i // 4) * h))
grid.save(os.path.join(OUT, '_grid.png'))
print('saved', os.path.join(OUT, '_grid.png'), grid.size)
