import os
import re

import httpx

from ..models import Offer, ParsedQuery
from .base import Source, parse_brl


class GoogleShopping(Source):
    """Google Shopping via SerpAPI: agrega ofertas de centenas de lojas brasileiras.

    É a forma mais ampla e estável de "varrer a internet" sem manter um scraper por loja.
    """

    name = "Google Shopping"
    URL = "https://serpapi.com/search.json"

    def enabled(self) -> bool:
        return bool(os.getenv("SERPAPI_KEY"))

    async def search(self, client: httpx.AsyncClient, pq: ParsedQuery, limit: int) -> list[Offer]:
        params = {
            "engine": "google_shopping", "q": pq.search_text, "gl": "br", "hl": "pt-br",
            "google_domain": "google.com.br", "num": min(limit, 100),
            "api_key": os.environ["SERPAPI_KEY"],
        }
        r = await client.get(self.URL, params=params)
        r.raise_for_status()
        offers = []
        for it in r.json().get("shopping_results", []):
            price = it.get("extracted_price") or parse_brl(it.get("price"))
            if not price:
                continue
            delivery = (it.get("delivery") or "").lower()
            m = re.search(r"r\$\s*([\d.,]+)", delivery)
            if "grátis" in delivery or "gratis" in delivery:
                shipping = 0.0
            else:
                shipping = parse_brl(m.group(1)) if m else None
            offers.append(Offer(
                source=self.name,
                store=it.get("source") or "Loja",
                title=it.get("title", ""),
                price=float(price),
                shipping=shipping,
                url=it.get("link") or it.get("product_link") or "",
                image=it.get("thumbnail"),
                condition="used" if "usad" in (it.get("second_hand_condition") or "").lower() else "new",
            ))
        return offers
