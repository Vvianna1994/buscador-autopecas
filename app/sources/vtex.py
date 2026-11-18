"""Conector genérico para lojas na plataforma VTEX (muito comum no varejo brasileiro).

As lojas são configuradas em stores.json — basta adicionar o domínio.
"""

import json
from pathlib import Path

import httpx

from ..models import Offer, ParsedQuery
from .base import Source

STORES_FILE = Path(__file__).resolve().parents[2] / "stores.json"


class VtexStore(Source):
    def __init__(self, name: str, domain: str):
        self.name = name
        self.domain = domain.removeprefix("https://").removeprefix("http://").strip("/")

    async def search(self, client: httpx.AsyncClient, pq: ParsedQuery, limit: int) -> list[Offer]:
        url = f"https://{self.domain}/api/catalog_system/pub/products/search"
        r = await client.get(url, params={"ft": pq.search_text, "_from": 0, "_to": min(limit, 50) - 1})
        r.raise_for_status()
        offers = []
        for p in r.json():
            for item in p.get("items", [])[:1]:
                seller = next((s for s in item.get("sellers", [])
                               if (s.get("commertialOffer") or {}).get("AvailableQuantity", 0) > 0), None)
                if not seller:
                    continue
                price = seller["commertialOffer"].get("Price") or 0
                refs = item.get("referenceId") or []
                images = item.get("images") or []
                offers.append(Offer(
                    source="Lojas VTEX",
                    store=self.name,
                    title=p.get("productName", ""),
                    price=float(price),
                    shipping=None,
                    url=p.get("link", ""),
                    image=images[0].get("imageUrl") if images else None,
                    condition="new",
                    part_brand=p.get("brand"),
                    reference=refs[0].get("Value") if refs else None,
                ))
        return offers


def load_vtex_stores() -> list[VtexStore]:
    if not STORES_FILE.exists():
        return []
    data = json.loads(STORES_FILE.read_text(encoding="utf-8"))
    return [VtexStore(s["name"], s["domain"]) for s in data.get("vtex", []) if s.get("enabled", True)]
