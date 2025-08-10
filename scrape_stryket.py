# scrape_stryket.py
from __future__ import annotations
from typing import List, Dict, Any
import requests, re
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Tipsbot)"}

def _float(x: str) -> float:
    return float(x.replace(",", ".").strip())

def scrape_stryketanalysen(url: str) -> List[Dict[str, Any]]:
    """
    Snäv/”stabil” version som vi körde när det fungerade för dig:
    - Letar främst i .list-group-item (så som sidan normalt är uppbyggd)
    - Regex för 'Odds', 'Svenska folket', 'Spelvärde'
    - Returnerar exakt 13 matcher (matchnr, lag, odds, folk, spelvärde)
    """
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Primär layout: varje match som ett list-item
    blocks = soup.select(".list-group-item")

    # Liten fallback om sidan justerat markup (men fortfarande samma struktur)
    if not blocks:
        blocks = soup.select(".panel, .card, .match-card")

    matches: List[Dict[str, Any]] = []

    for block in blocks:
        txt = " ".join(block.stripped_strings)

        # Matchnr + lag: " 1 Halmstad - Sirius "
        m = re.search(
            r"^\s*(\d+)\s+([A-Za-zÅÄÖåäö\.\-\' ]+?)\s*[-–]\s*([A-Za-zÅÄÖåäö\.\-\' ]+?)\s",
            txt
        )
        if not m:
            continue

        matchnr = int(m.group(1))
        home = m.group(2).strip().rstrip(".")
        away = m.group(3).strip().rstrip(".")

        # Odds 1 X 2
        mo = re.search(
            r"Odds[^0-9]*(\d+(?:[.,]\d+)?)[^\d]+(\d+(?:[.,]\d+)?)[^\d]+(\d+(?:[.,]\d+)?)",
            txt, re.I
        )
        if not mo:
            # om vi inte hittar odds hoppar vi hellre över blocket än att stoppa flödet
            continue
        o1, ox, o2 = _float(mo.group(1)), _float(mo.group(2)), _float(mo.group(3))

        # Svenska folket i procent
        mf = re.search(
            r"Svenska\s*folket[^0-9]*(\d+)%[^\d]+(\d+)%[^\d]+(\d+)%",
            txt, re.I
        )
        f1 = fx = f2 = None
        if mf:
            f1, fx, f2 = int(mf.group(1)), int(mf.group(2)), int(mf.group(3))

        # Spelvärde (kan vara negativa tal)
        ms = re.search(
            r"Spelvärde[^0-9\-]*([-+]?\d+(?:[.,]\d+)?)[^\d\-]+([-+]?\d+(?:[.,]\d+)?)[^\d\-]+([-+]?\d+(?:[.,]\d+)?)",
            txt, re.I
        )
        sv1 = svx = sv2 = None
        if ms:
            sv1, svx, sv2 = _float(ms.group(1)), _float(ms.group(2)), _float(ms.group(3))

        matches.append({
            "matchnr": matchnr,
            "hemmalag": home,
            "bortalag": away,
            "odds_1": o1, "odds_x": ox, "odds_2": o2,
            "folk_1": f1, "folk_x": fx, "folk_2": f2,
            "spelv_1": sv1, "spelv_x": svx, "spelv_2": sv2
        })

        if len(matches) == 13:
            break

    if len(matches) < 13:
        raise RuntimeError("Inga matcher hittades på stryketanalysen-sidan.")
    return matches
