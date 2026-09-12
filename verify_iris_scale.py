# -*- coding: utf-8 -*-
# 验证：眼睛里的圆 0.5s 缩放呼吸
import os
from playwright.sync_api import sync_playwright
from PIL import Image

BASE = r'D:\work\fairy-pet'
OUT = os.path.join(BASE, 'compare_iris_scale')
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.png'):
        os.remove(os.path.join(OUT, f))

with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome')
    page = b.new_page(viewport={'width': 360, 'height': 380})
    page.goto('file:///' + (BASE + r'\renderer\index.html').replace('\\', '/'))
    page.wait_for_timeout(1400)
    page.evaluate("document.getElementById('bubble').classList.add('hidden')")

    page.evaluate("""
      const els = [document.getElementById('brightRing'), document.getElementById('ringGlow'),
                   document.getElementById('halo'), document.getElementById('irisPulse')];
      for (const el of els) el.style.animation = 'none';
      document.getElementById('brightRing').getBoundingClientRect();
      for (const el of els) el.style.animation = '';
    """)

    # 0.5s 周期，取 8 个相位（每 62.5ms）
    for i in range(8):
        page.wait_for_timeout(62)
        page.screenshot(path=os.path.join(OUT, f'p{i}.png'))

    # 顺便记录峰值时的 computed transform
    page.wait_for_timeout(200)
    peak = page.evaluate("""() => getComputedStyle(document.getElementById('irisPulse')).transform""")
    page.wait_for_timeout(125)
    trough = page.evaluate("""() => getComputedStyle(document.getElementById('irisPulse')).transform""")
    print('irisPulse transform samples:', peak, '|', trough)
    b.close()

# 拼成 2x4 网格便于一眼看全
crops = [Image.open(os.path.join(OUT, f'p{i}.png')).convert('RGB') for i in range(8)]
w, h = crops[0].size
grid = Image.new('RGB', (w * 4, h * 2), (0, 0, 0))
for i, c in enumerate(crops):
    grid.paste(c, ((i % 4) * w, (i // 4) * h))
outp = os.path.join(BASE, 'compare_iris_scale', '_grid.png')
grid.save(outp)
print('saved', outp, grid.size)

# 量测内部圆的像素数变化
print(f'{"帧":>3} | {"蓝灰圈":>6} {"中蓝圈":>6} {"核心":>6}')
for i in range(8):
    im = crops[i]
    px = im.load(); W, H = im.size
    o = m = c = 0
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            if 120 <= r <= 140 and 130 <= g <= 150 and 190 <= b <= 210: o += 1
            elif 40 <= r <= 80 and 90 <= g <= 110 and 180 <= b <= 200: m += 1
            elif r < 60 and g < 100 and 100 < b < 160: c += 1
    print(f'{i:>3} | {o:6d} {m:6d} {c:6d}')