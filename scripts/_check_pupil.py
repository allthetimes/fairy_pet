# -*- coding: utf-8 -*-
"""检查深眼半径改动是否生效(半径 / 滑条 / 高光联动位置)。"""
import asyncio
import pathlib

from playwright.async_api import async_playwright

HTML = pathlib.Path(r"D:\work\fairy_pet\dev\fairy-lab.html")

JS = """() => {
  const p = document.getElementById('irisPupil');
  const g = document.querySelector('#glintG > circle');
  const sl = document.getElementById('pIris');
  return {
    pupil_r: p.getAttribute('r'),
    pupil_diameter_bbox: +p.getBBox().width.toFixed(2),      // 不含 stroke, 不受 transform 影响
    slider_value: sl.value,
    slider_label: document.getElementById('vIris').textContent,
    glint_r: g.getAttribute('r'),
    glint_cx: g.getAttribute('cx'),
    glint_cy: g.getAttribute('cy'),
    glint_dist: +Math.hypot(+g.getAttribute('cx'), +g.getAttribute('cy')).toFixed(2),
    glint_static_cx: 20.2,
    glint_gap_to_pupil: +(Math.hypot(+g.getAttribute('cx'), +g.getAttribute('cy')) - +g.getAttribute('r') - +p.getAttribute('r')).toFixed(2),
    mid_r: document.getElementById('irisMid').getAttribute('r'),
    white_r: document.getElementById('lyWhite').getAttribute('r'),
  };
}"""


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome")
        pg = await b.new_page(viewport={"width": 900, "height": 900})
        await pg.goto(HTML.as_uri())
        await pg.wait_for_timeout(600)
        d = await pg.evaluate(JS)
        await b.close()
    for k, v in d.items():
        print(f"{k:<16} {v}")


asyncio.run(main())
