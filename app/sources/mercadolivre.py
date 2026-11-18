import os

import httpx

from ..models import Offer, ParsedQuery
from .base import Source


class MercadoLivre(Source):
    """API oficial do Mercado Livre Brasil (site MLB). Exige token OAuth (ML_ACCESS_TOKEN)."""

    name = "Mercado Livre"
    URL = "https://api.mercadolibre.com/sites/MLB/search"

    def enabled(self) -> bool:
        return bool(os.getenv("ML_ACCESS_TOKEN"))

    async def search(self, client: httpx.AsyncClient, pq: ParsedQuery, limit: int) -> list[Offer]:
        headers = {"Authorization": f"Bearer {os.environ['ML_ACCESS_TOKEN']}"}
        r = await client.get(self.URL, params={"q": pq.search_text, "limit": min(limit, 50)},
                             headers=headers)
        r.raise_for_status()
        offers = []
        for it in r.json().get("results", []):
            attrs = {a.get("id"): a.get("value_name") for a in it.get("attributes", []) or []}
            free = (it.get("shipping") or {}).get("free_shipping")
            offers.append(Offer(
                source=self.name,
                store=it.get("official_store_name") or (it.get("seller") or {}).get("nickname") or "Mercado Livre",
                title=it.get("title", ""),
                price=float(it.get("price") or 0),
                shipping=0.0 if free else None,
                url=it.get("permalink", ""),
                image=(it.get("thumbnail") or "").replace("http://", "https://") or None,
                condition=it.get("condition"),
                part_brand=attrs.get("BRAND"),
                reference=attrs.get("PART_NUMBER") or attrs.get("OEM"),
            ))
        return offers
