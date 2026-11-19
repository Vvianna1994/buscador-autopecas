# Buscador Inteligente de Peças Automotivas

Aplicação web responsiva que pesquisa **somente pelo código da peça**. O fluxo é:

1. Pesquisa o código no Google, entre aspas e com variações de formatação (`881620K021` / `88162-0K021`), até reunir **50 resultados** (configurável).
2. Tenta acessar cada página encontrada. Respeita o `robots.txt`, detecta bloqueios (Cloudflare, captcha, login, HTTP 403/429) e **apenas registra** o bloqueio, sem tentar contorná-lo.
3. Extrai dos anúncios, **sem IA**: nome, código anunciado, código OEM, fabricante, descrição, preço, condição, loja, vendedor, foto e link. As fontes são, em ordem de preferência: JSON-LD schema.org, microdados, meta tags e tabela de especificações.
4. Identifica **referências cruzadas** e pesquisa os códigos equivalentes encontrados.
5. Organiza os anúncios: remove duplicados, agrupa produtos iguais, separa em 3 seções e ordena pelo menor preço.
6. Usa **IA (Claude)** só onde é necessária: classificar fabricantes, avaliar a reputação dos vendedores (opcional) e interpretar trechos ambíguos de referência cruzada.

## Instalação e uso

```bash
pip install -r requirements.txt
playwright install chromium        # opcional, só se for ativar o modo navegador
cp .env.example .env               # preencha as chaves
uvicorn app.main:app --host 0.0.0.0 --port 8000
# abra http://localhost:8000 (no celular: http://IP-DO-COMPUTADOR:8000)
```

| Chave no `.env` | Para quê | Obrigatória? |
|---|---|---|
| `SERPAPI_KEY` **ou** `GOOGLE_CSE_KEY` + `GOOGLE_CSE_CX` | Resultados do Google | Sim |
| `ANTHROPIC_API_KEY` | Classificação de fabricantes, reputação, referências ambíguas | Não. Sem ela, a pesquisa de preços funciona e os fabricantes ficam "Sem classificação" |

A página do Google não é raspada diretamente: a descoberta usa APIs que entregam os resultados do Google. A SerpAPI é a opção recomendada. A API de pesquisa programável do Google não aceita mais clientes novos.

## Regras de funcionamento

**Seções da tela de resultados** (nunca misturadas):

1. **Anúncios do código pesquisado**: o código do produto (MPN, SKU ou especificação) ou o título traz o código pesquisado.
2. **Referências cruzadas confirmadas**: anúncios de códigos de outros fabricantes cuja equivalência foi confirmada.
3. **Compatíveis a verificar**: anúncios que só *citam* o código pesquisado ou trazem uma referência não confirmada.

**Quando uma referência cruzada é confirmada** (`app/crossref.py`): descrições parecidas não bastam. Ela é confirmada quando aparece em site de fabricante ou catálogo técnico (lista em `app/brands.py`, que pode ser ampliada nas configurações), **ou** em tabelas de referência/aplicação de pelo menos **2 sites independentes** (número configurável). Quando a única fonte é o próprio anúncio de uma loja, ela fica como "a verificar".

**Classificação de fabricantes** (Premium, Intermediária, Custo-benefício ou Sem classificação): é feita por segmento (filtros, freios, suspensão etc.), com pesquisa na web, justificativa e fontes. Há controles automáticos:
- URLs citadas pela IA que não vieram da pesquisa são descartadas.
- "Premium" sem nenhuma fonte independente é rebaixado para "Sem classificação", porque publicidade do fabricante não comprova qualidade.
- Uma classificação sem fontes verificáveis vira "Sem classificação".
- As análises ficam armazenadas por 90 dias e são reaproveitadas, para economizar tokens.

**Reputação dos vendedores**: vem **desativada**. Liga e desliga em Configurações, e a escolha fica salva no banco. Desativada, nenhuma consulta é feita e nenhum token é gasto. A falta de informações aparece como "sem informações", nunca como reputação ruim.

**Contadores**: a tela mostra quantos resultados o Google trouxe, quantos sites foram acessados, quantos ficaram sem acesso, quantos anúncios foram identificados e quantos estão incompletos (sem preço, nome ou fabricante). Campos que o anúncio não traz aparecem como "não informado". Nada é inventado.

**Resultados armazenados**: valem por 24 h (configurável). Pesquisar de novo o mesmo código, mesmo em outra formatação, reaproveita o resultado e mostra a data da coleta com o aviso de que os preços podem ter mudado. O botão "Atualizar resultados" faz uma coleta nova.

## Custos e tokens

- A raspagem e a extração não consomem tokens.
- A IA recebe apenas campos curtos (marca, segmento, até 3 títulos, trechos de no máximo 300 caracteres), nunca páginas inteiras.
- Cada chamada fica registrada com tokens de entrada e saída, modelo, tipo de análise, número de pesquisas web e custo estimado. Veja em **Configurações → Consumo de tokens**.
- O modelo padrão é `claude-opus-5-5`, com esforço `medium`. Para reduzir custos, troque `AI_MODEL` (por exemplo, `claude-sonnet-5-5` ou `claude-haiku-5-5`) e/ou `AI_EFFORT=low` no `.env`.
- As chamadas usam o *fallback* do lado do servidor (`fallbacks: "default"`): se o modelo recusar uma análise, a API a refaz automaticamente em outro modelo, e o modelo efetivamente usado fica registrado.

## Painel de configurações e administração

Abas: Configurações (todas as opções acima, fontes de pesquisa e sites ignorados), Pesquisas, Falhas de acesso, Consumo de tokens e Análises de fabricantes.

## Estrutura

```
app/
  main.py           API (FastAPI) e servidor da interface
  pipeline.py       orquestração da pesquisa (tarefa em segundo plano com progresso)
  search_engine.py  pesquisa no Google (SerpAPI / Google CSE)
  fetcher.py        acesso às páginas, robots.txt, detecção de bloqueios, Playwright opcional
  extractor.py      extração convencional dos anúncios
  crossref.py       referências cruzadas e regras de confirmação
  ai.py             análises com Claude e registro de tokens
  codes.py          validação, normalização e localização de códigos
  brands.py         montadoras, fabricantes, catálogos técnicos e categorias
  db.py             SQLite (configurações, histórico, falhas, tokens, análises)
  static/           interface (HTML, CSS, JS)
tests/              testes com Google, sites e IA simulados
```

## API

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/search` `{code, refresh}` | Inicia a pesquisa ou devolve o resultado armazenado |
| GET | `/api/search/{id}` | Progresso ou resultado |
| GET | `/api/history` | Pesquisas realizadas |
| GET/PUT | `/api/settings` | Configurações |
| GET | `/api/status` | Chaves configuradas |
| GET | `/api/admin/failures` · `/tokens` · `/manufacturers` | Painel administrativo |

## Testes

```bash
python -m pytest -q
```

Os testes simulam o Google, as lojas (JSON-LD, microdados, meta tags, páginas de listagem, bloqueio Cloudflare, robots.txt) e a API de IA. Nenhuma chamada externa é feita.
