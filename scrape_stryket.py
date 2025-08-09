# -*- coding: utf-8 -*-
# scrape_stryket.py – läser kupongen från stryketanalysen.se/stryktipset/
# Returnerar: {"results": [ {matchnr, hemmalag, bortalag, odds_1, odds_x, odds_2, folk_1, folk_x, folk_2}, ... ]}
# eller {"error": "..."} vid fel.

from typing import Dict, Any, List, Optional
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def _to_float(s: str) -> Optional[float]:
    s = s.strip().replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def _to_int(s: str) -> Optional[int]:
    s = re.sub(r"[^\d]", "", s or "")
    try:
        return int(s)
    except Exception:
        return None

def _parse(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: List[Dict[str, Any]] = []

    # --- Försök 1: tabellrader ---
    # Letar rader där det finns "Hemmalag - Bortalag", och ev. odds/procent på samma rad.
    tr_candidates = soup.select("table tr")
    for tr in tr_candidates:
        txt = " ".join(tr.stripped_strings)
        if not txt:
            continue

        m = re.search(r"([A-Za-zÅÄÖåäö0-9\.\-’'& ]+?)\s*-\s*([A-Za-zÅÄÖåäö0-9\.\-’'& ]+)", txt)
        if not m:
            continue

        home = m.group(1).strip()
        away = m.group(2).strip()

        # Odds (tre tal) om de finns på samma rad
        num_tokens = re.findall(r"(\d+(?:[.,]\d+)?)", txt)
        o1 = ox = o2 = None
        if len(num_tokens) >= 3:
            o1, ox, o2 = map(_to_float, num_tokens[:3])

        # Svenska folket-procent (tre heltal med %)
        folk_tokens = re.findall(r"(\d{1,2})\s*%", txt)
        f1 = fx = f2 = None
        if len(folk_tokens) >= 3:
            f1, fx, f2 = map(_to_int, folk_tokens[:3])

        if home and away:
            rows.append({
                "matchnr": len(rows) + 1,
                "hemmalag": home, "bortalag": away,
                "odds_1": o1, "odds_x": ox, "odds_2": o2,
                "folk_1": f1, "folk_x": fx, "folk_2": f2,
            })

    # --- Försök 2: generiska block (div/li) om tabell inte gav resultat ---
    if not rows:
        blocks = soup.select("li, .match, .match-row, .kupong-row, .game-row, article, .entry-content div")
        for blk in blocks:
            txt = " ".join(blk.stripped_strings)
            if not txt:
                continue
            m = re.search(r"([A-Za-zÅÄÖåäö0-9\.\-’'& ]+?)\s*-\s*([A-Za-zÅÄÖåäö0-9\.\-’'& ]+)", txt)
            if not m:
                continue

            home = m.group(1).strip()
            away = m.group(2).strip()

            # Odds & folk om de råkar stå i samma block
            num_tokens = re.findall(r"(\d+(?:[.,]\d+)?)", txt)
            o1 = ox = o2 = None
            if len(num_tokens) >= 3:
                o1, ox, o2 = map(_to_float, num_tokens[:3])

            folk_tokens = re.findall(r"(\d{1,2})\s*%", txt)
            f1 = fx = f2 = None
            if len(folk_tokens) >= 3:
                f1, fx, f2 = map(_to_int, folk_tokens[:3])

            if home and away:
                rows.append({
                    "matchnr": len(rows) + 1,
                    "hemmalag": home, "bortalag": away,
                    "odds_1": o1, "odds_x": ox, "odds_2": o2,
                    "folk_1": f1, "folk_x": fx, "folk_2": f2,
                })

    # --- Deduplicera i insamlingsordning & klipp till 13 ---
    seen = set()
    unique: List[Dict[str, Any]] = []
    for r in rows:
        key = (
            r.get("hemmalag"), r.get("bortalag"),
            r.get("odds_1"), r.get("odds_x"), r.get("odds_2"),
            r.get("folk_1"), r.get("folk_x"), r.get("folk_2"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    # Sätt matchnr 1..13
    for i, r in enumerate(unique[:13], start=1):
        r["matchnr"] = i

    return unique[:13]

def fetch_stryket(url: str) -> Dict[str, Any]:
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
