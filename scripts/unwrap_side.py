"""把官方立绘和代码复刻在极坐标下展开并并排输出，用于逐角度比对缺口形状。

用法: python unwrap_side.py <官方图> <复刻图> <输出.png> [stride]
"""
import sys
import numpy as np
from PIL import Image

ref_path, mine_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
NA, SCALE = 720, 2

# (路径, 圆心, 外缘半径)
CASES = [
    ("官方 2.6", ref_path, (257.5, 254.0), 212.5),
    ("代码复刻", mine_path, (349.5, 349.5), 214.8),
]

rows = []
for label, path, (cx, cy), R in CASES:
    a = np.asarray(Image.open(path).convert("RGB"))
    H, W, _ = a.shape
    th = np.linspace(0, 2 * np.pi, NA, endpoint=False)
    un = np.linspace(0.60, 1.10, 200)          # 归一化半径范围，只看外圈结构
    T, U = np.meshgrid(th, un)
    rg = U * R
    xs = np.clip((cx + rg * np.cos(T)).round().astype(int), 0, W - 1)
    ys = np.clip((cy + rg * np.sin(T)).round().astype(int), 0, H - 1)
    rows.append(a[ys, xs])

gap = np.full((10, NA, 3), 255, np.uint8)
stack = np.vstack([rows[0], gap, rows[1]])
img = Image.fromarray(stack).resize((NA * SCALE, stack.shape[0] * SCALE), Image.NEAREST)

# 画一条 33.5°+90k 的参考刻度线，验证四个角是否落在这四个角度
arr = np.array(img)
for base in (33.5, 123.5, 213.5, 303.5):
    x = int(base / 360 * NA * SCALE)
    for w in range(2):
        if x + w < arr.shape[1]:
            arr[:, x + w] = [255, 40, 40]
Image.fromarray(arr).save(out)
print(f"-> {out}  {arr.shape[1]}x{arr.shape[0]}")
print("  上=官方 2.6，下=代码复刻；红线为 33.5°/123.5°/213.5°/303.5°")
print("  x 轴 0°(右) → 90°(下) → 180°(左) → 270°(上) → 360°")
print("  y 轴 u=0.60(顶) → u=1.10(底)；四个角应出现在红线处，尖端指向下方(外侧)")
