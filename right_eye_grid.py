# -*- coding: utf-8 -*-
# 抽取 0-15s 每 1s 一帧的右眼区域，拼成一张网格图，用于肉眼观察动画
import imageio_ffmpeg, subprocess, os
from PIL import Image

BASE = r'D:\work\fairy-pet'
ff = imageio_ffmpeg.get_ffmpeg_exe()
src = os.path.join(BASE, 'ref_video/iris_pulse.f30080.mp4')
tmp = os.path.join(BASE, 'right_eye_seq')
os.makedirs(tmp, exist_ok=True)
for f in os.listdir(tmp):
    os.remove(os.path.join(tmp, f))

# 右眼大致范围（1920 宽下）：中心 (1335, 452)，半径 ~300
# 先抽全帧再裁
times = [round(i * 1.0, 1) for i in range(16)]   # 0..15s
for i, t in enumerate(times):
    full = os.path.join(tmp, f'_full{i:02d}.png')
    subprocess.run([ff, '-y', '-ss', str(t), '-i', src, '-frames:v', '1',
                    full], capture_output=True, text=True)

# 拼图：每帧裁右眼
crops = []
for i, t in enumerate(times):
    im = Image.open(os.path.join(tmp, f'_full{i:02d}.png')).convert('RGB')
    W, H = im.size
    # 右眼中心：1280 宽下约 (890, 301) → 按比例
    sx = W / 1280.0
    cx, cy, R = int(890 * sx), int(301 * sx), int(240 * sx)
    crop = im.crop((cx - R, cy - R, cx + R, cy + R)).resize((220, 220), Image.LANCZOS)
    crops.append(crop)

COLS, ROWS = 4, 4
grid = Image.new('RGB', (COLS * 220, ROWS * 220), (0, 0, 0))
for i, c in enumerate(crops):
    grid.paste(c, ((i % COLS) * 220, (i // COLS) * 220))
outp = os.path.join(BASE, 'compare_events', 'right_eye_seq_1s.png')
grid.save(outp)
print('saved', outp, grid.size)
for f in os.listdir(tmp):
    if f.startswith('_full'):
        os.remove(os.path.join(tmp, f))