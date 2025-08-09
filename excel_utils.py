# excel_utils.py – HEL (med auto-insättning av Spelvärde J:K:L + borttagning AK:AP)
from __future__ import annotations
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string
from io import BytesIO
from typing import Dict, Any, List

# ---------------- Debug-state ----------------
KUPONG: List[Dict[str, Any]] = []
FOOTY: Dict[int, Dict[str, Any]] = {}

def reset_state():
    global KUPONG, FOOTY
    KUPONG = []
    FOOTY = {}

# ----------- Kolumnlayout (1-baserad) ----------
# A=1, B=2, ...
# Efter vår layout-fix är:
#   J,K,L = Spelvärde 1/X/2
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
    "spelv_1": 10,      # J  (läggs in automatiskt om saknas)
    "spelv_x": 11,      # K
    "spelv_2": 12,      # L
}
START_ROW = 2          # första dataraden
SHEET_NAME = None      # None = aktiv flik; annars t.ex. "Stryktips"

# --------- Hjälpare ----------
def _put(ws, row: int, key: str, value):
    col = COLS.get(key)
    if col:
        ws.cell(row=row, column=col, value=value)

def _pick(d: dict, *names, default=None):
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return default

def _ensure_layout(ws):
    """
    Säkerställ att:
      - J,K,L finns och heter Spelvärde 1/X/2 (annars: insert 3 kolumner på J)
      - Kolumner AK..AP tas bort om de finns
    Körs varje gång innan vi skriver data, men gör faktiska ändringar bara om det behövs.
    """
    # 1) Lägg till J:K:L = Spelvärde 1/X/2 om J1 != "Spelvärde 1"
    header_j = (ws.cell(row=1, column=COLS["spelv_1"]).value or "").strip() if ws.max_column >= COLS["spelv_1"] else ""
    if header_j != "Spelvärde 1":
        # Skjut allt från J och höger: lägg in tre kolumner från J
        ws.insert_cols(COLS["spelv_1"], amount=3)
        ws.cell(row=1, column=COLS["spelv_1"], value="Spelvärde 1")
        ws.cell(row=1, column=COLS["spelv_x"], value="Spelvärde X")
        ws.cell(row=1, column=COLS["spelv_2"], value="Spelvärde 2")

    # 2) Ta bort AK..AP om de finns
    idx_AK = column_index_from_string("AK")  # 37
    idx_AP = column_index_from_string("AP")  # 42
    # Ta bort bakifrån så index inte flyttar sig före nästa radering
    if ws.max_column >= idx_AK:
        for c in range(min(ws.max_column, idx_AP), idx_AK - 1, -1):
            ws.delete_cols(c, 1)

# --------- API som kallas från main.py ----------
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
    Öppnar mallen, justerar layouten (J:K:L + rensa AK:AP), skriver KUPONG (+ ev. FOOTY)
    och returnerar filen som bytes.
    """
    wb = load_workbook(template_path)
    ws = wb[SHEET_NAME] if SHEET_NAME and SHEET_NAME in wb.sheetnames else wb.active

    # Se till att layouten stämmer (infoga Spelvärde-kolumner + rensa AK:AP)
    _ensure_layout(ws)

    # Skriv kupongen
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

    # (Valfritt) skriv FOOTY på en separat flik om du har en sådan.
    # if "Footy" in wb.sheetnames and FOOTY:
    #     wf = wb["Footy"]
    #     for mn, data in FOOTY.items():
    #         row = START_ROW - 1 + mn
    #         wf.cell(row=row, column=1, value=mn)
    #         # ... osv

    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
