# -*- coding: utf-8 -*-
# BV1CkcbzgEkC 0-15s 60fps 高密度抽帧（之前 12fps alias 严重）
import imageio_ffmpeg, subprocess, os

BASE = r'D:\work\fairy-pet'
ff = imageio_ffmpeg.get_ffmpeg_exe()
src = os.path.join(BASE, 'ref_video/iris_pulse.f30080.mp4')
outdir = os.path.join(BASE, 'frames_hifps2')
os.makedirs(outdir, exist_ok=True)
for f in os.listdir(outdir):
    os.remove(os.path.join(outdir, f))
# 0-15s, fps=60, scale=1280 (足够保留细节但不太慢)
cmd = [ff, '-y', '-ss', '0', '-t', '15', '-i', src,
       '-vf', 'fps=60,scale=1280:-1:flags=lanczos', '-pix_fmt', 'rgb24',
       os.path.join(outdir, 'f%04d.png')]
r = subprocess.run(cmd, capture_output=True, text=True)
files = sorted(f for f in os.listdir(outdir) if f.endswith('.png'))
print(f'60fps frames: {len(files)} (expected ~900)')