# -*- coding: utf-8 -*-
# 验证 0.5s 同步脉冲：每 100ms 截图共 6 张（覆盖 0.5s 周期）
import os
from playwright.sync_api import sync_playwright
from PIL import Image

BASE = r'D:\work\fairy-pet'
OUT = os.path.join(BASE, 'compare_pulse05')
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.png'):
        os.remove(os.path.join(OUT, f))

with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome')
    page = b.new_page(viewport={'width': 360, 'height': 380})
    page.goto('file:///' + (BASE + r'\renderer\index.html').replace('\\', '/'))
    page.wait_for_timeout(1400)
    page.evaluate("document.getElementById('bubble').classList.add('hidden'); document.getElementById('fairy-svg').style.filter='none'")

    # 同步所有动画到相位 0
    page.evaluate("""
      const els = [document.getElementById('brightRing'), document.getElementById('ringGlow'), document.getElementById('halo')];
      for (const el of document.querySelectorAll('.r-outer,.r-mid,.r-core,.r-glint')) els.push(el);
      for (const el of els) el.style.animation = 'none';
      document.getElementById('brightRing').getBoundingClientRect();
      for (const el of els) el.style.animation = '';
    """)

    for i in range(6):
        page.wait_for_timeout(100)
        page.screenshot(path=os.path.join(OUT, f'p{i*0.1:.1f}.png'))

    # 同时取 computed style 验证 stroke-width / transform
    cs = page.evaluate("""() => ({
      o: getComputedStyle(document.querySelector('.r-outer')).strokeWidth,
      m: getComputedStyle(document.querySelector('.r-mid')).strokeWidth,
      c: getComputedStyle(document.querySelector('.r-core')).transform,
      r: getComputedStyle(document.getElementById('brightRing')).strokeWidth,
      g: getComputedStyle(document.getElementById('ringGlow')).opacity
    })""")
    print('peak computed style:', cs)
    b.close()

# 像素：每张的 4 个圆描边像素数
def measure(im):
    px = im.convert('RGB').load(); W, H = im.size
    layers = {
        'r-core':  (lambda r,g,b: r<60 and g<100 and 100<b<160),
        'r-mid':   (lambda r,g,b: 40<=r<=80 and 90<=g<=110 and 180<=b<=200),
        'r-outer': (lambda r,g,b: 120<=r<=140 and 130<=g<=150 and 190<=b<=210),
        'ring':    (lambda r,g,b: b>130 and b-r>110 and b-g>70 and r<80),
    }
    out = {}
    for k, f in layers.items():
        n = 0
        for y in range(H):
            for x in range(W):
                r, g, b = px[x, y]
                if f(r, g, b): n += 1
        out[k] = n
    return out

print(f'{"t":>4} | {"core":>5} {"mid":>5} {"outer":>5} {"ring":>5}')
for i in range(6):
    t = i * 0.1
    p = os.path.join(OUT, f'p{t:.1f}.png')
    m = measure(Image.open(p))
    print(f'{t:.1f} | {m["r-core"]:5d} {m["r-mid"]:5d} {m["r-outer"]:5d} {m["ring"]:5d}')