"""
Re-resolve the white-disc animation question for the BV1CkcbzgEkC reference video.
- Eye center (1011.9, 364.7), frames at 60fps.
- For each of 8 angular rays, find the white-disc outer edge (first contiguous "white"
  block of >=5px thickness after the deep-blue core gap).
- Also track the iris-core outer edge (deep-blue -> middle-blue transition) on the same rays.
- Also track the bright-blue outer-ring INNER edge (where the dark-navy band ends and
  bright blue starts) -- if this is camera-zoom it should change uniformly across all
  measurements.
- Detrend each series (subtract moving mean of N=20 samples = ~0.33s), then FFT.
- If the white disc has a STRONG 0.85s peak after detrending, that's a real pulse.
"""
import os, math
import numpy as np
from PIL import Image

FRAMES_DIR = r'D:\work\fairy-pet\frames_hifps2'
CENTER = (1011.9, 364.7)  # white-disc centroid from prior localization
N_FRAMES = 900
EVERY = 3                # use 300 frames (~5s spans) — keeps noise low but covers many periods
ANGLES_DEG = [0, 45, 90, 135, 180, 225, 270, 315]

# approx eye outer radius in pixels (boundary of bright-blue ring)
R_OUTER_PX = 105.0

def load(i):
    p = os.path.join(FRAMES_DIR, f'f{i+1:04d}.png')   # frames are 1-indexed: f0001.png .. f0900.png
    return np.asarray(Image.open(p).convert('RGB'))

def is_white(rgb):
    r,g,b = rgb[0], rgb[1], rgb[2]
    return r > 200 and g > 200 and b > 200

def is_blue_ring(rgb):
    # bright-blue outer band color is near #5078E5 (R~80,G~120,B~229)
    r,g,b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    return b > 180 and b > r + 40 and b > g

def is_dark_navy(rgb):
    # dark navy band ~ #232A8F
    r,g,b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    return r < 80 and g < 80 and 80 < b < 180

def first_white_outer_disc(arr, cx, cy, ang, r_min=20, r_max=R_OUTER_PX):
    # walk outward from r_min; the first time we ENTER a run of >=3 white pixels, record
    # its outer edge (last white pixel index)
    dx, dy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    in_white = False
    run_start = 0
    last = None
    # step 1px
    for s in range(int(r_min), int(r_max)+1):
        x = int(round(cx + dx*s))
        y = int(round(cy + dy*s))
        if not (0 <= x < arr.shape[1] and 0 <= y < arr.shape[0]):
            break
        rgb = arr[y, x]
        if is_white(rgb):
            if not in_white:
                in_white = True
                run_start = s
            last = s
        else:
            if in_white and (s - run_start) >= 3:
                return float(last)
            in_white = False
    return float(last) if last is not None else float('nan')

def iris_core_edge(arr, cx, cy, ang):
    # find radius where pixel changes from very-dark core (mostly #C9D7FF glints not dark;
    # the dark core is dark-blue around (40,55,160)+#3056B8) to middle-blue.
    # simplest: find pixel where b drops sharply (deep-blue core ~ 50,90,210 vs mid blue ~ 49,100,192).
    # We instead find the OUTERMOST "dark blue" cluster radius.
    dx, dy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    last_dark = None
    for s in range(2, 60):
        x = int(round(cx + dx*s))
        y = int(round(cy + dy*s))
        if not (0 <= x < arr.shape[1] and 0 <= y < arr.shape[0]):
            break
        rgb = arr[y, x]
        r,g,b = int(rgb[0]), int(rgb[1]), int(rgb[2])
        # deep / middle blue: B>=120, R<120, B>R+30
        if b >= 120 and r < 130 and b > r + 20:
            last_dark = s
        else:
            if last_dark is not None:
                break
    return float(last_dark) if last_dark else float('nan')

def bright_ring_inner(arr, cx, cy, ang):
    # find innermost bright-blue outer ring pixel (between dark navy and bright blue)
    dx, dy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    for s in range(int(R_OUTER_PX)-1, 30, -1):
        x = int(round(cx + dx*s))
        y = int(round(cy + dy*s))
        if not (0 <= x < arr.shape[1] and 0 <= y < arr.shape[0]):
            continue
        rgb = arr[y, x]
        if is_blue_ring(rgb):
            return float(s)
        if is_dark_navy(rgb):
            continue
    return float('nan')


def fft_mag(x):
    x = x - np.mean(x)
    if np.std(x) < 1e-9:
        return None, 0.0
    f = np.fft.rfft(x * np.hanning(len(x)))
    p = np.abs(f)**2
    return p, np.std(x)

def main():
    frames = list(range(0, N_FRAMES, EVERY))
    print('using', len(frames), 'frames')
    data_disc  = {a: [] for a in ANGLES_DEG}
    data_core  = {a: [] for a in ANGLES_DEG}
    data_bring = {a: [] for a in ANGLES_DEG}

    for fi, i in enumerate(frames):
        arr = load(i)
        for a in ANGLES_DEG:
            data_disc[a].append(first_white_outer_disc(arr, *CENTER, a))
            data_core[a].append(iris_core_edge(arr, *CENTER, a))
            data_bring[a].append(bright_ring_inner(arr, *CENTER, a))
        if fi % 20 == 0:
            print(f'  frame {i}  disc 0°={data_disc[0][-1]:.1f}  core 0°={data_core[0][-1]:.1f}  bring 0°={data_bring[0][-1]}')

    fs = len(frames) / 60.0 * (N_FRAMES / len(frames))   # 60 / EVERY  -> here 20
    dt = 1.0/60.0 * EVERY
    print(f'effective fs={fs:.3f}Hz, dt={dt:.4f}s, span={len(frames)*dt:.3f}s')

    def report(name, series_by_angle):
        print(f'\n--- {name} ---')
        print(f'{"ang":>5}  {"med":>6}  {"std":>6}  {"top1":>22}  {"top2":>22}  {"top3":>22}')
        for a in ANGLES_DEG:
            x = np.array(series_by_angle[a], dtype=float)
            x = x[~np.isnan(x)]
            if len(x) < len(series_by_angle[a]) * 0.5:
                print(f'{a:>5}  too few samples ({len(x)})')
                continue
            # detrend with very-short moving mean to kill only DC & very slow drift
            med = float(np.median(x))
            std = float(np.std(x))
            # detrend by subtracting running mean over 20 samples (~1s, kills <=0.1Hz)
            k = 20
            if len(x) > 2*k:
                rm = np.convolve(x, np.ones(k)/k, mode='same')
                xd = x - rm
            else:
                xd = x - np.mean(x)
            p, _ = fft_mag(xd)
            if p is None:
                continue
            p[0] = 0
            top = np.argsort(p)[::-1][:3]
            freqs = np.fft.rfftfreq(len(xd), d=dt)
            out = []
            for idx in top:
                if freqs[idx] > 0:
                    T = 1.0/freqs[idx] if freqs[idx] > 0 else float('inf')
                    out.append(f'{freqs[idx]:.2f}Hz({T:.2f}s,p={int(p[idx])})')
            print(f'{a:>5}  {med:6.2f}  {std:6.2f}  ' + '  '.join(f'{o:>22}' for o in out))

    report('WHITE DISC outer edge', data_disc)
    report('IRIS CORE  outer edge', data_core)
    report('BRIGHT RING inner edge', data_bring)

    # Save arrays
    import pickle
    with open(r'D:\work\fairy-pet\_disc_edge.pkl', 'wb') as f:
        pickle.dump({'frames': frames, 'disc': data_disc, 'core': data_core, 'bring': data_bring}, f)
    print('saved.')

if __name__ == '__main__':
    main()
