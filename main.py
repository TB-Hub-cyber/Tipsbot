from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from models import SvsReq, FootyReq
from scrape_svspel import fetch_kupong
from scrape_footy import fetch_footy
from excel_utils import (
    update_kupong,
    update_footy,
    write_excel_bytes,
    reset_state as excel_reset_state,
)
import excel_utils  # för att läsa state i /debug/state

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
    out = await fetch_kupong(req.url, debug=req.debug)
    update_kupong(out["results"])
    if req.debug and out.get("debug"):
        return {"count": len(out["results"]), "debug_html_len": len(out["debug"] or "")}
    return {"count": len(out["results"])}

@app.post("/footy")
async def footy(req: FootyReq):
    data = await fetch_footy(req.url, debug=req.debug)
    update_footy(req.matchnr, data)
    if req.debug and data.get("debug"):
        return {"ok": True, "debug_html_len": len(data["debug"] or "")}
    return {"ok": True}

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
    Visar vad som just nu ligger i minnet på servern.
    'svenskaspel' är listan med matcher/odds/streck.
    'footy' är en dict: matchnr -> footydata.
    """
    return {
        "svenskaspel": excel_utils.KUPONG,  # list[dict]
        "footy": excel_utils.FOOTY,        # dict[int, dict]
    }
