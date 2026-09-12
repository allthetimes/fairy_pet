# -*- coding: utf-8 -*-
# egg.mp4 高帧率抽帧 -> 眼部归一化裁剪 -> 逐帧指标（眨眼/瞳位/环亮度）
import imageio_ffmpeg, subprocess, os
from PIL import Image

BASE = r'D:\work\fairy-pet'
ff = imageio_ffmpeg.get_ffmpeg_exe()

# 1) 选一段干净的连续段 t=21-43s，fps=12，放大到 1920 宽
SEG = ('21', '43')
outdir = os.path.join(BASE, 'frames_hifps')
os.makedirs(outdir, exist_ok=True)
for f in os.listdir(outdir):
    if f.endswith('.png'):
        os.remove(os.path.join(outdir, f))
cmd = [ff, '-y', '-ss', SEG[0], '-to', SEG[1], '-i', os.path.join(BASE, 'ref_video/egg.mp4'),
       '-vf', 'fps=12,scale=1920:-1:flags=lanczos', '-pix_fmt', 'rgb24',
       os.path.join(outdir, 'f%05d.png')]
r = subprocess.run(cmd, capture_output=True, text=True)
files = sorted(f for f in os.listdir(outdir) if f.endswith('.png'))
print('hifps frames:', len(files), 'rc=', r.returncode)

# 2) 每帧定位眼睛并裁剪归一化 160x160
CROP_DIR = os.path.join(BASE, 'eye_crops')
os.makedirs(CROP_DIR, exist_ok=True)
for f in os.listdir(CROP_DIR):
    if f.endswith('.png'):
        os.remove(os.path.join(CROP_DIR, f))

def find_eye(img):
    im = img.convert('RGB'); W, H = im.size; px = im.load()
    step = 4
    xs, ys = [], []
    for y in range(0, H, step):
        for x in range(0, W, step):
            r, g, b = px[x, y]
            if b > 150 and b - r > 110 and b - g > 70 and g < 130:
                xs.append(x); ys.append(y)
    if len(xs) < 30:
        return None
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = x1 - x0, y1 - y0
    if w < 20 or h < 20 or not (0.5 < w / h < 2.0):
        return None
    return (x0 + x1) // 2, (y0 + y1) // 2, (w + h) / 4

crops = []
for f in files:
    img = Image.open(os.path.join(outdir, f))
    res = find_eye(img)
    if not res:
        continue
    cx, cy, r = res
    R = int(r * 1.55)  # 裁剪半径 = 眼半径 * 1.55（含外围暗环）
    R = max(R, 24)
    box = (cx - R, cy - R, cx + R, cy + R)
    crop = img.crop(box).convert('RGB').resize((160, 160), Image.LANCZOS)
    outp = os.path.join(CROP_DIR, f)
    crop.save(outp)
    crops.append((f, cx, cy, r))

print('eye crops:', len(crops))
if crops:
    import json
    with open(os.path.join(BASE, 'eye_crops_meta.json'), 'w') as fp:
        json.dump([{'f': a, 'cx': b, 'cy': c, 'r': d} for a, b, c, d in crops], fp)
