# -*- coding: utf-8 -*-
# 验证 iris 内部圈呼吸：截呼吸峰值 / 谷值 + 眨眼叠加 + 视线叠加
import os
from playwright.sync_api import sync_playwright
from PIL import Image

BASE = r'D:\work\fairy-pet'
OUT = os.path.join(BASE, 'compare_iris')
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

    def restart():
        page.evaluate("""
          const br  = document.getElementById('brightRing');
          const gl  = document.getElementById('ringGlow');
          const hal = document.getElementById('halo');
          const ip  = document.getElementById('irisPulse');
          for (const el of [br, gl, hal, ip]) { el.style.animation = 'none'; }
          br.getBoundingClientRect();
          for (const el of [br, gl, hal, ip]) { el.style.animation = ''; }
        """)

    # iris 呼吸 50% 相位 = peak (1.2s 后)
    restart(); page.wait_for_timeout(1200); page.screenshot(path=os.path.join(OUT, 'iris_peak.png'))
    # iris 呼吸 0% 相位 = trough (再加 1.2s)
    page.wait_for_timeout(1200); page.screenshot(path=os.path.join(OUT, 'iris_trough.png'))

    # 叠加视线 + 眨眼
    page.mouse.move(40, 250); page.wait_for_timeout(400)
    page.evaluate("document.getElementById('iris').classList.add('blinking')")
    page.wait_for_timeout(60)
    page.screenshot(path=os.path.join(OUT, 'gaze_blink.png'))
    page.evaluate("document.getElementById('iris').classList.remove('blinking')")

    b.close()

# 像素测：蓝灰外圈 + 中蓝圈的像素计数 vs 时间相位
from PIL import Image
print(f'{"state":<15} | {"irOut":>5} {"irMid":>5} {"core":>5}')
for f in sorted(os.listdir(OUT)):
    if not f.endswith('.png'): continue
    im = Image.open(os.path.join(OUT, f)).convert('RGB')
    px = im.load(); W, H = im.size
    iout = imid = core = 0
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            if 120 <= r <= 140 and 130 <= g <= 150 and 190 <= b <= 210: iout += 1
            elif 40 <= r <= 80 and 90 <= g <= 110 and 180 <= b <= 200: imid += 1
            elif r < 60 and g < 100 and 100 < b < 160: core += 1
    print(f'{f:<15} | {iout:5d} {imid:5d} {core:5d}')