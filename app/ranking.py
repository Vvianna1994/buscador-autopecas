"""Pontua cada anúncio: relevância, compatibilidade com o veículo e custo-benefício."""

from __future__ import annotations

import re
import statistics
from datetime import date

from .knowledge import ACCESSORY_WORDS, MODELS, PART_BRANDS, POSITIONS, SIDES, SOFT_WORDS, SYNONYMS
from .models import Offer, ParsedQuery, RankedOffer
from .text import has_phrase, normalize, stem, tokens

_RANGE_RE = re.compile(r"\b(\d{2}|\d{4})\s*(?:a|ate|ao|/|-|~)\s*(\d{2}|\d{4})\b")
_OPEN_RE = re.compile(r"\b(\d{2}|\d{4})\s*(?:em diante|\+|ate hoje|a atual|ao atual)")
_YEAR_RE = re.compile(r"\b((?:19[89]|20[0-3])\d)\b")
MAX_YEAR = date.today().year + 1


def _full_year(y: str) -> int:
    n = int(y)
    if len(y) == 4:
        return n
    return 2000 + n if n <= (MAX_YEAR % 100) else 1900 + n


def years_in_title(title: str) -> set[int]:
    """Extrai os anos cobertos por um anúncio: '08 a 14', '2010/2013', '2015 em diante'."""
    t = normalize(title)
    years: set[int] = set()
    for a, b in _RANGE_RE.findall(t):
        ya, yb = _full_year(a), _full_year(b)
        if 1980 <= ya <= yb <= MAX_YEAR and yb - ya <= 30:
            years.update(range(ya, yb + 1))
    for a in _OPEN_RE.findall(t):
        ya = _full_year(a)
        if 1980 <= ya <= MAX_YEAR:
            years.update(range(ya, MAX_YEAR + 1))
    years.update(int(y) for y in _YEAR_RE.findall(t) if int(y) <= MAX_YEAR)
    return years


def _term_present(term: str, title_stems: set[str]) -> bool:
    return term in title_stems or bool(SYNONYMS.get(term, set()) & title_stems)


def score_offer(pq: ParsedQuery, offer: Offer) -> RankedOffer:
    toks = tokens(offer.title + " " + (offer.part_brand or ""))
    stems = {stem(t) for t in toks}
    matches: list[str] = []
    warnings: list[str] = []
    score = 0.0
    incompatible = False
    vehicle_hits = 0

    # 1) a peça certa? (até 45 pts)
    required = [t for t in pq.part_terms if t not in SOFT_WORDS]
    if required:
        hit = sum(_term_present(t, stems) for t in required)
        score += 45 * hit / len(required)
        if hit == len(required):
            matches.append("peça")
        if not _term_present(required[0], stems):
            # a 1ª palavra é o núcleo ("pastilha" em "pastilha de freio")
            score -= 30
            warnings.append(f"Parece ser outra peça (não cita “{required[0]}”)")
        extras = (stems & ACCESSORY_WORDS) - set(required)
        if extras:
            score -= 35
            warnings.append(f"Parece acessório/componente: {', '.join(sorted(extras))}")
    else:
        score += 45

    # 2) código OEM / referência exata (bônus forte)
    ref = normalize(offer.reference or "").replace("-", "").replace(" ", "")
    title_compact = normalize(offer.title).replace("-", "").replace(" ", "")
    for code in pq.oem_codes:
        c = code.lower()
        if c and (c == ref or c in title_compact):
            score += 35
            matches.append(f"código {code}")
            break

    # 3) veículo
    v = pq.vehicle
    if v.model:
        if has_phrase(toks, v.model):
            score += 20
            vehicle_hits += 1
            matches.append(v.model.title())
        else:
            other = [m for m in MODELS if len(m) > 2 and has_phrase(toks, m)]
            if other:
                score -= 15
                incompatible = True
                warnings.append(f"Anúncio cita outro(s) modelo(s): {', '.join(o.title() for o in other[:3])}")
            else:
                warnings.append(f"Não cita o modelo {v.model.title()}")
    if v.year:
        yrs = years_in_title(offer.title)
        if v.year in yrs:
            score += 15
            vehicle_hits += 1
            matches.append(f"ano {v.year}")
        elif yrs:
            score -= 25
            incompatible = True
            warnings.append(f"Anos do anúncio: {min(yrs)}–{max(yrs)} (não inclui {v.year})")
    if v.engine:
        engines = {t for t in toks if re.fullmatch(r"[1-6]\.[0-9]", t)}
        if v.engine in engines:
            score += 5
            matches.append(f"motor {v.engine}")
        elif engines:
            score -= 10
            warnings.append(f"Motor do anúncio: {', '.join(sorted(engines))}")

    # 4) posição e lado
    title_positions = {POSITIONS[t] for t in toks if t in POSITIONS}
    if pq.position:
        if pq.position in title_positions:
            score += 10
            matches.append(pq.position)
        elif title_positions:
            score -= 30
            incompatible = True
            warnings.append(f"Posição do anúncio: {', '.join(title_positions)}")
    title_sides = {SIDES[t] for t in toks if t in SIDES}
    if pq.side and title_sides and pq.side not in title_sides:
        score -= 20
        incompatible = True
        warnings.append(f"Lado do anúncio: {', '.join(title_sides)}")

    # 5) marca da peça e estado
    if pq.part_brand:
        brand_norm = normalize(pq.part_brand)
        if brand_norm in normalize(offer.title + " " + (offer.part_brand or "")) or any(
            PART_BRANDS.get(t) == pq.part_brand for t in toks
        ):
            score += 5
            matches.append(pq.part_brand)
    if offer.condition == "used":
        score -= 15
        warnings.append("Peça usada")

    relevance = max(0.0, min(100.0, score))

    if incompatible:
        compat = "incompativel"
    elif (v.model or v.year) and vehicle_hits == (1 if v.model else 0) + (1 if v.year else 0):
        compat = "confirmada"
    elif vehicle_hits:
        compat = "provavel"
    else:
        compat = "verificar"

    return RankedOffer(offer=offer, total=offer.total, relevance=round(relevance, 1), value=0,
                       compatibility=compat, matches=matches, warnings=warnings)


def dedupe(offers: list[Offer]) -> list[Offer]:
    """Mesma loja + mesmo título => fica a oferta mais barata."""
    best: dict[tuple[str, str], Offer] = {}
    for o in offers:
        key = (normalize(o.store), " ".join(tokens(o.title)))
        if key not in best or o.total < best[key].total:
            best[key] = o
    return list(best.values())


MIN_RELEVANCE = 40.0


def rank(pq: ParsedQuery, offers: list[Offer], sort: str = "valor",
         only_compatible: bool = False) -> tuple[list[RankedOffer], dict]:
    scored = [score_offer(pq, o) for o in dedupe(offers) if o.price > 0]
    relevant = [r for r in scored if r.relevance >= MIN_RELEVANCE]
    if only_compatible:
        relevant = [r for r in relevant if r.compatibility != "incompativel"]

    stats: dict = {"encontrados": len(scored), "relevantes": len(relevant)}
    if relevant:
        totals = [r.total for r in relevant]
        median = statistics.median(totals)
        cheapest = min(totals)
        stats.update(menor=cheapest, mediana=round(median, 2), maior=max(totals))
        for r in relevant:
            # custo-benefício: relevância pesa sempre; preço modula até 40%
            value = r.relevance * (0.6 + 0.4 * cheapest / r.total)
            if r.total < 0.3 * median and len(relevant) >= 4:
                r.warnings.append("Preço muito abaixo da média: confira se é a peça completa")
                value -= 15
            if r.offer.shipping is None:
                r.warnings.append("Frete não informado")
            if r.compatibility == "incompativel":
                value -= 30
            r.value = round(max(0.0, value), 1)

    key = {
        "preco": lambda r: (r.compatibility == "incompativel", r.total),
        "relevancia": lambda r: (-r.relevance, r.total),
    }.get(sort, lambda r: (-r.value, r.total))
    relevant.sort(key=key)
    return relevant, stats
