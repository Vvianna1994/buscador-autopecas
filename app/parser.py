"""Entende uma busca em linguagem natural, ex.:
"pastilha de freio dianteira gol 1.0 2012 cobreq"
-> peça: pastilha freio | veículo: VW Gol 1.0 2012 | posição: dianteira | marca: Cobreq
"""

import re
from datetime import date

from .knowledge import (BRANDS, ENGINE_TAGS, MODELS, PART_BRANDS, POSITIONS, SIDES,
                        STOPWORDS)
from .models import ParsedQuery, Vehicle
from .text import stem, tokens

_ENGINE_RE = re.compile(r"^[1-6]\.[0-9]$")
# Código de peça/OEM: letras+números com 6+ caracteres, ou 7+ dígitos
_OEM_RE = re.compile(r"\b(?:(?=[A-Z0-9\-]*\d)(?=[A-Z0-9\-]*[A-Z])[A-Z0-9\-]{6,}|\d{7,})\b")

MAX_YEAR = date.today().year + 1


def _is_year(tok: str) -> bool:
    return tok.isdigit() and len(tok) == 4 and 1970 <= int(tok) <= MAX_YEAR


def parse_query(raw: str) -> ParsedQuery:
    pq = ParsedQuery(raw=raw)
    toks = tokens(raw)
    used: set[int] = set()

    # códigos OEM (no texto original, em maiúsculas)
    for code in _OEM_RE.findall(raw.upper()):
        if not _is_year(code):
            pq.oem_codes.append(code.replace("-", ""))
    oem_norm = {c.lower() for c in pq.oem_codes}

    # modelo: procura nomes compostos primeiro ("corolla cross" antes de "corolla")
    joined = " ".join(toks)
    for name in sorted(MODELS, key=len, reverse=True):
        m = re.search(rf"(?:^| ){re.escape(name)}(?: |$)", joined)
        if m:
            start = joined[: m.start()].count(" ") + (1 if m.start() > 0 else 0)
            idx = range(start, start + len(name.split()))
            if not used.intersection(idx):
                pq.vehicle.model = name
                pq.vehicle.brand = MODELS[name]
                used.update(idx)
                break

    year_tokens: list[int] = []
    for i, t in enumerate(toks):
        if i in used:
            continue
        if t in BRANDS:
            pq.vehicle.brand = pq.vehicle.brand or BRANDS[t]
            used.add(i)
        elif _is_year(t):
            year_tokens.append(int(t))
            used.add(i)
        elif _ENGINE_RE.match(t):
            pq.vehicle.engine = t
            used.add(i)
        elif t in ENGINE_TAGS:
            used.add(i)  # informativo; não obriga o título a conter
        elif t in POSITIONS:
            pq.position = POSITIONS[t]
            used.add(i)
        elif t in SIDES:
            pq.side = SIDES[t]
            used.add(i)
        elif t in PART_BRANDS:
            pq.part_brand = PART_BRANDS[t]
            used.add(i)
        elif t in oem_norm or t in STOPWORDS:
            used.add(i)

    if year_tokens:
        # "2010 a 2014" -> usa o primeiro ano informado para checar compatibilidade
        pq.vehicle.year = year_tokens[0]

    pq.part_terms = [stem(t) for i, t in enumerate(toks) if i not in used and not t.isdigit()]
    return pq


def describe(pq: ParsedQuery) -> dict:
    v: Vehicle = pq.vehicle
    return {
        "peca": " ".join(pq.part_terms) or None,
        "veiculo": " ".join(x for x in [v.brand, (v.model or "").title() or None, v.engine,
                                         str(v.year) if v.year else None] if x) or None,
        "posicao": pq.position,
        "lado": pq.side,
        "marca_peca": pq.part_brand,
        "codigos": pq.oem_codes,
    }
