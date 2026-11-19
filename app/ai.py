"""Análises com IA (Claude), usadas apenas onde a programação convencional não resolve:

- classificação de fabricantes por segmento (com pesquisa na web e fontes)
- reputação de vendedores (opcional; desativada não executa nada)
- interpretação de trechos ambíguos de referência cruzada

Cada chamada registra tokens de entrada/saída, modelo, tipo de análise e custo estimado.
Só trechos curtos são enviados — nunca páginas inteiras.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic

from . import config, db

FALLBACK_BETA = "server-side-fallback-2026-07-01"
TIERS = ["premium", "intermediaria", "custo_beneficio", "sem_classificacao"]
TIER_LABELS = {"premium": "Premium / Primeira linha", "intermediaria": "Segunda linha / Intermediária",
               "custo_beneficio": "Custo-benefício", "sem_classificacao": "Sem classificação"}

_client: anthropic.AsyncAnthropic | None = None


def available() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    return bool(os.environ.get("ANTHROPIC_PROFILE")) or (Path.home() / ".config" / "anthropic").exists()


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(max_retries=3, timeout=300)
    return _client


def estimate_cost(model: str, inp: int, out: int, cache_read: int, cache_write: int, searches: int) -> float:
    pin, pout = config.MODEL_PRICES.get(model, config.MODEL_PRICES.get(config.AI_MODEL, (4.0, 20.0)))
    return round((inp * pin + out * pout + cache_read * pin * 0.1 + cache_write * pin * 1.25) / 1e6
                 + searches * config.WEB_SEARCH_PRICE, 6)


class AIError(RuntimeError):
    pass


def _source_schema() -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["title", "url", "type"],
            "properties": {
                "title": {"type": "string"},
                "url": {"type": "string", "description": "URL exatamente como veio na pesquisa"},
                "type": {"type": "string", "enum": ["independente", "fabricante", "varejo", "outro"],
                         "description": "independente = imprensa técnica, testes, certificadoras, "
                                        "associações, avaliações de terceiros; fabricante = site/anúncio "
                                        "da própria marca"}}}


MANUFACTURER_TOOL = {
    "name": "registrar_classificacao",
    "description": "Registra a classificação final do fabricante. Chame exatamente uma vez, ao terminar "
                   "a pesquisa, com as conclusões e as fontes efetivamente consultadas.",
    "strict": True,
    "input_schema": {
        "type": "object", "additionalProperties": False,
        "required": ["tier", "summary", "history", "specialization", "quality_evidence",
                     "certifications", "justification", "sources"],
        "properties": {
            "tier": {"type": "string", "enum": TIERS},
            "summary": {"type": "string", "description": "1-2 frases sobre a marca neste segmento"},
            "history": {"type": "string", "description": "Origem, tempo de mercado, grupo controlador"},
            "specialization": {"type": "string"},
            "quality_evidence": {"type": "string",
                                 "description": "Evidências independentes de qualidade/reputação; "
                                                "vazio se não houver"},
            "certifications": {"type": "array", "items": {"type": "string"}},
            "justification": {"type": "string", "description": "Por que esta classificação, citando fontes"},
            "sources": {"type": "array", "items": _source_schema()},
        }},
}

MANUFACTURER_SYSTEM = """Você avalia fabricantes de autopeças para consumidores brasileiros.
Use a ferramenta de pesquisa na web para reunir evidências sobre a marca NO SEGMENTO informado.
Uma marca pode ser forte num segmento (ex.: filtros) e não em outro (ex.: suspensão).

Classificações:
- premium: posicionamento superior com evidências independentes de qualidade, tecnologia e confiabilidade
  (ex.: fornecedor de equipamento original das montadoras, testes independentes, certificações relevantes).
- intermediaria: posicionamento intermediário, com informações suficientes para sustentar isso.
- custo_beneficio: proposta competitiva de preço e desempenho, com evidências.
- sem_classificacao: informações insuficientes para avaliação responsável.

Regras:
- Publicidade, slogans e textos do próprio fabricante NÃO comprovam qualidade. Marque essas fontes
  como type="fabricante". Só classifique como premium com pelo menos uma fonte independente.
- Na dúvida, use sem_classificacao. Não invente fatos, números, certificações ou URLs.
- Cite somente URLs que apareceram nos resultados da pesquisa.
- Escreva em português, de forma objetiva. Faça no máximo algumas pesquisas.
- Termine chamando a ferramenta registrar_classificacao."""


REPUTATION_TOOL = {
    "name": "registrar_reputacao",
    "description": "Registra a reputação encontrada do vendedor. Chame exatamente uma vez, ao terminar.",
    "strict": True,
    "input_schema": {
        "type": "object", "additionalProperties": False,
        "required": ["overall", "summary", "ratings", "complaints", "resolution_rate", "years_active", "sources"],
        "properties": {
            "overall": {"type": "string", "enum": ["boa", "regular", "ruim", "sem_informacao"]},
            "summary": {"type": "string"},
            "ratings": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["platform", "score", "review_count"],
                "properties": {"platform": {"type": "string"}, "score": {"type": "string"},
                               "review_count": {"type": "string"}}}},
            "complaints": {"type": "string", "description": "Histórico de reclamações; vazio se não encontrado"},
            "resolution_rate": {"type": "string", "description": "Índice de solução; vazio se não encontrado"},
            "years_active": {"type": "string", "description": "Tempo de atuação; vazio se não encontrado"},
            "sources": {"type": "array", "items": _source_schema()},
        }},
}

REPUTATION_SYSTEM = """Você verifica a reputação de lojas e vendedores de autopeças no Brasil.
Pesquise o vendedor informado no Reclame Aqui, no Mercado Livre (reputação do vendedor) e em avaliações
públicas de lojas (ex.: Google, Ebit/Opinião Verificada, Trustpilot).
Procure: nota, quantidade de avaliações, histórico de reclamações, índice de solução, tempo de atuação.
Regras:
- Não invente números. Campo não encontrado fica vazio.
- Ausência de informações NÃO é má reputação: nesse caso use overall="sem_informacao".
- Cuidado com homônimos: só use dados que claramente se referem a este vendedor/domínio.
- Cite somente URLs que apareceram nos resultados da pesquisa.
- Termine chamando a ferramenta registrar_reputacao."""


CROSSREF_TOOL = {
    "name": "registrar_interpretacao",
    "description": "Registra, para cada trecho, se ele declara explicitamente a equivalência.",
    "strict": True,
    "input_schema": {
        "type": "object", "additionalProperties": False, "required": ["items"],
        "properties": {"items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "declares_equivalence", "note"],
            "properties": {"id": {"type": "integer"}, "declares_equivalence": {"type": "boolean"},
                           "note": {"type": "string"}}}}}},
}

CROSSREF_SYSTEM = """Você analisa trechos de páginas de autopeças. Para cada trecho, diga se o texto
declara explicitamente que a peça (marca + código indicados) é equivalente / referência cruzada /
substituta do código original indicado. Menções genéricas, listas de marcas, peças diferentes,
"similar" sem relação clara ou apenas descrições parecidas NÃO são declaração de equivalência.
Responda chamando registrar_interpretacao com um item por trecho."""


async def _run(operation: str, subject: str, search_id: int | None, system: str, prompt: str,
               tool: dict, web_searches: int = 0) -> dict:
    """Executa uma análise e devolve o input da ferramenta de registro. Registra o consumo."""
    tools: list[dict] = [tool]
    if web_searches:
        tools.insert(0, {"type": "web_search_20260209", "name": "web_search", "max_uses": web_searches,
                         "user_location": {"type": "approximate", "country": "BR"}})
    messages: list = [{"role": "user", "content": prompt}]
    totals = {"in": 0, "out": 0, "cr": 0, "cw": 0, "ws": 0}
    model_used = config.AI_MODEL
    seen_urls: set[str] = set()
    result = None
    error = ""
    try:
        for _ in range(5):
            resp = await client().beta.messages.create(
                model=config.AI_MODEL, max_tokens=16000, system=system, messages=messages, tools=tools,
                output_config={"effort": config.AI_EFFORT},
                betas=[FALLBACK_BETA], fallbacks="default",
            )
            model_used = resp.model or model_used
            u = resp.usage
            totals["in"] += u.input_tokens or 0
            totals["out"] += u.output_tokens or 0
            totals["cr"] += getattr(u, "cache_read_input_tokens", 0) or 0
            totals["cw"] += getattr(u, "cache_creation_input_tokens", 0) or 0
            stu = getattr(u, "server_tool_use", None)
            totals["ws"] += (getattr(stu, "web_search_requests", 0) or 0) if stu else 0
            for block in resp.content:
                if block.type == "web_search_tool_result" and isinstance(block.content, list):
                    seen_urls.update(r.url for r in block.content if getattr(r, "url", None))
            if resp.stop_reason == "refusal":
                error = "análise recusada pelo modelo"
                break
            call = next((b for b in resp.content if b.type == "tool_use" and b.name == tool["name"]), None)
            if call is not None and resp.stop_reason != "max_tokens":
                result = dict(call.input)
                break
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "pause_turn":
                continue
            if call is not None:  # truncado
                messages.append({"role": "user", "content": [{
                    "type": "tool_result", "tool_use_id": call.id, "is_error": True,
                    "content": "Resposta truncada. Envie novamente de forma mais concisa."}]})
            else:
                messages.append({"role": "user",
                                 "content": f"Registre o resultado chamando a ferramenta {tool['name']}."})
        else:
            error = "a IA não registrou o resultado"
    except anthropic.APIError as e:
        error = f"{type(e).__name__}: {getattr(e, 'message', str(e))}"[:300]
    finally:
        db.log_tokens(search_id=search_id, operation=operation, subject=subject, model=model_used,
                      input_tokens=totals["in"], output_tokens=totals["out"],
                      cache_read_tokens=totals["cr"], cache_write_tokens=totals["cw"],
                      web_searches=totals["ws"],
                      cost_usd=estimate_cost(model_used, totals["in"], totals["out"], totals["cr"],
                                             totals["cw"], totals["ws"]),
                      ok=1 if result is not None else 0, detail=error)
    if result is None:
        raise AIError(error or "falha na análise")
    if web_searches and "sources" in result:
        # descarta fontes que não vieram da pesquisa (evita URLs inventadas)
        result["sources"] = [s for s in result["sources"] if s.get("url") in seen_urls]
    return result


async def analyze_manufacturer(brand: str, category: str, examples: list[str], search_id: int | None) -> dict:
    prompt = (f"Fabricante: {brand}\nSegmento: {category}\n"
              f"Exemplos de anúncios encontrados: {json.dumps(examples[:3], ensure_ascii=False)}\n"
              "Avalie o posicionamento e a reputação desta marca neste segmento no mercado brasileiro.")
    r = await _run("fabricante", f"{brand} / {category}", search_id, MANUFACTURER_SYSTEM, prompt,
                   MANUFACTURER_TOOL, web_searches=4)
    if r["tier"] == "premium" and not any(s["type"] == "independente" for s in r["sources"]):
        r["tier"] = "sem_classificacao"
        r["justification"] += (" [Rebaixado automaticamente: nenhuma fonte independente confirmou a "
                               "classificação premium.]")
    if r["tier"] != "sem_classificacao" and not r["sources"]:
        r["tier"] = "sem_classificacao"
        r["justification"] += " [Sem fontes verificáveis: classificação não atribuída.]"
    r["tier_label"] = TIER_LABELS[r["tier"]]
    r["category"] = category
    r["model"] = config.AI_MODEL
    return r


async def analyze_seller(seller: str, domain: str, search_id: int | None) -> dict:
    prompt = (f"Vendedor/loja: {seller}\nSite onde o anúncio foi encontrado: {domain}\n"
              "Verifique a reputação deste vendedor.")
    r = await _run("reputacao", seller, search_id, REPUTATION_SYSTEM, prompt, REPUTATION_TOOL, web_searches=3)
    if not r["sources"] and r["overall"] != "sem_informacao":
        r["overall"] = "sem_informacao"
        r["summary"] = "Sem fontes verificáveis. " + r["summary"]
    return r


async def interpret_crossrefs(original_code: str, items: list[dict], search_id: int | None) -> dict[int, dict]:
    """items: [{id, brand, code, snippet}] -> {id: {declares_equivalence, note}}"""
    lines = [f"Código original: {original_code}", ""]
    for it in items:
        lines.append(f"[{it['id']}] Peça: {it['brand']} {it['code']}\nTrecho: {it['snippet'][:300]}\n")
    r = await _run("referencia_cruzada", original_code, search_id, CROSSREF_SYSTEM, "\n".join(lines),
                   CROSSREF_TOOL)
    return {int(i["id"]): i for i in r["items"]}
