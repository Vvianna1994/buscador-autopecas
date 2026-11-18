"""API e servidor web do buscador de autopeças.

Rodar:  uvicorn app.main:app --reload   e abrir http://localhost:8000
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from .models import Offer, SearchResponse, SourceStatus
from .parser import describe, parse_query
from .ranking import rank
from .sources import active_sources
from .sources.base import USER_AGENT, Source


def _load_dotenv() -> None:
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

app = FastAPI(title="Buscador Inteligente de Autopeças", version="0.1.0")
STATIC = Path(__file__).parent / "static"
SOURCE_TIMEOUT = 12.0
CACHE_TTL = 600
_cache: dict[str, tuple[float, list[Offer], list[SourceStatus]]] = {}


async def _run_source(client: httpx.AsyncClient, src: Source, pq, limit: int):
    t0 = time.perf_counter()
    try:
        offers = await asyncio.wait_for(src.search(client, pq, limit), SOURCE_TIMEOUT)
        st = SourceStatus(name=src.name, ok=True, count=len(offers))
    except Exception as e:  # uma fonte com problema não derruba a busca
        offers = []
        msg = f"HTTP {e.response.status_code}" if isinstance(e, httpx.HTTPStatusError) else (
            str(e) or type(e).__name__)
        st = SourceStatus(name=src.name, ok=False, error=msg[:200])
    st.elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return offers, st


async def gather_offers(pq, limit: int = 50) -> tuple[list[Offer], list[SourceStatus]]:
    key = pq.search_text.lower()
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1], hit[2]
    sources = active_sources()
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, follow_redirects=True,
                                 timeout=SOURCE_TIMEOUT) as client:
        results = await asyncio.gather(*(_run_source(client, s, pq, limit) for s in sources))
    offers = [o for res, _ in results for o in res]
    statuses = [st for _, st in results]
    _cache[key] = (time.time(), offers, statuses)
    return offers, statuses


@app.get("/api/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=2, description="Ex.: pastilha freio dianteira gol 1.0 2012"),
    sort: str = Query("valor", pattern="^(valor|preco|relevancia)$"),
    only_compatible: bool = False,
    limit: int = Query(50, ge=1, le=100),
):
    pq = parse_query(q)
    offers, statuses = await gather_offers(pq, limit)
    results, stats = rank(pq, offers, sort=sort, only_compatible=only_compatible)
    stats["entendimento"] = describe(pq)
    return SearchResponse(query=pq, sources=statuses, stats=stats, results=results)


@app.get("/api/parse")
def parse(q: str):
    pq = parse_query(q)
    return {"query": pq, "entendimento": describe(pq)}


@app.get("/api/sources")
def sources():
    return [{"name": s.name} for s in active_sources()]


@app.get("/")
def index():
    path = STATIC / "index.html"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)
