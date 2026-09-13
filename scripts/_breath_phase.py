# -*- coding: utf-8 -*-
"""呼吸相位实测: 逐帧测四个同心圆的缩放, 找出各环"谷"时刻, 验证由内向外 50ms 延迟。
用法: python scripts/_breath_phase.py
"""
import asyncio
import json
import pathlib

from playwright.async_api import async_playwright

HTML = pathlib.Path(r"D:\work\fairy_pet\dev\fairy-lab.html")
OUT = pathlib.Path(r"D:\work\fairy_pet\dev\breath_phase.json")

COLLECT_JS = """
() => new Promise(res => {
  const C = [['irisPupil',19.9],['irisMid',28.1],['lySlate',41.5],['lyWhite',62.2]];
  const out = []; const t0 = performance.now();
  function tick(){
    const row = {t: +(performance.now()-t0).toFixed(1)};
    for (const [id,r] of C){
      const w = document.getElementById(id).getBoundingClientRect().width;
      row[id] = +(w/(2*r)).toFixed(4);
    }
    out.push(row);
    if (performance.now()-t0 < 2000) requestAnimationFrame(tick); else res(out);
  }
  tick();
})
"""


def first_valley_times(rows, key):
    """返回每个"局部极小段"的起始时刻(ms)。缩放先停后升, 谷是一段平台, 取平台起点。"""
    vals = [r[key] for r in rows]
    ts = [r["t"] for r in rows]
    mn = min(vals)
    thr = mn + (max(vals) - mn) * 0.15
    times, i, n = [], 0, len(vals)
    while i < n:
        if vals[i] <= thr:
            j = i
            while j + 1 < n and vals[j + 1] <= thr:
                j += 1
            if i > 0:
                times.append(ts[i])
            i = j + 1
        else:
            i += 1
    return times


def mean_period(times):
    if len(times) < 2:
        return None
    ds = [b - a for a, b in zip(times, times[1:])]
    # 去掉因采样跨度过大造成的半周期误判: 取众数附近的均值
    ds = [d for d in ds if d < 1500]
    return sum(ds) / len(ds) if ds else None


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome")   # 复用本机 Chrome(无打包 chromium)
        pg = await b.new_page(viewport={"width": 900, "height": 900})
        await pg.goto(HTML.as_uri())
        await pg.wait_for_timeout(1500)          # 等 begin 延迟(<=150ms)结束, 进入稳态
        rows = await pg.evaluate(COLLECT_JS)
        await b.close()

    keys = ["irisPupil", "irisMid", "lySlate", "lyWhite"]
    report = {"samples": len(rows), "span_ms": rows[-1]["t"], "rings": {}}
    base = None
    for k in keys:
        tv = first_valley_times(rows, k)
        per = mean_period(tv)
        base = tv[1] if len(tv) > 1 else (tv[0] if tv else None)
        report["rings"][k] = {
            "min": min(r[k] for r in rows),
            "max": max(r[k] for r in rows),
            "valleys_ms": tv,
            "period_ms": round(per, 1) if per else None,
            "first_valley_ms": base,
        }

    # 相位: 每个环的谷相对最内环的谷 提前/滞后(按周期折叠, 消掉启动段)
    inner = report["rings"]["irisPupil"]["valleys_ms"]
    T = report["rings"]["irisPupil"]["period_ms"] or 860.0
    if inner:
        ref = inner[0]
        for k in keys[1:]:
            tv = report["rings"][k]["valleys_ms"]
            lags = [(t - ref) % T for t in tv] if tv else []
            report["rings"][k]["lag_vs_pupil_ms"] = round(min(lags), 1) if lags else None

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"samples={report['samples']} span={report['span_ms']}ms")
    for k in keys:
        r = report["rings"][k]
        lag = r.get("lag_vs_pupil_ms", 0)
        print(f"{k:<10} scale {r['min']:.3f}~{r['max']:.3f}  谷@ {r['valleys_ms']}  lag={lag}")
    print(f"\n-> {OUT}")


asyncio.run(main())
