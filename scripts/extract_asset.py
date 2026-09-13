"""概念图 → 可用的透明底素材。

做三件事：
  1. 抠背景
     - magenta: 按到 #FF00FF 的距离键控（AI 出图被要求在纯品红底上绘制时用）
     - border : 从图像边界洪水填充（白/灰底时用，保证不打穿内部的白色环）
  2. 取「最大连通域」作为主体 —— 自动丢掉右下角的 AI 水印和零散噪点
  3. 裁到主体外接框并补成正方形，同时导出深色/浅色两种预览图

用法:
  python extract_asset.py <输入.png> <输出.png> [--mode magenta|border] [--key-color R,G,B]
"""
import argparse
import os
import numpy as np
from PIL import Image
from scipy import ndimage

PAD_RATIO = 0.08      # 裁切后四周留白（相对主体尺寸）
ERODE_PX = 1          # 先腐蚀，去掉键控残留的彩边
BLUR_PX = 1.1         # 再轻微模糊，得到 1-2px 的柔和边缘


def build_bg_candidate(rgb, mode, key_color):
    """返回「疑似背景」的布尔掩码（尚未判断是否连通到边界）。"""
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    if mode == "magenta":
        k = np.array(key_color, dtype=np.float32)
        dist = np.sqrt(((rgb - k) ** 2).sum(axis=2))
        return dist < 90.0
    # border: 接近白/浅灰的低饱和像素
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1e-6)
    return (mx > 205) & (sat < 0.16)


def border_connected(candidate):
    """只保留与图像边界连通的候选背景。"""
    h, w = candidate.shape
    seed = np.zeros_like(candidate)
    seed[0, :] = seed[-1, :] = True
    seed[:, 0] = seed[:, -1] = True
    seed &= candidate
    if not seed.any():
        return np.zeros_like(candidate)
    # 迭代传播，直到不再增长
    cur = seed.copy()
    for _ in range(4000):
        nxt = ndimage.binary_dilation(cur, iterations=1) & candidate
        if nxt.sum() == cur.sum():
            break
        cur = nxt
    return cur


def despill(rgb, fringe, mode):
    """去掉边缘残留的底色污染。"""
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    if mode == "magenta":
        bad = fringe & (r > g + 20) & (b > g + 20)
        rgb[:, :, 1] = np.where(bad, np.maximum(g, (r + b) * 0.5 * 0.85), g)
    return rgb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--mode", choices=["magenta", "border"], default="magenta")
    ap.add_argument("--key-color", default="255,0,255")
    args = ap.parse_args()

    key_color = [float(x) for x in args.key_color.split(",")]

    im = Image.open(args.src).convert("RGB")
    rgb = np.array(im).astype(np.float32)
    h, w, _ = rgb.shape

    cand = build_bg_candidate(rgb, args.mode, key_color)
    bg = border_connected(cand) if args.mode == "border" else cand
    alpha = (~bg).astype(np.float32)

    # 只保留最大连通域 —— 水印是独立的小连通域，会被直接剔除
    labeled, n = ndimage.label(alpha > 0.5)
    if n == 0:
        raise SystemExit("抠图后没有内容，检查 --mode 与背景色是否匹配")
    sizes = ndimage.sum(alpha > 0.5, labeled, range(1, n + 1))
    main_id = int(np.argmax(sizes)) + 1
    keep = labeled == main_id
    dropped = int(n - 1)
    alpha = keep.astype(np.float32)

    rgb = despill(rgb, keep & (alpha > 0), args.mode)

    # 腐蚀去彩边 → 模糊出柔和边缘
    alpha = ndimage.binary_erosion(alpha > 0.5, iterations=ERODE_PX).astype(np.float32)
    alpha = ndimage.gaussian_filter(alpha, BLUR_PX)
    alpha = np.clip((alpha - 0.35) / 0.35, 0.0, 1.0)

    # 外接框 + 补正方形
    ys, xs = np.where(alpha > 0.02)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    side = int(round(max(x1 - x0, y1 - y0) * (1 + PAD_RATIO * 2)))
    left, top = int(round(cx - side / 2)), int(round(cy - side / 2))

    rgba = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)
    out = Image.fromarray(rgba, "RGBA")
    out = out.crop((left, top, left + side, top + side))
    out.save(args.dst)

    a = np.array(out)[:, :, 3]
    opaque = int((a > 200).sum())
    print(f"{os.path.basename(args.src)}  [{args.mode}]")
    print(f"  -> {os.path.basename(args.dst)}  {out.width}x{out.height}")
    print(f"  丢弃杂散连通域 {dropped} 个（含水印）")
    print(f"  不透明占比 {opaque / a.size * 100:.1f}%   四角 alpha = "
          f"{a[1, 1]}, {a[1, -2]}, {a[-2, 1]}, {a[-2, -2]}")

    # 预览图：深色底 / 浅色底，方便判断发光与实心效果
    base = os.path.splitext(args.dst)[0]
    arr = np.array(out).astype(np.float32)
    for name, bgc in (("dark", (16, 20, 32)), ("light", (245, 247, 250))):
        canvas = np.zeros_like(arr[:, :, :3]) + np.array(bgc, dtype=np.float32)
        al = arr[:, :, 3:4] / 255.0
        comp = arr[:, :, :3] * al + canvas * (1 - al)
        Image.fromarray(comp.astype(np.uint8), "RGB").save(f"{base}_preview_{name}.png")
    print(f"  预览: {os.path.basename(base)}_preview_dark.png / _light.png")


if __name__ == "__main__":
    main()
