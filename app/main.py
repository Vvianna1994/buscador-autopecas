"""Servidor web e API do Buscador Inteligente de Peças Automotivas.

Rodar:  uvicorn app.main:app   e abrir http://localhost:8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, codes, config, db, pipeline
from .search_engine import PROVIDERS

app = FastAPI(title="Buscador Inteligente de Peças Automotivas", version="1.0")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class SearchIn(BaseModel):
    code: str
    refresh: bool = False


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/search")
async def search(body: SearchIn):
    try:
        return pipeline.start(body.code, body.refresh)
    except codes.InvalidCode as e:
        raise HTTPException(400, str(e))


@app.get("/api/search/{search_id}")
def search_status(search_id: int):
    job = pipeline.JOBS.get(search_id)
    if job and job.status == "running":
        return {"status": "running", "job": job.view()}
    row = db.get_search(search_id)
    if not row:
        raise HTTPException(404, "Pesquisa não encontrada")
    if row["status"] == "error":
        return {"status": "error", "error": row.get("error") or "falha na pesquisa"}
    if row["status"] != "done" or not row.get("result"):
        # pesquisa interrompida (ex.: servidor reiniciado durante a coleta)
        return {"status": "error", "error": "A pesquisa não foi concluída. Tente novamente."}
    res = row["result"]
    res["collected_at"] = row["collected_at"]
    res["from_cache"] = job is None
    return {"status": "done", "result": res}


@app.get("/api/history")
def history(limit: int = 30):
    return db.search_history(limit)


@app.get("/api/settings")
def get_settings():
    return db.get_settings()


@app.put("/api/settings")
def put_settings(changes: dict):
    try:
        return db.update_settings(changes)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/status")
def status():
    return {
        "providers": {name: cls().available() for name, cls in PROVIDERS.items()},
        "ai_available": ai.available(),
        "ai_model": config.AI_MODEL,
        "ai_effort": config.AI_EFFORT,
    }


@app.get("/api/admin/failures")
def failures(limit: int = 200):
    return db.access_failures(limit)


@app.get("/api/admin/tokens")
def tokens(limit: int = 200):
    return db.token_report(limit)


@app.get("/api/admin/manufacturers")
def manufacturers(limit: int = 200):
    return db.manufacturer_history(limit)
