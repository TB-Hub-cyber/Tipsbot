# scrape_stryket.py
from __future__ import annotations
from typing import List, Dict, Any
import requests, re
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Tipsbot)"}

def _num3(txt: str):
    m = re.search(r"(\d+(?:[.,]\d+)?)\D+(\d+(?:[.,]\d+)?)\D+(\d+(?:[.,]\d+)?)", txt)
    if not m: return None, None, None
    a,b,c = (x.replace(",", ".") for x in m.groups())
    return float(a), float(b), float(c)

def scrape_stryketanalysen(url: str) -> List[Dict[str, Any]]:
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    matches: List[Dict[str, Any]] = []
    # Varje “rad” är en list-group-item/panel/card – ta bred selektor
    rows = soup.select(".list-group-item, .panel, .match-card, .card")
    # fallback: hämta sektionen under “Veckans kupong”
    if not rows:
        h = soup.find(string=re.compile("Veckans kupong", re.I))
        if h:
            root = h.find_parent()
            if root:
                rows = root.select(".list-group-item, .panel, .card")

    nr = 0
    for el in rows:
        txt = " ".join(el.stripped_strings)

        # Matchnr + lag
        m = re.search(r"^\s*(\d+)?\s*([A-Za-zÅÄÖåäö\.\-' ]+)\s*[-–]\s*([A-Za-zÅÄÖåäö\.\-' ]+)", txt)
        if not m:
            continue
        nr = nr + 1 if not m.group(1) else int(m.group(1))
        home = m.group(2).strip().rstrip(".")
        away = m.group(3).strip().rstrip(".")

        # Odds
        o1,oX,o2 = None, None, None
        mo = re.search(r"Odds[^0-9]*(.+?)Svenska\s*folket", txt, re.I)
        if mo:
            o1,oX,o2 = _num3(mo.group(1))

        # Svenska folket
        f1,fx,f2 = None, None, None
        mf = re.search(r"Svenska\s*folket[^0-9]*(\d+)%\D+(\d+)%\D+(\d+)%", txt, re.I)
        if mf:
            f1,fx,f2 = int(mf.group(1)), int(mf.group(2)), int(mf.group(3))

        # Spelvärde
        sv1,svx,sv2 = None, None, None
        ms = re.search(r"Spelvärde[^0-9\-]*([-+]?\d+(?:[.,]\d+)?)\D+([-+]?\d+(?:[.,]\d+)?)\D+([-+]?\d+(?:[.,]\d+)?)", txt, re.I)
        if ms:
            sv1,svx,sv2 = (float(x.replace(",", ".")) for x in ms.groups())

        matches.append({
            "matchnr": nr,
            "hemmalag": home,
            "bortalag": away,
            "odds_1": o1, "odds_x": oX, "odds_2": o2,
            "folk_1": f1, "folk_x": fx, "folk_2": f2,
            "spelv_1": sv1, "spelv_x": svx, "spelv_2": sv2
        })
        if len(matches) == 13:
            break

    if not matches:
        raise RuntimeError("Inga matcher hittades på stryketanalysen-sidan.")
    return matches
