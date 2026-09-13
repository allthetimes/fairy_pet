"""在视频里找 Fairy 头像出现的段落。

策略: 把视频按 fps 抽帧, 用 hd_avatar 的中心圆形 ROI 做模板, FFT-互相关
匹配, 找出最佳匹配分; 高分连续帧合并为段.

用法:
  python scan_fairy_segments.py <video> <outdir> [--ref ...] [--fps 0.5]
"""
import argparse
import os
import sys
import time

import numpy as np
from PIL import Image


def sample_video(video, fps, scale_w=480):
    """用 imageio v3 imiter 按 fps 降采样. 返回 (N, H, W, 3) float32."""
    import imageio.v3 as iio
    meta = iio.immeta(video)
    src_fps = float(meta.get("fps", 30))
    step = max(1, round(src_fps / fps))
    print(f"视频 fps={src_fps:.2f}, 抽 {1/step*src_fps:.2f} fps, 每 {step} 帧取 1")

    out = []
    for n, fr in enumerate(iio.imiter(video)):
        if n % step != 0:
            continue
        im = Image.fromarray(fr).convert("RGB")
        if im.size[0] != scale_w:
            scale = scale_w / im.size[0]
            new_h = int(im.size[1] * scale)
            im = im.resize((scale_w, new_h), Image.LANCZOS)
        out.append(np.asarray(im, dtype=np.float32))
    arr = np.stack(out, axis=0) if out else np.empty((0, 270, scale_w, 3), np.float32)
    return arr


def match_template(arr, template):
    """逐帧滑动窗 SSD. 返回 (N, outH, outW) SSD 图, 越小越好."""
    from numpy.lib.stride_tricks import sliding_window_view
    N, H, W, _ = arr.shape
    TH, TW, _ = template.shape
    outH, outW = H - TH + 1, W - TW + 1

    F = arr.mean(axis=-1).astype(np.float32)            # (N, H, W)
    T = template.mean(axis=-1).astype(np.float32)       # (TH, TW)

    ssd = np.empty((N, outH, outW), dtype=np.float32)
    T_sq_sum = float((T * T).sum())
    for n in range(N):
        # sliding windows of F[n] -> (outH, outW, TH, TW)
        win = sliding_window_view(F[n], (TH, TW))
        # 算每个窗口与 T 的 SSD
        # win: (outH, outW, TH, TW), T: (TH, TW)
        # 用 broadcasting 求 (win - T)**2 sum over (TH, TW)
        diff = win - T[None, None, :, :]
        ssd[n] = (diff * diff).sum(axis=(-2, -1))

    # 归一化
    ssd = ssd / (TH * TW)
    return ssd


def find_segments(scores, ratio_thr=0.4):
    """scores: (N,) 越小越像. 段: 连续 best < thr 的合并."""
    lo, hi = scores.min(), scores.max()
    thr = lo + (hi - lo) * ratio_thr
    in_seg = scores < thr
    segs = []
    cur = []
    for i, v in enumerate(in_seg):
        if v:
            cur.append(i)
        elif cur:
            segs.append(cur); cur = []
    if cur:
        segs.append(cur)
    return segs, thr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("outdir")
    ap.add_argument("--ref", default="analysis/hd_avatar.png")
    ap.add_argument("--fps", type=float, default=0.5)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    ref = np.asarray(Image.open(a.ref).convert("RGB"))
    H, W, _ = ref.shape
    cx, cy = W / 2, H / 2
    R = min(cx, cy) * 0.92
    yy, xx = np.mgrid[0:H, 0:W]
    in_mask = ((xx - cx) ** 2 + (yy - cy) ** 2) <= R * R
    ys, xs = np.where(in_mask)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    template_full = ref[y0:y1 + 1, x0:x1 + 1].astype(np.float32)
    tw = 120
    scale = tw / template_full.shape[1]
    th = max(8, int(template_full.shape[0] * scale))
    template_full = np.asarray(
        Image.fromarray(template_full.astype(np.uint8)).resize((tw, th), Image.LANCZOS),
        dtype=np.float32,
    )
    print(f"模板 {tw}x{th}")

    t0 = time.time()
    arr = sample_video(a.video, a.fps)
    print(f"抽 {len(arr)} 帧, shape={arr.shape}, 耗时 {time.time()-t0:.2f}s")

    if len(arr) == 0:
        print("无帧"); return

    print("匹配中...")
    t0 = time.time()
    ssd = match_template(arr, template_full)
    print(f"匹配耗时 {time.time()-t0:.2f}s")

    best = ssd.min(axis=(1, 2))
    best_pos = np.empty((len(arr), 2), dtype=np.int32)
    for n in range(len(arr)):
        idx = np.unravel_index(np.argmin(ssd[n]), ssd[n].shape)
        best_pos[n] = (idx[1], idx[0])

    log = os.path.join(a.outdir, "_scan.log")
    with open(log, "w", encoding="utf-8") as f:
        f.write(f"# scan_fairy_segments (FFT-cross)\nvideo={a.video}\nref={a.ref}\n")
        f.write(f"fps={a.fps}\ntemplate={tw}x{th}\n\n")
        f.write("# all frames, sorted by score\n")
        f.write("# t\tscore\t(x,y)\n")
        for i in range(len(arr)):
            t = i / a.fps
            x, y = best_pos[i]
            f.write(f"{t:7.2f}\t{best[i]:8.2f}\t({x:3d},{y:3d})\n")

    segs, thr = find_segments(best)
    summary = os.path.join(a.outdir, "_segments.txt")
    with open(summary, "w", encoding="utf-8") as f:
        f.write("# Fairy segments (sorted by start)\n")
        f.write(f"# threshold = best.min + 0.4*(max-min) = {thr:.2f}\n")
        f.write("# t_start\tt_end\tbest_t\tbest_score\n")
        for s in segs:
            t0 = s[0] / a.fps
            t1 = s[-1] / a.fps
            ib = s[int(np.argmin(best[s]))]
            f.write(f"{t0:7.2f}\t{t1:7.2f}\t{ib/a.fps:7.2f}\t{best[ib]:8.2f}\n")
    print(f"日志 -> {log}")
    print(f"段 -> {summary}")
    print(f"共 {len(segs)} 段, 最低分={best.min():.2f}, 阈值={thr:.2f}")
    for s in segs[:20]:
        t0 = s[0] / a.fps
        t1 = s[-1] / a.fps
        ib = s[int(np.argmin(best[s]))]
        print(f"  {t0:6.2f}s ~ {t1:6.2f}s   best {ib/a.fps:6.2f}s "
              f"({best[ib]:.2f}) @ {best_pos[ib][0]},{best_pos[ib][1]}")


if __name__ == "__main__":
    main()