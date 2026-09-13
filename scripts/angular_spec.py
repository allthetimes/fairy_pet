"""量 Fairy 外圈高饱和蓝圆盘的齿轮缺口（"四个角"）与内部结构。

外圈蓝的定义：B 高且 B-R 大（能把外圈高饱和蓝与内层靛蓝/瞳孔分开）。

用法: python angular_spec.py <图片> [cx] [cy]
"""
import sys
import numpy as np
from PIL import Image

path = sys.argv[1]
cx = float(sys.argv[2]) if len(sys.argv) > 2 else 257.5
cy = float(sys.argv[3]) if len(sys.argv) > 3 else 254.0

a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
H, W, _ = a.shape
R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]

outer_blue = (B > 180) & (G < 95) & (R < 85)   # 外圈高饱和蓝盘（背景辉光 G 很高，可区分）
rim = (R > 170) & (G > 180) & (B > 225)       # 细白描边

yy, xx = np.mgrid[0:H, 0:W]
rr = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
tt = (np.degrees(np.arctan2(yy - cy, xx - cx)) + 360) % 360   # 0=右, 90=下(图像坐标)

print("=== 外圈高饱和蓝：逐角度外边界半径 r(θ) ===")
print("（θ 以图像坐标计：0°=右, 90°=下, 180°=左, 270°=上）")
vals = []
for deg in np.arange(0, 360, 3.0):
    lo, hi = 140, 250
    cs = np.cos(np.radians(deg)); sn = np.sin(np.radians(deg))
    last = 0
    for r in np.arange(hi, lo, -0.5):
        x = int(round(cx + r * cs)); y = int(round(cy + r * sn))
        if 0 <= x < W and 0 <= y < H and outer_blue[y, x]:
            last = r; break
    vals.append((deg, last))

mx = max(v for _, v in vals) or 1
mn = min(v for _, v in vals if v > 0)
print(f"  外边界 r: 最大 {mx:.1f}  最小 {mn:.1f}   起伏 {mx-mn:.1f}px")
line = ""
for deg, r in vals:
    frac = (r - mn) / max(mx - mn, 1e-6)
    line += "█" if frac > 0.75 else ("▓" if frac > 0.45 else ("░" if frac > 0.15 else "·"))
print(f"  0°→357° 轮廓: {line}")
print("  逐点:", " ".join(f"{int(d)}:{int(v)}" for d, v in vals[::6]))

if mn > 0:
    deep = [(d, v) for d, v in vals if v < mn + (mx - mn) * 0.35]
    if deep:
        groups, cur = [], [deep[0]]
        for d, v in deep[1:]:
            if d - cur[-1][0] <= 3.5:
                cur.append((d, v))
            else:
                groups.append(cur); cur = [(d, v)]
        groups.append(cur)
        if len(groups) > 1 and groups[0][0][0] == 0 and groups[-1][-1][0] >= 357:
            groups[0] = groups[-1] + groups[0]; groups.pop()
        print(f"\n=== 缺口/内凹处共 {len(groups)} 个 ===")
        for g in groups:
            ds = [d for d, _ in g]
            c = (min(ds) + max(ds)) / 2
            print(f"  中心 {c:6.1f}°  跨度 {min(ds):5.1f}~{max(ds):5.1f}° "
                  f"(宽 {max(ds)-min(ds):4.1f}°)  最内凹 r={min(v for _,v in g):.1f}")

print("\n=== 中央瞳孔与高光球定位 ===")
pupil = (B > 100) & (B < 170) & (R < 80) & (G < 105)
cl = (R > 200) & (G > 205) & (B > 228)
for name, m in (("瞳孔暗区", pupil), ("白色高光", cl)):
    mm = m & (rr < 110)
    ys, xs = np.where(mm)
    if len(xs) > 20:
        px, py = xs.mean(), ys.mean()
        rad = np.sqrt(mm.sum() / np.pi)
        print(f"  {name}: 质心偏移圆心 (dx={px-cx:+6.1f}, dy={py-cy:+6.1f})  "
              f"等效半径 {rad:5.1f}px  像素 {mm.sum()}")
    else:
        print(f"  {name}: 未检出")
