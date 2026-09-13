"""把两张官方立绘的"眼球"区域按同一归一化尺度裁出来并排放大，用于对比眼球结构。

用法: python iris_compare.py <图A> <图B> <输出.png>
"""
import sys
import numpy as np
from PIL import Image


def find_center(arr, guess, span=26, step=2):
    """径向对称性最优的圆心（角度方差之和最小）。"""
    L = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    H, W = L.shape
    radii = np.arange(30, 200, 3)
    th = np.linspace(0, 2 * np.pi, 180, endpoint=False)
    ct, st = np.cos(th), np.sin(th)

    def score(cx, cy):
        xs = np.clip(np.round(cx + np.outer(radii, ct)).astype(int), 0, W - 1)
        ys = np.clip(np.round(cy + np.outer(radii, st)).astype(int), 0, H - 1)
        return L[ys, xs].std(axis=1).sum()

    best, bs = guess, None
    for cx in range(guess[0] - span, guess[0] + span + 1, step):
        for cy in range(guess[1] - span, guess[1] + span + 1, step):
            s = score(cx, cy)
            if bs is None or s < bs:
                bs, best = s, (cx, cy)
    cx0, cy0 = best
    for cx in np.arange(cx0 - step, cx0 + step + .25, .5):
        for cy in np.arange(cy0 - step, cy0 + step + .25, .5):
            s = score(cx, cy)
            if s < bs:
                bs, best = s, (cx, cy)
    return best


def outer_radius(arr, cx, cy):
    """内容外接半径（用非背景像素的 95 分位）。"""
    H, W, _ = arr.shape
    yy, xx = np.mgrid[0:H, 0:W]
    rr = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    L = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    m = (L > np.percentile(L, 55)) & (rr < 250)
    return np.percentile(rr[m], 99) if m.any() else 200


def crop_norm(arr, cx, cy, R, half_u, scale):
    d = int(R * half_u)
    box = (int(cx - d), int(cy - d), int(cx + d), int(cy + d))
    im = Image.fromarray(arr.astype(np.uint8)).crop(box)
    return im.resize((im.width * scale, im.height * scale), Image.LANCZOS)


A, B, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
res = []
for p in (A, B):
    arr = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)
    h, w, _ = arr.shape
    L = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    white = (arr[:, :, 0] > 185) & (arr[:, :, 1] > 185) & (arr[:, :, 2] > 195)
    ys, xs = np.where(white)
    guess = (int(xs.mean()) if len(xs) else w // 2, int(ys.mean()) if len(ys) else h // 2)
    cx, cy = find_center(arr, guess)
    R = outer_radius(arr, cx, cy)
    print(f"{p}: 圆心=({cx:.1f},{cy:.1f})  外缘R={R:.1f}  (图 {w}x{h})")
    res.append((p, arr, cx, cy, R))

HALF_U, SCALE = 0.42, 3      # 取核心半径的 42% 范围 = 眼球+高光所在区域
tiles = [crop_norm(a, cx, cy, R, HALF_U, SCALE) for _, a, cx, cy, R in res]
h = max(t.height for t in tiles)
gap = Image.new("RGB", (12, h), (255, 70, 70))
out = Image.new("RGB", (sum(t.width for t in tiles) + 12 * (len(tiles) - 1), h), (12, 16, 28))
x = 0
for i, t in enumerate(tiles):
    out.paste(t, (x, 0)); x += t.width
    if i < len(tiles) - 1:
        out.paste(gap, (x, 0)); x += 12
out.save(OUT)
print(f"-> {OUT}  {out.width}x{out.height}")
print(f"   左={A}  右={B}；范围 = 核心半径的 ±{HALF_U:.0%}，放大 {SCALE}x")
