"""Módulo de IA com o cliente da API simulado (sem chamadas reais)."""

import asyncio
from types import SimpleNamespace as NS

import pytest

from app import ai, db


def usage(i=1000, o=200, ws=2):
    return NS(input_tokens=i, output_tokens=o, cache_read_input_tokens=0, cache_creation_input_tokens=0,
              server_tool_use=NS(web_search_requests=ws))


def search_result(*urls):
    return NS(type="web_search_tool_result", content=[NS(url=u) for u in urls])


def tool_call(name, data):
    return NS(type="tool_use", name=name, id="toolu_1", input=data)


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def create(self, **kw):
        self.calls.append(kw)
        return self.responses.pop(0)


@pytest.fixture()
def fake(monkeypatch):
    def install(*responses):
        msgs = FakeMessages(responses)
        monkeypatch.setattr(ai, "client", lambda: NS(beta=NS(messages=msgs)))
        return msgs
    return install


def manu(tier, sources):
    return {"tier": tier, "summary": "s", "history": "h", "specialization": "x", "quality_evidence": "",
            "certifications": [], "justification": "j", "sources": sources}


def test_manufacturer_pause_turn_and_invented_urls(fake):
    msgs = fake(
        NS(model="claude-opus-5-5", stop_reason="pause_turn", usage=usage(),
           content=[search_result("https://a.example/1")]),
        NS(model="claude-opus-5-5", stop_reason="tool_use", usage=usage(500, 100, 0), content=[
            tool_call("registrar_classificacao", manu("intermediaria", [
                {"title": "A", "url": "https://a.example/1", "type": "independente"},
                {"title": "Inventada", "url": "https://inventada.example", "type": "independente"}]))]))
    r = asyncio.run(ai.analyze_manufacturer("Denso", "ar-condicionado", ["x"], 7))
    assert r["tier"] == "intermediaria"
    assert [s["url"] for s in r["sources"]] == ["https://a.example/1"]  # URL inventada descartada
    assert len(msgs.calls) == 2 and msgs.calls[0]["fallbacks"] == "default"
    row = db.token_report()["rows"][0]
    assert (row["input_tokens"], row["output_tokens"], row["web_searches"]) == (1500, 300, 2)
    assert row["operation"] == "fabricante" and row["search_id"] == 7 and row["cost_usd"] > 0


def test_premium_requires_independent_source(fake):
    fake(NS(model="claude-opus-5-5", stop_reason="tool_use", usage=usage(),
            content=[search_result("https://marca.example"),
                     tool_call("registrar_classificacao", manu("premium", [
                         {"title": "Site", "url": "https://marca.example", "type": "fabricante"}]))]))
    r = asyncio.run(ai.analyze_manufacturer("X", "freios", [], None))
    assert r["tier"] == "sem_classificacao" and "Rebaixado" in r["justification"]


def test_refusal_is_logged_and_raises(fake):
    fake(NS(model="claude-opus-5-5", stop_reason="refusal", usage=usage(10, 0, 0), content=[]))
    with pytest.raises(ai.AIError):
        asyncio.run(ai.analyze_seller("Loja", "loja.example", None))
    row = db.token_report()["rows"][0]
    assert row["ok"] == 0 and row["operation"] == "reputacao"


def test_seller_without_sources_is_no_information(fake):
    fake(NS(model="claude-opus-5-5", stop_reason="tool_use", usage=usage(), content=[
        tool_call("registrar_reputacao", {"overall": "ruim", "summary": "?", "ratings": [], "complaints": "",
                                          "resolution_rate": "", "years_active": "", "sources": []})]))
    r = asyncio.run(ai.analyze_seller("Loja", "loja.example", None))
    assert r["overall"] == "sem_informacao"
