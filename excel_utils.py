from openpyxl import load_workbook
from openpyxl.utils import get_column_letter, column_index_from_string

# Kolumnindex för våra huvudfält (1-baserat, dvs A=1)
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
    "spelv_1": 10,      # J (ny kolumn om den saknas)
    "spelv_x": 11,      # K
    "spelv_2": 12,      # L
}

def _ensure_layout(ws):
    """
    Säkerställ att:
      - J,K,L finns och heter Spelvärde 1/X/2 (annars: insert 3 kolumner på J)
      - Kolumner AK, AL, AM tas bort om de finns
    """
    # 1) Lägg till J:K:L = Spelvärde 1/X/2 om J1 != "Spelvärde 1"
    header_j = (ws.cell(row=1, column=COLS["spelv_1"]).value or "").strip() if ws.max_column >= COLS["spelv_1"] else ""
    if header_j != "Spelvärde 1":
        ws.insert_cols(COLS["spelv_1"], amount=3)
        ws.cell(row=1, column=COLS["spelv_1"], value="Spelvärde 1")
        ws.cell(row=1, column=COLS["spelv_x"], value="Spelvärde X")
        ws.cell(row=1, column=COLS["spelv_2"], value="Spelvärde 2")

    # 2) Ta bort AK, AL, AM i omvänd ordning
    for col_letter in ["AM", "AL", "AK"]:
        idx = column_index_from_string(col_letter)
        if ws.max_column >= idx:
            ws.delete_cols(idx, 1)

def update_excel(file_path, svenskaspel_data):
    """
    Uppdatera Excel-filen med nya data från svenskaspel_data.
    svenskaspel_data = lista med dictar:
      {
        matchnr, hemmalag, bortalag,
        odds_1, odds_x, odds_2,
        folk_1, folk_x, folk_2,
        spelv_1, spelv_x, spelv_2
      }
    """
    wb = load_workbook(file_path)
    ws = wb.active

    _ensure_layout(ws)

    for match in svenskaspel_data:
        row_idx = match["matchnr"] + 1  # rad 2..14
        ws.cell(row=row_idx, column=COLS["matchnr"], value=match["matchnr"])
        ws.cell(row=row_idx, column=COLS["hemmalag"], value=match["hemmalag"])
        ws.cell(row=row_idx, column=COLS["bortalag"], value=match["bortalag"])
        ws.cell(row=row_idx, column=COLS["odds_1"], value=match["odds_1"])
        ws.cell(row=row_idx, column=COLS["odds_x"], value=match["odds_x"])
        ws.cell(row=row_idx, column=COLS["odds_2"], value=match["odds_2"])
        ws.cell(row=row_idx, column=COLS["folk_1"], value=match["folk_1"])
        ws.cell(row=row_idx, column=COLS["folk_x"], value=match["folk_x"])
        ws.cell(row=row_idx, column=COLS["folk_2"], value=match["folk_2"])
        ws.cell(row=row_idx, column=COLS["spelv_1"], value=match["spelv_1"])
        ws.cell(row=row_idx, column=COLS["spelv_x"], value=match["spelv_x"])
        ws.cell(row=row_idx, column=COLS["spelv_2"], value=match["spelv_2"])

    wb.save(file_path)
    wb.close()
