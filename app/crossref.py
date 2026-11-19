"""Referências cruzadas: identificação convencional de pares (fabricante, código) que as
páginas apresentam como equivalentes ao código pesquisado.

Regra de confirmação (não basta descrição parecida):
- "confirmada": o par aparece num domínio de fabricante/catálogo técnico, OU numa tabela de
  referência cruzada/aplicação em pelo menos N domínios independentes (configurável).
- "a_verificar": citado só em anúncios ou textos soltos, ou numa única fonte.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import brands, codes
from .extractor import PageData

KEYWORDS = re.compile(
    r"refer[eê]ncias?\s+cruzadas?|cross[\s-]?reference|equival[eê]n|equivalente|similares?|"
    r"intercambi[aá]v|substitui|compat[ií]vel com|c[oó]digos?\s+(de\s+)?refer[eê]ncia|"
    r"outras?\s+refer[eê]ncias|refer[eê]ncias?|aplica[cç][aã]o|conversão|conversao|"
    r"c[oó]digo\s+original|n[uú]mero\s+original|oem",
    re.IGNORECASE)
CODE_TOKEN = re.compile(r"[A-Z0-9][A-Z0-9.\-/ ]{2,22}[A-Z0-9]", re.IGNORECASE)
CONFIRM_KINDS = {"catalogo", "tabela"}


@dataclass
class Evidence:
    url: str
    domain: str
    kind: str            # catalogo | tabela | texto | anuncio
    snippet: str = ""


@dataclass
class CrossRef:
    brand: str
    code: str
    evidence: list[Evidence] = field(default_factory=list)
    status: str = "a_verificar"     # confirmada | a_verificar
    reason: str = ""
    ai_note: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return brands.brand_key(self.brand), codes.normalize(self.code)

    def to_dict(self) -> dict:
        return {"brand": self.brand, "code": self.code, "status": self.status, "reason": self.reason,
                "ai_note": self.ai_note,
                "sources": [e.__dict__ for e in self.evidence],
                "domains": sorted({e.domain for e in self.evidence})}


def _canonical_brand(raw: str) -> str:
    return brands.canonical_maker(raw) or raw.strip().title()


def _first_code_after(text: str, start: int) -> str | None:
    window = text[start:start + 40]
    # aceita grupos separados por espaço/ponto/hífen, desde que cada grupo extra tenha dígito
    # (ex.: "0 986 4B2 101"), para não engolir a palavra seguinte
    m = re.match(r"\s*[:\-–]?\s*(?:c[oó]d(?:igo)?\.?\s*|ref\.?\s*)?"
                 r"((?=[A-Z]*\d)[A-Z0-9]+(?:[ .\-/](?=[A-Z]*\d)[A-Z0-9]+){0,4})",
                 window, re.IGNORECASE)
    if m and codes.looks_like_part_code(m.group(1)):
        return m.group(1).strip(".-/ ")
    return None


def pairs_in_text(text: str) -> list[tuple[str, str, str]]:
    """Pares (marca, código, trecho) em trechos de texto com contexto de referência cruzada."""
    out = []
    for km in KEYWORDS.finditer(text):
        seg_start = km.start()
        seg = text[seg_start: seg_start + 700]
        for mm in brands.MAKER_RE.finditer(seg):
            code = _first_code_after(seg, mm.end())
            if code:
                snip = seg[max(0, mm.start() - 80): mm.end() + 60]
                out.append((mm.group(1), code, snip.strip()))
    return out


def pairs_in_tables(page: PageData) -> list[tuple[str, str, str]]:
    """Tabelas com cabeçalho/conteúdo de referência e linhas 'marca | código'."""
    out = []
    if page.soup is None:
        return out
    for table in page.soup.find_all("table"):
        ttext = table.get_text(" ", strip=True)
        context = ttext[:300]
        prev = table.find_previous(["h1", "h2", "h3", "h4", "strong", "p"])
        if prev:
            context += " " + prev.get_text(" ", strip=True)
        if not KEYWORDS.search(context):
            continue
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            maker = next((c for c in cells if brands.canonical_maker(c) or brands.is_automaker(c)), None)
            if not maker:
                continue
            for c in cells:
                if c != maker and codes.looks_like_part_code(c):
                    out.append((maker, c, " | ".join(cells)[:200]))
                    break
    return out


class CrossRefCollector:
    def __init__(self, code: str, min_sources: int = 2, extra_catalogs: set[str] | None = None):
        self.code = code
        self.min_sources = max(1, min_sources)
        self.extra_catalogs = extra_catalogs or set()
        self.refs: dict[tuple[str, str], CrossRef] = {}

    def _add(self, brand: str, code: str, ev: Evidence) -> None:
        if codes.same(code, self.code) or not codes.looks_like_part_code(code):
            return
        brand = _canonical_brand(brand)
        ref = CrossRef(brand, code.upper())
        ref = self.refs.setdefault(ref.key, ref)
        if not any(e.url == ev.url and e.kind == ev.kind for e in ref.evidence):
            ref.evidence.append(ev)

    def add_page(self, page: PageData, about_code: str | None = None) -> None:
        """about_code: código pesquisado nesta página (o original ou uma referência cruzada).
        Páginas de referência cruzada só contam se citarem também o código original."""
        if not codes.contains(page.text, self.code):
            return
        catalog = brands.domain_is_catalog(page.domain, self.extra_catalogs)
        for brand, code, snip in pairs_in_tables(page):
            self._add(brand, code, Evidence(page.url, page.domain, "catalogo" if catalog else "tabela", snip))
        for brand, code, snip in pairs_in_text(page.text):
            self._add(brand, code, Evidence(page.url, page.domain, "catalogo" if catalog else "texto", snip))
        for li in page.listings:
            if li.match == "mentions" and li.announced_code and li.brand and not brands.is_automaker(li.brand):
                self._add(li.brand, li.announced_code,
                          Evidence(li.url, li.domain, "catalogo" if catalog else "anuncio",
                                   f"{li.title} — cita {self.code} ({li.match_where})"[:200]))
        # Página encontrada pela pesquisa de uma referência cruzada, que cita o código original
        if about_code and not codes.same(about_code, self.code):
            for li in page.listings:
                if li.brand and codes.same(li.announced_code, about_code):
                    self._add(li.brand, about_code,
                              Evidence(li.url, li.domain, "catalogo" if catalog else "anuncio",
                                       f"{li.title} — página cita {self.code}"[:200]))

    def drop(self, key: tuple[str, str]) -> None:
        self.refs.pop(key, None)

    def finalize(self) -> list[CrossRef]:
        for ref in self.refs.values():
            kinds = {e.kind for e in ref.evidence}
            table_domains = {e.domain for e in ref.evidence if e.kind in CONFIRM_KINDS}
            all_domains = {e.domain for e in ref.evidence}
            if "catalogo" in kinds:
                ref.status = "confirmada"
                ref.reason = "Consta em site de fabricante/catálogo técnico."
            elif len(table_domains) >= self.min_sources:
                ref.status = "confirmada"
                ref.reason = f"Consta em tabelas de referência de {len(table_domains)} sites independentes."
            else:
                ref.status = "a_verificar"
                ref.reason = (f"Citada em {len(all_domains)} site(s), sem catálogo técnico ou tabelas "
                              f"suficientes para confirmar a equivalência.")
        order = {"confirmada": 0, "a_verificar": 1}
        return sorted(self.refs.values(),
                      key=lambda r: (order[r.status], -len({e.domain for e in r.evidence}), r.brand))
