from playwright.sync_api import sync_playwright
import urllib.parse

queries = ["绝区零 fairy 眼睛", "绝区零 fairy 自我介绍", "绝区零 fairy 待机", "绝区零 fairy 觉醒 开机"]
results = []

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 900},
    )
    pg = ctx.new_page()
    for q in queries:
        url = "https://search.bilibili.com/all?keyword=" + urllib.parse.quote(q)
        try:
            pg.goto(url, timeout=30000)
            pg.wait_for_timeout(2500)
            items = pg.evaluate(
                """() => Array.from(document.querySelectorAll('.bili-video-card')).slice(0,15).map(card => {
                    const a = card.querySelector('a[href*="/video/BV"]');
                    const t = card.querySelector('.bili-video-card__info--tit');
                    const dur = card.querySelector('.bili-video-card__stats__duration');
                    return { href: a ? a.href : '', title: t ? t.textContent.trim() : '', dur: dur ? dur.textContent.trim() : '' };
                })"""
            )
            for it in items:
                if it["href"] and it["href"] not in [r["href"] for r in results]:
                    results.append(it)
        except Exception as e:
            print("ERR", q, repr(e)[:120])
    b.close()

for r in results:
    print(r["dur"], "|", r["href"], "|", r["title"][:50])
print("total:", len(results))
