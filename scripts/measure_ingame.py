"""从游戏内渲染里精确量 Fairy 头像：拟合外圈白细边定圆心/外径，再量各层。

比质心法可靠：外圈那条细白边是完整的圆，直接最小二乘拟合即可；
背景梯度、画面高光都影响不到它的圆心。

用法: python measure_ingame.py <图> [--bbox x,y,w,h] [--bright 225]
"""
import argparse
import numpy as np
from PIL import Image


def fit_circle(xs, ys):
    """最小二乘拟合圆: x^2+y^2 + D x + E y + F = 0"""
    A = np.c_[xs, ys, np.ones(len(xs))]
    b = -(xs ** 2 + ys ** 2)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    D, E, F = sol
    cx, cy = -D / 2, -E / 2
    r = np.sqrt(cx ** 2 + cy ** 2 - F)
    return cx, cy, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("img")
    ap.add_argument("--bbox", default=None)
    ap.add_argument("--bright", type=float, default=225)
    a = ap.parse_args()

    im = Image.open(a.img).convert("RGB")
    if a.bbox:
        x, y, w, h = [int(v) for v in a.bbox.split(",")]
        im = im.crop((x, y, x + w, y + h))
    A = np.asarray(im).astype(np.float32)
    H, W, _ = A.shape
    L = 0.299 * A[:, :, 0] + 0.587 * A[:, :, 1] + 0.114 * A[:, :, 2]
    print(f"图 {W}x{H}")

    # 粗定：亮区质心附近
    m = L > a.bright
    if m.sum() < 100:
        print("亮像素太少，降低 --bright"); return
    gx, gy = np.where(m)[1].mean(), np.where(m)[0].mean()

    # 只取距粗定心 0.75~1.25 倍中位半径的亮像素参与拟合（即外圈那条细白边）
    yy, xx = np.mgrid[0:H, 0:W]
    d0 = np.sqrt((xx - gx) ** 2 + (yy - gy) ** 2)
    r0 = np.median(d0[m])
    sel = m & (d0 > r0 * 0.88) & (d0 < r0 * 1.06)
    # 迭代两次去掉离群点
    xs, ys = xx[sel], yy[sel]
    for _ in range(3):
        cx, cy, R = fit_circle(xs.astype(float), ys.astype(float))
        dd = np.abs(np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) - R)
        keep = dd < max(2.0, R * 0.03)
        xs, ys = xs[keep], ys[keep]
    print(f"拟合外圈白边: 圆心 ({cx:.2f}, {cy:.2f})  半径 {R:.2f}  参与点 {len(xs)}")

    # 径向剖面
    n = 1440
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    cs, sn = np.cos(th), np.sin(th)
    rmax = int(R * 1.25)
    rr = np.arange(2, rmax, 0.5)
    prof = np.empty(len(rr))
    for i, r in enumerate(rr):
        xs2 = np.clip(np.round(cx + r * cs).astype(int), 0, W - 1)
        ys2 = np.clip(np.round(cy + r * sn).astype(int), 0, H - 1)
        prof[i] = L[ys2, xs2].mean()

    print("\n=== 归一化径向剖面 u = r / R_out（R_out = 外圈白边半径）===")
    print(f"{'u':>6} {'r':>7} {'亮度':>7}")
    for i in range(0, len(rr), 8):
        print(f"{rr[i]/R:6.3f} {rr[i]:7.1f} {prof[i]:7.1f}")

    # 自动找层边界：梯度极大
    g = np.abs(np.diff(prof))
    idx = np.where(g > np.percentile(g, 92))[0]
    # 归并相邻
    groups, cur = [], [idx[0]]
    for k in idx[1:]:
        if k - cur[-1] <= 3:
            cur.append(k)
        else:
            groups.append(cur); cur = [k]
    groups.append(cur)
    print(f"\n=== 检测到的层边界（u = r/R，R={R:.1f}）===")
    for gp in groups:
        r = rr[int(np.mean(gp))]
        if r < R * 1.02:
            print(f"  u = {r/R:.4f}   r = {r:6.1f}px")


if __name__ == "__main__":
    main()
