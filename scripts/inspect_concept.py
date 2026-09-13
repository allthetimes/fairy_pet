"""概念图体检：透明底是否真透明、主色提取、几何比例测量。"""
import sys, os, glob
import numpy as np
from PIL import Image

def report(path):
    im = Image.open(path).convert("RGBA")
    a = np.array(im)
    h, w, _ = a.shape
    alpha = a[:, :, 3]
    rgb = a[:, :, :3].astype(np.int16)

    print("=" * 72)
    print(f"FILE  {os.path.basename(path)}   {w}x{h}")
    print(f"  alpha  min={alpha.min():3d} max={alpha.max():3d} mean={alpha.mean():6.1f}")
    corners = [alpha[2, 2], alpha[2, w - 3], alpha[h - 3, 2], alpha[h - 3, w - 3]]
    print(f"  四角 alpha = {corners}")
    cy, cx = h // 2, w // 2
    print(f"  中心 alpha = {alpha[cy, cx]}")

    # 判定：四角是否真透明
    if max(corners) <= 8:
        verdict = "真透明底 (PASS)"
    elif max(corners) >= 250:
        verdict = "不透明/白底 (需抠图)"
    else:
        verdict = f"半透明 (边缘羽化/可疑)"
    print(f"  判定: {verdict}")

    # 棋盘格检测：透明区若被画成灰白小方块，采样四角区域的方差会异常高
    patch = rgb[0:64, 0:64].reshape(-1, 3)
    print(f"  左上 64x64 均值={patch.mean(axis=0).round(1)} 标准差={patch.std(axis=0).round(1)}")
    if max(corners) >= 250 and patch.std() > 12:
        print("  ⚠️ 疑似把『棋盘格』画成了实际像素（经典 AI 出图坑）")

    # 非透明区域的主色聚类（简单量化）
    mask = alpha > 200
    if mask.sum() > 0:
        px = (rgb[mask] // 16 * 16).astype(np.uint8)
        colors, counts = np.unique(px.reshape(-1, 3), axis=0, return_counts=True)
        order = np.argsort(-counts)[:6]
        print("  非透明区主色 TOP6 (量化到16级):")
        for i in order:
            r, g, b = colors[i]
            print(f"    #{r:02X}{g:02X}{b:02X}  占比 {counts[i] / mask.sum() * 100:5.1f}%")

    # 内容包围盒 & 几何比例
    ys, xs = np.where(mask)
    if len(xs):
        bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
        bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
        print(f"  内容包围盒 {bw}x{bh}  距窗口边距 L={bx0} R={w-1-bx1} T={by0} B={h-1-by1}")
        print(f"  填充率(内容/外接方) = {mask.sum() / (bw * bh) * 100:5.1f}%  (环形应明显 <60%)")

        # 沿水平中线扫 alpha，判断环带结构
        row = alpha[cy, bx0:bx1 + 1]
        edges, prev = [], row[0] > 128
        for i, v in enumerate(row):
            cur = v > 128
            if cur != prev:
                edges.append((i, "in" if cur else "out"))
                prev = cur
        if edges:
            print(f"  水平中线穿越次数 = {len(edges)}  (越多=同心环/刻度越复杂)")
            print(f"  前 10 个边界: {[e[0] for e in edges[:10]]}")
    print()

target_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
files = sorted(glob.glob(os.path.join(target_dir, "*.png")))
if not files:
    print(f"没有找到 png，目录: {target_dir}")
for f in files:
    report(f)
