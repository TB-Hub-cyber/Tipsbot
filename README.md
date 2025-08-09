# Stryktips API (FastAPI + Playwright) — utan API-nyckel

## Endpoints
- `POST /svenskaspel` — body: `{"url": "<svenskaspel stryktips URL>", "debug": false}`
- `POST /footy` — body: `{"matchnr": 1..13, "url": "<footystats url>", "debug": false}`
- `GET /excel/download` — returnerar Excel byggd från `Stryktipsanalys_MASTER.xlsx`
- `POST /reset` — nollställer serverns minne (kupong/footy)

## Deploy på Render
1. Lägg upp detta repo på GitHub.
2. Skapa ny **Web Service** på https://render.com → koppla repot.
3. Render läser `render.yaml`, installerar Playwright och startar appen.
4. Din bas-URL blir något i stil med `https://<ditt-namn>.onrender.com`.

## Tips
- Om du senare vill låsa ner API:t: lägg till API-nyckel i koden och en env-var i Render.
