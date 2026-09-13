# -*- coding: utf-8 -*-
"""原版各圆直径实测 v2: 呼吸周期内的均值 / 最大 / 最小直径 + 真实振幅。

源素材: dev/20260913-130732.mp4 (1920x1080, 60fps, 12.03s)
口径与 v1 的区别:
  1. 深眼外缘改用**颜色掩膜**(逐角度找"深蓝 L<thr"的最外半径 → 取中位数),
     不用亮度梯度极值 —— 深眼与蓝瞳之间隔着一条白描边, 梯度法会在描边两侧来回跳,
     这正是旧测量深眼 corr=0.407 的原因
  2. 其余环仍用径向平均剖面的梯度极值(与旧口径一致)
  3. 振幅不再用 raw max-min(被噪声放大), 改为**正弦最小二乘拟合**(周期先扫描定准),
     得到 A0(均值) ± amp(真实呼吸幅度) → 最大/最小直径 = 2(A0±amp)
  4. 同时给出 raw 极值与拟合残差 std, 便于判断信噪比

单位: px(原生) / u(相对外圈) / SVG 单位(外圈 u=1.0 ↔ 100, 即 svg_r = u*100)

用法: python scripts/_measure_diameters.py [--dur 9] [--fps 60]
"""
import argparse
import json
import pathlib
import subprocess
import sys

import numpy as np

SCRIPTS = pathlib.Path(__file__).parent
sys.path.insert(0, str(SCRIPTS))
from video_tool import ffmpeg_exe                     # noqa: E402

ROOT = pathlib.Path(r"D:\work\fairy_pet")
VIDEO = ROOT / "dev" / "20260913-130732.mp4"
ALIGN = json.load(open(ROOT / "dev" / "align_data.json", encoding="utf-8"))
OUT = ROOT / "dev" / "ring_diameters.json"

N_ANG, STEP = 360, 0.5

# 环边界搜索区间(u) / 梯度方向: + 亮度上升沿, - 亮度下降沿, BR 蓝-红差下降沿
RINGS = [
    ("蓝瞳外缘",   0.24, 0.38, "BR"),
    ("灰紫蓝外缘", 0.38, 0.52, "+"),
    ("白环外缘",   0.56, 0.72, "-"),
    ("靛蓝外缘",   0.70, 0.86, "BR"),
    ("外圈蓝外缘", 0.90, 1.02, "-"),
]
ORDER = ["深眼外缘"] + [r[0] for r in RINGS]


def stream_frames(video, crop, fps, dur, start=0.0):
    x, y, w, h = crop
    args = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error"]
    if start:
        args += ["-ss", str(start)]
    args += ["-i", str(video)]
    if dur:
        args += ["-t", str(dur)]
    args += ["-vf", f"crop={w}:{h}:{x}:{y},fps={fps}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    nb, i = w * h * 3, 0
    while True:
        buf = p.stdout.read(nb)
        if len(buf) < nb:
            break
        yield i, np.frombuffer(buf, np.uint8).reshape(h, w, 3).astype(np.float32)
        i += 1
    p.stdout.close()
    err = p.stderr.read().decode("utf-8", "replace")
    p.wait()
    if i == 0 and err:
        print("ffmpeg 错误:", err[-800:])


def profile2d(im, cxl, cyl, rmax):
    """返回 (rs, prof[n_r, n_ang, 3]) 亚像素双线性径向剖面"""
    H, W, _ = im.shape
    ang = np.linspace(0, 2 * np.pi, N_ANG, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    rs = np.arange(0, rmax, STEP)
    prof = np.zeros((len(rs), N_ANG, 3), dtype=np.float32)
    for i, r in enumerate(rs):
        x = cxl + r * ca
        y = cyl + r * sa
        xi = np.clip(np.floor(x).astype(int), 0, W - 2)
        yi = np.clip(np.floor(y).astype(int), 0, H - 2)
        fx = np.clip(x - xi, 0, 1)[:, None]
        fy = np.clip(y - yi, 0, 1)[:, None]
        prof[i] = (im[yi, xi] * (1 - fx) * (1 - fy) + im[yi, xi + 1] * fx * (1 - fy) +
                   im[yi + 1, xi] * (1 - fx) * fy + im[yi + 1, xi + 1] * fx * fy)
    return rs, prof


def smooth(x, k=5):
    return np.convolve(x, np.ones(k) / k, mode="same")


def deep_edge(rs, prof, R):
    """深眼外缘: 逐角度找'深蓝'区域的最外半径, 取中位数(抗高光/离群)。
    thr = (深蓝本体亮度 + 蓝瞳本体亮度)/2, 每帧自适应。"""
    L2 = 0.299 * prof[:, :, 0] + 0.587 * prof[:, :, 1] + 0.114 * prof[:, :, 2]   # [n_r, n_ang]
    u = rs / R
    l_deep = np.median(L2[(u > 0.04) & (u < 0.12), :])
    l_iris = np.median(L2[(u > 0.24) & (u < 0.27), :])
    if not (l_iris - l_deep > 12):
        return np.nan
    thr = (l_deep + l_iris) / 2.0
    deep = L2 < thr
    m = (u > 0.08) & (u < 0.34)
    sub, us = deep[m, :], u[m]
    # 从内向外: 每角度取最后一个 True 的 u (即深蓝区外缘)
    idx = np.where(sub[::-1, :].any(axis=0),
                   len(us) - 1 - np.argmax(sub[::-1, :], axis=0), -1)
    vals = np.where(idx < 0, np.nan, us[np.clip(idx, 0, len(us) - 1)])
    return float(np.nanmedian(vals))


def edge_in(u, sig, lo, hi, mode):
    m = (u >= lo) & (u <= hi)
    if not m.any():
        return np.nan
    g = sig[m] * (1 if mode == "+" else -1)
    return float(u[m][int(np.argmax(g))])


def fit_sine(ts, y, T):
    w = 2 * np.pi / T
    M = np.column_stack([np.ones_like(ts), np.cos(w * ts), np.sin(w * ts)])
    c, *_ = np.linalg.lstsq(M, y, rcond=None)
    resid = y - M @ c
    amp = float(np.hypot(c[1], c[2]))
    ph = float(np.arctan2(c[2], c[1]))          # 相位(rad), 越靠前=越早到达峰
    return float(c[0]), amp, ph, float(resid.std())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dur", type=float, default=9.0)
    ap.add_argument("--fps", type=float, default=60.0)
    ap.add_argument("--video", default=str(VIDEO))
    ap.add_argument("--align", default=str(ROOT / "dev" / "align_data.json"))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--ss", type=float, default=0.0)
    a = ap.parse_args()

    align = json.load(open(a.align, encoding="utf-8"))
    video = pathlib.Path(a.video)
    out_path = pathlib.Path(a.out)
    cx, cy, R = align["cx"], align["cy"], align["R_px"]
    T_meas = float(align.get("T_meas") or align.get("period_s") or 0.8584)
    side = 620
    x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    print(f"素材 {video.name}  圆心=({cx:.2f},{cy:.2f})  外圈 R={R:.2f}px  抽帧 {a.dur}s @ {a.fps}fps\n")

    series = {k: [] for k in ORDER}
    ts = []
    for idx, im in stream_frames(video, (x0, y0, side, side), a.fps, a.dur, a.ss):
        rs, prof = profile2d(im, side / 2, side / 2, R * 1.06)
        L = 0.299 * prof[:, :, 0] + 0.587 * prof[:, :, 1] + 0.114 * prof[:, :, 2]
        Lm = L.mean(axis=1)
        BRm = (prof[:, :, 2] - prof[:, :, 0]).mean(axis=1)
        Ls, BRs = smooth(Lm, 5), smooth(BRm, 5)
        dL, dBR = np.gradient(Ls), np.gradient(BRs)
        u = rs / R
        series["深眼外缘"].append(deep_edge(rs, prof, R))
        for name, lo, hi, mode in RINGS:
            sig = dBR if mode == "BR" else dL
            series[name].append(edge_in(u, sig, lo, hi, "+" if mode == "+" else "-"))
        ts.append(idx / a.fps)
    ts = np.array(ts)
    n = len(ts)
    print(f"采样 {n} 帧, 覆盖 {ts[-1]:.2f}s\n")

    # ---- 周期精定: 用信噪比最高的白环扫描 T ----
    yw = np.array(series["白环外缘"], dtype=float)
    m = ~np.isnan(yw)
    cands = []
    for T in np.arange(0.80, 0.95, 0.0002):
        try:
            _, amp, _, rsd = fit_sine(ts[m], yw[m], T)
        except Exception:
            continue
        cands.append((rsd, T, amp))
    cands.sort()
    T_best = cands[0][1]
    print(f"周期精定(白环拟合残差最小): T={T_best:.4f}s  "
          f"(对齐文件记录 {T_meas}s, 差 {(T_best - T_meas) * 1000:+.1f}ms)\n")

    out = {"video": video.name, "fps": a.fps, "frames": n, "duration_s": round(float(ts[-1]), 2),
           "period_s": round(float(T_best), 4), "R_px": R, "cx": cx, "cy": cy,
           "unit": "svg_r = u*100, 外圈=100", "rings": {}}

    hdr = (f"{'环':<9}{'均值Ø':>8}{'最大Ø':>8}{'最小Ø':>8}{'最大±%':>8}"
           f"{'raw极差%':>9}{'残差%':>7}{'相位ms':>8}")
    print(hdr)
    print("-" * 68)
    phases = {}
    for name in ORDER:
        y = np.array(series[name], dtype=float)
        ok = ~np.isnan(y)
        if ok.sum() < n * 0.7:
            print(f"{name:<9}  检出率过低 ({ok.sum()}/{n}), 跳过")
            continue
        # 先按周期折出"同一相位"的均值归零, 再拟合
        A0, amp, ph, rsd = fit_sine(ts[ok], y[ok], T_best)
        # raw 极值(分位鲁棒): 0.5%~99.5%
        lo_q, hi_q = np.percentile(y[ok], [0.5, 99.5])
        raw_range = (y[ok].max() - y[ok].min()) / A0 * 100
        sv = lambda r: r * 100.0
        px = lambda r: r * R                      # u -> 原生像素半径
        rec = {
            "svg_diam_mean": round(sv(A0) * 2, 2),
            "svg_diam_max": round(sv(A0 + amp) * 2, 2),
            "svg_diam_min": round(sv(A0 - amp) * 2, 2),
            "px_diam_mean": round(px(A0) * 2, 1),
            "px_diam_max": round(px(A0 + amp) * 2, 1),
            "px_diam_min": round(px(A0 - amp) * 2, 1),
            "svg_r_mean": round(sv(A0), 2),
            "svg_r_max": round(sv(A0 + amp), 2),
            "svg_r_min": round(sv(A0 - amp), 2),
            "amp_pct": round(amp / A0 * 100, 2),
            "range_pct": round(2 * amp / A0 * 100, 2),
            "raw_range_pct": round(float(raw_range), 2),
            "resid_pct": round(rsd / A0 * 100, 2),
            "phase_rad": round(ph, 4),
            "valid_frames": int(ok.sum()),
            "quantile_diam_pct": [round(sv(lo_q) * 2, 2), round(sv(hi_q) * 2, 2)],
        }
        out["rings"][name] = rec
        phases[name] = ph
        print(f"{name:<9}{rec['svg_diam_mean']:>8.2f}{rec['svg_diam_max']:>8.2f}{rec['svg_diam_min']:>8.2f}"
              f"{rec['amp_pct']:>8.2f}{rec['raw_range_pct']:>9.2f}{rec['resid_pct']:>7.2f}"
              f"{(ph - phases.get('白环外缘', ph)) / (2 * np.pi) * T_best * 1000:>8.0f}")

    # ---- 相位差 (以白环为基准, 负=更早) ----
    if "白环外缘" in phases:
        base = phases["白环外缘"]
        print("\n相位差 (相对白环, 负号=更早到达):")
        for name in ORDER:
            if name not in phases:
                continue
            d = (phases[name] - base) / (2 * np.pi) * T_best * 1000
            d = (d + T_best * 500) % (T_best * 1000) - T_best * 500
            out["rings"][name]["phase_ms_vs_white"] = round(d, 1)
            print(f"  {name:<9} {d:+7.1f} ms")

    # ---- 与我的当前实现对照 ----
    mine = {"深眼外缘": 17.9, "蓝瞳外缘": 28.1, "灰紫蓝外缘": 41.5, "白环外缘": 62.2, "外圈蓝外缘": 100.0}
    print(f"\n{'环':<9}{'原版Ø均值':>11}{'我的Ø':>9}{'差':>9}   (SVG 单位)")
    for name, r in mine.items():
        if name in out["rings"]:
            d = out["rings"][name]["svg_diam_mean"]
            print(f"{name:<9}{d:>11.2f}{r*2:>9.2f}{r*2-d:>+9.2f}")
    out["mine_svg_r"] = mine

    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {out_path}")


if __name__ == "__main__":
    main()
