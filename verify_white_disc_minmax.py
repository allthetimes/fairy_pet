"""
Two-state comparison: whiteDisc at scale(1) vs scale(1.04).
Freeze all other animations. Detect disc outer edge in both.
"""
import asyncio, os
from playwright.async_api import async_playwright
import numpy as np
from PIL import Image

ROOT = r'D:\work\fairy-pet'
OUT  = os.path.join(ROOT, 'verify_white_disc2')
os.makedirs(OUT, exist_ok=True)

INDEX = 'file:///' + os.path.join(ROOT, 'renderer', 'index.html').replace('\\','/')

# Two CSS injections — freeze everything, force #whiteDisc to a fixed scale.
INJECT_MIN = """
#irisPulse, #brightRing, #corners, #ringGlow, #halo {
  animation: none !important;
  transform: none !important;
}
#whiteDisc { animation: none !important; transform: scale(1) !important; }
"""
INJECT_MAX = """
#irisPulse, #brightRing, #corners, #ringGlow, #halo {
  animation: none !important;
  transform: none !important;
}
#whiteDisc { animation: none !important; transform: scale(1.04) !important; }
"""

async def cap(page, name):
    await page.add_style_tag(content="""
        body { background: #0a0a14; margin: 0; }
        #stage { position: absolute; left: 0; top: 0; }
    """)
    rect = await page.evaluate('() => { const r = document.getElementById("fairy-svg").getBoundingClientRect(); return {l:r.left, t:r.top, w:r.width, h:r.height}; }')
    shot = await page.screenshot(clip={'x': rect['l'], 'y': rect['t'], 'width': rect['w'], 'height': rect['h']})
    fp = os.path.join(OUT, f'{name}.png')
    with open(fp, 'wb') as f: f.write(shot)
    return fp, rect

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome')
        ctx = await browser.new_context(viewport={'width': 320, 'height': 320})
        for tag, inj in [('min', INJECT_MIN), ('max', INJECT_MAX)]:
            page = await ctx.new_page()
            await page.goto(INDEX)
            await page.add_style_tag(content=inj)
            await page.wait_for_timeout(200)
            fp, rect = await cap(page, f'disc_{tag}')
            print(f'{tag} -> {fp}, rect={rect}')
            await page.close()
        await browser.close()

asyncio.run(run())

# Measure disc edge in both
def measure(path):
    arr = np.asarray(Image.open(path).convert('RGB'))
    h, w = arr.shape[:2]
    # bright-blue ring outer radius (use 90 deg ray)
    mask_bb = (arr[:,:,2] > 200) & (arr[:,:,0] < 130)
    yb, xb = np.where(mask_bb)
    bcx = float(np.median(xb)); bcy = float(np.median(yb))
    import math
    R_max = min(bcx, w-bcx, bcy, h-bcy) - 2
    # 4 angles
    res = {}
    for a in [0, 90, 180, 270]:
        dx, dy = math.cos(math.radians(a)), math.sin(math.radians(a))
        last_w = 0; in_w = False; rs = 0
        for s in range(5, int(R_max)+1):
            x = int(round(bcx + dx*s)); y = int(round(bcy + dy*s))
            if not (0<=x<w and 0<=y<h): break
            w_white = (arr[y,x,0] > 200 and arr[y,x,1] > 200 and arr[y,x,2] > 200)
            if w_white:
                if not in_w: in_w = True; rs = s
                last_w = s
            else:
                if in_w and (s-rs) >= 3:
                    break
                in_w = False
        res[a] = last_w
    return arr, (bcx, bcy), res

for tag in ['min', 'max']:
    p = os.path.join(OUT, f'disc_{tag}.png')
    arr, ctr, res = measure(p)
    vals = [v for v in res.values() if v > 0]
    print(f'{tag}: center={ctr}  per-angle Rw={res}  median={np.median(vals):.2f}')
