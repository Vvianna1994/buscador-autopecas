"""Fonte de DEMONSTRAÇÃO com anúncios fictícios.

Serve para testar a interface e o ranking sem chaves de API nem internet.
Ligada automaticamente quando nenhuma fonte real está configurada (ou com DEMO_MODE=1).
"""

import httpx

from ..models import Offer, ParsedQuery
from ..text import stem, tokens
from .base import Source

# (loja, título, preço, frete, marca, referência)
_CATALOG = [
    ("Loja Demo A", "Pastilha Freio Dianteira Gol G5 G6 1.0 1.6 2008 a 2016 Cobreq N-325", 89.90, 0.0, "Cobreq", "N325"),
    ("Loja Demo B", "Jogo Pastilha De Freio Dianteiro Vw Gol Voyage Fox 2009/2015 Bosch", 112.50, 18.90, "Bosch", "0986BB0597"),
    ("Loja Demo C", "Pastilha Freio Dianteira Gol G4 2005 a 2008 Syl", 64.90, 15.00, "Syl", None),
    ("Loja Demo A", "Pastilha Freio Traseira Golf 1.6 2010/2013", 79.90, 0.0, None, None),
    ("Loja Demo D", "Kit Pastilha Freio Dianteira Fras-le Gol Saveiro 2012 2013 2014", 98.00, None, "Fras-le", "PD/580"),
    ("Loja Demo E", "Pastilha de Freio Dianteira Universal Cerâmica", 39.90, 12.00, None, None),
    ("Loja Demo B", "Parafuso Pinça Pastilha Freio Gol", 9.90, 8.00, None, None),
    ("Loja Demo C", "Pastilha Freio Dianteira Onix Prisma 1.0 1.4 2013 a 2019 TRW", 105.00, 0.0, "TRW", None),
    ("Loja Demo D", "Disco De Freio Dianteiro Gol G5 G6 2008 a 2016 Par Fremax", 189.90, 0.0, "Fremax", None),
    ("Loja Demo E", "Pastilha Freio Dianteira Gol 1.0 Cobreq Usada Bom Estado", 35.00, 20.00, "Cobreq", None),
    ("Loja Demo A", "Amortecedor Dianteiro Gol G5 G6 2008 a 2016 Cofap Turbogas Par", 459.90, 0.0, "Cofap", None),
    ("Loja Demo B", "Amortecedor Traseiro Gol G5 G6 2008/2016 Cofap Par", 329.90, 25.00, "Cofap", None),
    ("Loja Demo C", "Amortecedores Dianteiros Gol G5 2009 a 2013 Nakata", 389.00, 0.0, "Nakata", None),
    ("Loja Demo D", "Amortecedor Dianteiro Onix 2013 a 2019 Monroe", 410.00, 0.0, "Monroe", None),
    ("Loja Demo E", "Filtro de Óleo Gol Fox Polo 1.0 1.6 Tecfil PSL55", 22.90, 14.90, "Tecfil", "PSL55"),
    ("Loja Demo A", "Filtro Óleo Mann W712/95 Gol 1.0 8v 2008 em diante", 27.50, 0.0, "Mann", "W71295"),
    ("Loja Demo B", "Filtro De Oleo Onix Prisma Cobalt Spin Tecfil PSL619", 24.90, 9.90, "Tecfil", "PSL619"),
    ("Loja Demo C", "Kit Correia Dentada Tensor Gol 1.0 8v 2008 a 2016 Gates", 219.90, 0.0, "Gates", None),
    ("Loja Demo D", "Correia Dentada Gol 1.6 Power Contitech", 69.90, 15.00, "Continental", None),
    ("Loja Demo E", "Vela de Ignição NGK BKR6E Gol 1.0 1.6 8v Jogo 4 un", 79.90, 0.0, "NGK", "BKR6E"),
    ("Loja Demo A", "Bomba Combustível Gol G5 Flex 2009/2014 Bosch", 249.00, 0.0, "Bosch", None),
    ("Loja Demo B", "Bomba de Gasolina Gol Fox Polo Flex Vdo", 199.90, 22.00, "VDO", None),
    ("Loja Demo C", "Kit Embreagem Gol 1.0 8v G5 G6 2008 a 2014 Sachs", 489.00, 0.0, "Sachs", None),
    ("Loja Demo D", "Kit Embreagem Onix 1.0 2013 a 2019 Luk", 520.00, 0.0, "LUK", None),
    ("Loja Demo E", "Farol Dianteiro Gol G5 2009 2010 2011 2012 Lado Esquerdo", 289.00, 35.00, None, None),
    ("Loja Demo A", "Farol Gol G5 2009 a 2012 Lado Direito", 279.00, 0.0, None, None),
]


class DemoSource(Source):
    name = "Demonstração"

    async def search(self, client: httpx.AsyncClient, pq: ParsedQuery, limit: int) -> list[Offer]:
        wanted = set(pq.part_terms) or {stem(t) for t in tokens(pq.raw)}
        out = []
        for store, title, price, ship, brand, ref in _CATALOG:
            if wanted & {stem(t) for t in tokens(title)}:
                out.append(Offer(source=self.name, store=store, title=title, price=price,
                                 shipping=ship, url="https://example.com/demo",
                                 condition="used" if "Usad" in title else "new",
                                 part_brand=brand, reference=ref))
        return out[:limit]
