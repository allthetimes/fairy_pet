"""品红底抠图 + 内容裁切。

针对"平涂矢量风 + 纯品红 #FF00FF 背景"的 AI 出图：
  1. 按到品红的距离生成 alpha
  2. 边缘去品红溢出 (despill)
  3. 内容外接框裁切 + 等比留边

用法: python chroma_key.py <输入png> [输出png]
"""
import sys
import os
import numpy as np
from PIL import Image

KEY = np.array([255.0, 0.0, 255.0])   # 品红
T_LOW = 55.0                          # 距离 <= T_LOW  → 全透明
T_HIGH = 150.0                        # 距离 >= T_HIGH → 全不透明
PAD_RATIO = 0.06                      # 裁切后四周留白比例


def key_out(path, out_path):
    im = Image.open(path).convert("RGB")
    rgb = np.array(im).astype(np.float32)
    h, w, _ = rgb.shape

    dist = np.sqrt(((rgb - KEY) ** 2).sum(axis=2))
    alpha = np.clip((dist - T_LOW) / (T_HIGH - T_LOW), 0.0, 1.0)

    # 边缘 despill: 把残留的品红（R高 G低 B高）往中性拉
    fringe = (alpha > 0.0) & (alpha < 1.0)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    magenta_like = (r > g + 25) & (b > g + 25)
    fix = fringe & magenta_like
    target_g = np.minimum(255.0, (r + b) * 0.5)
    rgb[:, :, 1] = np.where(fix, np.maximum(g, target_g * 0.85), g)

    rgba = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)
    out = Image.fromarray(rgba, "RGBA")

    # 内容外接框 + 等边留白，保证是正方形且物体居中
    a = rgba[:, :, 3]
    ys, xs = np.where(a > 16)
    if len(xs) == 0:
        raise SystemExit("抠图后没有内容，检查背景色是否为纯品红")
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    side = int(max(x1 - x0, y1 - y0) * (1 + PAD_RATIO * 2))
    half = side // 2
    box = (int(cx - half), int(cy - half), int(cx - half) + side, int(cy - half) + side)
    out = out.crop(box)

    out.save(out_path)

    kept = int((np.array(out)[:, :, 3] > 200).sum())
    ratio = kept / (out.width * out.height) * 100
    print(f"{os.path.basename(path)}")
    print(f"  -> {os.path.basename(out_path)}  {out.width}x{out.height}")
    print(f"  不透明像素占比 {ratio:.1f}%   (纯环形 logo 通常 25-55%)")
    print(f"  四角 alpha = {np.array(out)[2, 2, 3]}, {np.array(out)[2, -3, 3]}, "
          f"{np.array(out)[-3, 2, 3]}, {np.array(out)[-3, -3, 3]}")
    return out_path


if __name__ == "__main__":
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + "_keyed.png"
    key_out(src, dst)
