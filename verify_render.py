# -*- coding: utf-8 -*-
# 用 Playwright 打开 renderer/index.html，在呼吸周期不同相位截图，
# 然后用与实机相同的颜色阈值计算指标，验证：周期 2.4s / 外径±2.6% / 蓝环±15% / 白盘±9%
import os
from playwright.sync_api import sync_playwright

BASE = r'D:\work\fairy-pet'
OUT = os.path.join(BASE, 'verify_shots')
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.png'):
        os.remove(os.path.join(OUT, f))

PHASES = [0.0, 0.3, 0.6, 0.9, 1.2, 1.5, 1.8, 2.1]  # 呼吸周期 2.4s 的 8 个相位

with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome')
    page = b.new_page(viewport={'width': 360, 'height': 380})
    page.goto('file:///' + (BASE + r'\renderer\index.html').replace('\\', '/'))
    page.wait_for_timeout(1400)  # 等 boot 动画结束
    # 关掉气泡，避免干扰；关掉 drop-shadow，让蓝色检测只反映环几何
    page.evaluate("document.getElementById('bubble').classList.add('hidden'); document.getElementById('fairy-svg').style.filter='none'")
    for ph in PHASES:
        # 重启呼吸动画到相位 0
        page.evaluate("""
          const br  = document.getElementById('brightRing');
          const gl  = document.getElementById('ringGlow');
          const hal = document.getElementById('halo');
          for (const el of [br, gl, hal]) { el.style.animation = 'none'; }
          br.getBoundingClientRect();  // SVG 元素没有 offsetWidth，用这个强制回流
          for (const el of [br, gl, hal]) { el.style.animation = ''; }
        """)
        page.wait_for_timeout(int(ph * 1000) + 60)
        page.screenshot(path=os.path.join(OUT, f'ph{ph:.1f}.png'))
    b.close()

# ---- 指标计算（与实机同一套阈值；白色只统计眼部区域内） ----
from PIL import Image
rows = []
for ph in PHASES:
    im = Image.open(os.path.join(OUT, f'ph{ph:.1f}.png')).convert('RGB')
    px = im.load()
    W, H = im.size
    # 眼心：#boot 居中，left 50%（180px），bottom 26 + 高 240 的中心
    ECX, ECY = 180, 380 - 26 - 120
    bx = []; wx = 0
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            if b > 140 and b - r > 100 and b - g > 60 and g < 135:
                bx.append((x, y))
            elif r > 150 and g > 145 and b > 150:
                d2 = (x - ECX) ** 2 + (y - ECY) ** 2
                if d2 < 70 * 70:
                    wx += 1
    if not bx:
        rows.append((ph, None)); continue
    xs = [q[0] for q in bx]; ys = [q[1] for q in bx]
    scale = (max(xs) - min(xs) + max(ys) - min(ys)) / 2
    rows.append((ph, dict(blue=len(bx), white=wx, scale=scale)))

print('相位  blue  white scale')
for ph, m in rows:
    if m:
        print('%.1f  %5d %5d %5.1f' % (ph, m['blue'], m['white'], m['scale']))

ok = [m for _, m in rows if m]
bl = [m['blue'] for m in ok]
wh = [m['white'] for m in ok]
sc = [m['scale'] for m in ok]
n = len(ok)
print()
print('blue  幅度: %d ~ %d  (±%.0f%%, 实机 ±17%%)' % (min(bl), max(bl), (max(bl)-min(bl))/2/(sum(bl)/n)*100))
print('white 幅度: %d ~ %d  (±%.0f%%, 实机  ±2%%)' % (min(wh), max(wh), (max(wh)-min(wh))/2/(sum(wh)/n)*100))
print('scale 幅度: %.1f ~ %.1f (±%.1f%%, 实机 ±2.6%%)' % (min(sc), max(sc), (max(sc)-min(sc))/2/(sum(sc)/n)*100))
# 周期检查：blue 峰值相位
bmax = max(range(n), key=lambda i: bl[i])
bmin = min(range(n), key=lambda i: bl[i])
print('blue 峰值相位 %.1fs, 谷值相位 %.1fs (应相差 ~1.2s)' % (rows[bmax][0], rows[bmin][0]))
