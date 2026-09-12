# -*- coding: utf-8 -*-
# 保存 BV1CkcbzgEkC 0-15s 若干整帧全图，供主人指认眼睛位置
import imageio_ffmpeg, subprocess, os

BASE = r'D:\work\fairy-pet'
ff = imageio_ffmpeg.get_ffmpeg_exe()
src = os.path.join(BASE, 'ref_video/iris_pulse.f30080.mp4')
out = os.path.join(BASE, 'full_frames')
os.makedirs(out, exist_ok=True)
for f in os.listdir(out):
    os.remove(os.path.join(out, f))

for t in [0.5, 3.0, 7.0, 11.0, 14.0]:
    cmd = [ff, '-y', '-ss', str(t), '-i', src, '-frames:v', '1',
           '-vf', 'scale=1280:-1', os.path.join(out, f't{t:.1f}.png')]
    subprocess.run(cmd, capture_output=True, text=True)
print('saved:', sorted(os.listdir(out)))