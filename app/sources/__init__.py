import os

from .base import Source
from .demo import DemoSource
from .google_shopping import GoogleShopping
from .mercadolivre import MercadoLivre
from .vtex import load_vtex_stores


def active_sources() -> list[Source]:
    real: list[Source] = [s for s in (GoogleShopping(), MercadoLivre()) if s.enabled()]
    real += load_vtex_stores()
    if not real or os.getenv("DEMO_MODE") == "1":
        real.append(DemoSource())
    return real
