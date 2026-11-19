"""Configuração: variáveis de ambiente (segredos) e valores padrão das configurações.

Segredos (chaves de API) ficam só no ambiente / arquivo .env.
As configurações que o usuário altera pela tela ficam no SQLite (tabela settings)
e usam os padrões de DEFAULT_SETTINGS.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


DB_PATH = Path(env("DB_PATH", str(ROOT / "data" / "buscador.db")))

# Mecanismo de pesquisa (resultados do Google)
SERPAPI_KEY = lambda: env("SERPAPI_KEY")  # noqa: E731
GOOGLE_CSE_KEY = lambda: env("GOOGLE_CSE_KEY")  # noqa: E731
GOOGLE_CSE_CX = lambda: env("GOOGLE_CSE_CX")  # noqa: E731

# IA (Claude). O SDK também aceita ANTHROPIC_AUTH_TOKEN ou perfil do `ant auth login`.
AI_MODEL = env("AI_MODEL", "claude-opus-5-5")
AI_EFFORT = env("AI_EFFORT", "medium")

USER_AGENT = env(
    "USER_AGENT",
    "BuscadorAutopecas/1.0 (+buscador de precos de autopecas; respeita robots.txt)",
)

# Preço por milhão de tokens (US$) usado na estimativa de custo. Ajuste se mudar o modelo.
MODEL_PRICES = {
    "claude-fable-5-2": (8.00, 40.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
WEB_SEARCH_PRICE = 10.00 / 1000  # US$ por pesquisa feita pela ferramenta web_search

# Configurações editáveis pela tela (padrões)
DEFAULT_SETTINGS: dict = {
    "reputation_enabled": False,        # reputação de vendedores (opcional, consome tokens)
    "manufacturer_ai_enabled": True,    # classificação de fabricantes por IA
    "crossref_ai_enabled": True,        # IA interpreta trechos ambíguos de referência cruzada
    "search_provider": "auto",          # auto | serpapi | google_cse
    "max_results": 50,                  # resultados do Google por pesquisa (meta: até 50)
    "crossref_search_count": 3,         # quantas referências cruzadas pesquisar em seguida
    "crossref_search_results": 10,      # resultados por pesquisa de referência cruzada
    "crossref_min_sources": 2,          # fontes independentes para confirmar sem catálogo
    "cache_hours": 24,                  # validade dos resultados armazenados
    "respect_robots": True,             # obedecer robots.txt
    "use_browser": False,               # Playwright para páginas dinâmicas (mais lento)
    "fetch_concurrency": 8,
    "fetch_timeout": 15,
    "max_brands_analyzed": 8,           # fabricantes analisados por pesquisa
    "max_sellers_analyzed": 10,         # vendedores analisados por pesquisa
    "manufacturer_cache_days": 90,
    "reputation_cache_days": 30,
    "blocked_domains": "",              # domínios ignorados (um por linha)
    "catalog_domains": "",              # domínios extras tratados como catálogo técnico
}
