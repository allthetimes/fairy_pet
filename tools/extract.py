# -*- coding: utf-8 -*-
"""
tools.extract — ffmpeg 抽帧（取代 7 个根目录 extract_*.py）

子命令：
  hifps2      BV1CkcbzgEkC 0-15s 60fps   → frames_hifps2/   （★README 主用）
  hifps_crop  egg.mp4 21-43s 12fps + 眼部 160x160 → frames_hifps/ + eye_crops/
  egg-voice   egg.mp4 / voice.mp4 全片 2fps → frames_egg/ + frames_voice/
  events      5 个关键时刻前后 0.4s 共 5x24 帧 → frames_evt_event_*/  + compare_events/events_grid.png
  full-frames BV1CkcbzgEkC 5 个时刻整帧 → full_frames/
  right-eye   BV1CkcbzgEkC 0-15s 每 1s 一帧右眼 → right_eye_seq/  + 网格图
  boot-idle   boot/idle 全片抽帧（待办 boot 分析用）→ ref_video/frames_boot/ + frames_idle/
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# 让 `python tools/extract.py` 与 `python -m tools.extract` 两种调用都能 import tools.*
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import imageio_ffmpeg

from tools.common import REF_VIDEO, ROOT, list_frames, reset_out


def ffmpeg_exe():
    return imageio_ffmpeg.get_ffmpeg_exe()


def ffmpeg_extract(src, outdir, *, start=None, end=None, duration=None,
                   fps=12, scale=None, q=None, single_frame=False):
    """统一 ffmpeg 抽帧接口。

    src      : Path-like, 源视频
    outdir   : Path-like, 输出目录
    start    : '-ss' 起始秒（None 不加）
    end      : '-to' 终止秒（与 start 互斥）
    duration : '-t' 持续秒
    fps      : '-vf fps=N'（single_frame 模式忽略）
    scale    : '-vf scale=W:-1'（None 不缩放）
    q        : '-q:v N'（JPEG 质量，仅 jpg 输出时有用）
    single_frame : 截单帧（'-frames:v 1'，常配合 start）
    """
    src = Path(src)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    ext = '.jpg' if q is not None else '.png'
    fmt = os.path.join(outdir, f'f%05d{ext}')

    vf = []
    if not single_frame:
        vf.append(f'fps={fps}')
    if scale:
        vf.append(f'scale={scale}:-1:flags=lanczos')
    args = [ffmpeg_exe(), '-y']
    if start is not None and duration is not None:
        args += ['-ss', str(start), '-t', str(duration)]
    elif start is not None and end is not None:
        args += ['-ss', str(start), '-to', str(end)]
    args += ['-i', str(src)]
    if single_frame:
        args += ['-frames:v', '1']
    if vf:
        args += ['-vf', ','.join(vf)]
    if ext == '.png':
        args += ['-pix_fmt', 'rgb24']
    if q is not None:
        args += ['-q:v', str(q)]
    args += [fmt]
    r = subprocess.run(args, capture_output=True, text=True)
    return r.returncode, list_frames(outdir, ext)


# ============== 子命令函数 ==============

def hifps2():
    """BV1CkcbzgEkC 0-15s 60fps 高密度抽帧（之前 12fps alias 严重）"""
    out = ROOT / 'frames_hifps2'
    reset_out(out)
    rc, files = ffmpeg_extract(
        REF_VIDEO / 'iris_pulse.f30080.mp4', out,
        start=0, duration=15, fps=60, scale=1280,
    )
    print(f'60fps frames: {len(files)} (expected ~900, rc={rc})')


def hifps_crop():
    """egg.mp4 高帧率抽帧 → 眼部归一化 160x160 → 写入 eye_crops/"""
    import json
    from PIL import Image

    out_full = ROOT / 'frames_hifps'
    reset_out(out_full)
    rc, files = ffmpeg_extract(
        REF_VIDEO / 'egg.mp4', out_full,
        start=21, end=43, fps=12, scale=1920,
    )
    print(f'hifps frames: {len(files)} rc={rc}')

    crop_dir = ROOT / 'eye_crops'
    reset_out(crop_dir)
    meta = []

    def find_eye(img):
        im = img.convert('RGB'); W, H = im.size; px = im.load()
        step = 4
        xs, ys = [], []
        for y in range(0, H, step):
            for x in range(0, W, step):
                r, g, b = px[x, y]
                if b > 150 and b - r > 110 and b - g > 70 and g < 130:
                    xs.append(x); ys.append(y)
        if len(xs) < 30:
            return None
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        w, h = x1 - x0, y1 - y0
        if w < 20 or h < 20 or not (0.5 < w / h < 2.0):
            return None
        return (x0 + x1) // 2, (y0 + y1) // 2, (w + h) / 4

    for f in files:
        img = Image.open(f)
        res = find_eye(img)
        if not res:
            continue
        cx, cy, r = res
        R = max(int(r * 1.55), 24)
        crop = img.crop((cx - R, cy - R, cx + R, cy + R)).convert('RGB').resize((160, 160), Image.LANCZOS)
        crop.save(crop_dir / f.name)
        meta.append({'f': f.name, 'cx': cx, 'cy': cy, 'r': r})

    (ROOT / 'eye_crops_meta.json').write_text(
        json.dumps(meta, ensure_ascii=False), encoding='utf-8')
    print(f'eye crops: {len(meta)}')


def egg_voice():
    """egg.mp4 / voice.mp4 全片 2fps 抽帧（voice.mp4 不可用，已记录）"""
    for src_name, out_name in [('egg.mp4', 'frames_egg'), ('voice.mp4', 'frames_voice')]:
        out = ROOT / out_name
        reset_out(out, ext='.jpg')
        rc, files = ffmpeg_extract(
            REF_VIDEO / src_name, out,
            fps=2, scale=960, q=3,
        )
        print(f'{out_name}: {len(files)} frames (rc={rc})')


def events():
    """提取 5 个关键时刻前后 0.4s 共 5x24 帧 + Playwright 拼接对比图"""
    events_list = [
        (0.583, 'event_0583'),
        (2.383, 'event_2383'),
        (6.750, 'event_6750'),
        (9.617, 'event_9617'),
        (11.183, 'event_11183'),
    ]
    src = REF_VIDEO / 'iris_pulse.f30080.mp4'
    for t, name in events_list:
        out = ROOT / f'frames_evt_{name}'
        reset_out(out)
        rc, _ = ffmpeg_extract(src, out, start=t - 0.2, duration=0.4,
                               fps=60, scale=1280)
        print(f'{name}: t={t}s, frames generated (rc={rc})')

    # 拼接 grid
    from playwright.sync_api import sync_playwright
    out = ROOT / 'compare_events'
    reset_out(out)
    rows_html = ''.join(
        f'<tr><td>{name}<br>t={t}s</td>' +
        ''.join(f'<td><img src="{(ROOT / f"frames_evt_{name}" / f"f{i:03d}.png").as_posix()}"></td>'
                for i in [1, 9, 17, 24]) +
        '</tr>'
        for t, name in events_list
    )
    html = f"""<style>body{{margin:0;background:#111;color:#fff;font:14px monospace}}
        table{{border-collapse:collapse}}td{{padding:4px 8px;border:1px solid #444}}
        img{{display:block;width:320px;height:240px}}</style>
        <table><tr><th>event</th><th>frame 1</th><th>frame 9</th><th>frame 17</th><th>frame 24</th></tr>
        {rows_html}</table>"""
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome')
        page = b.new_page(viewport={'width': 1280, 'height': 720})
        page.goto('about:blank')
        page.set_content(html)
        page.wait_for_timeout(1000)
        page.screenshot(path=str(out / 'events_grid.png'), full_page=True)
        b.close()
    print('Done:', out / 'events_grid.png')


def full_frames():
    """BV1CkcbzgEkC 5 个时刻的整帧（供主人指认眼睛）"""
    out = ROOT / 'full_frames'
    reset_out(out)
    src = REF_VIDEO / 'iris_pulse.f30080.mp4'
    for t in [0.5, 3.0, 7.0, 11.0, 14.0]:
        _, _ = ffmpeg_extract(src, out, start=t, scale=1280, single_frame=True)
    print('saved:', sorted([p.name for p in out.iterdir()]))


def right_eye():
    """抽 0-15s 每 1s 一帧右眼区域 → 网格图"""
    import math
    from PIL import Image

    tmp = ROOT / 'right_eye_seq'
    reset_out(tmp)
    src = REF_VIDEO / 'iris_pulse.f30080.mp4'
    times = [round(i * 1.0, 1) for i in range(16)]

    for i, t in enumerate(times):
        # 单帧输出到 _full{i}.png
        subprocess.run(
            [ffmpeg_exe(), '-y', '-ss', str(t), '-i', str(src), '-frames:v', '1',
             str(tmp / f'_full{i:02d}.png')],
            capture_output=True, text=True,
        )

    crops = []
    for i, t in enumerate(times):
        im = Image.open(tmp / f'_full{i:02d}.png').convert('RGB')
        W, H = im.size
        sx = W / 1280.0
        cx, cy, R = int(890 * sx), int(301 * sx), int(240 * sx)
        crops.append(im.crop((cx - R, cy - R, cx + R, cy + R)).resize((220, 220), Image.LANCZOS))

    COLS, ROWS = 4, 4
    grid = Image.new('RGB', (COLS * 220, ROWS * 220), (0, 0, 0))
    for i, c in enumerate(crops):
        grid.paste(c, ((i % COLS) * 220, (i // COLS) * 220))
    out = ROOT / 'compare_events'
    out.mkdir(parents=True, exist_ok=True)
    grid.save(out / 'right_eye_seq_1s.png')
    print('saved', out / 'right_eye_seq_1s.png', grid.size)

    # 清掉中间 _full 帧
    for f in tmp.iterdir():
        if f.name.startswith('_full'):
            f.unlink()


def boot_idle():
    """boot.f30080.mp4 (0-80s @ 1fps) + idle.f30080.mp4 (全片 @ 2fps) 抽帧

    用途：将来 boot 动画分析（待办项）。
    注意：原 extract_frames.py 把输出写到 ref_video/ 子目录。
    """
    base = REF_VIDEO / 'frames_boot'
    base.mkdir(parents=True, exist_ok=True)
    for f in base.iterdir():
        if f.suffix.lower() == '.jpg':
            f.unlink()
    rc, _ = ffmpeg_extract(
        REF_VIDEO / 'boot.f30080.mp4', base,
        start=0, duration=80, fps=1, scale=960, q=3,
    )
    print(f'boot frames: {len(list(base.iterdir()))} (rc={rc})')

    base = REF_VIDEO / 'frames_idle'
    base.mkdir(parents=True, exist_ok=True)
    for f in base.iterdir():
        if f.suffix.lower() == '.jpg':
            f.unlink()
    rc, _ = ffmpeg_extract(
        REF_VIDEO / 'idle.f30080.mp4', base,
        fps=2, scale=960, q=3,
    )
    print(f'idle frames: {len(list(base.iterdir()))} (rc={rc})')


# ============== argparse ==============

DISPATCH = {
    'hifps2': hifps2,
    'hifps_crop': hifps_crop,
    'egg-voice': egg_voice,
    'events': events,
    'full-frames': full_frames,
    'right-eye': right_eye,
    'boot-idle': boot_idle,
}


def main():
    p = argparse.ArgumentParser(description='fairy-pet 抽帧工具')
    p.add_argument('cmd', choices=sorted(DISPATCH.keys()))
    args = p.parse_args()
    DISPATCH[args.cmd]()


if __name__ == '__main__':
    main()