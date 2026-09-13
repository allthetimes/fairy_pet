# -*- coding: utf-8 -*-
"""高光球 v4 —— 固定窗口 + 紧阈值(排除白环)。

前几版的教训:
  - 全局阈值/DoG 会把整条白环卷进来(native 泛光下白环内缘整圈超阈), 质心被拉回圆心
  - 径向剖面测球外缘时球与白环相连, 分不开
  - 切向弧弦长在球心距未知时无法定界
本版: 用已知基准(高光相对圆心的方位≈54°、距离≈67px)开一个半径 45px 的窗口, 只在该窗口内
      用"窗口内 max-4"的紧阈值取像素 —— 白环亮部比球低 4~8 灰阶, 恰好被挡在外面。
输出逐帧: 质心距 / 球像素的 r 分位(P5=球内缘) / 等效半径 / 像素数

用法: python scripts/_glint_v4.py --video <f> --align <json> [--ss 0] [--dur 12] [--fps 120]
"""
import argparse
import json
import pathlib
import subprocess
import sys

import numpy as np

ROOT = pathlib.Path(r"D:\work\fairy_pet")
sys.path.insert(0, str(ROOT / "scripts"))
from video_tool import ffmpeg_exe        # noqa: E402

BASE_DEG = 53.8        # 高光相对圆心的方位(0°=右, 90°=下)
BASE_DIST = 0.310      # 高光中心距 (×R)
DEEP_DIRS = [200.0, 250.0, 300.0]
WIN = 45.0             # 窗口半径(px)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--align", required=True)
    ap.add_argument("--ss", type=float, default=0.0)
    ap.add_argument("--dur", type=float, default=12.0)
    ap.add_argument("--fps", type=float, default=120.0)
    ap.add_argument("--thr-drop", type=float, default=4.0, help="阈值 = 窗口内最亮 - thr-drop")
    ap.add_argument("--out", default=str(ROOT / "dev" / "glint_v4.json"))
    a = ap.parse_args()

    al = json.load(open(a.align, encoding="utf-8"))
    R = al["R_px"]
    side = int(R * 2.9)
    x0, y0 = int(round(al["cx"] - side / 2)), int(round(al["cy"] - side / 2))
    C = side / 2
    t = np.radians(BASE_DEG)
    gcx, gcy = BASE_DIST * R * np.cos(t), BASE_DIST * R * np.sin(t)

    ys, xs = np.mgrid[0:side, 0:side].astype(np.float32)
    dx, dy = xs - (C + gcx), ys - (C + gcy)
    win = np.hypot(dx, dy) < WIN
    rr = np.hypot(xs - C, ys - C)

    args = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", str(a.ss), "-i", a.video,
            "-t", str(a.dur), "-vf", f"crop={side}:{side}:{x0}:{y0},fps={a.fps}",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    nb = side * side * 3

    rec, n = [], 0
    dbg = None
    while True:
        buf = p.stdout.read(nb)
        if len(buf) < nb:
            break
        im = np.frombuffer(buf, np.uint8).reshape(side, side, 3).astype(np.float32)
        L = 0.299 * im[:, :, 0] + 0.587 * im[:, :, 1] + 0.114 * im[:, :, 2]

        Lw = np.where(win, L, -1)
        mx = float(Lw.max())
        gm = win & (L > mx - a.thr_drop)
        cnt = int(gm.sum())
        if cnt < 20:
            rec.append(None); n += 1; continue
        gx, gy = float(xs[gm].mean()), float(ys[gm].mean())
        dist = float(np.hypot(gx - C, gy - C))
        r_g = float(np.sqrt(cnt / np.pi))
        rg = rr[gm]
        rp5, rp50, rp95 = [float(np.percentile(rg, q)) for q in (5, 50, 95)]

        # 深眼边缘(避开高光的方向)
        deps = []
        for d in DEEP_DIRS:
            th = np.radians(d)
            rsr = np.arange(0.05 * R, 0.35 * R, 0.25)
            xx = np.clip(C + rsr * np.cos(th), 0, side - 1)
            yy = np.clip(C + rsr * np.sin(th), 0, side - 1)
            xi = np.floor(xx).astype(int); yi = np.floor(yy).astype(int)
            fx, fy = xx - xi, yy - yi
            v = (L[yi, xi] * (1 - fx) * (1 - fy) + L[yi, xi + 1] * fx * (1 - fy) +
                 L[yi + 1, xi] * (1 - fx) * fy + L[yi + 1, xi + 1] * fx * fy)
            v = np.convolve(v, np.ones(9) / 9, mode="same")
            deps.append(float(rsr[int(np.argmax(np.gradient(v)))]))
        r_deep = float(np.median(deps))

        rec.append((dist, r_g, r_deep, rp5, cnt, mx, rp50, rp95))
        if dbg is None:
            dbg = (im.copy(), gm.copy(), mx, (gx, gy), r_deep)
        n += 1
    p.stdout.close()
    p.wait()

    good = [r for r in rec if r]
    print(f"{pathlib.Path(a.video).name}  采样 {n}, 有效 {len(good)}   窗口 R={WIN}px 阈值=max-{a.thr_drop}")
    A = np.array(good)
    fps = a.fps
    ts = np.arange(len(good)) / fps
    dist, r_g, r_deep, rp5, cnt, mx, rp50, rp95 = A.T

    def stat(name, v):
        print(f"  {name:<14} 均值 {v.mean():8.3f}  std {v.std():6.3f}  "
              f"范围 {v.min():8.3f} ~ {v.max():8.3f}  峰谷 {(v.max()-v.min()):7.3f}"
              f" ({(v.max()-v.min())/abs(v.mean())*100:5.2f}%)")
    print("\n[序列统计] (px)")
    stat("球心距 dist", dist)
    stat("球等效半径", r_g)
    stat("球内缘 P5", rp5)
    stat("球像素中位r", rp50)
    stat("球外缘 P95", rp95)
    stat("深眼半径", r_deep)
    stat("球像素数", cnt)
    print(f"  球内缘 P5 vs 深眼边缘: {rp5.mean():.2f} vs {r_deep.mean():.2f}  "
          f"→ 球内缘在深眼{'内' if rp5.mean() < r_deep.mean() else '外'}侧 "
          f"{abs(rp5.mean()-r_deep.mean()):.2f}px")
    print(f"  球内缘跨过深眼边缘的帧: {int((rp5 < r_deep).sum())}/{len(rp5)} "
          f"({(rp5 < r_deep).mean()*100:.1f}%)")
    print(f"  球心距分位: " + "  ".join(f"P{q}={np.percentile(dist, q):.1f}" for q in (0, 5, 50, 95, 100)))
    print(f"  球半径分位: " + "  ".join(f"P{q}={np.percentile(r_g, q):.2f}" for q in (0, 5, 50, 95, 100)))

    def fitfreq(y, fmin=0.9, fmax=1.6):
        best = None
        for f in np.arange(fmin, fmax, 0.0002):
            M = np.column_stack([np.ones_like(ts), np.cos(2 * np.pi * f * ts), np.sin(2 * np.pi * f * ts)])
            c, *_ = np.linalg.lstsq(M, y, rcond=None)
            rsd = float((y - M @ c).std())
            if best is None or rsd < best[0]:
                best = (rsd, f, float(np.hypot(c[1], c[2])), float(np.arctan2(c[2], c[1])))
        return best
    print("\n[呼吸频率处拟合]")
    fr = {}
    for name, v in [("球心距", dist), ("球半径", r_g), ("球内缘", rp5), ("深眼半径", r_deep), ("像素数", cnt)]:
        rsd, f, amp, ph = fitfreq(v)
        fr[name] = (f, amp, ph, rsd)
        print(f"  {name:<10} f={f:.4f}Hz  振幅 {amp:7.3f} ({amp/abs(v.mean())*100:5.2f}%)  "
              f"相位 {np.degrees(ph):7.1f}°  残差 {rsd:6.3f}  信噪 {amp/(rsd+1e-9):5.2f}")

    out = {"video": pathlib.Path(a.video).name, "frames": len(good), "fps": fps, "R_px": R,
           "window_px": WIN, "thr_drop": a.thr_drop,
           "stats": {k: {"mean": round(float(v.mean()), 3), "std": round(float(v.std()), 3),
                         "min": round(float(v.min()), 3), "max": round(float(v.max()), 3)}
                     for k, v in [("dist", dist), ("r_glint", r_g), ("r_inner_p5", rp5),
                                  ("r_outer_p95", rp95), ("r_deep", r_deep), ("px_count", cnt)]},
           "inner_cross_ratio": round(float((rp5 < r_deep).mean()), 4),
           "fits": {k: {"f": round(v[0], 5), "amp_px": round(v[1], 3), "phase_deg": round(np.degrees(v[2]), 1),
                        "resid": round(v[3], 3), "snr": round(v[1] / (v[3] + 1e-9), 2)}
                    for k, v in fr.items()},
           "series": [[round(float(x), 3) for x in row[:6]] for row in A.tolist()]}
    pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {a.out}")

    from PIL import Image, ImageDraw
    im0, gm0, mx0, (gxx, gyy), rd0 = dbg
    v = im0.copy(); v[gm0] = [255, 40, 40]
    img = Image.fromarray(v.astype(np.uint8)).resize((side * 2, side * 2), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    for rr_, col in [(rd0, (0, 255, 120)), (BASE_DIST * R, (255, 200, 0))]:
        d.ellipse([2 * (C - rr_), 2 * (C - rr_), 2 * (C + rr_), 2 * (C + rr_)], outline=col, width=2)
    d.text((8, 8), f"mask {int(gm0.sum())}px  max {mx0:.0f}  deep {rd0:.1f}  "
                   f"glintdist {np.hypot(gxx-C, gyy-C):.1f}", fill=(255, 240, 120))
    img.save(ROOT / "dev" / "glint_mask_check.png")
    print("掩膜核对图 -> dev/glint_mask_check.png")


main()
