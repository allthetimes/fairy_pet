"""Fairy 官方立绘几何分析。

产出：
  1. 放大裁切图（供目视确认细节）
  2. 径向色带剖面 —— 找出同心环的精确半径
  3. 逐角度外边界扫描 —— 找出齿轮缺口（"四个角"）的角度位置

用法: python analyze_fairy.py <图片>
"""
import sys
import os
import numpy as np
from PIL import Image

OUT = os.path.dirname(os.path.abspath(__file__))


def save_zoom(im, box, name, scale=3):
    c = im.crop(box)
    c = c.resize((c.width * scale, c.height * scale), Image.NEAREST)
    p = os.path.join(OUT, name)
    c.save(p)
    print(f"  放大图 -> {name}  {c.width}x{c.height}  (原区域 {box})")


def radial_profile(im, cx, cy, rmax, step=1.0, samples=720):
    arr = np.asarray(im).astype(np.float32)
    th = np.linspace(0, 2 * np.pi, samples, endpoint=False)
    ct, st = np.cos(th), np.sin(th)
    out = []
    r = 0.0
    while r <= rmax:
        xs = np.clip((cx + r * ct).round().astype(int), 0, arr.shape[1] - 1)
        ys = np.clip((cy + r * st).round().astype(int), 0, arr.shape[0] - 1)
        px = arr[ys, xs]
        out.append((r, px.mean(axis=0), px.std(axis=0).mean()))
        r += step
    return out


def angular_boundary(im, cx, cy, r_in, r_out, thresh):
    """逐角度向外扫，找最后一个"深蓝"像素的半径 → 得到带缺口的外轮廓。"""
    arr = np.asarray(im).astype(np.float32)
    h, w, _ = arr.shape
    res = []
    for deg in np.arange(0, 360, 0.5):
        th = np.radians(deg)
        ct, st = np.cos(th), np.sin(th)
        last = 0
        for r in np.arange(r_in, r_out, 0.5):
            x = int(round(cx + r * ct)); y = int(round(cy + r * st))
            if not (0 <= x < w and 0 <= y < h):
                break
            R, G, B = arr[y, x]
            lum = 0.299 * R + 0.587 * G + 0.114 * B
            if B > R + 12 and lum < thresh:   # 深蓝圆盘
                last = r
        res.append((deg, last))
    return res


def main():
    path = sys.argv[1]
    im = Image.open(path).convert("RGB")
    W, H = im.size
    print(f"图片 {os.path.basename(path)}  {W}x{H}")

    # 从 2.6 版立绘看，主体近似居中；先用亮度重心定位
    arr = np.asarray(im).astype(np.float32)
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    # 中心近黑，用"最暗区域的质心"来定位圆心
    dark = lum < np.percentile(lum, 8)
    ys, xs = np.where(dark)
    cx, cy = float(xs.mean()), float(ys.mean())
    print(f"估计圆心 ({cx:.1f}, {cy:.1f})")

    # 1) 径向色带剖面
    print("\n--- 径向剖面 (每 2px 采样，标出显著色变) ---")
    prof = radial_profile(im, cx, cy, min(cx, cy, W - cx, H - cy) - 1, step=1.0)
    prev = None
    for r, mean, sd in prof:
        if prev is None:
            prev = mean
            continue
        d = np.abs(mean - prev).sum()
        if d > 26:      # 颜色显著跳变 → 环的边界
            print(f"  r={r:6.1f}  均值RGB=({mean[0]:5.1f},{mean[1]:5.1f},{mean[2]:5.1f})  "
                  f"跳变={d:6.1f}  角度标准差={sd:5.1f}")
        prev = mean
    print("\n  完整剖面（每 8px）:")
    for r, mean, sd in prof[::8]:
        bar = "#" * int(sd / 4)
        print(f"    r={r:6.1f}  ({mean[0]:5.1f},{mean[1]:5.1f},{mean[2]:5.1f})  离散={sd:5.1f} {bar}")

    # 2) 放大裁切
    print("\n--- 放大裁切 ---")
    R = min(cx, cy, W - cx, H - cy)
    save_zoom(im, (int(cx - R * 0.55), int(cy - R * 0.55),
                   int(cx + R * 0.55), int(cy + R * 0.55)), "zoom_center.png", 4)
    save_zoom(im, (int(cx - R), int(cy - R * 0.55),
                   int(cx + R), int(cy + R * 0.55)), "zoom_full.png", 2)

    # 3) 外轮廓（缺口/四角）
    print("\n--- 逐角度外边界（找齿轮缺口） ---")
    thresh = float(np.percentile(lum, 45))
    bnd = angular_boundary(im, cx, cy, R * 0.45, min(cx, cy, W - cx, H - cy), thresh)
    rs = np.array([b for _, b in bnd])
    if rs.max() > 0:
        mx = rs.max()
        print(f"  最大外半径 ≈ {mx:.1f}")
        # 找局部极小的角度 → 缺口位置
        print("  角度采样(r)：", "  ".join(
            f"{int(d)}:{int(r)}" for d, r in bnd[::40]))
        dips = [(d, r) for d, r in bnd if r < mx * 0.93]
        if dips:
            groups, cur = [], [dips[0]]
            for d, r in dips[1:]:
                if d - cur[-1][0] <= 2.5:
                    cur.append((d, r))
                else:
                    groups.append(cur); cur = [(d, r)]
            groups.append(cur)
            print(f"  缺口（外半径明显内凹）共 {len(groups)} 处:")
            for g in groups:
                ds = [d for d, _ in g]
                rr = min(r for _, r in g)
                print(f"    角度 {min(ds):6.1f}° ~ {max(ds):6.1f}°  "
                      f"中心 {(min(ds)+max(ds))/2:6.1f}°  最内凹 r={rr:.1f} "
                      f"(凹深 {mx - rr:.1f}px)")
        else:
            print("  未检测到明显缺口，可能阈值需调整")


if __name__ == "__main__":
    main()
