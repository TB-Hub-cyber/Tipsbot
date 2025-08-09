# -*- coding: utf-8 -*-
# scrape_stryket.py – Async-scraper för https://www.stryketanalysen.se/stryktipset/
# Returnerar {"results":[{ matchnr, hemmalag, bortalag, odds_1, odds_x, odds_2,
#                          folk_1, folk_x, folk_2, spelv_1, spelv_x, spelv_2 }]}
# eller {"error": "..."}.
#
# Körs från main.py med:
#   out = await fetch_stryket(url, debug=True/False)

from typing import Dict, Any, List, Optional, Iterable
import re
from bs4 import BeautifulSoup, Tag, NavigableString
from playwright.async_api import async_playwright

# ----------------------------- Regex & helpers ------------------------------

NAME = r"[A-Za-zÅÄÖåäö0-9\.\-’'&() ]+"

# Viktigt: bindestrecket MÅSTE ha mellanslag runt sig ("Halmstad - Sirius")
TITLE_RX = re.compile(fr"({NAME})\s-\s({NAME})")

NUM_RX = re.compile(r"(\d+(?:[.,]\d+)?)")
PCT_RX = re.compile(r"(\d{1,2})\s*%")

LABELS_ORDER = ["Odds", "Start-odds", "Svenska folket", "Spelvärde", "Tio Tidningar"]

def _to_float(s: str) -> Optional[float]:
    s = (s or "").strip().replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def _to_int(s: str) -> Optional[int]:
    s = re.sub(r"[^\d]", "", (s or ""))
    try:
        return int(s)
    except Exception:
        return None

def _section_after_label(text: str, label: str) -> str:
    i = text.find(label)
    if i < 0:
        return ""
    rest = text[i + len(label):]
    stop = len(rest)
    for lb in LABELS_ORDER:
        j = rest.find(lb)
        if j >= 0:
            stop = min(stop, j)
    return rest[:stop]

def _pick_three_floats(text: str):
    nums = NUM_RX.findall(text)
    vals = list(map(_to_float, nums[:3]))
    while len(vals) < 3:
        vals.append(None)
    return vals

def _pick_three_pcts(text: str):
    pcs = PCT_RX.findall(text)
    vals = list(map(_to_int, pcs[:3]))
    while len(vals) < 3:
        vals.append(None)
    return vals

def _nearest_match_container(node: Tag) -> Optional[Tag]:
    """Från en label-nod (t.ex. 'Svenska folket') klättra uppåt tills vi hittar ett block
    som även innehåller titel 'Lag - Lag' och texten 'Odds'."""
    cur: Optional[Tag] = node
    for _ in range(8):
        if cur is None:
            return None
        txt = " ".join(cur.stripped_strings)
        # Sök titel endast i prefix före 'Odds' (undviker 'Start-odds')
        prefix = txt.split("Odds", 1)[0] if "Odds" in txt else txt
        if "Odds" in txt and TITLE_RX.search(prefix):
            return cur
        cur = cur.parent if isinstance(cur.parent, Tag) else None
    return None

# ------------------------------- Parser -------------------------------------

def _parse(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    results: List[Dict[str, Any]] = []

    # 1) Primär: hitta varje matchblock via labeln "Svenska folket"
    folk_labels: Iterable[Tag] = soup.find_all(string=re.compile(r"^\s*Svenska folket\s*$", re.I))
    containers: List[Tag] = []
    for lbl in folk_labels:
        node = lbl if isinstance(lbl, Tag) else (lbl.parent if isinstance(lbl, NavigableString) else None)
        cont = _nearest_match_container(node) if isinstance(node, Tag) else None
        if cont and cont not in containers:
            containers.append(cont)

    # 2) Fallback: generiska block som innehåller titel + Odds + Svenska folket
    if not containers:
        for blk in soup.select(".content div, .entry-content div, li, article, .match, .match-row"):
            if not isinstance(blk, Tag):
                continue
            txt = " ".join(blk.stripped_strings)
            if "Odds" in txt and "Svenska folket" in txt:
                prefix = txt.split("Odds", 1)[0] if "Odds" in txt else txt
                if TITLE_RX.search(prefix):
                    containers.append(blk)

    # 3) Fallback: tabellrader
    if not containers:
        for tr in soup.select("table tr"):
            txt = " ".join(tr.stripped_strings)
            if "Odds" in txt:
                prefix = txt.split("Odds", 1)[0]
                if TITLE_RX.search(prefix):
                    containers.append(tr)

    # 4) Plocka fält ur respektive container
    for cont in containers:
        txt = " ".join(cont.stripped_strings)

        # Sök titel enbart i texten före "Odds"
        prefix = txt.split("Odds", 1)[0] if "Odds" in txt else txt
        m = TITLE_RX.search(prefix)
        if not m:
            continue
        home = m.group(1).strip()
        away = m.group(2).strip()

        odds_txt = _section_after_label(txt, "Odds")
        folk_txt = _section_after_label(txt, "Svenska folket")
        sv_txt   = _section_after_label(txt, "Spelvärde")

        o1, ox, o2 = _pick_three_floats(odds_txt)
        f1, fx, f2 = _pick_three_pcts(folk_txt)
        s1, sx, s2 = _pick_three_floats(sv_txt)

        results.append({
            "matchnr": len(results) + 1,
            "hemmalag": home, "bortalag": away,
            "odds_1": o1, "odds_x": ox, "odds_2": o2,
            "folk_1": f1, "folk_x": fx, "folk_2": f2,
            "spelv_1": s1, "spelv_x": sx, "spelv_2": s2,
        })

    # 5) Deduplicera + numrera 1..13
    seen = set()
    unique: List[Dict[str, Any]] = []
    for r in results:
        key = (r["hemmalag"], r["bortalag"], r["odds_1"], r["odds_x"], r["odds_2"],
               r["folk_1"], r["folk_x"], r["folk_2"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    for i, r in enumerate(unique[:13], start=1):
        r["matchnr"] = i

    return unique[:13]

# ------------------------------- Scraper ------------------------------------

async def fetch_stryket(url_obj, debug: bool = False) -> Dict[str, Any]:
    """
    Async Playwright:
      - renderar sidan
      - väntar in 'Svenska folket' (eller 'Odds' som fallback)
      - scrollar för att trigga lazyload
      - sparar debug-HTML/PNG om debug=True
      - parser och returnerar 13 matcher
    """
    url = str(url_obj).strip()
    if not url:
        return {"error": "Ingen URL angiven."}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage", "--disable-gpu",
                ],
            )
            ctx = await browser.new_context(user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ))
            page = await ctx.new_page()

            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)

            # Vänta in att matchrutor finns (”Svenska folket” eller ”Odds”)
            try:
                await page.wait_for_selector(":text('Svenska folket')", timeout=25_000)
            except Exception:
                await page.wait_for_selector(":text('Odds')", timeout=10_000)

            # Scrolla genom sidan för att trigga ev. lazyload
            await page.evaluate(
                """() => new Promise(res => {
                    let y = 0, step = 1200, limit = 10, i = 0;
                    const t = setInterval(() => {
                        window.scrollBy(0, step); y += step; i += 1;
                        if (i >= limit || y > document.body.scrollHeight * 2) {
                            clearInterval(t); setTimeout(res, 900);
                        }
                    }, 250);
                })"""
            )

            await page.wait_for_timeout(900)
            html = await page.content()

            if debug:
                try:
                    await page.screenshot(path="/tmp/stryket_debug.png", full_page=True)
                    with open("/tmp/stryket_debug.html", "w", encoding="utf-8") as f:
                        f.write(html)
                except Exception:
                    pass

            await browser.close()

        rows = _parse(html)
        if not rows:
            return {"error": "Hittade inga matcher på sidan."}

        return {"results": rows}

    except Exception as e:
        return {"error": str(e)}
