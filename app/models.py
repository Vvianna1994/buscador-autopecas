from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Vehicle(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine: Optional[str] = None  # ex.: "1.0", "1.6"


class ParsedQuery(BaseModel):
    """O que o buscador entendeu do texto digitado."""

    raw: str
    part_terms: list[str] = Field(default_factory=list)  # ex.: ["pastilha", "freio"]
    vehicle: Vehicle = Field(default_factory=Vehicle)
    position: Optional[str] = None  # dianteira | traseira
    side: Optional[str] = None  # esquerdo | direito
    oem_codes: list[str] = Field(default_factory=list)
    part_brand: Optional[str] = None  # marca da peça preferida (Bosch, Cofap...)

    @property
    def search_text(self) -> str:
        return self.raw.strip()


class Offer(BaseModel):
    """Uma oferta bruta, como veio da fonte."""

    source: str
    store: str
    title: str
    price: float
    shipping: Optional[float] = None  # None = desconhecido
    url: str
    image: Optional[str] = None
    condition: Optional[str] = None  # new | used
    seller: Optional[str] = None
    part_brand: Optional[str] = None
    reference: Optional[str] = None  # código da peça / OEM informado pela loja

    @property
    def total(self) -> float:
        return round(self.price + (self.shipping or 0.0), 2)


class RankedOffer(BaseModel):
    offer: Offer
    total: float
    relevance: float  # 0-100: quanto o anúncio bate com a peça/veículo pedidos
    value: float  # 0-100: custo-benefício (relevância + preço)
    compatibility: str  # confirmada | provavel | verificar | incompativel
    matches: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SourceStatus(BaseModel):
    name: str
    ok: bool
    count: int = 0
    error: Optional[str] = None
    elapsed_ms: int = 0


class SearchResponse(BaseModel):
    query: ParsedQuery
    sources: list[SourceStatus]
    stats: dict
    results: list[RankedOffer]
