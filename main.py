# -*- coding: utf-8 -*-
# main.py – FastAPI-backend som anropas från Pythonista-klienten.

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os, asyncio, traceback

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
PW_CACHE = "/opt/render/.cache/ms-playwright"
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", PW_CACHE)

app = FastAPI(title="Stryktips API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ---- Självläkning av Playwright/Chromium vid uppstart ----
async def _chromium_present() -> bool:
    if not os.path.isdir(PW_CACHE):
        return False
    for root, dirs, files in os.walk(PW_CACHE):
        if "chrome" in files:
            return True
    return False

async def _install_chromium():
    proc = await asyncio.create_subprocess_exec(
        "python", "-m", "playwright", "install", "chromium",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        print("[startup] playwright install chromium failed:", err.decode(errors="ignore"))
    else:
        print("[startup] playwright chromium installed.")

@app.on_event("startup")
async def startup():
    if not await _chromium_present():
        await _install_chromium()

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/reset")
def reset():
    excel_reset_state()
    return {"ok": True}

@app.post("/svenskaspel")
async def svenskaspel(req: SvsReq):
    """
    Hämtar kupongen. Returnerar {ok:true,count:N} eller {ok:false,error:"..."}.
    """
    try:
        out = await fetch_kupong(req.url, debug=req.debug)
        if "error" in out:
            resp = {"ok": False, "error": out["error"]}
            return JSONResponse(resp, status_code=200)

        results = out.get("results", [])
        # Uppdatera Excel-state (tål att folk_* är None)
        update_kupong(results)
        return {"ok": True, "count": len(results)}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e)}

@app.post("/footy")
async def footy(req: FootyReq):
    try:
        data = await fetch_footy(req.url, debug=req.debug)
        if not isinstance(data, dict) or not data:
            return {"ok": False, "matchnr": req.matchnr, "error": "Ingen data från Footy."}
        update_footy(req.matchnr, data)
        resp = {"ok": True, "matchnr": req.matchnr}
        if req.debug and data.get("debug") is not None:
            resp["debug_html_len"] = len(data["debug"])
        return resp
    except Exception as e:
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

# ---- DEBUG ----
@app.get("/debug/state")
def debug_state():
    return {"svenskaspel": excel_utils.KUPONG, "footy": excel_utils.FOOTY}

@app.get("/")
def root():
    return {"service": "tipsbot", "status": "ok"}
