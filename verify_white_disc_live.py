"""Live capture: no freezes. Render the page with all animations running, capture
5 snapshots over 4.3s (5 full breath cycles) and confirm the eye is alive.
"""
import asyncio, os
from playwright.async_api import async_playwright
from PIL import Image, ImageChops
import numpy as np

ROOT = r'D:\work\fairy-pet'
OUT  = os.path.join(ROOT, 'verify_white_disc_live')
os.makedirs(OUT, exist_ok=True)

INDEX = 'file:///' + os.path.join(ROOT, 'renderer', 'index.html').replace('\\','/')

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome')
        ctx = await browser.new_context(viewport={'width': 320, 'height': 320})
        page = await ctx.new_page()
        await page.goto(INDEX)
        # real layout — let boot settle
        await page.wait_for_timeout(1200)
        rect = await page.evaluate('() => { const r = document.getElementById("fairy-svg").getBoundingClientRect(); return {l:r.left, t:r.top, w:r.width, h:r.height}; }')
        paths = []
        N = 5
        # 4.3s = 5 cycles of 0.86s
        delays = [0, 430, 860, 1290, 1720, 2150, 3010, 3870, 4300]
        delays = delays[:N]
        prev = 0
        for i, d in enumerate(delays):
            wait = d - prev
            if wait > 0:
                await page.wait_for_timeout(wait)
            prev = d
            shot = await page.screenshot(clip={'x': rect['l'], 'y': rect['t'], 'width': rect['w'], 'height': rect['h']})
            fp = os.path.join(OUT, f'live_{i}_t{d}ms.png')
            with open(fp, 'wb') as f: f.write(shot)
            paths.append(fp)
            print(f'live {i} t={d}ms -> {fp}')
        await browser.close()

asyncio.run(run())

# Diff consecutive pairs to confirm activity (esp. expect disc region to change)
print('\n--- pixel-level comparison between consecutive live frames ---')
imgs = [Image.open(p).convert('RGB') for p in [os.path.join(OUT, f'live_{i}_t{[0,430,860,1290,1720][i]}ms.png') for i in range(5)]]
import math, numpy as np
def diff_stats(a, b):
    arr_a = np.asarray(a); arr_b = np.asarray(b)
    d = np.abs(arr_a.astype(int) - arr_b.astype(int)).sum(axis=-1)
    return float(d.max()), float(d.mean()), float((d>10).mean()*100)

for i in range(len(imgs)-1):
    mx, mn, pct = diff_stats(imgs[i], imgs[i+1])
    print(f'  frame {i:>1}-{i+1:>1}:  max_diff={mx:>5.0f}  mean_diff={mn:>6.2f}  pct_changed(>10)={pct:5.2f}%')

# Also diff first vs last — should look ~identical if cycle is 0.86s*5=4.3s
mx, mn, pct = diff_stats(imgs[0], imgs[-1])
print(f'\nfirst vs last (assuming exact 5-cycle match):  max={mx:.0f}  mean={mn:.2f}  pct={pct:.2f}%')

# composite strip with labels
from PIL import ImageDraw, ImageFont
strip = Image.new('RGB', (imgs[0].size[0]*len(imgs) + 10*(len(imgs)-1), imgs[0].size[1]+30), (15,15,30))
d = ImageDraw.Draw(strip)
for i, im in enumerate(imgs):
    strip.paste(im, (i*(im.size[0]+10), 30))
    d.text((i*(im.size[0]+10)+10, 5), f'frame {i}', fill=(220,220,255))
sp = os.path.join(OUT, '_live_strip.png')
strip.save(sp)
print('STRIP:', sp)
