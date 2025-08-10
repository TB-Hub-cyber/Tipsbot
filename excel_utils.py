# excel_utils.py
from __future__ import annotations
import io
import re
import datetime as dt
from typing import List, Dict, Any, Optional
from openpyxl import load_workbook

# Global state (fylls av API:et)
KUPONG: List[Dict[str, Any]] = []
FOOTY: Dict[int, Dict[str, Any]] = {}

DATA_SHEET_NAME = "Data"
START_ROW = 2  # rad där match 1 står

# ---------- Helpers ----------
def reset_state():
    KUPONG.clear()
    FOOTY.clear()

def update_kupong(rows: List[Dict[str, Any]]):
    """Spara kupongrader."""
    global KUPONG
    KUPONG = list(rows or [])

def update_footy(matchnr: int, data: Dict[str, Any]):
    """Spara footydata per match."""
    FOOTY[int(matchnr)] = data

def _open_wb(path: str):
    return load_workbook(path)

def _find_sheet(wb, name: str):
    if name in wb.sheetnames:
        return wb[name]
    # fallback: aktivt blad
    return wb.active

def find_col_by_header(ws, patterns):
    """
    patterns: str eller lista av regex som matchar headertext i rad 1.
    Returnerar kolumnindex (1-baserat) eller None.
    """
    if isinstance(patterns, str):
        patterns = [patterns]
    headers = {}
    for c in range(1, ws.max_column + 1):
        txt = ws.cell(row=1, column=c).value
        if isinstance(txt, str):
            headers[c] = txt.strip()
    for rx in patterns:
        cre = re.compile(rx, re.I)
        for c, txt in headers.items():
            if cre.search(txt):
                return c
    return None

# ---------- Skriv KUPONG till Data (om kolumner hittas) ----------
KUPONG_MAP = {
    # rubrik_regex : lambda row -> value
    r"^Matchnr": lambda r: r.get("matchnr"),
    r"^Hemmalag": lambda r: r.get("hemmalag"),
    r"^Bortalag": lambda r: r.get("bortalag"),
    r"^Odds\s*%?\s*1|^Odds\s*1\b": lambda r: r.get("odds_1"),
    r"^Odds\s*%?\s*X|^Odds\s*X\b": lambda r: r.get("odds_x"),
    r"^Odds\s*%?\s*2|^Odds\s*2\b": lambda r: r.get("odds_2"),
    r"(Svenska\s*folket|Folk).*\b1\b": lambda r: r.get("folk_1"),
    r"(Svenska\s*folket|Folk).*\bX\b": lambda r: r.get("folk_x"),
    r"(Svenska\s*folket|Folk).*\b2\b": lambda r: r.get("folk_2"),
    r"^V(a|ä)rde\s*1": lambda r: r.get("spelv_1"),
    r"^V(a|ä)rde\s*X": lambda r: r.get("spelv_x"),
    r"^V(a|ä)rde\s*2": lambda r: r.get("spelv_2"),
}

def write_kupong_into_data_sheet(wb):
    if not KUPONG:
        return
    ws = _find_sheet(wb, DATA_SHEET_NAME)

    # bygg kolumnkarta en gång
    col_map = {}
    for hdr_regex in KUPONG_MAP:
        col_map[hdr_regex] = find_col_by_header(ws, hdr_regex)

    for r in KUPONG:
        try:
            mn = int(r.get("matchnr"))
        except Exception:
            continue
        row = START_ROW - 1 + mn
        for hdr_regex, maker in KUPONG_MAP.items():
            c = col_map.get(hdr_regex)
            if not c:
                continue
            try:
                val = maker(r)
            except Exception:
                val = None
            ws.cell(row=row, column=c, value=val)

# ---------- Skriv FOOTY till Data ----------
FOOTY_TO_DATA_MAP = {
    r"^Form\s*H\b|Hemmaform": lambda d: (d.get("home") or {}).get("form_last5"),
    r"^Form\s*B\b|Bortaform": lambda d: (d.get("away") or {}).get("form_last5"),
    r"H2H.*(senaste|last)\s*5": lambda d: (
        "W:{W} D:{D} L:{L}".format(**{k: (d.get("h2h_last5") or {}).get(k) for k in ["W","D","L"]})
    ),
    r"^xG\s*H\b.*(s(a|ä)song|overall)|^xG H": lambda d: (d.get("home") or {}).get("xg_for"),
    r"^xGA\s*H\b|xG\s*H\s*\(hemma\)|xG-against H": lambda d: (d.get("home") or {}).get("xg_against"),
    r"^PPG\s*H\b": lambda d: (d.get("home") or {}).get("ppg"),
    r"^xG\s*B\b.*(s(a|ä)song|overall)|^xG B": lambda d: (d.get("away") or {}).get("xg_for"),
    r"^xGA\s*B\b|xG\s*B\s*\(borta\)|xG-against B": lambda d: (d.get("away") or {}).get("xg_against"),
    r"^PPG\s*B\b": lambda d: (d.get("away") or {}).get("ppg"),
}

def write_footy_into_data_sheet(wb):
    if not FOOTY:
        return
    ws = _find_sheet(wb, DATA_SHEET_NAME)

    # hitta kolumner
    col_map = {}
    for hdr_regex in FOOTY_TO_DATA_MAP:
        col_map[hdr_regex] = find_col_by_header(ws, hdr_regex)

    for mn, data in FOOTY.items():
        row = START_ROW - 1 + int(mn)
        for hdr_regex, maker in FOOTY_TO_DATA_MAP.items():
            c = col_map.get(hdr_regex)
            if not c:
                continue
            try:
                val = maker(data)
            except Exception:
                val = None
            ws.cell(row=row, column=c, value=val)

# ---------- Skriv hela Excel ----------
def write_excel_bytes(template_path: str) -> bytes:
    wb = _open_wb(template_path)

    # 1) kupong → Data (om rubriker hittas)
    write_kupong_into_data_sheet(wb)
    # 2) footy → Data
    write_footy_into_data_sheet(wb)

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()
