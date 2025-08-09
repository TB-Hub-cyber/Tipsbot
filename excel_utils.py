import io
from typing import Dict, Any, List
from openpyxl import load_workbook
import threading

STATE_LOCK = threading.Lock()
KUPONG: List[Dict[str, Any]] = []
FOOTY: Dict[int, Dict[str, Any]] = {}

def write_excel_bytes(template_path: str) -> bytes:
    with open(template_path, "rb") as f:
        base_bytes = f.read()
    bio_in = io.BytesIO(base_bytes)
    wb = load_workbook(bio_in)
    ws = wb["Data"]

    header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = {name: i+1 for i, name in enumerate(header)}

    def col(*names):
        for n in names:
            if n in idx: return idx[n]
        return None

    C_MATCH = col("Match", "Matchnr")
    C_HOME  = col("Hemmalag")
    C_AWAY  = col("Bortalag")
    C_F1 = col("Folkets val 1")
    C_FX = col("Folkets val X")
    C_F2 = col("Folkets val 2")
    C_O1 = col("Odds 1")
    C_OX = col("Odds X")
    C_O2 = col("Odds 2")

    FOOTY_MAP = [
        ("xG H (overall)", ("xG","H","overall")),
        ("xG H (hemma)",   ("xG","H","home")),
        ("xGA H (overall)",("xGA","H","overall")),
        ("xGA H (hemma)",  ("xGA","H","home")),
        ("Gjorda mål/sn H (overall)", ("scored","H","overall")),
        ("Insläppta/sn H (overall)",  ("conceded","H","overall")),

        ("xG B (overall)", ("xG","B","overall")),
        ("xG B (borta)",   ("xG","B","away")),
        ("xGA B (overall)",("xGA","B","overall")),
        ("xGA B (borta)",  ("xGA","B","away")),
        ("Gjorda mål/sn B (overall)", ("scored","B","overall")),
        ("Insläppta/sn B (overall)",  ("conceded","B","overall")),

        ("PPG H (overall)", ("ppg","H","overall")),
        ("PPG H (hemma)",   ("ppg","H","home")),
        ("PPG B (overall)", ("ppg","B","overall")),
        ("PPG B (borta)",   ("ppg","B","away")),

        ("Form H (senaste 5)", ("form","H","last5")),
        ("Hemmaform H (senaste 5)", ("form","H","home5")),
        ("Bortaform H (senaste 5)", ("form","H","away5")),
        ("Form B (senaste 5)", ("form","B","last5")),
        ("Hemmaform B (senaste 5)", ("form","B","home5")),
        ("Bortaform B (senaste 5)", ("form","B","away5")),
        ("H2H senaste 5", ("h2h","txt","5")),
    ]

    match_to_row = {}
    for row in ws.iter_rows(min_row=2, values_only=False):
        try:
            m = int(row[C_MATCH-1].value)
            match_to_row[m] = row[0].row
        except Exception:
            pass

    with STATE_LOCK:
        for item in KUPONG:
            r = match_to_row.get(item.get("match"))
            if not r: continue
            if C_HOME: ws.cell(r, C_HOME, item.get("home"))
            if C_AWAY: ws.cell(r, C_AWAY, item.get("away"))
            if C_F1: ws.cell(r, C_F1, item.get("folkets_1"))
            if C_FX: ws.cell(r, C_FX, item.get("folkets_x"))
            if C_F2: ws.cell(r, C_F2, item.get("folkets_2"))
            if C_O1: ws.cell(r, C_O1, item.get("odds_1"))
            if C_OX: ws.cell(r, C_OX, item.get("odds_x"))
            if C_O2: ws.cell(r, C_O2, item.get("odds_2"))

        for mnr, data in FOOTY.items():
            r = match_to_row.get(mnr)
            if not r: continue
            for colname, path in FOOTY_MAP:
                c = idx.get(colname)
                if not c: continue
                bucket, side, key = path
                val = None
                if bucket in ("xG","xGA"):
                    val = data.get(bucket, {}).get(side, {}).get(key)
                elif bucket in ("scored","conceded","ppg","form"):
                    val = data.get(bucket, {}).get(side, {}).get(key)
                elif bucket == "h2h":
                    val = data.get("h2h", {}).get("txt")
                if val is not None:
                    ws.cell(r, c, val)

    bio_out = io.BytesIO()
    wb.save(bio_out)
    return bio_out.getvalue()

def update_kupong(items: list):
    with STATE_LOCK:
        global KUPONG
        KUPONG = items

def update_footy(matchnr: int, data: Dict[str, Any]):
    with STATE_LOCK:
        FOOTY[matchnr] = data

def reset_state():
    with STATE_LOCK:
        KUPONG.clear()
        FOOTY.clear()
