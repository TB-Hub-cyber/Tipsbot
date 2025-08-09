# scrape_svspel.py
from typing import Dict, Any, Tuple, Optional, List
import asyncio, time, random
from playwright.async_api import async_playwright

# Några moderna Chrome-UA som roteras
UAS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

def _anti_detect_js() -> str:
    return r"""
// Dölj automation
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4] });
Object.defineProperty(navigator, 'languages', { get: () => ['sv-SE','sv','en-US','en'] });
const _q = (window.navigator.permissions||{}).query;
if (_q) {
  window.navigator.permissions.query = (p) => (p && p.name === 'notifications')
    ? Promise.resolve({ state: 'granted' })
    : _q(p);
}
try {
  const getParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, parameter);
  };
} catch(e){}
"""

async def _open_page(pw, url: str, ua: str, debug: bool):
    chromium = pw.chromium
    browser = await chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    ctx = await browser.new_context(
        user_agent=ua,
        locale="sv-SE",
        timezone_id="Europe/Stockholm",
        viewport={"width": 1366, "height": 850},
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    await ctx.add_init_script(_anti_detect_js())
    page = await ctx.new_page()
    page.set_default_timeout(10000)

    resp = await page.goto(url, wait_until="domcontentloaded")
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass

    html = await page.content()

    # Spara debugartefakter
    if debug:
        try:
            await page.screenshot(path="/tmp/svs_debug.png", full_page=True)
            with open("/tmp/svs_debug.html", "w", encoding="utf-8") as f:
                f.write(html)
        except Exception:
            pass

    return browser, ctx, page, resp, html

def _parse_kupong_html(html: str) -> Dict[str, Any]:
    """
    Tolerant parser för kupongsidan.
    Letar efter:
      - "Lag A - Lag B"
      - "Svenska folket" följt av tre procent
      - "Odds" följt av tre tal (punkt/komma)
    """
    import re
    res = {"matcher": []}

    titles = re.findall(
        r'>([A-Za-zÅÄÖåäö0-9\.\'’\-\/& ]+?)\s*-\s*([A-Za-zÅÄÖåäö0-9\.\'’\-\/& ]+?)<',
        html
    )
    folk = re.findall(
        r'Svenska\s*folket.*?(\d{1,2})\s*%.*?(\d{1,2})\s*%.*?(\d{1,2})\s*%',
        html, re.S | re.I
    )
    odds = re.findall(
        r'Odds[^0-9]*(\d+(?:[.,]\d+)?)[^\d]+(\d+(?:[.,]\d+)?)[^\d]+(\d+(?:[.,]\d+)?)',
        html, re.S | re.I
    )

    n = min(len(titles), len(folk), len(odds))
    for i in range(n):
        h, b = titles[i][0].strip(), titles[i][1].strip()
        f1, fx, f2 = folk[i]
        o1, ox, o2 = (x.replace(",", ".") for x in odds[i])
        res["matcher"].append({
            "matchnr": i + 1,
            "hemmalag": h, "bortalag": b,
            "folk_1": int(f1), "folk_x": int(fx), "folk_2": int(f2),
            "odds_1": float(o1), "odds_x": float(ox), "odds_2": float(o2),
        })
    return res

async def fetch_kupong(url: str, debug: bool = False) -> Dict[str, Any]:
    """
    Lyckat svar: { "results": [ {matchnr,...}, ... ], "debug": "<html>" (om debug) }
    Fel:        { "error": "text", "debug": "<html>" (om debug) }
    """
    attempts = 3
    last_err: Optional[str] = None
    last_html: Optional[str] = None

    async with async_playwright() as pw:
        for i in range(attempts):
            ua = UAS[i % len(UAS)]
            browser = ctx = page = None
            try:
                browser, ctx, page, resp, html = await _open_page(pw, url, ua, debug)
                last_html = html

                status = None
                try:
                    if resp:
                        status = resp.status
                except Exception:
                    status = None

                low = (html or "").lower()
                blocked = any(x in low for x in ["cloudflare", "captcha", "access denied", "attention required"]) \
                          or (status is not None and status >= 500)
                if blocked:
                    last_err = f"Blockerad/5xx (försök {i+1})."
                    await ctx.close(); await browser.close()
                    await asyncio.sleep(1.0 * (i + 1))
                    continue

                data = _parse_kupong_html(html or "")
                await ctx.close(); await browser.close()

                if not data["matcher"]:
                    return {"error": "Inga matcher hittades på sidan.", **({"debug": last_html} if debug else {})}

                return {"results": data["matcher"], **({"debug": last_html} if debug else {})}

            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                try:
                    if ctx: await ctx.close()
                    if browser: await browser.close()
                except Exception:
                    pass
                await asyncio.sleep(1.0 * (i + 1))

    return {"error": last_err or "Okänt fel", **({"debug": last_html} if debug and last_html else {})}

# Kompatibla alias (om något i din kod anropar run/fetch_kupong_entry)
run = fetch_kupong

async def fetch_kupong_entry(url: str, debug: bool = False) -> Tuple[Dict[str, Any], int]:
    out = await fetch_kupong(url, debug=debug)
    return out, len(out.get("debug") or "")
