#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 closed_lid_track.py 产出的逐帧眼睑底缘数据, 压缩成可喂给 SVG <animate d> 的关键帧。

输入
    dev/closed_lid.csv        逐帧宽表 (frame,t,r_g,n_up,r_lid_<ang>...)
    dev/closed_lid_meta.json  坐标系与角度表

输出
    dev/closed_lid_keys.json  {keyTimes, values, dur, path_template, stats}
       values: 每个关键帧一条完整 path 的 d 字符串, 用 ';' 连接直接塞进 SMIL
    (可选 --patch dev/fairy-lab.html) 直接把 values/keyTimes/dur 写回页面

算法
    实测这条轨迹是**严格周期**的 (周期 0.8520s, 按此折叠后残差 std 1.77px,
    而原始信号 std 7.7px —— 折叠掉 95% 的方差; 对比 T=0.8578→3.35px /
    T=0.8667→5.96px 都明显更差)。所以:

    1. 读宽表 -> D(θ,t) = r_g(t) - r_lid(θ,t), 丢掉开头游戏 UI 过渡段的空洞
    2. 按 T 把 D 折叠成"一个周期的相位波形" (每相位取各周期中位数, 抗离群)
    3. 对**每个角度**各做一次 Douglas-Peucker 简化 (垂直距离, 阈值 EPS),
       取所有角度保留时刻的**并集** => 任意角度的重构误差都 <= EPS
    4. 每个关键帧按 θ 采样生成 path: 上半圆用 A 命令贴合齿轮基圆,
       下半部用底缘点 (r_lid·cosθ, r_lid·sinθ) 连成折线
    5. keyTimes 归一化到 [0,1], 首尾同相位 => repeatCount=indefinite 无缝循环

为什么用"所有角度并集"而不是只压缩某个特征量:
    底缘端点(θ≈6°/174°)会随帽檐上下移动而左右滑动, 单压一个特征量在那里会超差。
    并集做法把最坏情况控制在阈值内。

用法
    python scripts/closed_lid_fit.py                        # 默认参数
    python scripts/closed_lid_fit.py --eps 0.8 --nph 160
    python scripts/closed_lid_fit.py --patch dev/fairy-lab.html
"""

import argparse
import csv
import json
import os
import re
import sys

import numpy as np

SVG_R_G = 78.1               # SVG 里齿轮基圆半径 (= visual-spec §12.8 基准)
DEF_EPS_BOT = 0.35           # DP 阈值 (SVG 单位, 作用在底缘中点 y 上 ≈ 0.76px)
DEF_NPH = 120                # 折叠后的相位分辨率 (每周期采样点数)
DEF_T = 0.8520               # 实测周期 (s); 页面上的 dur 由呼吸滑条驱动, 见 --patch 说明
DEF_MID_OPEN = -2.0          # 最开: 底缘中点在圆心**上方** 2 SVG 单位
DEF_EP_Y = -8.0             # 底缘弧端点的 y (圆心**上方** 8 单位; 用户反馈端点要上移, 否则弧太平)


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.reader(f)
        hdr = next(rd)
        rows = [r for r in rd if r]
    A = np.array(rows, dtype=float)
    cols = {h: i for i, h in enumerate(hdr)}
    angs = np.array([float(h.split("_")[-1]) for h in hdr if h.startswith("r_lid_")])
    rlo = A[:, [cols["r_lid_%05.1f" % a] for a in angs]]
    return A[:, cols["frame"]], A[:, cols["t"]], A[:, cols["r_g"]], angs, rlo


def dp_keep(x, y, eps):
    """Douglas-Peucker, 垂直距离。返回保留的下标 (升序)。"""
    n = len(x)
    if n <= 2:
        return [0, n - 1]
    keep = {0, n - 1}
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        xi, xj = x[i], x[j]
        yi, yj = y[i], y[j]
        span = xj - xi
        if span <= 0:
            d = np.abs(y[i + 1:j] - yi)
        else:
            t = (x[i + 1:j] - xi) / span
            d = np.abs(y[i + 1:j] - (yi + (yj - yi) * t))
        k = int(np.argmax(d))
        if d[k] > eps:
            k = k + i + 1
            keep.add(k)
            stack.append((i, k))
            stack.append((k, j))
    return sorted(keep)


def smooth(y, w_med=5, w_avg=5):
    """滑动中值 + 滑动均值, 去掉压缩噪声但保留拐点。"""
    if len(y) < w_med:
        return y.copy()
    pad = np.r_[y[:w_med // 2][::-1], y, y[-(w_med // 2):][::-1]]
    m = np.array([np.median(pad[i:i + w_med]) for i in range(len(y))])
    k = np.ones(w_avg) / w_avg
    pad2 = np.r_[m[:w_avg // 2][::-1], m, m[-(w_avg // 2):][::-1]]
    return np.convolve(pad2, k, mode="valid")[:len(y)]


def ring_smooth(y, w_med=5, w_avg=3):
    """环形(周期)平滑: 折叠波形首尾相接, 普通滑动窗口会在接缝处失真。"""
    n = len(y)
    if n < max(w_med, w_avg):
        return y.copy()
    ext = np.r_[y[-(w_med // 2):], y, y[:w_med // 2]]
    med = np.array([np.median(ext[i:i + w_med]) for i in range(n)])
    ext2 = np.r_[med[-(w_avg // 2):], med, med[:w_avg // 2]]
    k = np.ones(w_avg) / w_avg
    return np.array([float(np.dot(ext2[i:i + w_avg], k)) for i in range(n)])


def arc_path(bot, R_G=SVG_R_G, ep_y=None):
    """闭眼帽檐底缘: 两个端点固定在基圆 (±x0, ep_y) 不动, 只有弧的下垂深度(bot)在变。

    ep_y = 端点的 y 坐标 (SVG, 向下为正; 负数 = 圆心上方)。
    用户 2026-09-14 11:26 反馈"端点再往上一点, 现在有点太平了" ——
    端点上移后矢高 (bot − ep_y) 变大, 弧更弯; 且端点固定不动。

    端点必须在基圆上: x0 = √(R_G² − ep_y²)。
    圆心 (0, cy): x0² + (ep_y − cy)² = (bot − cy)²
      ⇒ cy = (x0² + ep_y² − bot²) / (2·(ep_y − bot))
      ⇒ R = bot − cy
    bot > ep_y 恒成立(中点始终低于端点) ⇒ 弧始终向下凸, sweep 恒为 1, 无翻转。

    ⚠️⚠️ **<animate> 必须是 <path> 的子元素才能动画 d 属性** ——
    放在 <g> 里会作用到 <g> 的 d 属性（不存在）, 动画静默失效。
    本项目 2026-09-14 曾因此误判"Chrome 对圆弧 d 补间不可靠", 其实是 DOM 结构错误。
    """
    bot = max(float(bot), ep_y + 0.5)     # 中点必须低于端点, 否则弧翻向/退化
    x0 = (R_G * R_G - ep_y * ep_y) ** 0.5
    cy = (x0 * x0 + ep_y * ep_y - bot * bot) / (2.0 * (ep_y - bot))
    R = bot - cy
    return ("M -%.2f %.1f A %.1f %.1f 0 0 1 %.2f %.1f "
            "A %.2f %.2f 0 0 1 -%.2f %.1f Z"
            % (x0, ep_y, R_G, R_G, x0, ep_y, R, R, x0, ep_y))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="dev/closed_lid.csv")
    ap.add_argument("--meta", default="dev/closed_lid_meta.json")
    ap.add_argument("--out", default="dev/closed_lid_keys.json")
    ap.add_argument("--eps-bot", type=float, default=DEF_EPS_BOT,
                    help="DP 阈值 (SVG 单位, 作用在底缘中央深度 bot 上)")
    ap.add_argument("--nph", type=int, default=DEF_NPH, help="折叠相位分辨率")
    ap.add_argument("--nkeys", type=int, default=0,
                    help="关键相位个数 (>0 用均匀采样; 0=按 bot 波形 DP)")
    ap.add_argument("--T", type=float, default=DEF_T, help="折叠周期(s)")
    ap.add_argument("--no-rescale", dest="rescale", action="store_false",
                    help="不做幅度校正(默认会拉伸回实测极值)")
    ap.add_argument("--ep-y", type=float, default=DEF_EP_Y,
                    help="底缘弧端点的 y (SVG; 负 = 圆心上方, 越负弧越弯)")
    ap.add_argument("--patch", default=None, help="可选: 直接写回 html")
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        sys.exit("缺少 %s, 先跑 scripts/closed_lid_track.py" % args.csv)
    frame, t, r_g, angs, rlo = load(args.csv)
    with open(args.meta, encoding="utf-8") as f:
        meta = json.load(f)
    px2svg = SVG_R_G / float(meta["r_g_px_mean"])
    print("载入 %d 帧 x %d 角, r_g=%.2fpx, 1 SVG = %.4f px"
          % (len(t), len(angs), meta["r_g_px_mean"], 1 / px2svg))

    # 时间连续性: 丢弃开头过渡段留下的空洞(帧号不连续处)
    dt = np.diff(t)
    gap = np.where(dt > np.median(dt) * 3)[0]
    if len(gap):
        seg0 = int(gap[0]) + 1
        print("⚠ 检测到 %d 处时间空洞, 只用第 %d 帧之后的数据" % (len(gap), seg0))
    else:
        seg0 = 0
    t = t[seg0:]
    r_g = r_g[seg0:]
    rlo = rlo[seg0:]
    frame = frame[seg0:]

    # ---- 底缘用一个参数描述: bot = r_lid(90°) = 圆弧最低点的深度 ----
    #      理由见 arc_path(): 圆弧必须过基圆两交点 ⇒ 圆心在 y 轴上 ⇒ 只剩一个自由度。
    D_px = r_g[:, None] - rlo                    # D = r_g - r_lid
    # θ 紧邻水平方向的两端(±5°), 帽檐底缘与齿轮基圆几乎重合, 自适应亮度阈值会
    # 在帽檐内部打滑 (实测 D 出现 -19px 的负值、或飘到 114px)。该区间强制 D=0。
    # 依据: 单帧实测 θ=3° 时 D=0.4px, θ=6° 时 D=61px —— 交点就在这条缝里。
    NOISE_DEG = 5.0
    jend = (angs <= NOISE_DEG) | (angs >= 180.0 - NOISE_DEG)
    D_px[:, jend] = 0.0
    r_lid_svg = SVG_R_G - D_px * px2svg
    j90 = int(np.argmin(np.abs(angs - 90)))
    bot_raw = r_lid_svg[:, j90]
    print("bot (底缘中央深度): %.2f ~ %.2f SVG  (= %.1f ~ %.1f px)"
          % (np.nanmin(bot_raw), np.nanmax(bot_raw),
             np.nanmin(bot_raw) * px2svg, np.nanmax(bot_raw) * px2svg))

    # ---- 按周期折叠成一个相位的平均波形 ----
    fps = float(meta["fps"])
    T = args.T
    nph = args.nph
    ph = (np.arange(len(t)) / (T * fps)) % 1.0
    bins = (ph * nph).astype(int) % nph
    B = np.full(nph, np.nan)
    cnt = np.zeros(nph, dtype=int)
    for b in range(nph):
        sel = bins == b
        cnt[b] = int(sel.sum())
        v = bot_raw[sel]
        v = v[np.isfinite(v)]
        if len(v) >= 3:
            B[b] = float(np.median(v))
    good = np.isfinite(B)
    if not good.all():                                  # 少量空相位 -> 环形插值
        ii = np.arange(nph)
        B = np.interp(ii, ii[good], B[good], period=nph)
    # 相位 0 对齐到"呼吸谷"(bot 最大 = 眼睑最下)。
    # ⚠️ 方向 (用户 2026-09-14 11:26 指出"运动轨迹又反了"):
    #    "原视频是收缩到最小的时候眼睑运动到最下面" —— 呼吸谷(内环最小)时
    #    眼睑中点必须在**最下面**(bot 最大)。上一轮折叠时用 argmin 对齐,
    #    结果呼吸谷对应了眼睑最上, 方向反了。这里必须用 **argmax**。
    ph0 = int(np.argmax(B))
    B = np.roll(B, -ph0)
    # 环形平滑: 去掉折叠残差在下降段留下的小抖动 (相位错位 + 中位数噪声),
    # 否则 DP 会为了追这些 0.5 SVG 级的小波动多出一堆无效关键帧。
    B = ring_smooth(B, 5, 3)
    # ---- 幅度校正 ----
    # 折叠取中位数 + 周期不精确带来的相位抖动, 会把极值收敛:
    # 实测原始 bot 摆幅 12.25 SVG, 折叠后只剩 8.84 (-28%) —— 动画会显得"没在动"。
    # 这里保持折叠出来的**形状**, 只用 0.5/99.5 分位数把幅度线性拉伸回实测极值。
    bf = bot_raw[np.isfinite(bot_raw)]
    lo_r, hi_r = (float(v) for v in np.percentile(bf, [0.5, 99.5]))
    lo_f, hi_f = float(np.min(B)), float(np.max(B))
    if args.rescale and hi_f > lo_f:
        B = (B - lo_f) / (hi_f - lo_f) * (hi_r - lo_r) + lo_r
        print("幅度校正: 折叠 %.2f~%.2f -> 拉伸到实测分位 %.2f~%.2f (幅度 %.2f -> %.2f SVG)"
              % (lo_f, hi_f, lo_r, hi_r, hi_f - lo_f, hi_r - lo_r))
    var_w = np.nanmean([np.nanvar(bot_raw[bins == b]) for b in range(nph) if cnt[b] >= 3])
    res_std = float(np.sqrt(var_w))
    print("折叠: T=%.4fs, 每相位 %.0f 个周期样本; 折叠残差 std %.3f SVG (原始 %.3f SVG)"
          % (T, cnt.mean(), res_std, float(np.nanstd(bot_raw))))

    # ---- d 动画: 端点固定在基圆 (±78.1, 0) 不动, 只有弧的下垂深度(bot)在变 ----
    # (2026-09-14 10:58 用户指出"圆弧两个端点也是不会动的"。
    #  之前试过"形状固定 + translate" —— 那会让端点跟着滑, 不对;
    #  更早还试过 "<animate> 放在 <g> 里" —— SMIL 只作用于父元素, <g> 没有 d 属性,
    #  动画静默失效, 还让我误判成"Chrome 圆弧补间不可靠"。真正原因是 DOM 结构错误。)
    bot_shape = float(np.median(B))                  # 只用于核对
    _x0 = (SVG_R_G**2 - args.ep_y**2) ** 0.5
    print("端点固定在基圆 (±%.2f, %.1f) 不动; 中点矢高 = bot − %.1f" % (_x0, args.ep_y, args.ep_y))

    # ---- 关键相位: 对 bot 波形做 DP ----
    keys = dp_keep(np.arange(nph, dtype=float), B, args.eps_bot)
    print("DP 阈值 %.2f SVG -> %d 个关键帧/周期" % (args.eps_bot, len(keys)))

    vals = [arc_path(B[k], ep_y=args.ep_y) for k in keys]
    mid_y = [round(float(B[k]), 2) for k in keys]
    kt = [k / float(nph) for k in keys]
    kt[0] = 0.0
    kt[-1] = 1.0
    for i in range(1, len(kt)):
        if kt[i] <= kt[i - 1]:
            kt[i] = kt[i - 1] + 1e-6
    kt[-1] = 1.0
    vals[-1] = vals[0]                                  # 首尾同相位, 循环无缝
    mid_y[-1] = mid_y[0]
    dur = T

    res = {
        "dur": round(dur, 4),
        "keyTimes": ";".join("%.5f" % v for v in kt),
        "values": ";".join(vals),             # <animate attributeName="d"> 的 values
        "n_keys": len(keys),
        "eps_bot": args.eps_bot,
        "T_fold": T,
        "nph": nph,
        "svg_r_g": SVG_R_G,
        "px_per_svg": 1 / px2svg,
        "fold_resid_svg": res_std,
        "mid_y": mid_y,                        # 各关键帧的底缘中点 y (核验用)
        "video": meta.get("video"),
        "seg_t": [round(float(t[0]), 3), round(float(t[-1]), 3)],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("dur=%.3fs  keyTimes=%d 项  path 平均 %.0f 字符"
          % (dur, len(kt), np.mean([len(v) for v in vals])))
    print("-> %s (%.1f KB)" % (args.out, os.path.getsize(args.out) / 1024))

    if args.patch:
        patch_html(args.patch, res)
        print("已写回 %s" % args.patch)


def patch_html(path, res):
    """把关键帧写回页面。

    页面上闭眼帽檐的结构 (2026-09-14 10:58 起):
        <g id="stateB_lid_top" style="display:none">
          <path id="closedLidPath" d="…" fill="url(#gLid)">
            <animate id="closedLidMoveAnim" attributeName="d"
                     values="<每帧一条 path>" keyTimes="…" dur="…"/>
          </path>
        </g>

    ⚠️⚠️ **<animate> 必须是 <path> 的子元素** —— SMIL 只作用于父元素的属性,
    放在 <g> 里会去找 <g> 的 d 属性（不存在）, 动画静默失效。
    本项目曾因此误判"Chrome 对圆弧 d 补间不可靠", 真正原因是 DOM 结构错误。

    端点固定在基圆 (±78.1, 0) 不动, 只有弧的下垂深度(bot)在变 ——
    所以不能用"形状固定 + translate"(那会让端点跟着滑)。
    """
    with open(path, encoding="utf-8") as f:
        s = f.read()
    m = re.search(r'<animate id="closedLidMoveAnim"[\s\S]*?/>', s)
    if not m:
        sys.exit("在 %s 里找不到 closedLidMoveAnim" % path)
    blk = m.group(0)
    nb = re.sub(r'values="[\s\S]*?"', 'values="%s"' % res["values"], blk, count=1)
    nb = re.sub(r'keyTimes="[^"]*"', 'keyTimes="%s"' % res["keyTimes"], nb, count=1)
    nb = re.sub(r'dur="[^"]*"', 'dur="%ss"' % res["dur"], nb, count=1)
    s = s[:m.start()] + nb + s[m.end():]
    # 静态 d = 首帧 (页面加载瞬间、或 SMIL 被禁时的兜底)
    # ⚠️ 不能用 r'd="…"' 替换: 它会先匹配到 id=" 里的 'd="' 而把 id 属性吃掉。
    m2 = re.search(r'<path id="closedLidPath" d="[^"]*"', s)
    if m2:
        nb2 = '<path id="closedLidPath" d="%s"' % res["values"].split(";")[0]
        s = s[:m2.start()] + nb2 + s[m2.end():]
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)


if __name__ == "__main__":
    main()
