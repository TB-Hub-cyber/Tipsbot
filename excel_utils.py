# excel_utils.py – No-op layout (respekterar din mall)
from __future__ import annotations
from openpyxl import load_workbook
from io import BytesIO
from typing import Dict, Any, List

# ---------- Debug-state som /debug/state visar ----------
KUPONG: List[Dict[str, Any]] = []
FOOTY: Dict[int, Dict[str, Any]] = {}

def reset_state():
    global KUPONG, FOOTY
    KUPONG = []
    FOOTY = {}

# ---------- Kolumnlayout (1-baserad) ----------
# A=1, B=2, ...
# Din mall har Spelvärde i J:K:L – vi skriver bara dit.
COLS = {
    "matchnr": 1,       # A
    "hemmalag": 2,      # B
    "bortalag": 3,      # C
    "odds_1": 4,        # D
    "odds_x": 5,        # E
    "odds_2": 6,        # F
    "folk_1": 7,        # G
    "folk_x": 8,        # H
    "folk_2": 9,        # I
    "spelv_1": 10,      # J
    "spelv_x": 11,      # K
    "spelv_2": 12,      # L
}
START_ROW = 2          # första dataraden (2..14 för 13 matcher)
SHEET_NAME = None      # None = aktiv flik; eller sätt till t.ex. "Stryktips"

def _pick(d: dict, *names, default=None):
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return default

def _put(ws, row: int, key: str, value):
    col = COLS.get(key)
    if col is not None:
        ws.cell(row=row, column=col, value=value)

def _ensure_layout(ws):
    """
    Respektera mallen. Gör inget med kolumner.
    Sätt bara rubriker i J/K/L om de helt saknas.
    """
    header_j = (ws.cell(row=1, column=COLS["spelv_1"]).value or "").strip()
    header_k = (ws.cell(row=1, column=COLS["spelv_x"]).value or "").strip()
    header_l = (ws.cell(row=1, column=COLS["spelv_2"]).value or "").strip()

    if not header_j and not header_k and not header_l:
        ws.cell(row=1, column=COLS["spelv_1"], value="Spelvärde 1")
        ws.cell(row=1, column=COLS["spelv_x"], value="Spelvärde X")
        ws.cell(row=1, column=COLS["spelv_2"], value="Spelvärde 2")
    # i övrigt: rör inget

# ---------- API som main.py anropar ----------
def update_kupong(rows: List[Dict[str, Any]]):
    """
    Lagra kupongrader (13 st). Skrivs till Excel vid write_excel_bytes().
    """
    global KUPONG
    KUPONG = []
    for i, r in enumerate(rows[:13], start=1):
        KUPONG.append({
            "matchnr": _pick(r, "matchnr", default=i),
            "hemmalag": _pick(r, "hemmalag", "home"),
            "bortalag": _pick(r, "bortalag", "away"),
            "odds_1": _pick(r, "odds_1", "odds1"),
            "odds_x": _pick(r, "odds_x", "oddsx"),
            "odds_2": _pick(r, "odds_2", "odds2"),
            "folk_1": _pick(r, "folk_1", "folk1"),
            "folk_x": _pick(r, "folk_x", "folkx"),
            "folk_2": _pick(r, "folk_2", "folk2"),
            "spelv_1": _pick(r, "spelv_1"),
            "spelv_x": _pick(r, "spelv_x"),
            "spelv_2": _pick(r, "spelv_2"),
        })

def update_footy(matchnr: int, data: Dict[str, Any]):
    """Valfri: spara FootyStats-data per matchnr (för ev. separat flik)."""
    FOOTY[matchnr] = data or {}

def write_excel_bytes(template_path: str) -> bytes:
    """
    Öppnar mallen, säkerställer rubriker i J/K/L om de saknas,
    skriver KUPONG (och ev. FOOTY), och returnerar bytes.
    """
    wb = load_workbook(template_path)
    ws = wb[SHEET_NAME] if SHEET_NAME and SHEET_NAME in wb.sheetnames else wb.active

    _ensure_layout(ws)

    # Skriv kupongraderna
    for i, r in enumerate(KUPONG, start=0):
        row = START_ROW + i
        _put(ws, row, "matchnr", r.get("matchnr"))
        _put(ws, row, "hemmalag", r.get("hemmalag"))
        _put(ws, row, "bortalag", r.get("bortalag"))
        _put(ws, row, "odds_1", r.get("odds_1"))
        _put(ws, row, "odds_x", r.get("odds_x"))
        _put(ws, row, "odds_2", r.get("odds_2"))
        _put(ws, row, "folk_1", r.get("folk_1"))
        _put(ws, row, "folk_x", r.get("folk_x"))
        _put(ws, row, "folk_2", r.get("folk_2"))
        _put(ws, row, "spelv_1", r.get("spelv_1"))
        _put(ws, row, "spelv_x", r.get("spelv_x"))
        _put(ws, row, "spelv_2", r.get("spelv_2"))

    # (Valfritt) skriv FOOTY på egen flik om du vill i framtiden
    # if "Footy" in wb.sheetnames and FOOTY:
    #     wf = wb["Footy"]
    #     for mn, data in FOOTY.items():
    #         row = START_ROW - 1 + mn
    #         wf.cell(row=row, column=1, value=mn)
    #         # Fyll fler fält här...

    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
