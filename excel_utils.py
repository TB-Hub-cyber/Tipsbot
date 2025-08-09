# excel_utils.py – HEL & kompatibel med main.py (update_kupong + write_excel_bytes)
from __future__ import annotations
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string
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
# Efter layoutfixen ligger Spelvärde i J:K:L.
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
    if col:
        ws.cell(row=row, column=col, value=value)

def _ensure_layout(ws):
    """
    Säkerställ att:
      - J,K,L finns och heter Spelvärde 1/X/2 (infoga 3 kolumner från J om saknas)
      - Kolumner AK, AL, AM tas bort om de finns (alltid, i omvänd ordning)
    """
    # 1) Spelvärdekolumner på J:K:L
    header_j = (ws.cell(row=1, column=COLS["spelv_1"]).value or "").strip() if ws.max_column >= COLS["spelv_1"] else ""
    if header_j != "Spelvärde 1":
        ws.insert_cols(COLS["spelv_1"], amount=3)
        ws.cell(row=1, column=COLS["spelv_1"], value="Spelvärde 1")
        ws.cell(row=1, column=COLS["spelv_x"], value="Spelvärde X")
        ws.cell(row=1, column=COLS["spelv_2"], value="Spelvärde 2")

    # 2) Ta bort AK, AL, AM i omvänd ordning så index inte flyttar sig
    for col_letter in ["AM", "AL", "AK"]:
        idx = column_index_from_string(col_letter)
        if ws.max_column >= idx:
            ws.delete_cols(idx, 1)

# ---------- API som main.py anropar ----------
def update_kupong(rows: List[Dict[str, Any]]):
    """
    Tar listan från scrapen (13 rader) och normaliserar nycklarna.
    Vi skriver inte till fil här – vi sparar i KUPONG och låter
    write_excel_bytes() göra själva skrivningen vid nedladdning.
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
    """Valfri: spara FootyStats-data per matchnr (för din andra flik)."""
    FOOTY[matchnr] = data or {}

def write_excel_bytes(template_path: str) -> bytes:
    """
    Öppnar mallen, justerar layouten (J:K:L + ta bort AK/AL/AM), skriver KUPONG
    (+ ev. FOOTY) och returnerar filen som bytes.
    """
    wb = load_workbook(template_path)
    ws = wb[SHEET_NAME] if SHEET_NAME and SHEET_NAME in wb.sheetnames else wb.active

    # Säkerställ layout
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

    # (Valfritt) skriv FOOTY på egen flik
    # if "Footy" in wb.sheetnames and FOOTY:
    #     wf = wb["Footy"]
    #     for mn, data in FOOTY.items():
    #         row = START_ROW - 1 + mn
    #         wf.cell(row=row, column=1, value=mn)
    #         # ... fyll fler fält här

    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
