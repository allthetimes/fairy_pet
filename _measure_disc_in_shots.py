"""Measure #whiteDisc outer-edge radius across the 8 phased screenshots.
This confirms whether the transform:scale animation actually grows/shrinks the disc
in pixel space across the 0.86s cycle.
"""
import os, math
import numpy as np
from PIL import Image

OUT = r'D:\work\fairy-pet\verify_white_disc'
N = 8

def is_white(p):
    r,g,b = int(p[0]), int(p[1]), int(p[2])
    return r>180 and g>180 and b>180

def disc_outer_edges(arr, cx, cy, r_min=20, r_max=120):
    # for each of 8 angles, find first >=3-pixel contiguous white run, return last index
    res = {}
    for a in [0, 45, 90, 135, 180, 225, 270, 315]:
        dx, dy = math.cos(math.radians(a)), math.sin(math.radians(a))
        in_w = False
        last = None
        run_start = -1
        for s in range(int(r_min), int(r_max)+1):
            x = int(round(cx + dx*s))
            y = int(round(cy + dy*s))
            if not (0 <= x < arr.shape[1] and 0 <= y < arr.shape[0]):
                break
            if is_white(arr[y,x]):
                if not in_w:
                    in_w = True
                    run_start = s
                last = s
            else:
                if in_w and (s-run_start) >= 3:
                    res[a] = float(last)
                    break
                in_w = False
        if a not in res:
            res[a] = float('nan')
    return res

# SVG viewBox 240x240, whiteDisc at cx=120 cy=120 r=65
# When Playwright captures the SVG element, the actual px == viewBox coords * (svg_width/240)
# We pick a fixed scale factor — getBoundingClientRect.width / 240.
# Detect scale by finding the iris-core edge (stable across animation timing) — but core was
# animated-frozen, so just find by assuming scale from #boot width.

results = []
for k in range(N):
    # actual filenames: shot_kk_t{N}ms.png where N ≈ k*107, but k=6 was t=645, not 642
    ms = [0, 107, 215, 322, 430, 537, 645, 752][k]
    path = os.path.join(OUT, f'shot_{k:02d}_t{ms}ms.png')
    img = np.asarray(Image.open(path).convert('RGB'))
    h, w = img.shape[:2]
    # find the eye center = centroid of white-ish pixels
    mask = (img[:,:,0] > 200) & (img[:,:,1] > 200) & (img[:,:,2] > 200)
    ys, xs = np.where(mask)
    if len(xs) < 100:
        print(f'frame {k}: no white px')
        continue
    cx = float(np.median(xs))
    cy = float(np.median(ys))
    rmax = min(w-cx-2, cx-2, h-cy-2, cy-2) - 4
    res = disc_outer_edges(img, cx, cy, r_max=min(rmax, 100))
    rw = [v for v in res.values() if not math.isnan(v)]
    rw_med = float(np.median(rw))
    results.append((k, ms, cx, cy, rw_med, res))
    print(f'frame {k}  t={ms:>4}ms  center=({cx:.1f},{cy:.1f})  disc median={rw_med:.2f}  per-angle={res}')

# Expected: median disc radius peaks ~ frame 3-4 (t≈322-430ms, midway through 0.86s = 0.43s).
rs = np.array([r[4] for r in results])
print(f'\nacross {N} frames: median={np.median(rs):.2f}, std={np.std(rs):.2f}, range=[{rs.min():.2f},{rs.max():.2f}]')
