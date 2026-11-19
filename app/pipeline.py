"""Orquestração da pesquisa: Google -> acesso às páginas -> extração -> referências cruzadas ->
organização (deduplicação, separação, ordenação) -> análises de IA -> armazenamento."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from . import ai, brands, codes, config, db
from .crossref import CrossRefCollector
from .extractor import Listing, PageData, extract_page
from .fetcher import Fetcher
from .search_engine import Provider, SearchHit, pick_provider, search_code

log = logging.getLogger("buscador")

TRACKING = re.compile(r"^(utm_|gclid|fbclid|srsltid|ref$|tracking|matt_|_gl$|gad_)", re.I)


@dataclass
class Job:
    id: int
    code: str
    status: str = "running"        # running | done | error
    stage: str = "Iniciando"
    progress: dict = field(default_factory=dict)
    result: dict | None = None
    error: str = ""
    started: float = field(default_factory=time.time)

    def view(self) -> dict:
        return {"id": self.id, "code": self.code, "status": self.status, "stage": self.stage,
                "progress": self.progress, "error": self.error,
                "elapsed": round(time.time() - self.started, 1)}


JOBS: dict[int, Job] = {}
_TASKS: set[asyncio.Task] = set()

# Permite trocar o mecanismo de pesquisa e o cliente HTTP nos testes
provider_factory = pick_provider


def canonical_url(url: str) -> str:
    p = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)]
    return urlunsplit((p.scheme, p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), urlencode(q), ""))


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={
        "User-Agent": config.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
    }, follow_redirects=True)


def start(code: str, refresh: bool = False) -> dict:
    """Inicia a pesquisa (ou devolve resultado armazenado ainda válido)."""
    code = codes.validate(code)
    norm = codes.normalize(code)
    settings = db.get_settings()
    if not refresh:
        cached = db.latest_valid_search(norm, int(settings["cache_hours"]))
        if cached and cached.get("result"):
            res = cached["result"]
            res["from_cache"] = True
            res["collected_at"] = cached["collected_at"]
            return {"cached": True, "search_id": cached["id"], "result": res}
    for job in JOBS.values():  # evita duas coletas simultâneas do mesmo código
        if job.status == "running" and codes.normalize(job.code) == norm:
            return {"cached": False, "search_id": job.id, "job": job.view()}
    search_id = db.create_search(code, norm)
    job = Job(search_id, code)
    JOBS[search_id] = job
    task = asyncio.get_running_loop().create_task(_run_job(job, settings))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return {"cached": False, "search_id": search_id, "job": job.view()}


async def _run_job(job: Job, settings: dict) -> None:
    try:
        provider = provider_factory(settings["search_provider"])
        async with http_client() as client:
            result = await run_search(job, settings, provider, client)
        job.result = result
        job.status = "done"
        job.stage = "Concluído"
        db.finish_search(job.id, "done", result["stats"], result)
    except Exception as e:  # registra a falha para o usuário e para o painel
        log.exception("falha na pesquisa %s", job.code)
        job.status = "error"
        job.error = str(e) or type(e).__name__
        db.finish_search(job.id, "error", job.progress or None, None, job.error)


async def _fetch_and_extract(fetcher: Fetcher, hit: SearchHit, code: str, search_id: int,
                             use_browser: bool) -> PageData | None:
    res = await fetcher.fetch(hit.url)
    page = None
    if res.ok:
        page = extract_page(res.html, res.final_url or hit.url, code)
    js_like = res.ok and (page is None or (not page.listings and len(page.text) < 800))
    if use_browser and (js_like or res.outcome in ("http_error",)):
        rendered = await fetcher.render(hit.url)
        if rendered.ok:
            res = rendered
            page = extract_page(res.html, hit.url, code)
    db.log_access(search_id, hit.url, hit.domain, res.outcome,
                  res.detail or ("ok (navegador)" if res.via_browser else "ok"))
    if page:
        for li in page.listings:
            li.__dict__["position"] = hit.position
    return page if res.ok else None


async def run_search(job: Job, settings: dict, provider: Provider, client: httpx.AsyncClient) -> dict:
    code = job.code
    sid = job.id
    blocked = {d.strip().lower().removeprefix("www.") for d in settings["blocked_domains"].splitlines() if d.strip()}
    extra_catalogs = {d.strip().lower().removeprefix("www.") for d in settings["catalog_domains"].splitlines()
                      if d.strip()}
    max_results = max(1, min(int(settings["max_results"]), 100))
    warnings: list[str] = []
    p = job.progress

    # Etapa 1 — Google
    job.stage = "Pesquisando o código no Google"
    hits, raw_total = await search_code(client, provider, code, max_results, blocked)
    p.update(google_results=len(hits), google_raw=raw_total)

    # Etapa 2/3 — acesso e extração
    job.stage = f"Acessando {len(hits)} sites"
    fetcher = Fetcher(client, settings)
    use_browser = bool(settings["use_browser"])
    pages: list[PageData] = []
    p.update(sites_accessed=0, sites_failed=0)

    async def one(hit: SearchHit, c: str):
        page = await _fetch_and_extract(fetcher, hit, c, sid, use_browser)
        if page is None:
            p["sites_failed"] += 1
        else:
            p["sites_accessed"] += 1
        return page

    try:
        results = await asyncio.gather(*(one(h, code) for h in hits))
        pages = [pg for pg in results if pg]
        fetched = {canonical_url(h.url) for h in hits}

        collector = CrossRefCollector(code, int(settings["crossref_min_sources"]), extra_catalogs)
        for pg in pages:
            collector.add_page(pg)

        # Pesquisa dos códigos de referência cruzada encontrados
        ref_pages: list[tuple[str, PageData]] = []
        n_refs = int(settings["crossref_search_count"])
        prelim = collector.finalize()[:n_refs] if n_refs else []
        if prelim:
            job.stage = f"Pesquisando {len(prelim)} referência(s) cruzada(s)"
            for ref in prelim:
                try:
                    rhits, _ = await search_code(client, provider, ref.code,
                                                 int(settings["crossref_search_results"]), blocked)
                except Exception as e:
                    warnings.append(f"Falha ao pesquisar a referência {ref.brand} {ref.code}: {e}")
                    continue
                rhits = [h for h in rhits if canonical_url(h.url) not in fetched]
                fetched |= {canonical_url(h.url) for h in rhits}
                p["google_results"] += len(rhits)
                rres = await asyncio.gather(*(one(h, ref.code) for h in rhits))
                for pg in rres:
                    if pg:
                        collector.add_page(pg, about_code=ref.code)
                        ref_pages.append((ref.code, pg))
            p["crossref_searches"] = len(prelim)
    finally:
        await fetcher.close()

    # Interpretação por IA de referências citadas só em texto solto
    if settings["crossref_ai_enabled"] and ai.available():
        ambiguous = [r for r in collector.refs.values() if {e.kind for e in r.evidence} <= {"texto"}][:15]
        if ambiguous:
            job.stage = "IA interpretando referências ambíguas"
            items = [{"id": i, "brand": r.brand, "code": r.code, "snippet": r.evidence[0].snippet}
                     for i, r in enumerate(ambiguous)]
            try:
                verdicts = await ai.interpret_crossrefs(code, items, sid)
                for i, r in enumerate(ambiguous):
                    v = verdicts.get(i)
                    if v and not v["declares_equivalence"]:
                        collector.drop(r.key)
                    elif v:
                        r.ai_note = v.get("note", "")
            except ai.AIError as e:
                warnings.append(f"Interpretação de referências por IA indisponível: {e}")
    refs = collector.finalize()
    ref_by_code = {codes.normalize(r.code): r for r in refs}

    # Etapa 4 — organização
    job.stage = "Organizando resultados"
    all_listings: list[tuple[Listing, str]] = []  # (anúncio, código buscado na página)
    for pg in pages:
        for li in pg.listings:
            all_listings.append((li, code))
    for rcode, pg in ref_pages:
        for li in pg.listings:
            all_listings.append((li, rcode))

    sections = {"original": [], "confirmed": [], "to_verify": []}
    discarded = 0
    seen_urls: set[str] = set()
    seen_keys: set[tuple] = set()
    for li, searched in all_listings:
        cu = canonical_url(li.url)
        dkey = (li.domain, brands.fold(li.title), li.price)
        if cu in seen_urls or (li.title and dkey in seen_keys):
            continue
        seen_urls.add(cu)
        seen_keys.add(dkey)
        d = li.to_dict()
        d["position"] = li.__dict__.get("position", 999)
        d["brand_key"] = brands.brand_key(li.brand)
        d["origin"] = ("original" if brands.is_automaker(li.brand) else "paralelo") if li.brand else ""
        d["incomplete"] = any(m in li.missing for m in ("preço", "nome", "fabricante"))
        d["seller_key"] = _seller_key(li)
        ref = ref_by_code.get(codes.normalize(li.announced_code)) if li.announced_code else None
        if searched == code and li.match == "exact":
            d["section"] = "original"
        elif ref is not None and (li.match == "exact" or searched == code):
            d["section"] = "confirmed" if ref.status == "confirmada" else "to_verify"
            d["ref_status"] = ref.status
            d["ref_reason"] = ref.reason
        elif searched == code and li.match == "mentions":
            d["section"] = "to_verify"
            d["ref_status"] = "a_verificar"
            d["ref_reason"] = f"O anúncio cita o código {code}, mas a equivalência não foi confirmada."
        else:
            discarded += 1
            continue
        sections[d["section"]].append(d)

    groups: dict[tuple, int] = {}
    for sec in sections.values():
        for d in sec:
            if d["announced_code"]:
                g = (d["brand_key"], codes.normalize(d["announced_code"]))
                groups[g] = groups.get(g, 0) + 1
    for sec in sections.values():
        for d in sec:
            g = (d["brand_key"], codes.normalize(d["announced_code"])) if d["announced_code"] else None
            d["same_product_stores"] = groups.get(g, 1) if g else 1
        sec.sort(key=lambda d: (d["price"] is None, d["price"] or 0, d["position"]))

    flat = [d for sec in sections.values() for d in sec]
    automakers = [d["brand"] for d in sections["original"] if d["brand"] and brands.is_automaker(d["brand"])]
    oem_brand = max(set(automakers), key=automakers.count) if automakers else ""

    # Etapa 5 — fabricantes
    manufacturers = await _manufacturers(job, settings, flat, sid, warnings)
    # Etapa 6 — reputação (opcional)
    reputations: dict = {}
    if settings["reputation_enabled"]:
        reputations = await _reputations(job, settings, flat, sid, warnings)

    tokens = db.query("SELECT COALESCE(SUM(input_tokens),0) AS i, COALESCE(SUM(output_tokens),0) AS o, "
                      "COALESCE(SUM(cost_usd),0) AS c FROM token_usage WHERE search_id=?", (sid,))[0]
    stats = {
        "google_results": p.get("google_results", 0),
        "sites_accessed": p.get("sites_accessed", 0),
        "sites_failed": p.get("sites_failed", 0),
        "listings": len(flat),
        "listings_incomplete": sum(1 for d in flat if d["incomplete"]),
        "listings_original": len(sections["original"]),
        "listings_confirmed": len(sections["confirmed"]),
        "listings_to_verify": len(sections["to_verify"]),
        "discarded_without_code": discarded,
        "crossrefs": len(refs),
        "crossrefs_confirmed": sum(1 for r in refs if r.status == "confirmada"),
        "crossref_searches": p.get("crossref_searches", 0),
        "ai_input_tokens": tokens["i"], "ai_output_tokens": tokens["o"], "ai_cost_usd": round(tokens["c"], 4),
    }
    return {
        "search_id": sid, "code": code, "code_norm": codes.normalize(code), "provider": provider.name,
        "collected_at": db.now(), "from_cache": False, "stats": stats,
        "oem": {"code": code, "brand": oem_brand},
        "crossrefs": [r.to_dict() for r in refs],
        "sections": sections, "manufacturers": manufacturers, "reputations": reputations,
        "reputation_enabled": bool(settings["reputation_enabled"]), "warnings": warnings,
    }


def _seller_key(li: Listing) -> str:
    if li.seller and brands.fold(li.seller) not in (brands.fold(li.store), li.domain):
        return f"{li.domain}|{brands.fold(li.seller)}"
    return li.domain


async def _manufacturers(job: Job, settings: dict, flat: list[dict], sid: int, warnings: list[str]) -> dict:
    by_brand: dict[str, list[dict]] = {}
    for d in flat:
        if d["brand_key"]:
            by_brand.setdefault(d["brand_key"], []).append(d)
    if not by_brand:
        return {}
    category = brands.categorize([d["title"] for d in flat])
    ranked = sorted(by_brand.items(), key=lambda kv: -len(kv[1]))
    limit = int(settings["max_brands_analyzed"])
    out: dict[str, dict] = {}
    todo = []
    for i, (key, items) in enumerate(ranked):
        name = items[0]["brand"]
        cached = db.get_manufacturer(key, category, int(settings["manufacturer_cache_days"]))
        if cached:
            out[key] = cached | {"brand": name, "cached": True}
        elif i < limit and settings["manufacturer_ai_enabled"] and ai.available():
            todo.append((key, name, [x["title"] for x in items]))
        else:
            reason = ("Análise por IA desativada nas configurações." if not settings["manufacturer_ai_enabled"]
                      else "IA não configurada (ANTHROPIC_API_KEY)." if not ai.available()
                      else f"Fora do limite de {limit} fabricantes analisados por pesquisa.")
            out[key] = {"brand": name, "tier": "sem_classificacao", "tier_label": ai.TIER_LABELS["sem_classificacao"],
                        "category": category, "justification": reason, "sources": [], "pending": True}
    if todo:
        job.stage = f"IA analisando {len(todo)} fabricante(s)"
        sem = asyncio.Semaphore(3)

        async def run(key, name, examples):
            async with sem:
                try:
                    r = await ai.analyze_manufacturer(name, category, examples, sid)
                    db.save_manufacturer(key, name, category, r)
                    out[key] = r | {"brand": name, "analyzed_at": db.now()}
                except ai.AIError as e:
                    warnings.append(f"Análise do fabricante {name} falhou: {e}")
                    out[key] = {"brand": name, "tier": "sem_classificacao", "category": category,
                                "tier_label": ai.TIER_LABELS["sem_classificacao"],
                                "justification": f"Análise não concluída: {e}", "sources": [], "pending": True}

        await asyncio.gather(*(run(*t) for t in todo))
    return out


async def _reputations(job: Job, settings: dict, flat: list[dict], sid: int, warnings: list[str]) -> dict:
    sellers: dict[str, dict] = {}
    for d in sorted(flat, key=lambda d: (d["price"] is None, d["price"] or 0)):
        sellers.setdefault(d["seller_key"], d)
    out: dict[str, dict] = {}
    todo = []
    limit = int(settings["max_sellers_analyzed"])
    for i, (key, d) in enumerate(sellers.items()):
        name = d["seller"] or d["store"] or d["domain"]
        cached = db.get_reputation(key, int(settings["reputation_cache_days"]))
        if cached:
            out[key] = cached | {"seller": name, "cached": True}
        elif i < limit and ai.available():
            todo.append((key, name, d["domain"]))
        else:
            out[key] = {"seller": name, "overall": "sem_informacao", "pending": True,
                        "summary": "IA não configurada." if not ai.available()
                        else f"Fora do limite de {limit} vendedores analisados por pesquisa."}
    if todo:
        job.stage = f"IA verificando reputação de {len(todo)} vendedor(es)"
        sem = asyncio.Semaphore(3)

        async def run(key, name, domain):
            async with sem:
                try:
                    r = await ai.analyze_seller(name, domain, sid)
                    db.save_reputation(key, name, r)
                    out[key] = r | {"seller": name, "analyzed_at": db.now()}
                except ai.AIError as e:
                    warnings.append(f"Reputação de {name} não verificada: {e}")
                    out[key] = {"seller": name, "overall": "sem_informacao", "pending": True,
                                "summary": f"Verificação não concluída: {e}"}

        await asyncio.gather(*(run(*t) for t in todo))
    return out
