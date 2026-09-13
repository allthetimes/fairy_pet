"""精确定位 Fairy 圆心 + 量出同心环半径。

思路：真圆心能让"同一半径上各角度的颜色"最一致（径向对称性最好）。
所以对候选圆心做网格搜索，取角度方差之和最小的那个。

用法: python measure.py <图片> [输出前缀]
"""
import sys
import os
import json
import numpy as np
from PIL import Image

OUT = os.path.dirname(os.path.abspath(__file__))


def lum_of(arr):
    """arr 末维是 RGB 即可，支持 (H,W,3) 或 (N,3)。"""
    return 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]


def angular_samples(arr, cx, cy, radii, n_ang=180):
    h, w, _ = arr.shape
    th = np.linspace(0, 2 * np.pi, n_ang, endpoint=False)
    ct, st = np.cos(th), np.sin(th)
    L = lum_of(arr)
    rows = []
    for r in radii:
        xs = np.clip((cx + r * ct).round().astype(int), 0, w - 1)
        ys = np.clip((cy + r * st).round().astype(int), 0, h - 1)
        rows.append(L[ys, xs])
    return np.array(rows)


def find_center(arr, guess, span=30, step=2, radii=None):
    if radii is None:
        radii = np.arange(30, 200, 3)
    best, best_score = guess, None
    # 粗搜
    for cx in range(guess[0] - span, guess[0] + span + 1, step):
        for cy in range(guess[1] - span, guess[1] + span + 1, step):
            s = angular_samples(arr, cx, cy, radii).std(axis=1).sum()
            if best_score is None or s < best_score:
                best_score, best = s, (cx, cy)
    # 细搜
    cx0, cy0 = best
    for cx in np.arange(cx0 - step, cx0 + step + 0.25, 0.5):
        for cy in np.arange(cy0 - step, cy0 + step + 0.25, 0.5):
            s = angular_samples(arr, cx, cy, radii).std(axis=1).sum()
            if s < best_score:
                best_score, best = s, (float(cx), float(cy))
    return best, best_score


def main():
    path = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else "spec"
    im = Image.open(path).convert("RGB")
    arr = np.asarray(im).astype(np.float32)
    W, H = im.size

    # 白色环主导 → 用它的质心当初始猜测
    R, G, B = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    white = (R > 185) & (G > 185) & (B > 195) & (np.abs(B - R) < 45)
    ys, xs = np.where(white)
    guess = (float(xs.mean()), float(ys.mean())) if len(xs) else (W / 2, H / 2)
    print(f"白环质心初猜 ({guess[0]:.1f}, {guess[1]:.1f})   白色像素 {len(xs)}")

    (cx, cy), score = find_center(arr, (int(round(guess[0])), int(round(guess[1]))))
    print(f"径向对称最优圆心 ({cx:.1f}, {cy:.1f})   残差 {score:.0f}")
    print(f"（图像中心是 ({W/2}, {H/2})）")

    # 径向剖面（带角度离散度）
    L = lum_of(arr)
    th = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    ct, st = np.cos(th), np.sin(th)
    rmax = int(min(cx, cy, W - cx, H - cy))
    prof = []
    for r in np.arange(0, rmax, 1.0):
        xs2 = np.clip((cx + r * ct).round().astype(int), 0, W - 1)
        ys2 = np.clip((cy + r * st).round().astype(int), 0, H - 1)
        px = arr[ys2, xs2]
        m, sd = px.mean(axis=0), lum_of(px).std()
        prof.append((r, m, sd))

    print(f"\n=== 径向剖面（亮度角度离散度 sd 突增处 = 环边界） rmax={rmax} ===")
    print(f"{'r':>6} {'R':>6} {'G':>6} {'B':>6} {'sd':>6}  条")
    for r, m, sd in prof:
        if r % 2 == 0:
            bar = "▌" * int(sd / 3)
            mark = "  <== 边界" if sd > 26 else ""
            print(f"{r:6.1f} {m[0]:6.1f} {m[1]:6.1f} {m[2]:6.1f} {sd:6.1f}  {bar}{mark}")

    # 水平剖线（过圆心）
    print(f"\n=== 水平剖线 y={cy:.0f}（只看 R 通道跳变，定位环边界 x） ===")
    row = arr[int(round(cy))]
    prev = row[0]
    edges = []
    for x in range(1, W):
        d = np.abs(row[x] - prev).sum()
        if d > 38:
            edges.append(x)
        prev = row[x]
    print(f"  跳变 x: {edges}")
    print(f"  距圆心 r: {[round(x - cx, 1) for x in edges]}")

    # 垂直剖线
    print(f"\n=== 垂直剖线 x={cx:.0f} ===")
    col = arr[:, int(round(cx))]
    prev = col[0]
    edges_v = []
    for y in range(1, H):
        d = np.abs(col[y] - prev).sum()
        if d > 38:
            edges_v.append(y)
        prev = col[y]
    print(f"  距圆心 r: {[round(y - cy, 1) for y in edges_v]}")

    # 输出 JSON 供后续使用
    spec = {
        "source": os.path.basename(path),
        "image_size": [W, H],
        "center": [round(cx, 1), round(cy, 1)],
        "rmax": rmax,
        "radial": [{"r": round(r, 1), "rgb": [round(v, 1) for v in m], "sd": round(sd, 1)}
                   for r, m, sd in prof],
        "h_edges_r": [round(x - cx, 1) for x in edges],
        "v_edges_r": [round(y - cy, 1) for y in edges_v],
    }
    p = os.path.join(OUT, f"{prefix}_{os.path.splitext(os.path.basename(path))[0]}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    print(f"\n已写出 {os.path.basename(p)}")


if __name__ == "__main__":
    main()
