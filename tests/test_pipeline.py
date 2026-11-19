"""Fluxo completo com Google e sites simulados (sem rede)."""

import asyncio
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db, pipeline
from app.main import app
from app.search_engine import Provider, SearchHit

from . import pages
from .pages import CODE

SITES = {
    "https://alfa.example/p": pages.STORE_A,
    "https://beta.example/x/item": pages.STORE_B,
    "https://c.example/u": pages.STORE_C,
    "https://d.example/denso": pages.STORE_D,
    "https://e.example/tabela": pages.STORE_E,
    "https://www.mahle-aftermarket.com/cat": pages.CATALOG,
    "https://loja.example/busca": pages.LISTING_PAGE,
    "https://blog.example/post": pages.UNRELATED,
    "https://protegido.example/p": pages.CLOUDFLARE,
    "https://norobots.example/p": pages.STORE_A,
    # página encontrada ao pesquisar a referência Bosch: anúncio Bosch que cita o original
    "https://f.example/bosch": pages.jsonld({
        "@type": "Product", "name": "Válvula Bosch 0986AC5123", "mpn": "0986AC5123", "brand": "Bosch",
        "description": "Equivalente ao Toyota 88162-0K021",
        "offers": {"price": "355.50", "itemCondition": "NewCondition"}}),
}


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url.endswith("/robots.txt"):
        if "norobots" in url:
            return httpx.Response(200, text="User-agent: *\nDisallow: /", headers={"content-type": "text/plain"})
        return httpx.Response(404)
    if "protegido" in url:
        return httpx.Response(403, text=pages.CLOUDFLARE, headers={"content-type": "text/html"})
    key = url.split("?")[0]
    if key in SITES:
        return httpx.Response(200, text=SITES[key], headers={"content-type": "text/html; charset=utf-8"})
    return httpx.Response(404, text="nao encontrado", headers={"content-type": "text/html"})


class FakeGoogle(Provider):
    name = "fake"
    calls: list[str] = []

    def available(self):
        return True

    async def page(self, client, query, start):
        FakeGoogle.calls.append(query)
        if start:
            return []
        if "0986AC5123" in query.replace(" ", ""):
            return [SearchHit(url="https://f.example/bosch", position=1, query=query)]
        if query != f'"{CODE}"':
            return []
        urls = [u for u in SITES if "f.example" not in u] + ["https://youtube.com/watch?v=1"]
        return [SearchHit(url=u, position=i + 1, query=query) for i, u in enumerate(urls)]


def mock_client():
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), headers={"User-Agent": "test"})


def run(settings_changes=None):
    settings = db.update_settings(settings_changes or {})
    sid = db.create_search(CODE, CODE)
    job = pipeline.Job(sid, CODE)

    async def go():
        async with mock_client() as c:
            return await pipeline.run_search(job, settings, FakeGoogle(), c)

    return asyncio.run(go()), sid


def test_full_pipeline():
    res, sid = run()
    s = res["stats"]
    sec = res["sections"]
    assert s["google_results"] == 11   # 10 sites + 1 da pesquisa da referência (youtube ignorado)
    assert s["sites_failed"] == 2      # cloudflare + robots.txt
    orig = sec["original"]
    # menor preço primeiro
    assert [d["price"] for d in orig] == sorted(d["price"] for d in orig)
    assert {d["domain"] for d in orig} == {"alfa.example", "beta.example", "c.example", "loja.example"}
    assert all(d["origin"] == "original" for d in orig)
    # Bosch confirmada por duas tabelas independentes; anúncio veio da pesquisa da referência
    refs = {r["brand"]: r for r in res["crossrefs"]}
    assert refs["Bosch"]["status"] == "confirmada" and refs["Mahle"]["status"] == "confirmada"
    assert refs["Denso"]["status"] == "a_verificar"
    assert [d["brand"] for d in sec["confirmed"]] == ["Bosch"]
    assert sec["confirmed"][0]["price"] == 355.50
    assert [d["brand"] for d in sec["to_verify"]] == ["Denso"]
    assert res["oem"]["brand"] == "Toyota"
    assert s["listings"] == len(orig) + 2
    # incompletos: B não tem condição (não conta), loja.example não tem foto/condição
    assert s["listings_incomplete"] == 0
    # falhas registradas
    fails = {f["domain"]: f["outcome"] for f in db.access_failures()}
    assert fails["protegido.example"] == "blocked" and fails["norobots.example"] == "robots"
    # sem IA: fabricantes sem classificação, nenhum token gasto, reputação desligada
    assert all(m["tier"] == "sem_classificacao" for m in res["manufacturers"].values())
    assert res["reputations"] == {} and res["reputation_enabled"] is False
    assert db.token_report()["total"]["calls"] == 0


def test_pipeline_without_crossref_search():
    res, _ = run({"crossref_search_count": 0})
    assert res["sections"]["confirmed"] == []  # referência confirmada, mas nenhum anúncio dela


def test_ignore_robots_setting():
    res, _ = run({"respect_robots": False, "crossref_search_count": 0})
    assert "norobots.example" in {d["domain"] for d in res["sections"]["original"]}


# ---------------- API ----------------

@pytest.fixture()
def api(monkeypatch):
    monkeypatch.setattr(pipeline, "provider_factory", lambda choice: FakeGoogle())
    monkeypatch.setattr(pipeline, "http_client", mock_client)
    with TestClient(app) as c:
        yield c


def wait(c, sid):
    for _ in range(100):
        r = c.get(f"/api/search/{sid}").json()
        if r["status"] != "running":
            return r
        time.sleep(0.05)
    raise AssertionError("pesquisa não terminou")


def test_api_search_cache_and_history(api):
    assert api.post("/api/search", json={"code": "filtro de oleo"}).status_code == 400
    r = api.post("/api/search", json={"code": "88162-0K021"}).json()
    assert r["cached"] is False
    done = wait(api, r["search_id"])
    assert done["status"] == "done" and done["result"]["stats"]["listings"] >= 5
    # segunda pesquisa (outra formatação do mesmo código) reutiliza o resultado armazenado
    r2 = api.post("/api/search", json={"code": "881620K021"}).json()
    assert r2["cached"] is True and r2["result"]["from_cache"] is True
    assert r2["result"]["collected_at"]
    # atualização manual ignora o armazenamento
    r3 = api.post("/api/search", json={"code": CODE, "refresh": True}).json()
    assert r3["cached"] is False
    wait(api, r3["search_id"])
    hist = api.get("/api/history").json()
    assert len(hist) == 2 and all(h["status"] == "done" for h in hist)
    assert api.get("/api/admin/failures").json()


def test_api_settings_persist(api):
    assert api.get("/api/settings").json()["reputation_enabled"] is False
    assert api.put("/api/settings", json={"reputation_enabled": True}).json()["reputation_enabled"] is True
    assert api.get("/api/settings").json()["reputation_enabled"] is True
    assert api.put("/api/settings", json={"nao_existe": 1}).status_code == 400
    assert api.put("/api/settings", json={"max_results": -1}).status_code == 400


def test_reputation_enabled_without_ai_marks_no_info(api):
    api.put("/api/settings", json={"reputation_enabled": True, "crossref_search_count": 0})
    r = api.post("/api/search", json={"code": CODE}).json()
    res = wait(api, r["search_id"])["result"]
    assert res["reputation_enabled"] is True
    assert res["reputations"] and all(v["overall"] == "sem_informacao" for v in res["reputations"].values())


def test_no_provider_configured(monkeypatch):
    with TestClient(app) as c:
        r = c.post("/api/search", json={"code": CODE}).json()
        res = wait(c, r["search_id"])
        assert res["status"] == "error" and "SERPAPI_KEY" in res["error"]
