from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os, traceback, asyncio

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

app = FastAPI(title="Stryktips API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ---------- Självläkning av Playwright/Chromium ----------
PW_CACHE = "/opt/render/.cache/ms-playwright"

async def _install_chromium():
    # Kör "python -m playwright install chromium"
    proc = await asyncio.create_subprocess_exec(
        "python", "-m", "playwright", "install", "chromium",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode(errors="ignore"), err.decode(errors="ignore")

async def _chromium_ok():
    # Liten sanity check: finns chrome-bin någonstans i cache?
    for root, dirs, files in os.walk(PW_CACHE):
        if "chrome" in files or "chrome-linux" in root:
            return True
    return False

@app.on_event("startup")
async def ensure_playwright_ready():
    # Sätt sökvägen (hjälper Playwright hitta browsern mellan builds)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", PW_CACHE)

    # Om cache ser tom ut – försök installera
    if not await _chromium_ok():
        rc, out, err = await _install_chromium()
        if rc != 0:
            # Sista försök: ibland hjälper ett andra körning
            rc2, out2, err2 = await _install_chromium()
            if rc2 != 0:
                print("Playwright install failed:", err or err2)
            else:
                print("Playwright installed on retry.")
        else:
            print("Playwright Chromium installed at startup.")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/reset")
def reset():
    excel_reset_state()
    return {"ok": True}

@app.post("/svenskaspel")
async def svenskaspel(req: SvsReq):
    try:
        out = await fetch_kupong(req.url, debug=req.debug)
        if "error" in out:
            resp = {"ok": False, "error": out["error"]}
            if req.debug and out.get("debug") is not None:
                resp["debug_html_len"] = len(out["debug"])
            return JSONResponse(resp, status_code=200)

        results = out.get("results", [])
        update_kupong(results)
        resp = {"ok": True, "count": len(results)}
        if req.debug and out.get("debug") is not None:
            resp["debug_html_len"] = len(out["debug"])
        return resp
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

# ---------- DEBUG ----------
@app.get("/debug/state")
def debug_state():
    return {
        "svenskaspel": excel_utils.KUPONG,
        "footy": excel_utils.FOOTY,
    }

@app.get("/debug/svs-html")
def debug_svs_html():
    p = "/tmp/svs_debug.html"
    if not os.path.exists(p):
        raise HTTPException(404, "Ingen svs_debug.html ännu – kör /svenskaspel med debug.")
    return FileResponse(p, media_type="text/html", filename="svs_debug.html")

@app.get("/debug/svs-shot")
def debug_svs_shot():
    p = "/tmp/svs_debug.png"
    if not os.path.exists(p):
        raise HTTPException(404, "Ingen svs_debug.png ännu – kör /svenskaspel med debug.")
    return FileResponse(p, media_type="image/png", filename="svs_debug.png")
