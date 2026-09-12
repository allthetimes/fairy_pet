# -*- coding: utf-8 -*-
# 验证：统一 0.86s 同步呼吸 —— 截 6 帧 + 量测外环/尖角/内部圆
import os
from playwright.sync_api import sync_playwright
from PIL import Image

BASE = r'D:\work\fairy-pet'
OUT = os.path.join(BASE, 'compare_full_breathe')
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
                   document.getElementById('halo'), document.getElementById('irisPulse'),
                   document.getElementById('corners')];
      for (const el of els) el.style.animation = 'none';
      document.getElementById('brightRing').getBoundingClientRect();
      for (const el of els) el.style.animation = '';
    """)

    # 0.86s 周期，每 144ms 一帧，共 6 帧
    for i in range(6):
        page.wait_for_timeout(144)
        page.screenshot(path=os.path.join(OUT, f'p{i}.png'))

    cs = page.evaluate("""() => ({
      iris:  getComputedStyle(document.getElementById('irisPulse')).transform,
      corn:  getComputedStyle(document.getElementById('corners')).transform,
      br:    getComputedStyle(document.getElementById('brightRing')).strokeWidth,
      glow:  getComputedStyle(document.getElementById('ringGlow')).opacity,
      halo:  getComputedStyle(document.getElementById('halo')).transform,
    })""")
    print('computed:', cs)
    b.close()

# 拼成 6 帧横排
crops = [Image.open(os.path.join(OUT, f'p{i}.png')).convert('RGB') for i in range(6)]
w, h = crops[0].size
grid = Image.new('RGB', (w * 6, h), (0, 0, 0))
for i, c in enumerate(crops):
    grid.paste(c, (i * w, 0))
grid.save(os.path.join(OUT, '_strip.png'))
print('saved', grid.size)