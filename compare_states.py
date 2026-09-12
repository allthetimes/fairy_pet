# -*- coding: utf-8 -*-
# 截 4 个状态对比：idle、鼠标在窗口左、鼠标在窗口右、眨眼瞬间
import os
from playwright.sync_api import sync_playwright

BASE = r'D:\work\fairy-pet'
OUT = os.path.join(BASE, 'compare')
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

    # 状态 A：idle (鼠标在右下角远离眼睛)
    page.mouse.move(350, 350)
    page.wait_for_timeout(300)
    page.screenshot(path=os.path.join(OUT, 'A_idle.png'))

    # 状态 B：鼠标在窗口左下（视线应该偏左下）
    page.mouse.move(40, 250)
    page.wait_for_timeout(400)
    page.screenshot(path=os.path.join(OUT, 'B_gaze_left.png'))

    # 状态 C：鼠标在窗口右上（视线应该偏右上）
    page.mouse.move(320, 30)
    page.wait_for_timeout(400)
    page.screenshot(path=os.path.join(OUT, 'C_gaze_right.png'))

    # 状态 D：强制触发眨眼 (加 class 110ms)
    page.evaluate("document.getElementById('iris').classList.add('blinking')")
    page.wait_for_timeout(60)
    page.screenshot(path=os.path.join(OUT, 'D_blink.png'))
    page.evaluate("document.getElementById('iris').classList.remove('blinking')")

    # 状态 E：呼吸峰值（等 1.2s 让 ringBreathe 跑到 50% 相位）
    page.wait_for_timeout(600)
    page.screenshot(path=os.path.join(OUT, 'E_breathe_peak.png'))

    b.close()

print('已生成：', sorted(f for f in os.listdir(OUT) if f.endswith('.png')))