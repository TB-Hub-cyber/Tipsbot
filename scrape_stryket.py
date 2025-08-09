# -*- coding: utf-8 -*-
# scrape_stryket.py – hämtar veckans kupong från stryketanalysen.se/stryktipset
# Fält per match:
#   matchnr, hemmalag, bortalag,
#   odds_1, odds_x, odds_2,
#   folk_1, folk_x, folk_2,
#   spelv_1, spelv_x, spelv_2   (kan vara None om ej visat)
#
# Returnerar {"results":[...]} eller {"error":"..."}.

from typing import Dict, Any, List, Optional, Iterable
import re
import requests
from bs4 import BeautifulSoup, NavigableString, Tag

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.stryketanalysen.se/",
}

# ── små hjälpare ───────────────────────────────────────────────────────────────

NAME = r"[A-Za-zÅÄÖåäö0-9\.\-’'&() ]+"
TITLE_RX = re.compile(fr"({NAME})\s*-\s*({NAME})")

NUM_RX = re.compile(r"(\d+(?:[.,]\d+)?)")
PCT_RX = re.compile(r"(\d{1,2})\s*%")

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

LABELS_ORDER = ["Odds", "Start-odds", "Svenska folket", "Spelvärde", "Tio Tidningar"]

def _section_after_label(text: str, label: str) -> str:
    """Returnera texten direkt efter 'label' fram till nästa kända label."""
    i = text.find(label)
    if i < 0:
        return ""
    rest = text[i+len(label):]
    stop_idx = len(rest)
    for lb in LABELS_ORDER:
        j = rest.find(lb)
        if j >= 0:
            stop_idx = min(stop_idx, j)
    return rest[:stop_idx]

def _pick_three_floats(text: str) -> List[Optional[float]]:
    nums = NUM_RX.findall(text)
    vals = list(map(_to_float, nums[:3]))
    while len(vals) < 3:
        vals.append(None)
    return vals

def _pick_three_pcts(text: str) -> List[Optional[int]]:
    pcs = PCT_RX.findall(text)
    vals = list(map(_to_int, pcs[:3]))
    while len(vals) < 3:
        vals.append(None)
    return vals

def _nearest_match_container(node: Tag) -> Optional[Tag]:
    """Utgår från en label-nod (t.ex. <span>Svenska folket</span>) och
    klättrar uppåt tills vi hittar ett block som även innehåller
    matchtiteln ('Lag A - Lag B') och 'Odds'."""
    cur: Optional[Tag] = node
    for _ in range(6):  # klättra upp några nivåer, DOM:en är grunt byggd
        if cur is None:
            return None
        txt = " ".join(cur.stripped_strings)
        if "Odds" in txt and TITLE_RX.search(txt):
            return cur
        cur = cur.parent if isinstance(cur.parent, Tag) else None
    return None

# ── parser ────────────────────────────────────────────────────────────────────

def _parse(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    results: List[Dict[str, Any]] = []

    # Hitta alla rader via labeln "Svenska folket" (unikt för varje matchruta på sidan)
    folk_labels: Iterable[Tag] = soup.find_all(string=re.compile(r"^\s*Svenska folket\s*$", re.I))
    containers: List[Tag] = []

    for lbl in folk_labels:
        node = lbl if isinstance(lbl, Tag) else None
        # Om labeln är NavigableString, ta dess förälder
        if node is None and isinstance(lbl, NavigableString) and isinstance(lbl.parent, Tag):
            node = lbl.parent
        if not isinstance(node, Tag):
            continue
        cont = _nearest_match_container(node)
        if cont and cont not in containers:
            containers.append(cont)

    # Fallback om vi inte hittade via labels – försök via rubriker "Lag - Lag"
    if not containers:
        for blk in soup.select(".entry-content div, .content div, .main div, li, article, .match, .match-row"):
            if not isinstance(blk, Tag):
                continue
            txt = " ".join(blk.stripped_strings)
            if "Odds" in txt and "Svenska folket" in txt and TITLE_RX.search(txt):
                containers.append(blk)

    # Plocka data ur varje container
    for cont in containers:
        txt = " ".join(cont.stripped_strings)

        m = TITLE_RX.search(txt)
        if not m:
            continue
        home = m.group(1).strip()
        away = m.group(2).strip()

        odds_txt = _section_after_label(txt, "Odds")
        folk_txt = _section_after_label(txt, "Svenska folket")
        sv_txt   = _section_after_label(txt, "Spelvärde")

        o1, ox, o2 = _pick_three_floats(odds_txt)
        f1, fx, f2 = _pick_three_pcts(folk_txt)
        s1, sx, s2 = _pick_three_floats(sv_txt)  # kan bli None om ej visat

        results.append({
            "matchnr": len(results) + 1,
            "hemmalag": home, "bortalag": away,
            "odds_1": o1, "odds_x": ox, "odds_2": o2,
            "folk_1": f1, "folk_x": fx, "folk_2": f2,
            "spelv_1": s1, "spelv_x": sx, "spelv_2": s2,
        })

    # Deduplicera i insamlingsordning och klipp till 13
    seen = set()
    unique: List[Dict[str, Any]] = []
    for r in results:
        key = (
            r["hemmalag"], r["bortalag"],
            r.get("odds_1"), r.get("odds_x"), r.get("odds_2"),
            r.get("folk_1"), r.get("folk_x"), r.get("folk_2"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    for i, r in enumerate(unique[:13], start=1):
        r["matchnr"] = i

    return unique[:13]

# ── publikt anrop ─────────────────────────────────────────────────────────────

def fetch_stryket(url_obj) -> Dict[str, Any]:
    url = str(url_obj).strip()
    if not url:
        return {"error": "Ingen URL angiven."}
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code >= 400:
            return {"error": f"HTTP {r.status_code}"}
        rows = _parse(r.text)
        if not rows:
            return {"error": "Hittade inga matcher på sidan."}
        return {"results": rows}
    except requests.RequestException as e:
        return {"error": f"Nätverksfel: {e}"}
    except Exception as e:
        return {"error": str(e)}
