# -*- coding: utf-8 -*-
# main.py – komplett API för Stryktipsflödet med källväxling (SVS/Stryketanalysen)

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os, asyncio, traceback

# ====== Importer från ditt projekt ======
# models.py ska definiera SvsReq(url:str, debug:bool=False) och FootyReq(matchnr:int, url:str, debug:bool=False)
from models import SvsReq, FootyReq

# Scrapers
from scrape_svspel import fetch_kupong as fetch_svs   # async
from scrape_stryket import fetch_stryket              # sync

# Excel-hjälpare (din befintliga excel_utils)
from excel_utils import (
    update_kupong,     # tar list[dict] (matchnr, hemmalag, bortalag, odds_1, odds_x, odds_2, folk_1..)
    update_footy,      # skriver FootyStats per matchnr
    write_excel_bytes, # returnerar bytes för aktuell arbetsbok (från template)
    reset_state as excel_reset_state,  # nollställer in-memory state (KUPONG/FOOTY)
)
import excel_utils  # för att exponera KUPONG/FOOTY i /debug/state

# ====== Konfig ======
TEMPLATE = "Stryktipsanalys_MASTER.xlsx"
PW_CACHE = "/opt/render/.cache/ms-playwright"
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", PW_CACHE)

app = FastAPI(title="Stryktips API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ====== Playwright-självläkning vid uppstart ======
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
    # Installera Chromium om Render-cachen rensats
    if not await _chromium_present():
        await _install_chromium()

# ====== Hälso-/verktygsendpoints ======
@app.get("/health")
def health():
    return {"ok": True}

@app.post("/reset")
def reset():
    excel_reset_state()
    return {"ok": True}

# ====== Kupong: auto-källa (SVS eller Stryketanalysen) ======
@app.post("/svenskaspel")
async def svenskaspel(req: SvsReq):
    """
    Hämtar och skriver kupongen:
      - Om URL innehåller 'svenskaspel.se' → Playwright-scrape (async)
      - Om URL innehåller 'stryketanalysen.se' → requests/BS4-scrape (sync)
    Returnerar alltid 200 med {ok:true/false, ...} så klienten kan visa fel snyggt.
    """
    try:
        url = (req.url or "").strip()
        if not url:
            return {"ok": False, "error": "Ingen URL angiven."}

        # Välj källa
        if "svenskaspel.se" in url:
            out = await fetch_svs(url, debug=req.debug)
            källa = "Svenska Spel"
        elif "stryketanalysen.se" in url:
            out = fetch_stryket(url)
            källa = "Stryketanalysen"
        else:
            return {"ok": False, "error": "Okänd kupongkälla. Ange URL från SVS eller Stryketanalysen."}

        # Fel från scraper
        if "error" in out:
            resp = {"ok": False, "källa": källa, "error": out["error"]}
            # Vid SVS och debug kan fetch_svs ha lagt in debug-html i /tmp via sin egen logik
            return JSONResponse(resp, status_code=200)

        results = out.get("results", [])
        if not results:
            return {"ok": False, "källa": källa, "error": "Inga matcher hittades."}

        # Skriv in i vår arbetsbok/state
        update_kupong(results)
        return {"ok": True, "källa": källa, "count": len(results)}

    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e)}

# ====== FootyStats (låt ligga kvar om du använder det i ditt flöde) ======
@app.post("/footy")
async def footy(req: FootyReq):
    """
    Hämta FootyStats-data (scrape_footy.fetch_footy bör redan finnas i ditt projekt).
    """
    try:
        from scrape_footy import fetch_footy  # lazy import för att undvika import-fel vid tom fil
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

# ====== Excel-download ======
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

# ====== Debug ======
@app.get("/debug/state")
def debug_state():
    """
    Inspecta serverns in-memory data.
    'svenskaspel' = list[dict] med matcher (senaste kupongen)
    'footy'       = dict[int, dict] per matchnr
    """
    return {"svenskaspel": excel_utils.KUPONG, "footy": excel_utils.FOOTY}

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

@app.get("/")
def root():
    return {"service": "tipsbot", "status": "ok"}
