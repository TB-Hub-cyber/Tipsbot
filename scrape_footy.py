# scrape_footy.py
from __future__ import annotations
from typing import Dict, Any, Optional, Tuple, List
import re, difflib, requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Tipsbot)"}

def _to_float(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    s = s.strip().replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None

def _clean_team(s: str) -> str:
    s = s.lower()
    s = re.sub(r"fc|afc|cf|bk|ik|if|fk|u\d+|[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

ALIASES = {
    # engelska exempel
    "wolves": "wolverhampton wanderers",
    "man city": "manchester city",
    "man utd": "manchester united",
    "spurs": "tottenham hotspur",
    "newcastle": "newcastle united",
    "west brom": "west bromwich albion",
    "qpr": "queens park rangers",
    "sheff u": "sheffield united",
    "sheff utd": "sheffield united",
    "forest": "nottingham forest",
    # svenska/eng
    "hbk": "halmstads bk",
    "sirius": "ik sirius",
}

def _alias_norm(name: str) -> str:
    n = _clean_team(name)
    return ALIASES.get(n, n)

def _best_match(target: str, choices: List[str]) -> Tuple[str, float]:
    t = _alias_norm(target)
    pool = [_alias_norm(c) for c in choices]
    scores = [difflib.SequenceMatcher(None, t, p).ratio() for p in pool]
    if not scores:
        return target, 0.0
    i = max(range(len(scores)), key=lambda k: scores[k])
    return choices[i], scores[i]

def fetch_footy(url: str) -> Dict[str, Any]:
    """
    Hämtar Footystats-matchsidan och extraherar:
    - team_namn (home, away)
    - form (senaste 5) som t.ex. 'WDLWW'
    - xG/xGA overall + home/away om tillgängligt
    - mål/insläppta (avg per match) overall
    - PPG overall + home/away
    - H2H senaste 5 (t.ex. 'H:2 X:1 B:2' och sträng)
    Returnerar som dict -> excel_utils skriver till filen.
    """
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    text = " ".join(soup.stripped_strings)

    # Lag-namn (rubrik överst brukar ha "Team A vs Team B")
    title = soup.select_one("h1, h2, .page-title, .match-headline")
    if title:
        m = re.search(r"(.+?)\s+vs\s+(.+)", title.get_text(" ", strip=True), re.I)
    else:
        m = re.search(r"(.+?)\s+vs\s+(.+?)\s+(?:H2H|Stats)", text, re.I)
    home_name = away_name = None
    if m:
        home_name = m.group(1).strip()
        away_name = m.group(2).strip()

    # Form (senaste 5) – ofta visas med W/D/L-bokstäver nära teamkort
    def find_form_for(label: str) -> Optional[str]:
        # Försök hitta sektion med "Form" nära lagets namn
        patt = re.compile(rf"{re.escape(label)}.*?Form[^WDL]*(W|D|L){{3,6}}", re.I | re.S)
        mm = patt.search(text)
        if mm:
            seq = re.search(r"(W|D|L){3,6}", mm.group(0))
            if seq: return seq.group(0)
        # fallback: första sekvensen W/D/L på sidan
        seq = re.search(r"(W|D|L){3,6}", text)
        return seq.group(0) if seq else None

    form_home = find_form_for(home_name or "Home")
    form_away = find_form_for(away_name or "Away")

    # xG / xGA / Goals per match – försöker plocka med “per match/avg”
    def find_metric(prefix: str, scope: str) -> Optional[float]:
        # Ex: "Home xG (per match) 1.65" eller "xG (Avg) 1.45"
        p = rf"{scope}[^\.]*{prefix}[^0-9\-]*(-?\d+(?:[.,]\d+)?)"
        m = re.search(p, text, re.I)
        return _to_float(m.group(1)) if m else None

    # PPG (Points Per Game)
    def find_ppg(scope: str) -> Optional[float]:
        m = re.search(rf"{scope}[^\.]*PPG[^0-9\-]*(-?\d+(?:[.,]\d+)?)", text, re.I)
        return _to_float(m.group(1)) if m else None

    # H2H – ta ut en sammanfattning (senaste 5)
    h2h_summary = None
    m = re.search(r"H2H[^:]*:\s*([^\n\r]+)", text, re.I)
    if m:
        h2h_summary = m.group(1).strip()
    else:
        # ibland står 'Head to Head'
        m = re.search(r"Head to Head[^:]*:\s*([^\n\r]+)", text, re.I)
        if m:
            h2h_summary = m.group(1).strip()

    data = {
        "home_name": home_name,
        "away_name": away_name,
        "form_home": form_home,
        "form_away": form_away,
        "xg_home_overall": find_metric("xG", "Home") or find_metric("xG", "Overall"),
        "xg_home_home": find_metric("xG", "Home"),
        "xga_home_overall": find_metric("xGA", "Home") or find_metric("xGA", "Overall"),
        "xga_home_home": find_metric("xGA", "Home"),
        "gf_home_overall": find_metric("Goals For", "Home") or find_metric("GF", "Home") or find_metric("Goals", "Home"),
        "ga_home_overall": find_metric("Goals Against", "Home") or find_metric("GA", "Home"),
        "xg_away_overall": find_metric("xG", "Away") or find_metric("xG", "Overall"),
        "xg_away_away": find_metric("xG", "Away"),
        "xga_away_overall": find_metric("xGA", "Away") or find_metric("xGA", "Overall"),
        "xga_away_away": find_metric("xGA", "Away"),
        "gf_away_overall": find_metric("Goals For", "Away") or find_metric("GF", "Away") or find_metric("Goals", "Away"),
        "ga_away_overall": find_metric("Goals Against", "Away") or find_metric("GA", "Away"),
        "ppg_home_overall": find_ppg("Home") or find_ppg("Overall"),
        "ppg_home_home": find_ppg("Home"),
        "ppg_away_overall": find_ppg("Away") or find_ppg("Overall"),
        "ppg_away_away": find_ppg("Away"),
        "h2h_last5": h2h_summary,
        "source": url
    }
    return data
