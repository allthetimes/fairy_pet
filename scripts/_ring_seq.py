"""拼接 ring_anim 7 帧呼吸序列为一张拼版图"""
from PIL import Image, ImageDraw
import glob

paths = sorted(glob.glob('analysis/ring_anim2/r_*.png'))
print(f'共 {len(paths)} 帧')

if not paths:
    print('没有 r_*.png 文件')
    exit(1)

ims = [Image.open(p).convert('RGB') for p in paths]

# 每帧裁剪到 Fairy 区域 (450x450 中央)
def crop_fairy(im, side=420):
    W, H = im.size
    return im.crop((W//2 - side//2, H//2 - side//2 + 30,
                    W//2 + side//2, H//2 + side//2 + 30))

crops = [crop_fairy(im) for im in ims]
W = H = 420
gap = 12
top_label = 40
canvas = Image.new('RGB', (W*len(crops) + gap*(len(crops)+1), H + top_label + 30), (15, 18, 30))
d = ImageDraw.Draw(canvas)
for i, (crop, p) in enumerate(zip(crops, paths)):
    x = gap + i*(W + gap)
    canvas.paste(crop, (x, top_label))
    d.rectangle([x, top_label, x+W-1, top_label+H-1], outline=(80, 110, 180), width=2)
    # 时间标签 (从文件名解析)
    t = p.split('_t')[-1].split('.png')[0]
    d.text((x + 8, 8), f't={t}s', fill=(255, 220, 110))

canvas.save('analysis/_ring_breath_seq.png')
print('saved')