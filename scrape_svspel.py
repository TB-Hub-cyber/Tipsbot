import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

SVS_URL = "https://www.svenskaspel.se/stryktipset"

async def _open_page(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        page = await browser.new_page()
        
        # Viktigt: Gör om URL till ren sträng innan vi skickar till page.goto()
        resp = await page.goto(str(url), wait_until="domcontentloaded")
        
        if not resp or resp.status != 200:
            await browser.close()
            raise Exception(f"Svs-fel: status {resp.status if resp else 'No response'}")
        
        html = await page.content()
        await browser.close()
        return html

async def fetch_svs_matches():
    html = await _open_page(SVS_URL)
    soup = BeautifulSoup(html, "html.parser")

    matches = []
    match_elements = soup.select("div.sry-match-row")
    
    if not match_elements:
        raise Exception("Svs-fel: Inga matcher hittades på sidan.")
    
    for m in match_elements:
        try:
            match_number = m.select_one(".sry-match-row__number").get_text(strip=True)
            home_team = m.select_one(".sry-match-row__team--home").get_text(strip=True)
            away_team = m.select_one(".sry-match-row__team--away").get_text(strip=True)
            odds = [o.get_text(strip=True) for o in m.select(".sry-odds__value")]
            
            matches.append({
                "match_number": match_number,
                "home_team": home_team,
                "away_team": away_team,
                "odds": odds
            })
        except Exception:
            continue
    
    return matches

if __name__ == "__main__":
    matches = asyncio.run(fetch_svs_matches())
    for m in matches:
        print(f"{m['match_number']}: {m['home_team']} - {m['away_team']} (odds: {', '.join(m['odds'])})")
