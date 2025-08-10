# main.py
from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, HttpUrl
from typing import List, Dict, Any
import io
import datetime as dt

from excel_utils import (
    update_kupong, update_footy, write_excel_bytes, reset_state, KUPONG
)
from scrape_footy import fetch_footy, align_with_excel_names

TEMPLATE_XLSX = "Stryktipsanalys_MASTER.xlsx"  # lägg denna i repo-roten

app = FastAPI()

class KupongIn(BaseModel):
    svenskaspel: List[Dict[str, Any]]

class FootyIn(BaseModel):
    matchnr: int
    url: HttpUrl

@app.post("/svenskaspel")
def post_svenskaspel(payload: KupongIn):
    update_kupong(payload.svenskaspel)
    return {"ok": True, "n": len(payload.svenskaspel)}

@app.post("/footy")
def post_footy(payload: FootyIn):
    excel_home = excel_away = None
    for r in KUPONG:
        try:
            if int(r.get("matchnr")) == int(payload.matchnr):
                excel_home = r.get("hemmalag") or ""
                excel_away = r.get("bortalag") or ""
                break
        except Exception:
            continue

    try:
        data = fetch_footy(str(payload.url), payload.matchnr)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Footy-fel: {e}")

    if excel_home and excel_away:
        h = data.get("home", {}).get("name") or ""
        a = data.get("away", {}).get("name") or ""
        nh, na, swapped = align_with_excel_names(h, a, excel_home, excel_away)
        if swapped:
            data["home"], data["away"] = data["away"], data["home"]
            data["home"]["name"], data["away"]["name"] = nh, na

    update_footy(payload.matchnr, data)
    return {"ok": True, "matchnr": payload.matchnr,
            "home": data.get("home", {}).get("name"),
            "away": data.get("away", {}).get("name")}

@app.get("/excel")
def get_excel():
    try:
        blob = write_excel_bytes(TEMPLATE_XLSX)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Excel-fel: {e}")
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"Stryktipsanalys_fylld_{ts}.xlsx"
    return StreamingResponse(
        io.BytesIO(blob),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'}
    )

@app.post("/reset")
def post_reset():
    reset_state()
    return {"ok": True}

@app.get("/")
def root():
    return JSONResponse({"ok": True, "endpoints": ["/svenskaspel", "/footy", "/excel", "/reset"]})
