# -*- coding: utf-8 -*-
"""
tools.verify — 用 Playwright 渲染 renderer/index.html 做可视化验证

子命令：
  render          8 相位 2.4s 截图（旧版呼吸周期）           → verify_shots/
  iris            iris 峰值/谷值 + 眨眼/视线叠加            → compare_iris/
  iris-scale      iris 0.5s 缩放 8 帧                       → compare_iris_scale/
  ripple          0.2s 间隔 8 帧 验证波纹                    → compare_ripple/
  pulse05         0.1s 间隔 6 帧 验证 0.5s 脉冲（旧）         → compare_pulse05/
  corners-pop     0.25s 间隔 8 帧 验证尖刺 2.0s 伸缩（旧）    → compare_corners_pop/
  full-breathe    0.144s 间隔 6 帧 验证 0.86s 同步呼吸       → compare_full_breathe/
  states          5 状态对比：idle/视线左/视线右/眨眼/峰值   → compare/
  white-disc      白盘脉动验证（★三件套合一：--mode phased|minmax|live）
  pulse-real      实机关键帧 vs 视频脉动真伪验证             （无产物）

⚠️ 全部使用 sync_playwright；唯一异步的是 white-disc（沿用原 verify_white_disc*.py）。
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# 让 `python tools/verify.py` 与 `python -m tools.verify` 两种调用都能 import tools.*
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import imageio_ffmpeg
from PIL import Image

from tools.common import ROOT, RENDERER_URL, is_blue_ring, list_frames, reset_out
from tools.extract import ffmpeg_exe


# ============== 像素测通用 ==============

def _measure_layers(im, layers):
    """layers: dict name -> predicate(r,g,b). 返回 dict name -> count."""
    px = im.convert('RGB').load()
    W, H = im.size
    out = {k: 0 for k in layers}
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            for k, f in layers.items():
                if f(r, g, b):
                    out[k] += 1
                    break
    return out


LAYER_OUTER = lambda r, g, b: 120 <= r <= 140 and 130 <= g <= 150 and 190 <= b <= 210
LAYER_MID = lambda r, g, b: 40 <= r <= 80 and 90 <= g <= 110 and 180 <= b <= 200
LAYER_CORE = lambda r, g, b: r < 60 and g < 100 and 100 < b < 160
LAYER_RING = lambda r, g, b: b > 130 and b - r > 110 and b - g > 70 and r < 130
LAYER_WHITE = lambda r, g, b: r > 150 and g > 145 and b > 150


def _set_pause_bubble(page):
    page.evaluate("document.getElementById('bubble').classList.add('hidden')")


def _set_pause_shadow(page):
    page.evaluate("document.getElementById('fairy-svg').style.filter='none'")


def _reset_animations(page, ids=None):
    if ids is None:
        ids = ['brightRing', 'ringGlow', 'halo', 'irisPulse', 'corners']
    page.evaluate("""
        (ids) => {
          for (const id of ids) {
            const el = document.getElementById(id);
            if (el) el.style.animation = 'none';
          }
          document.getElementById('brightRing')?.getBoundingClientRect();
          for (const id of ids) {
            const el = document.getElementById(id);
            if (el) el.style.animation = '';
          }
        }
    """, ids)


# ============== 子命令函数 ==============

def render():
    """8 相位 2.4s 截图（旧版呼吸周期）。每张量 blue/white/scale vs 周期相位。"""
    from playwright.sync_api import sync_playwright
    out = ROOT / 'verify_shots'
    reset_out(out)
    PHASES = [0.0, 0.3, 0.6, 0.9, 1.2, 1.5, 1.8, 2.1]

    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome')
        page = b.new_page(viewport={'width': 360, 'height': 380})
        page.goto(RENDERER_URL)
        page.wait_for_timeout(1400)
        _set_pause_bubble(page); _set_pause_shadow(page)
        for ph in PHASES:
            _reset_animations(page)
            page.wait_for_timeout(int(ph * 1000) + 60)
            page.screenshot(path=str(out / f'ph{ph:.1f}.png'))
        b.close()

    # 像素量
    rows = []
    for ph in PHASES:
        im = Image.open(out / f'ph{ph:.1f}.png').convert('RGB')
        px = im.load(); W, H = im.size
        ECX, ECY = 180, H - 26 - 120
        bx, wx = [], 0
        for y in range(H):
            for x in range(W):
                r, g, b = px[x, y]
                if is_blue_ring((r, g, b)):
                    bx.append((x, y))
                elif LAYER_WHITE(r, g, b) and (x - ECX) ** 2 + (y - ECY) ** 2 < 70 * 70:
                    wx += 1
        if bx:
            xs = [q[0] for q in bx]; ys = [q[1] for q in bx]
            rows.append((ph, dict(blue=len(bx), white=wx,
                                  scale=(max(xs) - min(xs) + max(ys) - min(ys)) / 2)))
        else:
            rows.append((ph, None))

    print('相位  blue  white scale')
    for ph, m in rows:
        if m:
            print(f'{ph:.1f}  {m["blue"]:5d} {m["white"]:5d} {m["scale"]:5.1f}')

    ok = [m for _, m in rows if m]
    if ok:
        bl = [m['blue'] for m in ok]; wh = [m['white'] for m in ok]; sc = [m['scale'] for m in ok]
        n = len(ok)
        print(f'\nblue  幅度: {min(bl)} ~ {max(bl)} (±{(max(bl)-min(bl))/2/(sum(bl)/n)*100:.0f}%)')
        print(f'white 幅度: {min(wh)} ~ {max(wh)} (±{(max(wh)-min(wh))/2/(sum(wh)/n)*100:.0f}%)')
        print(f'scale 幅度: {min(sc):.1f} ~ {max(sc):.1f} (±{(max(sc)-min(sc))/2/(sum(sc)/n)*100:.1f}%)')


def iris():
    """iris 峰值/谷值 + 视线叠加 + 眨眼叠加"""
    from playwright.sync_api import sync_playwright
    out = ROOT / 'compare_iris'
    reset_out(out)
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome')
        page = b.new_page(viewport={'width': 360, 'height': 380})
        page.goto(RENDERER_URL)
        page.wait_for_timeout(1400)
        _set_pause_bubble(page); _set_pause_shadow(page)
        _reset_animations(page)
        page.wait_for_timeout(1200)
        page.screenshot(path=str(out / 'iris_peak.png'))
        page.wait_for_timeout(1200)
        page.screenshot(path=str(out / 'iris_trough.png'))
        page.mouse.move(40, 250); page.wait_for_timeout(400)
        page.evaluate("document.getElementById('iris').classList.add('blinking')")
        page.wait_for_timeout(60)
        page.screenshot(path=str(out / 'gaze_blink.png'))
        page.evaluate("document.getElementById('iris').classList.remove('blinking')")
        b.close()

    layers = {'irOut': LAYER_OUTER, 'irMid': LAYER_MID, 'core': LAYER_CORE}
    print(f'{"state":<15} | ' + ' '.join(f'{k:>5}' for k in layers))
    for f in sorted(out.glob('*.png')):
        m = _measure_layers(Image.open(f), layers)
        print(f'{f.name:<15} | ' + ' '.join(f'{m[k]:5d}' for k in layers))


def iris_scale():
    """iris 0.5s 缩放 8 帧（每 62ms）"""
    from playwright.sync_api import sync_playwright
    out = ROOT / 'compare_iris_scale'
    reset_out(out)
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome')
        page = b.new_page(viewport={'width': 360, 'height': 380})
        page.goto(RENDERER_URL)
        page.wait_for_timeout(1400)
        _set_pause_bubble(page)
        _reset_animations(page, ['brightRing', 'ringGlow', 'halo', 'irisPulse'])
        for i in range(8):
            page.wait_for_timeout(62)
            page.screenshot(path=str(out / f'p{i}.png'))
        page.wait_for_timeout(200)
        peak = page.evaluate("() => getComputedStyle(document.getElementById('irisPulse')).transform")
        page.wait_for_timeout(125)
        trough = page.evaluate("() => getComputedStyle(document.getElementById('irisPulse')).transform")
        print('irisPulse transform samples:', peak, '|', trough)
        b.close()

    crops = [Image.open(out / f'p{i}.png').convert('RGB') for i in range(8)]
    w, h = crops[0].size
    grid = Image.new('RGB', (w * 4, h * 2), (0, 0, 0))
    for i, c in enumerate(crops):
        grid.paste(c, ((i % 4) * w, (i // 4) * h))
    grid.save(out / '_grid.png')

    layers = {'蓝灰圈': LAYER_OUTER, '中蓝圈': LAYER_MID, '核心': LAYER_CORE}
    print(f'{"帧":>3} | ' + ' '.join(f'{k:>6}' for k in layers))
    for i in range(8):
        m = _measure_layers(crops[i], layers)
        print(f'{i:>3} | ' + ' '.join(f'{m[k]:6d}' for k in layers))


def ripple():
    """0.2s 间隔 8 帧（覆盖 1.5s）"""
    from playwright.sync_api import sync_playwright
    out = ROOT / 'compare_ripple'
    reset_out(out)
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome')
        page = b.new_page(viewport={'width': 360, 'height': 380})
        page.goto(RENDERER_URL)
        page.wait_for_timeout(1400)
        _set_pause_bubble(page); _set_pause_shadow(page)
        _reset_animations(page, ['brightRing', 'ringGlow', 'halo'])
        for i in range(8):
            page.wait_for_timeout(200)
            page.screenshot(path=str(out / f'ph{i*0.2:.1f}.png'))
        b.close()

    layers = {'r-core': LAYER_CORE, 'r-mid': LAYER_MID, 'r-outer': LAYER_OUTER, 'ring': LAYER_RING}
    print(f'{"t":>4} | ' + ' '.join(f'{k}_d:{k+"_n":>5}' for k in layers))
    for i in range(8):
        t = i * 0.2
        im = Image.open(out / f'ph{t:.1f}.png').convert('RGB')
        px = im.load(); W, H = im.size
        out_row = {}
        for k, pred in layers.items():
            xs, ys = [], []
            for y in range(H):
                for x in range(W):
                    r, g, b = px[x, y]
                    if pred(r, g, b):
                        xs.append(x); ys.append(y)
            out_row[k] = ((max(xs) - min(xs) + max(ys) - min(ys)) / 2 if xs else 0,
                          len(xs))
        print(f'{t:.1f} | ' + ' '.join(f'{out_row[k][0]:5.1f} {out_row[k][1]:5d}'
                                       for k in layers))


def pulse05():
    """0.1s 间隔 6 帧验证 0.5s 脉冲"""
    from playwright.sync_api import sync_playwright
    out = ROOT / 'compare_pulse05'
    reset_out(out)
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome')
        page = b.new_page(viewport={'width': 360, 'height': 380})
        page.goto(RENDERER_URL)
        page.wait_for_timeout(1400)
        _set_pause_bubble(page); _set_pause_shadow(page)
        _reset_animations(page, ['brightRing', 'ringGlow', 'halo'])
        for i in range(6):
            page.wait_for_timeout(100)
            page.screenshot(path=str(out / f'p{i*0.1:.1f}.png'))
        cs = page.evaluate("""() => ({
          o: getComputedStyle(document.querySelector('.r-outer'))?.strokeWidth,
          m: getComputedStyle(document.querySelector('.r-mid'))?.strokeWidth,
          r: getComputedStyle(document.getElementById('brightRing')).strokeWidth,
          g: getComputedStyle(document.getElementById('ringGlow')).opacity
        })""")
        print('peak computed style:', cs)
        b.close()

    layers = {'core': LAYER_CORE, 'mid': LAYER_MID, 'outer': LAYER_OUTER, 'ring': LAYER_RING}
    print(f'{"t":>4} | ' + ' '.join(f'{k:>5}' for k in layers))
    for i in range(6):
        t = i * 0.1
        m = _measure_layers(Image.open(out / f'p{t:.1f}.png').convert('RGB'), layers)
        print(f'{t:.1f} | ' + ' '.join(f'{m[k]:5d}' for k in layers))


def corners_pop():
    """0.25s 间隔 8 帧验证尖刺 2.0s 伸缩（旧版，已被 rotate 取代）"""
    from playwright.sync_api import sync_playwright
    out = ROOT / 'compare_corners_pop'
    reset_out(out)
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome')
        page = b.new_page(viewport={'width': 360, 'height': 380})
        page.goto(RENDERER_URL)
        page.wait_for_timeout(1400)
        _set_pause_bubble(page)
        for i in range(8):
            page.wait_for_timeout(250)
            page.screenshot(path=str(out / f'p{i}.png'))
        b.close()


def full_breathe():
    """0.144s 间隔 6 帧验证 0.86s 同步呼吸"""
    from playwright.sync_api import sync_playwright
    out = ROOT / 'compare_full_breathe'
    reset_out(out)
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome')
        page = b.new_page(viewport={'width': 360, 'height': 380})
        page.goto(RENDERER_URL)
        page.wait_for_timeout(1400)
        _set_pause_bubble(page)
        _reset_animations(page)
        for i in range(6):
            page.wait_for_timeout(144)
            page.screenshot(path=str(out / f'p{i}.png'))
        cs = page.evaluate("""() => ({
          iris: getComputedStyle(document.getElementById('irisPulse')).transform,
          corn: getComputedStyle(document.getElementById('corners')).transform,
          br:   getComputedStyle(document.getElementById('brightRing')).strokeWidth,
          glow: getComputedStyle(document.getElementById('ringGlow')).opacity,
          halo: getComputedStyle(document.getElementById('halo')).transform,
        })""")
        print('computed:', cs)
        b.close()

    crops = [Image.open(out / f'p{i}.png').convert('RGB') for i in range(6)]
    w, h = crops[0].size
    grid = Image.new('RGB', (w * 6, h), (0, 0, 0))
    for i, c in enumerate(crops):
        grid.paste(c, (i * w, 0))
    grid.save(out / '_strip.png')
    print('saved', grid.size)


def states():
    """5 状态对比：idle / 视线左 / 视线右 / 眨眼 / 呼吸峰值"""
    from playwright.sync_api import sync_playwright
    out = ROOT / 'compare'
    reset_out(out)
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome')
        page = b.new_page(viewport={'width': 360, 'height': 380})
        page.goto(RENDERER_URL)
        page.wait_for_timeout(1400)
        _set_pause_bubble(page)

        page.mouse.move(350, 350); page.wait_for_timeout(300)
        page.screenshot(path=str(out / 'A_idle.png'))
        page.mouse.move(40, 250); page.wait_for_timeout(400)
        page.screenshot(path=str(out / 'B_gaze_left.png'))
        page.mouse.move(320, 30); page.wait_for_timeout(400)
        page.screenshot(path=str(out / 'C_gaze_right.png'))
        page.evaluate("document.getElementById('iris').classList.add('blinking')")
        page.wait_for_timeout(60)
        page.screenshot(path=str(out / 'D_blink.png'))
        page.evaluate("document.getElementById('iris').classList.remove('blinking')")
        page.wait_for_timeout(600)
        page.screenshot(path=str(out / 'E_breathe_peak.png'))
        b.close()
    print('已生成：', sorted([p.name for p in out.glob('*.png')]))


async def _white_disc_phased():
    """原 verify_white_disc.py：8 相位（animation-delay 渐进）"""
    from playwright.async_api import async_playwright
    out = ROOT / 'verify_white_disc'
    reset_out(out)
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
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome')
        ctx = await browser.new_context(viewport={'width': 320, 'height': 320})
        page = await ctx.new_page()
        await page.goto(RENDERER_URL)
        await page.add_style_tag(content=INJECT_CSS)
        await page.wait_for_timeout(120)
        await page.evaluate("""
            document.body.style.margin = '0';
            document.body.style.background = '#0a0a14';
            const stage = document.getElementById('stage');
            stage.style.position = 'absolute';
            stage.style.left = '0'; stage.style.top = '0';
            const boot = document.getElementById('boot');
            boot.style.position = 'absolute';
            boot.style.left = '40px'; boot.style.top = '40px';
        """)
        await page.wait_for_timeout(60)
        N = 8
        dt = 0.86 * 1000 / N
        paths = []
        for k in range(N):
            ms = int(k * dt)
            await page.add_style_tag(content=f'#whiteDisc {{ animation-delay: -{ms}ms !important; }}')
            await page.wait_for_timeout(120)
            rect = await page.evaluate("""
                () => {
                  const r = document.getElementById('fairy-svg').getBoundingClientRect();
                  return { l: r.left, t: r.top, w: r.width, h: r.height };
                }
            """)
            shot = await page.screenshot(clip={'x': rect['l'], 'y': rect['t'],
                                              'width': rect['w'], 'height': rect['h']})
            fp = out / f'shot_{k:02d}_t{ms}ms.png'
            fp.write_bytes(shot)
            paths.append(fp)
            print(f'frame {k}  t={ms}ms  -> {fp}')
        imgs = [Image.open(p) for p in paths]
        w0, h0 = imgs[0].size
        strip = Image.new('RGBA', (w0 * N + 10 * (N - 1), h0), (20, 20, 40, 255))
        for i, im in enumerate(imgs):
            strip.paste(im, (i * (w0 + 10), 0))
        strip.save(out / '_strip.png')
        print('STRIP:', out / '_strip.png')
        await browser.close()


async def _white_disc_minmax():
    """原 verify_white_disc_minmax.py：CSS 强制 min vs max 对照"""
    from playwright.async_api import async_playwright
    out = ROOT / 'verify_white_disc2'
    reset_out(out)
    INJECT = """
#irisPulse, #brightRing, #corners, #ringGlow, #halo {
  animation: none !important;
  transform: none !important;
}
#whiteDisc { animation: none !important; transform: scale(SCALE) !important; }
"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome')
        ctx = await browser.new_context(viewport={'width': 320, 'height': 320})
        for tag, scale in [('min', '1'), ('max', '1.04')]:
            page = await ctx.new_page()
            await page.goto(RENDERER_URL)
            await page.add_style_tag(content=INJECT.replace('SCALE', scale))
            await page.wait_for_timeout(200)
            await page.add_style_tag(content="""
                body { background: #0a0a14; margin: 0; }
                #stage { position: absolute; left: 0; top: 0; }
            """)
            rect = await page.evaluate("""
                () => {
                  const r = document.getElementById('fairy-svg').getBoundingClientRect();
                  return { l: r.left, t: r.top, w: r.width, h: r.height };
                }
            """)
            shot = await page.screenshot(clip={'x': rect['l'], 'y': rect['t'],
                                              'width': rect['w'], 'height': rect['h']})
            (out / f'disc_{tag}.png').write_bytes(shot)
            print(f'{tag} -> {out / f"disc_{tag}.png"}')
            await page.close()
        await browser.close()


async def _white_disc_live():
    """原 verify_white_disc_live.py：全程动画 5 帧"""
    from playwright.async_api import async_playwright
    out = ROOT / 'verify_white_disc_live'
    reset_out(out)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome')
        ctx = await browser.new_context(viewport={'width': 320, 'height': 320})
        page = await ctx.new_page()
        await page.goto(RENDERER_URL)
        await page.wait_for_timeout(1200)
        rect = await page.evaluate("""
            () => {
              const r = document.getElementById('fairy-svg').getBoundingClientRect();
              return { l: r.left, t: r.top, w: r.width, h: r.height };
            }
        """)
        N = 5
        delays = [0, 430, 860, 1290, 1720, 2150, 3010, 3870, 4300][:N]
        prev = 0
        for i, d in enumerate(delays):
            wait = d - prev
            if wait > 0:
                await page.wait_for_timeout(wait)
            prev = d
            shot = await page.screenshot(clip={'x': rect['l'], 'y': rect['t'],
                                              'width': rect['w'], 'height': rect['h']})
            (out / f'live_{i}_t{d}ms.png').write_bytes(shot)
            print(f'live {i} t={d}ms -> {out / f"live_{i}_t{d}ms.png"}')
        await browser.close()

    # 拼图 + diff 报告
    from PIL import ImageChops
    imgs = [Image.open(out / f'live_{i}_t{d}ms.png').convert('RGB') for i, d in enumerate(delays)]
    for i in range(N - 1):
        a, b = np.asarray(imgs[i]), np.asarray(imgs[i + 1])
        d = np.abs(a.astype(int) - b.astype(int)).sum(axis=-1)
        print(f'frame {i:>1}-{i+1:>1}: max_diff={d.max():>5.0f} mean_diff={d.mean():>6.2f} '
              f'pct_changed(>10)={float((d > 10).mean()*100):5.2f}%')
    # strip
    strip = Image.new('RGB', (imgs[0].size[0] * N + 10 * (N - 1),
                              imgs[0].size[1] + 30), (15, 15, 30))
    from PIL import ImageDraw
    d = ImageDraw.Draw(strip)
    for i, im in enumerate(imgs):
        strip.paste(im, (i * (im.size[0] + 10), 30))
        d.text((i * (im.size[0] + 10) + 10, 5), f'frame {i}', fill=(220, 220, 255))
    strip.save(out / '_live_strip.png')
    print('STRIP:', out / '_live_strip.png')


def white_disc(mode):
    """白盘脉动验证 —— 三件套合一入口"""
    if mode == 'phased':
        asyncio_run(_white_disc_phased())
    elif mode == 'minmax':
        asyncio_run(_white_disc_minmax())
    elif mode == 'live':
        asyncio_run(_white_disc_live())
    else:
        raise SystemExit(f'Unknown --mode {mode!r}')


def asyncio_run(coro):
    """兼容 Python 3.13+：asyncio.run(coro) 已经存在；此处仅作显式入口"""
    import asyncio
    asyncio.run(coro)


def pulse_real():
    """实机关键帧 vs 视频脉动真伪（读 egg.mp4 关键帧时间 + frames_full 逐帧 blue/white）"""
    ff = ffmpeg_exe()
    src = ROOT / 'ref_video' / 'egg.mp4'
    r = subprocess.run([ff, '-i', str(src), '-vf', 'showinfo', '-f', 'null', '-'],
                       capture_output=True, text=True)
    kfs = []
    for line in r.stderr.splitlines():
        if 'pts_time:' in line and ('type:I' in line or 'I frame' in line):
            t = float(line.split('pts_time:')[1].split()[0])
            kfs.append(round(t, 2))
    kfs = sorted(set(kfs))
    print('关键帧时间(前30):', kfs[:30])

    D = ROOT / 'frames_full'
    files = list_frames(D)
    FPS = 12
    CX, CY, R = 195, 676, 48

    series = []
    for f in files:
        img = Image.open(f)
        crop = img.crop((CX - R, CY - R, CX + R, CY + R)).resize((180, 180), Image.BILINEAR)
        px = crop.load()
        bx = []; wx = 0; brt = 0
        for y in range(180):
            for x in range(180):
                rr, g, b = px[x, y]
                if is_blue_ring((rr, g, b)):
                    bx.append((x, y)); brt += rr + g + b
                elif LAYER_WHITE(rr, g, b) and (x - 90) ** 2 + (y - 90) ** 2 < 52 * 52:
                    wx += 1
        if not bx:
            series.append(None); continue
        xs = [q[0] for q in bx]; ys = [q[1] for q in bx]
        series.append(dict(blue=len(bx), white=wx,
                           scale=(max(xs) - min(xs) + max(ys) - min(ys)) / 2,
                           brt=brt / len(bx) / 3))

    print('\nt     blue  white scale  brt')
    for i in range(8 * FPS, 24 * FPS):
        m = series[i]
        if m:
            print(f'{i / FPS:5.2f} {m["blue"]:5d} {m["white"]:5d} {m["scale"]:5.1f} {m["brt"]:5.1f}')

    vals = [(i, m['blue']) for i, m in enumerate(series) if m]
    if vals:
        mu = sum(v for _, v in vals) / len(vals)
        print('blue mean=%.0f' % mu)
        best = []
        d_map = dict(vals)
        for lag in range(4, 120):
            num = den = 0
            for i, v in vals:
                if i + lag in d_map:
                    num += (v - mu) * (d_map[i + lag] - mu); den += 1
            ac = num / den / mu if den > 100 else 0
            best.append((ac, lag))
        best.sort(reverse=True)
        print('blue 自相关 top5 lag:', [(l, round(a, 3)) for a, l in best[:5]])
    if len(kfs) > 3:
        gaps = [round(kfs[i + 1] - kfs[i], 2) for i in range(len(kfs) - 1)]
        from collections import Counter
        print('关键帧间隔分布:', Counter(gaps).most_common(5))


# ============== argparse ==============

def main():
    p = argparse.ArgumentParser(description='fairy-pet 渲染验证工具')
    p.add_argument('cmd', choices=['render', 'iris', 'iris-scale', 'ripple',
                                   'pulse05', 'corners-pop', 'full-breathe',
                                   'states', 'white-disc', 'pulse-real'])
    p.add_argument('--mode', choices=['phased', 'minmax', 'live'],
                   default='phased', help='仅 white-disc 用')
    args = p.parse_args()

    if args.cmd == 'white-disc':
        white_disc(args.mode)
    elif args.cmd == 'render':
        render()
    elif args.cmd == 'iris':
        iris()
    elif args.cmd == 'iris-scale':
        iris_scale()
    elif args.cmd == 'ripple':
        ripple()
    elif args.cmd == 'pulse05':
        pulse05()
    elif args.cmd == 'corners-pop':
        corners_pop()
    elif args.cmd == 'full-breathe':
        full_breathe()
    elif args.cmd == 'states':
        states()
    elif args.cmd == 'pulse-real':
        pulse_real()


if __name__ == '__main__':
    main()