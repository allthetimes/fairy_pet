"""精确提取 Fairy 外圈缺口的角位置。

方法：逐角度沿半径扫描，找"深靛蓝 → 高饱和蓝"的边界半径 r_in(θ)。
缺口处该边界会显著外推（蓝被挖掉）。取 r_in(θ) 的局部极大值即为缺口中心。

用法: python notch_spec.py <图片> [cx] [cy]
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

# 高饱和外圈蓝：实测 #2C40D7 附近
bright_blue = (B > 190) & (G < 100) & (R < 80) & (B - R > 125)
# 深靛蓝暗带：实测 #242986 / #212888 附近
indigo = (B > 110) & (B < 175) & (R < 70) & (G < 75)

def r_at(deg, r_lo, r_hi, step=0.25):
    cs, sn = np.cos(np.radians(deg)), np.sin(np.radians(deg))
    for r in np.arange(r_lo, r_hi, step):
        x = int(round(cx + r * cs)); y = int(round(cy + r * sn))
        if 0 <= x < W and 0 <= y < H:
            yield r, x, y

degs = np.arange(0, 360, 0.5)
r_in_blue, r_out_blue, r_out_indigo = [], [], []
for d in degs:
    ri = ro = rind = np.nan
    for r, x, y in r_at(d, 150, 225):
        if bright_blue[y, x]:
            if np.isnan(ri):
                ri = r
            ro = r
    for r, x, y in r_at(d, 130, 200):
        if indigo[y, x]:
            rind = r
    r_in_blue.append(ri); r_out_blue.append(ro); r_out_indigo.append(rind)

r_in_blue = np.array(r_in_blue)
valid = ~np.isnan(r_in_blue)
print(f"外圈蓝：有效角度 {valid.sum()}/{len(degs)}")
print(f"  高饱和蓝 内边界 r_in : 中位 {np.nanmedian(r_in_blue):.1f}  "
      f"范围 {np.nanmin(r_in_blue):.1f} ~ {np.nanmax(r_in_blue):.1f}")
print(f"  高饱和蓝 外边界 r_out: 中位 {np.nanmedian(r_out_blue):.1f}  "
      f"范围 {np.nanmin(r_out_blue):.1f} ~ {np.nanmax(r_out_blue):.1f}")

# 缺口 = r_in 显著大于中位数的角度段
med = np.nanmedian(r_in_blue)
thr = med + (np.nanmax(r_in_blue) - med) * 0.35
is_deep = valid & (r_in_blue > thr)
print(f"\n判定阈值 r_in > {thr:.1f}（中位 {med:.1f}）")

groups, cur = [], None
for d, f in zip(degs, is_deep):
    if f and cur is None:
        cur = [d, d]
    elif f:
        cur[1] = d
    elif cur is not None:
        groups.append(cur); cur = None
if cur is not None:
    groups.append(cur)
# 首尾相接
if len(groups) > 1 and groups[0][0] <= 0.5 and groups[-1][1] >= 359.0:
    groups[0][0] = groups[-1][0] - 360
    groups.pop()

print(f"\n=== 缺口共 {len(groups)} 处 ===")
print("（θ 按图像坐标：0°=右 90°=下 180°=左 270°=上）")
res = []
for g in groups:
    m = (degs >= g[0] % 360) & (degs <= g[1])
    peak = np.nanmax(r_in_blue[m])
    c = float(degs[m][np.nanargmax(r_in_blue[m])])
    res.append({"center_deg": round(c % 360, 1), "span": [round(g[0] % 360, 1), round(g[1], 1)],
                "width_deg": round(g[1] - g[0], 1), "peak_r_in": round(peak, 1)})
    print(f"  中心 {c % 360:6.1f}°   跨度 {g[0] % 360:6.1f} ~ {g[1]:6.1f}°  "
          f"宽 {g[1]-g[0]:5.1f}°   尖端 r_in={peak:.1f}")

# 内层环边界（用于校核前面测到的半径）
print("\n=== 各环半径校核（沿 12 条射线取中位）===")
for name, mask in (("高饱和蓝", bright_blue), ("深靛蓝", indigo)):
    radii = []
    for d in np.arange(0, 360, 5):
        cs, sn = np.cos(np.radians(d)), np.sin(np.radians(d))
        hit = [r for r in np.arange(20, 230, 0.5)
               if 0 <= int(round(cx + r * cs)) < W and 0 <= int(round(cy + r * sn)) < H
               and mask[int(round(cy + r * sn)), int(round(cx + r * cs))]]
        if hit:
            radii.append((min(hit), max(hit)))
    if radii:
        arr = np.array(radii)
        print(f"  {name}: 内边界 中位 {np.median(arr[:,0]):.1f}   外边界 中位 {np.median(arr[:,1]):.1f}")

import json
print("\n" + json.dumps(res, ensure_ascii=False))
