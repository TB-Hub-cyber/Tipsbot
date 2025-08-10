# scrape_footy.py
from __future__ import annotations
import re
from typing import Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
from difflib import SequenceMatcher

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
}

# -------- Namn-normalisering & alias --------
ALIAS = {
    "wolves": "wolverhampton wanderers",
    "wolverhampton": "wolverhampton wanderers",
    "west brom": "west bromwich albion",
    "qpr": "queens park rangers",
    "sheff u": "sheffield united",
    "sheff.u": "sheffield united",
    "sheffield u": "sheffield united",
    "man utd": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham hotspur",
    "forest": "nottingham forest",
    "middlesb.": "middlesbrough",
    "portsmo.": "portsmouth",
    "northamp.": "northampton town",
    "stockp. c": "stockport county",
    "preston": "preston north end",
}
REMOVE_TOKENS = r"\b(fc|afc|cf|city|united|town|athletic|the|club)\b"

def norm_name(s: str) -> str:
    if not s: return ""
    s = s.lower()
    s = s.replace("&", "and").replace("-", " ").replace(".", " ")
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(REMOVE_TOKENS, "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return ALIAS.get(s, s)

def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, norm_name(a), norm_name(b)).ratio()

def align_with_excel_names(home: str, away: str, excel_home: str, excel_away: str):
    score_same = (similar(home, excel_home) + similar(away, excel_away)) / 2
    score_swap = (similar(home, excel_away) + similar(away, excel_home)) / 2
    return (home, away, False) if score_same >= score_swap else (away, home, True)

def _float_or_none(s: Optional[str]) -> Optional[float]:
    if not s: return None
    s2 = re.sub(r"[^\d\.\-]", "", s)
    return float(s2) if re.search(r"\d", s2) else None

def _text(el) -> str:
    return (el.get_text(" ", strip=True) if el else "").strip()

def fetch_footy(url: str, matchnr: int) -> Dict[str, Any]:
    """
    Hämta grunddata från en FootyStats H2H-sida:
    - Lag (home/away), xG For, xGA, PPG (overall), form (senaste 5),
      samt enkel H2H summering W/D/L om den finns.
    """
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    title = _text(soup.find(["h1", "h2", "h3"])) or _text(soup.find("title"))
    home = away = None
    m = re.search(r"(.+?)\s+vs\s+(.+?)\b", title, re.I)
    if m:
        home, away = m.group(1).strip(), m.group(2).strip()

    def scrape_team_block(team_name: Optional[str]):
        stats = {"team": team_name or ""}
        if not team_name:
            return stats

        block = None
        for tag in soup.find_all(True, string=re.compile(re.escape(team_name), re.I)):
            cand = tag
            for _ in range(3):
                cand = cand.parent or cand
            if cand and len(_text(cand)) > 50:
                block = cand
                break

        def find_value(regex):
            if not block:
                return None
            t = _text(block)
            m1 = re.search(regex + r".{0,20}?([-+]?\d+(?:\.\d+)?)", t, re.I)
            return _float_or_none(m1.group(1)) if m1 else None

        stats["xg_for"] = find_value(r"(?:\bxG(?:\s*For)?\b|Expected Goals)")
        stats["xg_against"] = find_value(r"(?:\bxGA\b|xG Against)")
        stats["ppg"] = find_value(r"(?:\bPPG\b|Points per game)")

        form_txt = None
        if block:
            t = _text(block)
            mform = re.search(r"([WDL]{3,})", t.replace(" ", ""))
            if mform:
                form_txt = mform.group(1)[:5]
        stats["form_last5"] = form_txt
        return stats

    home_stats = scrape_team_block(home)
    away_stats = scrape_team_block(away)

    h2h_w = h2h_d = h2h_l = None
    h2h_label = soup.find(string=re.compile(r"(Head\s*to\s*Head|H2H)", re.I))
    if h2h_label:
        box = h2h_label.find_parent()
        if box:
            seq = "".join(re.findall(r"[WDL]", _text(box)))[:10]
            if seq:
                h2h_w, h2h_d, h2h_l = seq.count("W"), seq.count("D"), seq.count("L")

    return {
        "matchnr": matchnr,
        "url": url,
        "home": {
            "name": home_stats.get("team"),
            "xg_for": home_stats.get("xg_for"),
            "xg_against": home_stats.get("xg_against"),
            "ppg": home_stats.get("ppg"),
            "form_last5": home_stats.get("form_last5"),
        },
        "away": {
            "name": away_stats.get("team"),
            "xg_for": away_stats.get("xg_for"),
            "xg_against": away_stats.get("xg_against"),
            "ppg": away_stats.get("ppg"),
            "form_last5": away_stats.get("form_last5"),
        },
        "h2h_last5": {"W": h2h_w, "D": h2h_d, "L": h2h_l},
        "page_title": title,
    }
