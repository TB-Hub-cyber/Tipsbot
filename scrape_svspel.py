# -*- coding: utf-8 -*-
# scrape_svspel.py – hämtar kupongsida och plockar ut matchnr, lag och odds.
# Bygger på Playwright + BeautifulSoup. Säker mot "Url-objekt" (str(url) i goto).

from typing import Dict, Any, List
import asyncio
import os
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# Se till att Playwright använder en skrivbar cache på Render
PW_CACHE = "/opt/render/.cache/ms-playwright"
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", PW_CACHE)

# Modern Chrome-UA (kan utökas om det behövs)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


async def _open_page(url: str):
    """Öppnar sidan och returnerar HTML (eller kastar fel med status)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        ctx = await browser.new_context(
            user_agent=UA,
            locale="sv-SE",
            timezone_id="Europe/Stockholm",
            viewport={"width": 1366, "height": 850},
        )
        page = await ctx.new_page()
        # VIKTIGT: konvertera alltid till sträng
        resp = await page.goto(str(url), wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

        if not resp or (resp.status and resp.status >= 400):
            status = resp.status if resp else "No response"
            await ctx.close(); await browser.close()
            raise RuntimeError(f"Svs-fel: status {status}")

        html = await page.content()

        # Spara debugfiler som hjälp vid felsökning
        try:
            await page.screenshot(path="/tmp/svs_debug.png", full_page=True)
            with open("/tmp/svs_debug.html", "w", encoding="utf-8") as f:
                f.write(html)
        except Exception:
            pass

        await ctx.close(); await browser.close()
        return html


def _parse_matches(html: str) -> List[Dict[str, Any]]:
    """
    Försöker hitta 13 rader med matchnummer, lag och odds.
    Vi använder både CSS-klasser (om de finns) och fallback-regex.
    'Svenska folket' varierar i DOM – vi lämnar den tom tills vi stabilt kan fånga den.
    """
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict[str, Any]] = []

    # 1) Försök med semantiska klassnamn om de finns
    rows = soup.select("div.sry-match-row, li.MatchRow, div.match-row")
    for i, row in enumerate(rows, start=1):
        # matchnummer
        nr = None
        nr_el = row.select_one(".sry-match-row__number, .MatchRow-number, .match-number")
        if nr_el:
            nr = nr_el.get_text(strip=True)
            try:
                nr = int(re.sub(r"\D+", "", nr))
            except Exception:
                nr = i  # fallback
        else:
            nr = i

        # lag
        h = row.select_one(".sry-match-row__team--home, .team-home, .home, .MatchRow-home")
        a = row.select_one(".sry-match-row__team--away, .team-away, .away, .MatchRow-away")
        home = (h.get_text(strip=True) if h else "").strip()
        away = (a.get_text(strip=True) if a else "").strip()

        # odds (tre värden)
        odds_els = row.select(".sry-odds__value, .odds__value, .odds")
        odds_vals = [el.get_text(strip=True) for el in odds_els][:3]
        if len(odds_vals) < 3:
            # prova regex lokalt på raden
            txt = row.get_text(" ", strip=True)
            m = re.findall(r"(\d+(?:[.,]\d+)?)", txt)
            if len(m) >= 3:
                odds_vals = m[:3]

        if home and away and len(odds_vals) == 3:
            o1, ox, o2 = (v.replace(",", ".") for v in odds_vals)
            try:
                out.append({
                    "matchnr": int(nr),
                    "hemmalag": home,
                    "bortalag": away,
                    "odds_1": float(o1),
                    "odds_x": float(ox),
                    "odds_2": float(o2),
                    # lämnar folk tomt tills vi fångar stabilt:
                    "folk_1": None, "folk_x": None, "folk_2": None,
                })
            except Exception:
                pass

    # 2) Om det inte lyckades – global fallback via regex på hela HTML
    if not out:
        titles = re.findall(
            r'>([A-Za-zÅÄÖåäö0-9\.\'’\-\/& ]+?)\s*-\s*([A-Za-zÅÄÖåäö0-9\.\'’\-\/& ]+?)<',
            html
        )
        odds = re.findall(
            r'Odds[^0-9]*(\d+(?:[.,]\d+)?)[^\d]+(\d+(?:[.,]\d+)?)[^\d]+(\d+(?:[.,]\d+)?)',
            html, re.S | re.I
        )
        n = min(len(titles), len(odds))
        for i in range(n):
            h, a = titles[i][0].strip(), titles[i][1].strip()
            o1, ox, o2 = (x.replace(",", ".") for x in odds[i])
            try:
                out.append({
                    "matchnr": i + 1,
                    "hemmalag": h, "bortalag": a,
                    "odds_1": float(o1), "odds_x": float(ox), "odds_2": float(o2),
                    "folk_1": None, "folk_x": None, "folk_2": None,
                })
            except Exception:
                pass

    return out


async def fetch_kupong(url: str, debug: bool = False) -> Dict[str, Any]:
    """
    Lyckat:  { "results": [ {matchnr, hemmalag, bortalag, odds_* ...}, ... ] }
    Vid fel: { "error": "text" }
    """
    html = await _open_page(url)
    rows = _parse_matches(html)
    if not rows:
        return {"error": "Inga matcher hittades på sidan."}
    return {"results": rows}
