"""Páginas HTML de exemplo usadas nos testes (simulam lojas, catálogos e bloqueios)."""

import json

CODE = "881620K021"


def jsonld(product: dict) -> str:
    return f'<script type="application/ld+json">{json.dumps(product)}</script>'


# Loja com JSON-LD completo — anúncio do código original (Toyota)
STORE_A = f"""<html><head><title>Válvula Toyota</title>
<meta property="og:site_name" content="Loja Alfa Peças">
{jsonld({"@context": "https://schema.org", "@type": "Product", "name": "Válvula de expansão ar condicionado Toyota Hilux 88162-0K021",
         "sku": "ALF-991", "mpn": "88162-0K021", "brand": {"@type": "Brand", "name": "Toyota"},
         "image": ["https://img.alfa.example/v.jpg"],
         "offers": {"@type": "Offer", "price": "689.90", "priceCurrency": "BRL",
                    "itemCondition": "https://schema.org/NewCondition", "availability": "https://schema.org/InStock"}})}
</head><body><h1>Válvula de expansão Toyota</h1></body></html>"""

# Loja com microdados — anúncio do código original, mais barato, sem condição informada
STORE_B = """<html><head><title>Valvula</title></head><body>
<div itemscope itemtype="https://schema.org/Product">
  <h1 itemprop="name">Valvula Expansao Hilux 881620K021 Original</h1>
  <img itemprop="image" src="/img/valvula.jpg">
  <span itemprop="brand">Toyota</span>
  <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
    <meta itemprop="price" content="512.00"><span>R$ 512,00</span>
  </div>
</div></body></html>"""

# Anúncio usado, só meta tags + tabela de especificação
STORE_C = """<html><head><title>Válvula usada</title>
<meta property="og:title" content="Válvula Expansão 88162 0K021 Hilux Usada">
<meta property="og:image" content="https://c.example/v.png">
<meta property="product:price:amount" content="250.00">
<meta property="og:type" content="product">
</head><body><table><tr><th>Marca</th><td>Toyota</td></tr><tr><th>Condição</th><td>Usado</td></tr></table></body></html>"""

# Peça paralela Denso que cita o código original e tem tabela de referência cruzada
STORE_D = f"""<html><head><title>Denso</title>
{jsonld({"@type": "Product", "name": "Válvula de Expansão Denso DVE-1234 Hilux", "mpn": "DVE-1234",
         "brand": "Denso", "description": "Substitui o original Toyota 88162-0K021",
         "offers": {"price": 399.0, "priceCurrency": "BRL", "itemCondition": "NewCondition"}})}
</head><body><h2>Referências cruzadas</h2>
<table><tr><th>Marca</th><th>Código</th></tr><tr><td>Toyota</td><td>88162-0K021</td></tr>
<tr><td>Bosch</td><td>0 986 AC5 123</td></tr></table></body></html>"""

# Outra loja com a mesma tabela de referência (segunda fonte independente para Bosch)
STORE_E = """<html><head><title>Tabela</title><meta property="og:type" content="article"></head>
<body><h3>Tabela de aplicação e equivalência</h3>
<table><tr><td>Toyota</td><td>881620K021</td></tr><tr><td>Bosch</td><td>0986AC5123</td></tr>
<tr><td>Mahle</td><td>AVE 99 000P</td></tr></table></body></html>"""

# Catálogo técnico (domínio de fabricante)
CATALOG = """<html><head><title>Catálogo Mahle</title></head><body>
<p>Referência cruzada: Toyota 88162-0K021 equivale a Mahle AVE99000P.</p></body></html>"""

# Página com vários produtos (busca interna da loja)
LISTING_PAGE = f"""<html><head>
{jsonld({"@type": "ItemList", "itemListElement": [
    {"@type": "ListItem", "item": {"@type": "Product", "name": "Válvula Toyota 88162-0K021", "url": "/p/1",
                                    "brand": "Toyota", "offers": {"price": "700,00"}}},
    {"@type": "ListItem", "item": {"@type": "Product", "name": "Filtro de óleo", "url": "/p/2",
                                    "offers": {"price": "30.00"}}}]})}
</head><body></body></html>"""

CLOUDFLARE = """<html><head><title>Just a moment...</title></head><body>
<div id="cf-chl-widget">Checking your browser</div></body></html>"""

UNRELATED = """<html><head><title>Blog</title></head><body><p>Dicas de manutenção.</p></body></html>"""
