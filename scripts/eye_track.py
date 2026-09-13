"""对抽出来的帧序列逐帧量化 Fairy 的"眼球"状态。

思路：Fairy 是径向对称图形，先用「角度方差最小」定位每帧的圆心与外径，
再在归一化半径上量三件事：
  1. 瞳孔（深色区）的等效半径 —— 瞳孔缩张
  2. 白色高光球的质心偏移与等效半径 —— 高光/眼球位移
  3. 若干固定半径上的平均色 —— 判断是否闭眼/整体状态切换

用法:
  python eye_track.py <帧目录> [--box x,y,w,h] [--out 前缀] [--strip]
"""
import argparse
import glob
import os

import numpy as np
from PIL import Image, ImageDraw


def lum(a):
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def find_center(L, guess, span=40, step=4, radii=None):
    if radii is None:
        radii = np.arange(30, 190, 5)
    H, W = L.shape
    th = np.linspace(0, 2 * np.pi, 120, endpoint=False)
    ct, st = np.cos(th), np.sin(th)

    def score(cx, cy):
        xs = np.clip(np.round(cx + np.outer(radii, ct)).astype(int), 0, W - 1)
        ys = np.clip(np.round(cy + np.outer(radii, st)).astype(int), 0, H - 1)
        return L[ys, xs].std(axis=1).sum()

    best, bs = guess, None
    for cx in range(max(0, guess[0] - span), min(W, guess[0] + span + 1), step):
        for cy in range(max(0, guess[1] - span), min(H, guess[1] + span + 1), step):
            s = score(cx, cy)
            if bs is None or s < bs:
                bs, best = s, (cx, cy)
    cx0, cy0 = best
    for cx in np.arange(cx0 - step, cx0 + step + .5, 1.0):
        for cy in np.arange(cy0 - step, cy0 + step + .5, 1.0):
            s = score(cx, cy)
            if s < bs:
                bs, best = s, (cx, cy)
    return best, bs


def outer_radius(L, cx, cy):
    """用亮度梯度最大处的半径作外缘（环形轮廓最亮的一跳）。"""
    H, W = L.shape
    rmax = int(min(cx, cy, W - cx, H - cy)) - 2
    th = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    ct, st = np.cos(th), np.sin(th)
    prof = []
    for r in np.arange(20, rmax, 1.0):
        xs = np.clip(np.round(cx + r * ct).astype(int), 0, W - 1)
        ys = np.clip(np.round(cy + r * st).astype(int), 0, H - 1)
        prof.append(L[ys, xs].mean())
    prof = np.array(prof)
    # 外缘 = 从外向内第一个出现"亮度明显高于外侧"的半径
    outer = L[max(0, cy - 3):cy + 4, max(0, cx - 3):cx + 4].mean()
    idx = np.where(prof > outer * 0.72)[0]
    return float(20 + idx.max()) if len(idx) else float(rmax)


def measure(rgb, cx, cy, R):
    H, W, _ = rgb.shape
    L = lum(rgb)
    yy, xx = np.mgrid[0:H, 0:W]
    rr = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    # 1) 瞳孔：核心区内的深色像素
    core = rr < R * 0.55
    dark = core & (L < 90)
    pupil_r = np.sqrt(dark.sum() / np.pi) if dark.sum() > 20 else 0.0
    # 2) 高光球：核心区内的高亮像素
    bright = core & (L > 175) & (rgb[:, :, 2] > 200)
    if bright.sum() > 15:
        ys, xs = np.where(bright)
        gdx, gdy = xs.mean() - cx, ys.mean() - cy
        gr = np.sqrt(bright.sum() / np.pi)
    else:
        gdx = gdy = gr = 0.0
    # 3) 固定半径上的平均色（归一化）
    out = {}
    th = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    for u in (0.10, 0.18, 0.25, 0.35, 0.45, 0.60):
        xs = np.clip(np.round(cx + u * R * np.cos(th)).astype(int), 0, W - 1)
        ys = np.clip(np.round(cy + u * R * np.sin(th)).astype(int), 0, H - 1)
        out[u] = rgb[ys, xs].mean(axis=0)
    return dict(pupil_r=pupil_r, pupil_u=pupil_r / R,
                glint_dx=gdx / R, glint_dy=gdy / R, glint_r=gr, glint_u=gr / R,
                colors=out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames")
    ap.add_argument("--box", default=None, help="x,y,w,h 先裁到 Fairy 头像区域")
    ap.add_argument("--out", default=None)
    ap.add_argument("--strip", action="store_true")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.frames, "f_*.png")))
    if not files:
        print("没找到帧", a.frames); return
    print(f"共 {len(files)} 帧")

    box = None
    if a.box:
        box = tuple(int(v) for v in a.box.split(","))

    rows = []
    tiles = []
    for i, f in enumerate(files):
        im = Image.open(f).convert("RGB")
        if box:
            im = im.crop((box[0], box[1], box[0] + box[2], box[1] + box[3]))
        rgb = np.asarray(im).astype(np.float32)
        L = lum(rgb)
        h, w = L.shape
        # 初始猜测：最暗区的质心（瞳孔）
        dk = L < np.percentile(L, 12)
        ys, xs = np.where(dk)
        guess = (int(xs.mean()), int(ys.mean())) if len(xs) else (w // 2, h // 2)
        (cx, cy), _ = find_center(L, guess)
        R = outer_radius(L, cx, cy)
        m = measure(rgb, cx, cy, R)
        m["frame"] = os.path.basename(f)
        m["cx"], m["cy"], m["R"] = cx, cy, R
        rows.append(m)
        if a.strip:
            tiles.append((im.copy(), cx, cy, R))

    # 输出
    prefix = a.out or os.path.join(a.frames, "eyetrack")
    print(f"\n{'帧':>10} {'R':>6} {'瞳孔u':>7} {'高光dx':>8} {'高光dy':>8} {'高光u':>7}   u=0.10 处颜色")
    for m in rows:
        c10 = m["colors"][0.10]
        print(f"{m['frame']:>10} {m['R']:6.1f} {m['pupil_u']:7.3f} "
              f"{m['glint_dx']:+8.3f} {m['glint_dy']:+8.3f} {m['glint_u']:7.3f}   "
              f"#{int(c10[0]):02X}{int(c10[1]):02X}{int(c10[2]):02X}")

    import csv
    with open(prefix + ".csv", "w", newline="", encoding="utf-8") as fp:
        wtr = csv.writer(fp)
        wtr.writerow(["frame", "cx", "cy", "R", "pupil_u", "glint_dx", "glint_dy", "glint_u"])
        for m in rows:
            wtr.writerow([m["frame"], m["cx"], m["cy"], m["R"],
                          f"{m['pupil_u']:.4f}", f"{m['glint_dx']:.4f}",
                          f"{m['glint_dy']:.4f}", f"{m['glint_u']:.4f}"])
    print(f"\n明细 -> {prefix}.csv")

    # 变化幅度汇总：一眼看出"到底哪里在变"
    arr = {k: np.array([m[k] for m in rows]) for k in ("pupil_u", "glint_dx", "glint_dy", "glint_u", "R")}
    print("\n=== 各指标的变化幅度（max-min，已归一化到核心半径）===")
    for k, v in arr.items():
        print(f"  {k:10s} 范围 {v.min():+.4f} ~ {v.max():+.4f}   极差 {v.max()-v.min():.4f}")
    print("\n极差最大的那项，就是动画真正在动的地方。")

    if a.strip and tiles:
        cols = min(8, len(tiles))
        tw, th = 200, 200
        rowsn = (len(tiles) + cols - 1) // cols
        sheet = Image.new("RGB", (tw * cols, th * rowsn), (10, 14, 24))
        d = ImageDraw.Draw(sheet)
        for i, (im, cx, cy, R) in enumerate(tiles):
            half = int(R * 0.55)
            c = im.crop((max(0, cx - half), max(0, cy - half),
                         min(im.width, cx + half), min(im.height, cy + half)))
            c = c.resize((tw, th), Image.LANCZOS)
            x, y = (i % cols) * tw, (i // cols) * th
            sheet.paste(c, (x, y))
            d.text((x + 4, y + 4), os.path.basename(tiles[i][0].filename if hasattr(tiles[i][0], 'filename') else f"f{i:05d}"),
                   fill=(255, 210, 110))
        p = prefix + "_eyestrip.png"
        sheet.save(p)
        print(f"眼球区拼版 -> {p}")


if __name__ == "__main__":
    main()
