# -*- coding: utf-8 -*-
# 验证波纹扩散：每 200ms 截图共 8 张（覆盖 1.5s 周期）
# 量测每张里 4 个圆的 bbox 直径，验证时序
import os
from playwright.sync_api import sync_playwright
from PIL import Image

BASE = r'D:\work\fairy-pet'
OUT = os.path.join(BASE, 'compare_ripple')
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

    # 重启所有动画到相位 0
    page.evaluate("""
      const els = ['brightRing','ringGlow','halo'].map(id=>document.getElementById(id))
      for (const el of document.querySelectorAll('.ripple')) els.push(el);
      for (const el of els) { el.style.animation = 'none'; }
      document.getElementById('brightRing').getBoundingClientRect();
      for (const el of els) { el.style.animation = ''; }
    """)

    # 200ms 间隔 8 张
    for i in range(8):
        page.wait_for_timeout(200)
        page.screenshot(path=os.path.join(OUT, f'ph{i*0.2:.1f}.png'))
    b.close()

# 像素测：每张图 4 个圆 + 蓝环外缘 的 bbox 直径
def measure(im):
    px = im.convert('RGB').load(); W, H = im.size
    layers = {
        'r-core':   (lambda r,g,b: r<60 and g<100 and 100<b<160),
        'r-mid':    (lambda r,g,b: 40<=r<=80 and 90<=g<=110 and 180<=b<=200),
        'r-outer':  (lambda r,g,b: 120<=r<=140 and 130<=g<=150 and 190<=b<=210),
        'ring':     (lambda r,g,b: b>130 and b-r>110 and b-g>70 and r<80),
    }
    out = {}
    for k, f in layers.items():
        xs, ys = [], []
        for y in range(H):
            for x in range(W):
                r, g, b = px[x, y]
                if f(r, g, b): xs.append(x); ys.append(y)
        if xs:
            out[k] = ((max(xs)-min(xs)+max(ys)-min(ys))/2, len(xs))
        else:
            out[k] = (0, 0)
    return out

print(f'{"t":>4} | {"core_d":>6} {"core_n":>6} | {"mid_d":>6} {"mid_n":>6} | {"outer_d":>6} {"outer_n":>6} | {"ring_d":>6} {"ring_n":>6}')
for i in range(8):
    t = i * 0.2
    p = os.path.join(OUT, f'ph{t:.1f}.png')
    m = measure(Image.open(p))
    print(f'{t:.1f} | {m["r-core"][0]:6.1f} {m["r-core"][1]:6d} | {m["r-mid"][0]:6.1f} {m["r-mid"][1]:6d} | {m["r-outer"][0]:6.1f} {m["r-outer"][1]:6d} | {m["ring"][0]:6.1f} {m["ring"][1]:6d}')