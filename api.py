"""
FastAPI API layer for Get JustDial.

- /health         : basic health check
- /config         : returns available cities & searches from JSON
- /scrape/manual  : structured scraping (cities + search)
- /scrape/nl      : natural-language scraping (LLM → cities + search)
- /download       : serves generated CSV files
"""

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List
import os
import json

from dotenv import load_dotenv
from openai import OpenAI

from main import run_single_scrape  # helper in main.py
from batch_scraper import load_json_file



# ---------------------------------------------------------------------------
# LLM / config setup
# ---------------------------------------------------------------------------

load_dotenv()

client = OpenAI()  # uses OPENAI_API_KEY from environment

app = FastAPI(title="Get JustDial")

app.mount("/static", StaticFiles(directory="static"), name="static")


# Serve the main UI at "/"
@app.get("/", response_class=HTMLResponse)
def serve_index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()
# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ManualSearchRequest(BaseModel):
    cities: List[str]         # ["Jaipur"] or ["Jaipur", "Delhi"]
    search: str               # "builders"


class NLSearchRequest(BaseModel):
    query: str                # natural language


# ---------------------------------------------------------------------------
# LLM-powered natural language interpretation
# ---------------------------------------------------------------------------

def interpret_nl_query(query: str) -> ManualSearchRequest:
    """
    Use the LLM to turn a messy natural-language query into a structured
    request: list of cities + a free-text search keyword (not limited to a list).
    """
    cities_list = load_json_file("cities.json", key="cities")

    system_prompt = (
        "You are a parser for JustDial scraping requests.\n"
        "Given a user query, output ONLY a JSON object with keys:\n"
        '  \"cities\": list of 1–5 city names taken from the provided city list '
        '(case-insensitive match), and\n'
        '  \"search\": a short search keyword or phrase (1–4 words) describing '
        "what to look for on JustDial (e.g. 'builders', 'plumbers', "
        "'civil contractors', 'interior designers', 'car mechanics').\n"
        "If user mentions 'all cities', choose several major cities from the list.\n"
        "If a city name is misspelled, choose the closest match from the list.\n"
        "Do NOT restrict the search term to any predefined list; infer it from the user text.\n"
        "Return JSON only, with no extra explanation."
    )

    user_prompt = (
        f"Known cities: {cities_list}\n\n"
        f"User query: {query}\n\n"
        "Return the JSON object now."
    )

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
    )

    raw = completion.choices[0].message.content.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            data = json.loads(raw[start : end + 1])
        else:
            data = {"cities": ["Jaipur"], "search": "builders"}

    cities = data.get("cities") or ["Jaipur"]
    search = data.get("search") or "builders"

    if isinstance(cities, str):
        cities = [cities]

    return ManualSearchRequest(cities=cities, search=search)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def config():
    cities = load_json_file("cities.json", key="cities")
    # No fixed searches anymore; UI / LLM can use free-text search
    return {"cities": cities}


@app.post("/scrape/manual")
def scrape_manual(req: ManualSearchRequest):
    """
    Scrape one or more cities for a structured search term.
    """
    csv_files = []
    for city in req.cities:
        path = run_single_scrape(city, req.search)
        csv_files.append({"city": city, "csv_path": path})

    return {
        "mode": "manual",
        "search": req.search,
        "cities": req.cities,
        "results": csv_files,
    }


@app.post("/scrape/nl")
def scrape_nl(req: NLSearchRequest):
    """
    Natural-language search:
    - LLM parses query into (cities, search)
    - Then we call the same scraper as manual mode
    """
    interpreted = interpret_nl_query(req.query)
    manual_response = scrape_manual(interpreted)
    manual_response["mode"] = "nl"
    manual_response["original_query"] = req.query
    return manual_response


@app.get("/download")
def download(csv_path: str):
    """
    csv_path is like: Scrapped/jaipur_builders.csv
    """
    if not os.path.exists(csv_path):
        return {"error": "file not found"}
    return FileResponse(
        csv_path,
        media_type="text/csv",
        filename=os.path.basename(csv_path),
    )
