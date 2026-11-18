# Buscador Inteligente de Autopeças

Você descreve a peça e o carro em português, por exemplo *"pastilha de freio dianteira gol 1.0 2012 cobreq"*. O buscador então:

1. **Interpreta a busca**: separa peça, montadora/modelo, ano, motor, posição (dianteira/traseira), lado, marca da peça e código OEM (`app/parser.py`).
2. **Consulta todas as fontes em paralelo** (`app/sources/`), com timeout por fonte. Se uma fonte falhar, as outras continuam respondendo.
3. **Confere a compatibilidade** lendo o título de cada anúncio. Reconhece faixas de ano como "08 a 12", "2010/2013" e "2015 em diante", e também posição, lado, outro modelo citado, acessórios ("parafuso da pinça"), peça usada e preço suspeitamente baixo (`app/ranking.py`).
4. **Ordena pelo custo-benefício**, que combina relevância e preço total com frete. Também dá para ordenar por menor preço ou por compatibilidade.

## Rodando

```bash
pip install -r requirements.txt
cp .env.example .env      # preencha as chaves que tiver
uvicorn app.main:app --reload
# abra http://localhost:8000
```

Sem nenhuma chave configurada, o app entra em **modo demonstração**, com anúncios fictícios.

## Fontes

| Fonte | Como ativar | Cobertura |
|---|---|---|
| Google Shopping (SerpAPI) | `SERPAPI_KEY` | Centenas de lojas. É a forma mais ampla de cobrir "a internet toda" |
| Mercado Livre (API oficial) | `ML_ACCESS_TOKEN` (OAuth) | Maior marketplace de autopeças do país |
| Lojas VTEX | domínios em `stores.json` | Qualquer loja na plataforma VTEX, pela API pública de catálogo |

Para criar um conector novo, crie uma subclasse de `Source` em `app/sources/` com o método `search()` retornando `list[Offer]` e registre-a em `app/sources/__init__.py`.

## API

- `GET /api/search?q=...&sort=valor|preco|relevancia&only_compatible=true`
- `GET /api/parse?q=...` mostra como a busca foi interpretada

## Testes

```bash
python -m pytest -q
```

## Próximos passos sugeridos

- Usar um LLM para extrair a compatibilidade de anúncios com títulos confusos e das fichas técnicas
- Cruzar com uma tabela de aplicação (código OEM ↔ veículos) para confirmar a compatibilidade com certeza
- Guardar o histórico de preços (SQLite) e criar alertas de queda de preço
- Calcular o frete real por CEP
