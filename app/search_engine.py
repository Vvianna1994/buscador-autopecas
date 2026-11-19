"""Descoberta de páginas: pesquisa do código no Google.

Usa APIs oficiais/autorizadas de resultados do Google, sem raspar a página do Google:
- SerpAPI (engine=google)                 -> SERPAPI_KEY
- Google Programmable Search JSON API     -> GOOGLE_CSE_KEY + GOOGLE_CSE_CX
Não consome tokens de IA.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from . import codes, config

# Domínios que não trazem anúncios nem dados técnicos
SKIP_DOMAINS = {
    "youtube.com", "facebook.com", "instagram.com", "pinterest.com", "twitter.com", "x.com",
    "tiktok.com", "google.com", "google.com.br", "linkedin.com", "reddit.com", "wikipedia.org",
}


class SearchNotConfigured(RuntimeError):
    pass


@dataclass
class SearchHit:
    url: str
    title: str = ""
    snippet: str = ""
    position: int = 0
    query: str = ""
    domain: str = field(default="")

    def __post_init__(self):
        if not self.domain:
            self.domain = domain_of(self.url)


def domain_of(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def _skip(url: str, blocked: set[str]) -> bool:
    d = domain_of(url)
    if not url.startswith(("http://", "https://")):
        return True
    return any(d == s or d.endswith("." + s) for s in SKIP_DOMAINS | blocked)


class Provider:
    name = "base"

    def available(self) -> bool:
        raise NotImplementedError

    async def page(self, client: httpx.AsyncClient, query: str, start: int) -> list[SearchHit]:
        raise NotImplementedError


class SerpApi(Provider):
    name = "serpapi"

    def available(self) -> bool:
        return bool(config.SERPAPI_KEY())

    async def page(self, client, query, start):
        r = await client.get("https://serpapi.com/search.json", params={
            "engine": "google", "q": query, "start": start, "num": 10, "hl": "pt-br", "gl": "br",
            "google_domain": "google.com.br", "api_key": config.SERPAPI_KEY(),
        }, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("error") and "hasn't returned any results" not in data["error"]:
            raise RuntimeError(f"SerpAPI: {data['error']}")
        hits = [SearchHit(url=o.get("link", ""), title=o.get("title", ""), snippet=o.get("snippet", ""),
                          position=start + int(o.get("position") or 0), query=query)
                for o in data.get("organic_results", [])]
        # Resultados de compras exibidos junto da pesquisa normal também são páginas de anúncio
        for o in data.get("inline_shopping_results", []) + data.get("shopping_results", []):
            link = o.get("link") or o.get("product_link") or ""
            if link and "google." not in domain_of(link):
                hits.append(SearchHit(url=link, title=o.get("title", ""), position=start + 99, query=query))
        return hits


class GoogleCse(Provider):
    name = "google_cse"

    def available(self) -> bool:
        return bool(config.GOOGLE_CSE_KEY() and config.GOOGLE_CSE_CX())

    async def page(self, client, query, start):
        if start >= 100:  # limite da API
            return []
        r = await client.get("https://www.googleapis.com/customsearch/v1", params={
            "key": config.GOOGLE_CSE_KEY(), "cx": config.GOOGLE_CSE_CX(), "q": query,
            "start": start + 1, "num": 10, "gl": "br", "hl": "pt-BR",
        }, timeout=30)
        r.raise_for_status()
        return [SearchHit(url=i.get("link", ""), title=i.get("title", ""), snippet=i.get("snippet", ""),
                          position=start + n + 1, query=query)
                for n, i in enumerate(r.json().get("items", []))]


PROVIDERS = {"serpapi": SerpApi, "google_cse": GoogleCse}


def pick_provider(choice: str) -> Provider:
    if choice in PROVIDERS:
        p = PROVIDERS[choice]()
        if p.available():
            return p
        raise SearchNotConfigured(f"O mecanismo '{choice}' não tem chave configurada no arquivo .env.")
    for cls in PROVIDERS.values():
        p = cls()
        if p.available():
            return p
    raise SearchNotConfigured(
        "Nenhum mecanismo de pesquisa configurado. Defina SERPAPI_KEY ou GOOGLE_CSE_KEY + GOOGLE_CSE_CX "
        "no arquivo .env.")


async def search_code(client: httpx.AsyncClient, provider: Provider, code: str, max_results: int,
                      blocked: set[str] | None = None) -> tuple[list[SearchHit], int]:
    """Pesquisa o código (entre aspas) e suas variações até reunir max_results URLs distintas.
    Retorna (resultados, total bruto recebido do Google)."""
    blocked = blocked or set()
    seen: set[str] = set()
    out: list[SearchHit] = []
    raw_total = 0
    for variant in codes.variations(code):
        query = f'"{variant}"'
        start = 0
        while len(out) < max_results and start < 100:
            hits = await provider.page(client, query, start)
            raw_total += len(hits)
            new = 0
            for h in hits:
                key = h.url.split("#")[0].rstrip("/")
                if not h.url or key in seen or _skip(h.url, blocked):
                    continue
                seen.add(key)
                out.append(h)
                new += 1
                if len(out) >= max_results:
                    break
            if len([h for h in hits if h.position < start + 99]) < 10 or new == 0:
                break
            start += 10
        if len(out) >= max_results:
            break
    return out, raw_total
