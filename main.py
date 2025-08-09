from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import traceback

from models import SvsReq, FootyReq
from scrape_svspel import fetch_kupong
from scrape_footy import fetch_footy
from excel_utils import (
    update_kupong,
    update_footy,
    write_excel_bytes,
    reset_state as excel_reset_state,
)
import excel_utils  # för /debug/state

TEMPLATE = "Stryktipsanalys_MASTER.xlsx"

app = FastAPI(title="Stryktips API (no API key)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/svenskaspel")
async def svenskaspel(req: SvsReq):
    """
    Hämtar kupongen från Svenska Spel.
    Returnerar aldrig 500 – utan {ok:false, error:"..."} vid fel så klienten kan logga och fortsätta.
    """
    try:
        out = await fetch_kupong(req.url, debug=req.debug)
        results = out.get("results", []) if isinstance(out, dict) else []
        if not results:
            return {"ok": False, "error": "Inga matcher hittades på sidan.", "debug_html_len": len(out.get("debug") or "") if isinstance(out, dict) else 0}
        update_kupong(results)
        resp = {"ok": True, "count": len(results)}
        if req.debug and isinstance(out, dict) and out.get("debug") is not None:
            resp["debug_html_len"] = len(out["debug"])
        return resp
    except Exception as e:
        print("SVS ERROR:", e)
        traceback.print_exc()
        return {"ok": False, "error": str(e)}

@app.post("/footy")
async def footy(req: FootyReq):
    """
    Hämtar FootyStats-data för en given länk + matchnr.
    Returnerar {ok:false, error:"..."} vid fel.
    """
    try:
        data = await fetch_footy(req.url, debug=req.debug)
        if not isinstance(data, dict) or not data:
            return {"ok": False, "error": "Ingen data från FootyStats."}
        update_footy(req.matchnr, data)
        resp = {"ok": True, "matchnr": req.matchnr}
        if req.debug and data.get("debug") is not None:
            resp["debug_html_len"] = len(data["debug"])
        return resp
    except Exception as e:
        print(f"FOOTY ERROR M{req.matchnr}:", e)
        traceback.print_exc()
        return {"ok": False, "matchnr": req.matchnr, "error": str(e)}

@app.get("/excel/download")
def excel_download():
    try:
        data = write_excel_bytes(TEMPLATE)
    except FileNotFoundError:
        raise HTTPException(500, "Template not found")
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Stryktipsanalys_fylld.xlsx"},
    )

@app.post("/reset")
def reset():
    excel_reset_state()
    return {"ok": True}

@app.get("/debug/state")
def debug_state():
    """
    Visar vad som ligger i minnet just nu.
    'svenskaspel' = list[dict] med matcher/odds/streck.
    'footy' = dict: matchnr -> footydata.
    """
    return {
        "svenskaspel": excel_utils.KUPONG,
        "footy": excel_utils.FOOTY,
    }
