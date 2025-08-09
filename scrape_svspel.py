# scrape_svspel.py
from typing import Dict, Any, Tuple, Optional, List
import asyncio, random, time
from playwright.async_api import async_playwright

# Ett gäng moderna UA-strängar (roteras mellan försök)
UAS: List[str] = [
    # Win10 / Chrome 124+
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Win11 / Chrome 125+
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # MacOS / Chrome 126+
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

def _anti_detect_init_script() -> str:
    # Maskerar några klassiska Playwright-avslöjanden
    return r"""
// navigator.webdriver -> undefined
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Chrome hints
window.chrome = { runtime: {} };

// Plugins och språk
Object.defineProperty(navigator, 'plugins',   { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['sv-SE','sv','en-US','en'] });

// Permissions prompt always 'granted' for notifications
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
  parameters.name === 'notifications' ?
    Promise.resolve({ state: 'granted' }) :
    originalQuery(parameters)
);

// WebGL vendor/renderer (enkelt spoof)
try {
  const getParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) { return 'Intel Inc.'; }     // UNMASKED_VENDOR_WEBGL
    if (parameter === 37446) { return 'Intel Iris OpenGL Engine'; } // UNMASKED_RENDERER_WEBGL
    return getParameter(parameter);
  };
} catch(e) {}
"""

async def _open_page(pw, url: str, ua: str, debug: bool):
    chromium = pw.chromium
    browser = await chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-gpu", "--disable-features=IsolateOrigins,site-per-process",
        ],
    )
    ctx = await browser.new_context(
        user_agent=ua,
        locale="sv-SE",
        timezone_id="Europe/Stockholm",
        viewport={"width": 1366, "height": 850},
        java_script_enabled=True,
        device_scale_factor=1.0,
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    await ctx.add_init_script(_anti_detect_init_script())

    page = await ctx.new_page()
    page.set_default_timeout(10000)

    resp = await page.goto(url, wait_until="domcontentloaded")
    # Försök att låta nätverket bli idle
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass

    if debug:
        try:
            await page.screenshot(path="/tmp/svs_debug.png", full_page=True)
        except Exception:
            pass

    return browser, ctx, page, resp

def _parse_kupong_html(html: str) -> Dict[str, Any]:
    """
    Minimal, robust parsing direkt på HTML med text-matchningar.
    Antaganden: Sidan listar 13 matcher, varje rad har lag + 'Svenska folket' + 'Odds' med tre tal.
    Den exakta DOM-strukturen kan ändras; vi håller parsing tolerant.
    """
    import re
    results = {"matcher": []}

    # Fånga block för varje match: försök hitta rader med "Svenska folket" följt av tre procent samt "Odds" med tre tal.
    # Vi matchar även lagrubriken innan.
    # OBS: Detta är förenklat men brukar räcka för kupongsidan.
    # Match: "Halmstad - Sirius" osv
    match_titles = re.findall(r'>([A-Za-zÅÄÖåäö0-9\.\-\/ ]+?)\s*-\s*([A-Za-zÅÄÖåäö0-9\.\-\/ ]+?)<', html)
    # Svenska folket proc
    folk_rows = re.findall(r'Svenska folket.*?(\d{1,2})%.*?(\d{1,2})%.*?(\d{1,2})%', html, re.S)
    # Odds rader
    odds_rows = re.findall(r'Odds.*?(\d+(?:[.,]\d+)?).*?(\d+(?:[.,]\d+)?).*?(\d+(?:[.,]\d+)?)', html, re.S)

    n = min(len(match_titles), len(folk_rows), len(odds_rows))
    for i in range(n):
        h, b = match_titles[i][0].strip(), match_titles[i][1].strip()
        f1, fx, f2 = folk_rows[i]
        o1, ox, o2 = odds_rows[i]
        # Normalisera decimaler
        o1 = o1.replace(",", "."); ox = ox.replace(",", "."); o2 = o2.replace(",", ".")
        results["matcher"].append({
            "matchnr": i+1,
            "hemmalag": h, "bortalag": b,
            "folk_1": int(f1), "folk_x": int(fx), "folk_2": int(f2),
            "odds_1": float(o1), "odds_x": float(ox), "odds_2": float(o2),
        })

    return results

async def fetch_kupong(url: str, debug: bool=False) -> Dict[str, Any]:
    """
    Returnerar:
      { "results": [...], "debug": "<html...>" }  vid debug=True
    eller { "results": [...] } vid debug=False
    och vid fel: { "error": "...", "debug": "<html...>" (om debug) }
    """
    attempts = 3
    last_err: Optional[str] = None
    html_dump: Optional[str] = None

    async with async_playwright() as pw:
        for i in range(attempts):
            ua = UAS[i % len(UAS)]
            try:
                browser, ctx, page, resp = await _open_page(pw, url, ua, debug)
                # Om Cloudflare/520: svarskod kan vara None (pga nav) – kolla HTML också
                html = await page.content()
                html_dump = html  # spara senaste

                # Fånga upp 520/5xx via response om möjligt
                status = None
                try:
                    if resp: status = resp.status
                except Exception:
                    status = None

                # Basic heuristik för block/CAPTCHA
                blocked = False
                low = html.lower()
                if any(x in low for x in ["attention required", "cloudflare", "captcha", "access denied"]):
                    blocked = True
                if status and status >= 500:
                    blocked = True

                if blocked:
                    last_err = f"Blockerad/520 (försök {i+1})."
                    await ctx.close(); await browser.close()
                    await asyncio.sleep(1.2 * (i+1))
                    continue

                # OK – parsa
                data = _parse_kupong_html(html)
                await ctx.close(); await browser.close()

                if not data["matcher"]:
                    # Ingenting hittat – returnera fel men med HTML i debug
                    out = {"error": "Inga matcher hittades på kupongsidan."}
                    if debug: out["debug"] = html
                    return out

                out = {"results": data["matcher"]}
                if debug: out["debug"] = html
                return out

            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                # säker stängning
                try:
                    await ctx.close()
                    await browser.close()
                except Exception:
                    pass
                await asyncio.sleep(1.0 * (i+1))

    # Efter alla försök – ge fel + ev. html-dump
    out: Dict[str, Any] = {"error": last_err or "Okänt fel mot kupongsidan."}
    if debug and html_dump:
        out["debug"] = html_dump
    return out

# För kompatibilitet med tidigare main.py:
async def fetch_kupong_entry(url: str, debug: bool=False) -> Tuple[Dict[str, Any], int]:
    out = await fetch_kupong(url, debug=debug)
    debug_len = len(out.get("debug") or "") if isinstance(out, dict) else 0
    return out, debug_len

# Legacy alias som du kan ha anropat tidigare:
run = fetch_kupong
