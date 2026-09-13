"""把 Fairy 各层分离成掩码图，直接看出齿轮/缺口形状。

用法: python layer_mask.py <图片> <输出前缀> [cx] [cy]
"""
import sys
import os
import numpy as np
from PIL import Image

path, prefix = sys.argv[1], sys.argv[2]
cx = float(sys.argv[3]) if len(sys.argv) > 3 else 257.5
cy = float(sys.argv[4]) if len(sys.argv) > 4 else 254.0

im = Image.open(path).convert("RGB")
a = np.asarray(im).astype(np.float32)
H, W, _ = a.shape
R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
yy, xx = np.mgrid[0:H, 0:W]
rr = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)

# 各层的颜色定义（取自实测剖面）
layers = {
    "outer_blue": (B > 185) & (R < 78) & (G > 48) & (G < 100),
    "indigo":     (B > 115) & (B < 185) & (R < 60) & (G < 60),
    "white_ring": (R > 195) & (G > 190) & (B > 200) & (B < 232),
    "slate":      (R > 115) & (R < 175) & (B > 180) & (B - R > 45),
    "mid_blue":   (B > 175) & (R > 50) & (R < 95) & (G > 95) & (G < 140),
    "pupil":      (B > 110) & (B < 175) & (R < 60) & (G < 95),
    "highlight":  (R > 195) & (G > 200) & (B > 222),
}

# 一张彩色分层总图：每层一个纯色
palette = {
    "outer_blue": (0, 90, 255),
    "indigo":     (60, 0, 200),
    "white_ring": (255, 255, 255),
    "slate":      (150, 160, 200),
    "mid_blue":   (0, 170, 255),
    "pupil":      (20, 40, 100),
    "highlight":  (255, 240, 120),
}
canvas = np.zeros((H, W, 3), np.uint8)
for name, m in layers.items():
    canvas[m] = palette[name]
Image.fromarray(canvas).save(f"{prefix}_layers.png")
print(f"分层总图 -> {prefix}_layers.png")

for name, m in layers.items():
    vis = np.zeros((H, W), np.uint8)
    vis[m] = 255
    Image.fromarray(vis, "L").save(f"{prefix}_mask_{name}.png")

# 外圈蓝盘的"逐角度存在率"：在 r∈[172,205] 上采样，看每个角度的覆盖率
print("\n=== 外圈蓝盘角度覆盖率（在 r=172..205 采样）===")
th = np.linspace(0, 2 * np.pi, 720, endpoint=False)
cov = []
for t in th:
    cs, sn = np.cos(t), np.sin(t)
    hit = 0
    tot = 0
    for r in np.arange(172, 205, 1.0):
        x = int(round(cx + r * cs)); y = int(round(cy + r * sn))
        if 0 <= x < W and 0 <= y < H:
            tot += 1
            if layers["outer_blue"][y, x]:
                hit += 1
    cov.append(hit / max(tot, 1))
cov = np.array(cov)
line = "".join("█" if c > 0.8 else ("▓" if c > 0.5 else ("░" if c > 0.2 else "·")) for c in cov)
print("  0°→360° 覆盖:", line)
deg = np.degrees(th)
low = cov < 0.5
# 找连续的"缺口"段
groups, cur = [], None
for d, l in zip(deg, low):
    if l and cur is None:
        cur = [d, d]
    elif l:
        cur[1] = d
    elif cur is not None:
        groups.append(cur); cur = None
if cur is not None:
    groups.append(cur)
if len(groups) > 1 and groups[0][0] == 0 and groups[-1][1] >= 359:
    groups[0][0] = groups[-1][0] - 360; groups.pop()
print(f"\n  缺口段共 {len(groups)} 处（θ: 0°=右 90°=下 180°=左 270°=上）:")
for g in groups:
    c = (g[0] + g[1]) / 2
    print(f"    中心 {c + 360 if c < 0 else c:7.1f}°   跨度 {g[0]+360 if g[0]<0 else g[0]:7.1f} ~ {g[1]:7.1f}°"
          f"   宽 {g[1]-g[0]:6.1f}°")
