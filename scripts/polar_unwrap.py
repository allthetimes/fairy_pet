"""极坐标展开：把 Fairy 的环形区域"拉直"成矩形图，直观看出缺口角度与径向结构。

输出图 x 轴 = 角度(0..360°)，y 轴 = 半径(由内到外)。
用法: python polar_unwrap.py <图片> <输出.png> [cx] [cy] [rmin] [rmax] [scale]
"""
import sys
import numpy as np
from PIL import Image

path, out = sys.argv[1], sys.argv[2]
cx = float(sys.argv[3]) if len(sys.argv) > 3 else 257.5
cy = float(sys.argv[4]) if len(sys.argv) > 4 else 254.0
rmin = float(sys.argv[5]) if len(sys.argv) > 5 else 120
rmax = float(sys.argv[6]) if len(sys.argv) > 6 else 235
scale = int(sys.argv[7]) if len(sys.argv) > 7 else 3

a = np.asarray(Image.open(path).convert("RGB"))
H, W, _ = a.shape

NA = 1440                      # 角度采样数
NR = int((rmax - rmin) * 4)    # 半径采样数
th = np.linspace(0, 2 * np.pi, NA, endpoint=False)
rr = np.linspace(rmin, rmax, NR)

T, Rg = np.meshgrid(th, rr)     # (NR, NA)
xs = np.clip((cx + Rg * np.cos(T)).round().astype(int), 0, W - 1)
ys = np.clip((cy + Rg * np.sin(T)).round().astype(int), 0, H - 1)
strip = a[ys, xs].astype(np.uint8)      # (NR, NA, 3)

img = Image.fromarray(strip).resize((NA * scale // 4, NR * scale), Image.NEAREST)
img.save(out)
print(f"极坐标展开 -> {out}  {img.width}x{img.height}")
print(f"  x 轴: 0°(右) → 90°(下) → 180°(左) → 270°(上) → 360°")
print(f"  y 轴: r={rmin} 在上, r={rmax} 在下；每 {NR}px 对应 {rmax-rmin}px 半径")

# 沿半径方向找颜色跳变 → 精确环边界
strip_f = strip.astype(np.float32)
d = np.abs(np.diff(strip_f, axis=0)).sum(axis=2).mean(axis=1)   # (NR-1,)
print("\n  径向跳变峰值（每 0.25px 半径一个采样）:")
peak_r = rmin + (np.argsort(-d)[:14] + 0.5) * (rmax - rmin) / NR
for r in sorted(peak_r):
    print(f"    r ≈ {r:7.2f}")
