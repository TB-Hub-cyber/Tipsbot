from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import scrape_svspel, scrape_footy, excel_utils

app = FastAPI()

# Håller allt i minnet
state = {
    "svenskaspel": {},
    "footy": {}
}

class SvenskaspelInput(BaseModel):
    url: str
    debug: Optional[bool] = False

class FootyInput(BaseModel):
    matchnr: int
    url: str
    debug: Optional[bool] = False

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/reset")
def reset_state():
    state["svenskaspel"] = {}
    state["footy"] = {}
    return {"status": "reset", "state": state}

@app.post("/svenskaspel")
async def fill_svenskaspel(data: SvenskaspelInput):
    kupong_data, debug_len = await scrape_svspel.run(data.url, data.debug)
    state["svenskaspel"] = kupong_data
    excel_utils.fill_svenskaspel(kupong_data)
    return {
        "status": "ok",
        "count": len(kupong_data.get("matcher", [])),
        "debug_html_len": debug_len if data.debug else None
    }

@app.post("/footy")
async def fill_footy(data: FootyInput):
    footy_data, debug_len = await scrape_footy.run(data.url, data.debug)
    state["footy"][data.matchnr] = footy_data
    excel_utils.fill_footy(data.matchnr, footy_data)
    return {
        "status": "ok",
        "matchnr": data.matchnr,
        "debug_html_len": debug_len if data.debug else None
    }

@app.get("/excel/download")
def download_excel():
    path = excel_utils.get_excel_path()
    return fastapi.responses.FileResponse(path, filename="Stryktipsanalys_fylld.xlsx")

@app.get("/debug/state")
def debug_state():
    """
    Returnerar hela nuvarande state i serverminnet.
    Kan användas för att felsöka vad som är ifyllt hittills.
    """
    return {
        "svenskaspel": state.get("svenskaspel", {}),
        "footy": state.get("footy", {})
    }
