# -*- coding: utf-8 -*-
# BV1CkcbzgEkC 0-15s 高帧率抽帧 + 找右边的眼睛
import imageio_ffmpeg, subprocess, os
from PIL import Image

BASE = r'D:\work\fairy-pet'
ff = imageio_ffmpeg.get_ffmpeg_exe()

src = os.path.join(BASE, 'ref_video/iris_pulse.f30080.mp4')
outdir = os.path.join(BASE, 'frames_iris_pulse')
os.makedirs(outdir, exist_ok=True)
for f in os.listdir(outdir):
    os.remove(os.path.join(outdir, f))
# 0-15s, fps=12, scale 1920
cmd = [ff, '-y', '-ss', '0', '-t', '15', '-i', src,
       '-vf', 'fps=12,scale=1920:-1:flags=lanczos', '-pix_fmt', 'rgb24',
       os.path.join(outdir, 'f%04d.png')]
r = subprocess.run(cmd, capture_output=True, text=True)
files = sorted(f for f in os.listdir(outdir) if f.endswith('.png'))
print(f'frames: {len(files)}')

# 在右侧 1/2 区域内找蓝环（眼睛在右边）
def find_eye(img):
    im = img.convert('RGB'); W, H = im.size; px = im.load()
    xs, ys = [], []
    step = 4
    for y in range(0, H, step):
        for x in range(W // 2, W, step):
            r, g, b = px[x, y]
            if b > 150 and b - r > 110 and b - g > 70 and g < 130:
                xs.append(x); ys.append(y)
    if len(xs) < 30:
        return None
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = x1 - x0, y1 - y0
    if bw < 20 or bh < 20 or not (0.5 < bw / bh < 2.0):
        return None
    return (x0 + x1) // 2, (y0 + y1) // 2, (bw + bh) / 4

# 采样几帧定位眼睛
sizes = []
for f in files[::12]:  # 每秒 1 帧采样
    img = Image.open(os.path.join(outdir, f))
    res = find_eye(img)
    sizes.append((f, res))
for f, res in sizes:
    print(f, '->', None if res is None else ('(%.0f,%.0f) r=%.1f' % res))