# -*- coding: utf-8 -*-
# scrape_svspel.py – robust hämtning av kupongsida från Svenska Spel

from typing import Dict, Any, Tuple, Optional, List
import asyncio, os, re
from playwright.async_api import async_playwright

PW_CACHE = "/opt/render/.cache/ms-playwright"
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", PW_CACHE)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

def _anti_detect_js() -> str:
    return r"""
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4] });
Object.defineProperty(navigator, 'languages', { get: () => ['sv-SE','sv','en-US','en'] });
"""

async def _ensure_chromium() -> None:
    # Installera browser om cache saknas
    ok = False
    if os.path.isdir(PW_CACHE):
        for r, _, files in os.walk(PW_CACHE):
            if "chrome" in files:
                ok = True
                break
    if not ok:
        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "playwright", "install", "chromium",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()

async def _open_and_get_html(url: str, debug: bool) -> Tuple[str, Optional[int]]:
    """Öppnar sidan och returnerar (html, status). Höga timeouts + networkidle."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--disable-blink-features=AutomationControlled"]
        )
        ctx = await browser.new_context(
            user_agent=UA, locale="sv-SE", timezone_id="Europe/Stockholm",
            viewport={"width": 1366, "height": 850},
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        await ctx.add_init_script(_anti_detect_js())
        page = await ctx.new_page()
        page.set_default_timeout(60_000)  # 60 sek

        resp = await page.goto(str(url), wait_until="domcontentloaded", timeout=60_000)
        # ge nätverket chans att bli idle
        try:
            await page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass

        html = await page.content()
        status = None
        try:
            if resp:
                status = resp.status
        except Exception:
            status = None

        if debug:
            try:
                await page.screenshot(path="/tmp/svs_debug.png", full_page=True)
                with open("/tmp/svs_debug.html", "w", encoding="utf-8") as f:
                    f.write(html)
            except Exception:
                pass

        await ctx.close(); await browser.close()
        return html, status

def _parse(html: str) -> List[Dict[str, Any]]:
    """Tolerant parser för matchnr, lag och odds."""
    rows: List[Dict[str, Any]] = []

    # Försök 1: CSS-liknande mönster
    # (behåller regex för att överleva DOM-ändringar)
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
            rows.append({
                "matchnr": i + 1,
                "hemmalag": h, "bortalag": a,
                "odds_1": float(o1), "odds_x": float(ox), "odds_2": float(o2),
                "folk_1": None, "folk_x": None, "folk_2": None,
            })
        except Exception:
            continue

    return rows

async def fetch_kupong(url: str, debug: bool = False) -> Dict[str, Any]:
    """
    Lyckat:  { "results": [ {...}, ... ] }
    Fel:     { "error": "text" }
    """
    await _ensure_chromium()

    backoffs = [5, 8, 12]  # sekunder
    last_err = None
    last_status = None

    for i, pause in enumerate(backoffs, start=1):
        try:
            html, status = await _open_and_get_html(url, debug)
            last_status = status

            low = html.lower()
            if ("cloudflare" in low or "captcha" in low or "access denied" in low) or (status and status >= 500):
                last_err = f"Blockerad/5xx (försök {i})."
                await asyncio.sleep(pause)
                continue

            rows = _parse(html)
            if not rows:
                last_err = "Inga matcher hittades på sidan."
                await asyncio.sleep(pause if i < len(backoffs) else 0)
                continue

            return {"results": rows}
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            await asyncio.sleep(pause)

    # efter alla försök
    msg = last_err or f"Misslyckades efter {len(backoffs)} försök."
    if last_status:
        msg += f" (HTTP {last_status})"
    return {"error": msg}

# kompatibilitet med tidigare importmönster
run = fetch_kupong

async def fetch_kupong_entry(url: str, debug: bool = False) -> Tuple[Dict[str, Any], int]:
    out = await fetch_kupong(url, debug=debug)
    return out, 0
