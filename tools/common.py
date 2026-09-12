# -*- coding: utf-8 -*-
"""
tools.common — fairy-pet 逐帧分析共享基础

消除了 30 个 .py 脚本各自重复的 8 处样板：
  - BASE = r'D:\\work\\fairy-pet'    路径硬编码
  - is_white / is_blue_ring / is_dark_navy    颜色判定
  - ray_walk(... predicate)                   极坐标射线
  - detrend_moving_mean + fft_top_peaks       周期分析
  - Playwright sync / async 启动 + 隐藏 bubble + 等待
  - os.listdir + os.remove(.png)              输出目录清理

用法：
  from tools.common import (
      ROOT, RENDERER_URL,
      is_white, is_blue_ring, is_dark_navy, is_deep_blue, is_glint,
      list_frames, load_frame, load_indexed,
      ray_walk, cart_at,
      detrend_moving_mean, fft_top_peaks,
      reset_out, make_sync_page, make_async_page, svg_clip_rect,
  )
"""
import math
import os
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]   # D:\work\fairy-pet\
RENDERER = ROOT / 'renderer' / 'index.html'
RENDERER_URL = RENDERER.as_uri()             # file:///D:/work/fairy-pet/renderer/index.html

REF_VIDEO = ROOT / 'ref_video'


# ============== 颜色判定 ==============
# 阈值采用「最宽松版本」，覆盖 8 个原脚本的颜色取值（disc_pulse / detect_eye /
# fixed_scan / locate_eye / scan_all_objects / corner_angles2 / iris_metrics /
# iris_period / hifps_crop / _measure_disc_in_shots）。
# 调阈值就改这里一处。

def is_white(rgb, thr=200):
    r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    return r > thr and g > thr and b > thr


def is_blue_ring(rgb):
    """亮蓝外环 #2D3FE8 / #5078E5 — 与外发光 #8AA6FF 也重叠，故阈值偏严"""
    r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    return b > 130 and b - r > 110 and b - g > 70 and r < 130


def is_dark_navy(rgb):
    """暗蓝环带 #232A8F + 暗蓝尖刺同色"""
    r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    return r < 95 and g < 105 and 120 < b < 220


def is_deep_blue(rgb):
    """深蓝核心 #2E4E8E 等 — 偏深但仍有蓝色"""
    r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    return r < 60 and g < 100 and 100 < b < 160


def is_glint(rgb):
    """白色高光球 #FFFFFF"""
    return is_white(rgb, thr=200)


# ============== 帧 IO ==============

def list_frames(d, ext='.png'):
    p = Path(d) if not isinstance(d, Path) else d
    return sorted([f for f in p.iterdir() if f.suffix.lower() == ext.lower()])


def load_frame(path):
    return np.asarray(Image.open(path).convert('RGB'))


def load_indexed(d, every=1, ext='.png'):
    """从 f0001.png..f0900.png 这种 1-indexed 序列中每 every 帧取一张"""
    fs = list_frames(d, ext)
    return [load_frame(fs[i]) for i in range(0, len(fs), every)]


def reset_out(d, ext='.png'):
    """mkdir + 清空旧帧（保险：只删 ext 后缀）"""
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    for f in p.iterdir():
        if f.suffix.lower() == ext.lower():
            f.unlink()


# ============== 几何：极坐标射线 ==============

def ray_walk(arr, cx, cy, ang_deg, r_min, r_max, predicate, run_len=3):
    """沿 ang_deg 方向从 r_min 走到 r_max，命中「连续 run_len 像素都过 predicate」
    的末端，返回 r 值；未命中返回 None。

    用法：
      ray_walk(arr, 998, 340, 0, 20, 120, lambda r,g,b: r>200 and g>200 and b>200)
      -> 返回白盘外缘 r（或 None）
    """
    h, w = arr.shape[:2]
    dx, dy = math.cos(math.radians(ang_deg)), math.sin(math.radians(ang_deg))
    in_run = False
    run_start = 0
    last = None
    for s in range(int(r_min), int(r_max) + 1):
        x = int(round(cx + dx * s))
        y = int(round(cy + dy * s))
        if not (0 <= x < w and 0 <= y < h):
            break
        if predicate(arr[y, x]):
            if not in_run:
                in_run = True
                run_start = s
            last = s
        else:
            if in_run and (s - run_start) >= run_len:
                return float(last)
            in_run = False
    return float(last) if last is not None else None


def cart_at(cx, cy, ang_deg, r):
    dx, dy = math.cos(math.radians(ang_deg)), math.sin(math.radians(ang_deg))
    return cx + dx * r, cy + dy * r


# ============== 信号：去趋势 + FFT ==============

def detrend_moving_mean(x, k=20):
    """滑动均值去趋势（消除相机推拉这种低频干扰）"""
    x = np.asarray(x, dtype=float)
    if len(x) <= 2 * k:
        return x - np.mean(x)
    kernel = np.ones(k) / k
    rm = np.convolve(x, kernel, mode='same')
    return x - rm


def fft_mag(x, dt):
    """加窗后 rfft，返回 (freqs, power, windowed_std)"""
    x = np.asarray(x, dtype=float)
    if len(x) < 4 or np.std(x) < 1e-9:
        return None, None, 0.0
    xd = detrend_moving_mean(x) if False else (x - np.mean(x))
    win = np.hanning(len(xd))
    f = np.fft.rfft(xd * win)
    p = np.abs(f) ** 2
    freqs = np.fft.rfftfreq(len(xd), d=dt)
    return freqs, p, float(np.std(xd))


def fft_top_peaks(x, dt, top=3, fmin=0.05, fmax=None):
    """返回 [(freq_Hz, period_s, power), ...]，按 power 降序"""
    freqs, p, _ = fft_mag(x, dt)
    if freqs is None:
        return []
    p = np.asarray(p)
    p[0] = 0   # 扔掉 DC
    if fmax is None:
        fmax = freqs[-1]
    mask = (freqs >= fmin) & (freqs <= fmax)
    if not mask.any():
        return []
    idxs = np.where(mask)[0]
    sub_p = p[idxs]
    sub_f = freqs[idxs]
    top_idx = np.argsort(sub_p)[::-1][:top]
    out = []
    for i in top_idx:
        fhz = float(sub_f[i])
        period = 1.0 / fhz if fhz > 0 else float('inf')
        out.append((fhz, period, int(sub_p[i])))
    return out


def autocorr_top(s, fps, top=3, fmin=0.05, fmax=None):
    """自相关找主周期（无趋势信号 fallback）。返回 [(lag_frames, period_s, ac), ...]"""
    s = np.asarray(s, dtype=float)
    n = len(s)
    if n < 8:
        return []
    mu = float(np.mean(s))
    sd = float(np.std(s))
    if sd < 1e-9:
        return []
    best = []
    max_lag = min(n // 2, int(n / (fps * fmin)) + 2)
    for lag in range(2, max_lag):
        num = 0.0
        cnt = 0
        for i in range(n - lag):
            num += (s[i] - mu) * (s[i + lag] - mu)
            cnt += 1
        ac = num / cnt / sd / sd if cnt else 0
        best.append((ac, lag))
    best.sort(reverse=True)
    out = []
    for ac, lag in best[:top]:
        period = lag / fps
        if fmax is not None and period > 1.0 / fmax:
            continue
        out.append((lag, period, ac))
    return out


# ============== Playwright helpers ==============
# 异步版（verify_white_disc_* 三件套）+ 同步版（其余 10 个 verify_*.py）。

def reset_animations(page):
    """把 fairy-svg 里所有动画统一重置到相位 0。返回 Promise<void> / None。"""
    return page.evaluate("""
        () => {
          const ids = ['brightRing', 'ringGlow', 'halo', 'irisPulse', 'corners'];
          for (const id of ids) {
            const el = document.getElementById(id);
            if (el) { el.style.animation = 'none'; }
          }
          document.getElementById('brightRing')?.getBoundingClientRect();
          for (const id of ids) {
            const el = document.getElementById(id);
            if (el) { el.style.animation = ''; }
          }
        }
    """)


def hide_bubble(page):
    return page.evaluate("document.getElementById('bubble').classList.add('hidden')")


def hide_shadow(page):
    return page.evaluate("document.getElementById('fairy-svg').style.filter='none'")


def make_sync_page(*, viewport=(360, 380), headless=True, channel='chrome'):
    """同步 Playwright。返回 (browser, page)。page 已 goto RENDERER_URL + 1.4s + 隐藏 bubble."""
    from playwright.sync_api import sync_playwright
    cm = sync_playwright().__enter__()
    browser = getattr(cm, 'chromium' if False else cm).__dict__ if False else cm.chromium
    browser = cm.chromium.launch(channel=channel, headless=headless)
    page = browser.new_page(viewport={'width': viewport[0], 'height': viewport[1]})
    page.goto(RENDERER_URL)
    page.wait_for_timeout(1400)
    page.evaluate("document.getElementById('bubble').classList.add('hidden')")
    return cm, browser, page


def close_sync(cm):
    cm.__exit__(None, None, None)


async def make_async_page(*, viewport=(320, 320), headless=True, channel='chrome'):
    """异步 Playwright。返回 (browser, page)。"""
    from playwright.async_api import async_playwright
    p = async_playwright()
    await p.start()
    browser = await p.chromium.launch(channel=channel, headless=headless)
    ctx = await browser.new_context(viewport={'width': viewport[0], 'height': viewport[1]})
    page = await ctx.new_page()
    await page.goto(RENDERER_URL)
    await page.wait_for_timeout(1200)
    return p, browser, page


async def close_async(p, browser):
    await browser.close()
    await p.stop()


async def svg_clip_rect(page):
    """异步：取 fairy-svg 元素在屏幕上的 bbox {l,t,w,h}，用作 screenshot clip。"""
    return await page.evaluate("""
        () => {
          const r = document.getElementById('fairy-svg').getBoundingClientRect();
          return { l: r.left, t: r.top, w: r.width, h: r.height };
        }
    """)


def clip_to_svg_sync(page):
    return page.evaluate("""
        () => {
          const r = document.getElementById('fairy-svg').getBoundingClientRect();
          return { x: r.left, y: r.top, width: r.width, height: r.height };
        }
    """)