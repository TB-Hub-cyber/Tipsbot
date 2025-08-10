# main.py
from __future__ import annotations
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, HttpUrl
from typing import List, Dict, Any, Optional
import io, datetime as dt

from excel_utils import (
    update_kupong, update_footy, write_excel_bytes, reset_state, KUPONG
)
from scrape_footy import fetch_footy, align_with_excel_names
from scrape_stryket import scrape_stryketanalysen
# (om du också har spela.svenskaspel-se-scraper:)
# from scrape_svspel import fetch_kupong as scrape_svenskaspel

TEMPLATE_XLSX = "Stryktipsanalys_MASTER.xlsx"
app = FastAPI()

class KupongList(BaseModel):
    svenskaspel: List[Dict[str, Any]]

class FootyIn(BaseModel):
    matchnr: int
    url: HttpUrl

@app.post("/svenskaspel")
def post_svenskaspel(
    maybe_list: Optional[KupongList] = Body(default=None),
    url: Optional[str] = Body(default=None),
    debug: Optional[bool] = Body(default=False)
):
    """
    Accepterar:
    1) { "svenskaspel":[{...}, ...] }  – direktdata från klienten
    2) { "url":"https://www.stryketanalysen.se/stryktipset/" } – så skrapar vi själva
       (auto-detekterar domän och väljer rätt scraper)
    """
    if maybe_list and maybe_list.svenskaspel:
        update_kupong(maybe_list.svenskaspel)
        return {"ok": True, "n": len(maybe_list.svenskaspel), "mode": "direct"}

    if url:
        try:
            if "stryketanalysen.se" in url:
                rows = scrape_stryketanalysen(url)
            # elif "svenskaspel.se" in url:
            #     rows = scrape_svenskaspel(url)   # om/ när du vill återaktivera
            else:
                raise ValueError("Okänd källa i url – använd stryketanalysen.se.")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Scrape-fel: {e}")

        update_kupong(rows)
        return {"ok": True, "n": len(rows), "mode": "scraped"}

    raise HTTPException(status_code=422, detail="Skicka {svenskaspel:[...]} ELLER {url:'...'}.")

@app.post("/footy")
def post_footy(payload: FootyIn):
    excel_home = excel_away = None
    for r in KUPONG:
        try:
            if int(r.get("matchnr")) == int(payload.matchnr):
                excel_home = (r.get("hemmalag") or "").strip()
                excel_away = (r.get("bortalag") or "").strip()
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
