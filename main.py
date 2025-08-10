# main.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Egna moduler
from scrape_stryket import scrape_stryketanalysen          # returnerar list[dict] för 13 matcher
from scrape_footy import fetch_footy                       # returnerar dict med Footy-fält
from excel_utils import update_kupong, update_footy        # skriver in i Stryktipsanalys_MASTER.xlsx

app = FastAPI(title="Tipsbot API", version="1.0.0")

# Tillåt att din iPad-klient anropar
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # låt vara öppet för enkelhet
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True}

@app.post("/svenskaspel")
def post_svenskaspel(
    url: Optional[str] = Body(default=None),
    svenskaspel: Optional[List[Dict[str, Any]]] = Body(default=None),
) -> Dict[str, Any]:
    """
    Anropa på två sätt:

    1) Scrapa Stryketanalysen:
       POST /svenskaspel
       {"url":"https://stryketanalysen.se/stryktipset/"}

    2) Skicka data direkt från klienten:
       POST /svenskaspel
       {"svenskaspel":[ {...}, {...} ]}
    """
    if svenskaspel:
        try:
            update_kupong(svenskaspel)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Excel-fel: {e}")
        return {"ok": True, "n": len(svenskaspel), "mode": "direct"}

    if url:
        try:
            rows = scrape_stryketanalysen(url)
        except Exception as e:
            # bubbla upp tydligt felmeddelande till klienten
            raise HTTPException(status_code=502, detail=f"Scrape-fel: {e}")
        try:
            update_kupong(rows)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Excel-fel: {e}")
        return {"ok": True, "n": len(rows), "mode": "scraped"}

    raise HTTPException(status_code=422, detail="Skicka {svenskaspel:[...]} ELLER {url:'...'}.")

@app.post("/footy")
def post_footy(items: List[Dict[str, Any]] = Body(...)) -> Dict[str, Any]:
    """
    Example body:
    [
      {"matchnr": 1, "url": "https://footystats.org/england/...-h2h-stats"},
      {"matchnr": 2, "url": "https://footystats.org/england/...-h2h-stats"}
    ]
    """
    results: List[Dict[str, Any]] = []
    written = 0

    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=422, detail="Skicka en icke-tom lista med objekt {matchnr, url}.")

    for it in items:
        matchnr = it.get("matchnr")
        url = it.get("url")
        if not matchnr or not url:
            results.append({"ok": False, "error": "saknar matchnr/url", "item": it})
            continue

        try:
            data = fetch_footy(url)              # hämta och tolka Footy-sidan
            update_footy(matchnr, data)          # skriv till Excel på raden för matchnr
            results.append({"ok": True, "matchnr": matchnr})
            written += 1
        except Exception as e:
            results.append({"ok": False, "matchnr": matchnr, "error": str(e)})

    if written == 0:
        # om allt misslyckades – returnera 502 med detaljer för felsökning
        raise HTTPException(status_code=502, detail={"items": results})

    return {"ok": True, "written": written, "items": results}

# Valfritt: root svarar 404 för att indikera att API:et inte har startsida
@app.get("/")
def root() -> Dict[str, Any]:
    return {"detail": "Tipsbot API – använd /health, /svenskaspel eller /footy."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=10000, reload=False)
