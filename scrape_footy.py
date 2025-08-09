import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def _to_float(x): 
    try: return float(x.replace(',', '.'))
    except: return None

async def fetch_footy(url: str, debug: bool=False):
    debug_snap = None
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=90000)
        await page.wait_for_timeout(1200)
        html = await page.content()
        if debug:
            debug_snap = html
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # home-away from title
    home = away = None
    title = soup.find(['h1','h2'])
    if title and '-' in title.get_text():
        parts = [t.strip() for t in title.get_text().split('-')]
        if len(parts) >= 2:
            home, away = parts[0], parts[1]

    # Grab triplets for xG/xGA/AVG/Scored/Conceded
    def grab_triples(label):
        all_tr = re.findall(rf"{label}\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)", text, flags=re.I)
        if len(all_tr) >= 2:
            def conv(t): return tuple(_to_float(x) for x in t)
            return conv(all_tr[0]), conv(all_tr[1])  # H then B
        return None

    triples = {}
    for lb in ("xG","xGA","AVG","Scored","Conceded"):
        triples[lb] = grab_triples(lb)

    # PPG heuristics
    def last_number_after(anchor, occur=0):
        ms = list(re.finditer(rf"{anchor}.*?(\d+(?:[.,]\d+)?)", text, flags=re.I))
        if len(ms) > occur:
            return _to_float(ms[occur].group(1))
        return None

    ppg_H_overall = last_number_after("Overall", 0)
    ppg_H_home    = last_number_after("Home", 0)
    ppg_B_overall = last_number_after("Overall", 1)
    ppg_B_away    = last_number_after("Away", 1)

    # Form (heuristic)
    form_H = None
    m = re.search(r"Form.*?([WLDrawX\-– ]{5,})", text, flags=re.I)
    if m: form_H = m.group(1).strip()
    form_B = None

    # H2H
    h2h_txt = None
    m = re.search(r"Head to Head.*?(\d+)\s*-\s*(\d+)\s*-\s*(\d+)", text, flags=re.I)
    if m: h2h_txt = f"{m.group(1)}–{m.group(2)}–{m.group(3)}"

    data = {
        "home": home, "away": away,
        "xG": {"H":{"overall":None,"home":None,"away":None}, "B":{"overall":None,"home":None,"away":None}},
        "xGA":{"H":{"overall":None,"home":None,"away":None}, "B":{"overall":None,"home":None,"away":None}},
        "scored":{"H":{"overall":None,"home":None,"away":None}, "B":{"overall":None,"home":None,"away":None}},
        "conceded":{"H":{"overall":None,"home":None,"away":None}, "B":{"overall":None,"home":None,"away":None}},
        "ppg":{"H":{"overall":ppg_H_overall,"home":ppg_H_home,"away":None},
               "B":{"overall":ppg_B_overall,"home":None,"away":ppg_B_away}},
        "form":{"H":{"last5":form_H,"home5":None,"away5":None},
                "B":{"last5":form_B,"home5":None,"away5":None}},
        "h2h":{"txt":h2h_txt},
        "debug": debug_snap if debug else None
    }

    if triples.get("xG"):
        h,b = triples["xG"]
        data["xG"]["H"]["overall"],data["xG"]["H"]["home"],data["xG"]["H"]["away"] = h
        data["xG"]["B"]["overall"],data["xG"]["B"]["home"],data["xG"]["B"]["away"] = b
    if triples.get("xGA"):
        h,b = triples["xGA"]
        data["xGA"]["H"]["overall"],data["xGA"]["H"]["home"],data["xGA"]["H"]["away"] = h
        data["xGA"]["B"]["overall"],data["xGA"]["B"]["home"],data["xGA"]["B"]["away"] = b
    if triples.get("Scored"):
        h,b = triples["Scored"]
        data["scored"]["H"]["overall"],data["scored"]["H"]["home"],data["scored"]["H"]["away"] = h
        data["scored"]["B"]["overall"],data["scored"]["B"]["home"],data["scored"]["B"]["away"] = b
    if triples.get("Conceded"):
        h,b = triples["Conceded"]
        data["conceded"]["H"]["overall"],data["conceded"]["H"]["home"],data["conceded"]["H"]["away"] = h
        data["conceded"]["B"]["overall"],data["conceded"]["B"]["home"],data["conceded"]["B"]["away"] = b
    if triples.get("AVG"):
        h,b = triples["AVG"]
        data["avg_goals"] = {"H": h[0], "B": b[0]}

    return data
