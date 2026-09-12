# -*- coding: utf-8 -*-
# 从 egg.mp4 / voice.mp4 抽帧，并按"亮蓝外环+白盘"特征自动定位 Fairy 眼睛
import imageio_ffmpeg, subprocess, os, sys

BASE = r'D:\work\fairy-pet'
ff = imageio_ffmpeg.get_ffmpeg_exe()

jobs = [
    ('ref_video/egg.mp4',   'frames_egg',   2.0, 960),
    ('ref_video/voice.mp4', 'frames_voice', 2.0, 960),
]

for src, outdir, fps, w in jobs:
    out = os.path.join(BASE, outdir)
    os.makedirs(out, exist_ok=True)
    # 清空旧帧
    for f in os.listdir(out):
        if f.endswith('.jpg'):
            os.remove(os.path.join(out, f))
    cmd = [ff, '-y', '-i', os.path.join(BASE, src),
           '-vf', f'fps={fps},scale={w}:-1', '-q:v', '3',
           os.path.join(out, 'f%05d.jpg')]
    r = subprocess.run(cmd, capture_output=True, text=True)
    n = len([f for f in os.listdir(out) if f.endswith('.jpg')])
    print(f'{outdir}: {n} frames (rc={r.returncode})')
