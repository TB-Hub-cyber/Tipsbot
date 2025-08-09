from playwright.async_api import async_playwright
import re

async def fetch_kupong(url: str, debug: bool=False):
    results = []
    debug_snap = None
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"))
        await page.goto(url, wait_until="networkidle", timeout=90000)

        # cookie
        try:
            btn = page.get_by_role("button", name=lambda n: n and "acceptera" in n.lower())
            await btn.click(timeout=4000)
        except:
            pass

        await page.wait_for_timeout(1200)

        cards = page.locator("[data-testid='match-card'], .match-card, [class*='matchCard']")
        await cards.first.wait_for(timeout=15000)
        count = await cards.count()
        for i in range(count):
            await cards.nth(i).scroll_into_view_if_needed()

        for i in range(count):
            card = cards.nth(i)

            matchnr = i+1
            try:
                t = await card.locator(":text-matches('^\s*\d+\s*$')").first.text_content(timeout=800)
                matchnr = int(t.strip())
            except:
                pass

            title = await card.locator(":text(' - ')").first.text_content()
            if title and " - " in title:
                home, away = [x.strip() for x in title.split(" - ", 1)]
            else:
                home = (await card.locator("[data-testid*='home'], .home-team").first.text_content()) or ""
                away = (await card.locator("[data-testid*='away'], .away-team").first.text_content()) or ""
                home, away = home.strip(), away.strip()

            txt = await card.text_content()
            folk = [int(x) for x in re.findall(r"(\d{1,2})%", txt)[:3]]
            odds = [float(x.replace(",", ".")) for x in re.findall(r"(\d+[.,]\d+)", txt)[:3]]

            results.append({
                "match": matchnr,
                "home": home,
                "away": away,
                "folkets_1": folk[0] if len(folk)>0 else None,
                "folkets_x": folk[1] if len(folk)>1 else None,
                "folkets_2": folk[2] if len(folk)>2 else None,
                "odds_1": odds[0] if len(odds)>0 else None,
                "odds_x": odds[1] if len(odds)>1 else None,
                "odds_2": odds[2] if len(odds)>2 else None,
            })

        if debug:
            debug_snap = await page.content()
        await browser.close()

    return {"results": results, "debug": debug_snap}
