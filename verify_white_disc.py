"""
Verify the new whiteDisc pulse by rendering renderer/index.html in Playwright (Chrome)
and screenshotting at multiple time offsets across the 0.86s breathing cycle.
Freeze the OTHER animations (#irisPulse, #brightRing, #corners, #halo, #ringGlow)
to isolate the #whiteDisc pulse.
"""
import asyncio, os, sys
from playwright.async_api import async_playwright

ROOT = r'D:\work\fairy-pet'
OUT  = os.path.join(ROOT, 'verify_white_disc')
os.makedirs(OUT, exist_ok=True)

INDEX = 'file:///' + os.path.join(ROOT, 'renderer', 'index.html').replace('\\','/')

# Inject CSS to isolate #whiteDisc animation (freeze everything else)
INJECT_CSS = """
#irisPulse, #brightRing, #corners, #ringGlow, #halo {
  animation: none !important;
}
#whiteDisc {
  animation: whiteDiscPulseTest 0.86s ease-in-out infinite !important;
}
@keyframes whiteDiscPulseTest {
  0%,100% { transform: scale(1);    }
  50%     { transform: scale(1.04); }
}
"""

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome')
        ctx = await browser.new_context(viewport={'width': 320, 'height': 320})
        page = await ctx.new_page()
        # add init script BEFORE the page loads
        await page.add_init_script(INJECT_CSS, content=None) if False else None
        # navigate
        await page.goto(INDEX)
        # inject after load
        await page.add_style_tag(content=INJECT_CSS)
        await page.wait_for_timeout(120)  # let layout settle
        # Make sure stage is at top-left so we can read pixels
        await page.evaluate('''
            document.body.style.margin = '0';
            document.body.style.background = '#0a0a14';
            const stage = document.getElementById('stage');
            stage.style.position = 'absolute';
            stage.style.left = '0';
            stage.style.top  = '0';
            const boot = document.getElementById('boot');
            boot.style.position = 'absolute';
            boot.style.left = '40px';
            boot.style.top  = '40px';
        ''')
        await page.wait_for_timeout(60)
        # capture 8 frames over 0.86s
        N = 8
        dt = 0.86 * 1000 / N  # ms between captures
        paths = []
        for k in range(N):
            ms = int(k*dt)
            targ = '#whiteDisc_pixel_%02d' % k
            await page.add_style_tag(content=f'#whiteDisc {{ animation-delay: -{ms}ms !important; }}')
            await page.wait_for_timeout(120)
            # measure white disc OUTER RADIUS in pixel space, by sampling radial color
            data = await page.evaluate('''
                () => {
                  const svg = document.getElementById('fairy-svg');
                  const r = svg.getBoundingClientRect();
                  return {rect: {l:r.left, t:r.top, w:r.width, h:r.height}};
                }
            ''')
            # screenshot the SVG region
            shot = await page.screenshot(clip={
                'x': data['rect']['l'], 'y': data['rect']['t'],
                'width': data['rect']['w'], 'height': data['rect']['h']
            })
            fp = os.path.join(OUT, f'shot_{k:02d}_t{ms}ms.png')
            with open(fp, 'wb') as f:
                f.write(shot)
            paths.append(fp)
            print(f'frame {k}  t={ms}ms  -> {fp}')
        # composite a strip
        from PIL import Image
        imgs = [Image.open(p) for p in paths]
        w0, h0 = imgs[0].size
        strip = Image.new('RGBA', (w0*N + 10*(N-1), h0), (20,20,40,255))
        for i,im in enumerate(imgs):
            strip.paste(im, (i*(w0+10), 0))
        strip_path = os.path.join(OUT, '_strip.png')
        strip.save(strip_path)
        print('STRIP:', strip_path)
        await browser.close()

asyncio.run(run())
