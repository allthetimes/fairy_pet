from PIL import Image, ImageDraw
import numpy as np

paths = [
    ('analysis/lid_v7.png', 'code_v7', '底边 r=200 浅弧, 挂 irisPulse'),
    ('analysis/v2_closed/f_00002.png', 'hero_real', '完整 Fairy 参考'),
]

def find_fairy(im):
    arr = np.asarray(im.convert('RGB')).astype(np.int32)
    R, G, B = arr[...,0], arr[...,1], arr[...,2]
    blue = ((B - R) > 50) & (B > 100)
    ys, xs = np.where(blue)
    if len(xs) == 0: return None
    sorted_idx = np.argsort(xs)
    n = len(xs); cut = n // 10
    xs = xs[sorted_idx[cut:-cut]]; ys = ys[sorted_idx[cut:-cut]]
    cy, cx = int(ys.mean()), int(xs.mean())
    d = np.sqrt((xs-cx)**2 + (ys-cy)**2)
    r = int(np.percentile(d, 80))
    return cx, cy, r

crops = []
for path_img, title, desc in paths:
    im = Image.open(path_img).convert('RGB')
    res = find_fairy(im)
    if res:
        cx, cy, r = res
        side = int(r * 2.4)
        x0 = max(0, cx-side//2); y0 = max(0, cy-side//2)
        x1 = min(im.width, cx+side//2); y1 = min(im.height, cy+side//2)
        crop = im.crop((x0, y0, x1, y1)).resize((400, 400), Image.LANCZOS)
        crops.append((crop, title, desc))

W = H = 400; gap = 14; top_label = 50; bot_label = 30
canvas = Image.new('RGB', (W*2 + gap*3, H + top_label + bot_label), (15, 18, 30))
d = ImageDraw.Draw(canvas)
for i, (crop, title, desc) in enumerate(crops):
    x = gap + i*(W + gap)
    canvas.paste(crop, (x, top_label))
    d.rectangle([x, top_label, x+W-1, top_label+H-1], outline=(80, 110, 180), width=2)
    d.text((x + 8, 8), title, fill=(255, 220, 110))
    d.text((x + 8, top_label + H + 6), desc, fill=(180, 200, 240))
canvas.save('analysis/_compare_v7.png')
print('saved')