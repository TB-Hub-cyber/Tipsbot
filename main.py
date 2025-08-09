# -*- coding: utf-8 -*-
# main.py – komplett API för Stryktipsflödet med källväxling (SVS/Stryketanalysen)
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os, asyncio, traceback

# ---- Projektmoduler ----
# models.py ska innehålla:
#   class SvsReq(BaseModel): url: Any; debug: bool = False
#   class FootyReq(BaseModel): matchnr: int; url: Any; debug: bool = False
from models import SvsReq, FootyReq

# Scrapers
from scrape_svspel import fetch_kupong as fetch_svs   # async
from scrape_stryket import fetch_stryket              # sync

# Excel-hjälpare
from excel_utils import (
    update_kupong, update_footy, write_excel_bytes, reset_state as excel_reset_state
)
import excel_utils  # för /debug/state

# ---- Konfig ----
TEMPLATE = "Stryktipsanalys_MASTER.xlsx"
PW_CACHE = "/opt/render/.cache/ms-playwright"
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", PW_CACHE)

app = FastAPI(title="Stryktips API", version="1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ---- Självläkning: installera Chromium om cachen är tom ----
async def _chromium_present() -> bool:
    if not os.path.isdir(PW_CACHE):
        return False
    for _, _, files in os.walk(PW_CACHE):
        if "chrome" in files:
            return True
    return False

async def _install_chromium():
    proc = await asyncio.create_subprocess_exec(
        "python", "-m", "playwright", "install", "chromium",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    print("[startup] playwright install chromium ->", proc.returncode)

@app.on_event("startup")
async def startup():
    if not await _chromium_present():
        await _install_chromium()

# ---- Utility endpoints ----
@app.get("/health")
def health():
    return {"ok": True}

@app.post("/reset")
def reset():
    excel_reset_state()
    return {"ok": True}

# ---- Kupong (auto-källa) ----
@app.post("/svenskaspel")
async def svenskaspel(req: SvsReq):
    """
    Hämtar kupongen och skriver den till serverns arbetsbok/state.
    Källval:
      - URL innehåller 'svenskaspel.se'  -> Playwright-scrape (async)
      - URL innehåller 'stryketanalysen.se' -> requests/BS4-scrape (sync)
    Returnerar alltid 200 med {ok: bool, ...} så klienten kan visa fel snyggt.
    """
    try:
        url = str(req.url).strip()  # <— viktig fix för pydantic Url
        if not url:
            return {"ok": False, "error": "Ingen URL angiven."}

        if "svenskaspel.se" in url:
            out = await fetch_svs(url, debug=req.debug)
            källa = "Svenska Spel"
        elif "stryketanalysen.se" in url:
            out = fetch_stryket(url)
            källa = "Stryketanalysen"
        else:
            return {"ok": False, "error": "Okänd kupongkälla. Ange SVS- eller Stryketanalysen-URL."}

        if "error" in out:
            return {"ok": False, "källa": källa, "error": out["error"]}

        results = out.get("results", [])
        if not results:
            return {"ok": False, "källa": källa, "error": "Inga matcher hittades."}

        update_kupong(results)
        return {"ok": True, "källa": källa, "count": len(results)}

    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e)}

# ---- FootyStats (om du använder det flödet) ----
@app.post("/footy")
async def footy(req: FootyReq):
    try:
        from scrape_footy import fetch_footy  # lazy import
        data = await fetch_footy(str(req.url).strip(), debug=req.debug)
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

# ---- Excel-download ----
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

# ---- Debug ----
@app.get("/debug/state")
def debug_state():
    return {"svenskaspel": excel_utils.KUPONG, "footy": excel_utils.FOOTY}

@app.get("/debug/svs-html")
def debug_svs_html():
    p = "/tmp/svs_debug.html"
    if not os.path.exists(p):
        raise HTTPException(404, "Ingen svs_debug.html ännu – kör /svenskaspel med debug=True.")
    return FileResponse(p, media_type="text/html", filename="svs_debug.html")

@app.get("/debug/svs-shot")
def debug_svs_shot():
    p = "/tmp/svs_debug.png"
    if not os.path.exists(p):
        raise HTTPException(404, "Ingen svs_debug.png ännu – kör /svenskaspel med debug=True.")
    return FileResponse(p, media_type="image/png", filename="svs_debug.png")

@app.get("/")
def root():
    return {"service": "tipsbot", "status": "ok"}
