#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
闭眼帽檐底缘轨迹重建 (concept/visual-spec.md §12.8)

目标
    只实现视频里出现的稳定闭眼状态: 点击 Fairy 直接进入闭眼, 再点恢复睁眼,
    不实现眼睑垂下/抬起的眨眼过程。本脚本负责"逐帧实测眼睑底缘轨迹"这一半。

素材
    E:\\My Files\\Downloads\\2026-09-13 22-44-30.mp4
    1920x1080 / 120fps / 3202 帧 / 26.7s。右侧为放大的 Fairy 环形核, 全片基本闭眼。

几何基准 (concept/visual-spec.md §12.8 规定)
    不是外圈 r=100, 也不是齿尖外端 r≈93, 而是**靛蓝齿轮环带的连续圆弧外缘** r_g。
    SVG 里 r_g = 78.1。视频实测: 白描边(最外细亮圈)中心 R_rim ≈ 215.6px,
    四方向(上下左右)给出的 r_g 一致 ≈ 167~168px。

    主指标:
        D(θ,t) = r_g(t) - r_lid(θ,t)
    D>0 表示眼睑底缘位于齿轮基圆内侧。

测量方法
    1. 圆心固定 (1607.0, 539.9): 全片白描边半径 215.64 ± 0.16px、圆心漂移 <0.5px,
       构图零漂移, 无需逐帧重估 —— 已用 scripts 里的稳定性检查确认。
    2. 每条射线取亮度 L, 自适应阈值 thr = median(L[r≈6..14px]) + DELTA,
       从内向外找**第一个**越过 thr 的位置 = 帽檐底缘。
       (不能用 |dL/dr| 全局极大: 更外侧"灰紫蓝→白"的梯度比帽檐底缘更强, 会抓错边。)
    3. 上半部(θ≈190°~350°)帽檐外缘贴合齿轮基圆 ⇒ 该段 r_lid 的中位数就是 r_g(t),
       兼作尺度自标定, 可吸收任何整体缩放。
    4. 四个尖齿(约 33.5/123.5/213.5/303.5°)所在角度会被剔除或回落到 r_g。

用法
    python scripts/closed_lid_track.py                       # 全片, 步长 1 帧
    python scripts/closed_lid_track.py --stride 3            # 抽帧加速
    python scripts/closed_lid_track.py --out dev/_lid_out    # 换输出目录

输出
    <out>/closed_lid.csv          逐帧实测 (宽表: frame,t,r_g,各角度 r_lid)
    <out>/closed_lid_meta.json    坐标系/角度表/统计摘要
    dev/shots/closed_lid_overlay_*.png   代表帧 overlay (固定基圆 + 实测底缘)
    <out>/lid_frames.json         压缩后的关键帧 (供 SVG 使用)

踩过的坑 (别重犯)
    1. 用蓝色掩膜(morphology)找圆盘 → 背景也是蓝的, 全部连成一片, 定位失败。
       改用最外细白描边(亮+低饱和)做基准。
    2. 亮度阈值判"深色"在 θ≈3°/177°(帽檐底缘与基圆即将交汇处)会误判:
       那些方向帽檐内部亮度升到 59~69、B-R 掉到 61~66, 固定阈 L<60 / B-R>65 全部翻车。
       必须用**自适应基准 + 增量**, 不能写死绝对阈值。
    3. |dL/dr| 全局极大抓到的往往是"灰紫蓝→白"(ΔL≈55)而不是帽檐底缘(ΔL≈25)。
    4. 帽檐底缘不等高: 最低点在 θ≈63° 而不是正下方 90°, 左右也不对称。
       不要假设它是关于 90° 对称的圆弧。
"""

import argparse
import csv
import json
import os
import sys

import cv2
import numpy as np

# ----------------------------------------------------------------------------
# 默认参数 (全部来自实测)
# ----------------------------------------------------------------------------
DEF_VIDEO = r"E:\My Files\Downloads\2026-09-13 22-44-30.mp4"
DEF_CX, DEF_CY = 1607.0, 539.9          # 圆心 (白描边圆拟合, 全片零漂移)
# 帽檐底缘判据: base 取"圆心附近最深处"(r 0~8px) 的亮度中位数。
# ⚠️ delta 必须 < "帽檐→深眼"的亮度差, 否则会跳过真正的底缘、抓到更外侧的
#    "深眼→中蓝环"边界。
#    实测(frame 1320 θ=90°) 层序: 帽檐(B111 L42) 0~6 → 深眼(B142 L62) 9~39 →
#    中蓝(B201 L124) 42~60 → 灰紫蓝(L158) 63~87 → 白(L220) 90+ 。
#    帽檐与深眼只差 ΔL≈20, 所以 delta=38 会误抓 r=45; delta=12 正确抓到 r≈9。
#    B-R/B-G 也无法区分两者(帽檐 75~97 / 深眼 97), 不能靠色度。
BASE_DELTA = 12.0
BR_THR = 145.0                           # 上半部"靛蓝→亮蓝"的 B-R 判据
SMOOTH_K = 5                             # 径向 5 点平滑 (压制扫描线/压缩噪声)
R_SAMPLE_MAX = 190.0                     # 径向采样上限 (需覆盖 r_g + 余量)
R_STEP = 0.25
ANG_STEP_DEF = 3.0                       # 角度步长
UP_LO, UP_HI = 190.0, 350.0              # 用这段角度标定 r_g (帽檐贴住基圆)
UP_ANG_STEP = 5.0
NOTCH_ANGS = (33.5, 123.5, 213.5, 303.5)  # 四个尖齿中心角 (SVG 规格)
# 齿尖保护半角: 齿尖本身是深靛色, 射线沿齿尖走到底都找不到"深靛→亮蓝"边界。
# 实测齿尖把边界推到 r=182+ 甚至完全推出去, 影响范围比几何半角(~12°)宽得多,
# 上半部扫出来 216~231° / 300~342° 两段异常, 故取 ±20°。
NOTCH_GUARD = 20.0

# 帧有效性过滤 (用于剔除视频开头的游戏 UI 过渡段)
BASE_LO, BASE_HI = 30.0, 70.0     # 帽檐内部基准亮度的合理区间 (实测 ≈ 41~49)
RG_LO, RG_HI = 150.0, 185.0       # r_g 合理区间 (实测 ≈ 163~174)
MIN_UP_VALID = 8                  # 上半部至少要有这么多个角度测到边界


# ----------------------------------------------------------------------------
# 采样网格 (圆心固定 ⇒ 坐标可复用, 用 cv2.remap 一次性取值)
# ----------------------------------------------------------------------------
RV = np.arange(0.0, R_SAMPLE_MAX + R_STEP, R_STEP)      # 径向采样半径表
N_BASE0 = 0                                             # "帽檐最深处"采样窗 r 0~8px
N_BASE1 = max(1, int(8.0 / R_STEP))


def _subpixel(rv, col, idx, lo, thr):
    """给定"首次越阈"的行号 idx, 在 col[idx-1]~col[idx] 之间线性插值出半径。"""
    if idx <= 0:
        return float(rv[0])
    a_, b_ = col[idx - 1], col[idx]
    fr = (thr - a_) / (b_ - a_) if abs(b_ - a_) > 1e-9 else 0.0
    return float(rv[idx - 1] + np.clip(fr, 0.0, 1.0) * R_STEP)


def lid_edge_from_column(col, rv):
    """单条亮度剖面的帽檐底缘 (自适应阈值 + 线性亚像素)。"""
    base = float(np.median(col[N_BASE0:N_BASE1]))
    thr = base + BASE_DELTA
    idx = np.where(col > thr)[0]
    if len(idx) == 0:
        return np.nan, base, thr
    return _subpixel(rv, col, int(idx[0]), None, thr), base, thr


def process_frame(L, BR, mapx, mapy, n_lo):
    """向量化: 下半部用亮度自适应阈值找帽檐底缘, 上半部用色度(B-R)找齿轮基圆。

    为什么分开:
      * 下半部边界是 深靛(L 24~78) → 白/中蓝(L 120~230), 亮度可分;
      * 上半部边界是 深靛(L 24~75) → 外圈亮蓝(L 88~95), 亮度差只有 ~15,
        而画面整体泛光会让深靛亮度整体抬升, 亮度阈值会整段失效(实测表现为间歇性
        全 NaN, 且呈 ~1.5s 周期性)。改用 B-R: 深靛 61~115 vs 亮蓝 155~170,
        分得干净, 且与整体亮度无关。
    """
    V = cv2.remap(L, mapx, mapy, cv2.INTER_LINEAR)
    VB = cv2.remap(BR, mapx, mapy, cv2.INTER_LINEAR)
    rv = RV
    n_ang = V.shape[1]
    out = np.full(n_ang, np.nan)
    bas = np.full(n_ang, np.nan)

    # ---- 下半部: 亮度自适应 ----
    Vlo = cv2.blur(V[:, :n_lo], (1, SMOOTH_K))        # 沿径向平滑
    col_j = np.arange(n_lo)
    base = np.median(V[:, :n_lo][N_BASE0:N_BASE1, :], axis=0)
    thr = base + BASE_DELTA
    mask = Vlo > thr[None, :]
    has = mask.any(axis=0)
    idx = np.argmax(mask, axis=0)
    i0 = np.clip(idx - 1, 0, Vlo.shape[0] - 1)
    Aa = Vlo[i0, col_j]
    Bb = Vlo[idx, col_j]
    den = Bb - Aa
    fr = np.where(np.abs(den) > 1e-9, (thr - Aa) / np.where(np.abs(den) > 1e-9, den, 1.0), 0.0)
    fr = np.clip(fr, 0.0, 1.0)
    rlo = rv[i0] + fr * R_STEP
    out[:n_lo] = np.where(has, rlo, np.nan)
    bas[:n_lo] = base

    # ---- 上半部: B-R 色度 ----
    VBup = VB[:, n_lo:]
    m2 = VBup > BR_THR
    has2 = m2.any(axis=0)
    idx2 = np.argmax(m2, axis=0)
    j2 = np.arange(VBup.shape[1])
    i1 = np.clip(idx2 - 1, 0, VBup.shape[0] - 1)
    Cc = VBup[i1, j2]
    Dd = VBup[idx2, j2]
    den2 = Dd - Cc
    fr2 = np.where(np.abs(den2) > 1e-9, (BR_THR - Cc) / np.where(np.abs(den2) > 1e-9, den2, 1.0), 0.0)
    fr2 = np.clip(fr2, 0.0, 1.0)
    rup = rv[i1] + fr2 * R_STEP
    out[n_lo:] = np.where(has2, rup, np.nan)
    return out, bas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=DEF_VIDEO)
    ap.add_argument("--cx", type=float, default=DEF_CX)
    ap.add_argument("--cy", type=float, default=DEF_CY)
    ap.add_argument("--stride", type=int, default=1, help="每 N 帧取一帧")
    ap.add_argument("--ang-step", type=float, default=ANG_STEP_DEF)
    ap.add_argument("--out", default="dev/_lid_out")
    ap.add_argument("--shots", default="dev/shots")
    ap.add_argument("--skip-sec", type=float, default=2.35,
                    help="跳过开头 N 秒 (游戏 UI 从 IDE 界面切到剧情画面的过渡段, "
                         "那段圆心附近全黑/构图标定不同, 不参与拟合)")
    ap.add_argument("--max-frames", type=int, default=0, help=">0 时只跑前 N 帧(调试)")
    args = ap.parse_args()

    if not os.path.exists(args.video):
        sys.exit("视频不存在: %s" % args.video)
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.shots, exist_ok=True)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        sys.exit("无法打开视频")
    fps = cap.get(cv2.CAP_PROP_FPS)
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print("视频 %dx%d @%.2ffps  %d 帧  %.2fs" % (W, H, fps, n_total, n_total / fps))

    # 采样网格 (圆心固定)。只处理圆盘外接的 ROI, 1080p 全图的高斯模糊/L·BR 计算
    # 是纯浪费 (ROI 面积只有全图的 ~6%)。
    PAD = 10
    RX0 = max(0, int(args.cx - R_SAMPLE_MAX) - PAD)
    RY0 = max(0, int(args.cy - R_SAMPLE_MAX) - PAD)
    RX1 = min(W, int(args.cx + R_SAMPLE_MAX) + PAD)
    RY1 = min(H, int(args.cy + R_SAMPLE_MAX) + PAD)
    RW, RH = RX1 - RX0, RY1 - RY0
    print("ROI %dx%d @(%d,%d)" % (RW, RH, RX0, RY0))
    angs_lo = np.arange(0.0, 180.0 + 1e-9, args.ang_step)          # 下半部: 主测量
    angs_up = np.arange(UP_LO, UP_HI + 1e-9, UP_ANG_STEP)          # 上半部: 标定 r_g
    angs_all = np.concatenate([angs_lo, angs_up])
    rad = np.deg2rad(angs_all)
    rv = np.arange(0.0, R_SAMPLE_MAX + R_STEP, R_STEP)
    mapx = (args.cx - RX0 + rv[:, None] * np.cos(rad)[None, :]).astype(np.float32)
    mapy = (args.cy - RY0 + rv[:, None] * np.sin(rad)[None, :]).astype(np.float32)
    n_lo = len(angs_lo)

    rows = []
    ov_cache = {}
    frame_idx = 0
    skip_frames = int(round(args.skip_sec * fps))
    if skip_frames > 0:
        print("跳过前 %.2fs (%d 帧) 的 UI 过渡段" % (args.skip_sec, skip_frames))
    kept = 0
    n_bad = 0
    t0 = None
    import time
    t0 = time.time()
    while True:
        if frame_idx < skip_frames:
            if not cap.grab():
                break
            frame_idx += 1
            continue
        if frame_idx % args.stride != 0:
            if not cap.grab():                 # 跳帧只 grab 不解码, 省时间
                break
            frame_idx += 1
            continue
        if args.max_frames and kept >= args.max_frames:
            break
        ok, frame = cap.read()
        if not ok:
            break
        roi = frame[RY0:RY1, RX0:RX1]
        fb = cv2.GaussianBlur(roi, (3, 3), 0).astype(np.float32)
        Bc, Gc, Rc = fb[:, :, 0], fb[:, :, 1], fb[:, :, 2]
        L = 0.114 * Bc + 0.587 * Gc + 0.299 * Rc
        BR = Bc - Rc
        r_lid, base = process_frame(L, BR, mapx, mapy, n_lo)
        r_lo = r_lid[:n_lo]
        r_up = r_lid[n_lo:]
        # 上半部标定 r_g: 排除齿尖附近 (射线困在齿尖里, 没有边界)
        up_ok = np.ones(len(angs_up), dtype=bool)
        for na in NOTCH_ANGS:
            d = np.abs(((angs_up - na + 180.0) % 360.0) - 180.0)
            up_ok &= d > NOTCH_GUARD
        _v = r_up[up_ok]
        _v = _v[np.isfinite(_v)]
        n_up_valid = int(len(_v))
        r_g = float(np.median(_v)) if len(_v) else float("nan")
        # ---- 帧有效性: 视频前 ~2.4s 是游戏 UI 过渡段(IDE 界面→剧情画面),
        #      圆心附近全黑(base≈8 而非正常的 44), 这类帧必须丢弃 ----
        base_med = float(np.nanmedian(base))
        valid = (BASE_LO <= base_med <= BASE_HI and np.isfinite(r_g)
                 and RG_LO <= r_g <= RG_HI and n_up_valid >= MIN_UP_VALID)
        if not valid:
            n_bad += 1
            frame_idx += 1
            continue
        if kept % 40 == 0:
            ov_cache[frame_idx] = (roi.copy(), r_lo.copy(), r_g)
        rows.append((frame_idx, frame_idx / fps, r_g, n_up_valid) + tuple(r_lo))
        kept += 1
        if kept % 200 == 0:
            el = time.time() - t0
            print("  %d 帧  %.1fs  (%.1f 帧/s)" % (kept, el, kept / max(el, 1e-6)))
        frame_idx += 1
    cap.release()
    print("处理 %d 帧, 丢弃无效 %d 帧, 用时 %.1fs" % (kept, n_bad, time.time() - t0))
    if kept == 0:
        sys.exit("没有有效帧, 检查 --cx/--cy 与有效性判据")

    # ---- 落盘 CSV ----
    cols = ["frame", "t", "r_g", "n_up"] + ["r_lid_%05.1f" % a for a in angs_lo]
    csv_path = os.path.join(args.out, "closed_lid.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    print("CSV -> %s (%.1f KB)" % (csv_path, os.path.getsize(csv_path) / 1024))

    A = np.array(rows, dtype=float)
    rg = A[:, 2]
    rlo = A[:, 4:]
    D = rg[:, None] - rlo
    n_up = A[:, 3]
    print("上半部标定有效角度数: %.0f ~ %.0f (中位 %.0f)" % (n_up.min(), n_up.max(), np.median(n_up)))
    meta = {
        "video": os.path.basename(args.video),
        "video_size": [W, H], "fps": fps, "frames_total": n_total,
        "stride": args.stride, "frames_used": kept, "frames_dropped": n_bad,
        "center": [args.cx, args.cy],
        "r_g_px_mean": float(np.mean(rg)), "r_g_px_std": float(np.std(rg)),
        "r_g_px_min": float(np.min(rg)), "r_g_px_max": float(np.max(rg)),
        "svg_r_g": 78.1,
        "angles_deg": [float(a) for a in angs_lo],
        "px_per_svg": float(np.mean(rg) / 78.1),
        "D_px_max": float(np.nanmax(D)), "D_px_min_d1": float(np.nanmin(D)),
    }
    with open(os.path.join(args.out, "closed_lid_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print("r_g = %.2f ± %.2f px  (%.2f~%.2f)  => 1 SVG 单位 = %.3f px"
          % (meta["r_g_px_mean"], meta["r_g_px_std"], meta["r_g_px_min"],
             meta["r_g_px_max"], meta["px_per_svg"]))
    print("D 范围 %.1f ~ %.1f px  (最大处约在 θ=%.0f°)"
          % (meta["D_px_min_d1"], meta["D_px_max"],
             float(angs_lo[int(np.nanargmax(np.nanmean(D, axis=0)))])))

    # ---- 代表帧 overlay (从缓存里均匀取 5 帧) ----
    keys = sorted(ov_cache.keys())
    if keys:
        idxs = [int(round(i * (len(keys) - 1) / 4.0)) for i in range(5)]
        for k in sorted(set(idxs)):
            fr = keys[k]
            img, r_lo_, rg_ = ov_cache[fr]
            vis = img.copy()
            ccx, ccy = args.cx - RX0, args.cy - RY0
            cv2.circle(vis, (int(round(ccx)), int(round(ccy))),
                       int(round(rg_)), (0, 255, 0), 2, cv2.LINE_AA)
            for a, rr in zip(angs_lo, r_lo_):
                if not np.isfinite(rr):
                    continue
                aa = np.deg2rad(a)
                px = int(round(ccx + rr * np.cos(aa)))
                py = int(round(ccy + rr * np.sin(aa)))
                cv2.circle(vis, (px, py), 3, (0, 0, 255), -1, cv2.LINE_AA)
            cv2.drawMarker(vis, (int(round(ccx)), int(round(ccy))),
                           (0, 255, 255), cv2.MARKER_CROSS, 24, 2)
            outp = os.path.join(args.shots, "closed_lid_overlay_f%05d.png" % fr)
            cv2.imwrite(outp, cv2.resize(vis, (RW * 3, RH * 3), interpolation=cv2.INTER_NEAREST))
            print("overlay -> %s" % outp)


if __name__ == "__main__":
    main()
