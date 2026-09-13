"""画 A 状态虹膜呼吸时序图"""
import argparse
import csv
import numpy as np
from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv')
    ap.add_argument('--out', default='analysis/iris_breath_timeline.png')
    a = ap.parse_args()

    data = []
    with open(a.csv) as f:
        for row in csv.DictReader(f):
            wo = float(row['white_outer_u']) if row['white_outer_u'] else None
            wi = float(row['white_inner_u']) if row['white_inner_u'] else None
            po = float(row['pupil_outer_u']) if row['pupil_outer_u'] else None
            data.append((wo, wi, po))

    n = len(data)
    w_arr = np.array([d[0] if d[0] is not None else 0 for d in data], dtype=float)
    i_arr = np.array([d[1] if d[1] is not None else 0 for d in data], dtype=float)
    p_arr = np.array([d[2] if d[2] is not None else 0 for d in data], dtype=float)
    t = np.arange(n) / 15.0  # 15 fps

    W, H = 1200, 500
    img = Image.new('RGB', (W, H), (20, 25, 35))
    d = ImageDraw.Draw(img)

    # 坐标
    x_margin_l, x_margin_r = 80, 30
    y_margin_t, y_margin_b = 50, 50
    plot_w = W - x_margin_l - x_margin_r
    plot_h = H - y_margin_t - y_margin_b

    # 数据范围 (u 0.3-0.7)
    u_min, u_max = 0.30, 0.70

    def x_to_px(x_val): return x_margin_l + int((x_val / (t[-1] if len(t) > 1 else 1)) * plot_w)
    def y_to_px(y_val):
        rel = (y_val - u_min) / (u_max - u_min)
        return y_margin_t + int((1 - rel) * plot_h)

    # 网格
    d.line([(x_margin_l, y_margin_t), (x_margin_l, y_margin_t + plot_h)], fill=(100, 110, 130), width=2)
    d.line([(x_margin_l, y_margin_t + plot_h), (x_margin_l + plot_w, y_margin_t + plot_h)], fill=(100, 110, 130), width=2)

    # 标签
    for u_val in [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]:
        y = y_to_px(u_val)
        d.line([(x_margin_l - 4, y), (x_margin_l, y)], fill=(100, 110, 130), width=1)
        d.text((x_margin_l - 50, y - 8), f'{u_val:.2f}', fill=(160, 180, 200))

    for i, t_val in enumerate(np.arange(0, t[-1] + 0.1, 0.5)):
        x = x_to_px(t_val)
        d.line([(x, y_margin_t + plot_h), (x, y_margin_t + plot_h + 4)], fill=(100, 110, 130), width=1)
        d.text((x - 10, y_margin_t + plot_h + 8), f'{t_val:.1f}s', fill=(160, 180, 200))

    def 画(arr, color, label):
        valid = arr > 0
        pts = [(x_to_px(t[i]), y_to_px(arr[i])) for i in range(n) if valid[i]]
        for i in range(len(pts) - 1):
            d.line([pts[i], pts[i+1]], fill=color, width=2)
        # dots
        for p in pts:
            d.ellipse([p[0]-2, p[1]-2, p[0]+2, p[1]+2], fill=color)
        return label

    l1 = 画(w_arr, (120, 200, 255), '白环内缘 (灰紫蓝)')
    l2 = 画(i_arr, (255, 180, 120), '白环外缘')
    l3 = 画(p_arr * 10, (180, 255, 180), '深眼外缘 ×10')

    # 图例
    legend_x = x_margin_l + 10
    legend_y = y_margin_t + 10
    for i, (color, label) in enumerate([
        ((120, 200, 255), l1),
        ((255, 180, 120), l2),
        ((180, 255, 180), l3),
    ]):
        d.line([(legend_x, legend_y + 10 + i*20), (legend_x + 25, legend_y + 10 + i*20)], fill=color, width=2)
        d.text((legend_x + 30, legend_y + 3 + i*20), label, fill=(220, 230, 240))

    # 标题
    d.text((W//2 - 250, 12), '常态 (A 状态) 虹膜呼吸脉冲 - BV1J9R2BNEpU 320-323s',
            fill=(255, 220, 110))

    # 计算并显示幅度
    valid_w = w_arr[w_arr > 0]
    valid_i = i_arr[i_arr > 0]
    if len(valid_w):
        amp_w = valid_w.max() - valid_w.min()
        amp_i = valid_i.max() - valid_i.min()
        msg = f'白环外幅度: {amp_w:.3f} u (±{amp_w*100/2:.1f}%)  周期 ≈ 0.5-0.7s\n'
        msg += f'白环内幅度: {amp_i:.3f} u (±{amp_i*100/2:.1f}%)  深眼几乎不动'
        d.text((W - 380, H - 80), msg, fill=(180, 220, 180))

    img.save(a.out)
    print(f'saved {a.out}')


if __name__ == '__main__':
    main()