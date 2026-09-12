# -*- coding: utf-8 -*-
# 抽 0-15s 每 1s 一帧的右眼尖角特写 → 拼成网格图
import os
from PIL import Image

BASE = r'D:\work\fairy-pet'
D = os.path.join(BASE, 'frames_hifps2')
files = sorted(f for f in os.listdir(D) if f.endswith('.png'))
FPS = 60

# 右眼 1280 宽下中心 (890, 301), R=215
# 每 30 帧一帧 (= 2fps)，15s 共 30 帧，拼 6x5
times = list(range(0, 900, 30))   # 0..870 共 30 个
crops = []
for i in times:
    img = Image.open(os.path.join(D, files[i])).convert('RGB')
    crop = img.crop((890-230, 301-230, 890+230, 301+230)).resize((260, 260), Image.LANCZOS)
    crops.append(crop)
COLS, ROWS = 6, 5
grid = Image.new('RGB', (COLS*260, ROWS*260), (0, 0, 0))
for i, c in enumerate(crops):
    grid.paste(c, ((i % COLS)*260, (i // COLS)*260))
outp = os.path.join(BASE, 'compare_events', 'corners_seq.png')
grid.save(outp)
print('saved', outp, grid.size, 'frames =', len(times))