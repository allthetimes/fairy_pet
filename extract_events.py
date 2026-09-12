# -*- coding: utf-8 -*-
# 提取帧差分 > 5 的关键时刻前后 2 帧（基线 → 大变化 → 之后 200ms）
# 共 5 个关键时刻
import os, shutil
from playwright.sync_api import sync_playwright

BASE = r'D:\work\fairy-pet'
OUT = os.path.join(BASE, 'compare_events')
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.png'):
        os.remove(os.path.join(OUT, f))

# 关键时刻（前后）
events = [
    (0.583, 'event_0583'),
    (2.383, 'event_2383'),
    (6.750, 'event_6750'),
    (9.617, 'event_9617'),
    (11.183, 'event_11183'),
]

# 直接从 frames_hifps2 拷贝关键时刻的帧（之前已生成 60fps 帧）
import imageio_ffmpeg
ff = imageio_ffmpeg.get_ffmpeg_exe()
src = os.path.join(BASE, 'ref_video/iris_pulse.f30080.mp4')

for t, name in events:
    # 截 [t-0.2s, t+0.2s] 这一段共 8 帧 (60fps → 24 帧 in 0.4s)
    out = os.path.join(BASE, f'frames_evt_{name}')
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        os.remove(os.path.join(out, f))
    cmd = [ff, '-y', '-ss', f'{t-0.2:.3f}', '-t', '0.4', '-i', src,
           '-vf', 'fps=60,scale=1280:-1:flags=lanczos', '-pix_fmt', 'rgb24',
           os.path.join(out, 'f%03d.png')]
    import subprocess
    subprocess.run(cmd, capture_output=True, text=True)
    print(f'{name}: t={t}s, frames generated')

# 用 Playwright 拼接成对比图：每行一个事件，每列 4 张关键帧
with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome')
    page = b.new_page(viewport={'width': 1280, 'height': 720})
    page.goto('about:blank')
    page.set_content("""<style>body{margin:0;background:#111;color:#fff;font:14px monospace}
        table{border-collapse:collapse}td{padding:4px 8px;border:1px solid #444}
        img{display:block;width:320px;height:240px}</style>""" +
        '<table><tr><th>event</th><th>frame 0</th><th>frame 8</th><th>frame 16</th><th>frame 24</th></tr>' +
        ''.join(f'<tr><td>{name}<br>t={t}s</td>' +
                ''.join(f'<td><img src="file:///{BASE}\\frames_evt_{name}\\f{i:03d}.png"></td>'
                        for i in [1, 9, 17, 24]) +
                '</tr>' for t, name in events) +
        '</table>')
    page.wait_for_timeout(1000)
    page.screenshot(path=os.path.join(OUT, 'events_grid.png'), full_page=True)
    b.close()

print('\nDone:', os.path.join(OUT, 'events_grid.png'))