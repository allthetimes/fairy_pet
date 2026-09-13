"""把官方立绘和代码复刻放在同一套算法下测量，输出对照表。

数值全部以"外圈蓝外缘半径"归一化，这样尺度不同也能直接比。

用法: python compare_spec.py <官方图> <我的裸渲染图>
"""
import sys
import numpy as np
from PIL import Image

# ---------- 通用工具 ----------

def radial_color_profile(arr, cx, cy, rmax, n_ang=720):
    H, W, _ = arr.shape
    th = np.linspace(0, 2 * np.pi, n_ang, endpoint=False)
    ct, st = np.cos(th), np.sin(th)
    rows = []
    for r in np.arange(0, rmax, 0.25):
        xs = np.clip((cx + r * ct).round().astype(int), 0, W - 1)
        ys = np.clip((cy + r * st).round().astype(int), 0, H - 1)
        rows.append(arr[ys, xs].mean(axis=0))
    return np.arange(0, rmax, 0.25), np.array(rows)


def find_color_edges(rr, prof, tol=26):
    """颜色显著跳变处的半径。"""
    d = np.abs(np.diff(prof, axis=0)).sum(axis=1)
    edges = []
    i = 0
    while i < len(d):
        if d[i] > tol:
            j = i
            peak = d[i]
            while j + 1 < len(d) and d[j + 1] > tol:
                j += 1
                peak = max(peak, d[j])
            edges.append((rr[i] + rr[j]) / 2)
            i = j + 1
        else:
            i += 1
    return edges


def notch_angles(arr, cx, cy, r_in_lo, r_in_hi, blue_test, step=0.5):
    """逐角度找高饱和蓝的内边界；内边界显著外推处即缺口。"""
    H, W, _ = arr.shape
    degs = np.arange(0, 360, step)
    r_in = np.full(len(degs), np.nan)
    for k, d in enumerate(degs):
        cs, sn = np.cos(np.radians(d)), np.sin(np.radians(d))
        for r in np.arange(r_in_lo, r_in_hi, 0.25):
            x = int(round(cx + r * cs)); y = int(round(cy + r * sn))
            if 0 <= x < W and 0 <= y < H and blue_test(arr[y, x]):
                r_in[k] = r
                break
    return degs, r_in


# ---------- 测量官方立绘（RGB，靠颜色分层） ----------

def measure_reference(path):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float32)
    H, W, _ = a.shape
    cx, cy = 257.5, 254.0
    rr, prof = radial_color_profile(a, cx, cy, 260)
    edges = find_color_edges(rr, prof, tol=24)
    out = {"中心": (cx, cy), "环边界r": edges}

    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    blue = lambda px: px[2] > 190 and px[1] < 100 and px[0] < 80 and (px[2] - px[0]) > 125
    degs, r_in = notch_angles(a, cx, cy, 150, 224, blue)
    med = np.nanmedian(r_in)
    mx = np.nanmax(r_in)
    thr = med + (mx - med) * 0.35
    deep = ~np.isnan(r_in) & (r_in > thr)
    groups, cur = [], None
    for d, f in zip(degs, deep):
        if f and cur is None: cur = [d, d]
        elif f: cur[1] = d
        elif cur is not None: groups.append(cur); cur = None
    if cur: groups.append(cur)
    if len(groups) > 1 and groups[0][0] <= 0.5 and groups[-1][1] >= 359:
        groups[0][0] = groups[-1][0] - 360; groups.pop()
    groups = [g for g in groups if g[1] - g[0] > 3]     # 丢掉噪点
    out["缺口中心角"] = [round(((g[0] + g[1]) / 2) % 360, 1) for g in groups]
    out["缺口楔尖r"] = round(mx, 1)
    out["蓝色内边界中位r"] = round(med, 1)
    out["外圈蓝外缘r"] = round(np.nanmax(rr[np.abs(np.diff(prof, axis=0)).sum(axis=1) > 0]) if False else 212.0, 1)
    return out


# ---------- 测量我的裸渲染（RGBA，靠 alpha 定形状 + 颜色分层） ----------

def measure_mine(path):
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im).astype(np.float32)
    H, W, _ = a.shape
    alpha = a[:, :, 3]
    ys, xs = np.where(alpha > 128)
    cx, cy = xs.mean(), ys.mean()
    R_outer = np.sqrt((alpha > 128).sum() / np.pi)      # 等效半径（含描边）
    rgb = a[:, :, :3]
    rr, prof = radial_color_profile(rgb, cx, cy, R_outer + 6)
    edges = find_color_edges(rr, prof, tol=24)
    out = {"中心": (round(cx, 1), round(cy, 1)), "环边界r": edges, "外缘等效r": round(R_outer, 1)}

    blue = lambda px: px[2] > 190 and px[1] < 100 and px[0] < 80 and (px[2] - px[0]) > 125
    degs, r_in = notch_angles(rgb, cx, cy, R_outer * 0.60, R_outer * 1.02, blue)
    med = np.nanmedian(r_in); mx = np.nanmax(r_in)
    thr = med + (mx - med) * 0.35
    deep = ~np.isnan(r_in) & (r_in > thr)
    groups, cur = [], None
    for d, f in zip(degs, deep):
        if f and cur is None: cur = [d, d]
        elif f: cur[1] = d
        elif cur is not None: groups.append(cur); cur = None
    if cur: groups.append(cur)
    if len(groups) > 1 and groups[0][0] <= 0.5 and groups[-1][1] >= 359:
        groups[0][0] = groups[-1][0] - 360; groups.pop()
    groups = [g for g in groups if g[1] - g[0] > 3]
    out["缺口中心角"] = [round(((g[0] + g[1]) / 2) % 360, 1) for g in groups]
    out["缺口楔尖r"] = round(mx, 1)
    out["蓝色内边界中位r"] = round(med, 1)
    return out


if __name__ == "__main__":
    ref = measure_reference(sys.argv[1])
    mine = measure_mine(sys.argv[2])

    print("=" * 74)
    print("官方立绘（520x520，外圈蓝外缘 r=212.5）")
    for k, v in ref.items():
        print(f"  {k}: {v}")
    print("\n代码复刻裸渲染")
    for k, v in mine.items():
        print(f"  {k}: {v}")

    # 归一化对比
    R_ref = 212.5
    R_mine = mine["外缘等效r"]
    print("\n" + "=" * 74)
    print(f"归一化对照（各自除以自己的外缘半径：官方 {R_ref}，复刻 {R_mine:.1f}）")
    print(f"{'层边界':>28} {'官方 u':>9} {'复刻 u':>9} {'差':>8}")
    ref_edges = [e for e in ref["环边界r"] if 30 < e < 230]
    mine_edges = [e for e in mine["环边界r"] if 30 < e < 230]
    for e in ref_edges:
        u = e / R_ref
        near = min(mine_edges, key=lambda x: abs(x / R_mine - u)) if mine_edges else None
        um = near / R_mine if near else float("nan")
        print(f"{'r=' + str(round(e, 1)):>28} {u:9.3f} {um:9.3f} {um - u:+8.3f}")
    print("\n缺口：官方", ref["缺口中心角"], " 复刻", mine["缺口中心角"])
    print("楔尖归一化：官方", round(ref["缺口楔尖r"] / R_ref, 3),
          " 复刻", round(mine["缺口楔尖r"] / R_mine, 3))
    print("蓝内边界归一化：官方", round(ref["蓝色内边界中位r"] / R_ref, 3),
          " 复刻", round(mine["蓝色内边界中位r"] / R_mine, 3))
