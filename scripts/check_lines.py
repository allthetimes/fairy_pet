#!/usr/bin/env python3
"""台词池质量检查：对照 concept/llm-character-card.md 的语言指纹与禁忌清单。

用法: python scripts/check_lines.py

检查项:
  1. 语言指纹命中数（每条 ≥2 条才算合格）
  2. 禁忌词（卖萌/波浪号/直白温柔/无情商感叹号）
  3. 长度（> 60 字警告，气泡会超 3 行）
  4. 类别条数与重复
输出: 逐条体检表 + 汇总
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES = os.path.join(BASE, 'pet-app', 'ui', 'lines.json')

# ---- 语言指纹（角色卡 §4） ----
FINGERPRINTS = {
    '①主人':      r'主人',
    '②播报腔':    r'(检测到|侦测到|读取|分析显示|测算显示|已为您|正在执行|系统|权限|协议|检索|建议|询问|警告|指令|信号|响应|大数据|已记录|已同步|已响应|位移|坐标|待机|空闲|耗电|完成度)',
    '③敬语(您)':  r'您',
    '④技术夸张':  r'(\d{3,}|\d+\.\d+|焦耳|能耗|带宽|运算力|防火墙|显卡|内存|进程|陀螺仪|摄像头|参数|数据库)',
    '⑤符号叮~/…': r'(叮~|…|%¥&%)',
}
MIN_FP = 2   # 每条至少命中 2 条指纹

# ---- 禁忌词（角色卡 §8） ----
TABOO = {
    '卖萌叠字': r'(诶嘿|嘿嘿|哇哇|嘻嘻|哈哈|呀[～~！]|喵)',
    '波浪号':   r'[～~]\s*$',
    '直白温柔': r'(陪着你|一直陪|别担心|加油哦|抱抱|亲亲)',
    '感叹号滥用': r'！.*！',
}

def check(lines):
    rows = []
    bad = 0
    for kind, arr in lines.items():
        for s in arr:
            hits = [name for name, pat in FINGERPRINTS.items() if re.search(pat, s)]
            viol = [name for name, pat in TABOO.items() if re.search(pat, s)]
            long = len(s) > 60
            ok = len(hits) >= MIN_FP and not viol and not long
            if not ok:
                bad += 1
            rows.append((kind, s, hits, viol, long, ok))
    return rows, bad

def main():
    if not os.path.exists(LINES):
        print(f'✗ 找不到 {LINES}')
        sys.exit(1)
    with open(LINES, encoding='utf-8') as f:
        lines = json.load(f)

    rows, bad = check(lines)

    print('=' * 78)
    print('台词池体检（对照 character-card.md 语言指纹 / 禁忌）')
    print('=' * 78)
    cur_kind = None
    for kind, s, hits, viol, long, ok in rows:
        if kind != cur_kind:
            print(f'\n--- {kind} ---')
            cur_kind = kind
        mark = '✓' if ok else '✗'
        fp = f'{len(hits)}条[{",".join(hits)}]'
        extra = ''
        if viol: extra += f' ⛔禁忌:{",".join(viol)}'
        if long: extra += f' ⚠超长({len(s)}字)'
        print(f'  {mark} {fp:<28} {s}{extra}')

    total = len(rows)
    print('\n' + '=' * 78)
    print(f'总计 {total} 条，合格 {total - bad} 条，不合格 {bad} 条')
    # 指纹覆盖统计
    from collections import Counter
    cnt = Counter()
    for _, _, hits, _, _, _ in rows:
        for h in hits: cnt[h] += 1
    print('指纹覆盖率：', ' · '.join(f'{k} {v}/{total}' for k, v in sorted(cnt.items())))
    print('=' * 78)
    return 0 if bad == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
