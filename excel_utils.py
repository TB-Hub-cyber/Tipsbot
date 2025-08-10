# excel_utils.py
from __future__ import annotations
from typing import Dict, Any, List, Optional
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

EXCEL_PATH = "Stryktipsanalys_MASTER.xlsx"
SHEET = "Data"

# Hjälpare: hitta kolumnindex via headertext
def _header_map(ws: Worksheet) -> Dict[str, int]:
    m: Dict[str, int] = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(row=1, column=c).value
        if isinstance(v, str) and v.strip():
            m[v.strip()] = c
    return m

def _find_row_by_matchnr(ws: Worksheet, hdr: Dict[str, int], matchnr: int) -> Optional[int]:
    col = hdr.get("Matchnr") or hdr.get("MatchNr") or hdr.get("matchnr")
    if not col:
        return None
    for r in range(2, ws.max_row + 1):
        if ws.cell(row=r, column=col).value == matchnr:
            return r
    return None

def update_kupong(rows: List[Dict[str, Any]]) -> None:
    """Skriv in stryket-data (odds, folk, spelvärde) – kolumnerna antas redan finnas."""
    wb = load_workbook(EXCEL_PATH)
    ws = wb[SHEET]
    hdr = _header_map(ws)

    need = [
        "Matchnr","Hemmalag","Bortalag",
        "Odds % 1","Odds % X","Odds % 2",
        "Folk % 1","Folk % X","Folk % 2",
        "Värde 1","Värde X","Värde 2",
    ]
    miss = [h for h in need if h not in hdr]
    if miss:
        raise RuntimeError(f"Saknar kolumner i Excel: {miss}")

    for row in rows:
        r = _find_row_by_matchnr(ws, hdr, row["matchnr"])
        if not r:
            continue
        ws.cell(r, hdr["Hemmalag"]).value = row["hemmalag"]
        ws.cell(r, hdr["Bortalag"]).value = row["bortalag"]
        ws.cell(r, hdr["Odds % 1"]).value = row.get("odds_1")
        ws.cell(r, hdr["Odds % X"]).value = row.get("odds_x")
        ws.cell(r, hdr["Odds % 2"]).value = row.get("odds_2")
        ws.cell(r, hdr["Folk % 1"]).value = row.get("folk_1")
        ws.cell(r, hdr["Folk % X"]).value = row.get("folk_x")
        ws.cell(r, hdr["Folk % 2"]).value = row.get("folk_2")
        ws.cell(r, hdr["Värde 1"]).value = row.get("spelv_1")
        ws.cell(r, hdr["Värde X"]).value = row.get("spelv_x")
        ws.cell(r, hdr["Värde 2"]).value = row.get("spelv_2")

    wb.save(EXCEL_PATH)

def update_footy(matchnr: int, data: Dict[str, Any]) -> None:
    """Skriv in Footy-data till fördefinierade kolumner (efter rubrikerna i din MASTER-fil)."""
    wb = load_workbook(EXCEL_PATH)
    ws = wb[SHEET]
    hdr = _header_map(ws)

    r = _find_row_by_matchnr(ws, hdr, matchnr)
    if not r:
        raise RuntimeError(f"Hittar ingen rad med Matchnr={matchnr}")

    # Mappning: anpassad efter rubriknamn i din fil
    mapping = {
        "Form H (senaste 5)": "form_home",
        "Form B (senaste 5)": "form_away",
        "H2H senaste 5": "h2h_last5",
        "xG H (overall)": "xg_home_overall",
        "xG H (hemma)": "xg_home_home",
        "xGA H (overall)": "xga_home_overall",
        "xGA H (hemma)": "xga_home_home",
        "Gjorda mål H (overall)": "gf_home_overall",
        "Insläppta H (overall)": "ga_home_overall",
        "xG B (overall)": "xg_away_overall",
        "xG B (borta)": "xg_away_away",
        "xGA B (overall)": "xga_away_overall",
        "xGA B (borta)": "xga_away_away",
        "Gjorda mål B (overall)": "gf_away_overall",
        "Insläppta B (overall)": "ga_away_overall",
        "PPG H (overall)": "ppg_home_overall",
        "PPG H (hemma)": "ppg_home_home",
        "PPG B (overall)": "ppg_away_overall",
        "PPG B (borta)": "ppg_away_away",
        "Footy-källa": "source",
    }

    for col_header, key in mapping.items():
        c = hdr.get(col_header)
        if not c:
            # hoppa tyst om kolumn inte finns (så vi kan lägga till i filen utan krasch)
            continue
        ws.cell(row=r, column=c).value = data.get(key)

    wb.save(EXCEL_PATH)
