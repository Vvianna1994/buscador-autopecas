from __future__ import annotations

import httpx

from ..models import Offer, ParsedQuery

USER_AGENT = "Mozilla/5.0 (compatible; BuscadorAutopecas/0.1)"


class Source:
    """Interface de um conector. Para adicionar uma loja nova, crie uma subclasse."""

    name: str = "fonte"

    def enabled(self) -> bool:
        return True

    async def search(self, client: httpx.AsyncClient, pq: ParsedQuery, limit: int) -> list[Offer]:
        raise NotImplementedError


def parse_brl(value) -> float | None:
    """Converte 'R$ 1.234,56' / 1234.56 em float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace("R$", "").replace("\xa0", "").strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
