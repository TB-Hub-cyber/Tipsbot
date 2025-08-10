import re
import os
import pathlib
from urllib.parse import urlparse, urlunparse
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")

STATIC_DIR = pathlib.Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

DEBUG_HTML_PATH = STATIC_DIR / "stryket_debug.html"

def _normalize_url(url: str) -> str:
    """
    Se till att vi alltid landar på https://www.stryketanalysen.se/stryktipset/
    även om användaren matat in en annan variant.
    """
    if not url:
        return "https://www.stryketanalysen.se/stryktipset/"
    u = url.strip()
    if u.startswith("http://"):
        u = "https://" + u[len("http://"):]
    if "stryketanalysen.se" in u and not u.startswith("https://"):
        u = "https://" + u.split("://", 1)[-1]
    # tvinga www
    if "://stryketanalysen.se" in u:
        u = u.replace("://stryketanalysen.se", "://www.stryketanalysen.se")
    # tvinga /stryktipset/
    if "/stryktipset" not in u:
        u = u.rstrip("/") + "/stryktipset/"
    if not u.endswith("/"):
        u += "/"
    return u

def _get(url: str) -> str:
    r = requests.get(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.text

def _parse_percent(cell_text: str) -> int:
    # ex: "26%" -> 26
    m = re.search(r"(\d+)\s*%", cell_text)
    return int(m.group(1)) if m else 0

def _parse_float(txt: str) -> float:
    # hantera både 2.30 och 2,30 om de råkar dyka upp
    t = txt.strip().replace(",", ".")
    try:
        return float(t)
    except:
        return 0.0

def _extract_matches(soup: BeautifulSoup):
    """
    Försöker flera vägar för att hitta 13 matchrader:
    - 'div' som ser ut som kort/rad för en match
    - letar efter odds (tre tal), 'Svenska folket' (tre procentsiffror),
      samt lag/nummer längst till vänster.
    OBS: Klassnamn kan ändras – därför matchar vi semantiskt.
    """
    candidates = []

    # 1) Sektion "Veckans kupong" – ofta ett wrapper-kort med många rader
    main_sections = soup.select("div#content, main, div.container, section")
    if not main_sections:
        main_sections = [soup]

    # plocka alla “rader” vi kan hitta
    rows = []
    for sec in main_sections:
        rows += sec.select("div.match, li.match, div.list-group-item, div.card, div.row")

    if not rows:
        # fallback – hämta alla divs som innehåller 'Odds' och 'Svenska folket'
        for d in soup.select("div"):
            txt = d.get_text(" ", strip=True)
            if "Odds" in txt and "Svenska folket" in txt:
                rows.append(d)

    # heuristiskt: en rad måste innehålla tre odds & tre folk-procent
    for r in rows:
        txt = r.get_text(" ", strip=True)

        # hitta matchnummer och lag (väldigt tolerant)
        # ex: "1 Halmstad - Sirius"
        mnr = None
        home = None
        away = None

        # matchnr: först siffra i raden
        m_mnr = re.search(r"\b(\d{1,2})\b", txt)
        if m_mnr:
            mnr = int(m_mnr.group(1))

        # lag – försök fånga "A - B" kring början
        m_teams = re.search(r"\b\d{1,2}\s+([^\-–]+?)\s*[-–]\s*([^\d]+?)\s+(Odds|Start|Svenska folket|Spelvärde)", txt)
        if m_teams:
            home = m_teams.group(1).strip()
            away = m_teams.group(2).strip()
        else:
            # fallback: hitta två ordsekvenser åtskilda av streck någonstans
            m_teams2 = re.search(r"([A-Za-zÅÄÖåäö\.\s]+?)\s*[-–]\s*([A-Za-zÅÄÖåäö\.\s]+?)\s+(Odds|Start|Svenska folket|Spelvärde)", txt)
            if m_teams2:
                home = m_teams2.group(1).strip()
                away = m_teams2.group(2).strip()

        # odds – leta tre decimaltal nära "Odds"
        odds = None
        m_odds_block = re.search(r"Odds[^0-9]*(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(\d+[.,]\d+)", txt)
        if m_odds_block:
            odds = tuple(_parse_float(x) for x in m_odds_block.groups())

        # folk – leta tre procentsiffror nära "Svenska folket"
        folk = None
        m_folk_block = re.search(r"Svenska folket[^%]*?(\d+)\s*%\s+(\d+)\s*%\s+(\d+)\s*%", txt)
        if m_folk_block:
            folk = tuple(int(x) for x in m_folk_block.groups())

        # spelvärde – tre tal nära "Spelvärde" (kan vara +/-)
        spelv = None
        m_spelv = re.search(r"Spelvärde[^-\d]*?([\-+]?\d+[.,]?\d*)\s+([\-+]?\d+[.,]?\d*)\s+([\-+]?\d+[.,]?\d*)", txt)
        if m_spelv:
            spelv = tuple(_parse_float(x) for x in m_spelv.groups())

        # rimlig rad?
        if mnr and home and away and odds and folk:
            entry = {
                "matchnr": mnr,
                "hemmalag": home,
                "bortalag": away,
                "odds_1": odds[0],
                "odds_x": odds[1],
                "odds_2": odds[2],
                "folk_1": folk[0],
                "folk_x": folk[1],
                "folk_2": folk[2],
            }
            if spelv:
                entry.update({
                    "spelv_1": spelv[0],
                    "spelv_x": spelv[1],
                    "spelv_2": spelv[2],
                })
            candidates.append(entry)

    # deduplikation & sortering på matchnr
    uniq = {}
    for c in candidates:
        uniq[c["matchnr"]] = c
    out = [uniq[k] for k in sorted(uniq.keys())]
    return out

def fetch_stryket(url: str, debug: bool = False):
    """
    Returnerar dict {"svenskaspel": [13 poster]} eller höjer Exception.
    Sparar alltid debug-HTML om debug=True eller om 0 rader hittas.
    """
    norm = _normalize_url(url)
    html = _get(norm)
    soup = BeautifulSoup(html, "html.parser")

    rows = _extract_matches(soup)

    # spara debug-HTML om vi misslyckas eller om debug begärts
    if debug or not rows:
        try:
            DEBUG_HTML_PATH.write_text(html, encoding="utf-8")
        except Exception:
            pass

    if not rows:
        raise RuntimeError("Scrape-fel: Inga matcher hittades på stryketanalysen-sidan.")

    # begränsa till 13 (om sidan råkar visa fler, ex kupong + reserv)
    rows = rows[:13]
    return {"svenskaspel": rows}
